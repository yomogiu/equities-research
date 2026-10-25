"""Five-stage controller with one authoritative, durable ``job.json``.

Handlers perform one stage and return ``status`` (completed, blocked, revise),
``outputs`` (relative artifact paths mapped to SHA-256), and ``tokens`` (all
input, cached-input and output usage). Analysis/review also return a fresh
``session_id``; review/publication bind ``input_sha256`` to the exact candidate.
Only review may request revision. Financial tables must consume zero tokens.

Handlers must enforce the remaining token budget before each paid call. They
should call :func:`save_outcome` immediately after external work is durably
complete, particularly publication. That result is stored *inside job.json*.
A crash before that checkpoint is uncertain, never an automatic retry, unless
a non-model handler explicitly declares ``replay_safe = True``. That promise
means zero paid calls and idempotent effects; it is only allowed for sources,
financial tables and publication. Otherwise an operator must reconcile the
external operation before making another attempt.
Artifact names are relative to the job directory. Retained source/table files
must never be overwritten. The controller runs at most one stage per advance.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

STAGES = ("sources", "financial_tables", "analysis", "review", "publication")
ALL_STAGES = (*STAGES, "financial_selection")
MODEL_STAGES = ("financial_selection", "analysis", "review")
MAX_TOKENS = 1_200_000
_ACTIVE = ContextVar("sequential_stage", default=None)


def _integer(value, label, minimum=0, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"invalid {label}")
    return value


def _artifact(root, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute() or ".." in Path(name).parts:
        raise ValueError("artifact path must be relative and contained in the job directory")
    path = root / name
    if path.resolve() == root or root not in path.resolve().parents:
        raise ValueError("artifact path escapes job directory")
    if path.resolve() in (root / "job.json", root / ".job.lock"):
        raise ValueError("reserved artifact path")
    return path


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(root, job):
    data = json.dumps(job, indent=2, sort_keys=True, allow_nan=False) + "\n"
    fd, name = tempfile.mkstemp(prefix=".job-", suffix=".tmp", dir=root)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, root / "job.json")
        directory = os.open(root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def _lock(root):
    with (root / ".job.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def _read(root):
    return json.loads((root / "job.json").read_text())


def create(root, specification):
    """Create a new job; never replace or reset an existing job/budget."""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    specification = copy.deepcopy(specification)
    budget = _integer(specification.get("budget_tokens", MAX_TOKENS), "budget_tokens", 1, MAX_TOKENS)
    rounds = _integer(specification.get("max_revision_rounds", 2), "max_revision_rounds", 0, 2)
    candidate = specification.get("candidate_artifact", "report.md")
    _artifact(root, candidate)
    job = dict(schema_version=1, specification=specification, stage=STAGES[0], status="ready",
               budget_tokens=budget, tokens_used=0, revision_round=0, max_revision_rounds=rounds,
               candidate_artifact=candidate, artifacts={}, attempts=[], accepted_candidate_sha256=None)
    with _lock(root):
        if (root / "job.json").exists():
            raise FileExistsError("job already exists; creating cannot reset its history")
        _write(root, job)
    return job


def save_outcome(root, result):
    """Checkpoint a handler's outcome in job.json while its advance lock is held.

    Call this before returning after an externally visible action. A subsequent
    advance consumes a saved outcome without invoking the handler again.
    """
    root = Path(root).resolve()
    active = _ACTIVE.get()
    if active is None or active[0] != root:
        raise RuntimeError("save_outcome is only permitted inside this job's active handler")
    job = _read(root)
    if job["status"] != "running" or job["attempts"][-1]["id"] != active[1]:
        raise RuntimeError("active attempt changed")
    attempt = job["attempts"][-1]
    if "outcome" in attempt and attempt["outcome"] != result:
        raise ValueError("a saved outcome is immutable")
    attempt["outcome"] = copy.deepcopy(result)
    _write(root, job)


def _verify(root, artifacts):
    for name, expected in artifacts.items():
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise ValueError(f"invalid artifact digest: {name}")
        path = _artifact(root, name)
        if not path.is_file() or _digest(path) != expected:
            raise ValueError(f"artifact missing or changed: {name}")


def _block(root, job, reason):
    job.update(status="blocked", reason=reason)
    if job["attempts"] and job["attempts"][-1]["status"] == "running":
        job["attempts"][-1]["status"] = "blocked"
    final = job.get("final_review")
    if final and job["attempts"] and final.get("attempt_id") == job["attempts"][-1]["id"] and job["attempts"][-1]["stage"] == "review":
        final["state"] = "blocked"
    _write(root, job)
    return job


def _finish(root, job):
    attempt = job["attempts"][-1]
    outcome = attempt["outcome"]
    stage = attempt["stage"]
    try:
        tokens = _integer(outcome.get("tokens"), "outcome tokens")
    except (ValueError, AttributeError) as exc:
        return _block(root, job, str(exc))
    # Charge even a malformed/failed outcome; an invalid result never resets usage.
    if not attempt.get("usage_recorded"):
        job["tokens_used"] += tokens
        attempt["usage_recorded"] = True
    try:
        status = outcome.get("status")
        if status not in ("completed", "blocked", "revise") or (status == "revise" and stage != "review"):
            raise ValueError("invalid stage outcome status")
        outputs = outcome.get("outputs", {})
        if not isinstance(outputs, dict):
            raise ValueError("outputs must be an artifact mapping")
        _verify(root, job["artifacts"])
        _verify(root, outputs)
        final = job.get("final_review")
        if final:
            _verify(root, final["artifacts"])
            if stage == "review" and (attempt["id"] != final.get("attempt_id") or final["state"] != "running"):
                raise ValueError("final review allowance belongs to one exact attempt")
            if stage == "publication" and (tokens != 0 or final["state"] != "accepted"):
                raise ValueError("final review allowance permits only zero-token publication after acceptance")
        if any(name in job["artifacts"] and job["artifacts"][name] != digest for name, digest in outputs.items()):
            raise ValueError("stage overwrote a retained artifact")
        if job["tokens_used"] > job["budget_tokens"]:
            raise ValueError("token budget exceeded")
        if stage == "financial_tables" and tokens != 0:
            raise ValueError("financial tables must be deterministic and use zero model tokens")
        if attempt.get("replay_safe") and tokens != 0:
            raise ValueError("replay-safe handler must use zero model tokens")
        if status == "blocked":
            return _block(root, job, str(outcome.get("reason", "stage blocked")))
        if final and status == "revise":
            return _block(root, job, "final authorized review requires corrections; no further correction authorized")
        if not outputs:
            raise ValueError("completed stage requires durable output artifacts")
        deterministic_revision = stage == 'analysis' and outcome.get('execution_kind') == 'deterministic_revision'
        if deterministic_revision:
            proof_name = f"correction-r{job['revision_round']}.json"
            if tokens != 0 or not job['revision_round'] or proof_name not in outputs or outcome.get('session_id'):
                raise ValueError('Deterministic revision requires zero tokens, no model session and a bound correction proof')
            proof = json.loads(_artifact(root, proof_name).read_text())
            prior_review = f"review-r{job['revision_round']-1}.json"
            if (prior_review not in job['artifacts'] or proof.get('candidate_after_sha256') != outputs.get(job['candidate_artifact'])
                    or proof.get('baseline_artifacts', {}).get(prior_review) != job['artifacts'].get(prior_review)):
                raise ValueError('Deterministic revision proof does not bind candidate and independent review')
        if stage in MODEL_STAGES and not deterministic_revision:
            session = outcome.get("session_id")
            if not isinstance(session, str) or not session:
                raise ValueError("analysis/review requires an attributable session_id")
            prior = [a.get("outcome", {}).get("session_id") for a in job["attempts"][:-1]
                     if a["stage"] in MODEL_STAGES]
            prior.extend(item.get('session_id') for item in job.get('administrative_history',[]) if item.get('action')=='adopt_financial_selection')
            if session in prior:
                raise ValueError("analysis/review must use a fresh independent session")
        if stage == 'financial_selection':
            name = f"financial-selection-r{job['revision_round']}.json"
            if set(outputs) != {name}: raise ValueError('Selection must produce one bound immutable mapping')
        if stage == "analysis" and job["candidate_artifact"] not in outputs:
            raise ValueError("analysis did not produce the candidate artifact")
        if stage == 'analysis' and job.get('single_author_enabled') and not job['revision_round']:
            required={'financial-selection-r0.json','financial-analysis.json','financial-configuration.json','financial-tables.md','analysis-r0.json'}
            if not required<=outputs.keys():raise ValueError('Combined author requires selection, computed tables and analysis')
        if stage == 'analysis' and job.get('single_author_enabled') and job['revision_round']:
            if not {f"analysis-r{job['revision_round']}.json",f"correction-r{job['revision_round']}.json"}<=outputs.keys():
                raise ValueError('Single-author correction requires merged analysis and immutable delta proof')
        if stage in ("review", "publication"):
            candidate = job["artifacts"].get(job["candidate_artifact"])
            if not candidate or outcome.get("input_sha256") != candidate:
                raise ValueError("outcome does not bind the exact candidate")
            if stage == "publication" and job["accepted_candidate_sha256"] != candidate:
                raise ValueError("publication candidate was not accepted")
        target = outcome.get('revision_target', 'analysis')
        if target not in ('analysis', 'financial_tables') or ('revision_target' in outcome and (stage != 'review' or status != 'revise')):
            raise ValueError('invalid revision target')
        if status == 'revise' and target == 'financial_tables':
            from .earnings_sequential_editorial import review_name
            name = review_name(job)
            if name not in outputs or outcome.get('execution_certainty') != 'completed':
                raise ValueError('Automatic table repair requires a completed bound review')
            decision = json.loads(_artifact(root, name).read_text())
            if decision.get('verdict') != 'revise' or not any(row.get('location') == 'financial_tables' for row in decision.get('findings', [])):
                raise ValueError('Review must identify a financial_tables finding')
        if status == 'revise' and job['revision_round'] and 'revision_target' in outcome:
            current = f"review-r{job['revision_round']}.json"
            previous = f"review-r{job['revision_round']-1}.json"
            if current in outputs and previous in job['artifacts']:
                def fingerprint(name):
                    findings = json.loads(_artifact(root, name).read_text()).get('findings', [])
                    return sorted((row.get('location'), ' '.join(row.get('problem', '').split()),
                                   ' '.join(row.get('fix', '').split())) for row in findings)
                if fingerprint(current) and fingerprint(current) == fingerprint(previous):
                    raise ValueError('Repeated unchanged review findings; automatic repair made no progress')
        if status == 'revise' and not job.get('editorial_repair'):
            if job.get('single_author_enabled') and target == 'financial_tables':
                job['artifacts'].update(outputs)
                return _block(root,job,'Single-author financial selection repair requires explicit source-bound migration')
            if not job.get('single_author_enabled') and _editorial_revision(root, job, outputs, outcome):
                attempt['status'] = status
                attempt['outputs'] = outputs
                _write(root, job)
                return job
        if status == 'revise' and job.get('editorial_repair'):
            raise ValueError('Editorial review still requires corrections; bounded repair exhausted')
        if status == "revise" and job["revision_round"] >= job["max_revision_rounds"]:
            job["artifacts"].update(outputs)
            raise ValueError("revision limit reached")
    except (ValueError, OSError) as exc:
        return _block(root, job, str(exc))
    attempt["status"] = status
    attempt["outputs"] = outputs
    if status == 'revise' and target == 'financial_tables':
        try:
            return _table_revision(root, job, outputs, attempt,
                                   job.get('execution_code_commit', job['specification'].get('code_commit')),
                                   'Independent review requested automatic financial repair', automatic=True)
        except (ValueError, OSError) as exc:
            return _block(root, job, str(exc))
    if status == "revise":
        job["revision_round"] += 1
        # Prior findings and structured analysis remain immutable correction
        # inputs. Only the candidate itself may be replaced by the next author.
        job["artifacts"].update(outputs)
        job["revision_input"] = {job["candidate_artifact"]: job["artifacts"].pop(job["candidate_artifact"])}
        job.update(stage="analysis", status="ready", accepted_candidate_sha256=None)
    else:
        job["artifacts"].update(outputs)
        if stage == "analysis":
            job.pop("revision_input", None)
            if job.get('single_author_enabled'):
                job.update(financial_selection_enabled=True,financial_selection_artifact='financial-selection-r0.json')
        if stage == "review":
            job["accepted_candidate_sha256"] = job["artifacts"][job["candidate_artifact"]]
            if job.get("final_review"):
                job["final_review"]["state"] = "accepted"
        if stage == "publication":
            job["status"] = "completed"
        else:
            next_stage = ('financial_tables' if stage == 'financial_selection' else
                          'analysis' if stage == 'sources' and job.get('single_author_enabled') else
                          'financial_selection' if stage == 'sources' and job.get('financial_selection_enabled') else
                          STAGES[STAGES.index(stage) + 1])
            if stage == 'financial_selection':job['financial_selection_artifact'] = name
            job.update(stage=next_stage, status="ready")
    job.pop("reason", None)
    _write(root, job)
    return job


def advance(root, handlers, execute=True):
    """Run one ready stage, or reconcile its saved result. Never retry uncertainty.

    ``execute=False`` is read-only. Completed/blocked/uncertain jobs are returned
    unchanged. Handlers receive a copy with ``remaining_tokens`` added. All paid
    calls, including corrections and review, must fit that remaining allowance.
    """
    root = Path(root).resolve()
    with _lock(root):
        job = _read(root)
        if not execute:
            return job
        replay = None
        if job["status"] == "running":
            if "outcome" in job["attempts"][-1]:
                return _finish(root, job)
            last = job["attempts"][-1]
            if (last.get("replay_safe") and job["stage"] in ("sources", "financial_tables", "publication")
                    and getattr(handlers.get(job["stage"]), "replay_safe", False) is True):
                replay = last
            else:
                job.update(status="execution_uncertain", reason="interrupted stage has no durable outcome; reconcile external work before retrying")
                last["status"] = "execution_uncertain"
                _write(root, job)
                return job
        if job["status"] != "ready" and replay is None:
            return job
        try:
            _verify(root, job["artifacts"])
            _verify(root, job.get("revision_input", {}))
            if job.get("final_review"):
                _verify(root, job["final_review"]["artifacts"])
        except (ValueError, OSError) as exc:
            return _block(root, job, str(exc))
        if job["stage"] == "publication" and (not job["accepted_candidate_sha256"] or
                job["artifacts"].get(job["candidate_artifact"]) != job["accepted_candidate_sha256"]):
            return _block(root, job, "publication requires exact accepted candidate")
        if job["tokens_used"] >= job["budget_tokens"] and job["stage"] in MODEL_STAGES:
            return _block(root, job, "token budget exhausted")
        handler = handlers.get(job["stage"])
        if not callable(handler):
            return _block(root, job, "stage handler unavailable")
        replay_safe = getattr(handler, "replay_safe", False) is True
        final = job.get("final_review")
        if final:
            if job["stage"] == "review":
                if (final["state"] != "authorized" or final.get("attempt_id") is not None
                        or job["tokens_used"] != final["starting_tokens"]
                        or job["budget_tokens"] != final["starting_tokens"] + final["review_cap"]):
                    return _block(root, job, "final review allowance belongs to one exact attempt")
            elif job["stage"] != "publication" or final["state"] != "accepted" or not replay_safe:
                return _block(root, job, "final review allowance cannot fund another stage")
        if replay_safe and job["stage"] not in ("sources", "financial_tables", "publication"):
            return _block(root, job, "model stages cannot declare safe replay")
        if replay is None:
            attempt = dict(id=uuid.uuid4().hex, stage=job["stage"], revision_round=job["revision_round"],
                           status="running", replay_safe=replay_safe)
            job["attempts"].append(attempt)
        else:
            attempt = replay
            attempt["replays"] = attempt.get("replays", 0) + 1
        job["status"] = "running"
        if final and job["stage"] == "review":
            final.update(state="running", attempt_id=attempt["id"])
        _write(root, job)
        context = _ACTIVE.set((root, attempt["id"]))
        try:
            supplied = copy.deepcopy(job)
            supplied["remaining_tokens"] = job["budget_tokens"] - job["tokens_used"]
            outcome = handler(root, supplied)
            save_outcome(root, outcome)
        except Exception as exc:
            current = _read(root)
            if replay_safe and "outcome" not in current["attempts"][-1]:
                # A known local validation failure is terminal, not a crash to
                # retry every wake. Actual process interruption leaves running.
                save_outcome(root, {"status": "blocked", "outputs": {}, "tokens": 0,
                                    "reason": str(exc)})
            else:
                raise
        except BaseException:
            # Keep running + saved outcome if present; next advance reconciles it.
            # Without an outcome the next advance stops as execution_uncertain.
            raise
        finally:
            _ACTIVE.reset(context)
        return _finish(root, _read(root))


def _commit(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ValueError("exact execution code commit required")
    return value


def bind_execution_code(root, code_commit, *, financial_selection=False, single_author=False):
    """Select code for an unstarted job without changing its frozen specification."""
    root = Path(root).resolve()
    code_commit = _commit(code_commit)
    with _lock(root):
        job = _read(root)
        if job["status"] != "ready" or job["attempts"]:
            raise ValueError("only an unstarted ready job can bind execution code")
        job["execution_code_commit"] = code_commit
        if single_author:
            if financial_selection:raise ValueError('Combined author replaces separate financial selection')
            job['single_author_enabled']=True
        if financial_selection:job["financial_selection_enabled"] = True
        _write(root, job)
        return job


def _model_restart(attempt):
    """Classify the recorded attempt, never an operator's description of it."""
    outcome = attempt.get("outcome", {})
    tokens = _integer(outcome.get("tokens"), "recorded outcome tokens")
    if not attempt.get("usage_recorded"):
        raise ValueError("resume history must reference accounted attempts")
    if (tokens == 0 and attempt.get("replay_safe") is True
            and attempt["stage"] in ("sources", "financial_tables", "publication")):
        return False
    if (tokens == 0 and outcome.get("execution_certainty") == "not_started"
            and attempt["stage"] in MODEL_STAGES
            and not outcome.get("session_id") and not outcome.get("execution_directory")):
        return False
    return True


