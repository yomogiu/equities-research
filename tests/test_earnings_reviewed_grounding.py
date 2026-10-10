import copy
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from research import earnings_reviewed_grounding as g
from research import earnings_mixed_runner as r

class ReviewedGroundingTests(TestCase):
 def test_replay_retains_closing_and_rejects_unapproved_edits(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'text';source.write_text('Question?Answer.Closing outlook.')
   turns=[dict(id=str(i),start=a,end=b,role=role) for i,(a,b,role) in enumerate([(0,9,'analyst'),(9,16,'management'),(16,32,'management')])]
   # Use exact actual text length for final scope.
   turns[-1]['end']=len(source.read_text())
   e=dict(id='E',turn_ids=['0','1','2'],question_turn_ids=['0'],answer_turn_ids=['1','2'])
   bundle={'transcript_index':{'source':{'document_id':'fake','text_sha256':r.sha(source)},'turns':turns,'exchanges':[e]}}
   row={'exchange_id':'E','grounding_status':'unresolved','answer':'Answer.'};out={'exchange_coverage':[row]}
   proposal={'source':{'path':str(source),'sha256':r.sha(source),'document_id':'fake'},'exchange':e,'turns':[{**t,'text':source.read_text()[t['start']:t['end']],'span_sha256':g.hashlib.sha256(source.read_text()[t['start']:t['end']].encode()).hexdigest()} for t in turns],'proposed_membership':{'question_turn_ids':['0'],'answer_turn_ids':['1'],'non_question_turns':['2']},'coverage_row':row,'proposed_coverage_change':{'grounding_status':'bound','grounding_notes':'Reviewed'}}
   path=root/'proposal.json';r.save(path,proposal)
   binding={'proposal':str(path),'proposal_sha256':r.sha(path),'review':{'job':str(root/'job')}}
   verdict={'content':dict(decision='accept',membership_accepted=True,coverage_status_change_accepted=True,closing_content_retained=True)}
   read=r.read
   def reader(p):
    return {'bindings':{'proposal_sha256':r.sha(path),'scope':'source-attribution-only'}} if Path(p).name=='request.json' else read(p)
   with patch.object(g.imp,'authenticate',return_value=verdict),patch.object(g.r,'read',side_effect=reader):
    b,o,_=g.apply(binding,bundle,out)
    self.assertEqual(b['transcript_index']['turns'],turns);self.assertEqual(o['exchange_coverage'][0]['answer'],'Answer.')
    self.assertEqual(out['exchange_coverage'][0]['grounding_status'],'unresolved')
    verdict['content']['closing_content_retained']=False
    with self.assertRaisesRegex(ValueError,'acceptance'):g.apply(binding,bundle,out)
    verdict['content']['closing_content_retained']=True
    proposal['proposed_coverage_change']['answer']='Changed'
    path.write_text(__import__('json').dumps(proposal));binding['proposal_sha256']=r.sha(path)
    with self.assertRaisesRegex(ValueError,'Only reviewed'):g.apply(binding,bundle,out)
