"""Run the actual JS helper against a fictional SDK; no auth/network/model calls."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from research import earnings_file_runner as runner

SDK='''
import fs from 'node:fs';import path from 'node:path';
export class AuthStorage {static create(){return {drainErrors:()=>[]}}}
export class ModelRegistry {static inMemory(){return {find:(provider,id)=>({id,provider,api:'openai-codex-responses',maxTokens:128000}),isUsingOAuth:()=>true}}}
export class SettingsManager {static inMemory(x){return x}}
export class DefaultResourceLoader {constructor(x){this.x=x}async reload(){}}
export class SessionManager {static create(){return {flushNow(){}}}}
export async function createAgentSession(opts){
 if(JSON.stringify(opts.tools)!==JSON.stringify(['ipython']) || opts.noTools==='all')throw Error('wrong tools');
 if(!opts.resourceLoader.x.noExtensions || !opts.resourceLoader.x.noSkills || !opts.resourceLoader.x.noContextFiles)throw Error('ambient context');
 const q=JSON.parse(fs.readFileSync(path.join(opts.cwd,'request.json')));const model=opts.model;
 const session={sessionId:'fictional-session',model,thinkingLevel:q.effort,agent:{state:{tools:[{name:'ipython'}],messages:[]}},
 async prompt(text){
  if(text!=='# Fictional role assignment')throw Error('wrong prompt');
  const payload=()=>({model:q.model,reasoning:{effort:q.effort},tools:[{name:'ipython'}],input:[]});
  const first=payload();this.agent.onPayload(first);if('max_output_tokens' in first)throw Error('unsupported API field');
  this.agent.state.messages.push({role:'assistant',usage:{totalTokens:20},content:[{type:'toolCall',name:'ipython',id:'one'}]});
  const followup=payload();this.agent.onPayload(followup);if(q.execution_policy && followup.tool_choice!=='none')throw Error('final phase missing');
  this.agent.state.messages.push({role:'assistant',stopReason:'stop',content:[{type:'text',text:'# Role result\\n```json\\n{"fictional":true}\\n```'}]});
 },async disposeAsync(options){if(options.kernelSnapshot!==false)throw Error('snapshot enabled')}};
 return {session};
}
'''


@unittest.skipUnless(shutil.which('node'),'Local Node runtime required')
class PrimeHelperTests(unittest.TestCase):
    def run_helper(self,cap=200000,tool_calls=48,large_prefix=False,changed_prefix=False,work_limit=None,capture_index=None,bad_final_tool=False):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);sdk=root/'sdk';job=root/'job';job.mkdir();(sdk/'dist').mkdir(parents=True)
            oauth=sdk/'node_modules/@earendil-works/pi-ai/dist';oauth.mkdir(parents=True)
            (sdk/'package.json').write_text('{"type":"module","version":"fictional-test"}')
            source=SDK
            if large_prefix:
                source=source.replace('usage:{totalTokens:20}', 'usage:{input:10,output:7,cacheRead:3,cacheWrite:0,totalTokens:20}')
                head="(payloadRound===0?'x':'z')" if changed_prefix else "'x'"
                source=source.replace("const payload=()=>({model:q.model,reasoning:{effort:q.effort},tools:[{name:'ipython'}],input:[]});",
                    "let payloadRound=0; const payload=()=>({model:q.model,reasoning:{effort:q.effort},tools:[{name:'ipython'}],input:[{role:'user',content:"+head+".repeat(100000)}, ...(payloadRound++?[{role:'tool',content:'y'.repeat(120000)}]:[])]});")
            if capture_index:
                source=source.replace("import fs from 'node:fs';import path from 'node:path';", "import fs from 'node:fs';import path from 'node:path';import {spawnSync} from 'node:child_process';")
                source=source.replace('  const followup=payload();', '''  if(q.context_index){
    await this.agent.beforeToolCall({toolCall:{id:'one'}},undefined);
    const read=spawnSync(q.checkpoint_python,['-B','-I','-c',"import sys;sys.path.insert(0,sys.argv[1]);from research.earnings_file_context import Evidence;c=Evidence(sys.argv[2],sys.argv[3]);print(c.scope('D001'))",q.code_root,q.context_index,path.join(opts.cwd,'retrieval.jsonl')],{encoding:'utf8'});
    if(read.status!==0)throw Error('fictional source read failed');
    await this.agent.afterToolCall({toolCall:{id:'one'},result:{content:[{type:'text',text:read.stdout}]},isError:false});
  }
  const followup=payload();''')
            if bad_final_tool:
                source=source.replace("  this.agent.state.messages.push({role:'assistant',stopReason:'stop'", "  const blocked=await this.agent.beforeToolCall({toolCall:{id:'forbidden'}},undefined);if(!blocked?.block)throw Error('late tool executed');this.agent.onPayload(payload());\n  this.agent.state.messages.push({role:'assistant',stopReason:'stop'")
            (sdk/'dist/index.js').write_text(source);(oauth/'oauth.js').write_text('export const getOAuthProvider=()=>({});')
            (job/'request.json').write_text(json.dumps({'version':runner.VERSION,'tool_names':['ipython'],'model':'gpt-6.1-sol','effort':'low','max_tokens':cap,'max_tool_calls':tool_calls,**({'execution_policy':{'work_tool_limit':work_limit,'automatic_checkpoints':False}} if work_limit else {})}))
            if capture_index:
                q=runner.request(job,'# Fictional role assignment','gpt-6.1-sol','low',{'role':'analysis'},capture_index,cap,tool_calls,15)
                (job/'request.json').write_text(json.dumps(q))
            (job/'launch.json').write_text('{"id":"fake-launch"}');(job/'prompt.md').write_text('# Fictional role assignment')
            result=subprocess.run([shutil.which('node'),str(runner.HELPER),str(sdk),str(job)],capture_output=True,text=True,timeout=15)
            files={p.name:p.read_text() for p in job.iterdir() if p.is_file()}
            if (job/'automatic-checkpoints.json').exists():
                item=json.loads((job/'automatic-checkpoints.json').read_text())[0]
                files['captured-checkpoint']=Path(item['checkpoint']).read_text()
            return result.returncode,files

    def test_exact_ipython_multi_turn_markdown_and_no_ambient_tools(self):
        code,files=self.run_helper();self.assertEqual(code,0);self.assertIn('response.md',files)
        self.assertEqual(len(json.loads(files['wire.json'])),2)
        self.assertEqual(json.loads(files['wire.json'])[0]['tools'],['ipython'])

    def test_budget_guard_prevents_unreserved_provider_turn(self):
        code,files=self.run_helper(cap=1000);self.assertNotEqual(code,0);self.assertNotIn('response.md',files);self.assertIn('runtime-failure.json',files)

    def test_metered_stable_prefix_avoids_recounting_it_as_bytes(self):
        code,files=self.run_helper(cap=300000,large_prefix=True)
        self.assertEqual(code,0);self.assertIn('response.md',files)

    def test_changed_prefix_keeps_conservative_full_byte_reserve(self):
        code,files=self.run_helper(cap=300000,large_prefix=True,changed_prefix=True)
        self.assertNotEqual(code,0);self.assertNotIn('response.md',files)

    def test_work_phase_has_a_final_turn_without_tools(self):
        code,files=self.run_helper(cap=1200000,work_limit=1)
        self.assertEqual(code,0)
        wire=json.loads(files['wire.json'])
        self.assertEqual([w['tool_choice'] for w in wire],['auto','none'])
        self.assertIn('response.md',files)

    def test_low_remaining_budget_finalizes_before_another_tool_round(self):
        code,files=self.run_helper(cap=200000,work_limit=3)
        self.assertEqual(code,0)
        self.assertEqual(json.loads(files['wire.json'])[-1]['tool_choice'],'none')

    def test_real_host_hook_captures_without_a_model_checkpoint_call(self):
        from test_earnings_file_pipeline import FilePipelineTests
        fixture=FilePipelineTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        code,files=self.run_helper(cap=200000,capture_index=fixture.assemble())
        self.assertEqual(code,0,files.get('runtime-failure.json'))
        receipts=json.loads(files['automatic-checkpoints.json'])
        self.assertEqual(receipts[0]['status'],'saved')
        checkpoint=json.loads(files['captured-checkpoint'])
        self.assertEqual(checkpoint['draft']['kind'],'source_progress_only')
        self.assertIn('D001',checkpoint['draft']['source_ids'])
        self.assertEqual(json.loads(files['wire.json'])[-1]['tool_choice'],'none')

    def test_final_phase_refuses_unexpected_tool_execution(self):
        code,files=self.run_helper(cap=200000,work_limit=1,bad_final_tool=True)
        self.assertNotEqual(code,0)
        self.assertNotIn('response.md',files)
        self.assertEqual(json.loads(files['runtime-failure.json'])['code'],'finalization_tool_violation')

    def test_tool_call_limit_stops_followup(self):
        code,files=self.run_helper(tool_calls=1);self.assertNotEqual(code,0);self.assertNotIn('response.md',files)

if __name__=='__main__':unittest.main()
