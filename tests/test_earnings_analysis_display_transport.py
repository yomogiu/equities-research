"""Fictional layout-only display continuation; no real sources or providers."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_analysis_display_transport as t
from research import earnings_financial_display as display, earnings_mixed_runner as b
from research import earnings_prepared_analysis as prepared_analysis, earnings_prepared_retrieval as prepared
from research import earnings_file_pipeline as pipeline, earnings_financial_outline as outline
from research import earnings_qa_grounding as grounding, earnings_file_context as context
from test_earnings_passages import PassageFixture


class LayoutTests(unittest.TestCase):
    def test_only_standalone_terminal_layout_dots_removed(self):
        label='Equipment (related party $47 and $29, fictional periods)'
        self.assertEqual(display.strip_terminal_dot_leader(label+' '+'.'*200),label)
        for preserved in ('U.S. revenue','Margin 4.25','Uncertain ...','A ....','Revenue.....','A ..... B','A …','A . . . . .'):
            with self.subTest(label=preserved):self.assertEqual(display.strip_terminal_dot_leader(preserved),preserved)

    def test_equivalence_retains_all_values_units_periods_basis_and_original(self):
        raw='Fictional equipment '+'.'*200;clean='Fictional equipment';basis='GAAP (unaudited)'
        obs={'method':'reviewed_html_table','support':{'source_label':raw},'accounting_basis':basis}
        before={'row-fake':{'row':{'metric':raw+' ('+basis+')','cells':[{'value':'47','fact_ids':['F1']}],'dimensions':''},'unit':'USD','periods':['fictional']}}
        after=copy.deepcopy(before);after['row-fake']['row']['metric']=clean+' ('+basis+')'
        original=copy.deepcopy(before);proof=t.verify_label_equivalence(before,after,[obs])
        self.assertEqual(len(proof),1);self.assertEqual(before,original);self.assertEqual(obs['support']['source_label'],raw)
        for field,value in [('cells',[{'value':'48','fact_ids':['F1']}]),('metric','Equipment'),('dimensions','changed')]:
            bad=copy.deepcopy(after);bad['row-fake']['row'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):t.verify_label_equivalence(before,bad,[obs])
        with self.assertRaises(ValueError):t.verify_label_equivalence(before,{},[obs])

    def test_display_cleanup_preserves_legacy_and_strict_grouping(self):
        from test_earnings_financial_display import fixture
        from research import earnings_financial_context as financial_context
        selected,bundle=fixture();selected['rows']=[{'label':'Fictional selection','fact_ids':['F1','F2']}]
        for i,observation in enumerate(bundle['financial']['observations'][:2]):
            observation.update(method='reviewed_html_table',accounting_basis='GAAP',
                               support={'source_label':'Fictional revenue '+'.'*(20+i)})
        original=copy.deepcopy(bundle)
        legacy=display.build(selected,bundle)
        self.assertEqual(sum(len(g['rows']) for g in legacy['groups']),2)
        self.assertTrue(all(r['metric']=='Fictional revenue (GAAP)' for g in legacy['groups'] for r in g['rows']))
        selected['_display_contract']=financial_context.DISPLAY_CONTRACT
        identities={fid:{'label':'Fictional revenue','basis':'GAAP','label_origin':'exact_source_cells'} for fid in ('F1','F2')}
        with patch.object(financial_context,'source_identities',return_value=identities):
            strict=display.build(selected,bundle)
        self.assertEqual(sum(len(g['rows']) for g in strict['groups']),1)
        self.assertEqual(bundle,original)

    def test_exact_manifest_replay_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);case=root/'case';case.write_text('Fictional case');catalog={'fake':True}
            value={'version':t.VERSION,'previous_root':'original','case_sha256':b.sha(case),'catalog_sha256':b.digest(catalog),'tokens':123}
            path=root/'prepared';b.save(path,value)
            with patch.object(t,'derive',return_value=value):
                self.assertEqual(t.verify(path,case,catalog),value)
                path.unlink();b.save(path,{**value,'tokens':0})
                with self.assertRaises(ValueError):t.verify(path,case,catalog)


class PipelineTests(PassageFixture,unittest.TestCase):
    def setup_prepared(self):
        self.writing=self.root/'writing';self.writing.write_text('Fictional writing')
        self.retrieval_value={'version':'authenticated-exact-retrieval-identity-transport-v1','tokens':12000,'max_tokens':200000,
           'session_id':'fictional-retrieval','session_ids':['fictional-retrieval'],'models':copy.deepcopy(pipeline.ORIGINAL_MODELS),
           'writing_sha256':b.sha(self.writing),'report_template':pipeline.template.VERSION,'content':self.retrieval,
           'grounding':grounding.build(self.bundle,self.catalog,version=grounding.NAMED_GREETING_VERSION),'derivation':{'fake':'identity'}}
        self.retrieval_path=(self.root/'retrieval-prepared').resolve();b.save(self.retrieval_path,self.retrieval_value)
        content=copy.deepcopy(self.report);content['report_template']=pipeline.template.VERSION
        for finding,section in zip(content['findings'],('demand','earnings','outlook','qa')):finding['section']=section
        self.analysis_value={'version':t.VERSION,'tokens':24000,'analysis_tokens':12000,'max_tokens':200000,
           'analysis_session_id':'fictional-analysis','session_ids':['fictional-retrieval','fictional-analysis'],
           'models':copy.deepcopy(pipeline.ORIGINAL_MODELS),'writing_sha256':b.sha(self.writing),
           'report_template':pipeline.template.VERSION,'content':content,'spent_correction_rounds':0,
           'retrieval_preparation_path':str(self.retrieval_path),'retrieval_preparation_sha256':b.sha(self.retrieval_path),
           'derivation':{'fake':'layout only'}}
        self.analysis_path=self.root/'analysis-prepared';b.save(self.analysis_path,self.analysis_value)
        self.output=self.root/'continued'
        pipeline.initialize(self.casepath,self.output,self.writing,preparation=self.retrieval_path,analysis_preparation=self.analysis_path,max_tokens=200000)

    def test_init_load_preview_and_acceptance_retain_both_sessions_and_content(self):
        import test_earnings_file_pipeline as fixtures
        from research import earnings_file_runner as runner
        self.drain=fixtures.FilePipelineTests.drain.__get__(self);self.pack=fixtures.FilePipelineTests.pack.__get__(self)
        fake_run=fixtures.FilePipelineTests.fake_run.__get__(self)
        with patch.object(prepared,'verify',side_effect=lambda *a:self.retrieval_value),patch.object(prepared_analysis,'verify',side_effect=lambda *a:self.analysis_value):
            self.setup_prepared();p,bundle,_=pipeline.load(self.output)
            self.assertEqual(p['inherited_tokens'],24000);self.assertNotIn('analysis_repair_rounds',p)
            with patch.object(outline,'artifact',return_value=self.financial),patch.object(runner,'run_role',side_effect=fake_run) as run:
                result=pipeline.advance(self.output,False)
                self.assertEqual((result['stage'],result['tokens']),('signal_author',24000));run.assert_not_called()
                for _ in range(4):
                    result=pipeline.advance(self.output,True)
                    if result['status']=='accepted':break
            self.assertEqual(result['status'],'accepted');self.assertEqual(result['tokens'],24080);self.assertEqual(result['correction_rounds'],0)
            self.assertEqual({p.name for p in (self.output/'jobs').iterdir()},{'signal_author','review-0'})
            self.assertEqual(b.read(self.output/'contexts/review-0/artifacts.json')['analysis_display_transport_provenance'],self.analysis_value['derivation'])

    def test_nonlayout_long_label_stops_before_any_provider_launch(self):
        from research import earnings_file_runner as runner
        self.writing=self.root/'writing';self.writing.write_text('Fictional guide');root=self.root/'preflight'
        pipeline.initialize(self.casepath,root,self.writing)
        # A substantive 161-character metric cannot be silently shortened.
        longrow={'row':{'metric':'x'*161,'dimensions':'','cells':[{'fact_ids':['F002']}]}}
        with patch.object(outline,'artifact',return_value=self.financial),patch.object(pipeline.mechanical.repair,'row_catalog',return_value={'fake':longrow}),patch.object(runner,'run_role') as run:
            with self.assertRaisesRegex(ValueError,'Bounded plain-text labels'):pipeline.advance(root,True)
            run.assert_not_called()
        self.assertFalse((root/'jobs').exists())
