"""Fictitious source omissions; never real research or provider calls."""
import copy
import json
import unittest
from unittest.mock import patch
from test_earnings_passages import PassageFixture
from research import earnings_evidence_handoff as h, earnings_batch_review as b
from research import earnings_batch_context as context
import test_earnings_batch_review as batch_fixtures


class HandoffTests(PassageFixture, unittest.TestCase):
    def test_gap_prose_expands_existing_document_exactly(self):
        original=copy.deepcopy(self.bundle)
        chunk=self.bundle['documents']['chunks'][0]
        packet=h.packet(self.bundle,self.catalog,{'gaps':[chunk['id']+' is missing']})
        span=packet['slices'][0]['spans'][0]
        self.assertEqual(span['text'],h.evidence._text(chunk['path'])[chunk['start']:chunk['end']])
        self.assertEqual(self.bundle,original)
        self.assertEqual(h.absence_claims({'gap':chunk['id']+' is absent'},h.registry(self.bundle,self.catalog)),{chunk['id']})
    def test_unknown_source_is_specific_pre_call_blocker(self):
        with self.assertRaisesRegex(ValueError,'Unregistered evidence references: D9999'):
            h.packet(self.bundle,self.catalog,{'citation':['D9999']})
    def test_mutated_packet_rejected(self):
        values={'gap':self.bundle['documents']['chunks'][0]['id']+' is missing'}
        packet=h.packet(self.bundle,self.catalog,values)
        packet['slices']=[]
        with self.assertRaises(ValueError):h.verify_packet(packet,self.bundle,self.catalog,values)
    def test_source_change_is_not_silently_repaired(self):
        chunk=self.bundle['documents']['chunks'][0]
        from pathlib import Path
        Path(chunk['path']).write_text('changed source')
        with self.assertRaises(ValueError):h.packet(self.bundle,self.catalog,[chunk['id']])
    def test_exchange_closure_keeps_every_turn(self):
        exchange=self.bundle['transcript_index']['exchanges'][0]
        packet=h.packet(self.bundle,self.catalog,[exchange['turn_ids'][0]])
        self.assertTrue(set(exchange['turn_ids'])<=set(packet['scope_ids']))
        self.assertIn(exchange['id'],packet['scope_ids'])


