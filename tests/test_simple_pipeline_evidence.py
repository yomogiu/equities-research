"""Fictional regressions for evidence parity and positional statement rendering."""
import copy,json,unittest
from unittest.mock import patch
from research import earnings_simple_runner as simple
from research import earnings_pdf_tables as pdf,earnings_markdown_render as markdown
from research import financial_evidence as financial
from test_earnings_simple_runner import SimpleRunnerTests


class SourceParity(unittest.TestCase):
    def test_pdf_row_addresses_preserve_the_complete_original_values_once(self):
        from research import earnings_report_display as display
        text='[Page 1]\nRevenue             100          90\nCost                 60          55\nProfit               40          35\n'
        table=pdf.tables(text,{'document_id':'fictional','sha256':financial.digest(text.encode())})[0]
        packet={'documents':[{'source_id':table['source_id'],'start':0,'text':text}],
                'document_scopes':[['D001',0,0,len(text)]], 'source_policy':'Original',
                'financial_inventory':{'original_tables':{'tables':[{'id':table['id'],'source_id':table['source_id'],'rows':[]} ]}}}
        original=copy.deepcopy(table)
        result=display.compact(packet,{'packet_inventory':{'tables':[table]}})
        for row in result['financial_inventory']['original_tables']['tables'][0]['rows']:
            number=row[1]
            self.assertIn('L'+str(number)+': '+__import__('re').sub(r'[ \t]{2,}','\t',text.splitlines()[number-1]),result['documents'][0]['text'])
        self.assertEqual(table,original)

    def test_repeated_annual_headings_cannot_hide_statement_or_mda(self):
        text='FORM 10-K\nItem 8. Financial Statements (contents)\nMD&A: obligations mature next year.\nItem 8. Financial Statements\nRevenue 100 90\nItem 8. Financial Statements (index)\nFinal note.'
        packet={'version':'old','documents':[{'id':'fake','kind':'filing','start':0,'text':text}],
                'document_scopes':[['D001',0,0,len(text)]], 'transcript_index':{},
                'financial_inventory':{},'source_policy':''}
        with patch.object(simple.content,'packet',return_value=packet):value=simple.packet({})
        self.assertIn('obligations mature',value['documents'][0]['text'])
        self.assertIn('Revenue 100 90',value['documents'][0]['text'])
        self.assertEqual(value['document_scopes'],[['D001',0,0,len(text)]])

    def test_correction_does_not_expand_a_document_into_uncompressed_records(self):
        original={'documents':[{'text':'Revenue\t100\t90'}], 'document_scopes':[],
                  'financial_inventory':{'facts':[]},'transcript':'Call', 'source_policy':'Complete originals'}
        value=simple.revision_packet({},original,{}, {'findings':[]},True)
        self.assertEqual(value,original)
        self.assertEqual(simple.validation_packet(original),original)
        self.assertIsNot(value,original)

    def test_pdf_heading_on_preceding_page_and_sparse_columns_stay_aligned(self):
        heading='Fictional consolidated cash flows\n(In thousands of U.S. dollars)\n'
        lines=['Six months ended June 30,','                         2040         2039',
               'Operating cash flow       120          100',
               'Capital spending           20           15',
               'Other                       8            6']
        text='[Page 1]\n'+heading+'[Page 2]\n'+'\n'.join(lines)+'\n'
        table=pdf.tables(text,{'document_id':'fictional','sha256':financial.digest(text.encode())})[0]
        table['selected_row_ids']=[r['row_id'] for r in table['source_lines'] if 'Operating' in r['text']]
        rendered='\n'.join(pdf.render(table))
        self.assertIn('In thousands of U.S. dollars',rendered)
        self.assertIn(lines[1],rendered);self.assertIn(lines[2],rendered)
        self.assertNotIn('Source column',rendered)
        page=markdown.render(rendered+'\n[^'+table['source_id']+']: Fictional original.')
        self.assertIn('<pre class="source-layout">',page)
        self.assertIn(lines[2],page)


class LiveContractRegressions(SimpleRunnerTests):
    def test_optional_known_gap_does_not_consume_the_correction_allowance(self):
        invoke=self.invoke
        def output(*args,**kwargs):
            response=invoke(*args,**kwargs)
            if self.calls[-1]=='author':
                response['content']['financial_selection']['gaps'].append({'metric':'credit_capacity','reason':'Not disclosed in fictional source.','citations':['D001']})
            return response
        result=simple.run_company(self.job,self.spec,self.prepare,self.publish,invoke=output)
        self.assertEqual(result['status'],'published',result.get('reason'))
        self.assertEqual(self.calls,['author','review'])

    def test_independent_review_and_repair_receive_identical_original_documents(self):
        self.finding='blocking';invoke=self.invoke;documents=[]
        def output(directory,prompt,model,effort,bindings,index,**options):
            packet=simple.context.Evidence(index,self.root/'unused.jsonl',_replay=True).artifacts['single_report_packet']
            documents.append(copy.deepcopy(packet['documents']))
            return invoke(directory,prompt,model,effort,bindings,index,**options)
        result=simple.run_company(self.job,self.spec,self.prepare,self.publish,invoke=output)
        self.assertEqual(result['status'],'published',result.get('reason'))
        self.assertEqual(len(documents),4)
        self.assertTrue(all(d==documents[0] for d in documents))


if __name__=='__main__':unittest.main()
