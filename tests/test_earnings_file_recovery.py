import json
from pathlib import Path
import tempfile
import unittest
from research import earnings_file_recovery as recovery, earnings_mixed_runner as base

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.job=Path(self.temp.name)/'financial';(self.job/'sessions').mkdir(parents=True)
        self.q={'model':'fictional','provider':'openai-codex','max_tokens':400000};base.save(self.job/'request.json',self.q)
        base.save(self.job/'execution.json',{'status':'execution_failed','exit_code':1,'request_sha256':base.digest(self.q)})
        base.save(self.job/'wire.json',[{}])
        self.messages=[{'role':'user','content':[]},{'role':'assistant','model':'fictional','provider':'openai-codex','stopReason':'toolUse','usage':{'input':10,'output':2,'cacheRead':3,'cacheWrite':0,'totalTokens':15},'content':[{'type':'toolCall','name':'ipython','id':'one'}]},{'role':'toolResult','toolName':'ipython','toolCallId':'one'},{'role':'assistant','stopReason':'error','errorMessage':'role_budget','usage':{'totalTokens':0}}]
        self.write()
    def write(self):
        (self.job/'sessions/one.jsonl').write_text(''.join(json.dumps({'type':'message','message':m})+'\n' for m in self.messages))
    def test_closed_budget_stop_counts_all_measured_tokens(self):self.assertEqual(recovery.failed_usage(self.job),15)
    def test_unknown_failure_cannot_be_relaunched(self):
        self.messages[-1]['errorMessage']='timeout';self.write()
        with self.assertRaisesRegex(ValueError,'local budget'):recovery.failed_usage(self.job)
    def test_unfinished_tool_or_unmetered_turn_cannot_recover(self):
        del self.messages[2];self.write()
        with self.assertRaises(ValueError):recovery.failed_usage(self.job)
    def test_usage_cannot_be_reset(self):
        self.messages[1]['usage']['totalTokens']=0;self.write()
        with self.assertRaisesRegex(ValueError,'measured usage'):recovery.failed_usage(self.job)
