"""Fictitious independently reviewed attribution overlay regressions."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from test_earnings_qa_header_repair import fixture
from research import earnings_attribution_overlay as overlay, earnings_experiment as base


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.bundle,self.catalog=fixture();text=''.join(p['text'] for p in self.catalog['passages']);self.source=self.root/'fake.txt';self.source.write_text(text)
        sha=base.sha(self.source);self.bundle['transcript_index']['source']['text_sha256']=sha
        for p in self.catalog['passages']:p['sha256']=sha
        self.proposal=self.root/'proposal.json';self.review=self.root/'review.json'
        self.proposal.write_text(json.dumps({'rows':[{'exchange_id':'E1','proposed_reviewed_turn_changes':{}}]}))
        spans=[dict(turn_id=t['id'],start=t['start'],end=t['end'],text=text[t['start']:t['end']],span_sha256=hashlib.sha256(text[t['start']:t['end']].encode()).hexdigest())for t in self.bundle['transcript_index']['turns'][:3]]
        self.decision={'exchange_id':'E1','decision':'pass','source_spans':spans,'proposed_reviewed_turn_changes':{},'approved_disposition':overlay.DISPOSITION}
        self.value={'decision':'pass_for_new_attribution_sidecar','reviewer':'Independent fictitious reviewer','proposal':{'path':str(self.proposal),'sha256':base.sha(self.proposal)},'source':{'path':str(self.source),'sha256':sha,'document_id':'fake-source'},'decisions':[self.decision]}
    def run_overlay(self):
        self.review.write_text(json.dumps(self.value))
        return overlay.apply(self.bundle,self.catalog,self.proposal,self.review)
    def test_source_and_original_index_preserved(self):
        original=copy.deepcopy(self.bundle);derived,receipt=self.run_overlay()
        self.assertEqual(original,self.bundle)
        self.assertEqual(derived['qa_grounding']['exchanges'][0]['reviewed_disposition'],overlay.DISPOSITION)
        self.assertEqual(receipt['original_index_sha256'],base.digest(original['transcript_index']))
    def test_unreviewed_or_partial_spans_rejected(self):
        self.decision['source_spans'].pop()
        with self.assertRaisesRegex(ValueError,'every original member'):self.run_overlay()
    def test_tampered_text_rejected(self):
        self.decision['source_spans'][0]['text']='Invented'
        with self.assertRaisesRegex(ValueError,'span mismatch'):self.run_overlay()
    def test_changed_source_rejected(self):
        self.source.write_text('Changed')
        with self.assertRaisesRegex(ValueError,'source changed'):self.run_overlay()
