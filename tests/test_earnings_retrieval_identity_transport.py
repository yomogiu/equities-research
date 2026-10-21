"""Fictional exact-address transport and inherited protocol checks; no providers."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_retrieval_identity_transport as t
from research import earnings_file_pipeline as pipeline, earnings_prepared_retrieval as prepared
from research import earnings_mixed_runner as b


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.index={'exchanges':[{'id':'exchange-one','question_turn_ids':['q1'],'answer_turn_ids':['a1']},
                                 {'id':'exchange-two','question_turn_ids':['q2'],'answer_turn_ids':['a2']}]}
        self.catalog={'passages':[{'passage_id':p,'scope_id':s} for p,s in [('p1','q1'),('p2','a1'),('p3','q2'),('p4','a2')]]}
        self.raw={'exchange_coverage':[{'exchange_id':'unknown','question_passage_ids':['p1'],'answer_passage_ids':['p2'],'answer':'Fictional answer.'},
                                       {'exchange_id':'exchange-two','question_passage_ids':['p3'],'answer_passage_ids':['p4'],'answer':'Other fictional answer.'}],
                  'quotes':['Unchanged fictional quotation']}

    def test_exact_membership_changes_only_typed_address_without_mutating_original(self):
        original=copy.deepcopy(self.raw);actual,proof=t.exact_identity(self.raw,self.catalog,self.index)
        expected=copy.deepcopy(original);expected['exchange_coverage'][0]['exchange_id']='exchange-one'
        self.assertEqual(actual,expected);self.assertEqual(self.raw,original)
        self.assertEqual(proof['path'],'/exchange_coverage/0/exchange_id')
        self.assertEqual(proof['question_scope_ids'],['q1'])

    def test_nonunique_membership_rejected(self):
        self.index['exchanges'][1].update(question_turn_ids=['q1'],answer_turn_ids=['a1'])
        with self.assertRaisesRegex(ValueError,'Unique missing'):t.exact_identity(self.raw,self.catalog,self.index)

    def test_unknown_passage_or_crossed_answer_or_empty_support_rejected(self):
        for values in (['not-a-passage'],['p4'],[]):
            raw=copy.deepcopy(self.raw);raw['exchange_coverage'][0]['answer_passage_ids']=values
            with self.subTest(values=values),self.assertRaises(ValueError):t.exact_identity(raw,self.catalog,self.index)

    def test_duplicate_missing_or_valid_identity_is_not_repaired(self):
        for identity in ('exchange-two','exchange-one'):
            raw=copy.deepcopy(self.raw);raw['exchange_coverage'][0]['exchange_id']=identity
            with self.subTest(identity=identity),self.assertRaises(ValueError):t.exact_identity(raw,self.catalog,self.index)

    def test_unknown_identity_in_prose_cannot_silently_survive(self):
        self.raw['exchange_coverage'][0]['answer']='See unknown in the report.'
        with self.assertRaisesRegex(ValueError,'outside typed identity'):t.exact_identity(self.raw,self.catalog,self.index)

    def test_verified_manifest_must_equal_replayed_derivation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);case=root/'case.json';b.save(case,{'fictional':True})
            value={'version':t.VERSION,'previous_root':str(root/'original'),'case_sha256':b.sha(case),'catalog_sha256':b.digest(self.catalog),'tokens':123}
            manifest=root/'prepared.json';b.save(manifest,value)
            with patch.object(t,'derive',return_value=copy.deepcopy(value)):
                self.assertEqual(t.verify(manifest,case,self.catalog),value)
                changed={**value,'tokens':0};manifest.unlink();b.save(manifest,changed)
                with self.assertRaisesRegex(ValueError,'derivation changed'):t.verify(manifest,case,self.catalog)

    def test_prepared_dispatch_uses_new_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest=Path(tmp)/'prepared.json';b.save(manifest,{'version':t.VERSION})
            with patch.object(t,'verify',return_value={'checked':True}) as verify:
                self.assertEqual(prepared.verify(manifest,'case',{}),{'checked':True})
                verify.assert_called_once_with(manifest,'case',{})

from test_earnings_passages import PassageFixture
from research import earnings_qa_grounding as grounding
from research import earnings_file_context as context
from research import earnings_financial_outline as outline


class InheritedProtocolTests(PassageFixture, unittest.TestCase):
    def prepare(self):
        self.writing=self.root/'writing.md';self.writing.write_text('Fictional writing standard.')
        self.value={'version':t.VERSION,'tokens':12345,'max_tokens':200000,'session_id':'fictional-original-session',
                    'session_ids':['fictional-original-session'],'models':copy.deepcopy(pipeline.ORIGINAL_MODELS),
                    'writing_sha256':b.sha(self.writing),'report_template':pipeline.template.VERSION,
                    'content':self.retrieval,'grounding':grounding.build(self.bundle,self.catalog,version=grounding.NAMED_GREETING_VERSION),
                    'derivation':{'fictional':'exact source membership'}}
        self.value['grounding']['fictional_derivation_marker']='original source dispositions retained'
        self.manifest_path=self.root/'preparation.json';b.save(self.manifest_path,self.value)
        self.output=self.root/'transport'
        pipeline.initialize(self.casepath,self.output,self.writing,max_tokens=200000,preparation=self.manifest_path)

    def test_original_routes_template_tokens_and_grounding_survive_init_load_preview(self):
        with patch.object(prepared,'verify',side_effect=lambda *a:self.value):
            self.prepare()
            protocol,bundle,_=pipeline.load(self.output)
            self.assertEqual(protocol['models'],pipeline.ORIGINAL_MODELS)
            self.assertEqual(protocol['report_template'],pipeline.template.VERSION)
            self.assertEqual(protocol['inherited_tokens'],12345)
            self.assertNotIn('retrieval_repair_rounds',protocol)
            self.assertEqual(bundle['qa_grounding'],self.value['grounding'])
            with patch.object(outline,'artifact',return_value=self.financial):
                result=pipeline.advance(self.output,False)
            self.assertEqual(result['status'],'pending');self.assertEqual(result['stage'],'analysis')
            self.assertEqual(result['tokens'],12345)
            artifacts=b.read(Path(result['context_index']).parent/'artifacts.json')
            self.assertEqual(artifacts['retrieval_transport_provenance'],self.value['derivation'])
            self.assertFalse((self.output/'jobs').exists())

    def test_changed_model_template_usage_or_guide_rejected_at_load(self):
        with patch.object(prepared,'verify',side_effect=lambda *a:self.value):
            self.prepare();path=self.output/'protocol.json';original=b.read(path)
            for field,value in [('models',pipeline.profile_models(None)),('report_template',None),('inherited_tokens',0),('retrieval_repair_rounds',1)]:
                path.unlink();context.write(path,{**original,field:value})
                with self.subTest(field=field),self.assertRaises(ValueError):pipeline.load(self.output)
            path.unlink();context.write(path,original)
            self.value['writing_sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'settings/accounting'):pipeline.load(self.output)

    def test_accepted_fake_report_counts_inherited_usage_and_fresh_distinct_sessions(self):
        import test_earnings_file_pipeline as fixtures
        from research import earnings_file_runner as runner
        self.fake_run=fixtures.FilePipelineTests.fake_run.__get__(self)
        self.drain=fixtures.FilePipelineTests.drain.__get__(self)
        self.pack=fixtures.FilePipelineTests.pack.__get__(self)
        with patch.object(prepared,'verify',side_effect=lambda *a:self.value):
            self.prepare()
            with patch.object(outline,'artifact',return_value=self.financial),patch.object(runner,'run_role',side_effect=self.fake_run):
                for _ in range(6):
                    result=pipeline.advance(self.output,True)
                    if result['status']=='accepted':break
                self.assertEqual(result['status'],'accepted')
                # Three fresh roles each have two fake assistant messages x20 tokens.
                self.assertEqual(result['tokens'],12345+3*40)
                self.assertEqual(result['correction_rounds'],0)
                self.assertEqual(set(p.name for p in (self.output/'jobs').iterdir()),{'analysis','signal_author','review-0'})
                review_artifacts=b.read(self.output/'contexts/review-0/artifacts.json')
                self.assertEqual(review_artifacts['retrieval_transport_provenance'],self.value['derivation'])


class FrozenProgramTests(PassageFixture, unittest.TestCase):
    def test_original_authenticated_context_and_all_bindings_replayed(self):
        import json
        import subprocess
        import sys
        import test_earnings_file_pipeline as fixtures
        self.drain=fixtures.FilePipelineTests.drain.__get__(self)
        fake_run=fixtures.FilePipelineTests.fake_run.__get__(self)
        writing=self.root/'writing.md';writing.write_text('Fictional guide.')
        correct=copy.deepcopy(self.retrieval)
        self.retrieval['exchange_coverage'][0]['exchange_id']='fictional-unknown-id'
        for changed in (None,'artifact_sha256','metadata_sha256','context_sha256'):
            root=(self.root/('original-'+str(changed))).resolve();pipeline.initialize(self.casepath,root,writing)
            with patch.object(outline,'artifact',return_value=self.financial):
                pending=pipeline.advance(root,False)
            index=Path(pending['context_index'])
            deps=b.read(index.parent/'artifacts.json');metadata=b.read(index.parent/'metadata.json')
            bindings={'protocol_sha256':b.sha(root/'protocol.json'),'role':'retrieval','context_sha256':b.sha(index),
                      'artifact_sha256':b.digest(deps),'metadata_sha256':b.digest(metadata)}
            if changed:bindings[changed]='f'*64
            protocol=b.read(root/'protocol.json');job=root/'jobs/retrieval'
            prompt=pipeline.instruction('retrieval',index,job,protocol)
            fake_run(job,prompt,*protocol['models']['retrieval'],bindings,index,max_tokens=protocol['max_tokens'],max_tool_calls=48)
            wrapper="import sys,json;sys.path.insert(0,sys.argv[1]);from unittest.mock import patch;from research import earnings_financial_outline as outline\nwith patch.object(outline,'artifact',return_value=json.loads(sys.argv[3])):exec(sys.argv[4])"
            result=subprocess.run([sys.executable,'-I','-B','-c',wrapper,str(Path(pipeline.__file__).resolve().parents[1]),str(root),json.dumps(self.financial),t.PROGRAM],
                                  input=json.dumps(correct),text=True,capture_output=True)
            with self.subTest(binding=changed):
                if changed:self.assertNotEqual(result.returncode,0)
                else:
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertEqual(json.loads(result.stdout)['tokens'],40)
