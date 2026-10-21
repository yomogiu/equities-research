"""Exact reserved-profile compatibility for authenticated inherited author work."""
from pathlib import Path
import json,re,subprocess,sys
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-inherited-host-model-profile-v1'
HANDLER='authenticated-analysis-host-address-preparation-v1'
def matches(value,expected):
 from .earnings_file_pipeline import profile_models
 c.require(expected=='original-file-review-routes-v1' and value['model_profile'] is None and value['preparation_version']==HANDLER and value['models']==profile_models(expected),'Exact inherited original model routes required');return True
def validate(root,expected):
 root=Path(root).resolve();protocol=b.read(root/'protocol.json');code=Path(next(x['path'] for x in protocol['code'] if x['path'].endswith('/earnings_file_pipeline.py'))).parent.parent
 c.require(code.parent.name=='.report-workflow' and re.fullmatch('[a-f0-9]{40}',code.name),'Managed frozen pipeline required')
 c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip() and subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Official frozen pipeline required')
 program="import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from research import earnings_file_pipeline as p,earnings_mixed_runner as b;v,_,_=p.load(Path(sys.argv[2]));print(json.dumps({'model_profile':v.get('model_profile'),'models':v['models'],'preparation_version':b.read(v['analysis_preparation_path'])['version']}))"
 value=json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(root)],text=True));matches(value,expected);return {'version':VERSION,'protocol_sha256':b.sha(root/'protocol.json'),'reserved_model_profile':expected,**value}

HEADING_HANDLER='authenticated-final-heading-proposal-continuation-v1'
def matches_heading(value,expected):
 from .earnings_file_pipeline import profile_models
 c.require(expected=='original-file-review-routes-v1' and value['model_profile'] is None and value['preparation_version']==HEADING_HANDLER and value['models']==profile_models(expected) and value['spent_correction_rounds']==2 and value['session_count']==6,'Exact final-heading inherited routes and accounting required');return True

def validate_heading(root,expected):
 root=Path(root).resolve();protocol=b.read(root/'protocol.json');code=Path(next(x['path'] for x in protocol['code'] if x['path'].endswith('/earnings_file_pipeline.py'))).parent.parent
 c.require(code.parent.name=='.report-workflow' and re.fullmatch('[a-f0-9]{40}',code.name),'Managed frozen pipeline required')
 c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip() and subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Official frozen pipeline required')
 program="import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from research import earnings_file_pipeline as p,earnings_mixed_runner as b;v,_,_=p.load(Path(sys.argv[2]));h=b.read(v['review_preparation_path']);print(json.dumps({'model_profile':v.get('model_profile'),'models':v['models'],'preparation_version':h['version'],'spent_correction_rounds':h['spent_correction_rounds'],'session_count':len(h['session_ids'])}))"
 value=json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(root)],text=True));matches_heading(value,expected);return {'version':'authenticated-inherited-heading-model-profile-v1','protocol_sha256':b.sha(root/'protocol.json'),'reserved_model_profile':expected,**value}

QUESTION_HANDLER='authenticated-single-retrieval-question-address-preparation-v1'
def matches_question(value,expected):
 from .earnings_file_pipeline import profile_models
 c.require(expected=='original-file-review-routes-v1' and value['model_profile'] is None and value['preparation_version']==QUESTION_HANDLER and value['models']==profile_models(expected) and type(value['spent_correction_rounds']) is int and value['spent_correction_rounds']==1 and type(value['session_count']) is int and value['session_count']==2,'Exact question inherited routes and accounting required');return True

