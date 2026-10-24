"""Bounded presentation-only repairs; no financial or narrative regeneration."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from . import earnings_sequential_revisions as revisions

VERSION = 'sequential-editorial-repair-v1'
NOTICE = 'Debt total unavailable; see supporting evidence for any separately reported debt and lease obligations.'
MISSING = 'Current consolidated metrics unavailable: Total debt. No substitute period or zero is assumed.'


def review_name(job):
    suffix = '-editorial1' if job.get('editorial_repair') else ''
    return f"review-r{job['revision_round']}{suffix}.json"


def repair(candidate, analysis, decision):
    """Delete two known generated notices only when the fuller caveat survives.

    The reviewer must have passed every substantive criterion and requested only
    debt-caveat deduplication. All narrative, financial rows and references stay
    byte-for-byte unchanged. Unsupported editorial requests return None.
    """
    criteria = decision.get('criteria', {})
    expected = {'source_accuracy', 'qa_fidelity', 'financial_context', 'reasoning',
                'counterevidence', 'coverage', 'materiality', 'concise_writing'}
    if (decision.get('verdict') != 'revise' or set(criteria) != expected
            or any(row.get('status') != ('fail' if key == 'concise_writing' else 'pass')
                   for key, row in criteria.items())):
        return None
    questions = decision.get('questions', {})
    if (set(questions) != {'demand', 'earnings', 'cash', 'outlook', 'valuation'}
            or any(row.get('status') not in ('answered', 'disclosed_gap') for row in questions.values())):
        return None
    findings = decision.get('findings', [])
    if not findings: return None
    for finding in findings:
        problem, fix = finding.get('problem', '').lower(), finding.get('fix', '').lower()
        if (finding.get('location') not in ('financial_tables', 'cash')
                or 'debt' not in problem or not re.search(r'repeat|repetit|again|duplicat', problem)
                or not re.search(r'consolidat|remove|deduplicat', fix)
                or re.search(r'\b(?:calculate|recalculate|add|correct|replace)\b', fix)):
            return None
    cash = analysis.get('sections', {}).get('cash', {})
    text = cash.get('text', '')
    if (not re.search(r'(?:total debt|debt total).{0,50}unavailable', text, re.I)
            or not re.search(r'lease.{0,100}(?:not|incomplete).{0,100}(?:complete|debt)', text, re.I)
            or not cash.get('citations') or candidate.count(text) != 1):
        return None
    for notice in (MISSING, NOTICE):
        if candidate.count('\n'+notice+'\n') != 1: return None
    # Both notices must be beside the same cash prose, not a different table.
    section = candidate.rfind('\n## ', 0, candidate.index(text))
    prefix = candidate[section:candidate.index(text)]
    if not all(notice in prefix for notice in (MISSING, NOTICE)): return None
    result = candidate
    for notice in (MISSING, NOTICE):
        result = result.replace(notice+'\n\n', '', 1) if notice+'\n\n' in result else result.replace(notice+'\n', '', 1)
    return result


def prepare(root, job, outputs, outcome, render_candidate):
    """Verify the exact reviewed baseline and prepare a deterministic edit."""
    root = Path(root).resolve()
    if (job.get('editorial_repair') or job.get('final_review')
            or job['stage'] != 'review' or job['tokens_used'] >= job['budget_tokens']
            or outcome.get('execution_certainty') != 'completed' or not outcome.get('session_id')):
        return None
    revisions._verify(root, job['artifacts']); revisions._verify(root, outputs)
    name = review_name(job)
    if name not in outputs: return None
    candidate = job['candidate_artifact']
    if outcome.get('input_sha256') != job['artifacts'].get(candidate):
        raise ValueError('Editorial repair review must bind exact candidate')
    analysis_name = f"analysis-r{job['revision_round']}.json"
    if analysis_name not in job['artifacts']: return None
    analysis = revisions._read(root/analysis_name)
    decision = revisions._read(root/name)
    before = (root/candidate).read_text()
    if render_candidate(analysis, revisions._read(root/'financial-analysis.json'), root/'sources/manifest.json') != before:
        raise ValueError('Editorial baseline does not reconstruct from frozen analysis and tables')
    after = repair(before, analysis, decision)
    if after is None: return None
    sources = revisions._source_bindings(root)
    return {'version':VERSION, 'baseline_artifacts':{**job['artifacts'], **outputs},
            'original_sources':sources, 'analysis_artifact':analysis_name, 'review_artifact':name,
            'candidate_before':candidate, 'candidate_after':'report-editorial-1.md',
            'candidate_before_sha256':revisions._text_sha(before),
            'candidate_after_sha256':revisions._text_sha(after),
            'removed_notices':[MISSING, NOTICE], 'tokens':0}, after


def load(root, job, render_candidate):
    """Reproduce and authenticate the deletion before review and publication."""
    root = Path(root).resolve()
    record = job['editorial_repair']
    proof_name = record['proof_artifact']
    revisions._verify(root, job['artifacts'])
    if proof_name not in job['artifacts']: raise ValueError('Editorial proof is not bound')
    proof = revisions._read(root/proof_name)
    revisions._verify(root, proof['baseline_artifacts'])
    if proof['version'] != VERSION or proof['original_sources'] != revisions._source_bindings(root):
        raise ValueError('Editorial source binding changed')
    analysis = revisions._read(root/proof['analysis_artifact'])
    decision = revisions._read(root/proof['review_artifact'])
    before = revisions._path(root, proof['candidate_before']).read_text()
    after = revisions._path(root, proof['candidate_after']).read_text()
    if (render_candidate(analysis, revisions._read(root/'financial-analysis.json'), root/'sources/manifest.json') != before
            or repair(before, analysis, decision) != after
            or revisions._text_sha(before) != proof['candidate_before_sha256']
            or revisions._text_sha(after) != proof['candidate_after_sha256']
            or job['candidate_artifact'] != proof['candidate_after']):
        raise ValueError('Editorial deletion proof does not reproduce exact candidate')
    # Reuse the selective-review packet: full candidate, prior criteria, original
    # evidence for the finding, no author call and no newly introduced claims.
    plan = {'previous_review':decision, 'previous_analysis':analysis,
            'allowed_locations':[], 'table_changes':{},
            'unchanged_components':{k:revisions._digest(v) for k,v in revisions._components(analysis).items()},
            'previous_candidate_sha256':proof['candidate_before_sha256'],
            'citations':sorted(revisions._citations(decision['findings'])),
            'previous_passed_criteria':{k:copy.deepcopy(v) for k,v in decision['criteria'].items() if v['status']=='pass'}}
    return {'plan':plan, 'proof':{**proof, 'component_changes':{}}}
