import unittest
import numpy as np
from diagnostics import audit_slices, lane_for, trajectory_metrics


class DiagnosticTests(unittest.TestCase):
    def test_smape_zeros_and_constant_correlation(self):
        result=trajectory_metrics(np.array([2022,2023]),np.array([0.,0.]),np.array([0.,2.]))
        self.assertEqual(result['mean_smape'],100.)
        self.assertEqual(result['sse'],4.)
        self.assertIsNone(result['pearson_r'])
        self.assertEqual(result['both_zero_years'],1)

    def test_crossings_follow_years_and_ignore_tolerance_noise(self):
        result=trajectory_metrics(np.array([2025,2022,2023,2024]),np.ones(4),np.array([0.,2.,1.001,0.]),.01,0)
        self.assertEqual(result['sign_flips'],1)
        self.assertEqual(result['first_divergence_year'],2022)

    def test_missing_year_breaks_crossing_sequence(self):
        result=trajectory_metrics(np.array([2022,2024]),np.ones(2),np.array([2.,0.]))
        self.assertEqual(result['sign_flips'],0)

    def test_sector_slices_choose_each_worst_country(self):
        keys=np.array([[y,r,s] for y in [2022,2023] for r in [1,2] for s in [1,2]])
        base=np.ones(8)*10
        comp=base+np.array([1,4,3,2,1,4,3,2])
        buckets={0:{2022:'2022',2023:'2023'},1:{1:'A',2:'B'},14:{1:'Crop',2:'Meat'}}
        rows=audit_slices('AGP',[0,1,14],buckets,keys,base,comp,0,0)
        self.assertEqual(len(rows),2)
        self.assertEqual([r['selectors'] for r in rows],[[2,1],[1,2]])
        self.assertEqual(rows[0]['worst_cohort'],'B / Crop')
        self.assertEqual(rows[0]['lane'],'Core')

    def test_bilateral_partner_is_fixed_and_origin_is_selected(self):
        keys=np.array([[2022,1,1],[2022,1,2],[2022,2,1],[2022,2,2]])
        buckets={0:{2022:'2022'},1:{1:'A',2:'B'}}
        rows=audit_slices('AIDBILAT',[0,1,1],buckets,keys,np.ones(4),np.array([2.,5.,4.,2.]),0,0)
        self.assertEqual([r['selectors'] for r in rows],[[2,1],[1,2]])
        self.assertTrue(all(r['lane']=='Dyadic' for r in rows))

    def test_region_axis_need_not_be_second(self):
        keys=np.array([[2022,5,1],[2022,5,2]])
        buckets={0:{2022:'2022'},18:{5:'Category'},1:{1:'A',2:'B'}}
        rows=audit_slices('SWINGSTS',[0,18,1],buckets,keys,np.ones(2),np.array([2.,4.]),0,0)
        self.assertEqual(rows[0]['selectors'],[5,2])
        self.assertEqual(rows[0]['tracked_variable'],'SWINGSTS [Category]')

    def test_global_series(self):
        rows=audit_slices('CO2PPM',[0],{0:{2022:'2022',2023:'2023'}},np.array([[2022],[2023]]),np.ones(2),np.ones(2),0,0)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['worst_cohort'],'Global series')
        self.assertEqual(rows[0]['mean_smape'],0.)
        self.assertIsNone(rows[0]['max_divergence_year'])

    def test_nonfinite_values_are_excluded(self):
        result=trajectory_metrics(np.array([2022,2023]),np.array([np.nan,1.]),np.array([2.,1.]))
        self.assertEqual(result['finite_years'],1)
        self.assertEqual(result['mean_smape'],0.)


if __name__=='__main__':unittest.main()
