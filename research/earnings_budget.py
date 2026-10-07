"""Conservative local admission reservations, separate from measured usage.

Without a trusted tokenizer, reserve one input token per UTF-8 prompt byte plus
4,096 tokens for runtime framing and 32,768 for output/reasoning. This deliberately
overestimates typical prose input. It is an estimated reservation, not an exact
token count, provider cap, or guarantee about hidden runtime work/output length.
Authenticated receipt usage remains the sole measured accounting authority.
"""
from __future__ import annotations
from fractions import Fraction
from pathlib import Path
from research import earnings_experiment as base

VERSION = 'utf8-conservative-reservation-v1'
FRAMING_ALLOWANCE = 4096
OUTPUT_ALLOWANCE = 32768
CALIBRATED_VERSION = 'authenticated-review-reservation-v1'


def review_calibration(jobs, bindings, model, verifier):
    """Authenticate source-bound original reviewer jobs; never accept supplied usage."""
    if not isinstance(jobs, list) or not 1 <= len(jobs) <= 12 or len(set(jobs)) != len(jobs):
        raise ValueError('One to twelve distinct source review references required')
    rows = []
    for name in jobs:
        if not isinstance(name, str) or not Path(name).is_absolute():
            raise ValueError('Absolute source review reference required')
        job = Path(name).resolve()
        required = [job/k for k in ('request.json', 'prompt.txt', 'output.json', 'execution.json')]
        files = [p for p in job.rglob('*') if p.is_file()]
        if not files or any(p.is_symlink() for p in job.rglob('*')):
            raise ValueError('Source review reference must have immutable regular files')
        for path in set(files + required):
            if bindings.get(str(path)) != base.sha(path):
                raise ValueError('Review reference is not bound to stopped source')
        request = base.read(job/'request.json')
        if (request.get('model'), request.get('effort')) != tuple(model) or request.get('bindings', {}).get('role') != 'review':
            raise ValueError('Reference must be an original same-model/effort review')
        result = verifier(job); session = result['receipt']['session']; usage = session['usage']
        if (session.get('model'), session.get('effort')) != tuple(model) or session.get('provider') != 'openai-codex':
            raise ValueError('Authenticated reference provider/model/effort differs')
        if any(type(usage.get(k)) is not int or usage[k] < 0 for k in ('input', 'cacheRead', 'cacheWrite', 'output', 'totalTokens')):
            raise ValueError('Authenticated reference usage required')
        inputs = sum(usage[k] for k in ('input', 'cacheRead', 'cacheWrite'))
        size = len((job/'prompt.txt').read_bytes())
        if size <= 0 or inputs <= 0 or inputs + usage['output'] != usage['totalTokens']:
            raise ValueError('Invalid authenticated reference accounting')
        rows.append({'job': str(job), 'prompt_utf8_bytes': size, 'input_including_cache_tokens': inputs,
                     'output_tokens': usage['output'], 'session_id': session['id'],
                     'output_sha256': base.sha(job/'output.json')})
    return rows


def calibrated_admission(prompt, remaining_tokens, references):
    """Estimate from authenticated references with 25% margin and 0.5 token/byte floor.

    Callers must obtain references from review_calibration on every replay. Cached
    input is counted in full. This is not a tokenizer or provider-enforced cap.
    """
    result = admission(prompt, remaining_tokens)
    if not references: raise ValueError('Authenticated review calibration required')
    if remaining_tokens is None: return result
    rate = max(Fraction(1, 2), max(Fraction(r['input_including_cache_tokens'], r['prompt_utf8_bytes'])
                                 for r in references) * Fraction(5, 4))
    ceiling = lambda value: (value.numerator + value.denominator - 1) // value.denominator
    inputs = ceiling(result['prompt_utf8_bytes'] * rate) + FRAMING_ALLOWANCE
    outputs = max(OUTPUT_ALLOWANCE, ceiling(max(r['output_tokens'] for r in references) * Fraction(5, 4)))
    reserve = inputs + outputs
    return {**result, 'policy': CALIBRATED_VERSION, 'admitted': reserve <= remaining_tokens,
            'input_allowance_tokens': inputs, 'output_allowance_tokens': outputs, 'reserved_tokens': reserve,
            'input_tokens_per_byte': {'numerator': rate.numerator, 'denominator': rate.denominator},
            'reference_jobs': references,
            'notice': 'Authenticated same-model review calibration with 25% margin, 0.5 input-token/byte floor, '
                      'runtime framing and output reserve; estimated reservation, not an exact tokenizer or provider cap. '
                      'Only authenticated receipt usage is measured consumption.'}


def admission(prompt, remaining_tokens):
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError('Budget admission requires a nonempty exact prompt')
    if remaining_tokens is None:
        return {'policy': 'uncapped-usage-accounting-v1', 'admitted': True,
                'remaining_tokens': None, 'prompt_utf8_bytes': len(prompt.encode('utf-8')),
                'reserved_tokens': None, 'notice': 'Token cap disabled; authenticated usage is still recorded.'}
    if type(remaining_tokens) is not int:
        raise ValueError('Budget admission requires integer remaining tokens')
    prompt_bytes = len(prompt.encode('utf-8'))
    reserve = prompt_bytes + FRAMING_ALLOWANCE + OUTPUT_ALLOWANCE
    return {'policy': VERSION, 'admitted': reserve <= remaining_tokens,
            'remaining_tokens': remaining_tokens, 'prompt_utf8_bytes': prompt_bytes,
            'input_allowance_tokens': prompt_bytes + FRAMING_ALLOWANCE,
            'framing_allowance_tokens': FRAMING_ALLOWANCE,
            'output_allowance_tokens': OUTPUT_ALLOWANCE, 'reserved_tokens': reserve,
            'notice': 'Conservative estimated reservation; not an exact tokenizer count or provider cap. '
                      'Only authenticated receipt usage is measured consumption.'}


def compliance(measured_tokens, max_tokens, inherited_tokens=0):
    if (type(measured_tokens) is not int or measured_tokens < 0 or (max_tokens is not None and type(max_tokens) is not int)
            or type(inherited_tokens) is not int or inherited_tokens < 0):
        raise ValueError('Budget compliance requires measured integer counters')
    total = measured_tokens + inherited_tokens
    return {'within_budget': max_tokens is None or total <= max_tokens, 'measured_tokens': measured_tokens,
            'inherited_tokens': inherited_tokens, 'total_measured_tokens': total,
            'max_tokens': max_tokens, 'overrun_tokens': 0 if max_tokens is None else max(0, total - max_tokens)}


def remaining(max_tokens, *spent):
    """Keep unlimited policies explicit while retaining measured counters."""
    if any(type(x) is not int or x < 0 for x in spent):
        raise ValueError("Nonnegative integer usage required")
    return None if max_tokens is None else max_tokens - sum(spent)
