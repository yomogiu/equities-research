"""Conservative local admission reservations, separate from measured usage.

Without a trusted tokenizer, reserve one input token per UTF-8 prompt byte plus
4,096 tokens for runtime framing and 32,768 for output/reasoning. This deliberately
overestimates typical prose input. It is an estimated reservation, not an exact
token count, provider cap, or guarantee about hidden runtime work/output length.
Authenticated receipt usage remains the sole measured accounting authority.
"""
from __future__ import annotations

VERSION = 'utf8-conservative-reservation-v1'
FRAMING_ALLOWANCE = 4096
OUTPUT_ALLOWANCE = 32768


def admission(prompt, remaining_tokens):
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError('Budget admission requires a nonempty exact prompt')
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
    if (type(measured_tokens) is not int or measured_tokens < 0 or type(max_tokens) is not int
            or type(inherited_tokens) is not int or inherited_tokens < 0):
        raise ValueError('Budget compliance requires measured integer counters')
    total = measured_tokens + inherited_tokens
    return {'within_budget': total <= max_tokens, 'measured_tokens': measured_tokens,
            'inherited_tokens': inherited_tokens, 'total_measured_tokens': total,
            'max_tokens': max_tokens, 'overrun_tokens': max(0, total - max_tokens)}
