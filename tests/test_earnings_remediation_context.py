"""Explicit complete-source remediation editions retain history and review gates."""
import copy
from pathlib import Path
from unittest.mock import patch
from test_earnings_remediation import RemediationTests
from research import earnings_remediation as m, earnings_review_policy as rp
from research import earnings_experiment as b

class ContextEditionTests(RemediationTests):
    def policy(self):
        return {'version':rp.VERSION,**rp.LIMITS,'authorization':'Explicit synthetic complete-source edition',
                'token_authorization':'Explicit synthetic uncapped token authority'}

    def context_edition(self):
        old=self.edition(attempts=1);a=b.read(old/'authorization.json');p=b.read(old/'attempts/0/plan.json')
        out=self.root/'context-edition';a.update(output_path=str(out),max_tokens=None,review_context_policy=self.policy())
        m.initialize(self.seed,out,p,a)
        return out,old

    def test_new_context_edition_preserves_source_history_and_acceptance(self):
        out,old=self.context_edition();p,bu,ca,w=m.load(out)
        self.assertEqual(p['history'],b.read(old/'protocol.json')['history'])
        self.assertEqual(b.read(out/'initial.json'),b.read(old/'initial.json'))
        self.assertEqual(p['max_review_attempts'],1);self.assertIsNone(p['max_tokens'])
        self.assertEqual(p['max_prompt_chars'],550000)
        result=self.complete(out);result['receipt']['session']['usage']['totalTokens']=700001
        with patch.object(m,'verify_job',return_value=result):
            self.assertEqual(m.advance(out)['status'],'accepted')
        self.assertEqual(b.read(out/'result.json')['tokens'],700001)
        self.assertEqual(b.read(old/'protocol.json')['max_tokens'],600000)

    def test_blank_unknown_or_unbound_policy_rejected(self):
        out,old=self.context_edition();a=b.read(out/'authorization.json')
        for key,value in [('authorization',''),('token_authorization',''),('context_characters',500001),('version','unknown')]:
            wrong=copy.deepcopy(a);wrong['review_context_policy'][key]=value
            with self.assertRaises(ValueError):m.context_policy(wrong)
        wrong=copy.deepcopy(a);wrong['max_tokens']=600000
        with self.assertRaises(ValueError):m.context_policy(wrong)
        p=b.read(out/'protocol.json');p.pop('review_context_policy');(out/'protocol.json').write_text(__import__('json').dumps(p))
        with self.assertRaisesRegex(ValueError,'context authority'):m.load(out)

    def test_uncapped_requires_explicit_policy(self):
        out=self.edition();a=b.read(out/'authorization.json');a['max_tokens']=None
        with self.assertRaises(ValueError):m._authorization(a,self.seed,b.read(out/'attempts/0/plan.json'),out)

    def test_full_review_loop_receives_bound_policy(self):
        out,_=self.context_edition();p,bu,ca,w=m.load(out)
        original=m.corrections.replay_review
        with patch.object(m.corrections,'replay_review',wraps=original) as review:
            result=m._replay(out,p,bu,ca,w)
        self.assertEqual(result['status'],'pending')
        self.assertEqual(review.call_args.args[0],self.policy())
        self.assertIn('EXPLICIT USER-DIRECTED REMEDIATION EDITION',result['prompt'])
