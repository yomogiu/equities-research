"""Fictional recovery regressions: no live issuers or model dispatch."""
from datetime import date
import copy,unittest
from research import earnings_report_identity as identity,earnings_report_support as support
from research import earnings_report_only_sources as sources
from research import earnings_recovery_agent as agent
from research import earnings_runtime_common as runtime

class RecoverySources(unittest.TestCase):
    def test_legal_name_variants_keep_distinctive_identity(self):
        self.assertTrue(identity.matches_issuer('Example Devices Company Limited transcripts','EXAMPLE DEVICES CO LTD'))
        self.assertTrue(identity.matches_issuer('Example-Devices, Inc.','Example Devices Corporation'))
        self.assertFalse(identity.matches_issuer('Different Devices Company Limited','EXAMPLE DEVICES CO LTD'))
        self.assertFalse(identity.matches_issuer('Example Devicesmith Inc.','Example Devices Inc'))
        with self.assertRaises(ValueError):identity.matches_issuer('Anything','Co Ltd')
    def test_support_rebinds_only_ordered_verbatim_sentences(self):
        original={'analysis':{'sections':{'outlook':{'text':'Revenue rises. EPS rises. Prior guidance unavailable.'}},
            'report_support':{'coverage':{'guidance_basis':{'status':'addressed','report_excerpt':'Revenue rises. Prior guidance unavailable.'}}}}}
        before=copy.deepcopy(original);resolved,changes=support.synchronize(original)
        self.assertEqual(resolved['analysis']['report_support']['coverage']['guidance_basis']['report_excerpt'],original['analysis']['sections']['outlook']['text'])
        self.assertEqual(original,before);self.assertEqual(len(changes),1)
        original['analysis']['report_support']['coverage']['guidance_basis']['report_excerpt']='Revenue declines. Prior guidance unavailable.'
        self.assertEqual(support.synchronize(original),(original,[]))
    def test_report_discovery_uses_actual_latest_links(self):
        body='<a href="/first.pdf">2026年第1季合併財務報告</a><a href="/second.pdf">2026年第2季合併財務報告</a><a href="/future.pdf">2026年第4季合併財務報告</a>'
        chosen=sources.candidates(body.encode(),'https://issuer.example/reports',date(2026,10,28))
        self.assertEqual(chosen['url'],'https://issuer.example/second.pdf');self.assertEqual(chosen['end'],'2026-06-30')
        with self.assertRaisesRegex(ValueError,'Ambiguous'):
            sources.candidates((body+'<a href="/different.pdf">2026年第2季合併財務報告</a>').encode(),'https://issuer.example/reports',date(2026,10,28))
    def test_chinese_report_identity_period_and_statements(self):
        text='[Page 1]\n虛構科技股份有限公司\n民國一一五年及一一四年第二季\n資產負債表\n綜合損益表\n現金流量表\n'+'原文 '*6000
        profile={'issuer_name':'Fictional Devices','issuer_aliases':['虛構科技股份有限公司']}
        event={'year':2026,'quarter':2,'end':'2026-06-30'}
        self.assertEqual(sources.qualify(text,profile,event)['language'],'Chinese')
        with self.assertRaisesRegex(ValueError,'heading'):
            sources.qualify(text,profile,{**event,'year':2027})
        with self.assertRaisesRegex(ValueError,'identity'):
            sources.qualify(text,{'issuer_name':'Other Issuer'},event)
    def test_exact_terra_high_is_authorized(self):
        runtime._validate_selection(agent.MODEL,agent.EFFORT)
        with self.assertRaises(ValueError):runtime._validate_selection(agent.MODEL,'low')

if __name__=='__main__':unittest.main()
