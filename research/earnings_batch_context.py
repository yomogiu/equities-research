"""Declared review inventory: complete financial facts and complete call text.

Source-context selection is explicit. Full cited financial scopes and the complete
call remain verbatim; unrelated filing chunks are navigable deferred evidence.
"""
import copy
from . import earnings_financial_context as financial
from . import earnings_repair_context as transport
from . import earnings_mixed_runner as r

VERSION = 'complete-facts-cited-filing-full-call-v1'


def build(data, bundle, wanted):
    value=copy.deepcopy(data)
    sources=value['sources']
    turns={t['id'] for t in bundle['transcript_index']['turns']}
    groups=sources.get('passage_groups')
    if groups is not None:
        kept=[g for g in groups if g['scope_id'] in turns or g['scope_id'] in wanted]
        deferred=[g['scope_id'] for g in groups if g['scope_id'] not in turns and g['scope_id'] not in wanted]
        sources['passage_groups']=kept
        sources['scope_selection']={'version':VERSION,'deferred_financial_scope_ids':deferred,
            'notice':'All call turns and unassigned call text are complete. Cited financial scopes are complete. Other filing scopes are deferred, not reviewed source prose; their facts remain in the complete financial inventory. If material support is absent, return a source-specific revise decision, never infer support from a preview.'}
        assert [g for g in kept if g['scope_id'] in turns]==[g for g in groups if g['scope_id'] in turns]
        assert all(g in kept for g in groups if g['scope_id'] in wanted)
    if 'financial_source_context' in value:
        inventory=financial.financial_role_payload(bundle)
        rows=inventory['financial_observations']
        assert [row[0] for row in rows['rows']]==[o['id'] for o in bundle['financial']['observations']]
        assert not rows['omitted_observation_ids']
        value['financial_source_context']=inventory
    # Protect the readable complete rendered report from string/table factoring.
    value['report']=value.pop('rendered_report')
    value['review_context_policy']=VERSION
    packed=transport.compact_context(value)
    if transport.expand_context(packed)!=value:raise ValueError('Review transport changed evidence')
    return packed
