import copy,unittest
from research.earnings_financial_outline import build
from research.earnings_visual_signals import badges
class NewTests(unittest.TestCase):
 def test_ifrs_read_time_mapping_preserves_frozen_records(self):
  d={'contexts':{'q':{'start_date':'2026-07-01','end_date':'2026-09-30','dimensions':[]},'p':{'start_date':'2026-04-01','end_date':'2026-06-30','dimensions':[]},'y':{'start_date':'2025-07-01','end_date':'2025-09-30','dimensions':[]}},'observations':[],'gaps':[]}
  for i in ['q','p','y']:d['observations'].append({'id':i,'concept':'ifrs-full:Revenue','canonical_metric':None,'context_id':i,'unit_id':'TWD','value':'100','status':'extracted'})
  old=copy.deepcopy(d);self.assertEqual(build(d)['rows'][0]['fact_ids'],['q','y','p']);self.assertEqual(d,old)
 def test_comparable_badges_and_no_debt_or_nonquarter_growth(self):
  h=['Metric','Jul 1, 2026 – Sep 30, 2026','Apr 1, 2026 – Jun 30, 2026','Jul 1, 2025 – Sep 30, 2025']
  s=badges(h,['Revenue [^F1]','150 [^F1]','100 [^F2]','200 [^F3]'])[1];self.assertIn('↑ +50.0% QoQ',s);self.assertIn('↓ -25.0% YoY',s)
  self.assertFalse(any(badges(h,['Debt','150','100','200'])))
  self.assertFalse(any(badges(h,['Revenue','150','0','-100'])))
  self.assertFalse(any(badges(['Metric','Jan 1, 2026 – Sep 30, 2026',h[2]],['Revenue','150','100'])))
