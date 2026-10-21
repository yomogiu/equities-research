"""Authenticate a source-preparation stop before any model work existed.

This is a direct request lineage, never a completed-role recovery or a usage
reset. The coordinator must additionally replay source qualification, independent
speaker coverage, original code defaults and the complete funded path.
"""
from pathlib import Path
import re
from . import earnings_mixed_runner as b, earnings_file_context as c
VERSION='authenticated-unstarted-source-request-v1'
REASON='Q&A boundaries need review before transcript-led analysis'

def inspect(root,run_id):
 root=Path(root).resolve()
 c.require(isinstance(run_id,str) and re.fullmatch('[a-f0-9]{24}',run_id),'Exact original run identity required')
 run=root/'reporting/runs'/run_id
 c.require(not run.is_symlink() and run.is_dir(),'Original request directory required')
 c.require(sorted(p.name for p in run.iterdir())==['request.json','state.json'] and all(p.is_file() and not p.is_symlink() for p in run.iterdir()),'Unstarted request must have only original request and preparation stop; any pipeline, job or artifact disqualifies')
 q=b.read(run/'request.json');s=b.read(run/'state.json');spec=q['spec']
 c.require(q['run_id']==run_id==b.digest(spec)[:24] and q.get('schema_version')==1,'Original request identity changed')
 c.require(set(spec)=={'packet_id','issuer_id','period','code_commit','writing_sha256','signals','deterministic_corrections','review_policy'} and spec['signals'] is True and spec['deterministic_corrections'] is True and spec['review_policy']=='file-backed-markdown-review-v1','Only original unstarted file-report requests qualify')
 c.require(s.get('status')=='needs_attention' and s.get('run_id')==run_id and s.get('reason')==REASON,'Exact source preparation stop required')
 c.require(q.get('input_sha256') and all((root/p).resolve().is_relative_to(root) and b.sha((root/p).resolve())==h for p,h in q['input_sha256'].items()),'Original frozen input changed')
 auth=root/f'reporting/authorizations/{run_id}.json';a=b.read(auth)
 c.require(a.get('enabled') is True and a.get('request_sha256')==b.digest(q) and a.get('scope')=='one_packet','Original request authorization required')
 return {'version':VERSION,'source_run_id':run_id,'source_request_sha256':b.sha(run/'request.json'),'source_state_sha256':b.sha(run/'state.json'),'source_authorization_sha256':b.sha(auth),'original_spec':spec,'tokens':0,'sessions':[],'correction_rounds_spent':0,'resumes_spent':0,'whole_report_accepted':False}

def prepare(root,run_id,output):
 c.require(not Path(output).exists(),'Immutable new unstarted-source proof required');v=inspect(root,run_id);c.write(output,v);return v

def verify(root,path):
 v=b.read(path);c.require(v==inspect(root,v['source_run_id']),'Unstarted-source lineage or accounting changed');return v