def resume(root, reason, code_commit, *, reconcile=None):
    """Explicitly repair a technical failure; at most two actual model restarts.

    Budgets, evidence, attempts and revision counts are never reset. A legacy
    blocked outcome without certainty may be reconciled by a trusted adapter
    callback ``reconcile(root, job)``. It must validate authenticated execution
    receipts and return ``execution_certainty='closed'``, already charged tokens,
    and ``outputs`` mapping proof-file paths to hashes. The original outcome is
    retained; reconciliation evidence belongs to this same job's admin history.
    Proven zero-token prelaunch and replay-safe deterministic repairs require
    this same explicit action but do not consume the paid/model restart limit.
    """
    root = Path(root).resolve()
    code_commit = _commit(code_commit)
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 4000:
        raise ValueError("explicit bounded operator reason required")
    with _lock(root):
        job = _read(root)
        if job["status"] != "blocked" or job["stage"] not in ALL_STAGES:
            raise ValueError("only a blocked stage can resume")
        if job.get("final_review") and job["stage"] != "publication":
            raise ValueError("final review authorization does not permit another model attempt")
        history = job.get("administrative_history", [])
        if not job["attempts"]:
            raise ValueError("completed failure outcome required")
        attempt = job["attempts"][-1]
        outcome = attempt.get("outcome", {})
        tokens = _integer(outcome.get("tokens"), "closed outcome tokens")
        deterministic = (job["stage"] in ("sources", "financial_tables", "publication")
                         and attempt.get("replay_safe") is True and tokens == 0)
        if job["stage"] not in MODEL_STAGES and not deterministic:
            raise ValueError("deterministic resume requires an accounted zero-token replay-safe stage")
        if not deterministic and job["tokens_used"] >= job["budget_tokens"]:
            raise ValueError("token budget exhausted")
        if (outcome.get("status") == "revise" or
                (job["stage"] == "review" and outcome.get("status") == "blocked" and outcome.get("input_sha256"))):
            raise ValueError("a substantive review decision cannot be retried as a technical failure")
        if attempt["stage"] != job["stage"] or not attempt.get("usage_recorded"):
            raise ValueError("closed attempt must have accounted usage")
        attempts_by_id = {row["id"]: row for row in job["attempts"]}
        if len(attempts_by_id) != len(job["attempts"]):
            raise ValueError("attempt identities must be unique")
        model_restarts = 0
        for item in history:
            if item.get("action") == "resume":
                previous = attempts_by_id.get(item.get("attempt_id"))
                if previous is None:
                    raise ValueError("resume history references an unknown attempt")
                model_restarts += _model_restart(previous)
        if _model_restart(attempt) and model_restarts >= 2:
            raise ValueError("operator model resume limit reached")
        charged = sum(_integer(a["outcome"].get("tokens"), "recorded tokens")
                      for a in job["attempts"] if a.get("usage_recorded"))
        if charged != job["tokens_used"]:
            raise ValueError("cumulative charged usage does not match attempt history")
        _verify(root, job["artifacts"])
        _verify(root, job.get("revision_input", {}))
        certainty = outcome.get("execution_certainty")
        if outcome.get("status") == "completed" or deterministic:
            certainty = "completed"
        elif certainty == "not_started" and _model_restart(attempt):
            # A session, execution directory or charged usage contradicts a
            # prelaunch claim and requires authenticated closure instead.
            certainty = "unknown"
        proof = None
        if certainty not in ("closed", "completed", "not_started"):
            if not callable(reconcile):
                raise ValueError("execution closure must be verified before resume")
            proof = reconcile(root, copy.deepcopy(job))
            if (not isinstance(proof, dict) or proof.get("execution_certainty") != "closed"
                    or _integer(proof.get("tokens"), "reconciled tokens") != tokens
                    or not isinstance(proof.get("outputs"), dict) or not proof["outputs"]):
                raise ValueError("authenticated closure proof must match charged outcome")
            _verify(root, proof["outputs"])
        record = dict(action="resume", reason=reason.strip(), attempt_id=attempt["id"],
                      previous_code_commit=job.get("execution_code_commit", job["specification"].get("code_commit")),
                      code_commit=code_commit, tokens_used=job["tokens_used"], revision_round=job["revision_round"],
                      stage=job["stage"], closure=proof or {"execution_certainty": certainty})
        job.setdefault("administrative_history", []).append(record)
        job.update(status="ready", execution_code_commit=code_commit)
        job.pop("reason", None)
        _write(root, job)
        return job


