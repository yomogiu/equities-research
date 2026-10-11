"""Read-only classification of immutable failed launches, never retry authority."""
import json
from pathlib import Path
from . import earnings_mixed_runner as r


def classify(job):
    job = Path(job).resolve()
    uncertain = {'status': 'execution_uncertain', 'job': str(job),
                 'retry_allowed': False, 'actual_usage_known': False}
    try:
        if (job/'output.json').exists():
            verified = r.verify_job(job)
            return {'status': 'completed', 'job': str(job), 'retry_allowed': False,
                    'actual_usage_known': True, 'session': verified['receipt']['session']}
        request, launch, execution, start = [r.read(r._inside(job, n)) for n in
            ('request.json', 'launch.json', 'execution.json', 'runtime-start.json')]
        if not (launch['request_sha256'] == execution['request_sha256'] == r.digest(request)
                and execution['launch_sha256'] == r.sha(job/'launch.json')
                and start['launch_id'] == launch['id']
                and (start['model'], start['effort']) == (request['model'], request['effort'])
                and start['oauth'] is True):
            return uncertain
        # A missing process receipt, timeout or incomplete journal does not prove
        # provider termination. Keep its duplicate-launch protection intact.
        if execution['status'] != 'returned' or type(execution['exit_code']) is not int or execution['exit_code'] == 0:
            return uncertain
        journals = list((job/'sessions').rglob('*.jsonl'))
        if len(journals) != 1:
            return uncertain
        journal = r._inside(job, journals[0].relative_to(job))
        entries = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
        heads = [x for x in entries if x.get('type') == 'session']
        messages = [x['message'] for x in entries if x.get('type') == 'message']
        models = [x for x in entries if x.get('type') == 'model_change']
        efforts = [x for x in entries if x.get('type') == 'thinking_level_change']
        if (len(heads) != 1 or heads[0].get('parentSession') or heads[0]['id'] != start['session_id']
                or Path(heads[0]['cwd']).resolve() != job or len(messages) != 2
                or [m.get('role') for m in messages] != ['user', 'assistant']
                or r._text(messages[0]) != (job/'prompt.txt').read_text()
                or not models or any((x.get('provider'), x.get('modelId')) != (r.PROVIDER, request['model']) for x in models)
                or not efforts or any(x.get('thinkingLevel') != request['effort'] for x in efforts)
                or any(x.get('type') in {'compaction', 'branch_summary'} for x in entries)):
            return uncertain
        final = messages[-1]
        if (final.get('stopReason') != 'error'
                or (final.get('provider'), final.get('model'), final.get('api')) !=
                (r.PROVIDER, request['model'], 'openai-codex-responses')):
            return uncertain
        r._text(final)  # Reject tool calls, retain partial response only in journal.
        wires = r.read(r._inside(job, 'wire.json'))
        if not wires or any(x != {'model': request['model'], 'effort': request['effort'], 'tools': 0} for x in wires):
            return uncertain
        kind = 'provider_stream_failure' if any(x.get('type') == 'provider_stream_failure'
                     for x in final.get('diagnostics', [])) else 'provider_error'
        return {**uncertain, 'status': 'execution_failed', 'failure_kind': kind,
                'session_id': start['session_id'], 'execution_sha256': r.sha(job/'execution.json'),
                'journal_sha256': r.sha(journal),
                'partial_text_chars': len(r._text(final)),
                'usage_notice': 'Failed streams may report zero usage despite partial output; actual usage remains unknown.'}
    except (ValueError, KeyError, TypeError, OSError):
        return uncertain
