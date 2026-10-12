"""Local IFs run comparison. Source databases are always opened read-only."""
import csv
import io
import json
import math
import pathlib
import subprocess
import tempfile
import threading
import uuid
import sqlite3
import sys
import os
import shutil
import time
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import numpy as np
from diagnostics import CORE_VARIABLES, LEDGER_FIELDS, audit_slices, trajectory_metrics
from horizon import coverage, anchored_payload, year_map

ROOT = pathlib.Path(__file__).resolve().parent
FROZEN = getattr(sys, 'frozen', False)
DATA_ROOT = pathlib.Path(os.environ.get('IFS_VETTING_DATA_DIR') or
                         (pathlib.Path(os.environ.get('LOCALAPPDATA', pathlib.Path.home())) / 'IFsModelVetting'))
DECODER_EXE = ROOT / 'decoder-runtime/Decoder.exe'
DECODER = ROOT / 'decoder/bin/Release/net10.0/Decoder.dll'
SETTINGS = DATA_ROOT / 'settings.json'
JOBS = {}
LOCK = threading.Lock()


def initialize_storage():
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    # Preserve the developer's earlier local data without shipping it to users.
    if not FROZEN and ROOT != DATA_ROOT:
        if (ROOT/'settings.json').exists() and not SETTINGS.exists():
            shutil.copy2(ROOT/'settings.json', SETTINGS)
        for old in (ROOT/'results').glob('*'):
            destination = DATA_ROOT/'results'/old.name
            if old.is_dir() and not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(old, destination)


def empty_installation():
    return {'installation':None,'data':None,'runfiles':None,'runs':[], 'labels':{},'skipped':[]}


def saved_installation():
    try:
        return pathlib.Path(json.loads(SETTINGS.read_text(encoding='utf-8'))['installation'])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def installation_layout(path):
    """IFs installation contract: DATA and RUNFILES directly beneath the root."""
    installation = pathlib.Path(path).expanduser().resolve(strict=True)
    if not installation.is_dir():
        raise ValueError('Select an IFs installation folder')
    missing = [name for name in ('DATA', 'RUNFILES') if not (installation/name).is_dir()]
    if missing:
        raise ValueError('Expected '+', '.join(missing)+' directly inside the IFs installation folder. Select the installation root.')
    data, runfiles = installation/'DATA', installation/'RUNFILES'
    runs, skipped = [], []
    for candidate in sorted(runfiles.rglob('*')):
        if not candidate.is_file() or not candidate.name.lower().endswith(('.run.db', '.run')):
            continue
        try:
            with candidate.open('rb') as stream:
                supported = stream.read(16) == b'SQLite format 3\x00'
            if supported:
                runs.append(str(candidate))
            else:
                skipped.append({'path':str(candidate), 'reason':'Not a SQLite RUN database'})
        except OSError as exc:
            skipped.append({'path':str(candidate), 'reason':str(exc)})
    return {'installation':str(installation), 'data':str(data), 'runfiles':str(runfiles),
            'runs':runs, 'labels':{path:str(pathlib.Path(path).relative_to(runfiles)) for path in runs},
            'skipped':skipped}


def restore_jobs():
    # Browser tabs can continue viewing completed comparisons after a restart.
    for path in (DATA_ROOT/'results').glob('*/report.json'):
        try:
            report=json.loads(path.read_text(encoding='utf-8'))
            report['buckets']={int(dim):{int(key):label for key,label in values.items()}
                               for dim,values in report['buckets'].items()}
            JOBS[path.parent.name]={'status':'complete','progress':'Complete','report':report,'created':path.stat().st_mtime}
        except (ValueError,KeyError,TypeError):
            continue


def connect(path):
    path = pathlib.Path(path).resolve(strict=True)
    return sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)


def metadata(path):
    with closing(connect(path)) as db:
        names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {'ifs_var', 'ifs_var_dim', 'ifs_dim_bucket', 'ifs_var_blob'}
        if not required <= names:
            raise ValueError('Not a supported IFs RUN database: missing ' + ', '.join(sorted(required - names)))
        dims = {}
        for variable, seq, dimension in db.execute('SELECT VariableName, Seq, DimensionId FROM ifs_var_dim ORDER BY VariableName, Seq'):
            dims.setdefault(variable, []).append(dimension)
        buckets = {}
        for dimension, seq, name in db.execute('SELECT DimensionId, Seq, Name FROM ifs_dim_bucket ORDER BY DimensionId, Seq'):
            buckets.setdefault(dimension, {})[seq] = name
        variables = {}
        for name, display, kind in db.execute('SELECT Name, DisplayName, Type FROM ifs_var'):
            if name.isupper():
                variables[name] = {'name': name, 'display': display, 'type': kind, 'dims': dims.get(name, [])}
        return {'variables': variables, 'buckets': buckets, 'core_variables': sorted(CORE_VARIABLES)}