def automatic_repair_eligible(root):
    """Read-only screening for old closed table findings; rebuild revalidates all bytes."""
    root = Path(root).resolve()
    try:
        job = _read(root)
        if (job['status'] != 'blocked' or job['stage'] != 'review' or job.get('final_review')
                or job['revision_round'] >= job['max_revision_rounds']
                or job['tokens_used'] >= job['budget_tokens'] or not job['attempts']
                or job.get('automatic_table_repair')):
            return False
        attempt = job['attempts'][-1]; result = attempt.get('outcome', {})
        if (result.get('status') != 'blocked' or result.get('execution_certainty') != 'completed'
                or not result.get('session_id') or not attempt.get('usage_recorded')):
            return False
        name = f"review-r{job['revision_round']}.json"
        if name not in result.get('outputs', {}): return False
        _verify(root, {name: result['outputs'][name]})
        review = json.loads(_artifact(root, name).read_text())
        return review.get('verdict') == 'revise' and any(row.get('location') == 'financial_tables' for row in review.get('findings', []))
    except (ValueError, KeyError, TypeError, OSError):
        return False


def rebuild_tables(root, reason, code_commit, *, automatic=False):
    """Explicitly repair tables rejected by review within this job's revision cap.

    Archive the old calculated files as ordinary evidence, retaining their exact
    hashes. Source files, paid usage, prior attempts and the frozen specification
    do not change. The next advance performs financial_tables, then a new author
    and independent review; this operation itself performs no calculation.
    """
    root = Path(root).resolve()
    code_commit = _commit(code_commit)
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 4000:
        raise ValueError("explicit bounded operator reason required")
    with _lock(root):
        job = _read(root)
        if job.get("final_review"):
            raise ValueError("final review authorization does not permit further table corrections")
        if job["status"] != "blocked" or job["stage"] != "review" or not job["attempts"]:
            raise ValueError("table rebuild requires a blocked independent review")
        if job["revision_round"] >= job["max_revision_rounds"]:
            raise ValueError("revision limit reached")
        if job["tokens_used"] >= job["budget_tokens"]:
            raise ValueError("token budget exhausted")
        attempt = job["attempts"][-1]
        outcome = attempt.get("outcome", {})
        if (attempt["stage"] != "review" or outcome.get("status") != "blocked"
                or not attempt.get("usage_recorded") or not outcome.get("session_id")):
            raise ValueError("an accounted independent review result is required")
        charged = sum(_integer(a["outcome"].get("tokens"), "recorded tokens")
                      for a in job["attempts"] if a.get("usage_recorded"))
        if charged != job["tokens_used"]:
            raise ValueError("cumulative charged usage does not match attempt history")
        _verify(root, job["artifacts"])
        _verify(root, job.get("revision_input", {}))
        review_outputs = outcome.get("outputs", {})
        if not isinstance(review_outputs, dict):
            raise ValueError("verified review artifact required")
        _verify(root, review_outputs)
        candidate = job["artifacts"].get(job["candidate_artifact"])
        if not candidate or outcome.get("input_sha256") != candidate:
            raise ValueError("review must bind the exact candidate")
        review_name = f"review-r{job['revision_round']}.json"
        if review_name not in review_outputs:
            raise ValueError("verified review artifact required")
        decision = json.loads(_artifact(root, review_name).read_text())
        if (decision.get("verdict") != "revise" or
                not any(isinstance(row, dict) and row.get("location") == "financial_tables"
                        for row in decision.get("findings", []))):
            raise ValueError("review must identify a financial_tables finding")
        if automatic and outcome.get('execution_certainty') != 'completed':
            raise ValueError('Automatic repair requires a conclusively completed review')
        return _table_revision(root, job, review_outputs, attempt, code_commit, reason, automatic=automatic)


