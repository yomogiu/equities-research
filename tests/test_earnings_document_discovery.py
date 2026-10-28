import unittest
from research import earnings_document_discovery as discovery, earnings_fresh_sources as fresh

BASE='https://stockanalysis.com/quote/test/FAKE/transcripts/1-q2-2040/'
def link(n,label='Download'):
    return f'<a href="https://stockanalysis.com/filings/FAKE/{n}/">{label}</a>'.encode()
def record(n,kind='report',url=None):
    return ('{fileUrl:"'+(url or f'https://files.example.test/{n}.pdf')+'",id:'+str(n)+',type:"'+kind+'"}').encode()
def financial(period='Q2 REPORT 2040'):
    return '[Page 1]\nFICTIONAL MICRO | '+period+'\nCONSOLIDATED STATEMENTS OF INCOME\nSTATEMENTS OF FINANCIAL POSITION\nSTATEMENTS OF CASH FLOWS\n'+('original evidence '*1000)


class DiscoveryTests(unittest.TestCase):
    def test_labels_never_control_eligibility_and_duplicates_collapse(self):
        body=link(1,'Download')+link(1,'Quarterly report')+link(2,'資料')
        body+=b'<a href="https://evil.test/filings/FAKE/3/">Report</a><a href="/report-data-error/">Report</a>'
        rows=discovery.candidates(body,BASE)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['labels'],['Download','Quarterly report'])

    def test_binding_uses_exact_id_independent_of_order_or_kind(self):
        body=record(11)+record(1,'new_provider_type')
        self.assertEqual(discovery.binding(body,'https://stockanalysis.com/filings/FAKE/1/')['attachment_kind'],'new_provider_type')
        for b in [record(11),record(1)+record(1,url='https://files.example.test/conflict.pdf')]:
            with self.assertRaisesRegex(ValueError,'binding'):discovery.binding(b,'https://stockanalysis.com/filings/FAKE/1/')

    def test_candidate_limit_is_explicit_not_silent_truncation(self):
        with self.assertRaisesRegex(ValueError,'limit'):discovery.candidates(b''.join(link(n) for n in range(9)),BASE)

    def test_incomplete_and_wrong_period_candidates_do_not_block_valid_document(self):
        docs={1:financial('Q1 REPORT 2040'),2:'short presentation',3:financial()}
        decisions=[]
        def fetch(url,kind):return record(int(url.strip('/').split('/')[-1])),{'sha256':'fake'}
        def inspect(row):
            text=docs[int(row['filing_id'])]
            return fresh.qualify_report(text,'Fictional Micro',(2040,2))
        selected,value=discovery.select(link(1,'Quarterly report')+link(2,'Report')+link(3,'Download'),BASE,fetch,inspect,decisions)
        self.assertEqual(selected['filing_id'],'3')
        self.assertEqual([r['status'] for r in decisions],['rejected','rejected','selected'])
        self.assertEqual(value['completeness'],'financial_statements_present')

    def test_release_can_supply_full_statements_for_ordinary_call(self):
        decisions=[]
        selected,value=discovery.select(link(1,'Whatever'),BASE,lambda *a:(record(1,'earnings_release'),{'sha256':'fake'}),
            lambda row:fresh.qualify_report(financial(),'Fictional Micro',(2040,2)),decisions)
        self.assertEqual(selected['attachment_kind'],'earnings_release')
        self.assertEqual(value['completeness'],'financial_statements_present')
        with self.assertRaises(ValueError):fresh.qualify_report('[Page 1]\nRevenue 120 100 20\n'+'evidence '*1500,'Fictional Micro',(2040,2))

    def test_metadata_failure_is_retained_and_other_attachment_is_tried(self):
        decisions=[]
        def fetch(url,kind):return (b'no exact record' if '/1/' in url else record(2)),{'sha256':'fake'}
        selected,_=discovery.select(link(1)+link(2),BASE,fetch,lambda r:'qualified',decisions)
        self.assertEqual(selected['filing_id'],'2');self.assertIn('binding',decisions[0]['reason'])

    def test_all_rejections_fail_with_no_fabricated_selection(self):
        decisions=[]
        def reject(row):raise ValueError('wrong period')
        with self.assertRaisesRegex(ValueError,'No qualifying.*wrong period'):
            discovery.select(link(1),BASE,lambda *a:(record(1),{'sha256':'fake'}),reject,decisions)
        self.assertEqual(decisions[0]['status'],'rejected')


if __name__=='__main__':unittest.main()
