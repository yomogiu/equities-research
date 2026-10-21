import tempfile,unittest,json
from pathlib import Path
from research import earnings_unstarted_request as u, earnings_mixed_runner as b
class UnstartedTests(unittest.TestCase):
 def fixture(self,r):
  (r/'input').write_text('frozen source');s={'packet_id':'a'*64,'issuer_id':'fictional','period':'FY2026-Q2','code_commit':'b'*40,'writing_sha256':'c'*64,'signals':True,'deterministic_corrections':True,'review_policy':'file-backed-markdown-review-v1'};rid=b.digest(s)[:24];p=r/'reporting/runs'/rid;p.mkdir(parents=True);q={'schema_version':1,'run_id':rid,'spec':s,'input_sha256':{'input':b.sha(r/'input')}};u.c.write(p/'request.json',q);u.c.write(p/'state.json',{'status':'needs_attention','run_id':rid,'reason':u.REASON});a=r/f'reporting/authorizations/{rid}.json';a.parent.mkdir(parents=True);u.c.write(a,{'enabled':True,'request_sha256':b.digest(q),'scope':'one_packet'});return rid,p,a
 def test_exact_unstarted_and_no_acceptance(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);rid,p,a=self.fixture(r);before=(p/'request.json').read_bytes();v=u.prepare(r,rid,r/'proof');self.assertEqual(v,u.verify(r,r/'proof'));self.assertEqual(v['tokens'],0);self.assertFalse(v['whole_report_accepted']);self.assertEqual(before,(p/'request.json').read_bytes())
 def test_any_execution_or_prepared_artifact_rejected(self):
  for n in ['pipeline','prepared','launch.json','verified.json','receipt.json']:
   with self.subTest(n=n),tempfile.TemporaryDirectory() as d:
    r=Path(d);rid,p,a=self.fixture(r);(p/n).mkdir()
    with self.assertRaises(ValueError):u.inspect(r,rid)
 def test_changed_source_authorization_stop_and_proof_rejected(self):
  for change in ['source','auth','stop','proof']:
   with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
    r=Path(d);rid,p,a=self.fixture(r);u.prepare(r,rid,r/'proof')
    if change=='source':(r/'input').write_text('changed')
    if change=='auth':v=b.read(a);v['enabled']=False;a.write_text(json.dumps(v))
    if change=='stop':v=b.read(p/'state.json');v['reason']='transport uncertain';(p/'state.json').write_text(json.dumps(v))
    if change=='proof':v=b.read(r/'proof');v['tokens']=123;(r/'proof').write_text(json.dumps(v))
    with self.assertRaises(ValueError):u.verify(r,r/'proof')
