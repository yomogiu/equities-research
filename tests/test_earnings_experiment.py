"""Synthetic orchestration fixtures; no issuer documents or model calls."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research import earnings_experiment as engine


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def make_case(root):
    sources = []
    for kind in ('transcript', 'filing'):
        path = root / (kind + '.txt')
        path.write_text('Fictitious ' + kind + ' source only.')
        sources.append({'kind': kind, 'path': str(path), 'sha256': engine.sha(path)})
    financial = write(root / 'financial.json', {'observations': [{'observation_id': 'fictional-fact'}]})
    index = write(root / 'index.json', {'exchanges': []})
    case = {'schema_version': 1, 'scope': 'one_packet_experiment',
            'authorization': 'synthetic unittest only', 'sources': sources,
            'financial_path': str(financial), 'transcript_index_path': str(index),
            'transcript_path': sources[0]['path'],
            'artifacts': [{'path': str(p), 'sha256': engine.sha(p)} for p in (financial, index)]}
    return write(root / 'input-case.json', case), case


def review(criteria, verdict='pass', target='editor'):
    result = {'verdict': verdict,
              'criteria': {key: {'status': 'pass', 'evidence': 'Checked fictional source context.'} for key in criteria},
              'findings': []}
    if verdict == 'revise':
        result['criteria'][criteria[0]]['status'] = 'fail'
        result['findings'] = [{'target': target, 'severity': 'material', 'claim': 'Fictional disputed passage.',
                               'evidence': 'Fictional source shows a different value.',
                               'required_change': 'Correct the value and qualification.'}]
    return result


def fake_completed_job(run, role, case_path, case, dependencies, content, session_id=None):
    job = run / f'{role}-r0'
    job.mkdir(parents=True, exist_ok=True)
    prompt = engine.role_prompt(role, case_path, case, dependencies, 0)
    (job / 'prompt.txt').write_text(prompt)
    (job / 'stdout.txt').write_text(json.dumps(content))
    request = {'version': engine.VERSION, 'role': role, 'revision': 0,
               'case_sha256': engine.digest(case),
               'dependencies': {k: engine.sha(v) for k, v in dependencies.items()},
               'prompt_sha256': engine.sha(job / 'prompt.txt')}
    write(job / 'request.json', request)
    write(job / 'dependencies.json', {k: str(v) for k, v in dependencies.items()})
    write(job / 'output.json', {'request_sha256': engine.digest(request), 'content': content})
    events = [{'type': 'session', 'id': session_id or 'fictional-' + role},
              {'type': 'message', 'message': {'role': 'user', 'content': [{'type': 'text', 'text': prompt}]}},
              {'type': 'message', 'message': {'role': 'assistant', 'stopReason': 'stop',
               'content': [{'type': 'text', 'text': json.dumps(content)}]}}]
    session = job / 'sessions' / 'fixture.jsonl'
    session.parent.mkdir(parents=True, exist_ok=True)
    session.write_text('\n'.join(json.dumps(event) for event in events) + '\n')
    write(job / 'execution.json', {'status': 'returned', 'exit_code': 0, 'session': engine.session_receipt(job)})
    return job / 'output.json'


def synthetic_acceptance(root, wrong_reviewer=False, wrong_editor=False, duplicate_session=False):
    # Chain-focused fixture: tests mock role semantic validation, not chain checks.
    case_path, case = make_case(root)
    run = root / 'run'
    write(run / 'case.json', case)
    authors = {role: fake_completed_job(run, role, case_path, case, {}, {'synthetic': role})
               for role in ('extractor', 'commentator')}
    stale = write(run / 'stale-output.json', {'synthetic': 'stale'})
    reviewer_deps = dict(authors)
    if wrong_reviewer:
        reviewer_deps['extractor'] = stale
    rv = fake_completed_job(run, 'reviewer', case_path, case, reviewer_deps, review(engine.SUBSTANTIVE),
                            'fictional-extractor' if duplicate_session else None)
    ed_deps = {**authors, 'substantive_review': rv}
    if wrong_editor:
        ed_deps['commentator'] = stale
    body = 'Fictitious coherent report. ' * 40
    ed = fake_completed_job(run, 'editor', case_path, case, ed_deps, {'report_markdown': body})
    report = run / 'report-r0.md'
    report.write_text(body.strip() + '\n')
    fv_content = review(engine.EDITORIAL)
    fv_content['report_sha256'] = engine.sha(report)
    fv = fake_completed_job(run, 'final_reviewer', case_path, case,
                            {**authors, 'substantive_review': rv, 'report': report}, fv_content)
    outputs = {**authors, 'reviewer': rv, 'editor': ed, 'final_reviewer': fv}
    a = {'version': engine.VERSION, 'status': 'accepted_local', 'runtime': 'prime-agent',
         'case_sha256': engine.digest(case), 'revisions': 0, 'report': report.name,
         'report_sha256': engine.sha(report),
         'roles': {role: str(path.parent.relative_to(run)) for role, path in outputs.items()},
         'artifacts': {str(path.relative_to(run)): engine.sha(path) for path in [*outputs.values(), report]}}
    return run, a


class EarningsExperimentTests(unittest.TestCase):
    def test_session_prompt_and_final_response_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case_path, case = make_case(root)
            output = fake_completed_job(root / 'run', 'extractor', case_path, case, {}, {'value': 1})
            job = output.parent
            engine.session_receipt(job)
            (job / 'stdout.txt').write_text('{"value":2}')
            with self.assertRaisesRegex(ValueError, 'Session response'):
                engine.session_receipt(job)
            (job / 'stdout.txt').write_text('{"value":1}')
            (job / 'prompt.txt').write_text('A different task.')
            with self.assertRaisesRegex(ValueError, 'Session user prompt'):
                engine.session_receipt(job)

    def test_accepted_dependency_chain_and_independent_sessions(self):
        for bad in ('none', 'reviewer', 'editor', 'duplicate'):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as temp:
                run, a = synthetic_acceptance(Path(temp), wrong_reviewer=bad=='reviewer',
                                              wrong_editor=bad=='editor', duplicate_session=bad=='duplicate')
                with patch.object(engine, 'validate_content'):
                    if bad == 'none':
                        self.assertEqual(engine.verify_acceptance(run, a)['status'], 'verified_local')
                    else:
                        with self.assertRaises(ValueError):
                            engine.verify_acceptance(run, a)

    def test_artifact_paths_cannot_escape_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, a = synthetic_acceptance(root)
            a['roles']['reviewer'] = '../outside'
            with self.assertRaisesRegex(ValueError, 'escapes'):
                engine.verify_acceptance(run, a)
            (run / 'escape').symlink_to(root)
            with self.assertRaises(ValueError):
                engine.inside(run, run / 'escape' / 'source.txt')

    def test_failed_acceptance_does_not_write_accepted_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case_path, _ = make_case(root)
            run = root / 'run'
            def fake_role(run, role, revision, case_path, case, dependencies):
                if role == 'reviewer':
                    content = review(engine.SUBSTANTIVE)
                elif role == 'final_reviewer':
                    content = review(engine.EDITORIAL)
                elif role == 'editor':
                    content = {'report_markdown': 'Fictitious report. ' * 40}
                else:
                    content = {'synthetic': role}
                return write(run / f'{role}-r{revision}' / 'output.json', {'content': content})
            with patch.object(engine, 'run_role', side_effect=fake_role), patch.object(engine, 'verify_acceptance', side_effect=ValueError('invalid provenance')):
                with self.assertRaisesRegex(ValueError, 'invalid provenance'):
                    engine.execute(case_path, run)
            self.assertFalse((run / 'accepted.json').exists())

    def test_every_criterion_and_material_failures_block_pass(self):
        valid = review(engine.EDITORIAL)
        engine.validate_review(valid, engine.EDITORIAL)
        del valid['criteria'][engine.EDITORIAL[0]]
        with self.assertRaises(ValueError):
            engine.validate_review(valid, engine.EDITORIAL)
        invalid = review(engine.EDITORIAL, 'revise')
        invalid['verdict'] = 'pass'
        with self.assertRaises(ValueError):
            engine.validate_review(invalid, engine.EDITORIAL)
        invalid = review(engine.EDITORIAL)
        invalid['criteria'][engine.EDITORIAL[0]]['status'] = 'unavailable'
        with self.assertRaises(ValueError):
            engine.validate_review(invalid, engine.EDITORIAL)

    def test_final_review_binds_actual_report_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = root / 'report.md'
            report.write_text('Fictitious report version one.')
            content = review(engine.EDITORIAL)
            content['report_sha256'] = engine.sha(report)
            engine.validate_content('final_reviewer', content, {}, {'report': report})
            report.write_text('Fictitious report altered after review.')
            with self.assertRaisesRegex(ValueError, 'exact report'):
                engine.validate_content('final_reviewer', content, {}, {'report': report})

    def test_unfrozen_input_reference_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, case = make_case(root)
            alternate = write(root / 'unfrozen.json', {'observations': []})
            case['financial_path'] = str(alternate)
            with self.assertRaises(ValueError):
                engine.validate_case(case)

    def test_forged_accepted_receipt_cannot_certify_unreviewed_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, case = make_case(root)
            run = root / 'run'
            write(run / 'case.json', case)
            report = run / 'unreviewed.md'
            report.write_text('Fictitious output with no agent execution or review.')
            write(run / 'accepted.json', {'version': engine.VERSION, 'status': 'accepted_local',
                  'case_sha256': engine.digest(case), 'report': report.name,
                  'report_sha256': engine.sha(report), 'artifacts': {}, 'revisions': 0,
                  'runtime': 'prime-agent', 'remote_persistence': 'pending'})
            with self.assertRaises(ValueError):
                engine.verify(run)

    def test_shared_revision_budget_across_substantive_and_editorial(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case_path, _ = make_case(root)
            run = root / 'run'
            calls = []

            def fake_role(run, role, revision, case_path, case, dependencies):
                calls.append((role, revision))
                if role == 'reviewer':
                    content = review(engine.SUBSTANTIVE, 'revise' if revision == 0 else 'pass', 'commentator')
                elif role == 'final_reviewer':
                    content = review(engine.EDITORIAL, 'revise', 'editor')
                    content['report_sha256'] = engine.sha(dependencies['report'])
                elif role == 'editor':
                    content = {'report_markdown': 'Fictitious report content. ' * 40}
                else:
                    content = {'synthetic_role': role}
                return write(run / f'{role}-r{revision}' / 'output.json', {'content': content})

            with patch.object(engine, 'run_role', side_effect=fake_role):
                engine.execute(case_path, run)
            blocked = engine.read(run / 'blocked.json')
            self.assertEqual(blocked['stage'], 'final')
            self.assertEqual(blocked['revisions'], 2)
            self.assertFalse((run / 'accepted.json').exists())
            self.assertNotIn(('extractor', 1), calls)
            self.assertIn(('commentator', 1), calls)
            self.assertIn(('editor', 2), calls)
            self.assertFalse(any(revision > 2 for _, revision in calls))

    def test_cached_output_requires_actual_execution_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case_path, case = make_case(root)
            run = root / 'run'
            job = run / 'extractor-r0'
            prompt = engine.role_prompt('extractor', case_path, case, {}, 0)
            request = {'version': engine.VERSION, 'role': 'extractor', 'revision': 0,
                       'case_sha256': engine.digest(case), 'dependencies': {},
                       'prompt_sha256': engine.hashlib.sha256(prompt.encode()).hexdigest()}
            write(job / 'output.json', {'request_sha256': engine.digest(request),
                  'content': {'selected_fact_ids': ['fictional-fact'],
                              'financial_checks': [{'claim': 'Synthetic check.'}], 'gaps': []}})
            with patch.object(engine.subprocess, 'run') as launch:
                with self.assertRaises((ValueError, FileNotFoundError)):
                    engine.run_role(run, 'extractor', 0, case_path, case, {})
                launch.assert_not_called()

    def test_existing_uncertain_launch_stops_duplicate_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case_path, case = make_case(root)
            run = root / 'run'
            job = run / 'extractor-r0'
            write(job / 'launch.json', {'status': 'launched'})
            with patch.object(engine.subprocess, 'run') as launch:
                with self.assertRaisesRegex(ValueError, 'reconciled'):
                    engine.run_role(run, 'extractor', 0, case_path, case, {})
                launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
