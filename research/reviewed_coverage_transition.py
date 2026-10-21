"""Exact generated source-index equality across a pinned parser provenance change.

Callers must authenticate the independent coverage approval and catalog relocation
separately. No source address, speaker, boundary, function or review is inferred.
"""
import copy
import re
from .contracts import digest, require
VERSION = 'exact-reviewed-index-parser-provenance-transition-v1'
FILES = {'research/transcript_evidence.py', 'research/reviewed_transcript_index.py'}

def verify(before, after, approved_index_sha256, approved_implementation, current_implementation):
    require(set(approved_implementation) == FILES == set(current_implementation), 'Exact coverage producer files required')
    require(all(isinstance(v,str) and re.fullmatch('[a-f0-9]{64}',v) for v in [approved_index_sha256,*approved_implementation.values(),*current_implementation.values()]), 'Exact approved producer hashes required')
    require(digest(before) == approved_index_sha256, 'Independent approved baseline changed')
    require(before.get('boundary_review') == after.get('boundary_review') == 'partially_reviewed' and before.get('needs_review') is after.get('needs_review') is True, 'Do not promote source or whole-report review')
    require(before.get('parser_sha256') == approved_implementation['research/transcript_evidence.py'] and after.get('parser_sha256') == current_implementation['research/transcript_evidence.py'], 'Actual parser provenance required')
    require(before.get('source') and before.get('turns') and before.get('exchanges') and before.get('reviewed_sidecar'), 'Complete independently reviewed native index required')
    # Everything else, including every source offset and generated ID, is exact.
    old, new = copy.deepcopy(before), copy.deepcopy(after)
    old.pop('parser_sha256'); new.pop('parser_sha256')
    require(old == new, 'Generated source index changed beyond parser provenance')
    return {'version':VERSION,'approved_index_sha256':approved_index_sha256,'current_index_sha256':digest(after),'approved_implementation':approved_implementation,'current_implementation':current_implementation,'whole_report_accepted':False}
