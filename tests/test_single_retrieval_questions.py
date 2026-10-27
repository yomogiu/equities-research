"""Fictitious question-only targets, immutable results and canonical usage."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_single_retrieval_questions as q,earnings_single_retrieval_addresses as old

class QuestionTests(unittest.TestCase):
 def fixture(self):
  catalog={'passages':[{'passage_id':p,'scope_id':s}for p,s in [('Q1','q1'),('Q2','q1'),('A1','a1'),('Q3','q2'),('A2','a2')]]};index={'exchanges':[{'id':'e1','question_turn_ids':['q1'],'answer_turn_ids':['a1']},{'id':'e2','question_turn_ids':['q2'],'answer_turn_ids':['a2']}]}
  raw={'exchange_coverage':[{'exchange_id':'e1','question':'Original question','answer':'Original answer','question_passage_ids':['unknown','Q2'],'answer_passage_ids':['A1']},{'exchange_id':'e2','question':'Other original question','answer':'Other original answer','question_passage_ids':['Q3'],'answer_passage_ids':['A2']}],'quotes':[{'passage_id':'A1'}],'document_findings':[]};target=q.targets(raw,catalog,index);proposal={'repairs':[{'exchange_id':'e1','field':'question_passage_ids','before_ids':['unknown','Q2'],'after_ids':['Q1','Q2']}]};return raw,catalog,index,target,proposal
 def test_only_source_adjudicated_original_question_membership(self):
  raw,cat,index,t,p=self.fixture();before=copy.deepcopy(raw);self.assertEqual(t[0]['allowed_passage_ids'],['Q1','Q2']);self.assertEqual(t[0]['required_scope_ids'],['q1','a1']);out=q.apply(raw,t,p,cat);self.assertEqual(raw,before);out['exchange_coverage'][0]['question_passage_ids']=['unknown','Q2'];self.assertEqual(out,raw)
 def test_no_prefix_answer_other_exchange_or_duplicate_selection(self):
  raw,cat,index,t,p=self.fixture()
  for ids in [['Q'],['Q1x','Q2'],['A1','Q2'],['Q3','Q2'],['Q1','Q1','Q2'],['Q2'],['Q2','Q1']]:
   bad=copy.deepcopy(p);bad['repairs'][0]['after_ids']=ids
   with self.subTest(ids=ids),self.assertRaises(ValueError):q.apply(raw,t,bad,cat)
 def test_prose_other_rows_quotes_and_unrelated_addresses_cannot_change(self):
  raw,cat,index,t,p=self.fixture()
  for mutate in [lambda x:x['repairs'][0].update(text='rewrite'),lambda x:x['repairs'][0].update(field='answer_passage_ids'),lambda x:x['repairs'][0].update(exchange_id='e2'),lambda x:x['repairs'][0].update(before_ids=['different']),lambda x:x['repairs'].append(copy.deepcopy(x['repairs'][0]))]:
   bad=copy.deepcopy(p);mutate(bad)
   with self.assertRaises(ValueError):q.apply(raw,t,bad,cat)
 def test_one_question_field_only_no_answer_quote_or_duplicate_ledger_bypass(self):
  raw,cat,index,t,p=self.fixture()
  for mutate in [lambda x:x['exchange_coverage'][0].update(answer_passage_ids=['unknown-answer']),lambda x:x['exchange_coverage'][1].update(question_passage_ids=['unknown-two']),lambda x:x['exchange_coverage'][0].update(question_passage_ids=['unknown','second-unknown']),lambda x:x['exchange_coverage'][0].update(exchange_id='e2'),lambda x:x.update(exchange_coverage=[])]:
   bad=copy.deepcopy(raw);mutate(bad)
   with self.assertRaises(ValueError):q.targets(bad,cat,index)
 def test_same_canonical_slot_and_legacy_reservations_preserve_usage(self):
  with tempfile.TemporaryDirectory()as tmp:
   private=Path(tmp).resolve();code=private/'.report-workflow'/('a'*40);run='b'*24;previous=private/'reporting/runs'/run/'pipeline';job=previous/'jobs/retrieval';job.mkdir(parents=True);(job/'request.json').write_text(json.dumps({'code_root':str(code)}));slot=private/'reporting/repairs/retrieval-addresses'/run
   with patch.object(q.ref,'frozen',return_value=code):
    q.reservation_path(previous,slot)
    with self.assertRaises(ValueError):q.reservation_path(previous,slot.with_name(run+'-new'))
    legacy=private/'reporting/repairs/legacy/reservation.json';legacy.parent.mkdir(parents=True);legacy.write_text(json.dumps({'nested':{'previous_root':str(previous)},'tokens':123}))
    with self.assertRaisesRegex(ValueError,'legacy repair'):q.reservation_path(previous,slot)
    legacy.write_text(json.dumps({'previous_root':'/other/private/reporting/runs/'+run+'/pipeline'}))
    with self.assertRaisesRegex(ValueError,'legacy repair'):q.reservation_path(previous,slot)
 def test_preparation_cannot_reset_usage_models_round_or_distinct_sessions(self):
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);(root/'reservation.json').write_text('{}');case=root/'case';case.write_text('{}');actual={'tokens':300000,'max_tokens':1200000,'spent_correction_rounds':1,'session_ids':['old','fresh'],'models':{'retrieval':['original','max']},'case_sha256':q.b.sha(case),'catalog_sha256':q.b.digest({})};value={'version':q.PREPARATION_VERSION,'repair_root':str(root),'reservation_sha256':q.b.sha(root/'reservation.json'),**actual};out=root/'preparation.json'
   with patch.object(q,'completed',return_value=actual):
    out.write_text(json.dumps(value));self.assertEqual(q.verify(out,case,{})['tokens'],300000)
    for key,val in [('tokens',0),('max_tokens',2400000),('spent_correction_rounds',0),('spent_correction_rounds',True),('session_ids',['fresh']),('models',{})]:
     out.write_text(json.dumps({**value,key:val}))
     with self.assertRaises(ValueError):q.verify(out,case,{})

from test_earnings_passages import PassageFixture
from research import earnings_file_pipeline as pipeline,earnings_prepared_retrieval as prepared,earnings_file_context as context
class QuestionPipelineTests(PassageFixture,unittest.TestCase):
 def test_two_charged_sessions_and_original_correction_round_survive_pipeline(self):
  writing=self.root/'writing';writing.write_text('Fictional guide');proof=self.root/'prepared.json';proof.write_text(json.dumps({'version':q.PREPARATION_VERSION}));v={'version':q.PREPARATION_VERSION,'content':self.retrieval,'tokens':300000,'max_tokens':1200000,'models':pipeline.profile_models('original-file-review-routes-v1'),'report_template':'source-led-six-sections-v1','writing_sha256':q.b.sha(writing),'session_id':'repair','session_ids':['old','repair'],'spent_correction_rounds':1}
  proof.write_text(json.dumps(v))
  from research import earnings_financial_outline as outline
  with patch.object(prepared,'verify',return_value=v),patch.object(outline,'artifact',return_value=self.financial):
   dest=self.root/'continued';protocol=pipeline.initialize(self.casepath,dest,writing,preparation=proof);self.assertEqual(protocol['inherited_tokens'],300000);self.assertEqual(protocol['retrieval_repair_rounds'],1);pending=pipeline.advance(dest,False);self.assertEqual(pending['stage'],'analysis');self.assertEqual(pending['tokens'],300000)
   for key,val in [('max_tokens',2400000),('models',{}),('retrieval_repair_rounds',0)]:
    (dest/'protocol.json').write_text(json.dumps({**protocol,key:val}))
    with self.assertRaises(ValueError):pipeline.load(dest)
 def test_local_validation_never_waives_fresh_target_coverage(self):
  raw=copy.deepcopy(self.retrieval);row=raw['exchange_coverage'][0];row['question_passage_ids']=['unknown'];selected=q.targets(raw,self.catalog,self.bundle['transcript_index']);proposal={'repairs':[{'exchange_id':row['exchange_id'],'field':'question_passage_ids','before_ids':['unknown'],'after_ids':[selected[0]['allowed_passage_ids'][0]]}]};meta={'role':'retrieval_reference','repair_version':q.VERSION,'targets':selected,'source_scope_ids':selected[0]['required_scope_ids']};index=context.assemble(self.root/'evidence/manifest.json',self.catalog,self.root/'question-context',artifacts={'reference_candidate':raw,'reference_targets':selected},metadata=meta);job=self.root/'job';job.mkdir();(job/'request.json').write_text(json.dumps({'version':'file-prime-role-v1','context_index':str(index),'bindings':{'role':'retrieval_reference'}}));reader=context.Evidence(index,job/'retrieval.jsonl')
  with patch.object(pipeline,'coverage',side_effect=ValueError('target source not freshly inspected')):
   result=reader.validate_result(proposal);self.assertFalse(result['valid']);self.assertFalse(result['acceptance']);self.assertIn('freshly inspected',result['error'])

class RetainedLedgerInspectionTests(unittest.TestCase):
 def test_uninspected_paragraph_in_another_original_row_still_blocks(self):
  import subprocess,hashlib
  raw,cat,index,selected,proposal=QuestionTests().fixture()
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);previous=root/'pipeline';job=previous/'jobs/retrieval';job.mkdir(parents=True);code=root/'producer';pkg=code/'research';pkg.mkdir(parents=True);(pkg/'__init__.py').write_text('');protocol={'models':{'retrieval':['original','max']},'max_tokens':1200000,'max_correction_rounds':2,'report_template':'source-led-six-sections-v1','evidence_manifest':'manifest'};(previous/'protocol.json').write_text(json.dumps(protocol));(previous/'passages.json').write_text(json.dumps(cat));context=root/'index.json';context.write_text(json.dumps({'manifest':'manifest'}));(job/'prompt.md').write_text('Exact original instruction');(job/'request.json').write_text(json.dumps({'code_root':str(code),'model':'original','effort':'max','context_index':str(context),'bindings':{'protocol_sha256':hashlib.sha256((previous/'protocol.json').read_bytes()).hexdigest()}}))
   (pkg/'earnings_mixed_runner.py').write_text('import json,hashlib\nfrom pathlib import Path\ndef read(p):return json.loads(Path(p).read_text())\ndef sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()\n')
   (pkg/'earnings_file_runner.py').write_text("import json\ndef verify_job(job):return {'content':json.loads((job.parent.parent/'fixture.json').read_text())['raw']}\n")
   (pkg/'earnings_file_pipeline.py').write_text("import json,types\nfrom pathlib import Path\ndef load(root):\n global fixture\n fixture=json.loads((root/'fixture.json').read_text());return json.loads((root/'protocol.json').read_text()),{'transcript_index':fixture['index']},fixture['catalog']\ndef instruction(*args):return 'Exact original instruction'\ndef verify(root):raise ValueError('Required original evidence was not completely inspected: unknown')\ndef coverage(role,index,job,value,catalog,deps):\n ids=[p for row in value['exchange_coverage']for f in ['question_passage_ids','answer_passage_ids']for p in row[f]]\n if any(p not in fixture['delivered']for p in ids):raise ValueError('Uninspected retained paragraph')\ndef validate(role,value,bundle,catalog):\n known={p['passage_id']for p in catalog['passages']}\n assert all(p in known for row in value['exchange_coverage']for f in ['question_passage_ids','answer_passage_ids']for p in row[f])\npipe=types.SimpleNamespace(validate=validate)\n")
   fixture={'raw':raw,'catalog':cat,'index':index,'delivered':['Q1','Q2','A1','Q3','A2']};(previous/'fixture.json').write_text(json.dumps(fixture));real_call=subprocess.check_output
   def isolated(*args,**kwargs):kwargs['stderr']=subprocess.PIPE;return real_call(*args,**kwargs)
   from research import earnings_compact_evidence as evidence
   with patch.object(q.original,'original',return_value={'raw':raw}),patch.object(q.ref,'frozen',return_value=code),patch.object(evidence,'load_bundle',return_value={'transcript_index':index}),patch.object(q.subprocess,'check_output',side_effect=isolated):
    prior,candidate,targets=q.derive(previous);self.assertEqual(candidate,raw)
    fixture['delivered'].remove('Q3');(previous/'fixture.json').write_text(json.dumps(fixture))
    with self.assertRaises(subprocess.CalledProcessError):q.derive(previous)

class QuestionProfileTests(unittest.TestCase):
 def test_complete_original_model_map_and_two_charged_sessions_required(self):
  from research import earnings_inherited_profile_guard as guard,earnings_file_pipeline as pipeline
  value={'model_profile':None,'preparation_version':q.PREPARATION_VERSION,'models':pipeline.profile_models('original-file-review-routes-v1'),'spent_correction_rounds':1,'session_count':2};self.assertTrue(guard.matches_question(value,'original-file-review-routes-v1'))
  for key,val in [('model_profile','original-file-review-routes-v1'),('preparation_version',old.PREPARATION_VERSION),('models',{}),('spent_correction_rounds',0),('spent_correction_rounds',True),('session_count',1)]:
   with self.assertRaises(ValueError):guard.matches_question({**value,key:val},'original-file-review-routes-v1')
  changed=copy.deepcopy(value);changed['models']['review']=['substitute','low']
  with self.assertRaises(ValueError):guard.matches_question(changed,'original-file-review-routes-v1')
