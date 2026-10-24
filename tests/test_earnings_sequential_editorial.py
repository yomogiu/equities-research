"""Fictitious presentation-only repair and exact-candidate review regressions."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research import earnings_sequential as core
from research import earnings_sequential_editorial as editorial
from research import earnings_sequential_revisions as revisions


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.analysis = {'title':'Fictional Widgets', 'opening':{'text':'Fictional evidence.', 'citations':['D1']},
            'sections':{name:{'text':'Fictional analysis.', 'citations':['D1']} for name in revisions.SECTIONS},
            'qa':[], 'next_tests':[]}
        self.analysis['sections']['cash']['text'] = ('Cash supports operations. Total debt remains unavailable; '
            'separately disclosed lease liabilities are not a complete debt measure.')
        self.review = {'verdict':'revise', 'criteria':{name:{'status':'pass'} for name in
            ('source_accuracy','qa_fidelity','financial_context','reasoning','counterevidence','coverage','materiality')},
            'findings':[{'location':'financial_tables','problem':'The debt caveat is repeated.',
                         'fix':'Consolidate the debt caveat and remove the repetitions without changing financial values.',
                         'citations':['D1']}]}
        self.review['criteria']['concise_writing'] = {'status':'fail'}
        self.review['questions'] = {name:{'status':'answered'} for name in ('demand','earnings','cash','outlook','valuation')}
        self.before = self.render(self.analysis, {}, None)
        self.job = core.create(self.root, {'budget_tokens':1000, 'code_commit':'a'*40})
        self.job.update(stage='review', status='ready', revision_round=2, tokens_used=100)
        self.job['artifacts'] = {name:self.save(name,value) for name,value in {
            'analysis-r2.json':self.analysis,'financial-analysis.json':{},'financial-tables.md':'| Cash | 12 |',
            'report.md':self.before,'sources/manifest.json':{},'writing-standard.md':'Fictional writing standard'}.items()}
        self.job['attempts'] = [{'id':'prior','stage':'analysis','revision_round':2,'status':'completed',
            'usage_recorded':True,'outcome':{'tokens':100,'session_id':'fictional-author'}}]
        core._write(self.root, self.job)
        self.addCleanup(patch.stopall)
        patch('research.earnings_sequential_stages.render_candidate',side_effect=self.render).start()
        patch.object(revisions,'_source_bindings',return_value=[{'path':'fictional','sha256':'a'*64}]).start()

    @staticmethod
    def render(analysis, financial, manifest):
        return '# Fictional Widgets\n\n## Cash\n\n| Cash | 12 |\n\n'+editorial.MISSING+'\n\n'+editorial.NOTICE+'\n\n'+analysis['sections']['cash']['text']+' [^D1]\n'

    def save(self,name,value):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(value if isinstance(value,str) else json.dumps(value))
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def review_handler(self,root,job):
        name=editorial.review_name(job)
        return {'status':'revise','revision_target':'financial_tables','tokens':20,
            'execution_certainty':'completed','session_id':'fictional-review-'+name,
            'input_sha256':job['artifacts'][job['candidate_artifact']],
            'outputs':{name:self.save(name,self.review)}}

    def test_only_generated_notices_are_deleted(self):
        after=editorial.repair(self.before,self.analysis,self.review)
        self.assertEqual(after,self.before.replace(editorial.MISSING+'\n\n','').replace(editorial.NOTICE+'\n\n',''))
        self.assertIn('| Cash | 12 |',after)
        self.assertIn(self.analysis['sections']['cash']['text'],after)

    def test_missing_retained_qualifier_declines(self):
        for text in ('Debt unavailable.','Lease liabilities are debt.','Cash supports operations.'):
            analysis=copy.deepcopy(self.analysis);analysis['sections']['cash']['text']=text
            self.assertIsNone(editorial.repair(self.render(analysis,{},None),analysis,self.review))

    def test_substantive_failure_or_unrelated_finding_declines(self):
        for criterion in ('source_accuracy','financial_context','materiality'):
            review=copy.deepcopy(self.review);review['criteria'][criterion]['status']='fail'
            self.assertIsNone(editorial.repair(self.before,self.analysis,review))
        review=copy.deepcopy(self.review);review['findings'][0]['fix']='Recalculate debt.'
        self.assertIsNone(editorial.repair(self.before,self.analysis,review))
        review=copy.deepcopy(self.review);review['findings'].append({'location':'demand','problem':'Unsupported demand.', 'fix':'Remove claim.'})
        self.assertIsNone(editorial.repair(self.before,self.analysis,review))

    def test_ambiguous_missing_or_different_section_notices_decline(self):
        for candidate in (self.before+editorial.NOTICE+'\n',self.before.replace(editorial.MISSING,''),
                          self.before.replace(self.analysis['sections']['cash']['text'],'## Different section\n'+self.analysis['sections']['cash']['text'])):
            self.assertIsNone(editorial.repair(candidate,self.analysis,self.review))

    def test_automatic_repair_at_revision_cap_goes_directly_to_review(self):
        original=copy.deepcopy(self.job['artifacts'])
        job=core.advance(self.root,{'review':self.review_handler})
        self.assertEqual((job['stage'],job['status'],job['revision_round'],job['tokens_used']),('review','ready',2,120))
        self.assertIsNone(job['accepted_candidate_sha256'])
        self.assertEqual(job['budget_tokens'],1000)
        self.assertTrue(all(job['artifacts'][k]==v for k,v in original.items()))
        loaded=revisions.load(self.root,job,self.render)
        self.assertEqual(loaded['plan']['allowed_locations'],[])
        self.assertEqual(editorial.review_name(job),'review-r2-editorial1.json')
        self.assertEqual((self.root/'report.md').read_text(),self.before)

    def test_second_failed_review_stops_without_another_repair(self):
        core.advance(self.root,{'review':self.review_handler})
        job=core.advance(self.root,{'review':self.review_handler})
        self.assertEqual(job['status'],'blocked')
        self.assertIn('bounded repair exhausted',job['reason'])
        self.assertEqual(job['tokens_used'],140)

    def test_passing_review_binds_repaired_candidate(self):
        core.advance(self.root,{'review':self.review_handler})
        def passing(root,job):
            result=self.review_handler(root,job);result.update(status='completed');result.pop('revision_target')
            return result
        job=core.advance(self.root,{'review':passing})
        self.assertEqual((job['stage'],job['status']),('publication','ready'))
        self.assertEqual(job['accepted_candidate_sha256'],job['artifacts']['report-editorial-1.md'])
        self.assertNotEqual(job['accepted_candidate_sha256'],job['artifacts']['report.md'])

    def test_candidate_financial_and_proof_tampering_block(self):
        job=core.advance(self.root,{'review':self.review_handler})
        for name in ('report-editorial-1.md','financial-tables.md','editorial-repair-1.json','report.md'):
            path=self.root/name;original=path.read_text();path.write_text(original+'changed')
            with self.assertRaises(ValueError):revisions.load(self.root,job,self.render)
            path.write_text(original)

    def test_source_changes_block(self):
        job=core.advance(self.root,{'review':self.review_handler})
        with patch.object(revisions,'_source_bindings',return_value=[]):
            with self.assertRaisesRegex(ValueError,'source binding'):revisions.load(self.root,job,self.render)

    def test_budget_and_final_allowance_do_not_enable_repair(self):
        for key,value in [('tokens_used',1000),('final_review',{'state':'blocked'})]:
            job=copy.deepcopy(self.job);job[key]=value
            outcome=self.review_handler(self.root,job)
            self.assertIsNone(editorial.prepare(self.root,job,outcome['outputs'],outcome,self.render))

    def test_operator_adopts_closed_failure_without_resetting_usage(self):
        with patch.object(core,'_editorial_revision',return_value=False):
            job=core.advance(self.root,{'review':self.review_handler})
        self.assertEqual(job['status'],'blocked')
        job=core.repair_editorial(self.root,'User requests bounded editorial correction and review','b'*40)
        self.assertEqual((job['tokens_used'],job['revision_round'],job['budget_tokens']),(120,2,1000))
        self.assertEqual(job['execution_code_commit'],'b'*40)
        with self.assertRaises(ValueError):core.repair_editorial(self.root,'again','b'*40)

    def test_failed_or_uncertain_review_cannot_be_adopted(self):
        outcome=self.review_handler(self.root,self.job)
        for certainty in ('unknown','closed','not_started'):
            changed={**outcome,'execution_certainty':certainty}
            self.assertIsNone(editorial.prepare(self.root,self.job,changed['outputs'],changed,self.render))

    def test_explicit_review_allowance_is_recorded_without_reset(self):
        with patch.object(core,'_editorial_revision',return_value=False):
            core.advance(self.root,{'review':self.review_handler})
        job=core.repair_editorial(self.root,'User requests one review','b'*40,review_cap=1100)
        self.assertEqual(job['budget_tokens'],1220)
        self.assertEqual(job['tokens_used'],120)
        self.assertEqual(job['administrative_history'][-1]['previous_budget_tokens'],1000)
        self.assertEqual(job['revision_round'],2)

    def test_failed_question_is_not_a_presentation_only_repair(self):
        self.review['questions']['cash']['status']='fail'
        self.assertIsNone(editorial.repair(self.before,self.analysis,self.review))

    def test_review_stage_keeps_prior_review_and_uses_new_candidate(self):
        from research import earnings_sequential_stages as stages
        job=core.advance(self.root,{'review':self.review_handler})
        old=(self.root/'review-r2.json').read_bytes()
        with patch.object(stages,'_model',return_value=(self.review,{'tokens':20,'session_id':'fresh','execution_certainty':'completed'})):
            outcome=stages.review(self.root,job)
        self.assertEqual(outcome['status'],'revise')
        self.assertEqual(outcome['input_sha256'],job['artifacts']['report-editorial-1.md'])
        self.assertIn('review-r2-editorial1.json',outcome['outputs'])
        self.assertEqual((self.root/'review-r2.json').read_bytes(),old)
