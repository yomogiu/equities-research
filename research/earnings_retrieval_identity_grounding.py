"""Replay reviewed pre-question annotations for an explicit retrieval derivative.

This helper never edits the original case, index, sources or retrieval. The private
caller must also authenticate its reserved sidecar selection and separate generated
coverage approval. It does not qualify sources or accept a report.
"""
import copy
from pathlib import Path
from . import earnings_mixed_runner as b
from . import earnings_file_context as c
from . import earnings_compact_evidence as evidence
from . import earnings_passages as passages
from . import earnings_qa_grounding as qa
from . import earnings_passage_pipeline as pipe
from . import reviewed_transcript_index as reviewed
from . import transcript_evidence as transcript

VERSION = 'reviewed-pre-question-identity-grounding-v1'
DISPOSITION = 'reviewed_pre_question_non_qa'
FUNCTIONS = {'greeting', 'live_analyst_transition'}


def frozen_artifact(case, reference, digest=None):
    """Resolve only an exact frozen artifact; never search arbitrary files."""
    relative = Path(reference)
    c.require('..' not in relative.parts, 'Canonical frozen artifact reference required')
    matches = []
    for artifact in case['artifacts']:
        path = Path(artifact['path'])
        same = path == relative if relative.is_absolute() else path.parts[-len(relative.parts):] == relative.parts
        if same and (digest is None or artifact['sha256'] == digest):
            matches.append(artifact)
    c.require(len(matches) == 1, 'Exactly one frozen sidecar artifact required')
    artifact = matches[0]
    c.require(b.sha(artifact['path']) == artifact['sha256'], 'Frozen sidecar artifact changed')
    return Path(artifact['path'])


def derive(previous_pipeline, content, catalog):
    previous = Path(previous_pipeline).resolve()
    protocol = b.read(previous/'protocol.json')
    bundle = evidence.load_bundle(protocol['evidence_manifest'])
    case = b.read(bundle['manifest']['case_path'])
    c.require(b.sha(protocol['case_path']) == protocol['case_sha256'] and
              protocol['case_path'] == bundle['manifest']['case_path'], 'Original case binding changed')
    c.require(b.sha(protocol['evidence_manifest']) == protocol['evidence_sha256'] and
              b.sha(previous/'passages.json') == protocol['passages_sha256'] and
              catalog == b.read(previous/'passages.json') == passages.catalog(bundle['manifest']),
              'Original evidence or passage catalogue changed')
    # Native annotation/grounding policies are not silently upgraded in this path.
    implementations = {}
    for module in (reviewed, transcript, qa):
        path = Path(module.__file__)
        records = [x for x in protocol['code'] if Path(x['path']).name == path.name]
        c.require(len(records) == 1 and b.sha(records[0]['path']) == records[0]['sha256'] == b.sha(path),
                  'Original native source policy differs from executing code')
        implementations[path.name] = b.sha(path)
    selection_path = frozen_artifact(case, case['transcript_sidecar_selection_path'])
    selection = b.read(selection_path)
    proposal_path = frozen_artifact(case, selection['proposal_path'], selection['proposal_sha256'])
    review_path = frozen_artifact(case, selection['review_path'], selection['review_sha256'])
    index = bundle['transcript_index']
    c.require(case['transcript_sidecar'] == index.get('reviewed_sidecar'), 'Original reviewed sidecar differs')
    raw_sources = [s for s in case['sources'] if s['kind'] == 'transcript' and s['representation'] == 'raw'
                   and s['document_id'] == selection['document_id'] and s['sha256'] == selection['raw_sha256']]
    c.require(len(raw_sources) == 1, 'Exact original raw transcript required')
    source = {k: selection[k] for k in ('document_id', 'issuer_id', 'raw_sha256', 'text_sha256')}
    source.update(catalog_id=index['issuer_affiliation']['catalog_id'], issuer_names=index['issuer_affiliation']['names'])
    reapplied = reviewed.apply_reviewed_sidecar(
        Path(case['transcript_path']).read_bytes().decode('utf-8'), Path(raw_sources[0]['path']).read_bytes(),
        source, proposal_path.read_bytes(), review_path.read_bytes(), selection)
    c.require(reapplied == index, 'Native source replay differs from entire original index')
    proposal, review = b.read(proposal_path), b.read(review_path)
    decisions = [row for row in review.get('decisions', []) if row.get('symbol') == proposal.get('symbol')]
    c.require(len(decisions) == 1 and decisions[0].get('dialogue_function_decision') == 'pass'
              and decisions[0].get('qa_decision') == 'pass', 'Explicit reviewed dialogue and boundary approval required')
    boundary = index['reviewed_sidecar']['first_substantive_question_turn_start']
    c.require(boundary == proposal['qa_proposal']['first_substantive_question_turn_start'], 'Reviewed question boundary changed')
    frozen = b.read(previous/'qa-grounding.json')
    c.require(b.sha(previous/'qa-grounding.json') == protocol['qa_grounding_sha256'], 'Original grounding changed')
    rebuilt = qa.build(bundle, catalog, version=frozen['version'])
    c.require(rebuilt == frozen, 'Original grounding does not reproduce')
    derived = copy.deepcopy(rebuilt)
    turns = {t['id']: t for t in reapplied['turns']}
    dispositions = []
    for item in derived['unassigned_qa_turns']:
        if item['mechanical_disposition'] != 'unresolved':
            continue
        turn = turns[item['id']]
        # All other unassigned content stays unresolved and fails the full check.
        if not (turn['section_kind'] == 'qa' and turn['end'] <= boundary
                and turn['dialogue_function'] in FUNCTIONS
                and turn['indexed_dialogue_function'] == turn['dialogue_function']):
            continue
        matching = [x for x in proposal['dialogue_function_proposals']
                    if all(x.get(k) == turn[k] for k in ('start', 'end', 'dialogue_function'))
                    and x.get('source_speaker') == turn['speaker']]
        c.require(len(matching) == 1, 'Exact whole-turn reviewed annotation required')
        before = b.digest(item)
        item['mechanical_disposition'] = DISPOSITION
        item['reviewed_turn_disposition'] = {
            'dialogue_function': turn['dialogue_function'], 'boundary': boundary,
            'proposal_sha256': selection['proposal_sha256'], 'review_sha256': selection['review_sha256']}
        dispositions.append({'turn_id': turn['id'], 'start': turn['start'], 'end': turn['end'],
                             'text_sha256': turn['text_sha256'], 'dialogue_function': turn['dialogue_function'],
                             'before_sha256': before, 'after_sha256': b.digest(item)})
    candidate, links = qa.prune_unused_continuations(content, derived)
    pipe.validate('retrieval', candidate, {**bundle, 'qa_grounding': derived}, catalog)
    return {'content': candidate, 'grounding': derived, 'derivation': {
        'version': VERSION, 'native_index_sha256': b.digest(reapplied),
        'original_grounding_sha256': b.digest(rebuilt), 'derived_grounding_sha256': b.digest(derived),
        'original_content_sha256': b.digest(content), 'derived_content_sha256': b.digest(candidate),
        'pre_question_dispositions': dispositions, 'pruned_links': links,
        'source_bindings': {'selection_sha256': b.sha(selection_path),
                            'proposal_sha256': selection['proposal_sha256'], 'review_sha256': selection['review_sha256'],
                            'raw_sha256': selection['raw_sha256'], 'text_sha256': selection['text_sha256'],
                            'first_substantive_question_turn_start': boundary},
        'native_implementation_sha256': implementations,
        'full_qa_validation': 'passed', 'acceptance': 'unreviewed retrieval; original complete sources and fresh report review required'}}
