"""Mandatory guide enforcement on fictional prose; no provider calls."""
import copy
import unittest
from unittest.mock import patch
import test_earnings_batch_review as fixtures
from test_earnings_passages import PassageFixture
from research import earnings_batch_review as b
from research import earnings_batched_flow as flow

class EditorialTests(PassageFixture,unittest.TestCase):
    state=fixtures.BatchTests.state
    pack=fixtures.BatchTests.pack
    items=fixtures.BatchTests.items
    decision=fixtures.BatchTests.decision
    def review(self):
        items=self.items()
        review=self.decision(items,items)
        for d in review['decisions']:d['editorial_repairs']=[];d['review_kind']='none'
        d=next(d for d in review['decisions'] if d['unit_id']=='analysis:opening')
        text=items[d['unit_id']]['value']['opening']
        d.update(verdict='revise',review_kind='editorial',reason='Cut repetitive introductory prose.',passage_ids=[],editorial_repairs=[{
            'field_path':['opening'],'before':text,'after':'Fictional revenue increased.','reason':'Every sentence must add a distinct finding.'}])
        return items,review,d
    def test_initializer_binds_new_policy_and_old_policy_stays_supported(self):
        writing=self.root/'writing.txt';writing.write_text('Fictional mandatory guide')
        protocol={'writing_standard':str(writing),'writing_sha256':b.runner.sha(writing),'batch_review':b.EDITORIAL_VERSION}
        state=self.state();pack=self.pack(state)
        with patch.object(b.remediation,'_source_bundle',return_value=(self.bundle,self.catalog)):
            b.initialize(protocol,state,pack,self.root/'editorial','Fictional explicit authorization')
            frozen=b.runner.read(self.root/'editorial/protocol.json')
            self.assertEqual(frozen['version'],b.EDITORIAL_VERSION)
            b.load(self.root/'editorial')
        self.assertEqual(b.MAX_CORRECTIONS,2)
    def test_same_review_requires_guide_and_exact_repairs(self):
        items,review,d=self.review()
        text=b.prompt(items,items,set(items),{}, {},self.catalog,'Fictional mandatory guide',0,self.bundle,b.EDITORIAL_VERSION)
        self.assertIn('Fictional mandatory guide',text)
        self.assertIn('mandatory editorial acceptance',text)
        self.assertIn('editorial_repairs',text)
        self.assertNotIn('Optional wording preferences are nonblocking',text)
        old=b.prompt(items,items,set(items),{}, {},self.catalog,'Writing',0,self.bundle,b.MECHANICAL_VERSION)
        self.assertNotIn('editorial_repairs',old)
        self.assertIn('Optional wording preferences are nonblocking',old)
    def test_exact_editorial_only_cut_keeps_unaffected_acceptance(self):
        items,review,d=self.review();before=copy.deepcopy(items)
        accepted,findings=b.adjudicate(items,set(items),{},review,self.catalog,'review',b.EDITORIAL_VERSION)
        self.assertIn('EDITORIAL REPAIRS',findings['analysis:opening'])
        self.assertIn('financial',accepted)
        self.assertEqual(items,before)
        result={'round':1,'items':items,'findings':findings,'accepted':accepted}
        self.assertIn('exact editorial cuts',flow.proposal_prompt(result,self.bundle,self.catalog,'Writing',b.EDITORIAL_VERSION))
    def test_pass_cannot_list_unresolved_edits(self):
        items,review,d=self.review();d['verdict']='pass';d['review_kind']='none'
        with self.assertRaises(ValueError):b.adjudicate(items,set(items),{},review,self.catalog,'x',b.EDITORIAL_VERSION)
    def test_vague_or_stale_edits_and_binding_changes_rejected(self):
        for change in ({'before':'invented text'},{'after':None},{'field_path':['opening_citations',0]}):
            items,review,d=self.review();d['editorial_repairs'][0].update(change)
            with self.assertRaises(ValueError):b.adjudicate(items,set(items),{},review,self.catalog,'x',b.EDITORIAL_VERSION)
    def test_factual_revise_still_requires_evidence(self):
        items,review,d=self.review();d['editorial_repairs']=[];d['review_kind']='factual'
        with self.assertRaisesRegex(ValueError,'Exact original evidence'):b.adjudicate(items,set(items),{},review,self.catalog,'x',b.EDITORIAL_VERSION)
    def test_mixed_findings_require_source_evidence(self):
        items,review,d=self.review();d['review_kind']='mixed'
        with self.assertRaisesRegex(ValueError,'Exact original evidence'):b.adjudicate(items,set(items),{},review,self.catalog,'x',b.EDITORIAL_VERSION)
    def test_old_policy_cannot_silently_accept_new_review(self):
        items,review,d=self.review()
        with self.assertRaisesRegex(ValueError,'Malformed'):b.adjudicate(items,set(items),{},review,self.catalog,'x',b.MECHANICAL_VERSION)
    def test_no_editorial_reopen_of_unchanged_accepted_units(self):
        items,review,d=self.review();review['decisions']=[x for x in review['decisions'] if x['unit_id']!='analysis:opening']
        repair={k:d[k] for k in ('unit_id','reason','passage_ids','editorial_repairs','review_kind')}
        review['reopen']=[repair]
        with self.assertRaisesRegex(ValueError,'not unchanged accepted'):b.adjudicate(items,set(items)-{'analysis:opening'},{'analysis:opening':{'original':'receipt'}},review,self.catalog,'x',b.EDITORIAL_VERSION)

if __name__=='__main__':unittest.main()
