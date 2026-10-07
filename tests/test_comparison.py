import unittest
import numpy as np
from app import aligned, calculate

class ComparisonTests(unittest.TestCase):
    def test_alignment_uses_coordinates(self):
        dtype=np.dtype([('keys','<i2',(2,)),('value','<f4')])
        a=np.array([([2022,1],10),([2022,2],20)],dtype=dtype)
        b=np.array([([2022,2],22),([2022,1],11),([2023,1],30)],dtype=dtype)
        keys,x,y,only_a,only_b=aligned(a,b)
        np.testing.assert_array_equal(y-x,[1,2])
        self.assertEqual((only_a,only_b),(0,1))

    def test_constant_offset_zero_and_nonfinite(self):
        x=np.array([0.,10.,20.,np.nan]);y=np.array([2.,12.,22.,4.])
        metrics,delta,relative,changed=calculate(None,x,y,0,0)
        self.assertEqual(metrics['changed'],3)
        self.assertEqual(metrics['nonfinite'],1)
        self.assertEqual(metrics['rmse'],2)
        self.assertTrue(np.isnan(relative[0]))

    def test_tolerance(self):
        metrics,*_=calculate(None,np.array([100.,100.]),np.array([100.001,101.]),.01,.001)
        self.assertEqual(metrics['changed'],1)

    def test_bilateral_alignment_keeps_direction(self):
        dtype=np.dtype([('keys','<i2',(3,)),('value','<f4')])
        a=np.array([([2022,1,2],10),([2022,2,1],30)],dtype=dtype)
        b=np.array([([2022,2,1],32),([2022,1,2],11)],dtype=dtype)
        keys,x,y,*_=aligned(a,b)
        np.testing.assert_array_equal(y-x,[1,2])

    def test_duplicate_coordinates_rejected(self):
        dtype=np.dtype([('keys','<i2',(1,)),('value','<f4')])
        a=np.array([([2022],10),([2022],20)],dtype=dtype)
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            aligned(a,a)

if __name__=='__main__': unittest.main()