def _table_revision(root, job, review_outputs, attempt, code_commit, reason, *, automatic):
    """Lock-owned transition; one durable round, exact archives, unchanged costs."""
    names = ("financial-configuration.json", "financial-analysis.json", "financial-tables.md")
    if any(name not in job["artifacts"] for name in names):
        raise ValueError("all original financial artifacts must remain bound")
    archives = {}
    for name in names:
        archived = f"history/financial-r{job['revision_round']}/{name}"
        target = _artifact(root, archived)
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = job["artifacts"][name]
        if target.exists():
            _verify(root, {archived: digest})
        else:
            # A crash leaves either an exact archive or an ignorable temp
            # file, never a partial archive that blocks this free repair.
            descriptor, temporary = tempfile.mkstemp(prefix=".archive-", dir=target.parent)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(_artifact(root, name).read_bytes())
                    stream.flush()
                    os.fsync(stream.fileno())
                if _digest(Path(temporary)) != digest:
                    raise ValueError("financial artifact changed during archival")
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            _verify(root, {archived: digest})
        archives[archived] = digest
    record = dict(action="rebuild_tables", reason=reason.strip(), attempt_id=attempt["id"],
                  previous_code_commit=job.get("execution_code_commit", job["specification"].get("code_commit")),
                  code_commit=code_commit, tokens_used=job["tokens_used"],
                  revision_round=job["revision_round"], archived_artifacts=archives)
    job.setdefault("administrative_history", []).append(record)
    job["artifacts"].update(review_outputs)
    job["artifacts"].update(archives)
    for name in names:
        del job["artifacts"][name]
    job["revision_input"] = {job["candidate_artifact"]: job["artifacts"].pop(job["candidate_artifact"])}
    job.update(stage="financial_selection" if job.get("financial_selection_enabled") else "financial_tables", status="ready", revision_round=job["revision_round"] + 1,
               execution_code_commit=code_commit, accepted_candidate_sha256=None)
    job.pop("reason", None)
    if automatic:
        job['financial_repair_policy'] = 'filed-statement-repair-v1'
        job['automatic_table_repair'] = True
        record['automatic'] = True
    _write(root, job)
    return job


