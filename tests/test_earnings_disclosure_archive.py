"""Fictional archive records and guidance quotes; no real companies or requests."""
from datetime import date,datetime,timezone
import json,tempfile,unittest
from pathlib import Path
from research import earnings_disclosure_archive as archive,earnings_report_only_sources as report
from research import earnings_valuation_inventory as valuation
from research.fetch import Client


class ArchiveTests(unittest.TestCase):
    def test_issuer_linked_exchange_discovery_retains_actual_downloads(self):
        url='https://issuer.example/reports';linked='https://www.cninfo.com.cn/new/disclosure/stock?stockCode=001234&orgId=1234567'
        body=('<a href="'+linked+'">More disclosures</a>').encode();calls=[]
        row={'secCode':'001234','orgId':'1234567','announcementTime':int(datetime(2040,10,20,tzinfo=timezone.utc).timestamp()*1000),
             'announcementTitle':'2040年三季度报告','adjunctUrl':'finalpage/2040-10-20/123456789.PDF'}
        def fetch(u,kind,**kwargs):
            calls.append((u,kind,kwargs))
            return (b'var plate = "szse";' if u==linked else json.dumps({'announcements':[row]}).encode()),{}
        html,source=archive.discover(body,url,date(2040,10,28),fetch)
        chosen=report.candidates(html,source,date(2040,10,28))
        self.assertEqual(chosen['quarter'],3)
        self.assertEqual(chosen['url'],'https://static.cninfo.com.cn/finalpage/2040-10-20/123456789.PDF')
        self.assertEqual(calls[1][2]['form']['stock'],'001234,1234567')
        row['secCode']='009999'
        with self.assertRaisesRegex(ValueError,'another issuer'):archive.discover(body,url,date(2040,10,28),fetch)

    def test_simplified_chinese_reports_exclude_forecasts_and_summaries(self):
        html='<a href="/q3.pdf">2040年第三季度报告</a><a href="/half.pdf">2040年半年度报告</a><a href="/summary.pdf">2040年三季度报告摘要</a><a href="/forecast.pdf">2040年前三季度业绩预告</a>'
        chosen=report.candidates(html.encode(),'https://issuer.example/',date(2040,10,28))
        self.assertEqual(chosen['url'],'https://issuer.example/q3.pdf')
        text='[Page 1]\n虚构股份有限公司\n2040年第三季度报告\n资产负债表\n利润表\n现金流量表\n'+'财务报告 '*4000
        value=report.qualify(text,{'issuer_name':'Fictional','issuer_aliases':['虚构股份有限公司']},chosen)
        self.assertEqual(value['language'],'Chinese')

    def test_public_form_cache_is_bound_to_each_request_body(self):
        seen=[]
        def transport(url,headers,data):
            seen.append(data);return 200,{'Content-Type':'application/json'},data,url
        with tempfile.TemporaryDirectory() as d:
            c=Client(Path(d),{'archive.example'},'Fictional client',transport=transport,interval=0)
            first=c.get('https://archive.example/query',form={'page':1})
            second=c.get('https://archive.example/query',form={'page':2})
            self.assertNotEqual(first[1]['sha256'],second[1]['sha256'])
            self.assertEqual(c.get('https://archive.example/query',form={'page':1})[0],first[0])
            self.assertEqual(len(seen),2)


class GuidanceTests(unittest.TestCase):
    def test_forward_range_uses_full_year_guidance_not_quarterly_eps(self):
        text='Earnings Call: Q2 2040\nAugust 6, 2040\nFor Q3, non-GAAP diluted earnings per share of $0.20 to $0.25. For the full year of 2040, we expect revenue growth. Non-GAAP diluted earnings per share of $0.90 to $1.10.'
        source={'document_id':'fictional','sha256':'a'*64};prices=[{'document_id':'fictional','symbol':'FAKE','currency':'USD'}]
        rows=valuation.guidance_eps(text,source,prices)
        self.assertEqual([(r['low'],r['high'],r['fiscal_year']) for r in rows],[('0.90','1.10',2040)])
        self.assertEqual(rows[0]['guidance_date'],'2040-08-06')
        self.assertEqual(text[rows[0]['start']:rows[0]['end']],rows[0]['text'])
        self.assertEqual(valuation.guidance_eps(text.replace('For the full year of 2040,','For Q4,'),source,prices),[])
        self.assertEqual(valuation.guidance_eps(text,source,[{**prices[0],'currency':'EUR'}]),[])

    def test_explicit_fiscal_year_heading_preserves_annual_guidance_scope(self):
        text='Earnings Call: Q2 2041\nAugust 6, 2040\nFor fiscal year 2041, we expect non-GAAP diluted EPS of $1.25 to $1.26.'
        source={'document_id':'fictional','sha256':'a'*64};prices=[{'document_id':'fictional','symbol':'FAKE','currency':'USD'}]
        for heading in ['For fiscal year 2041','For fiscal 2041','For the fiscal year 2041']:
            original=text.replace('For fiscal year 2041',heading)
            rows=valuation.guidance_eps(original,source,prices)
            self.assertEqual([(r['fiscal_year'],r['low'],r['high']) for r in rows],[(2041,'1.25','1.26')])
            self.assertEqual(rows[0]['text'],original[rows[0]['start']:rows[0]['end']])
        self.assertEqual(valuation.guidance_eps(text.replace('For fiscal year 2041','For fiscal Q3 2041'),source,prices),[])
        self.assertEqual(valuation.guidance_eps(text.replace('For fiscal year 2041','For the full year 2041. For the third quarter'),source,prices),[])


if __name__=='__main__':unittest.main()
