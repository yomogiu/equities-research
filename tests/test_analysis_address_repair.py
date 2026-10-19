import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_analysis_address_repair as a

class AnalysisAddressTests(unittest.TestCase):
 def fixture(self):
  idx={'exchanges':[{'id':'exchange-original-one'},{'id':'exchange-original-two'}]}
  raw={'title':'Fictional issuer','opening':'Unchanged opening','opening_citations':['D001','exchange-unknown'],
       'findings':[{'heading':'Original','text':'Original prose','citations':['D002','exchange-unknown','exchange-original-two'],'quotes':[{'passage_id':'Pexact'}]},
                   {'heading':'Other','text':'Other prose','citations':['exchange-original-two'],'quotes':[]}],'scope':'Unchanged historical scope','next_tests':[]}
  candidate=copy.deepcopy(raw);candidate['opening_citations']=['D001','exchange-original-two'];candidate['findings'][0]['citations']=['D002','exchange-original-one','exchange-original-two']
  return raw,idx,candidate
 def test_fresh_selections_change_only_typed_positions(self):
  raw,idx,candidate=self.fixture();before=copy.deepcopy(raw);t=a.targets(raw,idx)
  self.assertEqual(len(t),2);self.assertEqual(t[0]['allowed_exchange_ids'],['exchange-original-one','exchange-original-two'])
  self.assertEqual(a.checked_candidate(raw,candidate,idx),candidate);self.assertEqual(raw,before)
  self.assertEqual(a.inspection_candidate(raw,idx)['opening_citations'],['D001']);self.assertEqual(raw,before)
 def test_no_prefix_guess_unlinked_id_or_preserved_unknown(self):
  raw,idx,candidate=self.fixture()
  for replacement in ['exchange-original','exchange-original-onex','exchange-unknown','Pexact']:
   bad=copy.deepcopy(candidate);bad['opening_citations'][1]=replacement
   with self.assertRaises(ValueError):a.checked_candidate(raw,bad,idx)
 def test_prose_quotes_scope_and_valid_addresses_are_immutable(self):
  raw,idx,candidate=self.fixture()
  mutations=[lambda x:x.update(opening='Changed'),lambda x:x.update(scope='Changed'),
             lambda x:x['findings'][0].update(text='Changed'),lambda x:x['findings'][0].update(quotes=[]),
             lambda x:x['findings'][0]['citations'].__setitem__(0,'D003'),lambda x:x.update(next_tests=[{'text':'Added'}])]
  for mutate in mutations:
   bad=copy.deepcopy(candidate);mutate(bad)
   with self.assertRaises(ValueError):a.checked_candidate(raw,bad,idx)
 def test_no_deletion_duplicate_reordering_or_unbounded_replacements(self):
  raw,idx,candidate=self.fixture()
  for ids in [['D001'],['exchange-original-one','D001'],['D001','exchange-original-one','exchange-original-one'],['D001',*['exchange-original-one']*4]]:
   bad=copy.deepcopy(candidate);bad['opening_citations']=ids
   with self.assertRaises(ValueError):a.checked_candidate(raw,bad,idx)
 def test_eligibility_fails_closed_outside_one_unknown_four_fields(self):
  raw,idx,_=self.fixture()
  for mutate in [lambda x:x['findings'][0]['citations'].__setitem__(1,'exchange-another-unknown'),
                 lambda x:x.update(opening_citations=['exchange-unknown']),
                 lambda x:x['findings'][0].update(citations=['D001','exchange-unknown','exchange-second-unknown']),
                 lambda x:x.update(opening_citations=['D001','exchange-original-one']) or x['findings'][0].update(citations=['D002','exchange-original-two'])]:
   bad=copy.deepcopy(raw);mutate(bad)
   with self.assertRaises(ValueError):a.targets(bad,idx)
  bad=copy.deepcopy(raw);bad['findings']*=4
  with self.assertRaises(ValueError):a.targets(bad,idx)
  with self.assertRaises(ValueError):a.targets(raw,{'exchanges':[]})
 def test_original_json_is_handoff_data_not_evidence_mapping(self):
  raw,idx,_=self.fixture();prior={'raw':raw,'targets':a.targets(raw,idx),'dependencies':{'retrieval':{'citations':['D001']}}}
  result=a.contents(prior)
  self.assertEqual(json.loads(result['unreviewed_prior_analysis_json']),raw)
  self.assertNotIn('unreviewed_prior_analysis',result)
  self.assertNotIn('exchange-unknown',result['original_valid_source_inventory']['citations']);self.assertIn('Pexact',result['original_valid_source_inventory']['citations']);self.assertIn('D002',result['original_valid_source_inventory']['citations'])
 def test_preparation_refuses_reset_dropped_session_changed_models_or_case(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'reservation.json').write_text('{}');case=root/'case';case.write_text('{}')
   actual={'tokens':410000,'max_tokens':1200000,'spent_correction_rounds':1,'session_ids':['retrieval','analysis','fresh-repair'],'models':{'analysis':['original','max']},'case_sha256':a.b.sha(case),'catalog_sha256':a.b.digest({})}
   record={'version':a.PREPARATION_VERSION,'repair_root':str(root),'reservation_sha256':a.b.sha(root/'reservation.json'),**actual};out=root/'prepared.json'
   with patch.object(a,'completed',return_value=actual):
    out.write_text(json.dumps(record));self.assertEqual(a.verify(out,case,{})['tokens'],410000)
    for key,value in [('tokens',0),('spent_correction_rounds',0),('session_ids',['fresh-repair']),('models',{}),('max_tokens',2400000),('case_sha256','altered')]:
     out.write_text(json.dumps({**record,key:value}))
     with self.assertRaises(ValueError):a.verify(out,case,{})

