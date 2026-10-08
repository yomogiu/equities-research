"""Entirely fictitious interrupted-question fixtures; no issuer data."""
import copy
import hashlib
import unittest
from research import earnings_followup_validation as fv
from research import transcript_evidence as te

TEXT=('Q&A\nAnalyst A: Can capacity double next year?\nExecutive A: Good question.\n'
      'Analyst A: Sorry, the year after that.\nExecutive A: Capacity may rise by half.\n'
      'Analyst B: What is the cost?\nExecutive A: Ten fictional units.\n')
SPEAKERS=[{'name':'Analyst A','role':'analyst'},{'name':'Analyst B','role':'analyst'},
          {'name':'Executive A','role':'management'}]


def fixture():
    source={'document_id':'fictional-call','text_sha256':hashlib.sha256(TEXT.encode()).hexdigest(),'speakers':SPEAKERS}
    provisional=te.index_transcript(TEXT,source)
    boundaries={'reviewed':True,'review_id':'synthetic-boundary-review','source_sha256':source['text_sha256'],
                'sections':provisional['sections'],'turns':provisional['turns']}
    index=te.index_transcript(TEXT,source,boundaries);parent,child,other=index['exchanges']
    quote='Capacity may rise by half.';start=TEXT.index(quote)
    finding={'id':'fictional-finding','exchange_ids':[parent['id'],child['id']],
             'answer_classification':'partial','question_assessed':'Can capacity double in the corrected year?',
             'answer_assessed':'The executive gives a lower possible increase.',
             'technical_mechanism':'Additional fictional capacity.','financial_implication':'Output opportunity.',
             'counterevidence':'The estimate remains conditional.','uncertainty':'Deployment timing.',
             'next_test':'Compare installed capacity.','fact_ids':['fake-fact'],
             'quotes':[{'exchange_id':child['id'],'document_id':'fictional-call','start':start,'end':start+len(quote),'text':quote}]}
    policy={'source_sha256':source['text_sha256'],'index_sha256':fv.index_digest(index),
            'allowed_links':[{'parent_exchange_id':parent['id'],'child_exchange_id':child['id']}]}
    return index,[finding],policy


