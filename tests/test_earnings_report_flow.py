"""Fictional finite report handoffs. No account, source network or model calls."""
import copy
import unittest
from unittest.mock import patch
from test_earnings_passages import PassageFixture
from research import earnings_experiment as base
from research import earnings_passage_pipeline as pipe
from research import earnings_report_flow as flow


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
