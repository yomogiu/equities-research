"""Synthetic contract checks for versioned concise-report prompts."""
from pathlib import Path
import tempfile
import unittest
from research import earnings_experiment as base
from research import earnings_native as native
from test_earnings_experiment import make_case

class WritingStandardTests(unittest.TestCase):
    def test_frozen_policy_reaches_all_five_roles_in_both_runtimes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); path,case=make_case(root)
            standard=root/'standard.md';standard.write_text('Fictitious rule: preserve material unanswered questions.')
            case['writing_standard_path']=str(standard)
            with self.assertRaisesRegex(ValueError, 'not frozen'):base.validate_case(case)
            case['artifacts'].append({'path':str(standard),'sha256':base.sha(standard)})
            base.validate_case(case)
            for role in ('extractor','commentator','reviewer','editor','final_reviewer'):
                prompt=base.role_prompt(role,path,case,{},0)
                self.assertIn(standard.read_text(),prompt)
                self.assertEqual(prompt,native.role_prompt(role,path,case,{},0))
            standard.write_text('Changed policy')
            with self.assertRaisesRegex(ValueError,'Frozen input changed'):base.validate_case(case)
