import json,subprocess,unittest
from pathlib import Path
class TransportDiagnosticsTests(unittest.TestCase):
 def test_only_closed_explicit_provider_rejections_retry_once(self):
  module=(Path(__file__).parents[1]/'research/earnings_transport_diagnostics.mjs').as_uri()
  program=f'''import {{instrumentFetch}} from {json.dumps(module)};
globalThis.setTimeout=(fn)=>{{fn();return 1}};
let calls=0,events=[];
const refused=()=>new Response(JSON.stringify({{error:{{code:'server_overloaded'}}}}),{{status:503,headers:{{'content-type':'application/json'}}}});
const f=instrumentFetch(async()=>{{calls++;return refused()}},()=>{{}},e=>events.push(e),true);
const response=await f('endpoint');if(calls!==2||response.status!==503)throw Error('Retry bound changed');
if(events.filter(e=>e.phase==='explicit_provider_rejection').length!==1)throw Error('Missing rejection evidence');
for(const value of [new Response('data: partial',{{status:200,headers:{{'content-type':'text/event-stream'}}}}),new Response('{{"error":{{"code":"unknown"}}}}',{{status:503,headers:{{'content-type':'application/json'}}}}),new Response('{{"error":{{"code":"server_overloaded"}},"usage":1}}',{{status:503,headers:{{'content-type':'application/json'}}}})]){{
let n=0;const g=instrumentFetch(async()=>{{n++;return value}},()=>{{}},()=>{{}},true);if(await g('endpoint')!==value||n!==1||value.bodyUsed)throw Error('Unsafe retry or consumed response');
}}
let n=0;const g=instrumentFetch(async()=>{{n++;throw new Error('unknown execution')}},()=>{{}},()=>{{}},true);try{{await g('endpoint')}}catch{{}}if(n!==1)throw Error('Network retry');'''
  subprocess.run(['node','--input-type=module','-e',program],check=True)
 def test_codes_only_no_secrets_and_no_retry(self):
  module=(Path(__file__).parents[1]/'research/earnings_transport_diagnostics.mjs').as_uri()
  program=f'''import {{failureCodes,instrumentFetch}} from {json.dumps(module)};
const privateValue="secret-account-token-and-source-body";
const error=Object.assign(new TypeError(privateValue),{{cause:{{code:"ECONNRESET",message:privateValue,stack:privateValue,errors:[{{code:"UND_ERR_SOCKET",url:privateValue}},{{code:privateValue}}]}}}});
let calls=0,notes=[]; const f=instrumentFetch(async()=>{{calls++;throw error}},v=>notes.push(v));
try{{await f(privateValue,{{headers:{{Authorization:privateValue}},body:privateValue}})}}catch(e){{if(e!==error)throw Error("Error identity changed")}}
console.log(JSON.stringify({{calls,notes}}));'''
  result=json.loads(subprocess.check_output(['node','--input-type=module','-e',program],text=True))
  self.assertEqual(result['calls'],1);self.assertEqual(result['notes'][0]['codes'],['ECONNRESET','UND_ERR_SOCKET']);self.assertFalse(result['notes'][0]['retry_authorized']);self.assertNotIn('secret-account',json.dumps(result))
 def test_success_response_and_call_arguments_unchanged(self):
  module=(Path(__file__).parents[1]/'research/earnings_transport_diagnostics.mjs').as_uri()
  program=f'''import {{instrumentFetch}} from {json.dumps(module)};let notes=[];const expected={{ok:true}};const opts={{method:"HEAD"}};const f=instrumentFetch(async(url,arg)=>{{if(url!=="endpoint"||arg!==opts)throw Error("Arguments changed");return expected}},v=>notes.push(v));if(await f("endpoint",opts)!==expected||notes.length)throw Error("Behavior changed");'''
  subprocess.run(['node','--input-type=module','-e',program],check=True)
 def test_lifecycle_preserves_stream_and_unknown_execution(self):
  module=(Path(__file__).parents[1]/'research/earnings_transport_diagnostics.mjs').as_uri()
  program=f'''import {{instrumentFetch,completionStage}} from {json.dumps(module)};
const events=[]; const response=new Response('source-private');
const f=instrumentFetch(async()=>response,()=>{{}},e=>events.push(e));
if(await f('secret-url')!==response || response.bodyUsed)throw Error('Stream consumed');
const error=Object.assign(new Error('secret'),{{code:'ETIMEDOUT'}});
const g=instrumentFetch(async()=>{{throw error}},()=>{{}},e=>events.push(e));
try{{await g('secret-url')}}catch(e){{if(e!==error)throw e}}
if(completionStage({{role:'assistant',stopReason:'error'}})!=='model_request')throw Error('Wrong stage');
if(completionStage({{role:'assistant',stopReason:'stop'}})!=='output_validation')throw Error('Wrong stage');
console.log(JSON.stringify(events));'''
  events=json.loads(subprocess.check_output(['node','--input-type=module','-e',program],text=True))
  self.assertEqual([e['phase'] for e in events],['fetch_started','headers_received','fetch_started','fetch_failed'])
  self.assertTrue(all(e['execution_certainty']=='unknown' and not e['retry_authorized'] for e in events))
  self.assertNotIn('secret',json.dumps(events));self.assertNotIn('source-private',json.dumps(events))
