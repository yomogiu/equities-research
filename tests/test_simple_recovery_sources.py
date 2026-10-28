"""Fictional recovery regressions: no live issuers or model dispatch."""
from datetime import date
import copy,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
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
    def test_recovery_packet_reaches_authenticated_transport_with_version(self):
        calls=[]
        def invoke(job,prompt,model,effort,bindings,index,**settings):
            from research import earnings_file_runner as transport
            transport._direct_packet(prompt,index,bindings)
            calls.append((model,effort))
            return {'content':{'diagnosis':'Fictional parser layout changed','action':'retry','reason':'General parser now supports it',
                              'patch':'','tests':[],'publication_risks':[]}}
        with TemporaryDirectory() as d:
            result=agent.diagnose(Path(d),{'incident':{'reason':'Fictional layout'}},invoke,max_tokens=220000)
        self.assertEqual(result['action'],'retry');self.assertEqual(calls,[(agent.MODEL,agent.EFFORT)])
    def test_display_preserves_numbers_lines_and_exact_table_inventory(self):
        from research import earnings_report_display as display
        text='Revenue                 12,345       10,000\nDebt                    (100)        (90)\nItem 9. Controls\nMaterial weakness disclosed.\nItem 10. Directors\nProxy material.'
        packet={'documents':[{'start':100,'text':text,'omitted_prefix':'Annual business/risk prose omitted'}],
                'document_scopes':[['D1',0,100,130],['D2',0,100,100+len(text)]],
                'financial_inventory':{'cells':['12,345','10,000','(100)','(90)']},'source_policy':'Financial event update.'}
        out=display.compact(packet);shown=out['documents'][0]['text']
        self.assertIn('12,345\t10,000',shown);self.assertIn('Material weakness disclosed.',shown)
        self.assertNotIn('Proxy material.',shown)
        self.assertEqual(out['financial_inventory'],packet['financial_inventory'])
        self.assertEqual(packet['documents'][0]['text'],text)
        self.assertEqual([x[0] for x in out['document_scopes']],['D1'])
        packet['financial_inventory']['original_tables']={'rows':[['R1',[[0,'Revenue       12,345'],[1,'10,000']]]]}
        out=display.compact(packet)
        self.assertEqual(out['financial_inventory']['original_tables']['rows'],[['R1',[[0,'Revenue\t12,345'],[1,'10,000']]]])
        self.assertEqual(packet['financial_inventory']['original_tables']['rows'][0][1][0][1],'Revenue       12,345')

if __name__=='__main__':unittest.main()
