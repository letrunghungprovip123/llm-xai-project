from __future__ import annotations
import unittest
import pandas as pd
from research.python.statistical_analysis.bootstrap import build_case_bootstrap

class BootstrapTests(unittest.TestCase):
    def test_case_bootstrap_is_deterministic_and_paired(self) -> None:
        rows=[]
        for case,base in [('c1',0.2),('c2',0.4),('c3',0.6)]:
            for level,delta in [('S0',0.0),('S1',0.1)]:
                rows.append({'case_id':case,'model_id':'m','model_order':0,'evidence_level':level,'evidence_order':0 if level=='S0' else 1,'metric':base+delta})
        frame=pd.DataFrame(rows)
        contrasts=[{'contrast_id':'x','contrast_family':'evidence_vs_s0','condition_a':{'model_id':'m','evidence_level':'S1'},'condition_b':{'model_id':'m','evidence_level':'S0'}}]
        a=build_case_bootstrap(frame,contrasts,'metric',iterations=1000,confidence=.95,seed=7)
        b=build_case_bootstrap(frame,contrasts,'metric',iterations=1000,confidence=.95,seed=7)
        pd.testing.assert_frame_equal(a[0],b[0]); pd.testing.assert_frame_equal(a[1],b[1])
        self.assertAlmostEqual(float(a[1].loc[0,'observed_mean_difference']),0.1)
        self.assertAlmostEqual(float(a[1].loc[0,'ci_lower']),0.1)
        self.assertAlmostEqual(float(a[1].loc[0,'ci_upper']),0.1)

if __name__=='__main__': unittest.main()
