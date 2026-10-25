"""Fictitious model mappings, deterministic arithmetic, provenance and stage costs."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_financial_selection as selection
from research import earnings_financial_analysis_report as report
from research import earnings_financial_statement_context as statements
from research import earnings_sequential as core
from research import earnings_runtime_common as storage
from test_earnings_financial_statement_context import fixture,Q,PY,rows


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.bundle=fixture(self.root,[('fiction:Revenue',120,Q,'Revenue'),('fiction:Revenue',100,PY,'Revenue'),
            ('fiction:CashFlow',30,Q,'Operating cash'),('fiction:Purchases',10,Q,'Gross PP&E purchases')],declaration=None)
        self.scopes=patch.object(selection.evidence,'_scopes',return_value={'D001':{},**{o['id']:{} for o in self.bundle['financial']['observations']}})
        self.scopes.start();self.addCleanup(self.scopes.stop)
        self.value={'rows':[self.row('revenue',['F001','F002']),self.row('operating_cash_flow',['F003']),self.row('capital_expenditure',['F004'])],
            'gaps':[{'metric':m,'reason':'Fictional original statements do not provide this metric.','citations':['D001']} for m in sorted(selection.REQUIRED-{'revenue','operating_cash_flow','capital_expenditure'})],
            'notes':[{'text':'Free cash flow uses operating cash flow less gross PP&E purchases.','citations':['D001']}]}

    def row(self,metric,ids):return {'metric':metric,'label':metric.replace('_',' '),'basis':'GAAP','fact_ids':ids,'citations':['D001'],'definition':'Fictional consolidated original statement definition.'}
    def build(self):return report.compile(selection.apply(statements.qualify(self.bundle),self.value),report.configuration(*Q))

    def test_custom_concepts_map_without_changing_facts_and_arithmetic_is_code(self):
        original=copy.deepcopy(self.bundle);value=self.build()
        self.assertEqual(self.bundle,original)
        self.assertEqual(rows(value,'revenue')[0]['changes']['yoy']['percent'],'20.0')
        self.assertEqual(rows(value,'free_cash_flow')[0]['cells']['current']['value'],'20')
        self.assertEqual(value['observations'],original['financial']['observations'])
        self.assertIn('20%',report.preview_markdown(value))
        self.assertIn('Free cash flow equals', '\n'.join(report.notes(value)))

    def test_missing_core_metric_or_fabricated_value_is_rejected(self):
        self.value['gaps']=[]
        with self.assertRaisesRegex(ValueError,'Every core metric'):selection.validate(self.value,self.bundle)
        self.value['rows'][0]['value']='999'
        with self.assertRaisesRegex(ValueError,'Exact selected row'):selection.validate(self.value,self.bundle)

    def test_unknown_nil_proposed_and_duplicate_fact_ids_rejected(self):
        for mutation in ('unknown','nil','proposed','duplicate'):
            v=copy.deepcopy(self.value);b=copy.deepcopy(self.bundle)
            if mutation=='unknown':v['rows'][0]['fact_ids']=['F999']
            elif mutation=='nil':b['financial']['observations'][0]['nil']=True
            elif mutation=='proposed':b['financial']['observations'][0]['status']='proposed'
            else:v['rows'][1]['fact_ids']=['F001']
            with self.assertRaises(ValueError):selection.validate(v,b)

    def test_units_class_and_period_conflicts_rejected(self):
        b=copy.deepcopy(self.bundle);obs=b['financial']['observations'];c=b['financial']['contexts'][obs[1]['context_id']]
        c['dimensions']=[{'dimension':'fiction:Segment','member':'fiction:Different'}]
        with self.assertRaises(ValueError):selection.validate(self.value,b)
        c['dimensions']=[];c['start_date']=Q[0];c['end_date']=Q[1]
        with self.assertRaisesRegex(ValueError,'Conflicting'):selection.validate(self.value,b)

    def test_different_share_classes_are_separate_and_visible(self):
        b=copy.deepcopy(self.bundle);v=copy.deepcopy(self.value)
        for i in (0,1):
            o=b['financial']['observations'][i];c=b['financial']['contexts'][o['context_id']]
            c.update(start_date=Q[0],end_date=Q[1],dimensions=[{'dimension':'us-gaap:StatementClassOfStockAxis','member':'fiction:Class'+str(i)}])
            # Each fact has its own copied unit, preventing accidental shared mutation.
            uid='EPS'+str(i);b['financial']['units'][uid]={'numerator':['iso4217:USD'],'denominator':['xbrli:shares']};o['unit_id']=uid
        v['rows']=[self.row('diluted_eps',['F001']),self.row('diluted_eps',['F002']),*v['rows'][1:]]
        v['rows'][0]['label']='Diluted EPS voting';v['rows'][1]['label']='Diluted EPS non-voting'
        v['gaps']=[g for g in v['gaps'] if g['metric']!='diluted_eps']+[{'metric':'revenue','reason':'Fictional gap.','citations':['D001']}]
        value=report.compile(selection.apply(statements.qualify(b),v),report.configuration(*Q))
        self.assertEqual(len(report.front_rows(value)['earnings']),2)
        self.assertIn('Diluted EPS non-voting',report.preview_markdown(value))
        v['rows'][0]['fact_ids'].append('F002');v['rows'].pop(1)
        with self.assertRaises(ValueError):selection.validate(v,b)

    def test_basis_needs_original_document_and_cannot_contradict_source(self):
        self.value['rows'][0]['citations']=['F001']
        with self.assertRaisesRegex(ValueError,'statement/note'):selection.validate(self.value,self.bundle)

    def test_record_rejects_changed_sources_and_map(self):
        manifest=self.root/'manifest.json';manifest.write_text('{}')
        record=selection.record(self.bundle,manifest,self.value)
        selection.verify_record(self.bundle,manifest,record)
        changed=copy.deepcopy(self.bundle);changed['financial']['observations'][0]['value']='121'
        with self.assertRaisesRegex(ValueError,'inputs changed'):selection.verify_record(changed,manifest,record)
        manifest.write_text('{"changed":true}')
        with self.assertRaises(ValueError):selection.verify_record(self.bundle,manifest,record)

    def test_fcf_acronym_is_the_same_explicit_convention(self):
        self.value['notes'][0]['text']='FCF equals operating cash flow less gross purchases.'
        selection.validate(self.value,self.bundle)

    def test_fcf_requires_explicit_convention(self):
        self.value['notes']=[]
        with self.assertRaisesRegex(ValueError,'FCF convention'):selection.validate(self.value,self.bundle)

    def test_fcf_definition_in_capex_row_needs_no_duplicate_note(self):
        before=self.build()
        self.value['notes']=[]
        self.value['rows'][2]['definition']='Positive gross PP&E purchases. FCF is same-period operating cash flow minus these gross purchases.'
        selection.validate(self.value,self.bundle)
        after=self.build()
        self.assertEqual(rows(before,'free_cash_flow'),rows(after,'free_cash_flow'))

    def test_unrelated_metric_cannot_supply_the_fcf_convention(self):
        self.value['notes']=[]
        self.value['rows'][0]['definition']='FCF uses operating cash flow less gross purchases.'
        with self.assertRaisesRegex(ValueError,'FCF convention'):selection.validate(self.value,self.bundle)


class SelectionStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        core.create(self.root,{'budget_tokens':1000});core.bind_execution_code(self.root,'a'*40,financial_selection=True)
    def handler(self,stage):
        def run(root,job):
            name='financial-selection-r0.json' if stage=='financial_selection' else stage+'.json'
            (root/name).write_text('{}');out={'status':'completed','tokens':25 if stage=='financial_selection' else 0,'outputs':{name:storage.sha(root/name)}}
            if stage=='financial_selection':out.update(session_id='fictional-selection',execution_certainty='completed')
            return out
        return run
    def test_selection_is_accounted_before_deterministic_tables(self):
        handlers={s:self.handler(s) for s in ('sources','financial_selection','financial_tables')}
        self.assertEqual(core.advance(self.root,handlers)['stage'],'financial_selection')
        job=core.advance(self.root,handlers);self.assertEqual(job['stage'],'financial_tables');self.assertEqual(job['tokens_used'],25)
        self.assertEqual(job['financial_selection_artifact'],'financial-selection-r0.json')
        self.assertEqual(core.advance(self.root,handlers)['stage'],'analysis')
    def test_selection_cannot_declare_safe_replay(self):
        core.advance(self.root,{'sources':self.handler('sources')})
        fn=self.handler('financial_selection');fn.replay_safe=True
        job=core.advance(self.root,{'financial_selection':fn});self.assertEqual(job['status'],'blocked');self.assertEqual(job['tokens_used'],0)
    def test_paid_failed_selection_keeps_usage_and_stops(self):
        core.advance(self.root,{'sources':self.handler('sources')})
        job=core.advance(self.root,{'financial_selection':lambda root,job:{'status':'blocked','tokens':25,'outputs':{},'reason':'fictional invalid mapping'}})
        self.assertEqual(job['status'],'blocked');self.assertEqual(job['tokens_used'],25)
    def test_saved_selection_recovery_preserves_charged_usage(self):
        core.advance(self.root,{'sources':self.handler('sources')})
        core.advance(self.root,{'financial_selection':lambda root,job:{'status':'blocked','tokens':25,'outputs':{},'execution_certainty':'completed','reason':'Fictional validator bug'}})
        def recover(root,job):
            name='financial-selection-r0.json';(root/name).write_text('{}');(root/'receipt.json').write_text('{}')
            return {'outputs':{name:storage.sha(root/name)},'proof_outputs':{'receipt.json':storage.sha(root/'receipt.json')},'tokens':25,'session_id':'original-fake-session'}
        job=core.adopt_financial_selection(self.root,'Fix validator without rerunning model','b'*40,recover)
        self.assertEqual((job['tokens_used'],job['budget_tokens'],job['revision_round']),(25,1000,0))
        self.assertEqual(job['stage'],'financial_tables');self.assertEqual(len(job['attempts']),2)
        self.assertEqual(job['administrative_history'][-1]['additional_tokens'],0)
        with self.assertRaises(ValueError):core.adopt_financial_selection(self.root,'again','b'*40,recover)

    def test_unknown_selection_cannot_be_recovered(self):
        core.advance(self.root,{'sources':self.handler('sources')})
        core.advance(self.root,{'financial_selection':lambda root,job:{'status':'blocked','tokens':25,'outputs':{},'execution_certainty':'unknown'}})
        with self.assertRaises(ValueError):core.adopt_financial_selection(self.root,'unsafe','b'*40,lambda root,job:{})


class SelectionIntegrationTests(unittest.TestCase):
    def setUp(self):
        from test_earnings_compact_evidence import fixture as case_fixture
        from research import earnings_sequential_stages as stages,earnings_file_context as context
        self.stages,self.context=stages,context
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        case,_,_=case_fixture(self.root);writing=self.root/'writing.md';writing.write_text('Fictional concise report.')
        self.job=self.root/'job';core.create(self.job,{'case_path':str(case),'writing_standard':str(writing),'financial_analysis':report.configuration('2040-01-01','2040-03-31')})
        core.bind_execution_code(self.job,'a'*40,financial_selection=True)
        core.advance(self.job,stages.handlers());self.skip=False
        self.patch=patch.object(stages.runner,'run_role',side_effect=self.run_model);self.patch.start();self.addCleanup(self.patch.stop)
        self.delivery=patch.object(context,'delivered_entries',side_effect=lambda root,entries:entries);self.delivery.start();self.addCleanup(self.delivery.stop)
    def run_model(self,role,prompt,model,effort,bindings,index,**kwargs):
        role.mkdir(parents=True);reader=self.context.Evidence(index,role/'retrieval.jsonl')
        if not self.skip:
            for i in range(len(reader.role_batch_plan())):reader.role_batch(i)
            reader.source_batch(['D001'])
        fid=next(o['id'] for o in json.loads((self.job/'sources/financial.json').read_text())['observations'] if o.get('concept')=='us-gaap:Revenues')
        value={'rows':[{'metric':'revenue','label':'Fictional revenue','basis':'GAAP','fact_ids':[fid],'citations':['D001'],'definition':'Fictional consolidated revenues.'}],
            'gaps':[{'metric':metric,'reason':'Fictional source gap.','citations':['D001']} for metric in sorted(selection.REQUIRED-{'revenue'})],'notes':[]}
        return {'content':value,'receipt':{'session':{'id':'fake-selector','usage':{'totalTokens':123}}}}
    def test_broad_inventory_selection_contract_and_zero_token_tables(self):
        from research import earnings_compact_evidence as e,earnings_sequential_financial_contract as contract
        b=e.load_bundle(self.job/'sources/manifest.json');packet=selection.compact(b)
        self.assertEqual([fid for r in packet['facts'] for fid in r[0]],[o['id'] for o in b['financial']['observations']])
        self.assertEqual(packet['omitted_observations'],0)
        raw=(self.job/'sources/financial.json').read_bytes()
        job=core.advance(self.job,self.stages.handlers());self.assertEqual(job['stage'],'financial_tables',job.get('reason'))
        job=core.advance(self.job,self.stages.handlers());self.assertEqual(job['stage'],'analysis',job.get('reason'))
        self.assertEqual(job['tokens_used'],123);self.assertEqual(job['attempts'][-1]['outcome']['tokens'],0)
        self.assertEqual((self.job/'sources/financial.json').read_bytes(),raw)
        self.assertEqual(contract.build(self.job)['verification'],'reproduced')
        (self.job/'financial-selection-r0.json').write_text('{}')
        with self.assertRaises(ValueError):contract.build(self.job)
    def test_unread_inventory_stops_before_author_and_accounts_usage(self):
        self.skip=True;job=core.advance(self.job,self.stages.handlers())
        self.assertEqual(job['status'],'blocked');self.assertEqual(job['tokens_used'],123)
        self.assertIn('inventory inspection',job['reason'])
        self.assertFalse((self.job/'financial-analysis.json').exists())