from test_earnings_passages import PassageFixture
from research import earnings_file_pipeline as pipeline,earnings_prepared_retrieval as retrieval,earnings_prepared_analysis as analysis,earnings_financial_outline as outline

class AnalysisRepairPipelineTests(PassageFixture,unittest.TestCase):
 def test_three_sessions_one_spent_round_and_original_budget_survive_pipeline(self):
  writing=self.root/'guide.md';writing.write_text('Fictional source-led guide');oldprep=self.root/'retrieval.json';newprep=self.root/'analysis.json';oldprep.write_text('{}');newprep.write_text(json.dumps({'version':a.PREPARATION_VERSION}));dest=self.root/'continued'
  content=copy.deepcopy(self.report);content['report_template']='source-led-six-sections-v1'
  for f,section in zip(content['findings'],['demand','earnings','cash','outlook']):f['section']=section
  old={'version':retrieval.VERSION,'session_id':'retrieval','tokens':120000,'max_tokens':1200000,'content':self.retrieval}
  new={'version':a.PREPARATION_VERSION,'content':content,'tokens':390000,'max_tokens':1200000,'models':pipeline.profile_models('original-file-review-routes-v1'),'session_ids':['retrieval','author','repair'],'spent_correction_rounds':1,'report_template':'source-led-six-sections-v1','writing_sha256':a.b.sha(writing)}
  oldprep.write_text(json.dumps(old));newprep.write_text(json.dumps(new))
  with patch.object(retrieval,'verify',return_value=old),patch.object(analysis,'verify',return_value=new),patch.object(outline,'artifact',return_value=self.financial):
   protocol=pipeline.initialize(self.casepath,dest,writing,preparation=oldprep,analysis_preparation=newprep)
   self.assertEqual(protocol['inherited_tokens'],390000);self.assertEqual(protocol['analysis_repair_rounds'],1);self.assertEqual(protocol['max_tokens'],1200000)
   result=pipeline.advance(dest,False);self.assertEqual(result['stage'],'signal_author');self.assertEqual(result['tokens'],390000)
   from test_earnings_signals import SignalTests
   calls=[]
   def closed_signals_then_pending_review(root,protocol,bundle,catalog,role,name,artifacts,metadata,report,execute,sessions,tokens):
    calls.append(name)
    if role=='signal_author':
     sessions.add('signals');return {'content':SignalTests.pack(self,artifacts['state'])},tokens+50
    self.assertEqual(role,'review');return {'status':'pending','stage':name,'tokens':tokens},tokens
   with patch.object(pipeline,'_job',side_effect=closed_signals_then_pending_review):
    reviewed=pipeline.advance(dest,False)
   self.assertEqual(calls,['signal_author','review-1']);self.assertEqual(reviewed['stage'],'review-1');self.assertEqual(reviewed['tokens'],390050)

   for key,value in [('analysis_repair_rounds',0),('analysis_repair_rounds',True),('max_tokens',2400000),('models',{})]:
    bad={**protocol,key:value};(dest/'protocol.json').write_text(json.dumps(bad))
    with self.assertRaises(ValueError):pipeline.load(dest)
   new['session_ids']=['retrieval','repair'];newprep.write_text(json.dumps(new));protocol['analysis_preparation_sha256']=a.b.sha(newprep);(dest/'protocol.json').write_text(json.dumps(protocol))
   with self.assertRaisesRegex(ValueError,'Three distinct'):pipeline.advance(dest,False)
 def test_local_validation_enforces_immutability_and_never_waives_coverage(self):
  from research import earnings_file_context as context
  raw=copy.deepcopy(self.report);raw['opening_citations']=['D001','exchange-unknown'];candidate=copy.deepcopy(raw);candidate['opening_citations']=['D001',self.bundle['transcript_index']['exchanges'][0]['id']]
  prior={'raw':raw,'targets':a.targets(raw,self.bundle['transcript_index']),'dependencies':{'retrieval':self.retrieval}}
  index=context.assemble(self.root/'evidence/manifest.json',self.catalog,self.root/'repair-context',artifacts=a.contents(prior),metadata={'role':'analysis','repair_version':a.VERSION})
  job=self.root/'repair-job';job.mkdir();(job/'request.json').write_text(json.dumps({'version':'file-prime-role-v1','context_index':str(index),'bindings':{'role':'analysis'}}));reader=context.Evidence(index,job/'retrieval.jsonl')
  with patch.object(pipeline,'coverage',side_effect=ValueError('uninspected original source')) as coverage:
   changed=copy.deepcopy(candidate);changed['opening']='Rewritten'
   result=reader.validate_result(changed);self.assertFalse(result['valid']);self.assertIn('must remain exact',result['error']);coverage.assert_not_called()
   result=reader.validate_result(candidate);self.assertFalse(result['valid']);self.assertIn('uninspected original source',result['error']);self.assertFalse(result['acceptance'])

