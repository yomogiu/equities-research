from unittest import TestCase
from unittest.mock import patch
from research import earnings_remediation as m
from research import earnings_reviewed_grounding as g, earnings_role_import as imp

class ReviewSourceLoaderTests(TestCase):
 def test_overlay_precedes_grounding_validation(self):
  original={'manifest':'fake','transcript_index':{'original':True}};derived={'manifest':'fake','transcript_index':{'reviewed':True}};catalog={'passages':[]}
  protocol={'evidence_manifest':'fake','grounding_recovery':{'reviewed_boundary':{'fake':True},'responses':{'retrieval':{'reference':'fake'}}}}
  with patch.object(m.evidence,'load_bundle',return_value=original),patch.object(m.passages,'catalog',return_value=catalog),patch.object(imp,'authenticate',return_value={'content':{'saved':True}}),patch.object(g,'apply',return_value=(derived,{},{})) as apply,patch.object(m.corrections.qa_grounding,'attach') as attach:
   self.assertEqual(m._source_bundle(protocol),(derived,catalog));apply.assert_called_once_with({'fake':True},original,{'saved':True});attach.assert_called_once_with(None,protocol,derived,catalog)
 def test_legacy_source_has_no_overlay(self):
  original={'manifest':'fake'}
  with patch.object(m.evidence,'load_bundle',return_value=original),patch.object(m.passages,'catalog',return_value={}),patch.object(g,'apply') as apply,patch.object(m.corrections.qa_grounding,'attach'):
   self.assertEqual(m._source_bundle({'evidence_manifest':'fake'}),(original,{}));apply.assert_not_called()
