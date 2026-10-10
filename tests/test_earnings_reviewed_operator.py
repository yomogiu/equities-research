import unittest
from unittest.mock import patch
from research import earnings_reviewed_operator as m
class OperatorTests(unittest.TestCase):
 def test_source_binding_fails_closed(self):
  with patch.object(m.r,'read',return_value={}),patch.object(m.r,'sha',return_value='changed'):
   with self.assertRaisesRegex(ValueError,'reservation'):m.apply({'reservation':'fake','reservation_sha256':'original'}, {}, {}, {})
 def test_prompt_binding_fails_closed(self):
  with patch.object(m.r,'read',side_effect=[{'bindings':{'x':1},'prompt_sha256':'p'},{'bindings':{'x':2}}]),patch.object(m.r,'sha',return_value='original'),patch.object(m.imp,'authenticate',return_value={}):
   with self.assertRaisesRegex(ValueError,'request'):m.apply({'reservation':'fake','reservation_sha256':'original','review':{'job':'fake'}},{},{},{})
