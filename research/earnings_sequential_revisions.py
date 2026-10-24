"""Exact narrative replacements for a reviewed, frozen sequential report.

No model calls, workflow transitions, file writes or acceptance decisions occur
here. A fresh reviewer still evaluates every criterion and expected question.
The caller validates the merged full analysis with its ordinary schema validator.
"""
from __future__ import annotations

import copy
import hashlib
import json
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
    """Return a verified patch plan, or None for initial/full table-repair work.

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
    if "financial_tables" in locations:
        return None
    _require(locations <= set(LOCATIONS), "Unknown review finding location")
    if any(record.get("action") == "rebuild_tables" and record.get("revision_round") == revision-1
           for record in job.get("administrative_history", [])):
        return None
    author_positions = [index for index, attempt in enumerate(job["attempts"])
                        if attempt["stage"] == "analysis" and attempt.get("revision_round") == revision-1
                        and attempt.get("outcome", {}).get("outputs", {}).get(analysis_name) == job["artifacts"][analysis_name]]
    _require(author_positions, "Prior author artifact lacks an attempt binding")
    previous_tables = next((attempt.get("outcome", {}).get("outputs", {})
                            for attempt in reversed(job["attempts"][:author_positions[-1]])
                            if attempt["stage"] == "financial_tables" and attempt.get("status") == "completed"), None)
    _require(previous_tables is not None and all(name in previous_tables for name in FINANCIAL_FILES),
             "Prior financial calculation binding required")
    if any(previous_tables[name] != frozen[name] for name in FINANCIAL_FILES):
        return None
    original_sources = next((attempt.get("outcome", {}).get("outputs", {})
                             for attempt in job["attempts"][:author_positions[-1]]
                             if attempt["stage"] == "sources" and attempt.get("status") == "completed"), None)
    _require(original_sources and all(job["artifacts"].get(name) == digest for name, digest in original_sources.items()),
             "Original source or writing-standard bindings changed")
    reviewers = [attempt for attempt in job["attempts"] if attempt["stage"] == "review"
                 and attempt.get("revision_round") == revision-1
                 and attempt.get("outcome", {}).get("outputs", {}).get(review_name) == job["artifacts"][review_name]]
    _require(reviewers, "Prior review artifact lacks an attempt binding")
    before = render_candidate(analysis, _read(root / "financial-analysis.json"), root / "sources/manifest.json")
    candidate_sha = _text_sha(before)
    _require(reviewers[-1]["outcome"].get("input_sha256") == candidate_sha, "Prior analysis does not reconstruct the reviewed candidate")
    if job.get("revision_input"):
        _require(job["revision_input"].get(job["candidate_artifact"]) == candidate_sha, "Correction candidate binding changed")
    allowed = [location for location in LOCATIONS if location in locations]
    components = _components(analysis)
    citations = set().union(*(_citations(components[name]) for name in allowed), _citations(review["findings"]))
    return {"version": VERSION, "revision_round": revision, "previous_analysis": analysis, "previous_review": review,
            "allowed_locations": allowed, "citations": sorted(citations),
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
            "analysis_before_digest": _digest(fresh["previous_analysis"]), "analysis_after_digest": _digest(merged),
            "candidate_before_sha256": fresh["previous_candidate_sha256"], "candidate_after_sha256": _text_sha(candidate_text),
            "component_changes": {name: {"before": _digest(_components(fresh["previous_analysis"])[name]),
                                         "after": _digest(_components(merged)[name])} for name in fresh["allowed_locations"]},
            "previous_passed_criteria": fresh["previous_passed_criteria"],
            "review_requirement": "Fresh independent review must assess all eight criteria and all five expected questions."}


def load(root, job, render_candidate):
    """Verify the saved delta and both candidates before the fresh review."""
    root = Path(root).resolve()
    name = f"correction-r{job['revision_round']}.json"
    if name not in job["artifacts"]:
        return None
    _verify(root, {name: job["artifacts"][name]})
    revision_plan = plan(root, job, render_candidate)
    _require(revision_plan is not None, "Saved narrative patch is not valid for a full table rebuild")
    analysis_name = f"analysis-r{job['revision_round']}.json"
    _require(analysis_name in job["artifacts"] and job["candidate_artifact"] in job["artifacts"], "Bound replacement analysis and candidate required")
    merged = _read(root / analysis_name)
    candidate_text = _path(root, job["candidate_artifact"]).read_text()
    proof = _read(root / name)
    _require(proof == audit(root, job, revision_plan, merged, candidate_text, render_candidate), "Saved revision proof changed")
    return {"plan": revision_plan, "proof": proof}