def authorize_final_review(root, review_cap, authorization, code_commit):
    """Bind one explicitly approved final review to the unchanged candidate.

    The user-supplied approval is retained verbatim. Existing costs/specification
    stay intact; the only added allowance is ``review_cap`` minus the previously
    remaining budget. No correction or another model attempt may use this grant.
    """
    root = Path(root).resolve()
    review_cap = _integer(review_cap, "final review cap", 1, MAX_TOKENS)
    code_commit = _commit(code_commit)
    if not isinstance(authorization, str) or not authorization.strip() or len(authorization) > 8000:
        raise ValueError("explicit final review authorization required")
    with _lock(root):
        job = _read(root)
        if job.get("final_review"):
            raise ValueError("final review authorization already exists")
        if job["status"] != "blocked" or job["stage"] != "review" or not job["attempts"]:
            raise ValueError("final review requires a blocked unlaunched review")
        attempt = job["attempts"][-1]
        outcome = attempt.get("outcome", {})
        if (attempt["stage"] != "review" or not attempt.get("usage_recorded")
                or outcome.get("status") != "blocked" or _model_restart(attempt)):
            raise ValueError("final review requires an accounted zero-token not_started outcome")
        charged = sum(_integer(row["outcome"].get("tokens"), "recorded tokens")
                      for row in job["attempts"] if row.get("usage_recorded"))
        if charged != job["tokens_used"]:
            raise ValueError("cumulative charged usage does not match attempt history")
        _verify(root, job["artifacts"])
        _verify(root, job.get("revision_input", {}))
        candidate = job["artifacts"].get(job["candidate_artifact"])
        if not candidate:
            raise ValueError("exact candidate artifact required")
        new_budget = job["tokens_used"] + review_cap
        if new_budget <= job["budget_tokens"]:
            raise ValueError("final review approval must specify an additional bounded allowance")
        record = dict(action="authorize_final_review", authorization=authorization, review_cap=review_cap,
                      previous_budget_tokens=job["budget_tokens"], budget_tokens=new_budget,
                      additional_tokens=new_budget - job["budget_tokens"], tokens_used=job["tokens_used"],
                      revision_round=job["revision_round"], candidate_sha256=candidate,
                      previous_code_commit=job.get("execution_code_commit", job["specification"].get("code_commit")),
                      code_commit=code_commit)
        job.setdefault("administrative_history", []).append(record)
        job["final_review"] = dict(state="authorized", attempt_id=None, review_cap=review_cap,
                                   starting_tokens=job["tokens_used"], candidate_sha256=candidate,
                                   artifacts=copy.deepcopy(job["artifacts"]))
        job.update(status="ready", budget_tokens=new_budget, execution_code_commit=code_commit)
        job.pop("reason", None)
        _write(root, job)
        return job


