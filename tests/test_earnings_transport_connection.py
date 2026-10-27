import json,subprocess,unittest
from pathlib import Path
class ConnectionPolicyTests(unittest.TestCase):
 def test_child_policy_preserves_family_fallback_no_retry_or_tls_bypass(self):
  module=(Path(__file__).parents[1]/'research/earnings_transport_connection.mjs').as_uri()
  program=f'''import {{configureWorkerConnections}} from {json.dumps(module)};let calls=[];const result=configureWorkerConnections({{setDefaultResultOrder:x=>calls.push(['dns',x])}},{{setDefaultAutoSelectFamily:x=>calls.push(['auto',x]),setDefaultAutoSelectFamilyAttemptTimeout:x=>calls.push(['timeout',x])}});console.log(JSON.stringify({{calls,result}}));'''
  v=json.loads(subprocess.check_output(['node','--input-type=module','-e',program],text=True));self.assertEqual(v['calls'],[['dns','ipv4first'],['auto',True],['timeout',1000]]);self.assertTrue(v['result']['tls_verification']);self.assertEqual(v['result']['request_retries'],0)
 def test_actual_node_child_settings(self):
  module=(Path(__file__).parents[1]/'research/earnings_transport_connection.mjs').as_uri()
  program=f'''import dns from 'node:dns';import net from 'node:net';import {{configureWorkerConnections}} from {json.dumps(module)};configureWorkerConnections();console.log(JSON.stringify([dns.getDefaultResultOrder(),net.getDefaultAutoSelectFamily(),net.getDefaultAutoSelectFamilyAttemptTimeout()]));'''
  self.assertEqual(json.loads(subprocess.check_output(['node','--input-type=module','-e',program],text=True)),['ipv4first',True,1000])
