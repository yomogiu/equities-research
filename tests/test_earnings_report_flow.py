"""Fictional finite report handoffs. No account, source network or model calls."""
import copy
import unittest
from unittest.mock import patch
from test_earnings_passages import PassageFixture
from research import earnings_experiment as base
from research import earnings_passage_pipeline as pipe
from research import earnings_report_flow as flow


def grounded_coverage(bundle):
    """Fictitious role output explicitly joins source-bound exchange IDs."""
    return [dict(exchange_id=e['exchange_id'], question='Fictional question', answer='Fictional response',
                 consequence='Fictional implication',
                 question_passage_ids=[pid for t in e['turns'] if t['id'] in e['question_turn_ids'] for pid in t['passage_ids']],
                 answer_passage_ids=[pid for t in e['turns'] if t['id'] in e['answer_turn_ids'] for pid in t['passage_ids']],
                 continuation_exchange_ids=[], grounding_status='bound',
                 grounding_notes='Fictitious indexed membership; source semantics still need review.')
            for e in bundle['qa_grounding']['exchanges']]


class FlowTests(PassageFixture,unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.writing=self.root/'writing.txt';self.writing.write_text('Fictional standard')
        self.output=self.root/'run'
        pipe.freeze(self.casepath,self.output,self.writing,deterministic_corrections=True)

    def test_finite_base_resume_one_call_per_turn_and_no_duplicate_jobs(self):
        jobs={};calls=[]
        def worker(path,text,model,effort,bindings,timeout):
            if str(path) in jobs:return jobs[str(path)]
            calls.append(bindings['role'])
            role=bindings['role']
            value={'financial':self.financial,'retrieval':self.retrieval,'analysis':self.report,
                   'review':{'verdict':'pass','criteria':{c:{'status':'pass','evidence':'Fictional check'} for c in pipe.legacy.CRITERIA},'findings':[]}}[role]
            base.save(path/'request.json',{'bindings':bindings,'model':model,'effort':effort});(path/'prompt.txt').write_text(text)
            receipt={'started_at':'2040-01-01T00:00:00+00:00','finished_at':'2040-01-01T00:00:01+00:00','session':{'id':path.name}}
            jobs[str(path)]={'content':copy.deepcopy(value),'receipt':receipt};return jobs[str(path)]
        with patch.object(pipe,'run_role',side_effect=worker),patch.object(pipe,'verify_job',side_effect=lambda p:jobs[str(p)]):
            for number in range(4):
                result=flow.advance(self.output)
                self.assertEqual(len(calls),number+1)
                self.assertEqual(result['status'],'pending')
            self.assertEqual(calls,['financial','retrieval','analysis','review'])
            self.assertEqual(flow.advance(self.output,False)['stage'],'signals')
            self.assertEqual(len(calls),4)

    def test_signals_not_skipped_and_blocked_annotations_do_not_publish(self):
        base.save(self.output/'result.json',{'status':'accepted'})
        edition=self.output.with_name('run-signals');edition.mkdir();base.save(edition/'protocol.json',{})
        with patch.object(pipe,'verify',return_value={'status':'accepted'}),patch.object(flow.signals,'advance',return_value={'status':'blocked'}) as signal:
            result=flow.advance(self.output)
            self.assertEqual(result['status'],'blocked');self.assertNotIn('report',result)
            signal.assert_called_once_with(edition.resolve(),True)

    def test_incomplete_preparation_does_not_launch_corrections(self):
        base.save(self.output/'result.json',{'status':'blocked'});base.save(self.output/'artifacts.json',{});base.save(self.output/'review.json',None)
        with patch.object(pipe,'verify',return_value={'status':'blocked'}),patch.object(flow.corrections,'initialize') as init:
            self.assertEqual(flow.advance(self.output)['status'],'blocked');init.assert_not_called()

    def test_missing_required_stage_flags_refuses_execution(self):
        protocol, bundle, catalog=pipe.load(self.output);protocol['report_signals']=False
        with patch.object(pipe,'load',return_value=(protocol,bundle,catalog)),patch.object(pipe,'run') as run:
            with self.assertRaises(ValueError):flow.advance(self.output)
            run.assert_not_called()

    def test_accepted_correction_defers_signals_to_next_turn(self):
        base.save(self.output/'result.json',{'status':'blocked'})
        continuation=self.output.with_name('run-corrections');continuation.mkdir();base.save(continuation/'protocol.json',{})
        with patch.object(pipe,'verify',return_value={'status':'blocked'}),patch.object(flow.corrections,'verify',return_value={'status':'pending'}),patch.object(flow.corrections,'advance',return_value={'status':'accepted'}),patch.object(flow.signals,'advance') as signal:
            self.assertEqual(flow.advance(self.output)['stage'],'signals');signal.assert_not_called()


class DirectCorrectionFlowTests(unittest.TestCase):
    """Routing tests for source-bound correction editions; no base or model work."""
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.output=Path(self.temp.name).resolve()/'continuation';self.output.mkdir()
        base.save(self.output/'protocol.json',{'version':flow.corrections.VERSION})
        self.protocol={'source_protocol':{'deterministic_corrections':True,'report_signals':True},
                       'prior_rounds':1,'max_rounds':1,'new_experiment':False,'inherited_tokens':125}
        self.load=patch.object(flow.corrections,'load',return_value=(self.protocol,None,None,None)).start()
        self.addCleanup(patch.stopall)
        self.base_load=patch.object(pipe,'load',side_effect=AssertionError('Base pipeline must not reload')).start()
        self.base_run=patch.object(pipe,'run',side_effect=AssertionError('Base stages must not rerun')).start()
        self.base_verify=patch.object(pipe,'verify',side_effect=AssertionError('Direct continuation must use its verifier')).start()
        self.init=patch.object(flow.corrections,'initialize',side_effect=AssertionError('Existing continuation must not reset')).start()

    def test_existing_continuation_advances_only_correction_worker(self):
        original=(self.output/'protocol.json').read_bytes()
        with patch.object(flow.corrections,'verify',return_value={'status':'pending'}), \
             patch.object(flow.corrections,'advance',return_value={'status':'blocked'}) as advance, \
             patch.object(flow.signals,'initialize') as init_signal:
            result=flow.advance(self.output)
        self.assertEqual(result['stage'],'corrections');self.assertEqual(result['status'],'blocked')
        advance.assert_called_once_with(self.output);init_signal.assert_not_called()
        self.assertEqual((self.output/'protocol.json').read_bytes(),original)
        self.base_run.assert_not_called();self.init.assert_not_called()

    def test_new_experiment_or_excess_round_budget_is_refused_before_execution(self):
        for patch_values in ({'new_experiment':True},{'prior_rounds':1,'max_rounds':2}):
            with self.subTest(patch_values=patch_values),patch.dict(self.protocol,patch_values), \
                 patch.object(flow.corrections,'verify') as verify,patch.object(flow.corrections,'advance') as advance:
                with self.assertRaisesRegex(ValueError,'original correction budget'):flow.advance(self.output)
                verify.assert_not_called();advance.assert_not_called()

    def test_missing_required_source_stage_flags_refuses_direct_continuation(self):
        for field in ('deterministic_corrections','report_signals'):
            with self.subTest(field=field),patch.dict(self.protocol['source_protocol'],{field:False}), \
                 patch.object(flow.corrections,'advance') as advance:
                with self.assertRaisesRegex(ValueError,'reviewed signals'):flow.advance(self.output)
                advance.assert_not_called()

    def test_correction_acceptance_defers_signal_worker_then_uses_continuation_seed(self):
        edition=self.output.with_name(self.output.name+'-signals')
        with patch.object(flow.corrections,'verify',side_effect=[{'status':'pending'},{'status':'accepted'}]), \
             patch.object(flow.corrections,'advance',return_value={'status':'accepted'}) as correction, \
             patch.object(flow.signals,'initialize') as initialize, \
             patch.object(flow.signals,'advance',return_value={'status':'pending'}) as signal:
            first=flow.advance(self.output)
            self.assertEqual(first,{'status':'pending','stage':'signals'})
            signal.assert_not_called();initialize.assert_not_called()
            second=flow.advance(self.output)
        self.assertEqual(second['stage'],'signals')
        correction.assert_called_once_with(self.output)
        initialize.assert_called_once_with(self.output,edition)
        signal.assert_called_once_with(edition,True)

    def test_nonexecuting_direct_route_never_starts_workers_or_initializers(self):
        edition=self.output.with_name(self.output.name+'-signals')
        with patch.object(flow.corrections,'verify',side_effect=[{'status':'pending'},{'status':'accepted'},{'status':'accepted'}]), \
             patch.object(flow.corrections,'advance') as correction, \
             patch.object(flow.signals,'initialize') as initialize, \
             patch.object(flow.signals,'advance',return_value={'status':'pending'}) as signal:
            self.assertEqual(flow.advance(self.output,False)['stage'],'corrections')
            self.assertEqual(flow.advance(self.output,False)['stage'],'signals')
            self.assertFalse(edition.exists());signal.assert_not_called()
            edition.mkdir();base.save(edition/'protocol.json',{})
            self.assertEqual(flow.advance(self.output,False)['stage'],'signals')
        correction.assert_not_called();initialize.assert_not_called()
        signal.assert_called_once_with(edition,False)

    def test_report_exposed_only_after_signal_acceptance(self):
        edition=self.output.with_name(self.output.name+'-signals');edition.mkdir()
        base.save(edition/'protocol.json',{});(edition/'report.html').write_text('Fictional reviewed report')
        with patch.object(flow.corrections,'verify',return_value={'status':'accepted'}), \
             patch.object(flow.corrections,'advance') as correction, \
             patch.object(flow.signals,'advance',side_effect=[{'status':'blocked'},{'status':'accepted'}]):
            self.assertNotIn('report',flow.advance(self.output,False))
            result=flow.advance(self.output,False)
        self.assertEqual(result['report'],str(edition/'report.html'))
        self.assertEqual(result['report_sha256'],base.sha(edition/'report.html'))
        correction.assert_not_called()


class PreparedFlowTests(unittest.TestCase):
    """Exercise production preparation, not a prebuilt experiment-case shortcut."""
    def setUp(self):
        import tempfile
        from pathlib import Path
        from test_earnings_compact_evidence import fixture as financial_fixture
        from test_publisher_transcript import fixture as publisher_fixture
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        financial_fixture(self.root)  # Real deterministic parser input, entirely fictional.
        raw, text, _ = publisher_fixture()
        # This end-to-end fixture needs an identified issuer response for every
        # question. Unknown supplier attribution has separate grounding tests.
        from research.source_parse import page
        raw = raw.replace(b'Guest, Fictional Supplier', b'COO, Fictional Widgets')
        text = page(raw, '').text
        (self.root/'call.html').write_bytes(raw)
        (self.root/'call.txt').write_bytes(text.encode())
        self.writing = self.root/'writing.txt'; self.writing.write_text('Fictional concise writing standard')
        def document(name, kind):
            return {'document_id': 'fictional-'+name, 'kind': kind, 'period': 'FY2040-Q1',
                    'completeness': 'full', 'source_url': 'https://example.invalid/'+name,
                    'raw_path': name+'.html', 'text_path': name+'.txt',
                    'raw_sha256': base.sha(self.root/(name+'.html')),
                    'text_sha256': base.sha(self.root/(name+'.txt'))}
        self.packet = {'issuer_id':'fictional:widgets', 'period':'FY2040-Q1',
                       'documents':[document('filing','periodic_filing'),document('call','transcript')]}
        self.original = {str(self.root/d[k+'_path']): d[k+'_sha256']
                         for d in self.packet['documents'] for k in ('raw','text')}
        catalog = {'catalog_id':'fictional-catalog','issuers':{'fictional:widgets':{'issuer':'Fictional Widgets, Inc.'}}}
        # Eligibility/freshness has its own suite. Everything after that gate is real.
        with patch.object(flow, 'validate_packet', return_value=self.packet), \
             patch.object(flow.library, 'catalog', return_value=catalog):
            self.casepath = flow.prepare(self.root, 'fictional-packet', self.root/'prepared',
                                         self.writing, 'Explicit fictional test')
        self.output = self.root/'prepared-run'
        pipe.freeze(self.casepath, self.output, self.writing, deterministic_corrections=True, signals=True)
        self.protocol, self.bundle, self.catalog = pipe.load(self.output)
        fid = self.bundle['financial']['observations'][0]['id']
        did = self.bundle['documents']['chunks'][0]['id']
        ids = [p['passage_id'] for p in self.catalog['passages'] if p['text'].strip()][:4]
        self.financial = {'rows':[{'label':'Fictional revenue','fact_ids':[fid]} for _ in range(4)],
                          'context':[], 'gaps':[]}
        self.retrieval = {'selected_document_ids':[did], 'exchange_coverage':[
            {'exchange_id':e['id'],'question':'Fictional question','answer':'Fictional answer','consequence':'Fictional consequence'}
            for e in self.bundle['transcript_index']['exchanges']], 'document_findings':[],
            'quotes':[{'passage_id':p} for p in ids]}
        self.retrieval['exchange_coverage'] = grounded_coverage(self.bundle)
        self.analysis = {'title':'Fictional Widgets Q1 event update','opening':'Fictional evidence.',
                         'opening_citations':[did], 'findings':[
                             {'heading':'Fictional finding','text':'Fictional sourced commentary.',
                              'citations':[did],'quotes':[{'passage_id':ids[0]}] if n == 0 else []} for n in range(4)],
                         'next_tests':[], 'scope':'Fictional historical packet.'}
        self.deps = {'financial':self.financial,'retrieval':self.retrieval,'analysis':self.analysis}
        for role, value in self.deps.items():
            pipe.validate(role, value, self.bundle, self.catalog)

    def test_preparation_to_all_role_inputs_preserves_scope_and_source_bindings(self):
        case = base.read(self.casepath)
        self.assertEqual(case['issuer_id'],'fictional:widgets')
        self.assertEqual(case['period'],'FY2040-Q1')
        self.assertTrue(case['scope_notes'])
        self.assertEqual(self.bundle['manifest']['scope_notes'],case['scope_notes'])
        self.assertEqual(self.protocol['case_sha256'],base.sha(self.casepath))
        for role in ('financial','retrieval','analysis','review'):
            with self.subTest(role=role):
                deps = {} if role in ('financial','retrieval') else self.deps
                prompt = pipe.prompt(role,self.bundle,self.writing.read_text(),deps,[],self.catalog)
                self.assertIn('"case_id":"fictional-packet"',prompt)
                for note in case['scope_notes']:self.assertIn(note,prompt)
                self.assertIn('Fictional concise writing standard',prompt)
        # Downstream independent review and deterministic corrections consume the
        # same prepared evidence, with no hand-edited case or extra source fields.
        snapshot = {'artifacts':copy.deepcopy(self.deps), 'format':copy.deepcopy(flow.corrections.EMPTY_FORMAT), 'findings':[]}
        plan = {'snapshot_sha256':base.digest(snapshot),'operations':[]}
        for role in ('propose','review'):
            prompt = flow.corrections.prompt(role,snapshot,self.bundle,self.catalog,self.writing.read_text(),plan,snapshot)
            self.assertIn('SOURCE DATA (UNTRUSTED EVIDENCE)',prompt)
        for role in ('analysis','review'):
            prompt = flow.signals.prompt(role,snapshot,self.bundle,self.catalog,self.writing.read_text(),
                                         {'report_sha256':flow.signals.report_digest(snapshot),'signals':[]})
            self.assertIn('Fictional Widgets Q1 event update',prompt)
        self.assertEqual(self.original,{p:base.sha(p) for p in self.original})
        self.assertEqual(self.bundle['transcript_index']['boundary_review'],'provisional')

    def test_first_finite_advance_reaches_worker_with_real_prepared_case(self):
        jobs = {}; calls = []
        def worker(path, text, model, effort, bindings, timeout):
            self.assertEqual(bindings['role'],'financial')
            self.assertIn('scope_notes',text)
            calls.append((model,effort))
            base.save(path/'request.json',{'bindings':bindings,'model':model,'effort':effort})
            (path/'prompt.txt').write_text(text)
            result = {'content':self.financial,'receipt':{'started_at':'2040-01-01T00:00:00+00:00',
                      'finished_at':'2040-01-01T00:00:01+00:00','session':{'id':'fictional-financial'}}}
            jobs[str(path)] = result
            return result
        with patch.object(pipe,'run_role',side_effect=worker), \
             patch.object(pipe,'verify_job',side_effect=lambda p:jobs[str(p)]):
            result = flow.advance(self.output)
        self.assertEqual(result['status'],'pending')
        self.assertEqual(calls,[('gpt-5.6-luna','xhigh')])
        self.assertEqual(self.original,{p:base.sha(p) for p in self.original})


class PreparedSidecarTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from test_earnings_compact_evidence import fixture as financial_fixture
        from test_reviewed_transcript_index import fixture, encoded
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();financial_fixture(self.root)
        text,raw,source,proposal,review,self.selection=fixture(True)
        (self.root/'call.html').write_bytes(raw);(self.root/'call.txt').write_bytes(text.encode())
        self.selection['proposal_path']='mapping.json';self.selection['review_path']='review.json'
        (self.root/'mapping.json').write_bytes(encoded(proposal));(self.root/'review.json').write_bytes(encoded(review))
        self.writing=self.root/'writing.txt';self.writing.write_text('Fictional concise writing standard')
        def document(name,kind):
            return {'document_id':source['document_id'] if kind=='transcript' else 'fake-filing',
                    'catalog_document_id':source['document_id'] if kind=='transcript' else 'catalog-filing',
                    'kind':kind,'period':'FY2040-Q1','completeness':'full',
                    'source_url':'https://example.invalid/'+name,'raw_path':name+'.html','text_path':name+'.txt',
                    'raw_sha256':base.sha(self.root/(name+'.html')),'text_sha256':base.sha(self.root/(name+'.txt'))}
        self.packet={'issuer_id':source['issuer_id'],'period':'FY2040-Q1',
                     'documents':[document('filing','periodic_filing'),document('call','transcript')]}
        self.catalog={'catalog_id':'fake-catalog','issuers':{source['issuer_id']:{'issuer':'Fictional Widgets'}}}

    def prepare(self, selection):
        with patch.object(flow,'validate_packet',return_value=self.packet),patch.object(flow.library,'catalog',return_value=self.catalog):
            return flow.prepare(self.root,'fake-packet',self.root/'prepared',self.writing,'Explicit fictional request',reviewed_sidecar=selection)

    def test_sidecar_inputs_freeze_with_original_receipts_and_neutral_questioner(self):
        path=self.prepare(self.selection);case=base.read(path)
        bound={x['path']:x['sha256'] for x in case['artifacts']}
        self.assertEqual(bound[str(self.root/'mapping.json')],self.selection['proposal_sha256'])
        self.assertEqual(bound[str(self.root/'review.json')],self.selection['review_sha256'])
        self.assertEqual(base.read(case['transcript_sidecar_selection_path']),self.selection)
        self.assertIn(case['transcript_sidecar_selection_path'],bound)
        index=base.read(case['transcript_index_path'])
        self.assertEqual(index['exchanges'][0]['questioner_occupation'],'unknown')
        self.assertTrue(index['needs_review'])
        pipe.freeze(path,self.root/'frozen',self.writing,deterministic_corrections=True,signals=True)
        protocol,bundle,catalog=pipe.load(self.root/'frozen')
        self.assertEqual(bundle['transcript_index']['reviewed_sidecar']['review']['sha256'],self.selection['review_sha256'])
        (self.root/'mapping.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'Frozen input changed'):base.validate_case(case)

    def test_distinct_packet_and_catalog_ids_prepare_freeze_and_build_role_inputs(self):
        call=self.packet['documents'][1]
        call['document_id']='qualified-packet-call-id'
        path=self.prepare(self.selection);case=base.read(path)
        index=base.read(case['transcript_index_path'])
        self.assertEqual(index['source']['document_id'],call['catalog_document_id'])
        transcript_sources=[x for x in case['sources'] if x['kind']=='transcript']
        self.assertEqual(len(transcript_sources),2)
        for source in transcript_sources:
            self.assertEqual(source['document_id'],call['catalog_document_id'])
            self.assertEqual(source['packet_document_id'],call['document_id'])
            self.assertEqual(source['catalog_document_id'],call['catalog_document_id'])
        pipe.freeze(path,self.root/'frozen',self.writing,deterministic_corrections=True,signals=True)
        _,bundle,catalog=pipe.load(self.root/'frozen')
        fid=bundle['financial']['observations'][0]['id']
        did=bundle['documents']['chunks'][0]['id']
        quote_ids=[p['passage_id'] for p in catalog['passages'] if p['text'].strip()][:4]
        deps={'financial':{'rows':[{'label':'Fictional revenue','fact_ids':[fid]}],'context':[],'gaps':[]},
              'retrieval':{'selected_document_ids':[did],'exchange_coverage':grounded_coverage(bundle),'document_findings':[],'quotes':[{'passage_id':x} for x in quote_ids]},
              'analysis':{'title':'Fictional report','opening':'Fictional source-backed overview.',
                          'opening_citations':[did],'findings':[],'next_tests':[],'scope':'Fictional scope'}}
        for role in ('financial','retrieval'):
            prompt=pipe.prompt(role,bundle,self.writing.read_text(),deps,[],catalog)
            self.assertIn('fake-packet',prompt)
        # The source-reviewed moderator role preserves occupation uncertainty,
        # but its unassigned turn (including a title line) has no mechanical
        # courtesy/routing exemption. Identity correctness cannot waive this gap.
        for role in ('analysis','review'):
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, 'Substantive unassigned Q&A turns'):
                pipe.prompt(role,bundle,self.writing.read_text(),deps,[],catalog)
        self.assertEqual(self.packet['documents'][1]['document_id'],'qualified-packet-call-id')

    def test_sidecar_requires_explicit_catalog_identity_and_rejects_wrong_identity(self):
        call=self.packet['documents'][1];call.pop('catalog_document_id')
        with self.assertRaisesRegex(ValueError,'catalog document identity'):self.prepare(self.selection)
        call['catalog_document_id']='another-catalog-document'
        with self.assertRaisesRegex(ValueError,'source identity mismatch'):self.prepare(self.selection)
        self.assertFalse((self.root/'prepared').exists())

    def test_mismatched_sidecar_fails_before_output(self):
        selection=copy.deepcopy(self.selection);selection['text_sha256']='wrong'
        with self.assertRaisesRegex(ValueError,'source hash'):self.prepare(selection)
        self.assertFalse((self.root/'prepared').exists())

    def test_unresolved_mapping_blocks_preparation(self):
        self.catalog['issuers']['fake-issuer']['issuer']='Different Fictional Issuer'
        with self.assertRaisesRegex(ValueError,'mapping remains unresolved'):self.prepare(self.selection)
        self.assertFalse((self.root/'prepared').exists())

    def test_existing_source_gate_runs_before_sidecar(self):
        with patch.object(flow,'validate_packet',side_effect=ValueError('Source freshness fails')),patch.object(flow.reviewed_index,'apply_reviewed_sidecar') as apply:
            with self.assertRaisesRegex(ValueError,'Source freshness fails'):
                flow.prepare(self.root,'fake',self.root/'prepared',self.writing,'Explicit',reviewed_sidecar=self.selection)
            apply.assert_not_called()

    def test_no_auto_discovery_and_standard_no_sidecar_path_preserved(self):
        # Valid sidecars on disk do not add annotations without explicit selection.
        with self.assertRaisesRegex(ValueError,'Q&A boundaries need review'):self.prepare(None)
        self.assertFalse((self.root/'prepared').exists())
