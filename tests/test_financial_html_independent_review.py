"""Independent synthetic checks for exact reviewed-cell arithmetic."""
import unittest
from decimal import Decimal, localcontext
from research import financial_html_tables as adapter

class ReviewedCellPrecisionTests(unittest.TestCase):
 def test_parentheses_do_not_round_decimal_before_reviewed_scale(self):
  digits='12345678901234567890123456789.12'
  self.assertEqual(adapter._number('('+digits+')',0),'-'+digits)
  with localcontext() as context:
   context.prec=60
   expected=Decimal('-'+digits)*Decimal(10)**6
  self.assertEqual(Decimal(adapter._number('('+digits+')',6)),expected)
 def test_signed_source_value_and_fractional_scale_remain_exact(self):
  self.assertEqual(adapter._number('-12345678901234567890123456789.12',-2),'-123456789012345678901234567.8912')

if __name__=='__main__':unittest.main()
