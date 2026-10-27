"""Byte-stable primitives shared by current and historical signed-in runners."""
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

from research import earnings_runtime_common as common
from research import earnings_mixed_runner as legacy


class RuntimeCommonTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()

    def test_legacy_receipts_keep_exact_whitespace_sensitive_digest(self):
        value={'b':'café','a':[1,2]}
        exact='{"a": [1, 2], "b": "café"}'.encode()
        self.assertEqual(common.digest(value),hashlib.sha256(exact).hexdigest())
        self.assertNotEqual(common.digest(value),hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())
        for name in ('digest','sha','read','save','_inside','_text','parse_response','_runtime_paths','_validate_selection'):
            self.assertIs(getattr(legacy,name),getattr(common,name))
        with self.assertRaises(ValueError):common.digest({'value':float('nan')})

    def test_exclusive_write_preserves_bytes_permissions_and_existing_receipt(self):
        path=self.root/'receipt.json';value={'token':'fictional','text':'café'}
        common.save(path,value)
        self.assertEqual(path.read_bytes(),(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
        self.assertEqual(common.read(path),value)
        with self.assertRaises(FileExistsError):common.save(path,{'replacement':True})
        self.assertEqual(common.read(path),value)

    def test_containment_rejects_parent_escape_and_symlinks(self):
        self.assertEqual(common._inside(self.root,'receipt.json'),self.root/'receipt.json')
        with self.assertRaises(ValueError):common._inside(self.root,'../escape.json')
        target=self.root/'target.json';target.write_text('{}');(self.root/'alias.json').symlink_to(target)
        with self.assertRaises(ValueError):common._inside(self.root,'alias.json')

    def test_immutable_text_allows_exact_repeat_but_not_different_content(self):
        path=self.root/'nested/report.md';common.immutable_text(path,'Fictional report\n')
        common.immutable_text(path,'Fictional report\n')
        with self.assertRaises(ValueError):common.immutable_text(path,'Changed report\n')
        self.assertEqual(path.read_text(),'Fictional report\n')

    def test_exact_model_and_response_validation_is_unchanged(self):
        common._validate_selection('gpt-6.1-sol','medium')
        for selection in [('unknown','medium'),('gpt-6.1-sol','max')]:
            with self.assertRaises(ValueError):common._validate_selection(*selection)
        self.assertEqual(common._text({'content':[{'type':'text','text':'one'},{'type':'text','text':'two'}]}),'onetwo')
        with self.assertRaises(ValueError):common._text({'content':[{'type':'toolCall'}]})
        self.assertEqual(common.parse_response('```json\n{"ok":true}\n```'),{'ok':True})
        with self.assertRaises(ValueError):common.parse_response('[]')

    def test_neutral_module_imports_no_report_workflow(self):
        code='''import sys
from research import earnings_runtime_common
for name in sys.modules:
    assert not name.startswith(('research.earnings_mixed_runner','research.earnings_file_pipeline','research.earnings_mixed_pipeline','research.earnings_experiment')), name
'''
        result=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).parents[1],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
