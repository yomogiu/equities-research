import tempfile,json,unittest
from pathlib import Path
from research.selected_source_checkout import paths
class SelectedSourceCheckoutTests(unittest.TestCase):
 def test_only_selected_source_bodies_are_included(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d)
   def save(p,v):
    target=r/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(v))
   save('config.json',{'earnings_pipeline':{'audit':'audit.json'}});save('workflow.json',{})
   save('published/latest.json',{'issuers':{'one':{'packet_id':'p'}}});save('library/packets/p.json',{'documents':[{'raw_path':'bodies/one.bin','text_path':'bodies/one.txt','qualification_id':'q','source_excerpt':'nonpath '*1000}],'catalog_id':'c'})
   save('library/catalog.json',{'documents':{'one':{'issuer_id':'one','raw_path':'bodies/one.bin'},'two':{'issuer_id':'two','raw_path':'bodies/two.bin'}}});save('library/snapshots/c.json',{})
   save('library/qualifications/q.json',{});save('audit.json',{'results':[{'issuer_id':'one','documents':[]},{'issuer_id':'two','documents':[{'raw_path':'bodies/two.bin'}]}]});save('collection/document-index.json',{'two':{'manifest_path':'documents/two.json'}});save('collection/documents/two.json',{})
   save('bodies/one.bin',{});save('bodies/one.txt',{});save('bodies/two.bin',{})
   found=paths(r,['one']);self.assertIn('bodies/one.bin',found);self.assertIn('library/qualifications/q.json',found);self.assertIn('collection/documents/two.json',found);self.assertNotIn('bodies/two.bin',found)
 def test_empty_or_unbounded_selection_is_rejected(self):
  for ids in ([],['a','b','c','d']):
   with self.assertRaises(ValueError):paths('/private/tmp',ids)
