"""Replay one independent repair review and at most one evidence expansion.

This module never launches a model or writes a job. It returns an exact next
request to the caller, or verifies completed immutable receipts. Evidence lookup
consumes measured tokens but does not consume an additional correction round.
"""
from __future__ import annotations

import copy
from pathlib import Path

from research import earnings_experiment as base
from research import earnings_repair_context as context
from research import earnings_budget as budget

VERSION = 'focused-repair-review-v1'


def replay(job_base, prompt_factory, bindings, model, bundle, catalog,
           candidate_sha256, plan_sha256, seen_sessions, remaining_tokens,
           max_prompt_chars, verifier, admission_fn=None):
    """Return pending/status request fields or completed/result; never execute.

    ``seen_sessions`` is the replay-wide mutable set, initialized from previous
    stages on each replay. Validated receipts reserve their fresh identity here.
    ``tokens`` always includes every verified receipt encountered by this call.
    The caller must launch exactly the returned prompt, model and bindings.
    """
    if not isinstance(seen_sessions, set):
        raise ValueError('Replay requires a mutable set of prior session IDs')
    if (remaining_tokens is not None and type(remaining_tokens) is not int) or type(max_prompt_chars) is not int or max_prompt_chars <= 0:
        raise ValueError('Integer token budget and positive prompt bound required')
    if not isinstance(bindings, dict) or not isinstance(model, (list, tuple)) or len(model) != 2:
        raise ValueError('Exact bindings and model/effort pair required')
    for label, value in (('candidate', candidate_sha256), ('plan', plan_sha256)):
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError(f'Exact {label} SHA-256 required')
        key = label + '_sha256'
        if key in bindings and bindings[key] != value:
            raise ValueError('Conflicting source identity binding')
    first = Path(job_base)
    extra_scopes, requests, prior_output = (), [], None
    tokens = 0
    for expansion in range(2):
        job = first if expansion == 0 else first.with_name(first.name + '-evidence-1')
        expected = {**copy.deepcopy(bindings), 'review_context_version': VERSION,
                    'candidate_sha256': candidate_sha256, 'plan_sha256': plan_sha256,
                    'evidence_expansion': expansion, 'evidence_requests_sha256': base.digest(requests),
                    'extra_scope_ids_sha256': base.digest(list(extra_scopes)),
                    'prior_review_output_sha256': prior_output}
        try:
            prompt = prompt_factory(extra_scopes)
        except context.ContextTooLarge as exc:
            return {'status': 'prompt_too_large', 'job': job, 'prompt': None, 'bindings': expected,
                    'tokens': tokens, 'error': str(exc)}
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError('Nonempty exact review prompt required')
        response = {'job': job, 'prompt': prompt, 'bindings': expected, 'tokens': tokens,
                    'evidence_expansion': expansion}
        if not (job/'output.json').exists():
            # A partial write, launch marker, journal, or request is uncertainty.
            # Never turn a missing output into an automatic duplicate launch.
            uncertain = job.exists() and any(job.iterdir())
            admission = (admission_fn or budget.admission)(prompt, budget.remaining(remaining_tokens, tokens))
            status = ('launch_uncertain' if uncertain else
                      'prompt_too_large' if len(prompt) > max_prompt_chars else
                      'budget_exhausted' if not admission['admitted'] else 'pending')
            return {**response, 'status': status, 'budget_admission': admission}
        result = verifier(job)
        request = base.read(job/'request.json')
        saved_output = base.read(job/'output.json')
        if (request.get('bindings') != expected or (request.get('model'), request.get('effort')) != tuple(model)
                or (job/'prompt.txt').read_text() != prompt
                or request.get('prompt_sha256') != base.sha(job/'prompt.txt')
                or saved_output.get('request_sha256') != base.digest(request)):
            raise ValueError('Review differs from exact immutable request')
        if result.get('content') != saved_output.get('content'):
            raise ValueError('Verified review differs from saved output')
        session = result.get('receipt', {}).get('session', {})
        sid = session.get('id')
        used = session.get('usage', {}).get('totalTokens')
        if not isinstance(sid, str) or not sid.strip() or sid in seen_sessions:
            raise ValueError('Independent fresh review sessions required')
        if type(used) is not int or used < 0:
            raise ValueError('Measured nonnegative integer token usage required')
        seen_sessions.add(sid)
        tokens += used
        compliance = budget.compliance(tokens, remaining_tokens)
        response.update(tokens=tokens, result=result, budget_compliance=compliance)
        content = result.get('content')
        if (not isinstance(content, dict) or content.get('candidate_sha256') != candidate_sha256
                or content.get('plan_sha256') != plan_sha256):
            raise ValueError('Review candidate or plan binding mismatch')
        if content.get('verdict') != 'needs_evidence':
            # The caller remains responsible for complete final review schema,
            # rubric and operation adjudication EVEN when measured usage or the
            # prompt exceeds its limit. A saved verdict is never approval alone.
            status = ('budget_exhausted' if not compliance['within_budget'] else
                      'prompt_too_large' if len(prompt) > max_prompt_chars else 'completed')
            return {**response, 'status': status, 'requires_adjudication': True,
                    'review_verdict': content.get('verdict')}
        if set(content) != {'verdict', 'candidate_sha256', 'plan_sha256', 'requests'}:
            raise ValueError('Evidence request requires only verdict, candidate, plan, requests')
        try:
            expansion_data = context.evidence_response(bundle, catalog, content['requests'], extra_scopes)
        except context.ContextTooLarge as exc:
            return {**response, 'status': 'prompt_too_large', 'error': str(exc)}
        # Validate even an over-budget evidence request before halting. Never
        # hide malformed/foreign references behind a budget status.
        if not compliance['within_budget']:
            return {**response, 'status': 'budget_exhausted', 'review_verdict': 'needs_evidence'}
        if len(prompt) > max_prompt_chars:
            return {**response, 'status': 'prompt_too_large', 'review_verdict': 'needs_evidence'}
        if expansion == 1 or not expansion_data['scope_ids']:
            return {**response, 'status': 'evidence_insufficient',
                    'error': 'One evidence expansion exhausted; no final review verdict was obtained'}
        requests = copy.deepcopy(content['requests'])
        extra_scopes = tuple(expansion_data['scope_ids'])
        prior_output = base.sha(job/'output.json')
    raise AssertionError('Unreachable review expansion state')
