import unittest
from research import earnings_report_identity as identity
from research.financial_evidence import digest


class ReportIdentityTests(unittest.TestCase):
    def check_spans(self,text,result):
        for item in (result['issuer_evidence'],result['report_period']['evidence']):
            self.assertEqual(text[item['start']:item['end']],item['text'])
            self.assertEqual(digest(item['text'].encode()),item['sha256'])

    def test_combined_issuer_quarter_heading_with_audit_label(self):
        text='[Page 1]\nFICTIONAL MICRO | Q3 REPORT 2040 (UNAUDITED)\n'
        result=identity.recognize(text,'Fictional Micro',(2040,3))
        self.assertEqual(result['report_period']['start'],'2040-07-01')
        self.check_spans(text,result)

    def test_wrapped_names_and_both_quarter_title_orders(self):
        for heading in ('Q2\nREPORT\n2040','2040\nSecond-quarter results','Second quarter\n2040'):
            with self.subTest(heading=heading):
                text='[Page 1]\nFictional\nMicro\n'+heading+'\n'
                result=identity.recognize(text,'Fictional Micro',(2040,2))
                self.assertEqual(result['report_period']['start'],'2040-04-01')
                self.assertTrue(result['report_period']['standalone_quarter'])
                self.check_spans(text,result)

    def test_image_cover_contents_and_late_legal_identity(self):
        text='[Page 2]\nContents\nTHE HALF-YEAR FINANCIAL REPORT AT\n30 JUNE 2040\n'
        text+='[Page 3]\n'+('body prose '*5000)
        text+='\n[Page 15]\nGeneral information\nThe Group’s parent company is Fictional Micro SA.\n'
        result=identity.recognize(text,'Fictional Micro',(2040,2))
        self.assertEqual(result['issuer_evidence']['rule'],'explicit_legal_identity')
        self.assertEqual(result['report_period']['basis'],'half_year')
        self.assertEqual(result['report_period']['start'],'2040-01-01')
        self.assertFalse(result['report_period']['standalone_quarter'])
        self.check_spans(text,result)

    def test_cumulative_periods_remain_distinct(self):
        for heading,quarter,basis in [('H1 2040',2,'half_year'),('Nine-month report 2040',3,'nine_months'),('Annual report 2040',4,'full_year')]:
            with self.subTest(heading=heading):
                result=identity.recognize('[Page 1]\nFictional Micro\n'+heading,'Fictional Micro',(2040,quarter))
                self.assertEqual(result['report_period']['basis'],basis)
                self.assertEqual(result['report_period']['start'],'2040-01-01')
                self.assertFalse(result['report_period']['standalone_quarter'])

    def test_incidental_mentions_and_substrings_do_not_establish_issuer(self):
        for mention in ('Our competitor Fictional Micro announced results.','Fictional Microsystems','We acquired Fictional Micro assets.'):
            with self.subTest(mention=mention):
                with self.assertRaisesRegex(ValueError,'issuer'):
                    identity.recognize('[Page 1]\nOther Entity\nQ2 2040\n'+mention,'Fictional Micro',(2040,2))

    def test_old_report_cannot_qualify_using_later_comparative_heading(self):
        text='[Page 1]\nFictional Micro\nQ1 REPORT 2040\n\nQ2 REPORT 2040\n'
        with self.assertRaisesRegex(ValueError,'differs'):identity.recognize(text,'Fictional Micro',(2040,2))

    def test_wrong_year_quarter_and_conflicting_date_rejected(self):
        for heading in ('Q2 2039','Half-year report 2040','Half-year financial report at 31 December 2040'):
            with self.subTest(heading=heading):
                expected=(2040,3) if heading=='Half-year report 2040' else (2040,2)
                with self.assertRaises(ValueError):identity.recognize('[Page 1]\nFictional Micro\n'+heading,'Fictional Micro',expected)

    def test_body_period_reference_does_not_qualify_report(self):
        text='[Page 1]\nFictional Micro\nBusiness report\nCompared with Q2 2040, the business improved.'
        with self.assertRaisesRegex(ValueError,'heading'):identity.recognize(text,'Fictional Micro',(2040,2))

    def test_auditor_subject_across_legal_forms_and_report_layouts(self):
        for form in ('AB','AB (publ)','AB (publ.)','Group AB (publ.)','plc','AG','N.V.','Limited',''):
            for heading,verb,subject in (
                ('Review Report','reviewed','condensed interim report for'),
                ("Independent auditor’s report",'audited','consolidated financial statements of'),
                ('Report of independent auditors','reviewed','interim financial information of')):
                with self.subTest(form=form,heading=heading):
                    text='[Page 1]\nQ2 2040\n[Page 8]\n'+heading+'\nIntroduction\nWe have '+verb+' the '+subject+' Fictional Micro '+form+' as at June 30, 2040.\n'
                    result=identity.recognize(text,'Fictional Micro',(2040,2))
                    self.assertEqual(result['issuer_evidence']['rule'],'auditor_report_subject')
                    self.check_spans(text,result)

    def test_group_registration_and_as_per_auditor_subject(self):
        for body, rule in (
            ('Fictional Micro Group AB (publ.), corporate identity number 123456-7890', 'registered_issuer_block'),
            ('We have reviewed the condensed interim report for Fictional Micro Group AB (publ.) as per June 30, 2040.', 'auditor_report_subject')):
            text='[Page 1]\nQ2 2040\n[Page 9]\nReview report\n'+body+'\n'
            result=identity.recognize(text,'Fictional Micro',(2040,2))
            self.assertEqual(result['issuer_evidence']['rule'],rule)
            self.check_spans(text,result)

    def test_registration_blocks_and_wrapped_labels(self):
        for heading in ('Review Report','Corporate information','Company information','Registered office'):
            for label,value in (('org.no','123456-7890'),('Company registration number:','AB123456'),('Corporate identity number:','123456789'),('Business ID:','123456-7')):
                for separator in (', ','\n'):
                    text='[Page 1]\nQ2 2040\n[Page 9]\n'+heading+'\nFictional Micro AB'+separator+label+' '+value+'\n'
                    result=identity.recognize(text,'Fictional Micro',(2040,2))
                    self.assertEqual(result['issuer_evidence']['rule'],'registered_issuer_block')
                    self.check_spans(text,result)

    def test_identity_blocks_do_not_admit_mentions_or_other_entities(self):
        bad=[
            'Acquisitions\nFictional Micro AB, org.no 123456-7890',
            'Review Report\nOther Company AB, org.no 123456-7890',
            'Review Report\nFictional Microsystems AB, org.no 123456-7890',
            'Review Report\nFictional Micro Group Holdings AB, org.no 123456-7890',
            'Review Report\nFictional Micro Holdings AB, org.no 123456-7890',
            'Our auditor wrote: We have reviewed the interim report for Fictional Micro AB as at June 30, 2040.',
            'Review Report\nWe have not reviewed the interim report for Fictional Micro AB as at June 30, 2040.',
            'Review Report\nWe have reviewed the interim report for Other Company AB as at June 30, 2040. Fictional Micro is a competitor.',
            'Review Report\n[Page 10]\nFictional Micro AB, org.no 123456-7890',
            'Corporate information\nFictional Micro AB, Telephone: 123456789',
            'Review Report\nFictional Micro AB, org.no unavailable',
        ]
        for body in bad:
            with self.subTest(body=body),self.assertRaisesRegex(ValueError,'issuer'):
                identity.recognize('[Page 1]\nQ2 2040\n[Page 9]\n'+body,'Fictional Micro',(2040,2))

    def test_report_running_headers_with_page_counters(self):
        for form in ('',' AB (publ)',' Group AB (publ.)'):
            for counter in ('',' Page 2 of 21',' 2 / 21'):
                text='[Page 1]\nQ2 2040\n[Page 2]\nFictional Micro'+form+' Interim Report Q2 2040'+counter+'\n'
                result=identity.recognize(text,'Fictional Micro',(2040,2))
                self.assertEqual(result['issuer_evidence']['rule'],'issuer_report_running_heading')
                self.check_spans(text,result)

    def test_statutory_publisher_statement(self):
        text='[Page 1]\nQ2 2040\n[Page 20]\nNote: Fictional Micro AB (publ) is required to publish the information in this report.\n'
        result=identity.recognize(text,'Fictional Micro',(2040,2))
        self.assertEqual(result['issuer_evidence']['rule'],'statutory_publishing_issuer')
        self.check_spans(text,result)

    def test_statutory_disclosure_preamble(self):
        text='[Page 1]\nQ2 2040\n[Page 20]\nThis is information that Fictional Micro AB is obliged to make public pursuant to the market rules.\n'
        result=identity.recognize(text,'Fictional Micro',(2040,2))
        self.assertEqual(result['issuer_evidence']['rule'],'statutory_publishing_issuer')
        self.check_spans(text,result)

    def test_running_header_rejects_competitors_and_body_mentions(self):
        for line in ('Other Entity Interim Report Q2 2040 Page 2 of 21',
                     'Fictional Microsystems Interim Report Q2 2040 Page 2 of 21',
                     'We compare Fictional Micro Interim Report Q2 2040 Page 2 of 21',
                     'Fictional Micro Holdings Interim Report Q2 2040 Page 2 of 21',
                     'Fictional Micro is not required to publish the information',
                     'Our supplier Fictional Micro is required to publish the information'):
            with self.subTest(line=line),self.assertRaisesRegex(ValueError,'issuer'):
                identity.recognize('[Page 1]\nQ2 2040\n'+line,'Fictional Micro',(2040,2))

    def test_new_identity_evidence_does_not_relax_period_checks(self):
        text='[Page 1]\nQ1 2040\n[Page 8]\nReview Report\nFictional Micro AB, org.no 123456-7890\n'
        with self.assertRaisesRegex(ValueError,'differs'):
            identity.recognize(text,'Fictional Micro',(2040,2))


if __name__=='__main__':unittest.main()
