import json,subprocess,unittest
from pathlib import Path
class TransportDiagnosticsTests(unittest.TestCase):
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
