# IFs Model Vetting

Standalone IFs runfile comparison tool, also bundled by the separate
`ifs-companion` application. This repository owns comparison logic, trajectory
audits, the comparison UI, the .NET Parquet decoder, and their tests.

Use Python 3.14 with NumPy (`python -m pip install numpy==2.5.3`) and a .NET 10 SDK.
Run `./build.ps1` to publish the decoder, then `./start.ps1 -PythonPath <python.exe>`
and open http://127.0.0.1:8765. Select an IFs folder containing DATA and RUNFILES,
choose two runs, load shared variables, and compare. Run
`python -m unittest discover -s tests -v` for the tool tests.

Source runfiles are opened read-only. Stored coordinate tuples drive alignment;
incompatible dimensions are skipped, partial payloads are identified, and
nonfinite values are excluded from numeric metrics. Each variable retains its own
units. Audits provide descriptive evidence, not causal or pass/fail judgments.
Completed reports and arrays are saved under `%LOCALAPPDATA%/IFsModelVetting`;
`IFS_VETTING_DATA_DIR` overrides the location for testing.

## Companion integration

Keep `ifs-companion` beside this checkout. Its build reads this repository directly
and bundles the tool into its installer. No Companion shell, desktop host, or
installer source is maintained here. The existing local HTTP API supplies
installation selection, metadata, comparisons, job status, reports, and exports.
`/api/recent` lists comparison jobs; the UI exposes `openCompanionReport(id)` for
the host to reopen a report. The comparison tool can still run on its own.

Older generated desktop distributions remain in ignored `dist` and `release`
directories for reference. New Companion builds belong to `ifs-companion`.
This project is MIT licensed; dependency notices remain in THIRD_PARTY_NOTICES.txt.

## Independent Companion package

After building the decoder, run `packaging/build-tool.py --python <packaging-python>`
using Python with the dependencies in `packaging/requirements-build.txt`. This
produces a self-contained `.ifstool` and checksum under ignored `release/`.
The package reuses the existing comparison engine and UI through a small
authenticated loopback adapter (`comparison_tool.py`). Companion supplies the
shared data folder, so installing or removing the package preserves reports.
Official packages and their catalog are published through the `ifs-companion`
repository. This repository remains responsible for the comparison source.

## Baseline horizon and multiple comparisons

Select one baseline and multiple comparison runs with Ctrl/Shift. The baseline calendar years anchor every comparison and chart. Loading indicators shows the baseline indicators available in at least one selected run; the list identifies availability across runs. Missing indicators or incompatible country/sector mappings skip only the affected indicator/run pair. Year keys can differ: the app matches actual calendar-year labels, reports missing baseline periods and excludes comparison years outside the baseline years. It also identifies holes inside the horizon.

Each run has independent numerical measures, audit cohorts, and year coverage. Summary rows show matched years against the baseline, and audit rows show finite matched years. Scores computed over different periods require care when comparing runs. Trajectories overlay the baseline once with all selected runs inside the baseline horizon, leaving missing years blank. Difference lines and SVG exports use the same horizon and run colors. CSV exports identify each comparison run. Previously saved single-pair reports remain readable.

## Comparison performance and storage

A comparison session keeps one lazy decoder process alive for selected payloads. Each baseline indicator is decoded and normalized once, then reused across runs through a temporary memory-mapped array. Completed reports compress one shared baseline array, store only comparison coordinates/values per run, and retain the existing report format and legacy chart readers. Pair CSVs are consolidation inputs and are removed after the combined exports finish. Measures, flags and full exports remain unchanged. Identical coordinate layouts take a validated fast path, and year mapping uses vectorized lookup.

The shared baseline is local to a comparison job. There is no permanent converted-run cache across sessions. Temporary memory-mapped baseline arrays can remain after interrupted jobs, just as other partial comparison outputs can; completed jobs compress and remove those temporary arrays.
