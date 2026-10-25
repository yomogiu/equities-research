"""Exact narrative replacements for a reviewed, frozen sequential report.

No model calls, workflow transitions, file writes or acceptance decisions occur
here. A fresh reviewer still evaluates every criterion and expected question.
The caller validates the merged full analysis with its ordinary schema validator.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

VERSION = "sequential-narrative-revision-v1"
LOCATIONS = ("opening", "demand", "earnings", "cash", "outlook", "qa", "next_tests")
SECTIONS = ("demand", "earnings", "cash", "outlook")
FINANCIAL_FILES = ("financial-configuration.json", "financial-analysis.json", "financial-tables.md")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _text_sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _digest(value):
    return _text_sha(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False))


def _read(path):
    return json.loads(Path(path).read_text())


def _path(root, name):
    path = root / name
    _require(isinstance(name, str) and not Path(name).is_absolute() and ".." not in Path(name).parts
             and root in path.resolve().parents, "Revision artifact must remain inside job")
    return path


def _verify(root, files):
    for name, expected in files.items():
        path = _path(root, name)
        _require(path.is_file() and _sha(path) == expected, "Revision artifact changed: " + name)


def _components(analysis):
    return {"title": analysis["title"], "opening": analysis["opening"],
            **{name: analysis["sections"][name] for name in SECTIONS},
            "qa": analysis["qa"], "next_tests": analysis["next_tests"]}


def _citations(value):
    if isinstance(value, dict):
        return set(value.get("citations", [])) | set().union(*(_citations(v) for k, v in value.items() if k != "citations"))
    if isinstance(value, list):
        return set().union(*(_citations(v) for v in value))
    return set()


def _source_bindings(root):
    manifest = _read(root / "sources/manifest.json")
    case_path = Path(manifest["case_path"])
    _require(_sha(case_path) == manifest["case_sha256"], "Frozen source case changed")
    case = _read(case_path)
    records = [{"path": str(case_path), "sha256": manifest["case_sha256"]}]
    for item in [*case.get("sources", []), *case.get("artifacts", [])]:
        _require(_sha(item["path"]) == item["sha256"], "Frozen original source changed")
        records.append({"path": item["path"], "sha256": item["sha256"]})
    return records


def plan(root, job, render_candidate):
    """Return a verified patch plan, or None for the initial author.

    ``render_candidate(analysis, financial, manifest_path)`` must be the actual
    renderer. Prior candidate bytes are reconstructed and matched to the prior
    review's exact input hash, including when report.md now holds a newer draft.
    """
    root = Path(root).resolve()
    revision = job["revision_round"]
    if revision == 0:
        return None
    _verify(root, job["artifacts"])
    _verify(root, job.get("revision_input", {}))
    frozen = {name: digest for name, digest in job["artifacts"].items()
              if name in (*FINANCIAL_FILES, "writing-standard.md", "passages.json") or name.startswith("sources/")}
    _require(set((*FINANCIAL_FILES, "sources/manifest.json", "writing-standard.md")) <= frozen.keys(),
             "Frozen financial/source/writing artifacts required")
    sources = _source_bindings(root)
    analysis_name, review_name = f"analysis-r{revision-1}.json", f"review-r{revision-1}.json"
    _require(analysis_name in job["artifacts"] and review_name in job["artifacts"], "Bound prior analysis and review required")
    analysis = _read(root / analysis_name)
    review = _read(root / review_name)
    _require(review.get("verdict") == "revise" and isinstance(review.get("findings"), list)
             and review["findings"], "Actionable prior review findings required")
    locations = {row.get("location") for row in review["findings"]}
    table_repair = "financial_tables" in locations
    _require(locations <= set(LOCATIONS) | {'financial_tables'}, "Unknown review finding location")
    locations.discard('financial_tables')
    author_positions = [index for index, attempt in enumerate(job["attempts"])
                        if attempt["stage"] == "analysis" and attempt.get("revision_round") == revision-1
                        and attempt.get("outcome", {}).get("outputs", {}).get(analysis_name) == job["artifacts"][analysis_name]]
    _require(author_positions, "Prior author artifact lacks an attempt binding")
    previous_tables = next((attempt.get("outcome", {}).get("outputs", {})
                            for attempt in reversed(job["attempts"][:author_positions[-1]])
                            if attempt["stage"] == "financial_tables" and attempt.get("status") == "completed"), None)
    _require(previous_tables is not None and all(name in previous_tables for name in FINANCIAL_FILES),
             "Prior financial calculation binding required")
    financial_before = _read(root / 'financial-analysis.json')
    table_changes = {}
    prior_financial_artifacts = {}
    added_table_citations = set()
    if any(previous_tables[name] != frozen[name] for name in FINANCIAL_FILES):
        _require(table_repair, 'Changed tables require an independent table finding')
        for name in FINANCIAL_FILES:
            archive = f'history/financial-r{revision-1}/{name}'
            _require(job['artifacts'].get(archive) == previous_tables[name], 'Prior financial archive differs from reviewed table inputs')
            prior_financial_artifacts[archive] = previous_tables[name]
        _verify(root, prior_financial_artifacts)
        financial_before = _read(root / f'history/financial-r{revision-1}/financial-analysis.json')
        from . import earnings_financial_analysis_report as finance
        before_sections = finance.sections(financial_before)
        after_sections = finance.sections(_read(root/'financial-analysis.json'))
        for name in sorted(set(before_sections) | set(after_sections)):
            before_text = '\n'.join(before_sections.get(name, []))
            after_text = '\n'.join(after_sections.get(name, []))
            if before_text != after_text:
                _require(name in SECTIONS, 'Changed financial table lacks an affected narrative section')
                locations.add(name)
                table_changes[name] = {'before': _text_sha(before_text), 'after': _text_sha(after_text)}
                added_table_citations.update(set(re.findall(r'\[\^([A-Za-z0-9_-]+)\]',after_text))
                    - set(re.findall(r'\[\^([A-Za-z0-9_-]+)\]',before_text)))
        _require(table_changes, 'Financial repair made no visible table changes')
    elif table_repair:
        raise ValueError('Financial finding requires changed, archived tables')
    original_sources = next((attempt.get("outcome", {}).get("outputs", {})
                             for attempt in job["attempts"][:author_positions[-1]]
                             if attempt["stage"] == "sources" and attempt.get("status") == "completed"), None)
    _require(original_sources and all(job["artifacts"].get(name) == digest for name, digest in original_sources.items()),
             "Original source or writing-standard bindings changed")
    reviewers = [attempt for attempt in job["attempts"] if attempt["stage"] == "review"
                 and attempt.get("revision_round") == revision-1
                 and attempt.get("outcome", {}).get("outputs", {}).get(review_name) == job["artifacts"][review_name]]
    _require(reviewers, "Prior review artifact lacks an attempt binding")
    before = render_candidate(analysis, financial_before, root / "sources/manifest.json")
    candidate_sha = _text_sha(before)
    _require(reviewers[-1]["outcome"].get("input_sha256") == candidate_sha, "Prior analysis does not reconstruct the reviewed candidate")
    if job.get("revision_input"):
        _require(job["revision_input"].get(job["candidate_artifact"]) == candidate_sha, "Correction candidate binding changed")
    allowed = [location for location in LOCATIONS if location in locations]
    components = _components(analysis)
    citations = set().union(*(_citations(components[name]) for name in allowed), _citations(review["findings"]), added_table_citations)
    return {"version": VERSION, "revision_round": revision, "previous_analysis": analysis, "previous_review": review,
            "allowed_locations": allowed, "citations": sorted(citations),
            "table_changes": table_changes, "prior_financial_artifacts": prior_financial_artifacts,
            "baseline_artifacts": {analysis_name: job["artifacts"][analysis_name], review_name: job["artifacts"][review_name]},
            "frozen_artifacts": frozen, "original_sources": sources, "previous_candidate_sha256": candidate_sha,
            "unchanged_components": {name: _digest(value) for name, value in components.items() if name not in allowed},
            "previous_passed_criteria": {name: copy.deepcopy(row) for name, row in review.get("criteria", {}).items()
                                         if row.get("status") == "pass"}}


def _shape(location, value):
    def paragraph(row, heading=False):
        _require(isinstance(row, dict) and (set(row) == {"text", "citations"}
                 or heading and set(row) == {"heading", "text", "citations"}), "Exact replacement paragraph fields required")
    if location in SECTIONS or location == "opening":
        paragraph(value, location in SECTIONS)
    else:
        _require(isinstance(value, list), "Replacement must retain the original list shape")
        for row in value:
            if location == "next_tests":
                paragraph(row)
            else:
                _require(isinstance(row, dict) and set(row) == {"exchange_id", "question", "answer", "assessment", "citations"},
                         "Exact replacement Q&A fields required")


def apply(revision_plan, response):
    """Apply exactly the affected components; the caller validates the full result."""
    _require(isinstance(response, dict) and set(response) == {"replacements"}, "Exact replacements response required")
    replacements = response["replacements"]
    _require(isinstance(replacements, dict) and set(replacements) == set(revision_plan["allowed_locations"]),
             "Replacements must contain exactly the reviewed locations")
    merged = copy.deepcopy(revision_plan["previous_analysis"])
    for location, replacement in replacements.items():
        _shape(location, replacement)
        _require(replacement != _components(merged)[location], "A reviewed replacement must change its component")
        if location in SECTIONS:
            merged["sections"][location] = copy.deepcopy(replacement)
        else:
            merged[location] = copy.deepcopy(replacement)
    _require(all(_digest(_components(merged)[name]) == digest for name, digest in revision_plan["unchanged_components"].items()),
             "Unreviewed component changed")
    return merged


def exact_deletions(revision_plan):
    """Apply only unambiguous reviewer-requested sentence deletions, or decline.

    This creates no new claims or citations. Every affected component must have
    an explicit deletion finding; other repairs still go to the correction model.
    A fresh reviewer, not this syntax recognizer, decides whether all fixes suffice.
    """
    if revision_plan is None: return None
    replacements = {}
    for location in revision_plan['allowed_locations']:
        original = _components(revision_plan['previous_analysis'])[location]
        if not isinstance(original, dict) or 'text' not in original: return None
        findings = [row for row in revision_plan['previous_review']['findings'] if row['location']==location]
        if not findings: return None
        text = original['text']
        for finding in findings:
            fix = finding['fix']
            if re.search(r'\b(?:add|replace|rewrite|insert|calculate|rephrase)\b',fix,re.I): return None
            prefix = re.search(r"delete the sentence beginning ['‘]([^'’]+)['’]",fix,re.I)
            suffix = re.search(r"sentence ending ['‘]([^'’]+)['’]",finding['problem'],re.I)
            if prefix:
                mode, fragment = 'prefix', prefix.group(1)
            elif suffix and re.search(r'\bdelete that sentence\b',fix,re.I):
                mode, fragment = 'suffix', suffix.group(1)
            else: return None
            if len(fragment)<12 or text.count(fragment)!=1: return None
            sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])',text)
            matches = [i for i,sentence in enumerate(sentences) if
                       (sentence.startswith(fragment) if mode=='prefix' else
                        sentence.rstrip('.!?').endswith(fragment.rstrip('.!?')))]
            if len(matches)!=1: return None
            del sentences[matches[0]]
            text = ' '.join(sentences).strip()
            if not text: return None
        replacements[location] = {**copy.deepcopy(original),'text':text}
    response = {'replacements':replacements}
    apply(revision_plan,response)  # Same exact-component schema and unchanged-content checks.
    return response


def audit(root, job, revision_plan, merged, candidate_text, render_candidate):
    """Return a deterministic delta proof before writing the replacement draft."""
    fresh = plan(root, job, render_candidate)
    _require(fresh is not None and fresh == revision_plan, "Revision plan or frozen inputs changed")
    replacements = {name: _components(merged)[name] for name in fresh["allowed_locations"]}
    _require(apply(fresh, {"replacements": replacements}) == merged, "Merged analysis changed an unreviewed component")
    root = Path(root).resolve()
    _require(render_candidate(merged, _read(root / "financial-analysis.json"), root / "sources/manifest.json") == candidate_text,
             "Replacement candidate does not match the merged analysis")
    return {"version": VERSION, "revision_round": fresh["revision_round"], "changed_locations": fresh["allowed_locations"],
            "baseline_artifacts": fresh["baseline_artifacts"], "frozen_artifacts": fresh["frozen_artifacts"],
            "original_sources": fresh["original_sources"], "unchanged_components": fresh["unchanged_components"],
            "table_changes": fresh["table_changes"], "prior_financial_artifacts": fresh["prior_financial_artifacts"],
            "analysis_before_digest": _digest(fresh["previous_analysis"]), "analysis_after_digest": _digest(merged),
            "candidate_before_sha256": fresh["previous_candidate_sha256"], "candidate_after_sha256": _text_sha(candidate_text),
            "component_changes": {name: {"before": _digest(_components(fresh["previous_analysis"])[name]),
                                         "after": _digest(_components(merged)[name])} for name in fresh["allowed_locations"]},
            "previous_passed_criteria": fresh["previous_passed_criteria"],
            "review_requirement": "Fresh independent review must assess all eight criteria and all five expected questions."}


def load(root, job, render_candidate):
    """Verify the saved delta and both candidates before the fresh review."""
    root = Path(root).resolve()
    if job.get('editorial_repair'):
        from . import earnings_sequential_editorial as editorial
        return editorial.load(root, job, render_candidate)
    name = f"correction-r{job['revision_round']}.json"
    if name not in job["artifacts"]:
        return None
    _verify(root, {name: job["artifacts"][name]})
    revision_plan = plan(root, job, render_candidate)
    _require(revision_plan is not None, "Saved correction requires a verified prior candidate")
    analysis_name = f"analysis-r{job['revision_round']}.json"
    _require(analysis_name in job["artifacts"] and job["candidate_artifact"] in job["artifacts"], "Bound replacement analysis and candidate required")
    merged = _read(root / analysis_name)
    candidate_text = _path(root, job["candidate_artifact"]).read_text()
    proof = _read(root / name)
    _require(proof == audit(root, job, revision_plan, merged, candidate_text, render_candidate), "Saved revision proof changed")
    return {"plan": revision_plan, "proof": proof}
