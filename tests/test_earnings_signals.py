"""Fictional signal annotations; no model calls or company data."""
import copy
from html.parser import HTMLParser
import unittest
from test_earnings_passages import PassageFixture
from research import earnings_signals as s
from research import earnings_experiment as base
from research import earnings_passage_pipeline as pipe


class SignalTests(PassageFixture, unittest.TestCase):
    def state(self):
        return {'artifacts':{'financial':copy.deepcopy(self.financial),'retrieval':copy.deepcopy(self.retrieval),'analysis':copy.deepcopy(self.report)},'format':{'rows':{},'basis':{'text':'','citations':[]}}}

    def pack(self,state):
        keys=list(s.finding_catalog(state))
        return {'report_sha256':s.report_digest(state),'signals':[{'id':f'signal-{i+1}','finding_id':keys[i],
            'direction':direction,'evidence_basis':'reported_result','label':'Fictional result','summary':'Fictional completed milestone.',
            'comparison':'Fictional prior milestone.','period':'Fictional quarter','rationale':'Fictional evidence-backed improvement.',
            'citations':['D001'],'passage_ids':[self.ids[0]]} for i,direction in enumerate(s.DIRECTIONS)]}

    def review(self,pack):
        return {'signals_sha256':base.digest(pack),'verdict':'pass','criteria':{k:{'status':'pass','evidence':'Fictional source check'} for k in s.CRITERIA},
                'decisions':[{'id':x['id'],'approved':True,'reason':'Fictional evidence','citations':['D001'],'passage_ids':[self.ids[0]]} for x in pack['signals']]}

    def test_stale_report_cannot_reuse_signals(self):
        state=self.state();p=self.pack(state);state['artifacts']['analysis']['opening']='Changed'
        with self.assertRaises(ValueError):s.validate(p,state,self.bundle,self.catalog)

    def test_signal_unknown_fields_ids_and_categories_rejected(self):
        state=self.state()
        for key,value in [('direction','buy'),('evidence_basis','high_confidence'),('finding_id','wrong'),('id','x'),('citations',['bad']),('passage_ids',['bad']),('label','x'*61)]:
            p=self.pack(state);p['signals'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):s.validate(p,state,self.bundle,self.catalog)
        p=self.pack(state);p['signals'][0]['company_score']=100
        with self.assertRaises(ValueError):s.validate(p,state,self.bundle,self.catalog)

    def test_does_not_force_four_signals_or_one_of_each_direction(self):
        state=self.state();p=self.pack(state);p['signals']=p['signals'][:2]
        for x in p['signals']:x['direction']='improving'
        self.assertEqual(s.validate(p,state,self.bundle,self.catalog),p)

    def test_each_signal_approved_and_review_digest_matches(self):
        state=self.state();p=self.pack(state);r=self.review(p)
        self.assertTrue(s.validate_review(r,p,state,self.bundle,self.catalog))
        for mutate in (lambda r:r.update(signals_sha256='stale'),lambda r:r['decisions'].pop(),lambda r:r['decisions'][0].update(approved=False),lambda r:r['criteria']['source_support'].update(status='fail')):
            r=self.review(p);mutate(r)
            with self.assertRaises(ValueError):s.validate_review(r,p,state,self.bundle,self.catalog)

    def test_rejected_signals_never_render_as_accepted(self):
        state=self.state();p=self.pack(state);r=self.review(p);r['verdict']='blocked';r['decisions'][0]['approved']=False
        target=self.root/'report.html'
        with self.assertRaises(ValueError):s.render(target,state,p,r,self.bundle,self.catalog)
        self.assertFalse(target.exists())

    def test_renderer_escapes_text_preserves_prose_and_has_all_link_targets(self):
        state=self.state();before=copy.deepcopy(state);p=self.pack(state)
        p['signals'][0]['label']='<script>alert(1)</script>'
        p['signals'][0]['evidence_basis']='management_guidance'
        s.render(self.root/'report.html',state,p,self.review(p),self.bundle,self.catalog)
        text=(self.root/'report.html').read_text()
        self.assertNotIn('<script>',text);self.assertIn('&lt;script&gt;',text)
        for f in state['artifacts']['analysis']['findings']:self.assertIn(f['text'],text)
        self.assertIn('Management guidance',text);self.assertIn('Business signals',text)
        for label in s.DIRECTIONS.values():self.assertIn(label,text)
        class Links(HTMLParser):
            def __init__(self):super().__init__();self.ids=[];self.targets=[]
            def handle_starttag(self,tag,attrs):
                a=dict(attrs)
                if 'id' in a:self.ids.append(a['id'])
                if a.get('href','').startswith('#'):self.targets.append(a['href'][1:])
        links=Links();links.feed(text)
        self.assertFalse(set(links.targets)-set(links.ids));self.assertEqual(len(links.ids),len(set(links.ids)))
        self.assertEqual(state,before)

    def test_multiple_signals_can_describe_different_aspects_of_one_finding(self):
        state=self.state();p=self.pack(state);p['signals'][1]['finding_id']=p['signals'][0]['finding_id']
        s.render(self.root/'report.html',state,p,self.review(p),self.bundle,self.catalog)
        self.assertTrue((self.root/'report.html').exists())

    def test_frozen_opt_in_binds_signal_code(self):
        w=self.root/'writing.txt';w.write_text('Fictional standard')
        p=pipe.freeze(self.casepath,self.root/'run',w,signals=True)
        self.assertTrue(p['report_signals']);self.assertTrue(any(x['path'].endswith('earnings_signals.py') for x in p['code']))

    def test_new_runs_enable_signals_and_allow_explicit_opt_out(self):
        w=self.root/'writing.txt';w.write_text('Fictional standard')
        enabled=pipe.freeze(self.casepath,self.root/'default-run',w)
        disabled=pipe.freeze(self.casepath,self.root/'disabled-run',w,signals=False)
        self.assertTrue(enabled['report_signals'])
        self.assertFalse(disabled['report_signals'])
        # New grounded freezes pin all transitive earnings helpers even when a
        # stage is disabled; the execution flag remains authoritative.
        self.assertTrue(any(x['path'].endswith('earnings_signals.py') for x in disabled['code']))

    def test_cli_signals_default_and_opt_out_are_frozen(self):
        from unittest.mock import patch
        for flags,expected in (([],True),(['--signals'],True),(['--no-signals'],False)):
            with self.subTest(flags=flags),patch('sys.argv',['pipeline','freeze','case','output','writing',*flags]),patch.object(pipe,'freeze') as freeze:
                pipe.main()
                self.assertIs(freeze.call_args.args[-1],expected)

    def test_signal_stage_resumes_and_verifies_without_duplicate_calls(self):
        from unittest.mock import patch
        import json
        state=self.state();p=self.pack(state);r=self.review(p)
        root=self.root/'signals';root.mkdir();base.save(root/'protocol.json',{'fake':True})
        protocol={'max_tokens':100,'max_prompt_chars':750000};calls=[]
        def fake_run(job,text,model,effort,bindings,timeout):
            job.mkdir(parents=True);calls.append(job.name)
            base.save(job/'request.json',{'model':model,'effort':effort,'bindings':bindings});(job/'prompt.txt').write_text(text)
            base.save(job/'output.json',{'content':p if job.name=='analysis' else r,'receipt':{'session':{'id':job.name,'usage':{'totalTokens':10}}}})
        with patch.object(s,'load',return_value=(protocol,state,self.bundle,self.catalog,'Fictional')),patch.object(s,'run_role',side_effect=fake_run),patch.object(s,'verify_job',side_effect=lambda job:base.read(job/'output.json')):
            self.assertEqual(s.advance(root)['status'],'pending');self.assertEqual(calls,['analysis'])
            self.assertEqual(s.advance(root)['status'],'accepted');self.assertEqual(calls,['analysis','review'])
            self.assertEqual(s.verify(root)['status'],'accepted');self.assertEqual(calls,['analysis','review'])
            (root/'signals.json').write_text('{}')
            with self.assertRaises(ValueError):s.verify(root)

    def test_uncertain_launch_is_not_retried(self):
        from unittest.mock import patch
        root=self.root/'signals';root.mkdir();base.save(root/'protocol.json',{})
        job=root/'jobs/analysis';job.mkdir(parents=True);base.save(job/'request.json',{})
        with patch.object(s,'load',return_value=({'max_tokens':100,'max_prompt_chars':750000},self.state(),self.bundle,self.catalog,'Fictional')),patch.object(s,'run_role') as runner:
            self.assertEqual(s.advance(root)['status'],'launch_uncertain');runner.assert_not_called()