def _editorial_revision(root, job, outputs, outcome):
    from . import earnings_sequential_editorial as editorial
    from .earnings_sequential_stages import render_candidate
    prepared = editorial.prepare(root, job, outputs, outcome, render_candidate)
    if prepared is None: return False
    proof, candidate = prepared
    proof_name = 'editorial-repair-1.json'
    for name, content in ((proof['candidate_after'], candidate),
                          (proof_name, json.dumps(proof, indent=2, sort_keys=True)+'\n')):
        path = _artifact(root, name)
        if path.exists() and path.read_text() != content:
            raise ValueError('Editorial output already exists with different content')
        path.write_text(content)
    job['artifacts'].update(outputs)
    job['artifacts'].update({proof_name:_digest(root/proof_name),
                            proof['candidate_after']:proof['candidate_after_sha256']})
    job['editorial_repair'] = {'proof_artifact':proof_name, 'max_repairs':1,
                              'starting_tokens':job['tokens_used']}
    job.update(candidate_artifact=proof['candidate_after'], stage='review', status='ready',
               accepted_candidate_sha256=None)
    job.pop('reason', None)
    return True


def repair_editorial(root, authorization, code_commit, *, review_cap=None):
    """Adopt a closed review for one deterministic repair plus a fresh review.

    This operator entry is for already blocked jobs; normal completed reviews
    use the same rule without extending budgets. An explicit review request may
    supply one bounded review cap; it never funds analysis or table regeneration.
    """
    root = Path(root).resolve()
    code_commit = _commit(code_commit)
    if not isinstance(authorization, str) or not authorization.strip():
        raise ValueError('Explicit repair authorization required')
    with _lock(root):
        job = _read(root)
        if job['status'] != 'blocked' or job['stage'] != 'review' or not job['attempts']:
            raise ValueError('Editorial repair requires a closed blocked review')
        attempt = job['attempts'][-1]; outcome = attempt.get('outcome', {})
        if (attempt['stage'] != 'review' or not attempt.get('usage_recorded')
                or outcome.get('status') != 'revise'
                or sum(a['outcome']['tokens'] for a in job['attempts'] if a.get('usage_recorded')) != job['tokens_used']):
            raise ValueError('Editorial repair requires fully accounted completed review')
        previous_budget = job['budget_tokens']
        if review_cap is not None:
            review_cap = _integer(review_cap, 'editorial review cap', 1, MAX_TOKENS)
            job['budget_tokens'] = max(previous_budget, job['tokens_used'] + review_cap)
        if not _editorial_revision(root, job, outcome.get('outputs', {}), outcome):
            raise ValueError('No supported presentation-only repair')
        job.setdefault('administrative_history', []).append(dict(action='repair_editorial',
            authorization=authorization, tokens_used=job['tokens_used'], revision_round=job['revision_round'],
            previous_budget_tokens=previous_budget, budget_tokens=job['budget_tokens'], review_cap=review_cap,
            previous_code_commit=job.get('execution_code_commit'), code_commit=code_commit))
        job['execution_code_commit'] = code_commit
        _write(root, job)
        return job


