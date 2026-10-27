"""Active report execution must work with retired workflow imports forbidden."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_earnings_compact_evidence import fixture


class SequentialDependencyTests(unittest.TestCase):
    def test_complete_correction_cycle_without_legacy_modules(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            (root/'writing.md').write_text('Fictional writing standard.')
            from test_publisher_transcript import fixture as publisher_fixture
            from research.source_parse import page
            from research.earnings_source_case import sha
            raw, _, _ = publisher_fixture()
            raw = raw.replace(b'Guest, Fictional Supplier', b'COO, Fictional Widgets')
            (root/'call.html').write_bytes(raw)
            (root/'call.txt').write_text(page(raw, '').text)
            docs = [{'document_id':'fictional-'+name,'kind':kind,'period':'FY2040-Q1',
                     'completeness':'full','source_url':'https://example.invalid/'+name,
                     'raw_path':name+'.html','text_path':name+'.txt',
                     'raw_sha256':sha(root/(name+'.html')),'text_sha256':sha(root/(name+'.txt'))}
                    for name,kind in (('filing','periodic_filing'),('call','transcript'))]
            (root/'packet.json').write_text(json.dumps({'issuer_id':'fictional:widgets',
                                                      'period':'FY2040-Q1','documents':docs}))
            program = r'''
import copy, importlib.abc, json, sys
from pathlib import Path
from unittest.mock import patch
blocked = {'earnings_experiment','earnings_mixed_runner','earnings_mixed_pipeline',
 'earnings_passage_pipeline','earnings_report_repair','earnings_report_flow',
 'earnings_signals','earnings_corrections','earnings_file_pipeline',
 'earnings_batch_review','earnings_batched_flow','earnings_legacy_result_validation',
 'earnings_markdown'}
class RejectLegacy(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname.startswith('research.') and fullname.rsplit('.',1)[-1] in blocked:
   raise AssertionError('Active path imported retired module: '+fullname)
sys.meta_path.insert(0, RejectLegacy())
from research import earnings_sequential as engine, earnings_sequential_stages as stages
from research import earnings_file_context as context, earnings_source_preparation
from research import earnings_file_checkpoint
root=Path(sys.argv[1]).resolve(); job=root/'job'
packet=json.loads((root/'packet.json').read_text())
catalog={'catalog_id':'fictional-catalog','issuers':{'fictional:widgets':{'issuer':'Fictional Widgets, Inc.'}}}
with patch.object(earnings_source_preparation.library,'catalog',return_value=catalog):
 case=earnings_source_preparation.prepare_selected(root,'fictional-packet',packet,*packet['documents'],
  root/'prepared',root/'writing.md','Explicit fictional test')
engine.create(job, {'case_path':str(case), 'writing_standard':str(root/'writing.md'),
 'financial_analysis':stages.finance.configuration('2040-01-01','2040-03-31')})
calls=[]
def fake(role_dir, prompt, model, effort, bindings, index, **settings):
 request=stages.runner.request(role_dir,prompt,model,effort,bindings,index,
  settings['max_tokens'],settings['max_tool_calls'],settings['timeout'])
 assert request['execution_policy'] is None
 role_dir.mkdir(parents=True)
 reader=context.Evidence(index,role_dir/'retrieval.jsonl')
 assert reader.validate_result({})['acceptance'] is False
 for page in range(len(reader.role_batch_plan())): reader.role_batch(page)
 ref=[reader.index['exchange_ids'][0]]
 paragraph={'text':'Fictional uncertainty remains.', 'citations':ref}
 if bindings['role']=='sequential_analysis':
  reader.filing_batch(stages.AUTHOR_FILING_QUERY,4)
  if 'section_revision' in reader.artifacts:
   replacements=copy.deepcopy(reader.artifacts['section_revision']['current_components'])
   for value in replacements.values(): value['text']+=' The qualification matters.'
   value={'replacements':replacements}
  else:
   value={'title':'Fictional report','opening':paragraph,
    'sections':{key:copy.deepcopy(paragraph) for key in stages.SECTIONS},
    'qa':[{'exchange_id':ref[0],'question':'Repeatable?','answer':'Uncertain.',
      'assessment':'Fictional limitation.', 'citations':ref}], 'next_tests':[paragraph]}
 else:
  reader.challenge_batch('guidance risk cash flow debt capital expenditure',4)
  value={'verdict':'pass','criteria':{key:{'status':'pass','evidence':'Fictional support.',
   'citations':ref} for key in stages.CRITERIA},
   'questions':{key:{'status':'disclosed_gap','evidence':'Explicit fictional gap.',
    'gap':'Fictional inputs missing.','citations':ref} for key in stages.questions.QUESTIONS},'findings':[]}
  if bindings['revision']==0:
   value['verdict']='revise';value['criteria']['reasoning']['status']='fail'
   value['findings']=[{'location':'outlook','problem':'Qualification missing.',
    'fix':'State the fictional qualification.','citations':ref}]
 calls.append((model,effort))
 return {'content':value,'receipt':{'session':{'id':'fake-'+str(len(calls)),
  'usage':{'totalTokens':100}}}}
with patch.object(stages.runner,'run_role',side_effect=fake), patch.object(context,'delivered_entries',side_effect=lambda job,entries:entries):
 for _ in range(8):
  result=engine.advance(job,stages.handlers())
  if result['status']!='ready': break
assert result['status']=='completed',result.get('reason')
assert result['tokens_used']==400
assert calls==[('gpt-6.1-sol','medium'),('gpt-6.1-sol','medium'),('gpt-6-luna','max'),('gpt-6.1-sol','medium')]
assert not any(name.rsplit('.',1)[-1] in blocked for name in sys.modules if name.startswith('research.'))
print(json.dumps({'status':result['status'],'models':calls,'legacy_imports':0}))
'''
            result = subprocess.run([sys.executable,'-c',program,str(root)],
                                    cwd=Path(__file__).resolve().parents[1],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['legacy_imports'],0)


if __name__ == '__main__': unittest.main()
