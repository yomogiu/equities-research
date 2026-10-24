"""Frozen fictional render bytes and a workflow-free renderer import boundary."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

from research import earnings_markdown as compatibility
from research import earnings_markdown_render as renderer


SAMPLES = [
    '# Fictional <company>\n\n## A finding\n\nRevenue & costs. [^F001]\n\n- qualification\n\n> Exact <words>\n\n| Metric | Unit / basis | Current |\n| --- | --- | --- |\n| Revenue | USD | 12 [^F001] |\n\n[^F001]: Original fictional evidence\n',
    '# Fictional comparison\n\n| Metric | Current | Prior |\n| --- | --- | --- |\n| Revenue | 12 | 10 |\n',
]
# Captured from the original renderer before extracting these helpers.
HASHES = [
    ('591a25a7a2c3fffa11b8a2db4ef09a0e8d4d893103fd218d10f37d86af508a72',
     '795505e532f3fa86aad48c31ec26e1f88aa0e4276858ffd0cba167f0064ac7d9'),
    ('2c20360e522bc5c0731047d4db06203c68eefbd07d5f6b0d1dd0a67efa883121',
     'f11c530347a879a9d584a109b074b142e8944f7c5115ea933e7c3f687be957fb'),
]


class MarkdownRenderTests(unittest.TestCase):
    def test_frozen_escaped_tables_citations_and_status_bytes(self):
        for sample, hashes in zip(SAMPLES, HASHES):
            for status, expected in zip(('draft', 'accepted'), hashes):
                with self.subTest(status=status, sample=sample[:25]):
                    actual = renderer.render(sample, status=status)
                    self.assertEqual(hashlib.sha256(actual.encode()).hexdigest(), expected)
                    self.assertEqual(compatibility.render(sample, status=status), actual)

    def test_compatibility_exports_use_the_same_neutral_helpers(self):
        for name in ('cell', 'refs', 'quote_markdown', 'inline', 'split_row', 'render'):
            self.assertIs(getattr(compatibility, name), getattr(renderer, name))

    def test_renderer_import_and_table_render_do_not_load_workflow_modules(self):
        code = """import json, sys
from research import earnings_markdown_render as renderer
renderer.render('# Fictional\\n\\n| Metric | Current | Prior |\\n| --- | --- | --- |\\n| Revenue | 12 | 10 |\\n')
print(json.dumps(sorted(name for name in sys.modules if name.startswith('research.'))))
"""
        completed = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
                                   capture_output=True, text=True, check=True)
        self.assertEqual(set(json.loads(completed.stdout)), {
            'research.earnings_markdown_render', 'research.earnings_visual_signals'})


if __name__ == '__main__': unittest.main()
