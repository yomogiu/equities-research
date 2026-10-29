"""Fictional regressions for evidence parity and positional statement rendering."""
import copy,json,unittest
from unittest.mock import patch
from research import earnings_simple_runner as simple
from research import earnings_pdf_tables as pdf,earnings_markdown_render as markdown
from research import financial_evidence as financial
from test_earnings_simple_runner import SimpleRunnerTests


class SourceParity(unittest.TestCase):
    def test_scope_is_reader_facing_and_retains_specific_missing_source(self):
        notes=['Freshly collected FY2040-Q2 earnings_call. Never infer approval.',
               'PDF financial tables are verbatim positional extraction. Prefer selected original rows.',
               'Call and report may disagree; use the original financial report.',
               'One qualified financial document and call collected; other releases, MD&A and presentations are not included by this bounded route.',
               'The prior-quarter filing is unavailable.']
        rendered='\n'.join(simple.content._reader_scope(notes))
        self.assertIn('FY2040-Q2',rendered);self.assertIn('prior-quarter filing is unavailable',rendered)
        self.assertNotIn('Never infer',rendered);self.assertNotIn('Prefer selected',rendered)
        self.assertNotIn('MD&A',rendered);self.assertNotIn('bounded route',rendered)

    def test_full_document_alias_requires_exact_unique_bound_identity(self):
        identifier='a'*20+'b'*44;other='a'*20+'c'*44;canonical='document-source-'+identifier[:20]
        bundle={'packet_inventory':{'tables':[]},'manifest':{'sources':[
            {'document_id':identifier,'kind':'filing','representation':'text','sha256':'d'*64}]}}
        value={'text':'Fictional source claim.','citations':['document-source-'+identifier,'document-source-'+other]}
        resolved,trace=simple.resolve_citations(value,bundle,{canonical})
        self.assertEqual(resolved['citations'],[canonical,'document-source-'+other])
        self.assertEqual(len(trace),1);self.assertEqual(trace[0]['source_sha256'],'d'*64)
        self.assertEqual(value['citations'][0],'document-source-'+identifier)
        bundle['manifest']['sources'].append({'document_id':other,'kind':'filing','representation':'text','sha256':'e'*64})
        ambiguous,trace=simple.resolve_citations(value,bundle,{canonical})
        self.assertEqual(ambiguous,value);self.assertEqual(trace,[])
        absent,trace=simple.resolve_citations(value,bundle,set())
        self.assertEqual(absent,value);self.assertEqual(trace,[])

    def test_inline_row_citation_alias_rejects_nonexistent_rows(self):
        table={'id':'T-fictional','source_id':'document-source-fictional','raw_span_sha256':'f'*64,'rows':[{'id':'R7'}]}
        bundle={'packet_inventory':{'tables':[table]},'manifest':{'sources':[]}}
        value={'citations':['T-fictional/R7','T-fictional/R8']}
        resolved,trace=simple.resolve_citations(value,bundle,{table['source_id']})
        self.assertEqual(resolved['citations'],[table['source_id'],'T-fictional/R8'])
        self.assertEqual(trace[0]['row_id'],'R7')

    def test_short_pdf_table_alias_binds_selection_and_citation_without_changing_rows(self):
        table={'id':'T-fictional','representation':'pdf_layout_text','source_id':'document-source-fictional','raw_span_sha256':'f'*64,'rows':[{'id':'R7'}]}
        bundle={'packet_inventory':{'tables':[table]},'manifest':{'sources':[]}}
        value={'financial_selection':{'reported_tables':[{'table_id':'P1','row_ids':['R7'],'section':'cash'}]},'citations':['P1/R7']}
        resolved,trace=simple.resolve_citations(value,bundle,{table['source_id']})
        self.assertEqual(resolved['financial_selection']['reported_tables'][0],{'table_id':'T-fictional','row_ids':['R7'],'section':'cash'})
        self.assertEqual(resolved['citations'],[table['source_id']])
        self.assertEqual(value['financial_selection']['reported_tables'][0]['table_id'],'P1')
        self.assertEqual(len(trace),2)

    def test_hash_prefix_alias_requires_long_unique_literal_known_scope(self):
        bundle={'packet_inventory':{'tables':[]},'manifest':{'sources':[]}}
        canonical='turn-'+'a'*18+'b'*6;prefix='turn-'+'a'*18
        unknown='turn-'+'c'*18;too_short='turn-'+'a'*8
        value={'citations':[prefix,unknown,too_short,canonical+'f']}
        resolved,trace=simple.resolve_citations(value,bundle,{canonical})
        self.assertEqual(resolved['citations'],[canonical,unknown,too_short,canonical+'f'])
        self.assertEqual(len(trace),1)
        ambiguous,trace=simple.resolve_citations(value,bundle,{canonical,'turn-'+'a'*18+'c'*6})
        self.assertEqual(ambiguous,value);self.assertEqual(trace,[])

    def test_hash_middle_elision_requires_unique_unchanged_prefix_and_suffix(self):
        bundle={'packet_inventory':{'tables':[]},'manifest':{'sources':[]}}
        canonical='turn-0123456789ababcdef012345';abbreviated='turn-0123456789ab012345'
        value={'citations':[abbreviated,'turn-0123456789ab012346']}
        resolved,trace=simple.resolve_citations(value,bundle,{canonical})
        self.assertEqual(resolved['citations'],[canonical,'turn-0123456789ab012346'])
        self.assertEqual(len(trace),1)
        ambiguous,trace=simple.resolve_citations(value,bundle,{canonical,'turn-0123456789abfedcba012345'})
        self.assertEqual(ambiguous,value);self.assertEqual(trace,[])

    def test_pdf_row_addresses_preserve_the_complete_original_values_once(self):
        from research import earnings_report_display as display
        text='[Page 1]\nRevenue             100          90\nCost                 60          55\nProfit               40          35\n'
        table=pdf.tables(text,{'document_id':'fictional','sha256':financial.digest(text.encode())})[0]
        packet={'documents':[{'source_id':table['source_id'],'start':0,'text':text}],
                'document_scopes':[['D001',0,0,len(text)]], 'source_policy':'Original',
                'financial_inventory':{'original_tables':{'tables':[{'id':table['id'],'source_id':table['source_id'],'rows':[]} ]}}}
        original=copy.deepcopy(table)
        result=display.compact(packet,{'packet_inventory':{'tables':[table]}})
        self.assertEqual(result['financial_inventory']['original_tables']['tables'][0]['row_count'],len(table['rows']))
        cells={c['id']:c for c in table['cells']}
        for row in table['rows']:
            rid=row['id'];number=text[:min(cells[i]['start'] for i in row['cells'])].count('\n')+1
            self.assertIn('[P1/'+rid+'] '+__import__('re').sub(r'[ \t]{2,}','\t',text.splitlines()[number-1]),result['documents'][0]['text'])
        self.assertEqual(table,original)

    def test_large_annual_projection_ignores_toc_and_preserves_mda_notes_and_all_tables(self):
        text=('[Page 1]\nFORM 10-K\nItem 7. Management Discussion\nItem 8. Financial Statements\nItem 9. Changes\n'
              '[Page 2]\nCover facts\n[Page 3]\nItem 1. Business\n'+('Business prose. '*5000)+'\n'
              '[Page 4]\nItem 1A. Risk Factors\n'+('Material risk. '*500)+'\nItem 1B. Unresolved Comments\n'
              '[Page 5]\nItem 7. Management Discussion\n'+('Financial operating explanation. '*500)+'\n'
              '[Page 6]\nItem 8. Financial Statements\n'+('Complete financial notes. '*500)+'\n'
              '[Page 7]\nItem 9. Changes\n'+('Governance prose. '*25000)+'\n'
              '[Page 8]\nOutside financial section\nRevenue             100          90\nCost                 60          55\nProfit               40          35\n')
        tables=pdf.tables(text,{'document_id':'fictional','sha256':financial.digest(text.encode())})
        packet={'documents':[{'source_id':tables[0]['source_id'],'start':0,'text':text}],
                'document_scopes':[['D001',0,text.index('[Page 7]'),text.index('[Page 8]')]],'source_policy':'Original',
                'financial_inventory':{'original_tables':{'shared_text':['unused duplicate'], 'tables':[{'id':t['id'],'source_id':t['source_id'],'rows':[]} for t in tables]}}}
        from research import earnings_report_display as display
        value=display.compact(packet,{'packet_inventory':{'tables':tables}})
        shown=value['documents'][0]['text']
        self.assertNotIn('Material risk.',shown);self.assertIn('Financial operating explanation.',shown)
        self.assertIn('Complete financial notes.',shown);self.assertIn('Revenue\t100\t90',shown)
        self.assertNotIn('Governance prose.',shown);self.assertNotIn('Business prose.',shown)
        self.assertTrue(value['documents'][0]['display_projection']['omitted_original_spans'])
        self.assertEqual(value['document_scopes'],[])
        self.assertEqual(value['financial_inventory']['original_tables']['shared_text'],[])
        self.assertEqual(packet['documents'][0]['text'],text)
        unknown=text.replace('Item 8. Financial Statements','Unrecognized statement heading')
        self.assertEqual(display.annual_lines(unknown,tables),(None,[]))

    def test_sparse_pdf_rows_have_their_actual_selection_ids_beside_the_values(self):
        from research import earnings_report_display as display
        text='[Page 1]\nFictional income statement\n\n                   2040    2039\nRevenue             100      90\nCost                 60      55\nResearch and development\n                     10       8\nDiluted EPS         1.2     1.0\n'
        tables=pdf.tables(text,{'document_id':'fictional','sha256':financial.digest(text.encode())})
        table=tables[0];packet={'documents':[{'source_id':table['source_id'],'start':0,'text':text}],
            'document_scopes':[['D001',0,0,len(text)]],'source_policy':'Original',
            'financial_inventory':{'original_tables':{'tables':[{'id':table['id'],'source_id':table['source_id'],'rows':[]}]}}}
        shown=display.compact(packet,{'packet_inventory':{'tables':tables}})['documents'][0]['text']
        cells={c['id']:c for c in table['cells']}
        for row in table['rows']:
            line=min(cells[c]['start'] for c in row['cells'])
            number=text[:line].count('\n')+1
            expected=text.splitlines()[number-1].strip(' \t')
            self.assertIn('[P1/'+row['id']+'] '+__import__('re').sub(r'[ \t]{2,}','\t',expected),shown)
        self.assertEqual(shown.count('1.2'),1)
        self.assertEqual(packet['documents'][0]['text'],text)

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

    def test_pdf_render_excludes_unselected_ambiguous_data_and_trailing_prose(self):
        text='[Page 1]\nFictional consolidated income statement\n(In thousands)\n                         2040       2039\nRevenue              $    100   $     90\nCost                       60        55\nProfit                     40        35\nUnrelated trailing footnote and page footer.\n'
        table=pdf.tables(text,{'document_id':'fictional','sha256':financial.digest(text.encode())})[0]
        table['selected_row_ids']=[r['row_id'] for r in table['source_lines'] if r['text'].startswith('Cost ')]
        rendered='\n'.join(pdf.render(table))
        self.assertIn('In thousands',rendered);self.assertIn('2040',rendered)
        self.assertIn('Cost                       60        55',rendered)
        self.assertNotIn('Revenue ',rendered);self.assertNotIn('Profit ',rendered)
        self.assertNotIn('Unrelated trailing footnote',rendered)

    def test_integer_statement_data_cannot_be_misread_as_detached_page_heading(self):
        text='[Page 1]\nFictional balance sheet\nCash                      100        90\nDebt                       60        55\nEquity                     40        35\n[Page 2]\nFictional cash flows\n                         2040      2039\nOperating cash flow       120       100\nCapital spending           20        15\nOther                       8         6\n'
        tables=pdf.tables(text,{'document_id':'fictional','sha256':financial.digest(text.encode())})
        second=tables[1]
        self.assertEqual(len(second['context']),1)
        self.assertEqual(second['context'][0]['text'],'[Page 2]')


