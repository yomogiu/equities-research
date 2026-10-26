import unittest,tempfile
from datetime import date
from pathlib import Path
from research import earnings_fresh_sources as fresh
from research import earnings_pdf_tables as pdf
from research import earnings_packet_inventory as inventory
from research import financial_evidence as financial

class FreshSourcesTests(unittest.TestCase):
    def test_latest_completed_ordinary_event_not_post_call_or_other_issuer(self):
        base='https://stockanalysis.com/quote/test/FAKE/transcripts/'
        body=(''.join('<a href="'+base+v+'">call</a>' for v in ['1-q1-2040/','2-q2-2040/','3-q2-2040-post-call/','4-q3-2040/'])+
              '<a href="https://stockanalysis.com/quote/test/OTHER/transcripts/5-q2-2040/">other</a>').encode()
        self.assertEqual(fresh.current_calls(body,base,date(2040,7,20)),((2040,2),base+'2-q2-2040/'))
    def test_ambiguous_current_period_does_not_select_arbitrarily(self):
        base='https://stockanalysis.com/quote/test/FAKE/transcripts/'
        body=(''.join('<a href="'+base+v+'">call</a>' for v in ['1-q2-2040/','2-q2-2040/'])).encode()
        with self.assertRaisesRegex(ValueError,'Ambiguous'):fresh.current_calls(body,base,date(2040,7,20))
    def test_filing_selection_is_exact_id_not_first_pdf(self):
        body=b'{id:1,type:"quarterly_report",fileUrl:"https://files.example.test/wrong.pdf"},{id:2,type:"quarterly_report",fileUrl:"https://files.example.test/right.pdf"}'
        self.assertEqual(fresh.filing_url(body,'https://example.test/filings/FAKE/2/'),'https://files.example.test/right.pdf')
        with self.assertRaises(ValueError):fresh.filing_url(body,'https://example.test/filings/FAKE/3/')
    def test_qualification_requires_issuer_period_and_statements(self):
        good='[Page 1]\nFICTIONAL MICRO | Q2 REPORT 2040\nIncome statement\nStatement of financial position\nCash flow\n'+('original text '*1000)
        self.assertEqual(fresh.qualify_report(good,'Fictional Micro',(2040,2))['issuer_and_period'],'explicit_cover_match')
        for text,issuer,period in [(good,'Other',(2040,2)),(good,'Fictional Micro',(2040,1)),(good.replace('Cash flow','Other'),'Fictional Micro',(2040,2))]:
            with self.assertRaises(ValueError):fresh.qualify_report(text,issuer,period)
    def test_pdf_sparse_rows_keep_original_positions_and_hashes(self):
        text='[Page 1]\nStatement\nAmounts USD thousand\n'+f'{"":25}{"2040":>12}{"2039":>12}\n'
        for label,a,b in [('Revenue','120 000','100 000'),('Cost','-80 000','-70 000'),('Profit','40 000','30 000'),('Optional','','10')]:
            text+=f'{label:25}{a:>12}{b:>12}\n'
        source={'document_id':'fictional','sha256':financial.digest(text.encode())}
        tables=pdf.tables(text,source);self.assertEqual(len(tables),1)
        cells=tables[0]['cells'];rev=next(c for c in cells if c['text']=='100 000');optional=next(c for c in cells if c['text']=='10')
        self.assertEqual(rev['column'],optional['column'])
        for c in cells:self.assertEqual(c['raw_span_sha256'],financial.digest(text[c['start']:c['end']].encode()))
    def test_single_digit_notes_and_dash_cells_remain_separate(self):
        text='[Page 1]\nAmounts USD thousand\n'
        for label,note,a,b in [('Revenue','4','120 000','100 000'),('Cost','','-80 000','-70 000'),('Profit','','40 000','30 000'),('Other','6','—','-96')]:
            text+=f'{label:25}{note:>8}{a:>12}{b:>12}\n'
        t=pdf.tables(text,{'document_id':'fictional','sha256':financial.digest(text.encode())})[0]
        self.assertTrue(any(c['text']=='4' for c in t['cells']))
        self.assertTrue(any(c['text']=='—' for c in t['cells']))
        self.assertFalse(any(c['text']=='4   120 000' for c in t['cells']))
        picks=[{'table_id':t['id'],'row_ids':[r['id'] for r in t['rows']],'section':'earnings'}]
        selected=inventory.selected(picks,{'packet_inventory':{'tables':[t]}})
        rendered='\n'.join(inventory.render_compact(selected[0]))
        self.assertIn('120 000',rendered);self.assertIn('USD thousand',rendered)

    def test_pdf_text_must_bind_original_and_reject_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=root/'source.pdf';raw.write_bytes(b'%PDF\xfforiginal')
            txt=root/'text.txt';txt.write_text('[Page 1]\nA    10    20\nB    30    40\nC    50    60\n')
            sources=[{'document_id':'fake','kind':'filing','representation':'raw','path':str(raw),'sha256':financial.digest(raw.read_bytes())},
                     {'document_id':'fake','kind':'filing','representation':'text','path':str(txt),'sha256':financial.digest(txt.read_bytes()),'extraction':'pdftotext-layout-v1','derived_from_sha256':financial.digest(raw.read_bytes())}]
            self.assertEqual(inventory.build(sources)['coverage'][0]['status'],'pdf_positional_tables')
            txt.write_text('changed')
            with self.assertRaisesRegex(ValueError,'PDF text source changed'):inventory.build(sources)

if __name__=='__main__':unittest.main()
