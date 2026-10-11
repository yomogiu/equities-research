import unittest
from research import earnings_qa_grounding as q
class CompleteCourtesy(unittest.TestCase):
 def turn(self,text,role='management'):
  return {'id':'fake','speaker':'Fictional','role':role,'start':0,'end':len(text)},[{'start':0,'end':len(text),'text':text}]
 def test_exact_thanks_and_frozen_version(self):
  t,r=self.turn('Thank you. Thanks for the questions.')
  self.assertTrue(q._greeting(t,r,q.COURTESY_ROUTING_VERSION))
  self.assertFalse(q._greeting(t,r,q.NAMED_GREETING_VERSION))
  t,r=self.turn('Thank you. Thanks for the questions. Revenue rose.')
  self.assertFalse(q._greeting(t,r,q.COURTESY_ROUTING_VERSION))
 def test_acknowledgment_retains_any_substantive_suffix(self):
  for text in ['Got it. That makes a lot of sense. Thank you.','Perfect. Thank you.']:
   t,r=self.turn(text);self.assertTrue(q._greeting(t,r,q.COURTESY_ROUTING_VERSION))
   t,r=self.turn(text+' Demand rose.');self.assertFalse(q._greeting(t,r,q.COURTESY_ROUTING_VERSION))
 def test_routing_binds_target_and_complete_turn(self):
  t,r=self.turn('The next question comes from Alex Doe with Fictional Bank. Please go ahead.','operator')
  self.assertTrue(q._routing(t,r,[('Alex Doe','Fictional Bank')],q.COURTESY_ROUTING_VERSION))
  self.assertFalse(q._routing(t,r,[('Alex Doe','Fictional Bank')],q.NAMED_GREETING_VERSION))
  self.assertFalse(q._routing(t,r,[('Someone Else','Fictional Bank')],q.COURTESY_ROUTING_VERSION))
  t['end']+=1
  self.assertFalse(q._routing(t,r,[('Alex Doe','Fictional Bank')],q.COURTESY_ROUTING_VERSION))
