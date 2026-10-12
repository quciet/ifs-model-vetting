"""Baseline-anchored coverage and independent multi-run comparisons."""
import io
from contextlib import closing
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import app
from horizon import coverage, anchored_payload


def run_file(path, years, delta=0, index_years=False, country='Kenya', missing_variable=False):
    with closing(sqlite3.connect(path)) as db:
        db.executescript('CREATE TABLE ifs_var(Name,DisplayName,Type); CREATE TABLE ifs_var_dim(VariableName,Seq,DimensionId); CREATE TABLE ifs_dim_bucket(DimensionId,Seq,Name); CREATE TABLE ifs_var_blob(VariableName,Data);')
        db.executemany('INSERT INTO ifs_dim_bucket VALUES(0,?,?)',[(i if index_years else year,str(year)) for i,year in enumerate(years)])
        db.executemany('INSERT INTO ifs_dim_bucket VALUES(1,?,?)',[(1,country),(2,'India')])
        if missing_variable:db.commit();return
        db.execute("INSERT INTO ifs_var VALUES('GDP','Gross domestic product','Numeric')")
        db.executemany('INSERT INTO ifs_var_dim VALUES(?,?,?)',[('GDP',0,0),('GDP',1,1)])
        values=np.array([([i if index_years else year,region],year-2000+region+delta) for i,year in enumerate(years) for region in [1,2]],dtype=[('keys','<i2',(2,)),('value','<f4')])
        buffer=io.BytesIO();np.save(buffer,values)
        db.execute('INSERT INTO ifs_var_blob VALUES(?,?)',('GDP',buffer.getvalue()))
        db.commit()


def fixture_decode(db, variable, dims, job=None):
    app.check_stop(job)
    return np.load(io.BytesIO(db.execute('SELECT Data FROM ifs_var_blob WHERE VariableName=?',(variable,)).fetchone()[0]))


class MultiRunTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name)
        self.base=self.root/'baseline.db';run_file(self.base,list(range(2023,2051)))
        self.a=self.root/'a.db';run_file(self.a,list(range(2020,2051)),1)
        self.b=self.root/'b.db';run_file(self.b,list(range(2023,2051)),2,index_years=True)
        self.c=self.root/'c.db';run_file(self.c,list(range(2025,2101)),3,index_years=True)
        self.storage=patch.object(app,'DATA_ROOT',self.root/'saved');self.storage.start()
        self.decoder=patch.object(app,'decode',side_effect=fixture_decode);self.decoder.start()
        app.JOBS.clear()
    def tearDown(self):
        self.decoder.stop();self.storage.stop();app.JOBS.clear();self.temp.cleanup()
    def compare(self,runs):
        app.JOBS['test']={'status':'running'}
        app.compare('test',{'a':str(self.base),'comparisons':list(map(str,runs)),'variables':['GDP'],'atol':0,'rtol':0})
        self.assertEqual(app.JOBS['test']['status'],'complete',app.JOBS['test'])
        return app.JOBS['test']['report']
    def test_three_runs_use_baseline_years_and_independent_metrics(self):
        report=self.compare([self.a,self.b,self.c])
        self.assertEqual(report['baseline_years'],list(range(2023,2051)))
        a,b,c=report['comparisons']
        self.assertEqual(a['coverage']['excluded_periods'],[[2020,2022]])
        self.assertEqual(b['coverage']['missing_periods'],[])
        self.assertEqual(c['coverage']['missing_periods'],[[2023,2024]])
        self.assertEqual(c['coverage']['excluded_periods'],[[2051,2100]])
        self.assertEqual([s['rmse'] for s in report['summaries']],[1,2,3])
        self.assertEqual([s['points'] for s in report['summaries']],[56,56,52])
        self.assertEqual([len(s['compared_years']) for s in report['summaries']],[28,28,26])
        self.assertEqual([s['only_run2'] for s in report['summaries']],[0,0,0])
        series=app.series_data('test','GDP',[1]);self.assertEqual(len(series['points']),28)
        self.assertEqual(series['points'][0],[2023,24,25,26,None])
        self.assertEqual(series['points'][2],[2025,26,27,28,29])
        self.assertEqual([r['metrics']['finite_years'] for r in series['comparisons']],[28,28,26])
        self.assertEqual([r['metrics']['sse'] for r in series['comparisons']],[28,112,234])
        self.assertEqual(series['points'][-1][0],2050)
        with (app.DATA_ROOT/'results/test/differences.csv').open() as stream:
            text=stream.read();self.assertIn('ComparisonRun',text);self.assertIn(str(self.c),text)
    def test_country_mismatch_skips_only_that_pair(self):
        different=self.root/'different.db';run_file(different,list(range(2023,2051)),country='Changed label')
        report=self.compare([self.a,different]);self.assertEqual(report['summaries'][0]['rmse'],1)
        self.assertIn('labels or coverage differ',report['summaries'][1]['error'])
        series=app.series_data('test','GDP',[1]);self.assertTrue(all(p[3] is None for p in series['points']))
    def test_no_overlap_draws_baseline_and_empty_comparison(self):
        future=self.root/'future.db';run_file(future,[2101,2102])
        report=self.compare([future]);self.assertEqual(report['summaries'][0]['points'],0)
        self.assertIsNone(report['summaries'][0]['rmse'])
        series=app.series_data('test','GDP',[1]);self.assertEqual(series['points'][0],[2023,24,None])
        self.assertEqual(series['comparisons'][0]['metrics']['finite_years'],0)
    def test_missing_indicator_does_not_remove_other_run_results(self):
        missing=self.root/'missing.db';run_file(missing,list(range(2023,2051)),missing_variable=True)
        report=self.compare([self.a,missing]);self.assertIn('error',report['summaries'][1])
        self.assertEqual(report['summaries'][0]['changed'],56)
    def test_saved_report_restores_overlay(self):
        report=self.compare([self.a,self.c]);before=app.series_data('test','GDP',[2])
        app.JOBS.clear();app.restore_jobs();after=app.series_data('test','GDP',[2]);self.assertEqual(before,after)
    def test_legacy_single_pair_request_remains_supported(self):
        app.JOBS['test']={'status':'running'}
        app.compare('test',{'a':str(self.base),'b':str(self.b),'variables':['GDP']})
        self.assertEqual(app.JOBS['test']['status'],'complete')
        self.assertEqual(len(app.JOBS['test']['report']['comparisons']),1)
    def test_parent_stop_interrupts_child(self):
        def interrupt(db,var,dims,job):
            app.JOBS['test']['stop_requested']=True;app.check_stop(job)
        with patch.object(app,'decode',side_effect=interrupt):
            app.JOBS['test']={'status':'running'}
            app.compare('test',{'a':str(self.base),'comparisons':[str(self.a),str(self.c)],'variables':['GDP']})
        self.assertEqual(app.JOBS['test']['status'],'stopped')
        self.assertNotIn('test-run-1',app.JOBS)
        self.assertFalse((app.DATA_ROOT/'results/test/report.json').exists())
    def test_missing_interior_year_stays_blank_and_is_reported(self):
        sparse=self.root/'sparse.db';run_file(sparse,[2023,2024,2026,2027],4)
        report=self.compare([sparse])
        self.assertIn([2025,2025],report['comparisons'][0]['coverage']['missing_periods'])
        series=app.series_data('test','GDP',[1])
        self.assertEqual(series['points'][2],[2025,26,None])
        self.assertEqual(series['points'][3],[2026,27,31])
        self.assertEqual(series['comparisons'][0]['metrics']['finite_years'],4)
    def test_no_double_counting_baseline_and_missing_payload(self):
        with sqlite3.connect(self.a) as db:
            raw=db.execute('SELECT Data FROM ifs_var_blob').fetchone()[0]
            data=np.load(io.BytesIO(raw));data=data[~((data['keys'][:,0]==2025)&(data['keys'][:,1]==1))]
            buffer=io.BytesIO();np.save(buffer,data);db.execute('UPDATE ifs_var_blob SET Data=?',(buffer.getvalue(),))
        db.close()
        report=self.compare([self.a])
        self.assertEqual(report['summaries'][0]['points'],55)
        self.assertEqual(report['summaries'][0]['only_run1'],1)
        series=app.series_data('test','GDP',[1]);self.assertEqual(series['points'][2],[2025,26,None])
        self.assertEqual(series['comparisons'][0]['metrics']['finite_years'],27)
    def test_negative_tolerance_fails_job(self):
        app.JOBS['test']={'status':'running'}
        app.compare('test',{'a':str(self.base),'comparisons':[str(self.a)],'variables':['GDP'],'atol':-1})
        self.assertEqual(app.JOBS['test']['status'],'failed')
    def test_previous_report_schema_uses_legacy_series_path(self):
        app.JOBS['old']={'status':'complete','report':{'run1':'a','run2':'b'}}
        self.assertIsNone(app.series_data('old','GDP',[]))
    def test_invalid_runs_rejected(self):
        for comparisons in [[],[''],[str(self.a),str(self.a)],'not a list']:
            with self.assertRaises(ValueError):app.comparison_runs({'comparisons':comparisons})

if __name__=='__main__':unittest.main()