def enable_financial_selection(root, authorization, code_commit):
    """Adopt source selection after a proven zero-token table failure, same budget."""
    root=Path(root).resolve();code_commit=_commit(code_commit)
    if not isinstance(authorization,str) or not authorization.strip():raise ValueError('Explicit selection repair authorization required')
    with _lock(root):
        job=_read(root)
        if job.get('financial_selection_enabled') or job.get('final_review') or job.get('editorial_repair'):
            raise ValueError('Selection migration cannot reset an existing repair')
        if job['status']!='blocked' or job['stage']!='financial_tables' or not job['attempts']:
            raise ValueError('Selection migration requires blocked deterministic table calculation')
        attempt=job['attempts'][-1];outcome=attempt.get('outcome',{})
        if not attempt.get('replay_safe') or not attempt.get('usage_recorded') or outcome.get('tokens')!=0 or outcome.get('status')!='blocked':
            raise ValueError('Verified zero-token deterministic failure required')
        if sum(a['outcome']['tokens'] for a in job['attempts'] if a.get('usage_recorded'))!=job['tokens_used']:
            raise ValueError('Cumulative usage differs from attempt history')
        _verify(root,job['artifacts']);_verify(root,job.get('revision_input',{}))
        job.setdefault('administrative_history',[]).append(dict(action='enable_financial_selection',authorization=authorization,
            previous_code_commit=job.get('execution_code_commit'),code_commit=code_commit,tokens_used=job['tokens_used'],revision_round=job['revision_round']))
        job.update(financial_selection_enabled=True,execution_code_commit=code_commit,stage='financial_selection',status='ready')
        job.pop('reason',None);_write(root,job);return job


def adopt_financial_selection(root, authorization, code_commit, recover):
    """Revalidate a saved completed selection after a code fix, without paid replay."""
    root=Path(root).resolve();code_commit=_commit(code_commit)
    if not isinstance(authorization,str) or not authorization.strip() or not callable(recover):raise ValueError('Explicit verified recovery required')
    with _lock(root):
        job=_read(root)
        if job['status']!='blocked' or job['stage']!='financial_selection' or not job.get('financial_selection_enabled'):
            raise ValueError('Blocked selection required')
        attempt=job['attempts'][-1];outcome=attempt.get('outcome',{})
        if not attempt.get('usage_recorded') or outcome.get('execution_certainty')!='completed':raise ValueError('Completed accounted selection required')
        if sum(a['outcome']['tokens'] for a in job['attempts'] if a.get('usage_recorded'))!=job['tokens_used']:raise ValueError('Selection usage differs from history')
        _verify(root,job['artifacts']);_verify(root,job.get('revision_input',{}))
        result=recover(root,copy.deepcopy(job));name=f"financial-selection-r{job['revision_round']}.json"
        if set(result['outputs'])!={name} or result['tokens']!=outcome['tokens'] or not result.get('session_id') or not result.get('proof_outputs'):
            raise ValueError('Recovery must bind original usage, session and saved selection')
        _verify(root,result['outputs']);_verify(root,result['proof_outputs'])
        job['artifacts'].update(result['outputs']);job['artifacts'].update(result['proof_outputs'])
        job.setdefault('administrative_history',[]).append(dict(action='adopt_financial_selection',authorization=authorization,
            attempt_id=attempt['id'],session_id=result['session_id'],tokens_used=job['tokens_used'],additional_tokens=0,
            proof_outputs=result['proof_outputs'],previous_code_commit=job.get('execution_code_commit'),code_commit=code_commit))
        job.update(financial_selection_artifact=name,execution_code_commit=code_commit,stage='financial_tables',status='ready')
        job.pop('reason',None);_write(root,job);return job


