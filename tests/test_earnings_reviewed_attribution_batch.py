"""Fictional complete-turn review binding; no provider calls."""
import copy
import unittest
from unittest.mock import patch
from research import earnings_reviewed_attribution_batch as m

class AttributionBatchTests(unittest.TestCase):
    def fixture(self):
        bundle={'transcript_index':{'exchanges':[{'id':'e','turn_ids':['t']}],
            'turns':[{'id':'t','role':'management'}]}}
        catalog={'passages':[{'passage_id':'P1','scope_id':'t','start':0,'text':'Fictional closing.'}]}
        reservation={'bindings':{'index_sha256':m.r.digest(bundle['transcript_index']),
            'catalog_sha256':'hash','retrieval_sha256':'hash','exchange_ids':['e']},
            'prompt_sha256':'hash','prior_session':'author'}
        decision={'exchange_id':'e','disposition':'boundary_repair_required',
            'question_turn_ids':[],'answer_turn_ids':[],'reason':'Fictional closing boundary',
            'turns':[{'turn_id':'t','classification':'management_closing','passage_ids':['P1'],'reason':'Fictional business closing'}]}
        content={'exchanges':[decision]}
        binding={'reservation':'reservation','reservation_sha256':'hash','review':{'job':'job'},
                 'catalog_path':'catalog','retrieval_output':'retrieval'}
        request={'bindings':reservation['bindings'],'model':'gpt-6.1-sol','effort':'medium'}
        grounding={'exchanges':[{'exchange_id':'e','turns':[{'id':'t'}], 'question_turn_ids':['t'],'answer_turn_ids':['t']}]}
        return binding,grounding,bundle,catalog,reservation,request,content

    def run_fixture(self,mutate=None):
        binding,grounding,bundle,catalog,reservation,request,content=self.fixture()
        if mutate:mutate(content)
        def read(path):
            return reservation if str(path)=='reservation' else catalog if str(path)=='catalog' else request
        with patch.object(m.r,'read',side_effect=read),patch.object(m.r,'sha',return_value='hash'),patch.object(m.imp,'authenticate',return_value={'content':content,'session':{'id':'reviewer'}}),patch('research.earnings_qa_grounding._complete',return_value=True):
            return m.apply(binding,grounding,bundle,catalog),grounding,bundle

    def test_closing_is_preserved_and_never_marked_courtesy(self):
        (out,_),original,bundle=self.run_fixture()
        row=out['exchanges'][0]
        self.assertEqual(row['mechanical_disposition'],'reviewed_non_qa')
        self.assertEqual(row['reviewed_turn_dispositions'][0]['classification'],'management_closing')
        self.assertEqual(row['answer_turn_ids'],[])
        self.assertEqual(out['exchanges'][0]['turns'],original['exchanges'][0]['turns'])
        self.assertEqual(bundle['transcript_index']['exchanges'][0]['turn_ids'],['t'])

    def test_incomplete_or_invented_evidence_fails(self):
        for ids in ([],['invented']):
            with self.subTest(ids=ids),self.assertRaises(ValueError):
                self.run_fixture(lambda c:c['exchanges'][0]['turns'][0].update(passage_ids=ids))

    def test_substantive_and_uncertain_are_not_normalized(self):
        for classification in ('uncertain','substantive_answer'):
            with self.subTest(classification=classification),self.assertRaises(ValueError):
                self.run_fixture(lambda c:c['exchanges'][0]['turns'][0].update(classification=classification))

    def test_duplicate_decisions_and_closing_suppression_fail(self):
        with self.assertRaises(ValueError):self.run_fixture(lambda c:c['exchanges'].append(copy.deepcopy(c['exchanges'][0])))
        with self.assertRaises(ValueError):self.run_fixture(lambda c:c['exchanges'][0].update(disposition='courtesy_and_routing_only'))

class ContinuedAnswerTests(unittest.TestCase):
 def fixture(self):
  turns=[{'id':'parent-q','role':'analyst','speaker':'Fictional Analyst','start':0,'end':10}, {'id':'thanks','role':'analyst','speaker':'Fictional Analyst','start':11,'end':20}, {'id':'answer','role':'management','speaker':'Fictional CEO','start':21,'end':40}]
  bundle={'transcript_index':{'turns':turns,'exchanges':[{'id':'parent','turn_ids':['parent-q'],'question_turn_ids':['parent-q'],'answer_turn_ids':[]},{'id':'continued','turn_ids':['thanks','answer'],'question_turn_ids':['thanks'],'answer_turn_ids':['answer'],'followup_of':'parent'}]}}
  catalog={'passages':[{'passage_id':t['id'],'scope_id':t['id'],'start':t['start'],'text':'Fictional'} for t in turns]}
  decision={'exchange_id':'continued','disposition':'answer_continuation','continued_from':'parent','question_turn_ids':[],'answer_turn_ids':['answer'],'reason':'Continues original answer after thanks','turns':[{'turn_id':'thanks','classification':'courtesy','passage_ids':['thanks'],'reason':'Thanks only'},{'turn_id':'answer','classification':'management_answer_continuation','passage_ids':['answer'],'reason':'Completes prior answer'}]}
  g={'version':'source-bound-qa-membership-v9','exchanges':[{'exchange_id':'continued','flags':['courtesy_only_question_turn'],'question_turn_ids':['thanks'],'answer_turn_ids':['answer'],'turns':[]}]}
  reservation={'bindings':{'scope':'complete-source-disposition-v2','index_sha256':m.r.digest(bundle['transcript_index']),'catalog_sha256':'hash','retrieval_sha256':'hash','exchange_ids':['continued']},'prompt_sha256':'hash','prior_session':'author'}
  binding={'reservation':'reservation','reservation_sha256':'hash','review':{'job':'job'},'catalog_path':'catalog','retrieval_output':'retrieval'}
  return bundle,catalog,decision,g,reservation,binding
 def call(self,change=None):
  bundle,catalog,d,g,res,bind=self.fixture()
  if change:change(bundle,d,res)
  res['bindings']['index_sha256']=m.r.digest(bundle['transcript_index'])
  def read(path):return res if str(path)=='reservation' else catalog if str(path)=='catalog' else {'bindings':res['bindings'],'model':'gpt-6.1-sol','effort':'medium'}
  with patch.object(m.r,'read',side_effect=read),patch.object(m.r,'sha',return_value='hash'),patch.object(m.imp,'authenticate',return_value={'content':{'exchanges':[d]},'session':{'id':'reviewer'}}),patch('research.earnings_qa_grounding._complete',return_value=True),patch('research.earnings_qa_grounding._greeting',return_value=True):
   return m.apply(bind,g,bundle,catalog)[0]
 def test_keeps_answer_and_explicit_parent_without_inventing_question(self):
  result=self.call()['exchanges'][0]
  self.assertEqual(result['mechanical_disposition'],'reviewed_answer_continuation')
  self.assertEqual(result['answer_turn_ids'],['answer']);self.assertEqual(result['question_turn_ids'],[])
  self.assertEqual(result['reviewed_continued_from'],'parent')
 def test_old_contract_wrong_parent_analyst_and_answer_rejected(self):
  changes=[lambda b,d,r:r['bindings'].update(scope='old'),lambda b,d,r:d.update(continued_from='invented'),lambda b,d,r:d.update(answer_turn_ids=[]),lambda b,d,r:b['transcript_index']['turns'][0].update(speaker='Different Analyst')]
  for change in changes:
   with self.assertRaises(ValueError):self.call(change)
