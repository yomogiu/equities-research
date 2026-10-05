"""Fictitious presentation-only routing: no numeric facts are edited or dropped."""
import copy
import html
from unittest.mock import patch
import unittest
from research import earnings_report_repair as repair


class CompactLayoutTests(unittest.TestCase):
    def setUp(self):
        self.periods = [{'key': ['instant', '2040-01-01'], 'label': 'Jan 1, 2040'}]
        def row(concept, value, fid):
            return {'concept': concept, 'metric': concept, 'dimensions': 'Fictional segment',
                    'cells': [{'value': value, 'fact_ids': [fid]}]}
        self.groups = [
            {'periods': self.periods, 'unit': 'USD millions', 'rows': [
                row('Revenue', '12.34', 'F001'), row('Lease commitments', '4.56', 'F003'),
                row('Lease present value', '3.21', 'F004')]},
            {'periods': self.periods, 'unit': 'ratio', 'rows': [row('Share of revenue', '0.42', 'F002')]}]
        self.model = {'groups': self.groups}
        self.financial = {'rows': [{'fact_ids': ['F001', 'F002', 'F003', 'F004']}]}
        self.bundle = {}
        mock = patch.object(repair.display, 'build', return_value=self.model)
        mock.start(); self.addCleanup(mock.stop)
        mock = patch.object(repair.legacy, 'ids_for', return_value={'D001', 'F001', 'F002', 'F003', 'F004'})
        mock.start(); self.addCleanup(mock.stop)
        self.keys = {v['row']['concept']: k for k, v in repair.row_catalog(self.financial, self.bundle).items()}
        self.spec = {'rows': {}, 'basis': {'text': 'Fictional lease accounting basis.', 'citations': ['D001']},
                     'layout': {'version': 'compact-financial-v1',
                                'fold': [{'row_id': self.keys['Share of revenue'], 'into_row_id': self.keys['Revenue'], 'label': 'Share'}],
                                'detail_rows': [self.keys['Lease commitments'], self.keys['Lease present value']],
                                'summaries': [{'text': 'Fictional leases total 4.56, with present value 3.21.',
                                               'citations': ['D001'], 'row_ids': [self.keys['Lease commitments'], self.keys['Lease present value']]}],
                                'basis_position': 'after_tables'}}

    @staticmethod
    def refs(ids):
        return ' '.join('<a href="#e-' + html.escape(i) + '">' + html.escape(i) + '</a>' for i in ids)

    def test_compact_render_preserves_every_numeric_cell_and_plain_review_detail(self):
        before = copy.deepcopy((self.financial, self.bundle, self.model, self.spec))
        content = repair.table(self.financial, self.bundle, self.spec, self.refs)
        text = repair.table(self.financial, self.bundle, self.spec)
        self.assertEqual(before, (self.financial, self.bundle, self.model, self.spec))
        self.assertEqual(content.count('<table>'), 2)
        self.assertIn('Share of revenue · Fictional segment (ratio): 0.42', content)
        self.assertNotIn('42%', content)
        detail = content.split('<details class="financial-detail">')[1]
        for fid, value in [('F001', '12.34'), ('F002', '0.42'), ('F003', '4.56'), ('F004', '3.21')]:
            self.assertIn('href="#e-' + fid + '"', content)
            self.assertIn(value + ' [' + fid + ']', text)
        self.assertIn('4.56', detail); self.assertIn('3.21', detail)
        self.assertLess(content.index('Fictional leases total'), content.index('Fictional lease accounting basis.'))
        self.assertLess(content.index('Fictional lease accounting basis.'), content.index('<details'))
        review = repair.rendered_review_view(content + '<h2>Original evidence</h2>')
        self.assertIn(detail, review['report_body_html_excerpt'])
        self.assertIn('Financial detail', text)

    def test_legacy_two_field_format_remains_valid(self):
        spec = {k: v for k, v in self.spec.items() if k != 'layout'}
        repair.validate_format(spec, self.financial, self.bundle)
        content = repair.table(self.financial, self.bundle, spec, self.refs)
        self.assertNotIn('<details', content)
        self.assertLess(content.index('Fictional lease accounting basis.'), content.index('<table>'))

    def test_unknown_duplicate_ids_fields_and_versions_rejected(self):
        mutations = [
            lambda x: x.update(version='unknown'),
            lambda x: x.update(code='execute()'),
            lambda x: x.update(detail_rows=['unknown']),
            lambda x: x['detail_rows'].append(x['detail_rows'][0]),
            lambda x: x['fold'].append(copy.deepcopy(x['fold'][0])),
            lambda x: x['fold'][0].update(row_id='unknown'),
            lambda x: x['fold'][0].update(into_row_id='unknown'),
            lambda x: x['fold'][0].update(into_row_id=x['fold'][0]['row_id']),
            lambda x: x['fold'][0].update(executable='code'),
            lambda x: x['detail_rows'].append(x['fold'][0]['row_id']),
            lambda x: x['detail_rows'].append(x['fold'][0]['into_row_id']),
            lambda x: x['summaries'][0].update(row_ids=[self.keys['Revenue']]),
            lambda x: x['summaries'][0].update(citations=['unknown']),
            lambda x: x['summaries'].append(copy.deepcopy(x['summaries'][0])),
            lambda x: x.update(basis_position='hidden'),
        ]
        for mutate in mutations:
            spec = copy.deepcopy(self.spec); mutate(spec['layout'])
            with self.subTest(layout=spec['layout']), self.assertRaises(ValueError):
                repair.validate_format(spec, self.financial, self.bundle)

    def test_incompatible_units_periods_dimensions_and_cycles_rejected(self):
        catalog = repair.row_catalog(self.financial, self.bundle)
        source = self.keys['Share of revenue']; target = self.keys['Revenue']
        for field, value in [('periods', []), ('unit', 'USD millions')]:
            rows = copy.deepcopy(catalog); rows[source][field] = value
            with self.assertRaises(ValueError):
                repair.validate_layout(self.spec['layout'], rows, {'D001'})
        rows = copy.deepcopy(catalog); rows[source]['row']['dimensions'] = 'Other segment'
        with self.assertRaises(ValueError): repair.validate_layout(self.spec['layout'], rows, {'D001'})
        layout = copy.deepcopy(self.spec['layout'])
        layout['fold'].append({'row_id': target, 'into_row_id': source, 'label': 'Reverse'})
        with self.assertRaises(ValueError): repair.validate_layout(layout, catalog, {'D001'})

    def test_all_presentation_text_is_escaped(self):
        spec = copy.deepcopy(self.spec)
        spec['layout']['summaries'][0]['text'] = '<script>alert("bad")</script>'
        spec['layout']['fold'][0]['label'] = '<img src=x onerror=bad>'
        spec['basis']['text'] = '<svg onload=bad>'
        content = repair.table(self.financial, self.bundle, spec, self.refs)
        self.assertNotIn('<script>', content); self.assertNotIn('<img', content); self.assertNotIn('<svg', content)
        self.assertIn('&lt;script&gt;', content); self.assertIn('&lt;img', content)


if __name__ == '__main__': unittest.main()
