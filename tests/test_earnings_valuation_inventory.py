"""Fictitious frozen filings: annual EPS and listed class binding, no live sources."""
import tempfile,unittest
from pathlib import Path
from research import earnings_valuation_inventory as inv,earnings_runtime_common as storage

class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.raw='''<html><xbrli:context id="annual"><xbrli:entity><xbrli:identifier scheme="fake">123</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2040-01-01</xbrli:startDate><xbrli:endDate>2040-12-31</xbrli:endDate></xbrli:period></xbrli:context><xbrli:unit id="u"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit><ix:nonNumeric name="dei:TradingSymbol" contextRef="annual">FAKE</ix:nonNumeric><table><tr><td>Diluted EPS</td><td><ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="annual" unitRef="u" decimals="2">2.00</ix:nonFraction></td></tr></table></html>'''
        self.quote='Fictional Corporation\nNYSE: FAKE · Real-Time Price · USD\nFull Chart Watchlist\n48.00\n+1.00 (2%)\nJan 2, 2041, 4:00 PM EST - Market closed\nEarnings Call: Q4\n'
    def bundle(self):
        sources=[]
        for name,kind,rep,text,url in [('annual.html','filing','raw',self.raw,'https://example.test/filing'),('quote.txt','transcript','text',self.quote,'https://stockanalysis.com/stocks/fake/transcripts/example/')]:
            p=self.root/name;p.write_text(text);sources.append({'document_id':name,'kind':kind,'representation':rep,'path':str(p),'sha256':storage.sha(p),'url':url})
        return {'manifest':{'sources':sources}}
    def test_annual_eps_and_price_are_reparsed_with_source_support(self):
        b=self.bundle();v=inv.build(b);self.assertEqual(len(v['prices']),1);self.assertEqual(len(v['annual_eps']),1)
        e=v['annual_eps'][0];self.assertEqual(e['value'],'2.00');self.assertEqual(e['symbol'],'FAKE');self.assertTrue(e['observations'][0]['support']['raw_span_sha256'])
        result=inv.resolve({'price_id':v['prices'][0]['id'],'eps_id':e['id'],'accounting_basis':'GAAP'},b)
        self.assertEqual(result['eps']['period_start'],'2040-01-01')
    def test_quarterly_eps_not_annualized(self):
        self.raw=self.raw.replace('2040-01-01','2040-10-01');self.assertEqual(inv.build(self.bundle())['annual_eps'],[])
    def test_unknown_quote_format_or_wrong_symbol_not_invented(self):
        self.quote=self.quote.replace('NYSE: FAKE','NYSE: WRONG');self.assertEqual(inv.build(self.bundle())['prices'],[])
    def test_ambiguous_filed_symbol_excluded(self):
        self.raw=self.raw.replace('</html>','<ix:nonNumeric name="dei:TradingSymbol" contextRef="annual">OTHER</ix:nonNumeric></html>')
        self.assertEqual(inv.build(self.bundle())['annual_eps'],[])
    def test_cached_source_tampering_fails(self):
        b=self.bundle();inv.build(b);(self.root/'annual.html').write_text('changed')
        with self.assertRaisesRegex(ValueError,'source changed'):inv.build(b)
    def test_duplicate_equal_facts_coalesce_with_both_lineages(self):
        node='<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="annual" unitRef="u" decimals="2">2.00</ix:nonFraction>'
        self.raw=self.raw.replace(node,node+node);v=inv.build(self.bundle());self.assertEqual(len(v['annual_eps']),1);self.assertEqual(len(v['annual_eps'][0]['observations']),2)

    def test_explicit_at_close_header_preserves_close_not_after_hours(self):
        self.quote=self.quote.replace('Jan 2, 2041, 4:00 PM EST - Market closed','At close: Jan 2, 2041, 4:00 PM EST\n49.99\n+1.99 (4%)\nAfter-hours: Jan 2, 2041, 7:48 PM EST')
        v=inv.build(self.bundle());self.assertEqual(len(v['prices']),1)
        self.assertEqual(v['prices'][0]['value'],'48.00');self.assertEqual(v['prices'][0]['date'],'2041-01-02')

    def test_after_hours_only_header_is_not_accepted_as_close(self):
        self.quote=self.quote.replace('Jan 2, 2041, 4:00 PM EST - Market closed','After-hours: Jan 2, 2041, 7:48 PM EST')
        self.assertEqual(inv.build(self.bundle())['prices'],[])

    def test_undesignated_intraday_timestamp_is_not_promoted_to_close(self):
        self.quote=self.quote.replace('4:00 PM EST - Market closed','2:00 PM EST')
        self.assertEqual(inv.build(self.bundle())['prices'],[])
