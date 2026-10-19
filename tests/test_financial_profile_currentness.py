import copy,tempfile,unittest
from pathlib import Path
from test_financial_html_tables import fixture,authorize
from research import financial_profile_currentness as current,financial_html_tables as adapter,financial_evidence as financial,source_parse
class FinancialCurrentnessTests(unittest.TestCase):
 def fixture(self,r):
  raw,source,profile=fixture();source['text_sha256']=financial.digest(source_parse.extract(raw,'text/html','https://www.sec.gov/Archives/fake.htm')[0].encode());profile['source']=copy.deepcopy(source);pb,rb,auth=authorize(source,profile);p=r/'original.bin';p.write_bytes(raw);new=raw+b'<!--transport-only--> ';fresh={**source,'raw_sha256':financial.digest(new)};wrapper={'version':current.VERSION,'enabled':True,'source':fresh,'original_authorization':auth,'original_raw_path':str(p),'source_url':'https://www.sec.gov/Archives/fake.htm','profile_sha256':auth['profile_sha256'],'review_sha256':auth['review_sha256']};return raw,new,source,fresh,pb,rb,auth,wrapper
 def test_exact_reviewed_semantics_and_spans_derived_for_current_raw(self):
  with tempfile.TemporaryDirectory() as d:
   a,b,old,new,pb,rb,auth,wrapper=self.fixture(Path(d));original=copy.deepcopy(wrapper);before=adapter.extract(a,old,pb,rb,auth);after=adapter.extract(b,new,pb,rb,wrapper);self.assertEqual(wrapper,original)
   for x,y in zip(before['observations'],after['observations']):
    self.assertEqual({k:v for k,v in x.items() if k not in ('observation_id','source_raw_sha256')},{k:v for k,v in y.items() if k not in ('observation_id','source_raw_sha256')});self.assertEqual(y['source_raw_sha256'],new['raw_sha256'])
 def test_moved_changed_spans_review_reset_and_identity_rejected(self):
  for change in ['moved','number','basis','review','identity','raw']:
   with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
    a,b,old,new,pb,rb,auth,w=self.fixture(Path(d))
    if change=='moved':b=b' '+b
    if change=='number':b=b.replace(b'1,234.50',b'9,999.99')
    if change=='basis':b=b.replace(b'IFRS',b'GAAP')
    if change=='review':w['original_authorization']['reviewer_id']=w['original_authorization']['author_id']
    if change=='identity':new['issuer_id']='different'
    if change=='raw':Path(w['original_raw_path']).write_bytes(a+b'changed')
    new['raw_sha256']=financial.digest(b);w['source']=new
    with self.assertRaises(ValueError):adapter.extract(b,new,pb,rb,w)
 def test_original_reviewed_raw_must_be_explicitly_frozen_in_case(self):
  import json
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);a,b,old,new,pb,rb,auth,w=self.fixture(r);paths={'authorization_path':r/'auth.json','profile_path':r/'profile.json','review_path':r/'review.json'}
   paths['authorization_path'].write_text(json.dumps(w));paths['profile_path'].write_bytes(pb);paths['review_path'].write_bytes(rb)
   case={'issuer_id':new['issuer_id'],'financial_adapter':{k:str(p) for k,p in paths.items()},'artifacts':[{'path':str(p),'sha256':financial.digest(p.read_bytes())} for p in paths.values()]}
   with self.assertRaises(ValueError):adapter.case_inputs(case,b,new)
   case['artifacts'].append({'path':w['original_raw_path'],'sha256':old['raw_sha256']});inputs=adapter.case_inputs(case,b,new);self.assertEqual(adapter.extract(*inputs)['source']['raw_sha256'],new['raw_sha256'])
