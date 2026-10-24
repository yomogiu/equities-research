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
        if not outputs:
            raise ValueError("completed stage requires durable output artifacts")
        if stage in ("analysis", "review"):
            session = outcome.get("session_id")
            if not isinstance(session, str) or not session:
                raise ValueError("analysis/review requires an attributable session_id")
            prior = [a.get("outcome", {}).get("session_id") for a in job["attempts"][:-1]
                     if a["stage"] in ("analysis", "review")]
            if session in prior:
                raise ValueError("analysis/review must use a fresh independent session")
        if stage == "analysis" and job["candidate_artifact"] not in outputs:
            raise ValueError("analysis did not produce the candidate artifact")
        if stage in ("review", "publication"):
            candidate = job["artifacts"].get(job["candidate_artifact"])
            if not candidate or outcome.get("input_sha256") != candidate:
                raise ValueError("outcome does not bind the exact candidate")
            if stage == "publication" and job["accepted_candidate_sha256"] != candidate:
                raise ValueError("publication candidate was not accepted")
        if status == "revise" and job["revision_round"] >= job["max_revision_rounds"]:
            raise ValueError("revision limit reached")
    except (ValueError, OSError) as exc:
        return _block(root, job, str(exc))
    attempt["status"] = status
    attempt["outputs"] = outputs
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
        if stage == "review":
            job["accepted_candidate_sha256"] = job["artifacts"][job["candidate_artifact"]]
        if stage == "publication":
            job["status"] = "completed"
        else:
            job.update(stage=STAGES[STAGES.index(stage) + 1], status="ready")
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
        except (ValueError, OSError) as exc:
            return _block(root, job, str(exc))
        if job["stage"] == "publication" and (not job["accepted_candidate_sha256"] or
                job["artifacts"].get(job["candidate_artifact"]) != job["accepted_candidate_sha256"]):
            return _block(root, job, "publication requires exact accepted candidate")
        if job["tokens_used"] >= job["budget_tokens"] and job["stage"] in ("analysis", "review"):
            return _block(root, job, "token budget exhausted")
        handler = handlers.get(job["stage"])
        if not callable(handler):
            return _block(root, job, "stage handler unavailable")
        replay_safe = getattr(handler, "replay_safe", False) is True
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
