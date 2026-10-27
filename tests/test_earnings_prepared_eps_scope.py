import unittest,copy,tempfile,json
from pathlib import Path
from unittest.mock import patch
from research import earnings_prepared_eps_scope as p,earnings_mixed_runner as b

def fixture():
    rows=[]
    for i,(concept,value) in enumerate(zip(p.CONCEPTS,('2.10','-0.10','2.00'))):
        rows.append({'id':'F'+str(i),'concept':concept,'value':value,'context_id':'C','unit_id':'USD/share','source_raw_sha256':'a'*64,'source_document_id':'fictional','status':'extracted','support':{'raw_span_sha256':'b'*64}})
    return {'observations':rows,'contexts':{'C':{'dimensions':[],'start_date':'2040-04-01','end_date':'2040-06-30'}}}

class ScopeTests(unittest.TestCase):
    def test_exact_accounting_bridge_preserves_sources(self):
        financial=fixture();before=copy.deepcopy(financial);out=p.scope_bridge(financial,['F0','F1','F2'])
        self.assertEqual([x['value'] for x in out['facts']],['2.10','-0.10','2.00']);self.assertEqual(financial,before)
    def test_wrong_scope_period_unit_source_or_arithmetic_rejected(self):
        for key,value in [('concept',p.CONCEPTS[0]),('context_id','different'),('unit_id','CAD/share'),('source_raw_sha256','c'*64),('value','3.00'),('status','uncertain')]:
            bad=fixture();bad['observations'][2][key]=value
            with self.assertRaises(ValueError):p.scope_bridge(bad,['F0','F1','F2'])
        bad=fixture();bad['contexts']['C']['dimensions']=[{'segment':'fictional'}]
        with self.assertRaises(ValueError):p.scope_bridge(bad,['F0','F1','F2'])
    def test_ambiguous_fact_identity_and_unrelated_block_rejected(self):
        bad=fixture();bad['observations'].append(copy.deepcopy(bad['observations'][0]))
        with self.assertRaises(ValueError):p.scope_bridge(bad,['F0','F1','F2'])
        with self.assertRaises(ValueError):p.scope_bridge(fixture(),['F0','F0','F2'])
        self.assertFalse(p.blocked_scope('Fetch failed'))
        self.assertFalse(p.blocked_scope('A diluted EPS difference'))
    def test_qualification_must_match_closed_conflict_values_and_fact(self):
        bridge=p.scope_bridge(fixture(),['F0','F1','F2'])
        message='D001 identifies $2.10 as diluted EPS, while F2 reports $2.00 as diluted earnings per share. The accounting-scope distinction is unclear without inventing a basis.'
        self.assertEqual(p.qualify_block(message,bridge),'D001')
        for bad in (message.replace('$2.10','$9.10'),message.replace('F2','F9'),message.replace('$2.00','$3.00')):
            with self.assertRaises(ValueError):p.qualify_block(bad,bridge)
    def test_manifest_cannot_reset_usage_rounds_or_completed_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'protocol.json').write_text('{}');case=root/'case.json';case.write_text('{}')
            catalog={'passages':[]};v={'case_sha256':b.sha(case),'catalog_sha256':b.digest(catalog),'tokens':700000,'max_tokens':1200000,'start_round':2,'spent_correction_rounds':1,'session_ids':['one','two','three','four','five'],'models':{'correction':['original','max']}}
            path=root/'prepared.json'
            with patch.object(p,'replay',return_value=v):
                record=p.prepare(root,case,path,['F0','F1','F2']);self.assertEqual(p.verify(path,case,catalog)['tokens'],700000)
                for key,bad in [('tokens',0),('start_round',1),('session_ids',[]),('models',{'correction':['different','low']})]:
                    changed=copy.deepcopy(record);changed[key]=bad;path.write_text(json.dumps(changed))
                    with self.assertRaisesRegex(ValueError,'Original work'):p.verify(path,case,catalog)