class ComparisonStopped(Exception):
    pass


def check_stop(job):
    if job is not None and (JOBS[job].get('stop_requested') or JOBS.get(JOBS[job].get('_parent'), {}).get('stop_requested')):
        raise ComparisonStopped()


def decode(db, variable, dims, job=None):
    check_stop(job)
    row = db.execute('SELECT Data FROM ifs_var_blob WHERE VariableName=?', (variable,)).fetchone()
    if row is None or row[0] is None:
        raise ValueError('Missing payload for ' + variable)
    with tempfile.TemporaryDirectory(prefix='ifs-vetting-') as folder:
        source, target = pathlib.Path(folder) / 'input.parquet', pathlib.Path(folder) / 'output.bin'
        source.write_bytes(row[0])
        command = [str(DECODER_EXE)] if DECODER_EXE.exists() else ['dotnet', str(DECODER)]
        with subprocess.Popen(command+[str(source),str(target)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0) as process:
            try:
                while True:
                    check_stop(job)
                    try:
                        _, stderr = process.communicate(timeout=0.1)
                        break
                    except subprocess.TimeoutExpired:
                        continue
            except ComparisonStopped:
                process.kill()
                process.communicate()
                raise
            if process.returncode:
                raise ValueError('IFs decoder failed: ' + stderr[-1200:])
        check_stop(job)
        with target.open('rb') as stream:
            header = np.frombuffer(stream.read(8), dtype='<i4')
            axes, count = map(int, header)
            if axes != len(dims):
                raise ValueError('Payload axes disagree with metadata')
            dtype = np.dtype([('keys', '<i2', (axes,)), ('value', '<f4')])
            records = np.fromfile(stream, dtype=dtype)
        if len(records) != count:
            raise ValueError('Truncated decoder output')
        return records


def aligned(a, b):
    # Match exact coordinate tuples; metadata parity alone is insufficient.
    axes = a['keys'].shape[1]
    dtype = np.dtype([(f'k{i}', '<i2') for i in range(axes)])
    ka = np.ascontiguousarray(a['keys']).view(dtype).reshape(-1)
    kb = np.ascontiguousarray(b['keys']).view(dtype).reshape(-1)
    if len(np.unique(ka)) != len(ka) or len(np.unique(kb)) != len(kb):
        raise ValueError('Duplicate payload coordinates')
    common, ia, ib = np.intersect1d(ka, kb, return_indices=True)
    return a['keys'][ia], a['value'][ia].astype(float), b['value'][ib].astype(float), len(a)-len(common), len(b)-len(common)


def calculate(keys, a, b, atol, rtol):
    valid = np.isfinite(a) & np.isfinite(b)
    delta = b - a
    changed = valid & (np.abs(delta) > atol + rtol * np.abs(a))
    relative = np.full(len(a), np.nan)
    np.divide(delta, a, out=relative, where=valid & (a != 0))
    d = delta[valid]
    correlation = None
    if valid.sum() > 1 and np.std(a[valid]) > 0 and np.std(b[valid]) > 0:
        correlation = float(np.corrcoef(a[valid], b[valid])[0, 1])
    metrics = {'points': len(a), 'finite': int(valid.sum()), 'nonfinite': int((~valid).sum()),
               'changed': int(changed.sum()), 'zero_baseline_changed': int((valid & (a == 0) & (b != 0)).sum()),
               'rmse': float(np.sqrt(np.mean(d*d))) if len(d) else None,
               'max_abs_delta': float(np.max(np.abs(d))) if len(d) else None,
               'correlation': correlation}
    return metrics, delta, relative, changed


def compare_pair(job, request):
    directory = pathlib.Path(JOBS[job].get('_directory', DATA_ROOT / 'results' / job))
    directory.mkdir(parents=True, exist_ok=True)
    try:
        ma, mb = metadata(request['a']), metadata(request['b'])
        horizon = coverage(ma['buckets'], mb['buckets'])
        chart_buckets = {**ma['buckets'], 0: {year: str(year) for year in horizon['baseline_years']}}
        atol, rtol = float(request.get('atol', 1e-6)), float(request.get('rtol', 1e-5))
        if not math.isfinite(atol) or not math.isfinite(rtol) or min(atol, rtol) < 0:
            raise ValueError('Tolerances must be finite and nonnegative')
        selected = request['variables']
        summaries, audits = [], []
        with closing(connect(request['a'])) as da, closing(connect(request['b'])) as db, (directory/'differences.csv').open('w', newline='', encoding='utf-8') as output:
            writer = csv.writer(output)
            writer.writerow(['Variable', 'Coordinates', 'Labels', 'Run1', 'Run2', 'Delta', 'RelativeDelta'])
            for index, variable in enumerate(selected):
                check_stop(job)
                with LOCK:
                    progress=f'{index+1}/{len(selected)}: {variable}'
                    JOBS[job].update(progress=progress)
                    parent = JOBS[job].get('_parent')
                    if parent: JOBS[parent].update(progress=JOBS[job]['_label']+' · '+progress)
                try:
                    va, vb = ma['variables'][variable], mb['variables'][variable]
                    dims = va['dims']
                    if dims != vb['dims']:
                        raise ValueError('Dimension order differs between runs')
                    for dim in set(dims):
                        if dim != 0 and ma['buckets'][dim] != mb['buckets'][dim]:
                            raise ValueError(f'Dimension {dim} labels or coverage differ; comparison skipped')
                    a, b = decode(da, variable, dims, job), decode(db, variable, dims, job)
                    check_stop(job)
                    a = anchored_payload(a, dims, ma['buckets'], ma['buckets'])
                    b = anchored_payload(b, dims, mb['buckets'], ma['buckets'])
                    check_stop(job)
                    keys, x, y, only_a, only_b = aligned(a, b)
                    check_stop(job)
                    metrics, delta, relative, changed = calculate(keys, x, y, atol, rtol)
                    check_stop(job)
                    slices = audit_slices(variable, dims, chart_buckets, keys, x, y, atol, rtol)
                    check_stop(job)
                    audits.extend(slices)
                    metrics.update(variable=variable, display=va['display'], dims=dims, only_run1=only_a, only_run2=only_b)
                    expected = math.prod(len(chart_buckets[dim]) for dim in dims)
                    metrics['compared_years'] = sorted(set(map(int, keys[:, dims.index(0)]))) if 0 in dims else []
                    metrics['baseline_year_count'] = len(horizon['baseline_years']) if 0 in dims else None
                    metrics.update(expected_points=expected, payload_points_run1=len(a), payload_points_run2=len(b),
                                   missing_coordinates_run1=max(0, expected-len(a)), missing_coordinates_run2=max(0, expected-len(b)))
                    for row_index, i in enumerate(np.flatnonzero(changed)):
                        if row_index % 256 == 0: check_stop(job)
                        labels = [chart_buckets[dim].get(int(key), f'UNKNOWN:{key}') for dim, key in zip(dims, keys[i])]
                        writer.writerow([variable, json.dumps(keys[i].tolist()), json.dumps(labels), x[i], y[i], delta[i], relative[i] if np.isfinite(relative[i]) else ''])
                    # Store coordinate-level aligned data for charts on demand.
                    check_stop(job)
                    np.savez_compressed(directory / (variable + '.npz'), keys=keys, a=x, b=y, baseline_keys=a['keys'], baseline_values=a['value'], comparison_keys=b['keys'], comparison_values=b['value'])
                    summaries.append(metrics)
                except ComparisonStopped:
                    raise
                except Exception as exc:
                    summaries.append({'variable': variable, 'error': str(exc)})
        if JOBS[job].get('stop_requested'):
            JOBS[job].update(status='stopped', progress='Stopped')
            return
        for lane in ('Core','Dyadic','Other'):
            rows = sorted((row for row in audits if row['lane']==lane),
                          key=lambda row: -(row['mean_smape'] if row['mean_smape'] is not None else -1))
            with (directory/(lane+'_audit.csv')).open('w',newline='',encoding='utf-8') as stream:
                ledger = csv.DictWriter(stream,fieldnames=LEDGER_FIELDS,extrasaction='ignore')
                ledger.writeheader()
                ledger.writerows(rows)
        report = {'run1': request['a'], 'run2': request['b'], 'atol': atol, 'rtol': rtol,
                  'audits': audits,
                  'summaries': summaries, 'buckets': chart_buckets, 'coverage': horizon, 'variables_only_run1': sorted(ma['variables'].keys()-mb['variables'].keys()),
                  'variables_only_run2': sorted(mb['variables'].keys()-ma['variables'].keys())}
        (directory/'report.json').write_text(json.dumps(report, allow_nan=False), encoding='utf-8')
        with LOCK:
            JOBS[job].update(status='complete', report=report, progress='Complete')
    except ComparisonStopped:
        with LOCK:
            JOBS[job].update(status='stopped', progress='Stopped')
    except Exception as exc:
        with LOCK:
            JOBS[job].update(status='failed', error=str(exc))


def comparison_runs(request):
    runs = request.get('comparisons', [request.get('b')])
    if not isinstance(runs, list) or not runs or any(not isinstance(p, str) or not p for p in runs):
        raise ValueError('Select at least one comparison run')
    if len(runs) != len(set(runs)):
        raise ValueError('Select each comparison run only once')
    return runs


def compare(job, request):
    runs = comparison_runs(request)
    directory = DATA_ROOT / 'results' / job
    directory.mkdir(parents=True, exist_ok=True)
    children = []
    try:
        atol, rtol = float(request.get('atol', 1e-6)), float(request.get('rtol', 1e-5))
        if not math.isfinite(atol) or not math.isfinite(rtol) or min(atol, rtol) < 0:
            raise ValueError('Tolerances must be finite and nonnegative')
        baseline = metadata(request['a'])
        years = sorted(year_map(baseline['buckets']).values())
        report = {'schema_version': 2, 'run1': request['a'], 'run2': runs[0],
                  'baseline_years': years, 'comparisons': [], 'summaries': [], 'audits': [],
                  'atol': float(request.get('atol', 1e-6)), 'rtol': float(request.get('rtol', 1e-5)),
                  'buckets': {**baseline['buckets'], 0: {year: str(year) for year in years}},
                  'variables_only_run1': [], 'variables_only_run2': []}
        for index, run in enumerate(runs):
            check_stop(job)
            identity = f'run-{index+1}'
            child = job+'-'+identity
            children.append(child)
            JOBS[child] = {'status': 'running', '_parent': job, '_label': pathlib.Path(run).name,
                           '_directory': str(directory / 'pairs' / identity)}
            compare_pair(child, {**request, 'b': run})
            state = JOBS[child]
            check_stop(job)
            if state['status'] == 'stopped': raise ComparisonStopped()
            if state['status'] != 'complete':
                report['comparisons'].append({'id': identity, 'run': run, 'error': state.get('error', 'Comparison failed')})
                continue
            pair = state['report']
            report['comparisons'].append({'id': identity, 'run': run, 'coverage': pair['coverage'],
                                          'variables_only_run1': pair['variables_only_run1'],
                                          'variables_only_run2': pair['variables_only_run2']})
            for key in ('summaries', 'audits'):
                report[key].extend({**row, 'run_id': identity, 'comparison_run': run} for row in pair[key])
        check_stop(job)
        for filename in ['differences.csv', 'Core_audit.csv', 'Dyadic_audit.csv', 'Other_audit.csv']:
            with (directory/filename).open('w', newline='', encoding='utf-8') as output:
                writer = csv.writer(output)
                header_written = False
                for pair in report['comparisons']:
                    source = directory/'pairs'/pair['id']/filename
                    if not source.exists() or pair.get('error'): continue
                    with source.open(newline='', encoding='utf-8') as stream:
                        reader = csv.reader(stream)
                        header = next(reader)
                        if not header_written: writer.writerow(['ComparisonRun', *header]); header_written = True
                        for row in reader:
                            check_stop(job)
                            writer.writerow([pair['run'], *row])
        check_stop(job)
        (directory/'report.json').write_text(json.dumps(report, allow_nan=False), encoding='utf-8')
        with LOCK: JOBS[job].update(status='complete', report=report, progress='Complete')
    except ComparisonStopped:
        with LOCK: JOBS[job].update(status='stopped', progress='Stopped')
    except Exception as exc:
        with LOCK: JOBS[job].update(status='failed', error=str(exc))
    finally:
        for child in children: JOBS.pop(child, None)


def series_data(job, variable, selectors):
    report = JOBS[job]['report']
    if report.get('schema_version') != 2:
        return None
    pairs = report['comparisons']
    dims = next(row['dims'] for row in report['summaries'] if row['variable'] == variable and not row.get('error'))
    if not dims or dims[0] != 0: raise ValueError('Chart requires a time axis first')
    datasets = []
    for pair in pairs:
        filename = DATA_ROOT/'results'/job/'pairs'/pair['id']/(variable+'.npz')
        if filename.exists():
            with np.load(filename) as saved:
                datasets.append((pair, {key: saved[key] for key in saved.files}))
    if not datasets: raise ValueError('No trajectory data for this indicator')
    baseline = datasets[0][1]
    options = []
    for axis, dim in enumerate(dims[1:], 1):
        values = sorted(set(map(int, baseline['baseline_keys'][:,axis])))
        options.append([{'key': k, 'label': report['buckets'][dim].get(k, str(k))} for k in values])
    chosen = [int(selectors[i]) if i < len(selectors) else opts[0]['key'] for i, opts in enumerate(options)]
    def values_for(keys, values):
        mask = np.ones(len(keys), dtype=bool)
        for axis, value in enumerate(chosen, 1): mask &= keys[:,axis] == value
        return {int(k[0]): float(v) if math.isfinite(v) else None for k,v in zip(keys[mask], values[mask])}
    base_values = values_for(baseline['baseline_keys'], baseline['baseline_values'])
    by_id = {pair['id']: data for pair,data in datasets}
    years = report['baseline_years']
    comparisons, maps = [], []
    for pair in pairs:
        data = by_id.get(pair['id'])
        values = values_for(data['comparison_keys'], data['comparison_values']) if data is not None else {}
        # Never draw an unmatched comparison observation against a missing baseline observation.
        values = {year: value for year,value in values.items() if year in base_values}
        metrics = trajectory_metrics(np.array(years), np.array([base_values.get(y, np.nan) if base_values.get(y) is not None else np.nan for y in years]),
                                     np.array([values.get(y, np.nan) if values.get(y) is not None else np.nan for y in years]), report['atol'], report['rtol'])
        comparisons.append({'id': pair['id'], 'label': pathlib.Path(pair['run']).name, 'metrics': metrics,
                            'coverage': pair.get('coverage'), 'error': pair.get('error') or (None if data is not None else 'Indicator unavailable or incompatible')})
        maps.append(values)
    points = [[year, base_values.get(year), *[values.get(year) for values in maps]] for year in years]
    return {'options': options, 'chosen': chosen, 'points': points, 'dims': dims,
            'baseline_label': pathlib.Path(report['run1']).name, 'comparisons': comparisons,
            'metrics': comparisons[0]['metrics'], 'baseline_years': years}


class Handler(BaseHTTPRequestHandler):
    def send(self, data, content='application/json', status=200):
        body = data if isinstance(data, bytes) else json.dumps(data, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content)
        self.send_header('Content-Length', str(len(body)))
        if content.startswith('text/csv'):
            self.send_header('Content-Disposition', 'attachment; filename="IFsCompanion-export.csv"')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if url.path == '/':
                return self.send((ROOT/'index.html').read_bytes(), 'text/html; charset=utf-8')
            if url.path == '/api/recent':
                with LOCK:
                    entries = []
                    for identity, state in JOBS.items():
                        if state.get('_parent'): continue
                        report = state.get('report', {})
                        a, b = report.get('run1', state.get('run1', '')), report.get('run2', state.get('run2', ''))
                        entries.append({'id': identity, 'status': state['status'], 'created': state.get('created', 0),
                                        'title': pathlib.Path(a).name+' vs '+(str(len(report['comparisons']))+' runs' if len(report.get('comparisons', []))>1 else pathlib.Path(b).name) if a and b else 'Comparison '+identity[:8]})
                return self.send({'jobs': sorted(entries, key=lambda item: item['created'], reverse=True)})
            if url.path == '/audit.js':
                return self.send((ROOT/'audit.js').read_bytes(), 'text/javascript; charset=utf-8')
            if url.path == '/favicon.ico':
                return self.send(b'', 'image/x-icon', status=204)
            if url.path == '/api/status':
                with LOCK:
                    return self.send({'running': any(j['status'] == 'running' for j in JOBS.values())})
            if url.path == '/api/runs':
                installation = query.get('installation',[saved_installation()])[0]
                return self.send(installation_layout(installation) if installation else empty_installation())
            if url.path == '/api/installation':
                installation = saved_installation()
                return self.send(installation_layout(installation) if installation else empty_installation())
            if url.path == '/api/metadata':
                return self.send(metadata(query['path'][0]))
            job = query.get('job', [''])[0]
            if job not in JOBS:
                raise ValueError('Unknown comparison')
            if url.path == '/api/job':
                with LOCK:
                    return self.send(dict(JOBS[job]))
            if url.path == '/api/export':
                lane = query.get('lane',[''])[0]
                if lane and lane not in ('Core','Dyadic','Other'):
                    raise ValueError('Unknown audit category')
                filename = lane+'_audit.csv' if lane else 'differences.csv'
                return self.send((DATA_ROOT/'results'/job/filename).read_bytes(), 'text/csv; charset=utf-8')
            if url.path == '/api/series':
                variable = query['variable'][0]
                report = JOBS[job]['report']
                multiple = series_data(job, variable, json.loads(query.get('selectors', ['[]'])[0]))
                if multiple is not None: return self.send(multiple)
                summary = next(s for s in report['summaries'] if s['variable']==variable and 'error' not in s)
                with np.load(DATA_ROOT/'results'/job/(variable+'.npz')) as data:
                    keys, a, b = data['keys'], data['a'], data['b']
                dims = summary['dims']
                if not dims or dims[0] != 0:
                    raise ValueError('Chart requires a time axis first')
                selectors = json.loads(query.get('selectors', ['[]'])[0])
                options = []
                for axis, dim in enumerate(dims[1:], 1):
                    values = sorted(set(map(int, keys[:,axis])))
                    options.append([{'key': k, 'label': report['buckets'][dim].get(k, str(k))} for k in values])
                chosen = [int(selectors[i]) if i < len(selectors) else o[0]['key'] for i,o in enumerate(options)]
                mask = np.ones(len(keys), dtype=bool)
                for axis, value in enumerate(chosen, 1): mask &= keys[:,axis] == value
                records = sorted(zip(keys[mask,0].tolist(), a[mask].tolist(), b[mask].tolist()))
                points = [[year, x if math.isfinite(x) else None, y if math.isfinite(y) else None] for year,x,y in records]
                metrics = trajectory_metrics(keys[mask,0],a[mask],b[mask],report['atol'],report['rtol'])
                return self.send({'options':options, 'chosen':chosen, 'points':points, 'dims':dims,'metrics':metrics})
            self.send({'error':'Not found'}, status=404)
        except Exception as exc:
            self.send({'error':str(exc)}, status=400)

    def do_POST(self):
        try:
            if self.path == '/api/stop':
                with LOCK:
                    for state in JOBS.values():
                        if state['status'] == 'running':
                            state.update(stop_requested=True, progress='Stopping…')
                return self.send({'ok': True})
            if self.path == '/api/select-installation':
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                with tempfile.TemporaryDirectory(prefix='ifs-folder-') as folder:
                    output = pathlib.Path(folder)/'selection.json'
                    prefix = [sys.executable,'--pick-folder'] if FROZEN else [sys.executable,str(ROOT/'folder_picker.py')]
                    initial = request.get('installation') or str(saved_installation() or pathlib.Path.home())
                    result = subprocess.run(prefix+[initial,str(output)],capture_output=True,
                                            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                    if result.returncode or not output.exists():
                        raise ValueError('Folder picker could not open. Enter the installation path directly.')
                    return self.send(json.loads(output.read_text(encoding='utf-8')))
            if self.path == '/api/installation':
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                layout = installation_layout(request['installation'])
                DATA_ROOT.mkdir(parents=True,exist_ok=True)
                SETTINGS.write_text(json.dumps({'installation':layout['installation']},indent=2),encoding='utf-8')
                return self.send(layout)
            if self.path != '/api/compare': raise ValueError('Unknown endpoint')
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if not request.get('variables'): raise ValueError('Select at least one variable')
            runs = comparison_runs(request)
            request['b'] = runs[0]
            # Single worker avoids competing large payload allocations.
            with LOCK:
                if any(j['status']=='running' for j in JOBS.values()):
                    raise ValueError('A comparison is already running')
                job = uuid.uuid4().hex
                JOBS[job] = {'status':'running', 'progress':'Reading metadata', 'created':time.time(), 'run1':request['a'], 'run2':request['b']}
            threading.Thread(target=compare, args=(job,request), daemon=True).start()
            self.send({'job':job})
        except Exception as exc:
            self.send({'error':str(exc)}, status=400)


def create_server(port=0):
    if not (DECODER_EXE.exists() or DECODER.exists()):
        raise RuntimeError('The bundled IFs decoder is missing. Reinstall the application.')
    initialize_storage()
    restore_jobs()
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


if __name__ == '__main__':
    server = create_server(8765)
    print('IFs Model Vetting: http://127.0.0.1:8765', flush=True)
    server.serve_forever()