class FollowupValidationTests(unittest.TestCase):
    def test_linked_context_passes_without_input_mutation(self):
        index,findings,policy=fixture();before=copy.deepcopy((index,findings,policy))
        with self.assertRaisesRegex(ValueError,fv.ERROR):te.validate_findings(findings,index,TEXT,['fake-fact'])
        result=fv.inspect_context_links(findings,index,TEXT,['fake-fact'],**policy)
        self.assertEqual(result['status'],'structurally_valid');self.assertEqual(len(result['context_links']),1)
        self.assertEqual(result['semantic_review'],'required_on_full_original_findings')
        self.assertEqual((index,findings,policy),before)
    def test_context_manager_restores_original_after_exception(self):
        index,findings,policy=fixture();original=te.validate_findings
        with self.assertRaisesRegex(RuntimeError,'synthetic'):
            with fv.adapter(**policy):
                self.assertEqual(te.validate_findings(findings,index,TEXT,['fake-fact'])['status'],'structurally_valid')
                raise RuntimeError('synthetic')
        self.assertIs(te.validate_findings,original)
    def test_all_exact_quote_checks_remain(self):
        for damage in ('text','document','span','exchange'):
            index,findings,policy=fixture();q=findings[0]['quotes'][0]
            if damage=='text':q['text']='Capacity will quadruple.'
            elif damage=='document':q['document_id']='another-call'
            elif damage=='span':q['start']=0;q['end']=3;q['text']=TEXT[:3]
            else:q['exchange_id']=index['exchanges'][2]['id']
            with self.subTest(damage=damage),self.assertRaises(ValueError):
                fv.inspect_context_links(findings,index,TEXT,['fake-fact'],**policy)
    def test_fact_and_required_fields_remain_checked(self):
        index,findings,policy=fixture()
        with self.assertRaisesRegex(ValueError,'fact references'):fv.inspect_context_links(findings,index,TEXT,[],**policy)
        findings[0]['technical_mechanism']=''
        with self.assertRaisesRegex(ValueError,'substantive field'):fv.inspect_context_links(findings,index,TEXT,['fake-fact'],**policy)
    def test_wrong_analyst_nonadjacent_and_unrelated_rejected(self):
        for damage in ('analyst','adjacency','link'):
            index,findings,policy=fixture();p,c,o=index['exchanges']
            if damage=='analyst':c['analyst']='Analyst B'
            elif damage=='adjacency':index['exchanges']=[p,o,c]
            else:c['followup_of']=None
            policy['index_sha256']=fv.index_digest(index)
            with self.subTest(damage=damage),self.assertRaisesRegex(ValueError,'direct adjacent same-questioner'):
                fv.inspect_context_links(findings,index,TEXT,['fake-fact'],**policy)
    def test_source_and_frozen_index_identity_required(self):
        index,findings,policy=fixture()
        with self.assertRaisesRegex(ValueError,'source hash'):fv.inspect_context_links(findings,index,TEXT+'changed',['fake-fact'],**policy)
        index['exchanges'][0]['analyst']='Edited'
        with self.assertRaisesRegex(ValueError,'index hash'):fv.inspect_context_links(findings,index,TEXT,['fake-fact'],**policy)
    def test_neutral_questioner_with_unknown_occupation_preserves_context_policy(self):
        index,findings,policy=fixture()
        for exchange in index['exchanges']:
            exchange['questioner']=exchange.pop('analyst')
            exchange['questioner_occupation']='unknown'
        policy['index_sha256']=fv.index_digest(index)
        before=copy.deepcopy(index)
        result=fv.inspect_context_links(findings,index,TEXT,['fake-fact'],**policy)
        self.assertEqual(len(result['context_links']),1)
        self.assertEqual(index,before)
        self.assertEqual(index['exchanges'][0]['questioner_occupation'],'unknown')

    def test_conflicting_questioner_legacy_labels_rejected(self):
        index,findings,policy=fixture();index['exchanges'][0]['questioner']='Different participant'
        policy['index_sha256']=fv.index_digest(index)
        with self.assertRaisesRegex(ValueError,'Conflicting questioner'):
            fv.inspect_context_links(findings,index,TEXT,['fake-fact'],**policy)

    def test_neutral_questioner_still_requires_full_index_review(self):
        index,findings,policy=fixture()
        for e in index['exchanges']:e['questioner']=e.pop('analyst')
        index['boundary_review']='partially_reviewed';index['needs_review']=True
        policy['index_sha256']=fv.index_digest(index)
        with self.assertRaisesRegex(ValueError,'reviewed index'):
            fv.inspect_context_links(findings,index,TEXT,['fake-fact'],**policy)

    def test_unreviewed_index_rejected(self):
        index,findings,policy=fixture();index['needs_review']=True;policy['index_sha256']=fv.index_digest(index)
        with self.assertRaisesRegex(ValueError,'reviewed index'):fv.inspect_context_links(findings,index,TEXT,['fake-fact'],**policy)
    def test_unapproved_parent_rejected(self):
        index,findings,policy=fixture();findings[0]['exchange_ids'].append(index['exchanges'][2]['id'])
        with self.assertRaisesRegex(ValueError,'approved directly quoted'):fv.inspect_context_links(findings,index,TEXT,['fake-fact'],**policy)
    def test_multihop_unquoted_chain_rejected(self):
        index,findings,policy=fixture();p,c,o=index['exchanges'];o['analyst']=p['analyst'];o['followup_of']=c['id']
        quote='Ten fictional units.';start=TEXT.index(quote)
        findings[0]['exchange_ids']=[p['id'],c['id'],o['id']]
        findings[0]['quotes']=[{'exchange_id':o['id'],'start':start,'end':start+len(quote),'text':quote}]
        policy['allowed_links'].append({'parent_exchange_id':c['id'],'child_exchange_id':o['id']});policy['index_sha256']=fv.index_digest(index)
        with self.assertRaisesRegex(ValueError,'approved directly quoted'):fv.inspect_context_links(findings,index,TEXT,['fake-fact'],**policy)
    def test_fully_quoted_original_validation_still_passes(self):
        index,findings,policy=fixture();findings[0]['exchange_ids']=findings[0]['exchange_ids'][1:]
        result=fv.inspect_context_links(findings,index,TEXT,['fake-fact'],**policy)
        self.assertEqual(result['context_links'],[]);self.assertEqual(result['semantic_review'],'required')


if __name__=='__main__':unittest.main()