class FrozenAnalysisAddressTests(unittest.TestCase):
 def test_launched_repairs_use_only_clean_official_managed_producers(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);job=root/'jobs/address-repair';job.mkdir(parents=True);code=root/'.report-workflow'/('a'*40)
   (job/'request.json').write_text(json.dumps({'code_root':str(code)}))
   for outputs in [[b'b'*40+b'\n'],[b'a'*40+b'\n',b' M changed.py\n'],[b'a'*40+b'\n',b'',b'https://example.invalid/not-official.git\n']]:
    with patch.object(a.subprocess,'check_output',side_effect=[x.decode() for x in outputs]):
     with self.assertRaises(ValueError):a.frozen(root,'completed')
   (job/'request.json').write_text(json.dumps({'code_root':str(root/'unmanaged')}))
   with patch.object(a.subprocess,'check_output') as process:
    with self.assertRaisesRegex(ValueError,'Managed frozen'):a.frozen(root,'completed')
    process.assert_not_called()
 def test_historical_completion_dispatches_to_its_own_isolated_verifier(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);job=root/'jobs/address-repair';job.mkdir(parents=True);code=root/'.report-workflow'/('b'*40)
   (job/'request.json').write_text(json.dumps({'code_root':str(code)}))
   with patch.object(a.subprocess,'check_output',side_effect=['b'*40+'\n','','https://github.com/yomogiu/equities-research.git\n','{"tokens":410000}']) as process:
    self.assertEqual(a.frozen(root,'completed'),{'tokens':410000});command=process.call_args.args[0];self.assertIn('-I',command);self.assertEqual(command[-1],'completed');self.assertIn(str(code.resolve()),command)

class QualifiedEndpointTests(unittest.TestCase):
 def test_report_must_use_an_exact_authenticated_qualification_endpoint(self):
  old={'packet_id':'old-digest','issuer_id':'fictitious:1','period':'Q2'};new={**old,'packet_id':'new-digest'};proof={'old_packet_id':old['packet_id'],'new_packet_id':new['packet_id']}
  self.assertEqual(a.qualified_identity(old,old,proof,old,new),'old_packet');self.assertEqual(a.qualified_identity(new,new,proof,old,new),'new_packet')
  for spec,case in [({**new,'packet_id':'unrelated'},new),(new,old),({**new,'issuer_id':'another'},new),(new,{**new,'period':'Q3'})]:
   with self.assertRaises(ValueError):a.qualified_identity(spec,case,proof,old,new)
  with self.assertRaises(ValueError):a.qualified_identity(new,new,{**proof,'new_packet_id':'renamed'},old,new)
