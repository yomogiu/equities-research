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
  this.agent.onPayload(payload());
  this.agent.state.messages.push({role:'assistant',stopReason:'stop',content:[{type:'text',text:'# Role result\\n```json\\n{"fictional":true}\\n```'}]});
 },async disposeAsync(options){if(options.kernelSnapshot!==false)throw Error('snapshot enabled')}};
 return {session};
}
'''


@unittest.skipUnless(shutil.which('node'),'Local Node runtime required')
class PrimeHelperTests(unittest.TestCase):
    def run_helper(self,cap=200000,tool_calls=48):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);sdk=root/'sdk';job=root/'job';job.mkdir();(sdk/'dist').mkdir(parents=True)
            oauth=sdk/'node_modules/@earendil-works/pi-ai/dist';oauth.mkdir(parents=True)
            (sdk/'package.json').write_text('{"type":"module","version":"fictional-test"}')
            (sdk/'dist/index.js').write_text(SDK);(oauth/'oauth.js').write_text('export const getOAuthProvider=()=>({});')
            (job/'request.json').write_text(json.dumps({'version':runner.VERSION,'tool_names':['ipython'],'model':'gpt-6.1-sol','effort':'low','max_tokens':cap,'max_tool_calls':tool_calls}))
            (job/'launch.json').write_text('{"id":"fake-launch"}');(job/'prompt.md').write_text('# Fictional role assignment')
            result=subprocess.run([shutil.which('node'),str(runner.HELPER),str(sdk),str(job)],capture_output=True,text=True,timeout=15)
            return result.returncode,{p.name:p.read_text() for p in job.iterdir() if p.is_file()}

    def test_exact_ipython_multi_turn_markdown_and_no_ambient_tools(self):
        code,files=self.run_helper();self.assertEqual(code,0);self.assertIn('response.md',files)
        self.assertEqual(len(json.loads(files['wire.json'])),2)
        self.assertEqual(json.loads(files['wire.json'])[0]['tools'],['ipython'])

    def test_budget_guard_prevents_unreserved_provider_turn(self):
        code,files=self.run_helper(cap=1000);self.assertNotEqual(code,0);self.assertNotIn('response.md',files);self.assertIn('runtime-failure.json',files)

    def test_tool_call_limit_stops_followup(self):
        code,files=self.run_helper(tool_calls=1);self.assertNotEqual(code,0);self.assertNotIn('response.md',files)

if __name__=='__main__':unittest.main()
