#!/usr/bin/env python3
"""Project-local learning ledger helper.

The CLI intentionally stays small: append and inspect canonical database
events, export deterministic compressed artifacts, build compact seven-day
aggregates, import legacy ledgers, and prune derived artifacts.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_LEDGER_DIR = ".learning-ledger"
RAW_RETENTION_DAYS = 7
DAILY_RETENTION_DAYS = 35
AGGREGATE_KEEP = 4
MAX_COMPRESSED_BYTES = 1_000_000
KANBAN_SCRIPT = Path(__file__).resolve().parents[2] / "kanban" / "scripts" / "kanban.py"
KANBAN_SPEC = importlib.util.spec_from_file_location("agentic_delta_kanban", KANBAN_SCRIPT)
if KANBAN_SPEC is None or KANBAN_SPEC.loader is None:
    raise RuntimeError(f"Cannot load Kanban helper: {KANBAN_SCRIPT}")
KANBAN = importlib.util.module_from_spec(KANBAN_SPEC)
KANBAN_SPEC.loader.exec_module(KANBAN)

ROLES = {"user", "assistant", "worker"}
EVENT_TYPES = {
    "prompt", "response", "feedback", "decision", "checkpoint", "commit", "test",
    "authorization", "gate", "evidence", "retry", "cancellation", "side_effect",
    "exception",
}
TRACKS = {"execution", "reflection"}
FEEDBACK_TAGS = {"approve", "correct", "interrupt", "revert", "redirect", "praise"}
CHECKPOINT_TYPES = {"commit", "test", "plan", "release"}
LEAKAGE_RESULTS = {"not_applicable", "pass", "needs_review", "fail"}
OUTCOME_TAGS = {"accepted", "reworked", "reverted", "blocked", "deferred"}


def fail(message: str, code: int = 2) -> None:
    print(f"FAIL {message}", file=sys.stderr)
    raise SystemExit(code)


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def parse_ts(value: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    if len(raw) == 10:
        raw += "T00:00:00+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        fail(f"Invalid timestamp/date: {value}")
        raise AssertionError from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_query_bound(value: str, until: bool = False) -> datetime:
    if until and len(value.strip()) == 10:
        return parse_ts(value) + timedelta(days=1) - timedelta(microseconds=1)
    return parse_ts(value)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        fail(f"Invalid date: {value}")
        raise AssertionError from exc


def project_root(args: argparse.Namespace) -> Path:
    return Path(args.project).resolve()


def ledger_root(args: argparse.Namespace) -> Path:
    return project_root(args) / args.ledger_dir


def board_path(args: argparse.Namespace) -> Path:
    raw = Path(args.db)
    return raw.resolve() if raw.is_absolute() else project_root(args) / raw


def board_connection(args: argparse.Namespace):
    conn = KANBAN.connect(board_path(args))
    KANBAN.init_db(conn, KANBAN.DEFAULT_SCHEMA_PATH)
    return conn


def rel_to_project(project: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project).as_posix()
    except ValueError:
        return path.as_posix()


def compliance_for(storage_location: str) -> str:
    path = Path(storage_location)
    if path.is_absolute() or ".." in path.parts:
        return "fail"
    return "pass"


def json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def read_json_arg(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    if value == "-":
        text = sys.stdin.read()
    elif value.startswith("@"):
        text = Path(value[1:]).read_text(encoding="utf-8")
    else:
        text = value
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        fail(f"Invalid JSON: {exc}")
    if not isinstance(data, dict):
        fail("Event JSON must be an object")
    return data


def parse_field(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            fail(f"Expected KEY=VALUE for --field, got {item!r}")
        key, value = item.split("=", 1)
        if not key:
            fail("Field key cannot be empty")
        parsed[key] = value
    return parsed


def ensure_enum(event: dict[str, Any], key: str, allowed: set[str], required: bool = False) -> None:
    value = event.get(key)
    if value in (None, ""):
        if required:
            fail(f"Missing required field: {key}")
        return
    if value not in allowed:
        fail(f"Invalid {key}: {value!r}; expected one of {', '.join(sorted(allowed))}")


def event_day(event: dict[str, Any]) -> date:
    return parse_ts(str(event["ts_utc"])).date()


def raw_path(root: Path, day: date) -> Path:
    return root / "raw" / f"{day.isoformat()}.ndjson"


def daily_path(root: Path, day: date, compacted: bool = False) -> Path:
    suffix = "compacted.json.gz" if compacted else "ndjson.gz"
    return root / "daily" / f"{day.isoformat()}.{suffix}"


def aggregate_path(root: Path, end_day: date) -> Path:
    return root / "aggregates" / f"{end_day.isoformat()}_7d.json.gz"


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    opener = gzip.open if path.suffix == ".gz" else open
    mode = "rt" if path.suffix == ".gz" else "r"
    with opener(path, mode, encoding="utf-8") as handle:  # type: ignore[arg-type]
        for line_no, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                fail(f"{path}:{line_no}: invalid JSON: {exc}")
            if isinstance(item, dict) and item.get("artifact_type") == "daily_compacted":
                events.extend(item.get("sample_events", []))
            elif isinstance(item, dict):
                events.append(item)
    return events


def write_gzip_deterministic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            gz.write(content)
    tmp.replace(path)


def artifact_events(events: list[dict[str, Any]], storage_location: str) -> list[dict[str, Any]]:
    updated = []
    for event in events:
        copy = dict(event)
        copy["storage_scope"] = "project-local"
        copy["storage_location"] = storage_location
        copy["storage_compliance_result"] = compliance_for(storage_location)
        updated.append(copy)
    return updated


def compact_daily(
    events: list[dict[str, Any]], day: date, source: str, storage_location: str
) -> dict[str, Any]:
    by_type = Counter(str(event.get("event_type", "unknown")) for event in events)
    by_track = Counter(str(event.get("context_track", "unknown")) for event in events)
    samples = events[:50]
    return {
        "artifact_type": "daily_compacted",
        "date": day.isoformat(),
        "source_artifact": source,
        "storage_scope": "project-local",
        "storage_location": storage_location,
        "storage_compliance_result": compliance_for(storage_location),
        "event_count": len(events),
        "counts_by_event_type": dict(sorted(by_type.items())),
        "counts_by_context_track": dict(sorted(by_track.items())),
        "sample_events": artifact_events(samples, storage_location),
        "loss_accounting": {
            "preserved_signal": "event counts by type and track plus first 50 chronological events",
            "dropped_detail": "remaining raw event bodies after the deterministic sample window",
            "rationale": "compressed daily artifact exceeded the configured 1MB hard cap",
        },
    }


def write_bounded_daily(root: Path, day: date, events: list[dict[str, Any]], max_bytes: int) -> Path:
    target = daily_path(root, day)
    target_location = rel_to_project(root.parent, target)
    payload_events = artifact_events(events, target_location)
    payload = "".join(json_dump(event) + "\n" for event in payload_events).encode("utf-8")
    write_gzip_deterministic(target, payload)
    if target.stat().st_size <= max_bytes:
        return target
    target.unlink()
    compacted_target = daily_path(root, day, compacted=True)
    compacted_location = rel_to_project(root.parent, compacted_target)
    compacted = compact_daily(
        events, day, f"raw/{day.isoformat()}.ndjson", compacted_location
    )
    while True:
        payload = (json_dump(compacted) + "\n").encode("utf-8")
        write_gzip_deterministic(compacted_target, payload)
        if compacted_target.stat().st_size <= max_bytes or not compacted["sample_events"]:
            return compacted_target
        compacted["sample_events"] = compacted["sample_events"][: len(compacted["sample_events"]) // 2]
        compacted["loss_accounting"]["dropped_detail"] = (
            "raw event bodies beyond the reduced deterministic sample window"
        )


def build_event(args: argparse.Namespace) -> dict[str, Any]:
    event = read_json_arg(args.json)
    event.update(parse_field(args.field))
    for key in (
        "session_id",
        "turn_id",
        "role",
        "event_type",
        "text",
        "reason_summary",
        "context_track",
        "classification_basis",
        "feedback_tag",
        "checkpoint_type",
        "checkpoint_ref",
        "checkpoint_range",
        "delta_link_id",
        "leakage_audit_result",
        "outcome_tag",
        "lane_id",
    ):
        value = getattr(args, key, None)
        if value not in (None, ""):
            event[key] = value
    event.setdefault("ts_utc", iso_z(utc_now()))
    event["ts_utc"] = iso_z(parse_ts(str(event["ts_utc"])))
    event.setdefault("leakage_audit_result", "not_applicable")
    for key in ("session_id", "role", "event_type", "text", "reason_summary", "context_track"):
        if event.get(key) in (None, ""):
            fail(f"Missing required field: {key}")
    ensure_enum(event, "role", ROLES, required=True)
    ensure_enum(event, "event_type", EVENT_TYPES, required=True)
    ensure_enum(event, "context_track", TRACKS, required=True)
    ensure_enum(event, "feedback_tag", FEEDBACK_TAGS)
    ensure_enum(event, "checkpoint_type", CHECKPOINT_TYPES)
    ensure_enum(event, "leakage_audit_result", LEAKAGE_RESULTS)
    ensure_enum(event, "outcome_tag", OUTCOME_TAGS)
    if "turn_id" in event and event["turn_id"] not in (None, ""):
        try:
            event["turn_id"] = int(event["turn_id"])
        except (TypeError, ValueError):
            fail("turn_id must be an integer")
    return event


def cmd_append(args: argparse.Namespace) -> None:
    event = build_event(args)
    occurred_at = int(parse_ts(str(event["ts_utc"])).timestamp())
    payload = dict(event)
    conn = board_connection(args)
    try:
        KANBAN.learning_event_add(
            conn,
            str(event["event_type"]),
            str(event["reason_summary"]),
            str(event["context_track"]),
            event.get("outcome_tag"),
            json_dump(payload),
            str(event.get("redaction_state", "redacted")),
            event.get("intent_id"),
            event.get("task_id"),
            event.get("run_id"),
            event.get("decision_id"),
            event.get("gate_id"),
            event.get("evidence_id"),
            event.get("reference_id") or event.get("source_id"),
            str(event["attempt_id"]) if event.get("attempt_id") is not None else None,
            event.get("artifact_id") or event.get("artifact_ref"),
            event.get("commit_ref") or event.get("checkpoint_ref") if event.get("checkpoint_type") == "commit" else None,
            event.get("reviewer_id"),
            occurred_at,
        )
    finally:
        conn.close()


def candidate_event_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in ("raw/*.ndjson", "daily/*.ndjson.gz", "daily/*.compacted.json.gz"):
        files.extend(root.glob(pattern))
    return sorted(files)


def load_file_events(root: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in candidate_event_files(root):
        events.extend(iter_jsonl(path))
    events.sort(key=lambda event: str(event.get("ts_utc", "")))
    return events


def load_database_events(
    args: argparse.Namespace, since: int | None = None, until: int | None = None
) -> list[dict[str, Any]]:
    conn = board_connection(args)
    try:
        rows = KANBAN.query_learning_events(
            conn, None, None, None, None, since, until, None
        )
    finally:
        conn.close()
    events: list[dict[str, Any]] = []
    for row in rows:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        event = dict(payload)
        event.update({
            "event_id": row["id"],
            "ts_utc": iso_z(datetime.fromtimestamp(row["occurred_at"], UTC)),
            "event_type": row["event_type"],
            "context_track": row["context_track"],
            "reason_summary": row["reason_summary"],
            "outcome_tag": row.get("outcome"),
        })
        for key in ("intent_id", "task_id", "run_id", "decision_id", "gate_id",
                    "evidence_id", "reference_id", "attempt_id", "artifact_ref",
                    "commit_ref", "reviewer_id"):
            if row.get(key) is not None:
                event[key] = row[key]
        events.append(event)
    return events


def load_metric_snapshots(
    args: argparse.Namespace, since: int | None = None, until: int | None = None
) -> list[dict[str, Any]]:
    conn = board_connection(args)
    try:
        return KANBAN.query_metric_snapshots(conn, since=since, until=until)
    finally:
        conn.close()


def matches_query(event: dict[str, Any], args: argparse.Namespace) -> bool:
    ts = parse_ts(str(event.get("ts_utc", "1970-01-01T00:00:00Z")))
    if args.since and ts < parse_query_bound(args.since):
        return False
    if args.until and ts > parse_query_bound(args.until, until=True):
        return False
    if args.track and event.get("context_track") != args.track:
        return False
    if args.event_type and event.get("event_type") != args.event_type:
        return False
    if args.checkpoint_range and event.get("checkpoint_range") != args.checkpoint_range:
        return False
    return True


def cmd_list(args: argparse.Namespace) -> None:
    events = [event for event in load_database_events(args) if matches_query(event, args)]
    if args.limit:
        events = events[-args.limit :]
    if args.json:
        for event in events:
            print(json_dump(event))
        return
    for event in events:
        print(
            "\t".join(
                [
                    str(event.get("ts_utc", "")),
                    str(event.get("context_track", "")),
                    str(event.get("event_type", "")),
                    str(event.get("session_id", "")),
                    str(event.get("reason_summary", "")),
                ]
            )
        )


def days_to_rotate(args: argparse.Namespace) -> list[date]:
    if args.date:
        return [parse_day(args.date)]
    today = utc_now().date()
    if args.all:
        return sorted({parse_ts(str(event["ts_utc"])).date() for event in load_database_events(args)})
    return [today - timedelta(days=1)]


def record_archive(
    args: argparse.Namespace,
    path: Path,
    events: list[dict[str, Any]],
    preserved_signal: str,
    dropped_detail: str,
) -> None:
    event_ids = [int(event["event_id"]) for event in events if event.get("event_id") is not None]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    conn = board_connection(args)
    try:
        if KANBAN.learning_archive_hash_exists(conn, f"sha256:{digest}"):
            return
        KANBAN.learning_archive_add(
            conn,
            min(event_ids) if event_ids else None,
            max(event_ids) if event_ids else None,
            len(event_ids),
            rel_to_project(project_root(args), path),
            f"sha256:{digest}",
            "1",
            preserved_signal,
            dropped_detail,
        )
    finally:
        conn.close()


def cmd_rotate(args: argparse.Namespace) -> None:
    root = ledger_root(args)
    for day in days_to_rotate(args):
        start = int(datetime.combine(day, datetime.min.time(), tzinfo=UTC).timestamp())
        end = int(datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=UTC).timestamp()) - 1
        events = load_database_events(args, start, end)
        if not events:
            print(f"skip no database events for {day.isoformat()}")
            continue
        target = write_bounded_daily(root, day, events, args.max_bytes)
        record_archive(
            args, target, events,
            "database event counts and bounded chronological context",
            "detail omitted only when the compressed artifact exceeded its configured cap",
        )
        print(rel_to_project(project_root(args), target))


def summarize_chain(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    material = [
        event
        for event in events
        if event.get("event_type") in {"feedback", "decision", "checkpoint", "commit", "test"}
        or event.get("outcome_tag")
        or event.get("checkpoint_ref")
    ]
    chains = []
    for event in material[:100]:
        chains.append(
            {
                "ts_utc": event.get("ts_utc"),
                "event_type": event.get("event_type"),
                "context_track": event.get("context_track"),
                "reason_summary": event.get("reason_summary"),
                "checkpoint_ref": event.get("checkpoint_ref"),
                "checkpoint_range": event.get("checkpoint_range"),
                "outcome_tag": event.get("outcome_tag"),
                "delta_link_id": event.get("delta_link_id"),
            }
        )
    return chains


def aggregate_doc(
    root: Path,
    end_day: date,
    events: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    start_day = end_day - timedelta(days=6)
    by_type = Counter(str(event.get("event_type", "unknown")) for event in events)
    by_track = Counter(str(event.get("context_track", "unknown")) for event in events)
    daily_sources = []
    for offset in range(7):
        day = start_day + timedelta(days=offset)
        for path in (daily_path(root, day), daily_path(root, day, compacted=True), raw_path(root, day)):
            if path.exists():
                daily_sources.append(rel_to_project(root.parent, path))
                break
    return {
        "artifact_type": "learning_ledger_7_day_aggregate",
        "period_start": start_day.isoformat(),
        "period_end": end_day.isoformat(),
        "event_count": len(events),
        "storage_scope": "project-local",
        "storage_location": rel_to_project(root.parent, aggregate_path(root, end_day)),
        "storage_compliance_result": "pass",
        "source_artifacts": daily_sources,
        "high_level_summary": {
            "counts_by_event_type": dict(sorted(by_type.items())),
            "counts_by_context_track": dict(sorted(by_track.items())),
            "outcomes": dict(
                sorted(
                    Counter(
                        str(event.get("outcome_tag"))
                        for event in events
                        if event.get("outcome_tag") not in (None, "")
                    ).items()
                )
            ),
        },
        "context_dense_chains": summarize_chain(events),
        "track_summaries": {
            track: {
                "event_count": by_track.get(track, 0),
                "reason_summaries": [
                    event.get("reason_summary")
                    for event in events
                    if event.get("context_track") == track and event.get("reason_summary")
                ][:50],
            }
            for track in sorted(TRACKS)
        },
        "metric_trends": {
            name: [
                {
                    "measured_at": item["measured_at"],
                    "value": item["metric_value"],
                    "unit": item["unit"],
                    "derivation_version": item["derivation_version"],
                }
                for item in metrics if item["metric_name"] == name
            ]
            for name in sorted({item["metric_name"] for item in metrics})
        },
        "loss_accounting": None,
    }


def write_bounded_aggregate(root: Path, end_day: date, doc: dict[str, Any], max_bytes: int) -> Path:
    target = aggregate_path(root, end_day)
    while True:
        payload = (json_dump(doc) + "\n").encode("utf-8")
        write_gzip_deterministic(target, payload)
        if target.stat().st_size <= max_bytes:
            return target
        chains = doc["context_dense_chains"]
        summaries = doc["track_summaries"]
        if chains:
            doc["context_dense_chains"] = chains[: len(chains) // 2]
        else:
            for summary in summaries.values():
                summary["reason_summaries"] = summary["reason_summaries"][
                    : len(summary["reason_summaries"]) // 2
                ]
        doc["loss_accounting"] = {
            "preserved_signal": "counts, source links, and the earliest high-signal chains that fit",
            "dropped_detail": "overflow chain entries and reason summaries",
            "rationale": "compressed 7-day aggregate exceeded the configured 1MB hard cap",
        }
        if not doc["context_dense_chains"] and all(
            not summary["reason_summaries"] for summary in summaries.values()
        ):
            return target


def cmd_aggregate(args: argparse.Namespace) -> None:
    root = ledger_root(args)
    end_day = parse_day(args.end_date) if args.end_date else utc_now().date() - timedelta(days=1)
    start = datetime.combine(end_day - timedelta(days=6), datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(end_day + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    events = load_database_events(args, int(start.timestamp()), int(end.timestamp()) - 1)
    metrics = load_metric_snapshots(args, int(start.timestamp()), int(end.timestamp()) - 1)
    doc = aggregate_doc(root, end_day, events, metrics)
    target = write_bounded_aggregate(root, end_day, doc, args.max_bytes)
    record_archive(
        args, target, events,
        "seven-day counts, metric context, source links, and bounded high-signal chains",
        "overflow chains and summaries when required by the configured cap",
    )
    prune_aggregates(root, args.keep_aggregates)
    print(rel_to_project(project_root(args), target))


def prune_aggregates(root: Path, keep: int) -> list[Path]:
    removed: list[Path] = []
    aggregates = sorted((root / "aggregates").glob("*_7d.json.gz"), reverse=True)
    for path in aggregates[keep:]:
        path.unlink()
        removed.append(path)
    return removed


def cmd_prune(args: argparse.Namespace) -> None:
    root = ledger_root(args)
    today = utc_now().date()
    removed: list[Path] = []
    raw_cutoff = today - timedelta(days=args.raw_days)
    daily_cutoff = today - timedelta(days=args.daily_days)
    for path in sorted((root / "raw").glob("*.ndjson")):
        if parse_day(path.stem) < raw_cutoff:
            path.unlink()
            removed.append(path)
    for pattern in ("*.ndjson.gz", "*.compacted.json.gz"):
        for path in sorted((root / "daily").glob(pattern)):
            day_text = path.name.split(".", 1)[0]
            if parse_day(day_text) < daily_cutoff:
                path.unlink()
                removed.append(path)
    removed.extend(prune_aggregates(root, args.keep_aggregates))
    for path in removed:
        print(rel_to_project(project_root(args), path))


def cmd_import_legacy(args: argparse.Namespace) -> None:
    project = project_root(args)
    source = Path(args.source).resolve()
    try:
        relative = source.relative_to(project).as_posix()
    except ValueError:
        fail("Legacy source must be inside the active project")
    digest = f"sha256:{hashlib.sha256(source.read_bytes()).hexdigest()}"
    events = iter_jsonl(source)
    conn = board_connection(args)
    try:
        if KANBAN.learning_archive_hash_exists(conn, digest):
            print(f"skip already imported {relative}")
            return
        records = []
        for event in events:
            timestamp = int(parse_ts(str(event.get("ts_utc", iso_z(utc_now())))).timestamp())
            records.append({
                "occurred_at": timestamp,
                "event_type": str(event.get("event_type", "legacy.import")),
                "context_track": str(event.get("context_track", "execution")),
                "outcome": event.get("outcome_tag"),
                "reason_summary": str(event.get("reason_summary") or event.get("text") or "legacy event"),
                "payload_json": json_dump(event),
                "intent_id": event.get("intent_id"), "task_id": event.get("task_id"),
                "run_id": event.get("run_id"), "decision_id": event.get("decision_id"),
                "gate_id": event.get("gate_id"), "evidence_id": event.get("evidence_id"),
                "reference_id": event.get("reference_id") or event.get("source_id"),
                "attempt_id": str(event["attempt_id"]) if event.get("attempt_id") is not None else None,
                "artifact_ref": event.get("artifact_id") or event.get("artifact_ref"),
                "commit_ref": event.get("commit_ref"), "reviewer_id": event.get("reviewer_id"),
            })
        KANBAN.learning_event_import(conn, records, relative, digest)
    finally:
        conn.close()
    print(f"imported {len(events)} events from {relative}")


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", default=".", help="project root; defaults to current directory")
    parser.add_argument(
        "--db", default=".kanban/kanban.db",
        help="project-relative canonical Kanban database; default: .kanban/kanban.db",
    )
    parser.add_argument(
        "--ledger-dir",
        default=DEFAULT_LEDGER_DIR,
        help=f"project-relative ledger directory; default: {DEFAULT_LEDGER_DIR}",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project-local learning ledger helper")
    sub = parser.add_subparsers(dest="command", required=True)

    append = sub.add_parser("append", help="append one structured event to the canonical Kanban database")
    add_common(append)
    append.add_argument("--json", help="event JSON object, @file, or - for stdin")
    append.add_argument("--field", action="append", default=[], help="extra KEY=VALUE field")
    append.add_argument("--session-id")
    append.add_argument("--turn-id")
    append.add_argument("--role")
    append.add_argument("--event-type")
    append.add_argument("--text")
    append.add_argument("--reason-summary")
    append.add_argument("--context-track")
    append.add_argument("--classification-basis")
    append.add_argument("--feedback-tag")
    append.add_argument("--checkpoint-type")
    append.add_argument("--checkpoint-ref")
    append.add_argument("--checkpoint-range")
    append.add_argument("--delta-link-id")
    append.add_argument("--leakage-audit-result")
    append.add_argument("--outcome-tag")
    append.add_argument("--lane-id")
    append.set_defaults(func=cmd_append)

    list_cmd = sub.add_parser("list", help="query canonical database events by time, track, type, or checkpoint range")
    add_common(list_cmd)
    list_cmd.add_argument("--since", help="inclusive UTC timestamp or YYYY-MM-DD")
    list_cmd.add_argument("--until", help="inclusive UTC timestamp or YYYY-MM-DD")
    list_cmd.add_argument("--track", choices=sorted(TRACKS))
    list_cmd.add_argument("--event-type", choices=sorted(EVENT_TYPES))
    list_cmd.add_argument("--checkpoint-range")
    list_cmd.add_argument("--limit", type=int)
    list_cmd.add_argument("--json", action="store_true", help="emit JSONL")
    list_cmd.set_defaults(func=cmd_list)

    rotate = sub.add_parser("rotate", help="export database events into bounded daily artifacts")
    add_common(rotate)
    rotate.add_argument("--date", help="rotate a specific YYYY-MM-DD raw ledger")
    rotate.add_argument("--all", action="store_true", help="rotate all raw ledgers including today")
    rotate.add_argument("--keep-raw", action="store_true", help="deprecated compatibility flag; database events are always retained")
    rotate.add_argument("--max-bytes", type=int, default=MAX_COMPRESSED_BYTES)
    rotate.set_defaults(func=cmd_rotate)

    aggregate = sub.add_parser("aggregate", help="build a bounded compressed 7-day aggregate")
    add_common(aggregate)
    aggregate.add_argument("--end-date", help="aggregate period end date; default: yesterday UTC")
    aggregate.add_argument("--max-bytes", type=int, default=MAX_COMPRESSED_BYTES)
    aggregate.add_argument("--keep-aggregates", type=int, default=AGGREGATE_KEEP)
    aggregate.set_defaults(func=cmd_aggregate)

    prune = sub.add_parser("prune", help="apply raw, daily, and aggregate retention limits")
    add_common(prune)
    prune.add_argument("--raw-days", type=int, default=RAW_RETENTION_DAYS)
    prune.add_argument("--daily-days", type=int, default=DAILY_RETENTION_DAYS)
    prune.add_argument("--keep-aggregates", type=int, default=AGGREGATE_KEEP)
    prune.set_defaults(func=cmd_prune)

    migrate = sub.add_parser("import-legacy", help="import a project-local NDJSON or gzip ledger once")
    add_common(migrate)
    migrate.add_argument("source")
    migrate.set_defaults(func=cmd_import_legacy)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if Path(args.ledger_dir).is_absolute() or ".." in Path(args.ledger_dir).parts:
        fail("--ledger-dir must be project-relative")
    try:
        board_path(args).resolve().relative_to(project_root(args))
    except ValueError:
        fail("--db must resolve inside the active project")
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