class LiveContractRegressions(SimpleRunnerTests):
    def test_financial_correction_cannot_introduce_unrequested_qa_rewrite(self):
        self.finding='blocking';invoke=self.invoke
        def output(*args,**kwargs):
            response=invoke(*args,**kwargs)
            if self.calls[-1]=='review' and self.calls.count('review')==1:
                response['content']['findings'][0]['citations']=['D001']
            if self.calls[-1]=='correction':
                response['content']['analysis']['qa'][0]['assessment']='Unrequested fictional analyst attribution.'
                simple.save(__import__('pathlib').Path(args[0])/'output.json',response['content'])
            return response
        result=simple.run_company(self.job,self.spec,self.prepare,self.publish,invoke=output)
        self.assertEqual(result['status'],'published',result.get('reason'))
        original=simple.read(self.job/'author-resolved.json')['analysis']['qa']
        self.assertEqual(simple.read(self.job/'correction-resolved.json')['analysis']['qa'],original)
        self.assertNotEqual(simple.read(self.job/'correction.json')['analysis']['qa'],original)
        self.assertTrue(simple.read(self.job/'correction-preservation.json')['changes'])
        self.assertEqual(result['tokens_used'],400)

    def test_qa_blocking_finding_still_permits_a_real_qa_repair(self):
        before={'analysis':{'qa':[{'assessment':'Old fictional answer.'}]}}
        after={'analysis':{'qa':[{'assessment':'Corrected fictional answer.'}]}}
        review={'findings':[{'severity':'blocking','location':'qa','citations':['Q1']}]}
        resolved,changes=simple.preserve_reviewed_qa(before,after,review,{'transcript_index':{'exchanges':[]}})
        self.assertEqual(resolved,after);self.assertEqual(changes,[])

    def test_full_document_citation_in_correction_uses_the_same_final_review(self):
        self.finding='blocking';invoke=self.invoke
        def output(*args,**kwargs):
            response=invoke(*args,**kwargs)
            if self.calls[-1]=='correction':
                bundle=simple.evidence.load_bundle(self.job/'sources/manifest.json')
                source=next(s for s in bundle['manifest']['sources'] if s['kind']=='filing' and s['representation']=='text')
                response['content']['analysis']['sections']['demand']['citations']=['document-source-'+source['document_id']]
                simple.save(__import__('pathlib').Path(args[0])/'output.json',response['content'])
            return response
        result=simple.run_company(self.job,self.spec,self.prepare,self.publish,invoke=output)
        self.assertEqual(result['status'],'published',result.get('reason'))
        self.assertEqual([a['role'] for a in result['attempts']],['author','review','correction','check'])
        self.assertEqual(result['corrections'],1)
        self.assertEqual(result['tokens_used'],400)

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
