"""Zero-model verification of the sequential pipeline's quantitative table layer.

Reproducibility is not semantic approval: an exact extraction can still omit a
material metric or use an inappropriate accounting interpretation. Independent
review retains that responsibility and original narrative evidence inspection.
"""
from copy import deepcopy
from pathlib import Path
import re

from . import earnings_compact_evidence as evidence
from . import earnings_financial_analysis_report as finance
from . import earnings_financial_statement_context as statements
from . import earnings_runtime_common as storage
from . import financial_evidence

VERSION = 'sequential-financial-contract-v1'
FILES = ('sources/manifest.json', 'financial-configuration.json',
         'financial-analysis.json', 'financial-tables.md')


def require(condition, message):
    if not condition: raise ValueError(message)


def _replayed_facts(bundle):
    """Reparse each bound original once; never promote manual proposals."""
    facts = bundle['financial']; cache = {}; verified = set()
    for row in facts['observations']:
        if row.get('method') != 'inline_xbrl': continue
        key = (row['source_path'], row['source_sha256'], row['source_document_id'])
        require(any((item['path'],item['sha256'],item['document_id']) == key
                    for item in bundle['manifest']['sources']), 'Financial fact source is not frozen')
        if key not in cache:
            source = {'document_id':key[2], 'raw_sha256':key[1]}
            extracted = financial_evidence.extract_inline_xbrl_file(key[0], source)
            cache[key] = {item['observation_id']:item for item in extracted['observations']}
        original = {key:deepcopy(value) for key,value in row.items()
                    if key not in ('id','context_id','unit_id','source_path','source_sha256')}
        original['context'] = facts['contexts'][row['context_id']]
        original['unit'] = facts['units'][row['unit_id']]
        require(cache[key].get(row['observation_id']) == original,
                'Financial fact differs from deterministic original-source extraction: '+row['id'])
        verified.add(row['id'])
    return verified


def build(root):
    """Verify frozen files and return a compact, reproducible model contract.

    ``trusted_table_ids`` authorizes only use of displayed quantitative table
    facts. It never substantiates qualitative claims or interpretations made with the same F reference.
    Non-replayable mappings stay explicitly subject to original inspection.
    This function has no model calls, publication effects, or filesystem writes.
    """
    root = Path(root).resolve(); job = storage.read(root/'job.json')
    hashes = {}
    for name in FILES:
        path = (root/name).resolve()
        require(root in path.parents, 'Financial artifact escapes the job')
        digest = storage.sha(path)
        require(job.get('artifacts',{}).get(name) == digest, 'Frozen financial artifact changed: '+name)
        hashes[name] = digest
    bundle = evidence.load_bundle(root/'sources/manifest.json')
    configuration = finance.validate_configuration(storage.read(root/'financial-configuration.json'))
    explicit = job['specification'].get('financial_analysis')
    require(explicit is None or explicit == configuration, 'Financial configuration differs from the job specification')
    value = storage.read(root/'financial-analysis.json')
    require(value.get('source_policy') == statements.VERSION, 'Unsupported financial source policy')
    replayed = _replayed_facts(bundle)
    reproduced = finance.compile(statements.qualify(bundle), configuration)
    require(value == reproduced, 'Financial analysis differs from deterministic source recomputation')
    rendered = finance.preview_markdown(reproduced)
    require((root/'financial-tables.md').read_text() == rendered,
            'Financial tables differ from deterministic rendering')
    # Basis declarations are independently rebound to original source spans.
    statements.source_support(reproduced, bundle)
    displayed = set(re.findall(r'\[\^(F[0-9]+)\]', '\n'.join(
        line for line in rendered.splitlines() if line.startswith('|'))))
    all_references = set(re.findall(r'\[\^(F[0-9]+)\]', rendered))
    trusted = sorted(displayed & replayed)
    slices = evidence.source_slices(root/'sources/manifest.json', trusted)
    source_bindings = sorted({(span['document_id'],span['sha256'])
                              for item in slices for span in item['spans']})
    references = []
    for item in slices:
        for span in item['spans']:
            references.append([item['id'],source_bindings.index((span['document_id'],span['sha256'])),
                               span['start'],span['end'],span['span_sha256']])
    selected = finance.front_rows(value); audit = []; gaps = []
    for section,rows in selected.items():
        gap = finance.front_gaps(selected,section)
        if gap: gaps.append({'section':section,'reason':gap})
        for family,row in rows:
            unavailable = {slot:cell.get('reason') or cell['status']
                           for slot,cell in row['cells'].items() if cell['status'] != 'available'}
            audit.append({'section':section,'period_family':family,'metric':row['metric_id'],
                          'basis':row['basis'],'basis_origin':row.get('basis_origin'),
                          'unit':row['unit'],'missing_comparisons':unavailable})
    result = {'version':VERSION, 'verification':'reproduced', 'source_policy':statements.VERSION,
              'artifact_sha256':hashes, 'source_computation_sha256':storage.digest(value),
              'trusted_table_ids':trusted,
              'requires_original_inspection_ids':sorted(all_references-set(trusted)),
              'source_binding_columns':['document_id','sha256'],
              'source_bindings':[list(item) for item in source_bindings],
              'reference_columns':['fact_id','source_binding','start','end','span_sha256'],
              'references':references, 'offset_unit':'unicode_character',
              'audit':{'displayed_metrics':audit,'gap_disclosures':gaps,
                       'calculation_notes':finance.notes(value)},
              'scope':'These IDs support displayed quantitative facts only; they do not substantiate qualitative claims or interpretations. Inspect original disclosures for those claims; independent review remains mandatory.',
              'limitations':['Reproduction verifies frozen-source extraction, calculations and table rendering, not source semantic correctness.',
                             'Missing metrics, disclosures, accounting interpretations and report quality remain subject to independent review; gaps are not approval.',
                             'Initial analysis/review require the complete original call, narrative source support and independent filing challenge. Verified section revisions retain original targeted sources and independent review.']}
    result['contract_sha256'] = storage.digest(result)
    return result
