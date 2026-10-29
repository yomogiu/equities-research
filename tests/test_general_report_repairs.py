"""Fictional regressions for shared release, archive and citation formats."""
from datetime import date
import copy
import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from research import earnings_release_eps as eps, earnings_pdf_valuation as valuation
from research import earnings_report_only_sources as reports, earnings_call_aliases as calls
from research import earnings_simple_runner as runner


RELEASE='''[Page 1]
Fictional Devices Inc. (NYSE: FAKE) reports full-year results.
GAAP measures and non-GAAP reconciliation.
[Page 2]
CONDENSED STATEMENTS OF INCOME
(In millions, except per-share data)
   Three Months Ended August 31,           Year Ended August 31,
             2040       2039                 2040       2039
Net sales     100         90                  400        350
Diluted earnings per share    $ 1.25    $ 1.00     $ 5.50     $ 4.00
Diluted weighted average shares 10.00    11.00       10.50      11.50
'''
SOURCE={'document_id':'fictional','sha256':'a'*64}
PRICES=[{'id':'P-fake','symbol':'FAKE','currency':'USD','date':'2040-10-28','value':'55.00','source_id':'transcript-source'}]


class GeneralRepairs(unittest.TestCase):
    def test_release_annual_column_does_not_use_quarter_or_share_count(self):
        rows=eps.extract(RELEASE,SOURCE,PRICES)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['value'],'5.50')
        self.assertEqual(rows[0]['period_end'],'2040-08-31')
        self.assertEqual(rows[0]['text'],RELEASE[rows[0]['start']:rows[0]['end']])
        self.assertEqual(valuation.unique_pair({'prices':PRICES,'annual_eps':rows})['eps_id'],rows[0]['id'])
    def test_release_rejects_quarter_only_adjusted_ambiguous_and_foreign_units(self):
        for text in [RELEASE.replace('Year Ended','Six Months Ended'),
                     RELEASE.replace('Diluted earnings per share','Adjusted diluted earnings per share'),
                     RELEASE.replace('2040       2039\nNet sales','2039       2040\nNet sales'),
                     RELEASE.replace('(In millions','(In Canadian dollars, millions'),
                     RELEASE.replace('NYSE: FAKE','NYSE: OTHER'),RELEASE.replace('NYSE: FAKE','NYSE: FAKE ADR'),
                     RELEASE.replace('GAAP measures','IFRS measures')]:
            self.assertEqual(eps.extract(text,SOURCE,PRICES),[],text)
    def test_release_kind_enters_bound_supplemental_inventory(self):
        from research import earnings_valuation_inventory as inventory,earnings_runtime_common as storage
        with TemporaryDirectory() as temporary:
            root=Path(temporary);raw=root/'original.pdf';raw.write_bytes(b'%PDF fictional original')
            text=root/'original.txt';text.write_text(RELEASE)
            call=root/'call.txt';call.write_text('NYSE: FAKE · Real-Time Price · USD\nDisplay\n55.00\nChange\nAt close: Oct 28, 2040, 4:00 PM EDT\nEarnings Call: Q4 2040\n')
            sources=[{'document_id':'fictional','kind':'release','representation':rep,'path':str(p),'sha256':storage.sha(p)} for rep,p in [('raw',raw),('text',text)]]
            sources.append({'document_id':'call','kind':'transcript','representation':'text','path':str(call),'sha256':storage.sha(call),'url':'https://stockanalysis.com/stocks/fake/transcripts/123-q4-2040/'})
            result=inventory.build({'manifest':{'sources':sources}})
            self.assertEqual([r['value'] for r in result['annual_eps']],['5.50'])
    def test_archive_context_combines_only_one_original_report_card(self):
        body='''<main><article><a href="first.pdf"><h2>2040</h2></a><p>Q1 Consolidated Report</p><a href="first.pdf">DOWNLOAD</a></article>
        <article><a href="second.pdf">2040</a><p>Q2 Consolidated Report</p><a href="second.pdf">DOWNLOAD</a></article></main>'''
        row=reports.candidates(body.encode(),'https://issuer.example/archive',date(2040,10,28))
        self.assertEqual(row['url'],'https://issuer.example/second.pdf');self.assertIn('label_evidence',row)
        evidence=row['label_evidence'];self.assertEqual(evidence['raw_span_sha256'],hashlib.sha256(body[evidence['start']:evidence['end']].encode()).hexdigest())
        with self.assertRaisesRegex(ValueError,'No dated'):
            reports.candidates(b'<main><div>2040</div><article><a href="x.pdf">DOWNLOAD</a><p>Q2 Consolidated Report</p></article><a href="other.pdf">Other</a></main>', 'https://issuer.example/archive',date(2040,10,28))
        with self.assertRaisesRegex(ValueError,'Ambiguous'):
            reports.candidates((body+'<article><h2>2040</h2><p>Q2 Consolidated Report</p><a href="different.pdf">DOWNLOAD</a></article>').encode(),'https://issuer.example/archive',date(2040,10,28))
    def test_report_only_english_original_calendar_endpoint_is_required(self):
        text='[Page 1]\nFICTIONAL DEVICES\nFOR THE SIX MONTHS ENDED JUNE 30, 2040\nBalance Sheets\nStatements of Income\nCash Flows\n'+'Original note '*1000
        event={'year':2040,'quarter':2,'end':'2040-06-30'}
        self.assertEqual(reports.qualify(text,{'issuer_name':'FICTIONAL DEVICES'},event)['language'],'English')
        with self.assertRaisesRegex(ValueError,'heading'):
            reports.qualify(text,{'issuer_name':'FICTIONAL DEVICES'},{**event,'end':'2040-09-30'})
    def test_split_page_headers_are_exact_and_new_statements_do_not_inherit(self):
        from research import earnings_pdf_tables as pdf
        previous='[Page 1]\nFICTIONAL CONSOLIDATED BALANCE SHEETS\n(In millions)\nDecember 31, 2040 and 2039\nCash                  40           30\nReceivables           12           10\n'
        current='[Page 2]\nLiabilities           20           15\nDebt                  10            8\nEquity                22           17\n'
        text=previous+current
        rows=pdf.continuation_header(text,9,len(previous),len(text))
        self.assertEqual(len(rows),1);self.assertIn('December 31, 2040',rows[0]['text']);self.assertNotIn('Cash ',rows[0]['text'])
        self.assertEqual(rows[0]['text'],text[rows[0]['start']:rows[0]['end']])
        self.assertEqual(rows[0]['raw_span_sha256'],hashlib.sha256(rows[0]['text'].encode()).hexdigest())
        tables=pdf.tables(text,SOURCE);second=next(t for t in tables if t['ordinal']==2)
        rendered='\n'.join(pdf.render({**second,'selected_row_ids':['R1','R2','R3']}))
        self.assertIn('December 31, 2040',rendered);self.assertIn('(In millions)',rendered)
        fresh='[Page 2]\nFICTIONAL CONSOLIDATED INCOME STATEMENTS\n(In thousands)\nYear ended 2040\nRevenue           100           90\nCosts              60           55\n'
        self.assertEqual(pdf.continuation_header(previous+fresh,9,len(previous),len(previous+fresh)),[])
        unrelated='[Page 1]\nShares issued (in thousands)           100           90\n'
        self.assertEqual(pdf.continuation_header(unrelated+current,9,len(unrelated),len(unrelated+current)),[])
        undated='[Page 1]\n(In thousands)\nCurrency             Rate             Value\nUSD                   30                100\n'
        self.assertEqual(pdf.continuation_header(undated+current,9,len(undated),len(undated+current)),[])
        orphan=previous+'FICTIONAL Reconciliation of adjusted measures\n(In millions except per-share data)   Three Months Ended August 31,\n'
        rows=pdf.continuation_header(orphan+current,9,len(orphan),len(orphan+current))
        self.assertEqual(len(rows),1);self.assertIn('Three Months Ended',rows[0]['text']);self.assertNotIn('BALANCE SHEETS',rows[0]['text'])

    def test_selected_source_notes_are_rendered_without_numeric_reinterpretation(self):
        from research import earnings_financial_analysis_report as finance
        value={'financial_selection':{'rows':[],'notes':[{'text':'Fictional balances are in millions as at June 30.','citations':['document-source-fake']}]}}
        with __import__('unittest.mock',fromlist=['patch']).patch.object(finance,'front_rows',return_value={'cash':[],'earnings':[],'demand':[],'outlook':[]}):
            notes=finance.notes(value)
        self.assertIn('- Fictional balances are in millions as at June 30. [^document-source-fake]',notes)

    def test_report_only_packet_does_not_advertise_a_transcript_scope(self):
        known={'D001','F001','document-source-fictional'}
        self.assertEqual(runner.source_availability(known),{'transcript_present':False,'document_citation_ids':['document-source-fictional'],'call_citation_id':None})
        self.assertEqual(runner.source_availability(known|{'transcript-source'})['call_citation_id'],'transcript-source')

    def test_call_aliases_are_exact_and_do_not_modify_original_payload_or_prose(self):
        turn='turn-'+'a'*24;exchange='exchange-'+'b'*24
        bundle={'transcript_index':{'turns':[{'id':turn}],'exchanges':[{'id':exchange}]},'packet_inventory':{'tables':[]},'manifest':{'sources':[]}}
        raw={'qa':[{'exchange_id':exchange,'citations':[turn,exchange]}],'text':'Original '+turn}
        projected=calls.project(raw,bundle)
        self.assertEqual(raw['qa'][0]['exchange_id'],exchange)
        self.assertEqual(projected['qa'][0],{'exchange_id':'QA1','citations':['CALL1','QA1']})
        self.assertEqual(projected['text'],raw['text'])
        candidate='Claim [^'+turn+'] and Q&A [^'+exchange+']. Unknown [^turn-unknown].'
        snapshot=candidate
        bindings=calls.compiled_bindings(candidate,bundle)
        self.assertEqual(bindings,[{'address':'CALL1','canonical_id':turn},{'address':'QA1','canonical_id':exchange}])
        self.assertEqual(candidate,snapshot)
        self.assertEqual(calls.compiled_bindings('No citations',bundle),[])

        restored,changes=runner.resolve_citations(projected,bundle,{turn,exchange})
        self.assertEqual(restored,raw);self.assertTrue(changes)
        changed,_=runner.resolve_citations({'citations':['CALL9','turn-'+'c'*24]},bundle,{turn,exchange})
        self.assertEqual(changed['citations'],['CALL9','turn-'+'c'*24])


if __name__=='__main__':unittest.main()
