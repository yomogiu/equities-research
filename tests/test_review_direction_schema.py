import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_prepared_direction_schema as p,earnings_mixed_runner as b,earnings_inherited_profile_guard as g

def fixture():
 message='The contract requires a neutral direction for signal-3, but the result validator rejects that direction as unknown. This schema conflict prevents submitting a valid atomic batch.'
 findings={'signal-3':'Use neutral direction for this context-dependent movement. Fictional disposal affects comparability.\nSOURCE PASSAGE IDS\n["P-fictional"]','analysis:0':'Preserve separate required correction'}
 units={'signal-3':{'value':{'id':'signal-3','direction':'deteriorating','passage_ids':['P-fictional']}}}
 return message,findings,units
class DirectionSchemaTests(unittest.TestCase):
 def test_bridge_preserves_review_and_source_without_direction_selection(self):
  args=fixture();before=copy.deepcopy(args);v=p.schema_bridge(*args);self.assertEqual(args,before);self.assertEqual(v['original_finding'],args[1]['signal-3']);self.assertEqual(v['allowed_directions'],list(p.DIRECTIONS));self.assertNotIn('replacement',v);self.assertIn('not automatically equivalent',v['notice'])
 def test_unrelated_or_mixed_block_rejected(self):
  m,f,u=fixture()
  for bad in (m+' Also change prose.',m.replace('signal-3','analysis:3'),m.replace('neutral','positive'),'Local budget guard'):
   with self.assertRaises(ValueError):p.schema_bridge(bad,f,u)
 def test_unknown_unbound_or_invalid_signal_rejected(self):
  m,f,u=fixture()
  for bad in ('No original source bindings','Use neutral direction for this context-dependent movement.\nSOURCE PASSAGE IDS\n[]','Use neutral direction for this context-dependent movement.\nSOURCE PASSAGE IDS\n["P-a","P-a"]'):
   with self.assertRaises(ValueError):p.schema_bridge(m,{'signal-3':bad},u)
  u['signal-3']['value']['direction']='neutral'
  with self.assertRaises(ValueError):p.schema_bridge(m,f,u)
 def test_saved_manifest_cannot_change_usage_rounds_sources_or_prose(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'protocol.json').write_text('{}');case=root/'case.json';case.write_text('{}');catalog={'passages':[]}
   value={'case_sha256':b.sha(case),'catalog_sha256':b.digest(catalog),'tokens':700001,'max_tokens':1200000,'start_round':2,'spent_correction_rounds':1,'session_ids':['a','b','c','d','e'],'models':{'correction':['original','max']},'findings':fixture()[1],'schema_bridge':p.schema_bridge(*fixture())}
   path=root/'preparation.json'
   with patch.object(p,'replay',return_value=value):
    record=p.prepare(root,case,path);self.assertEqual(p.verify(path,case,catalog)['tokens'],700001)
    for key,bad in [('tokens',0),('start_round',1),('spent_correction_rounds',0),('session_ids',[]),('findings',{}),('schema_bridge',{}),('models',{})]:
     changed=copy.deepcopy(record);changed[key]=bad;path.write_text(json.dumps(changed))
     with self.assertRaises(ValueError):p.verify(path,case,catalog)
 def test_profile_rejects_wrong_routes_handler_and_round_accounting(self):
  from research.earnings_file_pipeline import profile_models
  v={'model_profile':None,'models':profile_models('original-file-review-routes-v1'),'preparation_version':p.VERSION,'spent_correction_rounds':1,'session_count':5};self.assertTrue(g.matches_direction(v,'original-file-review-routes-v1'))
  for key,bad in [('models',{}),('preparation_version','unrelated'),('spent_correction_rounds',0),('session_count',4),('model_profile','changed')]:
   x={**v,key:bad}
   with self.assertRaises(ValueError):g.matches_direction(x,'original-file-review-routes-v1')
