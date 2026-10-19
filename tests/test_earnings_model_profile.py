import copy
import unittest
from research import earnings_file_pipeline as p
class ProfileTests(unittest.TestCase):
    def test_explicit_original_routes_without_default_mutation(self):
        default=p.profile_models(None);old=p.profile_models(p.ORIGINAL_MODEL_PROFILE)
        self.assertEqual(old['analysis'],['gpt-6-luna','max']);self.assertEqual(old['correction'],['gpt-6-luna','max'])
        self.assertEqual(old['review'],['gpt-6.1-sol','medium']);old['review'][0]='changed'
        self.assertEqual(p.profile_models(None),default);self.assertNotEqual(old,p.profile_models(p.ORIGINAL_MODEL_PROFILE))
    def test_frozen_assignment_and_new_request_only(self):
        protocol={'model_profile':p.ORIGINAL_MODEL_PROFILE,'models':p.profile_models(p.ORIGINAL_MODEL_PROFILE)}
        self.assertTrue(p.validate_profile(protocol));self.assertFalse(p.validate_profile({'models':p.profile_models(None)}))
        for role in protocol['models']:
            v=copy.deepcopy(protocol);v['models'][role][1]='low' if v['models'][role][1]!='low' else 'max'
            with self.subTest(role=role),self.assertRaises(ValueError):p.validate_profile(v)
        for field in ('preparation_path','analysis_preparation_path','review_preparation_path','signal_preparation_path','recovery_path'):
            with self.subTest(field=field),self.assertRaises(ValueError):p.validate_profile({**protocol,field:'existing-work'})
    def test_unknown_profiles_rejected(self):
        for profile in ('custom',{},False,1):
            with self.assertRaises(ValueError):p.profile_models(profile)
