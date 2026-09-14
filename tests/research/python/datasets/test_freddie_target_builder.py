from __future__ import annotations
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd
from research.python.datasets.freddie_sflld.target_builder import TargetProtocol, _aggregate_complete_frame, _process_quarter, payment_index
P=TargetProtocol(target_id='t',horizon_min=1,horizon_max=12,serious_min_cycles=3,reo_status='RA',unknown_status='XX',serious_zero_balance_codes=frozenset({'02','03','09'}),clean_negative_zero_balance_codes=frozenset({'01'}),censoring_zero_balance_codes=frozenset({'15','16','96'}))

def agg(months, first='202401'):
    rows=[]
    for idx,status,zbc in months:
        y=2024+(idx-1)//12; m=(idx-1)%12+1
        rows.append({'source_entity_id':'F24Q10000001','reporting_period':f'{y}{m:02d}','delinquency_status':status,'zero_balance_code':zbc})
    f=pd.DataFrame(rows)
    anchors=pd.DataFrame({'source_entity_id':['F24Q10000001'],'first_payment_period':[first],'first_payment_ordinal':[2024*12+1]}).set_index('source_entity_id',drop=False)
    return _aggregate_complete_frame(f,anchors=anchors,protocol=P).iloc[0]
class TargetTests(unittest.TestCase):
    def test_payment_index_anchor(self): self.assertEqual(payment_index('202312','202401'),0); self.assertEqual(payment_index('202412','202401'),12)
    def test_serious_delinquency_positive(self): self.assertEqual(agg([(i,'03' if i==5 else '00','') for i in range(1,13)])['target'],1)
    def test_60_then_cure_negative(self): self.assertEqual(agg([(i,'02' if i==4 else '00','') for i in range(1,13)])['target'],0)
    def test_month13_event_not_target(self): self.assertEqual(agg([(i,'03' if i==13 else '00','') for i in range(1,14)])['target'],0)
    def test_short_history_censored(self): self.assertTrue(pd.isna(agg([(i,'00','') for i in range(1,8)])['target']))
    def test_clean_early_payoff_negative(self): self.assertEqual(agg([(i,'00','01' if i==8 else '') for i in range(1,9)])['target'],0)
    def test_internal_gap_censored(self): self.assertEqual(agg([(i,'00','') for i in range(1,13) if i!=6])['censor_reason'],'missing_month_inside_12m_horizon')
    def test_unknown_censored(self): self.assertEqual(agg([(i,'XX' if i==6 else '00','') for i in range(1,13)])['censor_reason'],'unknown_delinquency_inside_12m_horizon')

    def test_streaming_production_path_matches_expected_target(self):
        def orig_line(first_payment: str, loan_id: str) -> str:
            cols = [""] * 31
            cols[1] = first_payment
            cols[19] = loan_id
            return "|".join(cols)

        def perf_line(loan_id: str, period: str, status: str = "00", zbc: str = "") -> str:
            cols = [""] * 35
            cols[0] = loan_id
            cols[1] = period
            cols[3] = status
            cols[8] = zbc
            return "|".join(cols)

        loan_pos = "F24Q10000001"
        loan_neg = "F24Q10000002"
        orig = "\n".join([orig_line("202401", loan_pos), orig_line("202401", loan_neg)]) + "\n"
        perf_rows = []
        for month in range(1, 13):
            period = f"2024{month:02d}"
            perf_rows.append(perf_line(loan_pos, period, "03" if month == 5 else "00"))
        for month in range(1, 9):
            period = f"2024{month:02d}"
            perf_rows.append(perf_line(loan_neg, period, "00", "01" if month == 8 else ""))
        perf = "\n".join(perf_rows) + "\n"

        with tempfile.TemporaryDirectory() as td:
            zip_path = Path(td) / "quarter.zip"
            target_path = Path(td) / "target.csv"
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("orig_2024Q1.txt", orig)
                zf.writestr("perf_2024Q1.txt", perf)
            with zipfile.ZipFile(zip_path) as nested:
                stats = _process_quarter(nested, "2024Q1", P, target_path)
            out = pd.read_csv(target_path, dtype={"source_entity_id": "string"})
            self.assertEqual(stats["loans"], 2)
            self.assertEqual(stats["eligible"], 2)
            self.assertEqual(stats["positive"], 1)
            self.assertEqual(stats["negative"], 1)
            self.assertEqual(out.set_index("source_entity_id").loc[loan_pos, "target"], 1)
            self.assertEqual(out.set_index("source_entity_id").loc[loan_neg, "target"], 0)
            self.assertEqual(out.set_index("source_entity_id").loc[loan_neg, "target_event"], "voluntary_payoff_before_12m")

    def test_duplicate_period_fails(self):
        f=pd.DataFrame([{'source_entity_id':'x','reporting_period':'202401','delinquency_status':'00','zero_balance_code':''},{'source_entity_id':'x','reporting_period':'202401','delinquency_status':'00','zero_balance_code':''}]); a=pd.DataFrame({'source_entity_id':['x'],'first_payment_period':['202401'],'first_payment_ordinal':[2024*12+1]}).set_index('source_entity_id',drop=False)
        with self.assertRaises(ValueError): _aggregate_complete_frame(f,anchors=a,protocol=P)
if __name__=='__main__': unittest.main()
