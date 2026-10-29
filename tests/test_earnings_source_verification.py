import hashlib, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock
from research import earnings_source_verification as v, earnings_file_context as context, earnings_file_runner as transport

class SourceVerificationTests(unittest.TestCase):
    def setUp(self):
        self.text='[Page 1]\nQ3 2040\nThis report presents Fictional Widget’s continuing operations.\n'
        self.provenance={'verified_issuer_index':True,'matched_call':True,'exact_attachment':True,'report_text_sha256':hashlib.sha256(self.text.encode()).hexdigest()}
        self.answer={'verdict':'accept','reason':'Report scope explicitly names issuer.','issuer_quote':'This report presents Fictional Widget’s continuing operations.','period_quote':'Q3 2040\n','basis':'quarter'}
    def qualify(self,answer=None):
        return v.qualify(self.text,'Fictional Widget',(2040,3),self.provenance,Mock(return_value=answer or self.answer))
    def test_ambiguous_layout_uses_cited_model_evidence(self):
        result=self.qualify();self.assertEqual(result['decision_method'],'bounded_model')
        evidence=result['issuer_evidence'];self.assertEqual(self.text[evidence['start']:evidence['end']],evidence['text'])
    def test_deterministic_success_has_no_model_call(self):
        text='[Page 1]\nFictional Widget\nQ3 2040\n';cb=Mock(side_effect=AssertionError('unnecessary call'))
        p={**self.provenance,'report_text_sha256':hashlib.sha256(text.encode()).hexdigest()}
        self.assertEqual(v.qualify(text,'Fictional Widget',(2040,3),p,cb)['decision_method'],'deterministic')
    def test_explicit_validation_can_exercise_model_on_recognized_identity(self):
        text='[Page 1]\nFictional Widget\nQ3 2040\n'
        cb=Mock(return_value={**self.answer,'issuer_quote':'Fictional Widget','period_quote':'Q3 2040'})
        p={**self.provenance,'report_text_sha256':hashlib.sha256(text.encode()).hexdigest()}
        result=v.qualify(text,'Fictional Widget',(2040,3),p,cb,always_verify=True)
        self.assertEqual(result['decision_method'],'bounded_model');cb.assert_called_once()

    def test_wrong_period_never_calls_model(self):
        cb=Mock();
        with self.assertRaisesRegex(ValueError,'differs'):v.qualify(self.text,'Fictional Widget',(2040,2),self.provenance,cb)
        cb.assert_not_called()
    def test_provenance_failure_never_calls_model(self):
        for field in ('verified_issuer_index','matched_call','exact_attachment'):
            cb=Mock()
            with self.assertRaisesRegex(ValueError,'chain'):v.qualify(self.text,'Fictional Widget',(2040,3),{**self.provenance,field:False},cb)
            cb.assert_not_called()
    def test_wrong_source_hash_never_calls_model(self):
        with self.assertRaisesRegex(ValueError,'binding'):v.qualify(self.text,'Fictional Widget',(2040,3),{**self.provenance,'report_text_sha256':'wrong'},Mock())
    def test_reject_and_uncertain_are_terminal(self):
        for verdict in ('reject','uncertain'):
            with self.assertRaisesRegex(ValueError,verdict):self.qualify({**self.answer,'verdict':verdict})
    def test_invented_or_wrong_issuer_citations_rejected(self):
        for quote in ('Fictional Widget registration number 12345678','Q3 2040\n'):
            with self.assertRaises(ValueError):self.qualify({**self.answer,'issuer_quote':quote})
    def test_model_cannot_override_duration(self):
        with self.assertRaisesRegex(ValueError,'duration'):self.qualify({**self.answer,'basis':'nine_months'})
    def test_source_packet_is_bounded(self):
        text=('Fictional Widget '*100+'\n')*1000
        rows=v.excerpts(text,'Fictional Widget');self.assertTrue(rows);self.assertEqual(rows[0]['start'],0)
        self.assertLessEqual(sum(len(x['text'].encode()) for x in rows),v.LIMIT)
    def test_short_period_heading_is_valid(self):
        self.assertEqual(self.qualify({**self.answer,'period_quote':'Q3 2040'})['decision_method'],'bounded_model')

    def test_fiscal_label_may_differ_from_explicit_calendar_endpoint(self):
        text='[Page 1]\nThis report presents Fictional Widget continuing operations.\nFor the second quarter ended July 31, 2040\n'
        p={**self.provenance,'report_text_sha256':hashlib.sha256(text.encode()).hexdigest(),
           'event':{'fiscal_calendar':'document_defined','published_on':'2040-08-20'}}
        answer={**self.answer,'issuer_quote':'Fictional Widget continuing operations.',
                'period_quote':'second quarter ended July 31, 2040'}
        result=v.qualify(text,'Fictional Widget',(2041,2),p,Mock(return_value=answer))
        self.assertEqual(result['report_period']['end'],'2040-07-31')
        self.assertIsNone(result['report_period']['start'])
        with self.assertRaisesRegex(ValueError,'Dated reporting'):
            v.qualify(text,'Fictional Widget',(2041,2),p,Mock(return_value={**answer,'period_quote':'This report presents Fictional Widget'}))

    def test_transport_binding_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=root/'raw.txt';raw.write_text(self.text)
            packet={'version':'simple-report-v1','instructions':'Verify source','_original_files':{str(raw):v.case.sha(raw)}}
            index=v.assemble(packet,root/'context');reader=context.Evidence(index,root/'unused',_replay=True)
            prompt='Untrusted source evidence.\n'+reader._report_packet()
            transport._direct_packet(prompt,index,{'workflow':'simple-report-v1','role':'single_report_analysis'})
            raw.write_text('changed')
            with self.assertRaisesRegex(ValueError,'source changed'):context.Evidence(index,root/'unused',_replay=True)
