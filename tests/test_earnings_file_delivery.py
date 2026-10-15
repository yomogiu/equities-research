"""Exercise the real JS delivery boundary, including Unicode and duplicate details."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from research import earnings_file_runner as runner


@unittest.skipUnless(shutil.which('node'),'Node required')
class DeliveryTests(unittest.TestCase):
    def deliver(self,blocks,details=None):
        with tempfile.TemporaryDirectory() as directory:
            script='''import fs from 'node:fs';import {installDelivery} from MODULE;
const job=process.argv[1];const input=JSON.parse(fs.readFileSync(0,'utf8'));
let preserved=false;const agent={afterToolCall:async()=>{preserved=true;return undefined}};
installDelivery(agent,job);const out=await agent.afterToolCall({toolCall:{id:'fictional-call'},result:input,isError:false});
console.log(JSON.stringify({out,preserved,record:JSON.parse(fs.readFileSync(job+'/delivery.jsonl','utf8')),files:fs.readdirSync(job+'/tool-output')}));'''.replace('MODULE',json.dumps(runner.DELIVERY.as_uri()))
            result=subprocess.run([shutil.which('node'),'--input-type=module','-e',script,directory],input=json.dumps({'content':blocks,'details':details}),text=True,capture_output=True,check=True)
            return json.loads(result.stdout)

    def test_aggregate_multiblock_unicode_overflow_preserved_on_disk(self):
        result=self.deliver([{'type':'text','text':'\\\n😀'*3000},{'type':'text','text':'more'*3000}],{'stdout':'duplicate'*10000})
        self.assertTrue(result['preserved']);self.assertFalse(result['record']['complete'])
        self.assertLessEqual(result['record']['delivered_bytes'],8192)
        self.assertGreater(result['record']['original_bytes'],8192)
        self.assertEqual(len(result['files']),1);self.assertIn('ctx.output',result['out']['content'][0]['text'])
        self.assertNotIn('stdout',result['out']['details'])

    def test_small_result_keeps_complete_text_but_removes_duplicate_details(self):
        result=self.deliver([{'type':'text','text':'small original source'}],{'stdout':'duplicate'*10000})
        self.assertTrue(result['record']['complete']);self.assertEqual(result['out']['content'][0]['text'],'small original source')
        self.assertLessEqual(result['record']['delivered_bytes'],8192)

    def test_nontext_cannot_count_as_inspected_source(self):
        result=self.deliver([{'type':'image','data':'fictional','mimeType':'image/png'}])
        self.assertFalse(result['record']['complete']);self.assertTrue(result['record']['unsupported']);self.assertTrue(result['out']['isError'])
