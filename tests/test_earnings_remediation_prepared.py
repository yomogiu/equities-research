"""Fictional authenticated prepared seed export; no model calls."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_remediation as m
from research import earnings_passage_pipeline as pipe
from research import earnings_experiment as base
from research import earnings_prepared_recovery as prepared


class PreparedRemediationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.protocol={'version':pipe.EFFICIENT_VERSION,'prepared_recovery':{'prior_rounds':2},'max_correction_rounds':2}
        (self.root/'protocol.json').write_text(json.dumps(self.protocol))
        self.artifacts={'financial':{},'retrieval':{},'analysis':{'opening':'Fictional final candidate'}}
        self.review={'verdict':'revise','findings':[{'target':'analysis','reason':'Fictional omission'}]}
        self.result={'status':'blocked','correction_rounds':2,'total_tokens':12345,'jobs':[{'role':'analysis','round':2},{'role':'review','round':2}]}
        self.inputs={'dependencies':self.artifacts}

    def export(self):
        values={'artifacts.json':self.artifacts,'review.json':self.review,'review-r2.json':self.inputs}
        out=io.StringIO()
        with patch.object(pipe,'verify',return_value=self.result) as verify, patch.object(base,'read',side_effect=lambda p:values[Path(p).name]), patch.object(pipe,'efficient_dependencies',side_effect=lambda r,a:a), patch('sys.argv',['export',str(self.root)]), contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as exit:
                exec(m.EXPORT,{})
            self.assertEqual(exit.exception.code,0);verify.assert_called_once_with(self.root)
        return json.loads(out.getvalue())

    def test_export_preserves_exhausted_rounds_usage_and_source_protocol(self):
        out=self.export()
        self.assertEqual(out['prior_rounds'],2);self.assertEqual(out['prior_tokens'],12345)
        self.assertEqual(out['source_protocol'],self.protocol)
        self.assertEqual(out['snapshot']['artifacts'],self.artifacts)
        self.assertEqual(out['snapshot']['findings'][0]['finding'],self.review['findings'][0])

    def test_no_export_of_running_accepted_unreviewed_or_different_candidate(self):
        for change in ['running','accepted','round','review_missing','analysis_missing','old_candidate','pass']:
            with self.subTest(change=change):
                saved=copy.deepcopy((self.result,self.artifacts,self.inputs,self.review))
                if change in ('running','accepted'):self.result['status']=change
                elif change=='round':self.result['correction_rounds']=1
                elif change=='review_missing':self.result['jobs']=self.result['jobs'][:1]
                elif change=='analysis_missing':self.artifacts.pop('analysis')
                elif change=='old_candidate':self.inputs={'dependencies':{'analysis':'older'}}
                elif change=='pass':self.review['verdict']='pass'
                with self.assertRaises(ValueError):self.export()
                self.result,self.artifacts,self.inputs,self.review=saved

    def test_reviewed_overlay_replayed_on_bundle_load(self):
        source={'evidence_manifest':'fictional','prepared_recovery':{'binding':'fictional'}}
        original={'manifest':{},'qa_grounding':{'identity':'unknown'}};derived={'qa_grounding':{'identity':'unknown','function':'reviewed_questioner'}}
        with patch.object(m.evidence,'load_bundle',return_value=original),patch.object(m.passages,'catalog',return_value={}),patch.object(m.corrections.qa_grounding,'attach') as attach,patch.object(prepared,'apply',return_value=(derived,{},5,set())) as apply:
            actual,catalog=m._source_bundle(source)
        self.assertEqual(actual,derived);attach.assert_called_once_with(None,source,original,{})
        apply.assert_called_once_with(source,original,{})

    def test_existing_correction_bundle_without_overlay_unchanged(self):
        original={'manifest':{}}
        with patch.object(m.evidence,'load_bundle',return_value=original),patch.object(m.passages,'catalog',return_value={}),patch.object(m.corrections.qa_grounding,'attach'),patch.object(prepared,'apply') as apply:
            actual,_=m._source_bundle({'evidence_manifest':'fictional'})
        self.assertIs(actual,original);apply.assert_not_called()

    def test_seed_bindings_include_authenticated_prepared_ancestry(self):
        ancestor=self.root/'ancestor';ancestor.mkdir()
        receipt=ancestor/'execution.json';receipt.write_text(json.dumps({'session':{'id':'fictional-preparer'}}))
        seed=self.root/'edition';seed.mkdir()
        current=seed/'execution.json';current.write_text(json.dumps({'session':{'id':'fictional-reviewer'}}))
        old={'prepared_recovery':{'bindings':{str(receipt):base.sha(receipt)}}}
        bindings,sessions=m.seed_bindings(seed,old)
        self.assertEqual(bindings[str(receipt)],base.sha(receipt))
        self.assertEqual(sessions,['fictional-preparer','fictional-reviewer'])
        receipt.write_text('{}')
        with self.assertRaisesRegex(ValueError,'ancestry source changed'):
            m.seed_bindings(seed,old)

    def test_conflicting_ancestry_bindings_rejected(self):
        receipt=self.root/'execution.json';receipt.write_text('{}')
        old={'source_bindings':{str(receipt):'0'*64},
             'prepared_recovery':{'bindings':{str(receipt):base.sha(receipt)}}}
        with self.assertRaisesRegex(ValueError,'Conflicting inherited'):
            m.seed_bindings(self.root,old)
