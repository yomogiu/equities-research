"""Fictional lossless handoff compression and delivered-source batching."""
import copy
import json
import unittest
from test_earnings_passages import PassageFixture
from research import earnings_file_context as context
from research import earnings_file_pipeline as pipeline
from research import earnings_mixed_runner as base


class CompactRoleContextTests(PassageFixture,unittest.TestCase):
    def assemble(self,name,*,compact=True,markdown=None,artifacts=None,sequential=False):
        metadata={'role':'review','pending_findings':{'analysis:0':'Inspect the fictional source.'}}
        if compact:metadata['context_projection']=context.COMPACT_VERSION
        if sequential:metadata.update(workflow='sequential-earnings-stages-v1',support_projection=context.SEQUENTIAL_SUPPORT_VERSION)
        return context.assemble(self.root/'evidence/manifest.json',self.catalog,self.root/name,
            artifacts=artifacts or {'report':self.report},
            markdown=markdown or '# Fictional report\n',metadata=metadata)

    def test_lossless_projection_keeps_report_and_all_nonrendered_fields(self):
        text='Fictional revenue rose, while operating cash declined. Café Δ. '*80
        packet={'metadata':{'pending_findings':{'analysis:0':'Check fictional cash.'}},
            'report_markdown':'# Fictional report\n'+text,
            'artifacts':{'units':{'analysis:0':{'value':{'text':text,'citations':['F002'],
                'unrendered':'Keep this caveat','literal':{'report_text_characters':[0,8]}},
                'depends_on':['financial','retrieval']}},'findings':{'analysis:0':'Check fictional cash.'}}}
        frozen=copy.deepcopy(packet);compact=context.compact_handoff(packet)
        self.assertEqual(packet,frozen)
        self.assertEqual(compact['report_markdown'],packet['report_markdown'])
        self.assertLess(len(json.dumps(compact)),len(json.dumps(packet)))
        self.assertEqual(context.expand_handoff(compact),packet)
        unit=compact['artifacts']['units']['analysis:0']
        self.assertEqual(unit['value']['citations'],['F002'])
        self.assertEqual(unit['value']['unrendered'],'Keep this caveat')
        self.assertEqual(unit['depends_on'],['financial','retrieval'])
        self.assertEqual(unit['value']['literal'],{'report_text_characters':[0,8]})
        compact['report_markdown']=compact['report_markdown'].replace('revenue','profits',1)
        with self.assertRaisesRegex(ValueError,'digest changed'):context.expand_handoff(compact)

    def test_old_packet_bytes_and_explicit_opt_in_are_preserved(self):
        text='Fictional complete narrative retained for independent review. '*100
        artifacts={'units':{'analysis:0':{'value':{'text':text}}}}
        index=self.assemble('old',compact=False,markdown=text,artifacts=artifacts)
        reader=context.Evidence(index,self.root/'legacy.jsonl')
        expected={'metadata':base.read(index.parent/'metadata.json'),
            'report_markdown':text,'artifacts':artifacts}
        self.assertEqual(reader._handoff_body(),json.dumps(expected,ensure_ascii=False,separators=(',',':')))
        with self.assertRaisesRegex(ValueError,'Compact role'):reader.role_batch_plan()
        index=self.assemble('compact',markdown=text,artifacts=artifacts)
        reader=context.Evidence(index,self.root/'compact.jsonl')
        projected=json.loads(reader._handoff_body())
        self.assertIn('projection',projected)
        expected['metadata']=base.read(index.parent/'metadata.json')
        self.assertEqual(context.expand_handoff(projected),expected)
        self.assertEqual(reader.artifacts,artifacts)

    def test_sequential_support_retains_every_source_block_id_and_provenance(self):
        old=self.assemble('original-support')
        new=self.assemble('sequential-support',sequential=True)
        old_reader=context.Evidence(old,self.root/'old.jsonl')
        reader=context.Evidence(new,self.root/'new.jsonl')
        original,old_ids,old_rows=old_reader._support_body()
        projected,ids,rows=reader._support_body()
        a=json.loads(original);b=json.loads(projected)
        self.assertEqual((ids,rows),(old_ids,old_rows))
        self.assertEqual(context.expand_source_map(b),a['source_map'])
        for field in ('unique_original_blocks','files','block_columns','passages','financial_contexts','units'):
            self.assertEqual(b[field],a[field])
        self.assertIn('complete_financial_inventory',a)
        self.assertNotIn('complete_financial_inventory',b)
        self.assertEqual(b['financial_inventory_reference']['sha256'],base.sha(new.parent/'financial.json'))
        # New projection never changes old-context bytes or original source pins.
        self.assertEqual(old_reader._support_body()[0],original)
        self.assertEqual(base.read(old)['original_sha256'],base.read(new)['original_sha256'])
        (new.parent/'financial.json').write_text('{}')
        with self.assertRaises(ValueError):context.Evidence(new,self.root/'changed.jsonl')

    def test_small_handoff_never_expands_just_to_add_projection_metadata(self):
        index=self.assemble('small');reader=context.Evidence(index,self.root/'small.jsonl')
        self.assertNotIn('projection',json.loads(reader._handoff_body()))

    def test_grouped_pages_deliver_original_report_call_and_support(self):
        index=self.assemble('grouped');job=self.root/'job';job.mkdir()
        base.save(job/'request.json',{'context_index':str(index)})
        reader=context.Evidence(index,job/'retrieval.jsonl')
        plan=reader.role_batch_plan()
        self.assertEqual(len(plan),1)
        self.assertFalse(reader.log.exists())
        self.assertEqual([p['method'] for p in plan[0]['packets']],
                         ['handoff_batch','call_batch','support_batch'])
        output=reader.role_batch(0)
        self.assertEqual(plan[0]['characters'],len(output))
        self.assertEqual(plan[0]['utf8_bytes'],len(output.encode()))
        output+=reader.challenge_batch()
        events=context.audit(index,reader.log)
        self.assertEqual(len(events),4)
        delivery='c'*24;(job/'tool-output').mkdir();path=job/'tool-output'/(delivery+'.txt')
        def deliver(text):
            path.write_bytes(text.encode())
            row={'id':delivery,'retrieval_start':0,'retrieval_end':4,'limit':None,
                'delivered_bytes':len(text.encode()),'unsupported':False,'sha256':base.sha(path),
                'original_bytes':len(text.encode()),'complete':True}
            (job/'delivery.jsonl').write_text(json.dumps(row)+'\n')
        deliver(output)
        proof=pipeline.coverage('review',index,job,self.report,self.catalog,reader.artifacts)
        self.assertIn('report.md',proof['files']);self.assertIn('transcript.md',proof['files'])
        self.assertIn('D001',proof['source_ids'])
        # Logging a combined API call is insufficient when its output was cut.
        deliver(output[:output.index('# support_batch')+100])
        with self.assertRaises(ValueError):pipeline.coverage('review',index,job,self.report,self.catalog,reader.artifacts)

    def test_large_pages_fit_boundary_and_reconstruct_all_original_ranges(self):
        # Distinct Unicode prose is not compressible against this small report.
        index=self.assemble('large',artifacts={'long':'Fictional Ω cash disclosure. '*5000})
        reader=context.Evidence(index,self.root/'large.jsonl')
        plan=reader.role_batch_plan();self.assertGreater(len(plan),1)
        self.assertFalse(reader.log.exists())
        for i,page in enumerate(plan):
            output=reader.role_batch(i)
            self.assertLessEqual(len(output),60000)
            self.assertEqual(len(output.encode()),page['utf8_bytes'])
        events=context.audit(index,reader.log)
        self.assertEqual(context.complete_ranges(events,'handoff_batch','name'),{'handoff'})
        self.assertEqual(context.complete_ranges(events,'call_batch','name'),{'transcript.md'})
        self.assertEqual(context.complete_ranges(events,'support_batch','name'),{'support'})
        self.assertEqual(context.inspected_role_batches(index,events)[0],set(reader._support_body()[1]))
        for page in (-1,len(plan),True):
            with self.assertRaisesRegex(ValueError,'Exact planned'):reader.role_batch(page)

    def test_challenge_selects_unrequired_scopes_even_without_query_matches(self):
        index=self.assemble('challenge');reader=context.Evidence(index,self.root/'challenge.jsonl')
        def record(text,document):
            return {'spans':[{'text':text,'path':'/fictional/'+document,'sha256':'fake',
                'document_id':document,'start':0,'end':len(text)}]}
        reader.records={'D001':record('Revenue cash debt guidance EBITDA capital expenditure.','required'),
                        'D002':record('Fictional litigation disclosure.','unrequired')}
        transcript=(index.parent/'transcript.md').read_text()
        reader.records['D003']={'spans':[{'text':transcript,'path':str(index.parent/'transcript.md'),
            'sha256':reader.index['files']['transcript.md'],'document_id':'fictional-call',
            'start':0,'end':len(transcript)}]}
        reader.artifacts={'report':{'citations':['D001']}}
        reader.catalog={'passages':[]}
        ordinary,ids=reader._filing_batch('revenue cash',1)
        self.assertEqual(ids,['D001'])
        packet,ids=reader._challenge_batch('revenue cash',1)
        self.assertEqual(ids,['D002'])
        metadata=json.loads(packet.splitlines()[1])
        self.assertEqual(metadata['challenge_status'],'new_source_scopes')
        self.assertFalse(metadata['challenge_fallback_used'])
        self.assertTrue(metadata['fallback_used'])
        self.assertEqual(metadata['excluded_required_scope_ids'],['D001'])
        self.assertIn('Fictional litigation disclosure.',packet)

    def test_exhausted_challenge_explicitly_rechecks_original_support(self):
        index=self.assemble('exhausted');reader=context.Evidence(index,self.root/'exhausted.jsonl')
        reader.artifacts={'report':{'selected_document_ids':[i for i in reader.records if i.startswith('D')]}}
        packet,ids=reader._challenge_batch('revenue cash',4)
        metadata=json.loads(packet.splitlines()[1])
        self.assertTrue(ids)
        self.assertEqual(metadata['challenge_status'],'exhausted_recheck_required_support')
        self.assertTrue(metadata['challenge_fallback_used'])
        self.assertTrue(set(ids)<=set(reader.artifacts['report']['selected_document_ids']))
        reader.records={};reader.artifacts={};reader.catalog={'passages':[]}
        packet,ids=reader._challenge_batch('revenue cash',4)
        self.assertEqual(ids,[])
        self.assertEqual(json.loads(packet.splitlines()[1])['challenge_status'],'no_eligible_filing_scopes')

    def test_challenge_rejects_duplicate_text_and_overlapping_filing_and_fact_scopes(self):
        index=self.assemble('duplicate-challenge');reader=context.Evidence(index,self.root/'duplicates.jsonl')
        def record(text,document,start=0):
            return {'spans':[{'text':text,'path':'/fictional/'+document,'sha256':'fake-'+document,
                'document_id':document,'start':start,'end':start+len(text)}]}
        reader.records={
            'D001':record('Fictional revenue cash debt disclosure.','required'),
            'D002':record('Fictional revenue cash debt disclosure.','duplicate-copy'),
            'D003':record('revenue cash debt disclosure.','required',10),
            'F001':record('Fictional cash fact.','financial',20),
            'D004':record('cash fact plus adjacent disclosure.','financial',30),
            'D005':record('Fictional litigation disclosure.','additional')}
        reader.artifacts={'report':{'citations':['D001','F001']}}
        reader.catalog={'passages':[]}
        packet,ids=reader._challenge_batch('revenue cash debt',4)
        self.assertEqual(ids,['D005'])
        selection=json.loads(packet.splitlines()[1])
        self.assertEqual(selection['challenge_status'],'new_source_scopes')
        self.assertTrue(selection['fallback_used'])
        self.assertFalse(selection['challenge_fallback_used'])
        # The remaining identifiers all repeat or overlap required evidence.
        # They cannot manufacture a successful fresh-scope challenge.
        del reader.records['D005']
        packet,ids=reader._challenge_batch('revenue cash debt',4)
        selection=json.loads(packet.splitlines()[1])
        self.assertTrue(ids)
        self.assertEqual(selection['challenge_status'],'exhausted_recheck_required_support')
        self.assertTrue(selection['challenge_fallback_used'])

    def test_challenge_requires_visible_exact_delivery_and_preserves_old_api(self):
        index=self.assemble('challenge-audit');job=self.root/'challenge-job';job.mkdir()
        base.save(job/'request.json',{'context_index':str(index)})
        reader=context.Evidence(index,job/'retrieval.jsonl')
        packet=reader.challenge_batch();events=context.audit(index,reader.log)
        self.assertEqual([e['method'] for e in events],['challenge_batch'])
        identifier='d'*24;(job/'tool-output').mkdir();path=job/'tool-output'/(identifier+'.txt')
        def delivered(text):
            path.write_bytes(text.encode())
            row={'id':identifier,'retrieval_start':0,'retrieval_end':1,'limit':None,
                'delivered_bytes':len(text.encode()),'unsupported':False,'sha256':base.sha(path),
                'original_bytes':len(text.encode()),'complete':True}
            (job/'delivery.jsonl').write_text(json.dumps(row)+'\n')
            return context.delivered_entries(job,context.audit(index,reader.log))
        self.assertEqual(delivered('Loaded, not printed.'),[])
        self.assertEqual(delivered(packet[:100]),[])
        self.assertEqual(delivered(packet),events)
        old=self.assemble('old-challenge',compact=False)
        old_reader=context.Evidence(old,self.root/'old-challenge.jsonl')
        with self.assertRaisesRegex(ValueError,'Compact independent'):old_reader.challenge_batch()
        self.assertNotIn('challenge_status',old_reader.filing_batch())


if __name__=='__main__':unittest.main()
