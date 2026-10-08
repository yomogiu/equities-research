import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
spec = importlib.util.spec_from_file_location('counter', Path(__file__).resolve().parents[1]/'scripts/count_prompt_tokens.py')
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)

class CounterTests(unittest.TestCase):
    def test_unmapped_model_requires_explicit_choice(self):
        tk = Mock(); tk.encoding_for_model.side_effect = KeyError('unknown')
        with self.assertRaisesRegex(ValueError, 'no tiktoken mapping'): c.select_encoding(tk, 'unknown')
        tk.get_encoding.assert_not_called()

    def test_explicit_encoding_is_labelled(self):
        tk = Mock()
        _, label = c.select_encoding(tk, 'unknown', 'o200k_base')
        self.assertEqual(label, 'explicit_encoding_assumption')

    def test_exact_unicode_crlf_and_special_spellings(self):
        text = 'café\r\n<|endoftext|>'
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'prompt.txt'; p.write_bytes(text.encode())
            encoder = Mock(); encoder.encode_ordinary.return_value = [1, 2, 3]
            row = c.count_file(p, encoder)
            encoder.encode_ordinary.assert_called_once_with(text)
            self.assertEqual(row['utf8_bytes'], len(text.encode()))
            self.assertEqual(row['text_tokens'], 3)
            self.assertNotIn(text, str(row))