def validate_question(root,expected):
 root=Path(root).resolve();protocol=b.read(root/'protocol.json');code=Path(next(x['path'] for x in protocol['code'] if x['path'].endswith('/earnings_file_pipeline.py'))).parent.parent
 c.require(code.parent.name=='.report-workflow' and re.fullmatch('[a-f0-9]{40}',code.name),'Managed frozen pipeline required')
 c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip() and subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Official frozen pipeline required')
 program="import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from research import earnings_file_pipeline as p,earnings_mixed_runner as b;v,_,_=p.load(Path(sys.argv[2]));h=b.read(v['preparation_path']);print(json.dumps({'model_profile':v.get('model_profile'),'models':v['models'],'preparation_version':h['version'],'spent_correction_rounds':h['spent_correction_rounds'],'session_count':len(h['session_ids'])}))"
 value=json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(root)],text=True));matches_question(value,expected);return {'version':'authenticated-inherited-question-model-profile-v1','protocol_sha256':b.sha(root/'protocol.json'),'reserved_model_profile':expected,**value}

DIRECTION_HANDLER='authenticated-review-direction-schema-continuation-v1'
def matches_direction(value,expected):
 from .earnings_file_pipeline import profile_models
 c.require(expected=='original-file-review-routes-v1' and value['model_profile'] is None and value['preparation_version']==DIRECTION_HANDLER and value['models']==profile_models(expected) and value['spent_correction_rounds']==1 and value['session_count']==5,'Exact direction-schema inherited routes and accounting required');return True

def validate_direction(root,expected):
 root=Path(root).resolve();protocol=b.read(root/'protocol.json');code=Path(next(x['path'] for x in protocol['code'] if x['path'].endswith('/earnings_file_pipeline.py'))).parent.parent
 c.require(code.parent.name=='.report-workflow' and re.fullmatch('[a-f0-9]{40}',code.name),'Managed frozen pipeline required')
 c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip() and subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Official frozen pipeline required')
 program="import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from research import earnings_file_pipeline as p,earnings_mixed_runner as b;v,_,_=p.load(Path(sys.argv[2]));h=b.read(v['review_preparation_path']);print(json.dumps({'model_profile':v.get('model_profile'),'models':v['models'],'preparation_version':h['version'],'spent_correction_rounds':h['spent_correction_rounds'],'session_count':len(h['session_ids'])}))"
 value=json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(root)],text=True));matches_direction(value,expected);return {'version':'authenticated-inherited-direction-model-profile-v1','protocol_sha256':b.sha(root/'protocol.json'),'reserved_model_profile':expected,**value}

CHARGED_RETRIEVAL_HANDLER='authenticated-charged-retrieval-preparation-v1'
def matches_charged_retrieval(value,expected):
 from .earnings_file_pipeline import profile_models
 c.require(expected=='original-file-review-routes-v1' and value['model_profile'] is None and value['preparation_version']==CHARGED_RETRIEVAL_HANDLER and value['models']==profile_models(expected) and type(value['spent_correction_rounds']) is int and value['spent_correction_rounds']==1 and type(value['session_count']) is int and value['session_count']==2,'Exact charged retrieval inherited routes and accounting required');return True

def validate_charged_retrieval(root,expected):
 root=Path(root).resolve();protocol=b.read(root/'protocol.json');code=Path(next(x['path'] for x in protocol['code'] if x['path'].endswith('/earnings_file_pipeline.py'))).parent.parent
 c.require(code.parent.name=='.report-workflow' and re.fullmatch('[a-f0-9]{40}',code.name),'Managed frozen pipeline required')
 c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip() and subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Official frozen pipeline required')
 program="import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from research import earnings_file_pipeline as p,earnings_mixed_runner as b;v,_,_=p.load(Path(sys.argv[2]));h=b.read(v['preparation_path']);print(json.dumps({'model_profile':v.get('model_profile'),'models':v['models'],'preparation_version':h['version'],'spent_correction_rounds':h['spent_correction_rounds'],'session_count':len(h['session_ids'])}))"
 value=json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(root)],text=True));matches_charged_retrieval(value,expected);return {'version':'authenticated-inherited-charged-retrieval-model-profile-v1','protocol_sha256':b.sha(root/'protocol.json'),'reserved_model_profile':expected,**value}