def adopt_single_author(root, authorization, code_commit, recover):
    """Recompile a saved author under a fixed compiler; no new model or budget."""
    root=Path(root).resolve();code_commit=_commit(code_commit)
    if not isinstance(authorization,str) or not authorization.strip() or not callable(recover):raise ValueError('Explicit verified recovery required')
    with _lock(root):
        job=_read(root)
        if job['status']!='blocked' or job['stage']!='analysis' or not job.get('single_author_enabled'):raise ValueError('Blocked single author required')
        previous=job['attempts'][-1];outcome=previous.get('outcome',{})
        if not previous.get('usage_recorded') or outcome.get('execution_certainty')!='completed':raise ValueError('Completed accounted author required')
        if sum(a['outcome']['tokens'] for a in job['attempts'] if a.get('usage_recorded'))!=job['tokens_used']:raise ValueError('Author usage differs from history')
        _verify(root,job['artifacts']);_verify(root,job.get('revision_input',{}))
        result=recover(root,copy.deepcopy(job))
        required={'financial-selection-r0.json','financial-analysis.json','financial-configuration.json','financial-tables.md','analysis-r0.json',job['candidate_artifact']}
        if result.get('status')!='completed' or not required<=set(result['outputs']) or result['tokens']!=outcome['tokens'] or not result.get('session_id') or not result.get('proof_outputs'):raise ValueError('Recovery must bind original author, usage and compiled outputs')
        _verify(root,result['outputs']);_verify(root,result['proof_outputs'])
        job.setdefault('administrative_history',[]).append(dict(action='adopt_single_author',authorization=authorization,attempt_id=previous['id'],tokens_used=job['tokens_used'],additional_tokens=0,previous_code_commit=job.get('execution_code_commit'),code_commit=code_commit,proof_outputs=result['proof_outputs']))
        result={k:v for k,v in result.items() if k!='proof_outputs'}|{'tokens':0}
        job['artifacts'].update(job['administrative_history'][-1]['proof_outputs'])
        job['attempts'].append(dict(id=uuid.uuid4().hex,stage='analysis',revision_round=job['revision_round'],status='running',replay_safe=False,outcome=result,recovered_from=previous['id']))
        job.update(status='running',execution_code_commit=code_commit);job.pop('reason',None)
        _write(root,job)
        return _finish(root,job)


def repair_single_author(root, authorization, code_commit):
    """Adopt a closed narrative review into bounded repair, without replay or new budget.

    Explicit operator migration for earlier comparison jobs configured with no
    revisions. New jobs already permit the normal two-round correction loop.
    """
    root=Path(root).resolve();code_commit=_commit(code_commit)
    if not isinstance(authorization,str) or not authorization.strip():raise ValueError('Explicit repair authorization required')
    with _lock(root):
        job=_read(root)
        if job['status']!='blocked' or job['stage']!='review' or not job.get('single_author_enabled') or job.get('final_review') or job.get('editorial_repair'):
            raise ValueError('Closed single-author narrative review required')
        if job['revision_round']>=2 or job['tokens_used']>=job['budget_tokens']:raise ValueError('Repair allowance exhausted')
        _verify(root,job['artifacts']);_verify(root,job.get('revision_input',{}))
        attempt=job['attempts'][-1];outcome=attempt.get('outcome',{})
        name=f"review-r{job['revision_round']}.json"
        if (attempt['stage']!='review' or not attempt.get('usage_recorded') or outcome.get('status')!='revise'
            or outcome.get('execution_certainty')!='completed' or not outcome.get('session_id')
            or outcome.get('input_sha256')!=job['artifacts'].get(job['candidate_artifact'])
            or outcome.get('outputs',{}).get(name)!=job['artifacts'].get(name)):
            raise ValueError('Accounted exact-candidate review required')
        if sum(a.get('outcome',{}).get('tokens',0) for a in job['attempts'] if a.get('usage_recorded'))!=job['tokens_used']:
            raise ValueError('Cumulative review accounting changed')
        from . import earnings_sequential_stages as stages, earnings_compact_evidence as evidence
        decision=json.loads(_artifact(root,name).read_text())
        stages.validate_review(decision,set(evidence._scopes(evidence.load_bundle(root/'sources/manifest.json'))))
        if not decision['findings'] or any(f['location']=='financial_tables' for f in decision['findings']):raise ValueError('Narrative findings required')
        previous=copy.deepcopy(job)
        job['revision_round']+=1;job['max_revision_rounds']=2
        job['revision_input']={job['candidate_artifact']:job['artifacts'].pop(job['candidate_artifact'])}
        from . import earnings_sequential_revisions as revisions
        revisions.plan(root,job,stages.render_candidate)
        job.setdefault('administrative_history',[]).append(dict(action='repair_single_author',authorization=authorization,
            previous_code_commit=previous.get('execution_code_commit'),code_commit=code_commit,
            previous_max_revision_rounds=previous['max_revision_rounds'],max_revision_rounds=2,
            tokens_used=job['tokens_used'],budget_tokens=job['budget_tokens'],review_sha256=job['artifacts'][name]))
        job.update(execution_code_commit=code_commit,status='ready',stage='analysis',accepted_candidate_sha256=None)
        job.pop('reason',None);_write(root,job);return job
