"""Fictitious complete-packet extraction and original-table selection invariants."""
import copy,json,tempfile,unittest
from pathlib import Path
from research import earnings_packet_inventory as inventory
from research import earnings_compact_evidence as compact
from research import earnings_source_case as storage
from research import earnings_financial_selection as selection
from research import earnings_valuation_inventory as valuation
from test_earnings_compact_evidence import fixture,write

class PacketTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path,self.case,_=fixture(self.root)
        self.case['financial_inventory_version']=inventory.VERSION
        self.release='<html><p>Fictional reconciliation; USD thousands except EPS.</p><table><tr><th>Non-GAAP</th><th colspan="2">Three months ended March 31</th></tr><tr><td></td><td>2040</td><td>2039</td></tr><tr><td>Adjusted EPS</td><td>0.33</td><td>0.36</td></tr><tr><td>Adjusted operating income</td><td>23,139</td><td>(23,097)</td></tr></table></html>'
        self.add('release','release',self.release)
        raw=(self.root/'filing.html').read_text().replace('12</ix:', '15</ix:').replace('2040-','2039-')
        self.add('annual','filing',raw)
    def add(self,name,kind,raw):
        for rep,suffix in [('raw','html'),('text','txt')]:
            path=self.root/(name+'.'+suffix);path.write_text(raw if rep=='raw' else 'Fictional plain text: '+raw)
            self.case['sources'].append({'document_id':name,'kind':kind,'representation':rep,'path':str(path),'sha256':storage.sha(path)})
    def bundle(self):
        write(self.path,self.case)
        return compact.load_bundle(compact.prepare(self.path,self.root/'out'))
    def pick(self,b):
        t=next(t for t in b['packet_inventory']['tables'] if t['document_id']=='release')
        return {'table_id':t['id'],'row_ids':['R3'],'section':'earnings'}
    def test_all_documents_all_tagged_observations_and_untagged_cells(self):
        b=self.bundle();facts=b['financial']['observations']
        self.assertEqual(len(facts),4) # two per filing; manual proposal is never promoted
        self.assertEqual({f['source_document_id'] for f in facts},{'fictional-filing','annual'})
        self.assertIn('15',{f['value'] for f in facts})
        inv=b['packet_inventory'];self.assertEqual(len(inv['coverage']),3)
        self.assertEqual(inv['source_set']['release'],'present')
        self.assertIn(('2039-01-01','2039-03-31'),map(tuple,inv['periods']))
        cells=[c for t in inv['tables'] if t['document_id']=='release' for c in t['cells']]
        self.assertIn('(23,097)',[c['text'] for c in cells])
        self.assertTrue(all(c['raw_span_sha256'] for c in cells))
        self.assertIn('valuation_inventory',b)
    def test_select_original_rows_preserves_values_headers_units_and_unselected_omission(self):
        b=self.bundle();pick=self.pick(b);t=inventory.selected([pick],b)[0]
        rendered='\n'.join(inventory.render(t))
        for text in ('0.33','0.36','2040','2039','USD thousands except EPS','Non-GAAP','Three months ended March 31'):
            self.assertIn(text,rendered)
        self.assertNotIn('23,139',rendered)
        self.assertIn('document-source-release',rendered)
    def test_selection_cannot_supply_values_or_unknown_rows(self):
        b=self.bundle();pick=self.pick(b)
        for bad in ({**pick,'value':'999'},{**pick,'row_ids':['R999']},{**pick,'section':'unknown'}):
            with self.assertRaises(ValueError):inventory.validate_selection([bad],b)
    def test_source_tampering_fails_before_author(self):
        (self.root/'release.html').write_text('changed')
        with self.assertRaisesRegex(ValueError,'Frozen input changed'):self.bundle()
    def test_missing_release_is_a_source_gap_not_claim_of_nondisclosure(self):
        self.case['sources']=[s for s in self.case['sources'] if s['kind']!='release']
        b=self.bundle();self.assertEqual(b['packet_inventory']['source_set']['release'],'not_in_qualified_packet')
    def test_unsupported_binary_format_is_explicit_and_does_not_destroy_other_data(self):
        for s in self.case['sources']:
            if s['document_id']=='release' and s['representation']=='raw':
                Path(s['path']).write_bytes(b'%PDF\xff');s['sha256']=storage.sha(s['path'])
        b=self.bundle();row=next(r for r in b['packet_inventory']['coverage'] if r['document_id']=='release')
        self.assertEqual(row['status'],'unsupported_format');self.assertEqual(len(b['financial']['observations']),4)
    def test_no_numeric_tags_is_allowed_with_table_evidence(self):
        self.case['sources']=[s for s in self.case['sources'] if s['document_id'] not in ('fictional-filing','annual')]
        # Existing selected-filing artifact still requires its authenticated raw source.
        # Use an empty original artifact bound to the untagged replacement filing.
        src=next(s for s in self.case['sources'] if s['document_id']=='release' and s['representation']=='raw')
        self.case['sources'][self.case['sources'].index(src)]={**src,'kind':'filing'}
        from research import financial_evidence as f
        a=f.extract_inline_xbrl(self.release,{'document_id':'release','raw_sha256':src['sha256']})
        p=Path(self.case['financial_path']);write(p,a)
        for item in self.case['artifacts']:
            if item['path']==str(p):item['sha256']=storage.sha(p)
        b=self.bundle();self.assertEqual(b['financial']['observations'],[]);self.assertTrue(b['packet_inventory']['tables'])
    def test_nested_tables_not_double_rendered_or_selectable_as_outer_row(self):
        raw='<table><tr><td><table><tr><td>EPS</td><td>2.0</td></tr></table></td></tr></table>'
        s={'document_id':'fake','sha256':'a'*64};ts=inventory.tables(raw,s)
        self.assertEqual(len(ts),2)
        self.assertEqual(len(ts[0]['rows']),1)
        with self.assertRaisesRegex(ValueError,'nested'):
            inventory.validate_selection([{'table_id':ts[0]['id'],'row_ids':['R1'],'section':'earnings'}],{'packet_inventory':{'tables':ts}})
    def test_rowspan_and_colspan_preserve_column_positions(self):
        ts=inventory.tables('<table><tr><td rowspan="2">Label</td><td colspan="2">Year</td></tr><tr><td>10</td><td>20</td></tr></table>',{'document_id':'fake','sha256':'a'*64})
        c=ts[0]['cells'];self.assertEqual([x['column'] for x in c],[0,1,1,2])
    def test_zero_selected_tagged_rows_with_explicit_gaps_is_valid(self):
        b=self.bundle();v={'rows':[],'notes':[],'gaps':[{'metric':m,'reason':'No reliable normalized selection. Original report tables supply available data.','citations':['D001']} for m in selection.REQUIRED],'reported_tables':[self.pick(b)]}
        selection.validate(v,b)
        applied=selection.apply(b,v);self.assertEqual(len(applied['reported_tables']),1)

    def test_replay_detects_tampered_original_table_without_trusting_saved_hash(self):
        from research import earnings_sequential_financial_contract as contract
        b=self.bundle();self.assertEqual(len(contract._replayed_facts(b)),4)
        b['packet_inventory']['tables'][0]['cells'][0]['text']='Invented value'
        with self.assertRaisesRegex(ValueError,'original-source replay'):contract._replayed_facts(b)

    def test_unsupported_numeric_transform_remains_explicit_not_zero(self):
        raw='<table><tr><td>Fictional metric</td><td><ix:nonfraction name="fake:X" contextref="missing" unitref="missing">none</ix:nonfraction></td></tr></table>'
        self.add('ambiguous','release',raw)
        b=self.bundle();doc=next(r for r in b['packet_inventory']['coverage'] if r['document_id']=='ambiguous')
        self.assertEqual(doc['tagged_observations'],0);self.assertTrue(doc['limitations'])
        self.assertTrue(any(c['text']=='none' for t in b['packet_inventory']['tables'] for c in t['cells']))

    def test_compact_shared_text_reconstructs_every_nonempty_cell(self):
        self.add('duplicate-release','release',self.release)
        b=self.bundle();packed=inventory.compact(b['packet_inventory'])
        self.assertTrue(packed['shared_text'])
        originals={t['id']:t for t in b['packet_inventory']['tables']}
        def text(value):return packed['shared_text'][value['text_ref']] if isinstance(value,dict) else value
        for table in packed['tables']:
            original=originals[table['id']]
            self.assertEqual([text(v) for v in table['context']],[c['text'] for c in original['context']])
            expected={(c['row'],c['column']):c['text'] for c in original['cells'] if c['text'].strip(' \u200b\ufeff')}
            actual={(int(row[0][1:])-1,c[0]):text(c[1]) for row in table['rows'] for c in row[1]}
            self.assertEqual(actual,expected)

    def test_compact_render_folds_headers_and_keeps_periods_and_values(self):
        b=self.bundle();t=inventory.selected([self.pick(b)],b)[0]
        text='\n'.join(inventory.render_compact(t))
        for token in ('0.33','0.36','2040','2039','Three months ended March 31'):
            self.assertIn(token,text)
        self.assertNotIn('Reported column',text)
        self.assertNotIn('23,139',text)

    def test_compatible_gaap_rows_combine_without_changing_values(self):
        raw='<p>Fictional results (Q2 2040)</p><p>(USD thousands)</p><table><tr><td>Metric</td><td>GAAP</td><td>Non-GAAP</td></tr><tr><td>Income</td><td>10</td><td>15</td><td>^</td></tr></table>'
        a=inventory.tables(raw,{'document_id':'fake','sha256':'a'*64})[0]
        b=inventory.tables(raw.replace('2040','2039').replace('>10<','>9<'),{'document_id':'fake2','sha256':'b'*64})[0]
        for table in (a,b):table['selected_row_ids']=['R2']
        result='\n'.join(inventory.render_comparison([a,b]))
        self.assertEqual(result.count('### '),1)
        for value in ('Q2 2040','Q2 2039','10','9','15','USD thousands'):self.assertIn(value,result)
        self.assertNotIn('15^',result)

    def test_units_in_column_zero_survive_numeric_projection(self):
        raw='<table><tr><td>Fictional adjusted results</td><td></td><td></td></tr><tr><td>(Unaudited - In thousands)</td><td></td><td></td></tr><tr><td></td><td>2040</td><td>2039</td></tr><tr><td>Income</td><td>123</td><td>100</td></tr></table>'
        t=inventory.tables(raw,{'document_id':'fake','sha256':'a'*64})[0]
        t['selected_row_ids']=['R4']
        output='\n'.join(inventory.render_compact(t))
        for text in ('Fictional adjusted results','In thousands','2040','2039','123','100'):self.assertIn(text,output)

    def test_explicit_document_units_survive_distant_table_and_boilerplate(self):
        raw='<p>Except where otherwise indicated, amounts presented in this Form 10-Q are in thousands, except per share amounts.</p>'
        raw+='<p>Fictional page furniture.</p>'*4+'<p>'+('Fictional boilerplate. '*100)+'</p>'
        raw+='<table><tr><td></td><td>2040</td></tr><tr><td>Total debt</td><td>123</td></tr></table>'
        t=inventory.tables(raw,{'document_id':'fake','sha256':'a'*64})[0];t['selected_row_ids']=['R2']
        output='\n'.join(inventory.render_compact(t))
        self.assertIn('amounts presented in this Form 10-Q are in thousands',output)
        self.assertNotIn('Fictional boilerplate.',output)
        declaration=next(c for c in t['context'] if 'in thousands' in c['text'])
        from research import financial_evidence
        self.assertEqual(declaration['raw_span_sha256'],financial_evidence.digest(raw[declaration['start']:declaration['end']].encode()))

    def test_combined_comparison_retains_internal_unit_heading(self):
        raw='<table><tr><td>(USD thousands except per share amounts)</td><td></td><td></td></tr><tr><td>Metric</td><td>GAAP</td><td>Non-GAAP</td></tr><tr><td>Income</td><td>12</td><td>15</td></tr></table>'
        t=inventory.tables(raw,{'document_id':'fake','sha256':'a'*64})[0];t['selected_row_ids']=['R3']
        output='\n'.join(inventory.render_comparison([t]))
        self.assertIn('USD thousands except per share amounts',output)
        self.assertIn('| 12 | 15 |',output)

if __name__=='__main__':unittest.main()
