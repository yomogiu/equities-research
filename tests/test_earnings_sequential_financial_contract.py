"""Fictional, zero-model financial contracts and adversarial frozen inputs."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_earnings_compact_evidence import fixture, refreeze, write
from research import earnings_sequential as controller
from research import earnings_sequential_stages as stages
from research import earnings_sequential_financial_contract as contract
from research import earnings_financial_analysis_report as finance
from research import earnings_mixed_runner as storage
from research import financial_evidence


class SequentialFinancialContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.case_path,self.case,_ = fixture(self.root)
        self.writing = self.root/'writing.md'; self.writing.write_text('Fictional reporting standard.')
        self.job = self.root/'job'

    def prepare(self):
        controller.create(self.job,{'case_path':str(self.case_path),'writing_standard':str(self.writing),
            'financial_analysis':finance.configuration('2040-01-01','2040-03-31')})
        controller.advance(self.job,stages.handlers())
        controller.advance(self.job,stages.handlers())

    def repin(self,name):
        job=storage.read(self.job/'job.json');job['artifacts'][name]=storage.sha(self.job/name)
        write(self.job/'job.json',job)

    def test_contract_reproduces_tables_and_trusts_only_displayed_quantitative_ids(self):
        self.prepare()
        before={str(path):storage.sha(path) for path in self.job.rglob('*') if path.is_file()}
        with patch.object(stages.runner,'run_role',side_effect=AssertionError('Model call forbidden')):
            result=contract.build(self.job)
        self.assertEqual(result,contract.build(self.job))
        self.assertEqual(result['verification'],'reproduced')
        facts=storage.read(self.job/'sources/financial.json')['observations']
        revenue=next(row['id'] for row in facts if row['concept']=='us-gaap:Revenues')
        self.assertEqual(result['trusted_table_ids'],[revenue])
        for row in facts:
            if row['id'] != revenue:self.assertNotIn(row['id'],result['trusted_table_ids'])
        self.assertEqual(result['contract_sha256'],storage.digest({k:v for k,v in result.items() if k!='contract_sha256'}))
        self.assertTrue(result['references'])
        self.assertNotIn('complete_financial_inventory',result)
        self.assertIn('do not substantiate qualitative claims',result['scope'])
        self.assertEqual(before,{str(path):storage.sha(path) for path in self.job.rglob('*') if path.is_file()})

    def test_source_mutation_is_rejected_without_refreshing_hashes(self):
        self.prepare();(self.root/'filing.html').write_text('Changed fictional source')
        with self.assertRaisesRegex(ValueError,'Frozen input changed'):contract.build(self.job)

    def test_table_mutation_is_rejected_even_if_new_file_hash_is_rebound(self):
        self.prepare();path=self.job/'financial-tables.md';path.write_text(path.read_text()+'\nAltered table\n')
        with self.assertRaisesRegex(ValueError,'Frozen financial artifact changed'):contract.build(self.job)
        self.repin('financial-tables.md')
        with self.assertRaisesRegex(ValueError,'deterministic rendering'):contract.build(self.job)

    def test_calculation_mutation_is_rejected_even_if_new_file_hash_is_rebound(self):
        self.prepare();path=self.job/'financial-analysis.json';value=storage.read(path)
        value['tables'][0]['rows'][0]['cells']['current']['value']='999'
        write(path,value);self.repin('financial-analysis.json')
        with self.assertRaisesRegex(ValueError,'source recomputation'):contract.build(self.job)

    def test_configuration_mutation_cannot_override_the_explicit_job_request(self):
        self.prepare();path=self.job/'financial-configuration.json'
        write(path,finance.configuration('2040-04-01','2040-06-30'));self.repin('financial-configuration.json')
        with self.assertRaisesRegex(ValueError,'job specification'):contract.build(self.job)

    def test_unknown_policy_is_rejected(self):
        self.prepare();path=self.job/'financial-analysis.json';value=storage.read(path)
        value['source_policy']='invented-policy';write(path,value);self.repin('financial-analysis.json')
        with self.assertRaisesRegex(ValueError,'Unsupported financial source policy'):contract.build(self.job)

    def test_mutated_extracted_fact_is_not_trusted_even_after_local_repin(self):
        self.prepare();path=self.job/'sources/financial.json';facts=storage.read(path)
        next(row for row in facts['observations'] if row['method']=='inline_xbrl')['value']='999';write(path,facts)
        manifest=storage.read(self.job/'sources/manifest.json')
        manifest['file_sha256']['financial']=storage.sha(path)
        write(self.job/'sources/manifest.json',manifest);self.repin('sources/manifest.json')
        with self.assertRaisesRegex(ValueError,'original-source extraction'):contract.build(self.job)

    def test_gaps_and_unstated_basis_are_reproduced_not_approved_as_quality(self):
        self.prepare();result=contract.build(self.job)
        self.assertTrue(result['audit']['gap_disclosures'])
        self.assertTrue(result['audit']['displayed_metrics'][0]['missing_comparisons'])
        self.assertIsNone(result['audit']['displayed_metrics'][0]['basis'])
        self.assertIn('gaps are not approval',' '.join(result['limitations']))
        self.assertNotIn('accepted',result)
        self.assertNotIn('quality_pass',result)

    def test_mixed_units_remain_separate_and_cannot_create_a_margin(self):
        raw_path=self.root/'filing.html';raw=raw_path.read_text()
        raw=raw.replace('<table>','<xbrli:unit id="eur"><xbrli:measure>iso4217:EUR</xbrli:measure></xbrli:unit>'
                        '<ix:nonNumeric name="us-gaap:BasisOfAccounting" contextRef="c">The consolidated financial statements are prepared in accordance with United States generally accepted accounting principles.</ix:nonNumeric><table>',1)
        raw=raw.replace('name="fiction:Widget" contextref="c" unitref="u"','name="us-gaap:GrossProfit" contextref="c" unitref="eur"')
        raw_path.write_text(raw)
        source={'document_id':'fictional-filing','raw_sha256':storage.sha(raw_path),'text_sha256':storage.sha(self.root/'filing.txt')}
        artifact=financial_evidence.extract_inline_xbrl(raw,source)
        write(self.root/'financial-source.json',artifact)
        refreeze(self.case_path,self.case,raw_path)
        refreeze(self.case_path,self.case,self.root/'financial-source.json')
        self.prepare();result=contract.build(self.job)
        self.assertFalse(any(row['metric']=='gross_margin' for row in result['audit']['displayed_metrics']))
        self.assertTrue(any('Gross margin' in gap['reason'] for gap in result['audit']['gap_disclosures']))
        self.assertEqual(result['trusted_table_ids'],['F001'])


if __name__=='__main__':unittest.main()
