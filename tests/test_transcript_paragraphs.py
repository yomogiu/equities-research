"""Fictional source boundaries; no real research fixtures."""
import hashlib
import unittest
from research.source_parse import page
from research.transcript_evidence import index_publisher_transcript

class ParagraphTests(unittest.TestCase):
 def source(self,body):
  raw=('<html><p>Provider summary</p><div id="article-body-transcript"><h2 id="full-conference-call-transcript">Full Conference Call Transcript</h2>'+body+'</div><p>Related news</p></html>').encode()
  text=page(raw,'').text
  source={'document_id':'fictional','raw_sha256':hashlib.sha256(raw).hexdigest(),'text_sha256':hashlib.sha256(text.encode()).hexdigest()}
  return raw,text,source
 def test_continuations_unicode_and_unknown_identity(self):
  raw,text,source=self.source('<p><strong>Operator:</strong> Welcome.</p><p><strong>Unknown Executive:</strong> Sales rose €2.</p><p>Costs fell &amp; margins grew.</p><p><strong>Operator:</strong> Disconnect.</p>')
  result=index_publisher_transcript(text,source,raw);self.assertEqual(len(result['turns']),3)
  t=result['turns'][1];self.assertEqual(t['role'],'unknown');self.assertEqual(text[t['start']:t['end']],'Unknown Executive: Sales rose €2.\nCosts fell & margins grew.')
  self.assertEqual(result['layout'],'speaker-paragraphs-v1');self.assertTrue(result['needs_review']);self.assertNotIn('Related news',text[result['call_span']['start']:result['call_span']['end']])
 def test_nonparagraph_substantive_text_rejected(self):
  raw,text,source=self.source('<p><strong>Operator:</strong> Welcome.</p><div>Omitted substantive answer</div>')
  with self.assertRaisesRegex(ValueError,'Unindexed content'):index_publisher_transcript(text,source,raw)
 def test_unlabeled_opening_rejected(self):
  raw,text,source=self.source('<p>Unattributed opening</p>')
  with self.assertRaisesRegex(ValueError,'without speaker'):index_publisher_transcript(text,source,raw)
 def test_duplicate_container_rejected(self):
  raw,text,source=self.source('<p><strong>Operator:</strong> Welcome.</p><div id="article-body-transcript"></div>')
  with self.assertRaisesRegex(ValueError,'ambiguous'):index_publisher_transcript(text,source,raw)
 def test_source_text_mismatch_rejected(self):
  raw,text,source=self.source('<p><strong>Operator:</strong> Welcome.</p>');text=text.replace('Welcome.','Changed.');source['text_sha256']=hashlib.sha256(text.encode()).hexdigest()
  with self.assertRaisesRegex(ValueError,'not uniquely present'):index_publisher_transcript(text,source,raw)
 def test_unknown_named_speakers_never_promoted(self):
  raw,text,source=self.source('<p><strong>Person Example:</strong> I lead this business.</p>')
  self.assertEqual(index_publisher_transcript(text,source,raw)['turns'][0]['role'],'unknown')
