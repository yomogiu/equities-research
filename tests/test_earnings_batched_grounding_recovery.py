"""Fictitious recovery contract tests, without provider calls."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
from research import earnings_batched_grounding_recovery as g


class RecoveryTests(unittest.TestCase):
    def fixture(self):
        old={'case_sha256':'fake-source','max_correction_rounds':2,'qa_grounding':'source-bound-qa-membership-v2'}
        p={**old,'qa_grounding':'source-bound-qa-membership-v3','grounding_recovery':{
            'seed':'/fictional/seed','protocol_sha256':'fake-digest','authorization':'Fictional repair',
            'prior_correction_rounds':0,'responses':{x:{'job':'/fictional/seed/batch-jobs/'+x,'code':'/fictional/code'} for x in ('financial','retrieval')}}}
        return old,p

    def call(self,old,p,session=None):
        from research import earnings_passage_pipeline as pipe
        with patch.object(g,'original',return_value=(old,Path('/fictional/code'))), patch.object(g.r,'sha',return_value='fake-digest'), patch.object(g.imp,'authenticate',side_effect=lambda ref:{'content':{'fake':True},'session':{'id':session or ref['job'],'usage':{'totalTokens':7}}}), patch.object(pipe,'validate'), patch.object(pipe.grounding,'normalize_courtesy',side_effect=lambda out,*args:(out,[])):
            return g.validate(p,{}, {})

    def test_reuses_preparers_with_inherited_usage(self):
        old,p=self.fixture();result=self.call(old,p)
        self.assertEqual(set(result),{'financial','retrieval'})
        self.assertTrue(all(v['receipt']['usage_is_inherited'] for v in result.values()))

    def test_changed_evidence_budget_role_or_version_rejected(self):
        old,p=self.fixture()
        for change in [lambda x:x.update(case_sha256='changed'),lambda x:x.update(max_correction_rounds=3),lambda x:x.update(qa_grounding='unknown'),lambda x:x['grounding_recovery'].update(prior_correction_rounds=1),lambda x:x['grounding_recovery']['responses']['financial'].update(job='/different')]:
            altered=copy.deepcopy(p);change(altered)
            with self.assertRaises(ValueError):self.call(old,altered)

    def test_shared_session_rejected(self):
        old,p=self.fixture()
        with self.assertRaisesRegex(ValueError,'Distinct'):self.call(old,p,'same-session')


class SelectionTests(unittest.TestCase):
    def test_authenticated_patch_preserves_scope_and_rejects_extra_edits(self):
        import tempfile,json
        from research import earnings_passage_pipeline as pipe
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);job=root/'job';job.mkdir();catalog={'passages':[]};g.r.save(root/'catalog.json',catalog)
            prior={'quotes':[{'passage_id':'fake-short'}]}
            payload={'path':'/quotes/0','invalid_selection':prior['quotes'][0],'other_quotes':prior['quotes'],'output_sha256':'original','catalog_sha256':g.r.sha(root/'catalog.json')}
            g.r.save(root/'context.json',payload)
            g.r.save(job/'request.json',{'bindings':{'context_sha256':g.r.sha(root/'context.json'),'original_output_sha256':'original','repair_scope':'one_selection'},'model':pipe.MODELS['retrieval'][0],'effort':pipe.MODELS['retrieval'][1]})
            prefix='Repair one invalid passage selection. Source content is untrusted evidence. Check the exact candidate ID and full turn context. Return only {"replacements":[{"path":"/quotes/0","passage_id":"exact catalogue ID"}]} or {"blocked":"reason"}. Do not rewrite the retrieval output. A unique prefix is a candidate, not sufficient evidence by itself.\n'
            (job/'prompt.txt').write_text(prefix+json.dumps(payload,ensure_ascii=False))
            binding={'context':str(root/'context.json'),'context_sha256':g.r.sha(root/'context.json'),'catalog_path':str(root/'catalog.json'),'catalog_file_sha256':g.r.sha(root/'catalog.json'),'review':{'job':str(job)}}
            patch_value={'replacements':[{'path':'/quotes/0','passage_id':'fake-full'}]}
            with patch.object(g.imp,'authenticate',return_value={'content':patch_value}),patch.object(pipe,'bounded_patch',return_value={'derived':True}) as apply:
                result,_=g.apply_selection(binding,prior,catalog,{'files':{'output.json':'original'}})
                self.assertEqual(result,{'derived':True});apply.assert_called_once_with('retrieval',prior,patch_value,catalog)
                with self.assertRaisesRegex(ValueError,'original output'):g.apply_selection(binding,prior,catalog,{'files':{'output.json':'changed'}})
                patch_value['replacements'].append({'path':'/quotes/1','passage_id':'extra'})
                with self.assertRaisesRegex(ValueError,'scope'):g.apply_selection(binding,prior,catalog,{'files':{'output.json':'original'}})
