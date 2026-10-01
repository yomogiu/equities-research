"""Fictitious continuation state; mocked provider, no network or real issuers."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_earnings_compact_evidence import fixture
from research import earnings_compact_evidence as evidence
from research import earnings_experiment as base
from research import earnings_mixed_pipeline as pipeline
from research import earnings_mixed_continuation as continuation


class ContinuationFixture:
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();case,_,_=fixture(self.root)
        self.parent=self.root/'parent';self.parent.mkdir()
        evidence.prepare(case,self.parent/'evidence')
        self.writing=self.root/'writing.txt';self.writing.write_text('Fictitious standard')
        self.protocol={'evidence_manifest':str(self.parent/'evidence/manifest.json'),
                       'writing_standard':str(self.writing),'models':{}}
        base.save(self.parent/'protocol.json',self.protocol)
        b=evidence.load_bundle(self.protocol['evidence_manifest'])
        financial={'rows':[{'label':'Fictional metric '+str(i),'fact_ids':['F002']} for i in range(4)],'context':[],'gaps':[]}
        retrieval={'selected_document_ids':['D001'],'exchange_coverage':[{'exchange_id':e['id'],'question':'Fictional question','answer':'Fictional answer','consequence':'Fictional consequence'} for e in b['transcript_index']['exchanges']],
                   'document_findings':[],'quotes':[{'scope_id':'D001','text':t} for t in ['Fictitious café guidance is provisional.','Repeated phrase. Repeated phrase.','Fictitious supporting row 000.','Fictitious supporting row 001.','Mismatched quote']]}
        report={'title':'Fictional report','opening':'Fictitious revenue.','opening_citations':['F002'],
                'findings':[{'heading':'Fictitious heading','text':'Fictitious finding','citations':['D001'],'quotes':[]} for _ in range(4)],
                'next_tests':[],'scope':'Fictitious scope'}
        review={'verdict':'pass','criteria':{c:{'status':'pass','evidence':'Fictitious evidence'} for c in pipeline.CRITERIA},'findings':[]}
        self.outputs={'financial':financial,'retrieval':retrieval,'analysis':report,'review':review};self.jobs={}
        for role in ('financial','retrieval'):
            path=self.parent/'jobs'/f'{role}-r0';path.mkdir(parents=True)
            base.save(path/'request.json',{'model':pipeline.MODELS[role][0],'effort':pipeline.MODELS[role][1],
                'bindings':{'role':role,'protocol_sha256':base.sha(self.parent/'protocol.json')}})
            self.make_job(path,role)
        self.output=self.root/'continuation'
        for target,value in [('verify_job',lambda p:self.jobs[str(p)]),('run_role',self.call)]:
            patcher=patch.object(continuation,target,side_effect=value);patcher.start();self.addCleanup(patcher.stop)
        patcher=patch.object(pipeline,'verify_protocol',return_value=self.protocol);patcher.start();self.addCleanup(patcher.stop)
        patcher=patch.object(pipeline,'prompt_for',return_value='Fictitious prompt');patcher.start();self.addCleanup(patcher.stop)

    def make_job(self,path,role):
        out={'content':copy.deepcopy(self.outputs[role]),'receipt':{'elapsed_seconds':1.0,'started_at':'2040-01-01T00:00:00+00:00','finished_at':'2040-01-01T00:00:01+00:00'},'output_path':str(path/'output.json')}
        base.save(path/'output.json',{'content':out['content']});self.jobs[str(path)]=out;return out

    def call(self,path,prompt,model,effort,bindings,timeout):
        path.mkdir(parents=True);base.save(path/'request.json',{'bindings':bindings})
        return self.make_job(path,bindings['role'])


class ContinuationTests(ContinuationFixture, unittest.TestCase):
    def test_validated_derivation_and_review_bound_to_exact_report(self):
        result=continuation.run(self.parent,self.output)
        self.assertEqual('accepted',result['status'])
        ledger=base.read(self.output/'candidate-qualification.json')
        self.assertEqual(4,len(ledger['accepted_quote_evidence']))
        self.assertEqual(1,len(ledger['rejected_candidates']))
        self.assertEqual(5,len(self.outputs['retrieval']['quotes']))
        self.assertEqual(result,continuation.verify(self.output))
        (self.output/'review.json').write_text('{}')
        with self.assertRaises(ValueError):continuation.verify(self.output)

    def test_unresolved_writing_stays_draft(self):
        self.outputs['review']['verdict']='revise'
        self.outputs['review']['criteria']['concise_specific_writing']['status']='fail'
        self.outputs['review']['findings']=[{'target':'analysis','passage':'Fictitious heading','reason':'Repetition','required_change':'Delete redundant text','citations':['D001']}]
        result=continuation.run(self.parent,self.output)
        self.assertEqual('draft',result['status'])
        self.assertIn('DRAFT',(self.output/'report.html').read_text())

    def test_tampered_preparation_protocol_rejected(self):
        request=self.parent/'jobs/financial-r0/request.json';j=base.read(request);j['bindings']['protocol_sha256']='wrong';request.write_text(json.dumps(j))
        with self.assertRaisesRegex(ValueError,'Reused preparation identity'):continuation.run(self.parent,self.output)

if __name__=='__main__':unittest.main()