class RecheckTests(PassageFixture, unittest.TestCase):
    state = batch_fixtures.BatchTests.state
    pack = batch_fixtures.BatchTests.pack
    items = batch_fixtures.BatchTests.items
    decision = batch_fixtures.BatchTests.decision
    def test_scoped_recheck_preserves_all_bytes_and_rounds(self):
        items=self.items();original=copy.deepcopy(items)
        key='financial';known=self.bundle['documents']['chunks'][0]['id']
        findings={key:known+' is absent'}
        accepted={k:{'unit_sha256':b.runner.digest(v),'review_receipt_sha256':'old'} for k,v in items.items() if k!=key}
        protocol=self.root/'protocol.json';protocol.write_text('{}')
        _,_,_,waiting=h.recheck(self.root,items,accepted,findings,self.bundle,self.catalog,2,set(),10)
        self.assertEqual(waiting['round'],2)
        self.assertEqual(waiting['stage'],'source_handoff_review')
        self.assertEqual(items,original)
        self.assertNotIn('rendered_report',waiting['prompt'])
        self.assertNotIn('financial_observations',waiting['prompt'])
        job=self.root/'batches/2/source-handoff-review';job.mkdir(parents=True)
        (job/'output.json').write_text('{}');(job/'prompt.txt').write_text(waiting['prompt'])
        request={'bindings':waiting['bindings'],'model':b.MODEL[0],'effort':b.MODEL[1]}
        review=self.decision(items,{key})
        result={'receipt':{'session':{'id':'fresh','usage':{'totalTokens':7}}},'content':review}
        with patch.object(h.runner,'verify_job',return_value=result),patch.object(h.runner,'read',return_value=request):
            updated,residual,tokens,pending=h.recheck(self.root,items,accepted,findings,self.bundle,self.catalog,2,set(),10)
        self.assertIsNone(pending);self.assertFalse(residual);self.assertEqual(tokens,17)
        self.assertEqual(items,original)
        for k in accepted:self.assertEqual(updated[k],accepted[k])
    def test_substantive_findings_do_not_trigger_transport_recheck(self):
        self.assertEqual(h.recheck_units({'financial':'Reported growth is incorrect'},self.bundle,self.catalog),{})
    def test_new_prompt_expands_prose_reference_old_policy_unchanged(self):
        items=self.items();chunk=self.bundle['documents']['chunks'][0]
        items['financial']['value'].setdefault('gaps',[]).append(chunk['id']+' is missing')
        args=(items,items,{'financial'},{},{},self.catalog,'Fake guide',1,self.bundle,b.FACTUAL_VERSION)
        old=b.prompt(*args,context.VERSION)
        new=b.prompt(*args,context.CHECKED_VERSION)
        self.assertNotIn('evidence_handoff',old)
        self.assertIn('evidence_handoff',new)
        from research import earnings_repair_context as t
        payload=t.expand_context(json.loads(new.split('\nBATCH\n')[1]))
        self.assertIn(chunk['id'],payload['evidence_handoff']['references'])

    def test_controller_replay_advances_source_check_without_author_round(self):
        from pathlib import Path
        items=self.items();root=self.root/'checked';root.mkdir()
        b.runner.save(root/'protocol.json',{})
        protocol={'version':b.FACTUAL_VERSION,'source_protocol':{},'review_context':context.CHECKED_VERSION,
                  'review_evidence_contract':'original-passages-and-financial-observations-v1'}
        registered=h.registry(self.bundle,self.catalog)
        cited=h.references(items)
        document=next(k for k in registered if k.startswith('D') and k not in cited)
        before=copy.deepcopy(items)
        calls=[]
        def verify(job):
            return {'content':b.runner.read(job/'output.json'),
                    'receipt':{'session':{'id':str(job),'usage':{'totalTokens':11}}}}
        def run(job,text,model,effort,bindings,timeout):
            job=Path(job);job.mkdir(parents=True);calls.append(str(job))
            self.assertEqual(job.name,'source-handoff-review')
            (job/'prompt.txt').write_text(text)
            b.runner.save(job/'request.json',{'model':model,'effort':effort,'bindings':bindings})
            b.runner.save(job/'output.json',self.decision(items,{'financial'}))
        with patch.object(b,'load',return_value=(protocol,items,self.bundle,self.catalog,'Fake guide')),patch.object(b.runner,'verify_job',side_effect=verify),patch.object(b.runner,'run_role',side_effect=run):
            initial=b.replay(root);job=Path(initial['job']);job.mkdir(parents=True)
            (job/'prompt.txt').write_text(initial['prompt'])
            b.runner.save(job/'request.json',{'model':b.MODEL[0],'effort':b.MODEL[1],'bindings':initial['bindings']})
            review=self.decision(items,set(items),{'financial'})
            next(d for d in review['decisions'] if d['unit_id']=='financial')['reason']=document+' is not supplied; inspect its basis.'
            b.runner.save(job/'output.json',review)
            waiting=b.replay(root)
            self.assertEqual(waiting['stage'],'source_handoff_review')
            self.assertEqual(waiting['round'],0)
            result=b.advance(root,True)
            self.assertEqual(result['status'],'accepted');self.assertEqual(result['round'],0)
            accepted=b.replay(root)['accepted']
            self.assertEqual(accepted['analysis:0']['review_receipt_sha256'],b.runner.sha(job/'output.json'))
            self.assertEqual(result['tokens'],22)
            self.assertEqual(len(calls),1)
            self.assertEqual(items,before)
            self.assertFalse((root/'batches/1').exists())
            b.advance(root,False);self.assertEqual(len(calls),1)

    def test_already_supplied_source_does_not_add_another_review(self):
        items=self.items();document=self.bundle['documents']['chunks'][0]['id']
        _,_,_,waiting=h.recheck(self.root,items,{}, {'financial':document+' missing'},self.bundle,self.catalog,0,set(),0,{document})
        self.assertIsNone(waiting)

    def test_supplement_deduplicates_complete_source_but_expands_preview(self):
        chunk=self.bundle['documents']['chunks'][0]
        packet=h.packet(self.bundle,self.catalog,[chunk['id']])
        text=packet['slices'][0]['spans'][0]['text']
        full=h.append_prompt(json.dumps({'source':text},ensure_ascii=False),self.bundle,self.catalog,[chunk['id']])
        preview=h.append_prompt(json.dumps({'preview':text[:3]}),self.bundle,self.catalog,[chunk['id']])
        self.assertEqual(json.loads(full.split('\nCHECKED ORIGINAL EVIDENCE HANDOFF\n')[1].split('\nAll referenced')[0])['missing_original_spans'],[])
        self.assertIn('span_sha256',preview)

    def test_reviewer_correction_of_stale_prose_is_a_factual_edit(self):
        document=self.bundle['documents']['chunks'][0]['id']
        reason='The draft incorrectly says '+document+' is absent. Remove the obsolete claim.'
        self.assertEqual(h.recheck_units({'financial':reason},self.bundle,self.catalog),{})

    def test_uncertain_source_check_never_launches_again(self):
        items=self.items();document=self.bundle['documents']['chunks'][0]['id']
        (self.root/'protocol.json').write_text('{}')
        job=self.root/'batches/0/source-handoff-review';job.mkdir(parents=True)
        (job/'request.json').write_text('{}')
        _,_,_,waiting=h.recheck(self.root,items,{}, {'financial':document+' absent'},self.bundle,self.catalog,0,set(),0)
        self.assertEqual(waiting['status'],'execution_uncertain')

    def test_persistent_absence_stops_after_one_receipted_check(self):
        items=self.items();document=self.bundle['documents']['chunks'][0]['id']
        (self.root/'protocol.json').write_text('{}')
        findings={'financial':document+' absent'}
        _,_,_,waiting=h.recheck(self.root,items,{},findings,self.bundle,self.catalog,0,set(),0)
        job=self.root/'batches/0/source-handoff-review';job.mkdir(parents=True)
        (job/'output.json').write_text('{}');(job/'prompt.txt').write_text(waiting['prompt'])
        request={'bindings':waiting['bindings'],'model':b.MODEL[0],'effort':b.MODEL[1]}
        review=self.decision(items,{'financial'},{'financial'})
        review['decisions'][0]['reason']=document+' absent'
        result={'receipt':{'session':{'id':'independent','usage':{'totalTokens':8}}},'content':review}
        with patch.object(h.runner,'verify_job',return_value=result),patch.object(h.runner,'read',return_value=request):
            _,_,tokens,stopped=h.recheck(self.root,items,{},findings,self.bundle,self.catalog,0,set(),0)
        self.assertEqual(stopped['status'],'blocked');self.assertEqual(tokens,8)
        self.assertFalse((self.root/'batches/1').exists())

    def test_ordinary_pressure_units_and_model_names_are_not_source_ids(self):
        self.assertEqual(h.references('Pressure is 10 Pa; the aircraft is F16.'),set())
