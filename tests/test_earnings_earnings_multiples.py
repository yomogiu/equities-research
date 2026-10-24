"""Fictitious caller-supplied prices/earnings; no live quotes or forecasts."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from research import earnings_earnings_multiples as pe


def fixture():
    security={'id':'FICTIONAL.ordinary','currency':'USD','earnings_unit':'ordinary_share',
              'ordinary_shares_per_security':'1','split_basis_id':'fictional-split-basis-2026'}
    def record(identifier,value):
        return {'id':identifier,'value':value,'security_id':security['id'],
                **{k:v for k,v in security.items() if k!='id'},'as_of':'2026-10-20',
                'source':{'url':'https://example.invalid/fictional/'+identifier,'document_id':identifier,'sha256':'a'*64}}
    price=record('price-1','120')
    current=record('eps-current','6'); current.update(measure='diluted_eps',accounting_basis='GAAP',
        period={'kind':'ttm','start':'2025-10-01','end':'2026-09-30'})
    forward=record('eps-forward','8'); forward.update(measure='diluted_eps',accounting_basis='Adjusted consensus',
        estimate_type='consensus',forecast_as_of='2026-10-19',
        period={'kind':'forward_annual','start':'2026-01-01','end':'2026-12-31'})
    return {'version':pe.VERSION,'security':security,'price':price,'current_eps':current,'forward_eps':forward}


class EarningsMultiplesTests(unittest.TestCase):
    def build(self,snapshot): return pe.build(snapshot,as_of='2026-10-20')

    def test_current_and_forward_exact_arithmetic_and_original_provenance(self):
        snapshot=fixture(); original=copy.deepcopy(snapshot); result=self.build(snapshot)
        self.assertEqual([r['value'] for r in result['rows']],['20','15'])
        self.assertEqual(result['rows'][0]['label'],'Reported TTM P/E')
        self.assertEqual(result['rows'][1]['earnings_period']['start'],'2026-01-01')
        self.assertEqual(result['rows'][1]['estimate_type'],'consensus')
        self.assertEqual(result['rows'][0]['input_ids'],['price-1','eps-current'])
        self.assertEqual(result['inputs'],original); self.assertEqual(snapshot,original)
        self.assertIn('Caller-provided',result['provenance']); self.assertNotIn('NTM',result['rows'][1]['label'])
        self.assertEqual(result['rows'][0]['accounting_basis'],'GAAP')
        self.assertEqual(result['rows'][1]['accounting_basis'],'Adjusted consensus')

    def test_missing_inputs_and_security_are_unavailable(self):
        for key in ('price','security'):
            snap=fixture(); snap.pop(key)
            self.assertTrue(all(r['status']=='unavailable' for r in self.build(snap)['rows']))
        for index,key in enumerate(('current_eps','forward_eps')):
            snap=fixture(); snap.pop(key); result=self.build(snap)
            self.assertEqual(result['rows'][index]['status'],'unavailable')
            self.assertEqual(result['rows'][1-index]['status'],'available')

    def test_nonpositive_eps_not_meaningful_not_negative_multiple(self):
        for value in ('0','-2'):
            snap=fixture();snap['current_eps']['value']=value;snap['forward_eps']['value']=value
            rows=self.build(snap)['rows']
            self.assertEqual([r['status'] for r in rows],['not_meaningful']*2)
            self.assertTrue(all(r['value'] is None for r in rows))

    def test_quarter_ytd_and_short_year_never_annualized(self):
        for kind,start in [('quarter','2026-07-01'),('ytd','2026-01-01'),('annual','2026-07-01')]:
            snap=fixture();snap['current_eps']['period'].update(kind=kind,start=start)
            self.assertEqual(self.build(snap)['rows'][0]['status'],'unavailable')

    def test_52_and_53_week_annual_periods(self):
        for start,end in [('2025-09-28','2026-09-26'),('2025-09-21','2026-09-26')]:
            snap=fixture();snap['current_eps']['period']={'kind':'annual','start':start,'end':end}
            row=self.build(snap)['rows'][0]
            self.assertEqual(row['value'],'20');self.assertEqual(row['label'],'Reported fiscal-year P/E')

    def test_currency_security_share_and_split_basis_must_match(self):
        for key,value in [('currency','EUR'),('security_id','FICTIONAL.preferred'),('earnings_unit','adr'),
                          ('ordinary_shares_per_security','2'),('split_basis_id','old-split')]:
            snap=fixture();snap['current_eps'][key]=value
            self.assertEqual(self.build(snap)['rows'][0]['status'],'unavailable')
            self.assertEqual(self.build(snap)['rows'][1]['status'],'available')

    def test_explicit_adr_per_security_basis_no_conversion(self):
        snap=fixture()
        for item in [snap['security'],snap['price'],snap['current_eps'],snap['forward_eps']]:
            item.update(earnings_unit='adr',ordinary_shares_per_security='2')
        self.assertEqual(self.build(snap)['rows'][0]['value'],'20')
        snap['current_eps']['ordinary_shares_per_security']='1'
        self.assertEqual(self.build(snap)['rows'][0]['status'],'unavailable')

    def test_no_hindsight_stale_quote_or_future_reported_earnings(self):
        for key,value in [('price','2026-10-19'),('price','2026-10-21'),('current_eps','2026-10-21')]:
            snap=fixture();snap[key]['as_of']=value
            self.assertEqual(self.build(snap)['rows'][0]['status'],'unavailable')
        snap=fixture();snap['current_eps']['period'].update(start='2025-11-01',end='2026-10-31')
        self.assertEqual(self.build(snap)['rows'][0]['status'],'unavailable')
        snap=fixture();snap['current_eps']['as_of']='2026-09-15'
        self.assertEqual(self.build(snap)['rows'][0]['status'],'unavailable')

    def test_forward_forecast_date_and_horizon_are_explicit(self):
        for update in [{'forecast_as_of':'2026-10-21'},{'estimate_type':'model_projection'},
                       {'period':{'kind':'forward_annual','start':'2025-01-01','end':'2025-12-31'}}]:
            snap=fixture();snap['forward_eps'].update(update)
            self.assertEqual(self.build(snap)['rows'][1]['status'],'unavailable')
        snap=fixture();snap['forward_eps']['estimate_type']='company_guidance'
        self.assertEqual(self.build(snap)['rows'][1]['value'],'15')

    def test_source_metadata_required_but_never_claimed_authenticated(self):
        for field in ('url','document_id','sha256'):
            snap=fixture();snap['current_eps']['source'].pop(field)
            self.assertEqual(self.build(snap)['rows'][0]['status'],'unavailable')
        snap=fixture();snap['current_eps']['source']['url']='file:///private/fictional'
        self.assertEqual(self.build(snap)['rows'][0]['status'],'unavailable')
        self.assertIn('does not establish source authenticity',self.build(fixture())['provenance'])

    def test_no_float_nonfinite_or_invalid_price(self):
        for value in (2.0,'NaN','Infinity','0','-1'):
            snap=fixture();snap['price']['value']=value
            self.assertTrue(all(r['status']=='unavailable' for r in self.build(snap)['rows']))
        snap=fixture();snap['price']['value']='0.3';snap['current_eps']['value']='0.1'
        self.assertEqual(self.build(snap)['rows'][0]['value'],'3')

    def test_duplicate_input_ids_and_invalid_snapshot_version_rejected(self):
        snap=fixture();snap['current_eps']['id']=snap['price']['id']
        with self.assertRaises(ValueError):self.build(snap)
        snap=fixture();snap['version']='unknown'
        with self.assertRaises(ValueError):self.build(snap)

    def test_snapshot_file_binding_is_verified_and_source_metadata_remains_declared(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'fictional-snapshot.json';path.write_text(json.dumps(fixture()))
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            result=pe.load(path,as_of='2026-10-20',expected_sha256=digest)
            self.assertEqual(result['snapshot_binding']['sha256'],digest)
            self.assertTrue(result['snapshot_binding']['external_hash_verified'])
            self.assertEqual(result['rows'][0]['value'],'20')
            self.assertIn('Caller-provided source metadata',result['provenance'])
            path.write_text(path.read_text()+' ')
            with self.assertRaisesRegex(ValueError,'binding changed'):
                pe.load(path,as_of='2026-10-20',expected_sha256=digest)


if __name__=='__main__': unittest.main()
