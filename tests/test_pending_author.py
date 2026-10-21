import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from research import earnings_pending_author as h,earnings_mixed_runner as b
class PendingAuthor(unittest.TestCase):
 def test_exact_lineage_and_no_spent_round(self):
  with tempfile.TemporaryDirectory() as tmp:
   r=Path(tmp);old=r/'old';(old/'jobs/retrieval').mkdir(parents=True);(old/'protocol.json').write_text('{}');(old/'jobs/retrieval/output.json').write_text('{}');case=r/'case.json';case.write_text('{}');catalog={'passages':[]}
   v={'protocol':{'case_sha256':b.sha(case),'max_tokens':1200000,'models':{'retrieval':['fake','medium']},'writing_sha256':'a'*64,'report_template':'fake'},'tokens':123,'session_id':'closed-fake','catalog_sha256':b.digest(catalog),'content':{'document_findings':[]}}
   with patch.object(h,'original',return_value=v):
    out=r/'prepared.json';result=h.prepare(old,case,out);self.assertEqual(result['spent_correction_rounds'],0);self.assertEqual(h.verify(out,case,catalog),result)
    result['tokens']=0;out.write_text(json.dumps(result))
    with self.assertRaises(ValueError):h.verify(out,case,catalog)
    with self.assertRaises(ValueError):h.prepare(old,case,out)
