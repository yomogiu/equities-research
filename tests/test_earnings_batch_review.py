"""Fictional batch review lifecycle; no provider calls."""
import copy
import json
import unittest
from unittest.mock import patch
import test_earnings_signals as fixtures
from test_earnings_passages import PassageFixture
from research import earnings_batch_review as b


class BatchTests(PassageFixture, unittest.TestCase):
    state = fixtures.SignalTests.state
    pack = fixtures.SignalTests.pack
    def items(self):
        state=self.state()
        return b.units(state,self.pack(state))

    def decision(self,items,pending,fail=()):
        return {'batch_sha256':b.runner.digest(items),'decisions':[
            {'unit_id':k,'verdict':'revise' if k in fail else 'pass',
             'reason':'Fictional exact-source assessment','passage_ids':[self.ids[0]]} for k in sorted(pending)],'reopen':[]}

    def plan(self,items,keys):
        changes=[]
        for key in keys:
            value=copy.deepcopy(items[key]['value'])
            value['label' if key.startswith('signal-') else 'text']='Fictional revised wording'
            changes.append({'unit_id':key,'before_sha256':b.runner.digest(items[key]['value']),
                            'value':value,'reason':'Fictional review finding'})
        return {'before_sha256':b.runner.digest(items),'changes':changes}

    def test_signal_only_keeps_report_acceptance(self):
        items=self.items();accepted,_=b.adjudicate(items,set(items),{},self.decision(items,items),self.catalog,'receipt')
        updated,pending=b.apply(items,self.plan(items,['signal-1']))
        self.assertEqual(pending,{'signal-1'})
        for k in pending:accepted.pop(k)
        final,findings=b.adjudicate(updated,pending,accepted,self.decision(updated,pending),self.catalog,'second')
        self.assertFalse(findings)
        self.assertEqual(final['analysis:0']['review_receipt_sha256'],'receipt')
        self.assertEqual(final['signal-1']['review_receipt_sha256'],'second')

    def test_mixed_batch_invalidates_dependencies_and_preserves_other_signals(self):
        items=self.items();updated,pending=b.apply(items,self.plan(items,['analysis:0','signal-2']))
        self.assertEqual(pending,{'analysis:0','analysis:next_tests','signal-1','signal-2'})
        b.validate(updated,self.bundle,self.catalog)
        self.assertEqual(updated['analysis:1'],items['analysis:1'])

    def test_stale_duplicate_and_noop_batches_fail(self):
        items=self.items()
        for change in ('stale','duplicate','noop'):
            plan=self.plan(items,['signal-1'])
            if change=='stale':plan['before_sha256']='wrong'
            if change=='duplicate':plan['changes']*=2
            if change=='noop':plan['changes'][0]['value']=items['signal-1']['value']
            with self.subTest(change=change),self.assertRaises(ValueError):b.apply(items,plan)

    def test_reopen_requires_actual_evidence_and_invalidates_dependents(self):
        items=self.items();review=self.decision(items,{'signal-1'})
        review['reopen']=[{'unit_id':'analysis:0','reason':'Fictional contradiction','passage_ids':['invented']}]
        with self.assertRaises(ValueError):b.adjudicate(items,{'signal-1'},{},review,self.catalog,'x')
        review['reopen'][0]['passage_ids']=self.ids[:1]
        _,findings=b.adjudicate(items,{'signal-1'},{},review,self.catalog,'x')
        self.assertEqual(set(findings),{'analysis:0','analysis:next_tests','signal-1'})

    def test_delta_prompt_preserves_full_exchange_sources_and_reduces_context(self):
        items=self.items();updated,pending=b.apply(items,self.plan(items,['signal-1']))
        baseline=b.prompt(items,items,set(items),{}, {},self.catalog,'Fictional writing',0,self.bundle)
        delta=b.prompt(items,updated,pending,{}, {},self.catalog,'Fictional writing',1,self.bundle)
        self.assertLess(len(delta),len(baseline))
        self.assertIn('rendered_report',delta)
        self.assertNotIn('financial_source_context',delta)
        self.assertIn('original_passages',delta)

    def test_authenticated_lifecycle_two_round_limit_and_saved_acceptance(self):
        items=self.items();root=self.root/'batch';root.mkdir()
        b.runner.save(root/'protocol.json',{'fictional':True})
        protocol={'source_protocol':{}}
        def verify(job):
            n=int(job.parent.name)
            return {'content':b.runner.read(job/'output.json'),
                    'receipt':{'session':{'id':'fresh-'+str(n),'usage':{'totalTokens':10}}}}
        with patch.object(b,'load',return_value=(protocol,items,self.bundle,self.catalog,'Fictional writing')),patch.object(b.runner,'verify_job',side_effect=verify):
            for n in range(3):
                v=b.replay(root);self.assertEqual(v['status'],'pending')
                job=__import__('pathlib').Path(v['job']);job.mkdir(parents=True)
                (job/'prompt.txt').write_text(v['prompt'])
                b.runner.save(job/'request.json',{'bindings':v['bindings'],'model':b.MODEL[0],'effort':b.MODEL[1]})
                pending=set(items) if n==0 else {'signal-1'}
                b.runner.save(job/'output.json',self.decision(v['items'],pending,{'signal-1'}))
                status=b.advance(root)
                self.assertEqual(status['tokens'],10*(n+1))
                if n<2:
                    self.assertEqual(status['status'],'awaiting_batch')
                    plan=self.plan(b.replay(root)['items'],['signal-1'])
                    plan['changes'][0]['value']['label']+=' '+str(n)
                    b.submit(root,plan)
            self.assertEqual(status['status'],'blocked')
            self.assertFalse((root/'report.html').exists())
            with self.assertRaises(ValueError):b.submit(root,self.plan(items,['signal-2']))
            self.assertTrue((root/'acceptance-2-blocked.json').exists())

    def test_uncertain_execution_never_relaunches(self):
        root=self.root/'batch';root.mkdir();b.runner.save(root/'protocol.json',{})
        folder=root/'batches/0/review';folder.mkdir(parents=True);(folder/'request.json').write_text('{}')
        with patch.object(b,'load',return_value=({'source_protocol':{}},self.items(),self.bundle,self.catalog,'Writing')),patch.object(b.runner,'run_role') as call:
            self.assertEqual(b.advance(root,True)['status'],'execution_uncertain');call.assert_not_called()

    def test_stale_signal_input_is_rejected_before_initialization(self):
        state=self.state();pack=self.pack(state);pack['report_sha256']='stale'
        with patch.object(b.remediation,'_source_bundle',return_value=(self.bundle,self.catalog)),self.assertRaises(ValueError):
            b.initialize({},state,pack,self.root/'new','Fictional authorization')

    def test_complete_acceptance_renders_and_replays_without_another_call(self):
        items=self.items();root=self.root/'accepted';root.mkdir()
        b.runner.save(root/'protocol.json',{})
        def verify(job):
            return {'content':b.runner.read(job/'output.json'),
                    'receipt':{'session':{'id':'independent','usage':{'totalTokens':12}}}}
        with patch.object(b,'load',return_value=({'source_protocol':{}},items,self.bundle,self.catalog,'Writing')),patch.object(b.runner,'verify_job',side_effect=verify),patch.object(b.runner,'run_role') as call:
            v=b.replay(root);job=__import__('pathlib').Path(v['job']);job.mkdir(parents=True)
            (job/'prompt.txt').write_text(v['prompt'])
            b.runner.save(job/'request.json',{'bindings':v['bindings'],'model':b.MODEL[0],'effort':b.MODEL[1]})
            b.runner.save(job/'output.json',self.decision(items,items))
            self.assertEqual(b.advance(root,True)['status'],'accepted')
            self.assertEqual(b.advance(root,True)['status'],'accepted')
            call.assert_not_called()
            self.assertIn('Business signals',(root/'report.html').read_text())
            self.assertTrue((root/'acceptance-0-accepted.json').exists())

    def test_format_changes_reopen_financial_interpretations(self):
        items=self.items()
        pending=b.affected(items,{'format'})
        self.assertIn('analysis:0',pending)
        self.assertIn('signal-1',pending)
        self.assertNotIn('retrieval',pending)

    def test_signal_binding_edits_are_never_silently_discarded(self):
        items=self.items();plan=self.plan(items,['signal-1'])
        plan['changes'][0]['value']['finding_id']='different-finding'
        with self.assertRaises(ValueError):b.apply(items,plan)

    def test_initializer_pins_sources_and_requires_exact_input_roundtrip(self):
        writing=self.root/'writing.txt';writing.write_text('Fictional writing')
        protocol={'writing_standard':str(writing),'writing_sha256':b.runner.sha(writing)}
        state=self.state();pack=self.pack(state);root=self.root/'initialized'
        with patch.object(b.remediation,'_source_bundle',return_value=(self.bundle,self.catalog)):
            b.initialize(protocol,state,pack,root,'New fictional draft')
            b.load(root)
            changed=copy.deepcopy(self.bundle);changed['unexpected']='changed'
            with patch.object(b.remediation,'_source_bundle',return_value=(changed,self.catalog)),self.assertRaisesRegex(ValueError,'Frozen source'):
                b.load(root)
        state['artifacts']['analysis']['ignored_field']='must not disappear'
        pack=self.pack(state)
        with patch.object(b.remediation,'_source_bundle',return_value=(self.bundle,self.catalog)),self.assertRaises(ValueError):
            b.initialize(protocol,state,pack,self.root/'other','New fictional draft')
