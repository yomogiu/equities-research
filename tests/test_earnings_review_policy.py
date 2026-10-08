import copy
import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from research import earnings_review_policy as p, earnings_repair_context as c, earnings_experiment as b

class ContextPolicyTests(unittest.TestCase):
    def test_larger_complete_payload_roundtrips_and_default_restores(self):
        value={'unique_source':'x'*350000}
        with self.assertRaises(c.ContextTooLarge):c._bounded(value)
        with c.authorized_limits({'version':p.VERSION,**p.LIMITS}):
            self.assertGreater(c._bounded(value),330000)
            self.assertEqual(c.expand_context(c.compact_context(value)),value)
        with self.assertRaises(c.ContextTooLarge):c._bounded(value)
    def test_parallel_workers_do_not_share_policy(self):
        value={'original':'x'*350000}
        def default():
            with self.assertRaises(c.ContextTooLarge):c._bounded(value)
        with c.authorized_limits({'version':p.VERSION,**p.LIMITS}):
            with ThreadPoolExecutor(1) as pool:pool.submit(default).result()
            self.assertGreater(c._bounded(value),330000)
    def test_policy_source_rounds_and_usage_bound(self):
        with tempfile.TemporaryDirectory() as d:
            seed=Path(d).resolve();(seed/'protocol.json').write_text('{}');path=seed/'authorization.json'
            exported={'used_rounds':1,'spent_tokens':123}
            v={'version':p.VERSION,'seed':str(seed),'seed_protocol_sha256':b.sha(seed/'protocol.json'),
               'model':['gpt-6.1-sol','medium'],'limits':p.LIMITS,'preserve_source_bytes':True,'preserve_rounds':True,
               'prior_rounds':1,'inherited_tokens':123,'authorization':'Explicit complete-context continuation','token_ceiling':None,'token_authorization':'User explicitly removed token ceiling; retain usage and rounds'}
            path.write_text(json.dumps(v));self.assertEqual(p.read(path,seed,exported)['context_characters'],500000)
            for key,value in [('prior_rounds',0),('inherited_tokens',0),('preserve_source_bytes',False),('authorization',''),('token_authorization',''),('token_ceiling',600000),('seed_protocol_sha256','wrong')]:
                changed=copy.deepcopy(v);changed[key]=value;path.write_text(json.dumps(changed))
                with self.assertRaises(ValueError):p.read(path,seed,exported)
    def test_arbitrary_limit_rejected_and_exception_restores_default(self):
        with self.assertRaises(ValueError):
            with c.authorized_limits({'version':p.VERSION,'context_characters':999999999,'prompt_characters':550000}):pass
        with self.assertRaises(RuntimeError):
            with c.authorized_limits({'version':p.VERSION,**p.LIMITS}):raise RuntimeError('fake')
        with self.assertRaises(c.ContextTooLarge):c._bounded({'x':'a'*350000})

    def test_outer_review_replay_carries_policy_to_evidence_expansion(self):
        from unittest.mock import patch
        from research import earnings_corrections as corrections
        def expansion(*args,**kwargs):return c._bounded({'source':'x'*350000})
        with patch.object(corrections.review_loop,'replay',side_effect=expansion):
            self.assertGreater(corrections.replay_review({'version':p.VERSION,**p.LIMITS}),330000)
            with self.assertRaises(c.ContextTooLarge):corrections.replay_review(None)
