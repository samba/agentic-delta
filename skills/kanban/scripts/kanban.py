#!/usr/bin/env python3
"""Small SQLite state kernel for the project Kanban workflow."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterator

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path.cwd().resolve()
KANBAN_DIR = ROOT / ".kanban"
DEFAULT_DB = KANBAN_DIR / "kanban.db"
DEFAULT_SCHEMA_PATH = SCRIPT_DIR / "schema.sql"
INTENT_STATES = ("captured", "researching", "refining", "planned", "deferred", "closed")
CHECK_TYPES = ("assurance", "control")
STATE_POLICY_COLUMNS = {
    "assurance_on_entry": "INTEGER NOT NULL DEFAULT 0",
    "worker_entry": "INTEGER NOT NULL DEFAULT 0",
    "review_queue": "INTEGER NOT NULL DEFAULT 0",
    "requires_checks": "INTEGER NOT NULL DEFAULT 0",
    "requires_evidence": "INTEGER NOT NULL DEFAULT 0",
    "requires_reviewed_references": "INTEGER NOT NULL DEFAULT 0",
}
CHECK_COLUMNS = {
    "reviewer_role_id": "TEXT REFERENCES specialist_roles(id) ON DELETE RESTRICT",
    "reviewer_worker_id": "TEXT",
}


def fail(message: str, code: int = 2) -> None:
    print(f"FAIL {message}", file=sys.stderr)
    raise SystemExit(code)


def now() -> int:
    return int(time.time())


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    return json.loads(value)


def json_object(value: str, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        fail(f"{label} must be valid JSON: {exc}")
    if not isinstance(parsed, dict):
        fail(f"{label} must be a JSON object")
    return parsed


def json_list(value: str, label: str) -> list[Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        fail(f"{label} must be valid JSON: {exc}")
    if not isinstance(parsed, list):
        fail(f"{label} must be a JSON list")
    return parsed


def connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextlib.contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def migrate_legacy_schema(conn: sqlite3.Connection, backup_path: Path | None) -> None:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "tasks" not in tables:
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
    if "state_id" in columns:
        return
    if backup_path is not None and not backup_path.exists():
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup = sqlite3.connect(backup_path)
        try:
            conn.backup(backup)
        finally:
            backup.close()
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
        conn.execute(f"DROP TRIGGER IF EXISTS {_quote_identifier(row[0])}")
    for name in sorted(tables):
        if name == "sqlite_sequence" or name.startswith("legacy__"):
            continue
        conn.execute(f"ALTER TABLE {_quote_identifier(name)} RENAME TO {_quote_identifier('legacy__' + name)}")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()


def migrate_legacy_rows(conn: sqlite3.Connection) -> None:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "legacy__intents" not in tables:
        return
    with transaction(conn):
        conn.execute("""INSERT OR IGNORE INTO intents(id, intent_type, summary, state, closure, details_json, created_at, updated_at)
            SELECT id, COALESCE(kind, 'problem'), summary, COALESCE(state, 'captured'), closure,
                   COALESCE(raw_json, '{}'), COALESCE(created_at, unixepoch()), COALESCE(updated_at, unixepoch())
            FROM legacy__intents""")
        conn.execute("""INSERT OR IGNORE INTO tasks(
            id, state_id, task_type, summary, owner, scope, goal, validation_status,
            acceptance_json, details_json, created_at, updated_at)
            SELECT t.id,
                   COALESCE((SELECT s.id FROM task_states s WHERE s.name=t.column_name), 'backlog'),
                   CASE WHEN json_extract(t.raw_json, '$.task_type') IS NOT NULL
                        THEN json_extract(t.raw_json, '$.task_type') ELSE 'work' END,
                   COALESCE(t.goal, t.id), COALESCE(t.owner, 'unassigned'), t.scope, t.goal,
                   COALESCE(t.validation_status, 'not_started'), '[]', COALESCE(t.raw_json, '{}'),
                   COALESCE(t.updated_at, unixepoch()), COALESCE(t.updated_at, unixepoch())
            FROM legacy__tasks t""")
        if "legacy__intent_work_links" in tables:
            conn.execute("INSERT OR IGNORE INTO task_intents(task_id, intent_id) SELECT task_id, intent_id FROM legacy__intent_work_links")
        if "legacy__task_dependencies" in tables:
            old_cols = {row[1] for row in conn.execute("PRAGMA table_info(legacy__task_dependencies)")}
            dependency = "dependency" if "dependency" in old_cols else "dependency_id"
            conn.execute(f"INSERT OR IGNORE INTO task_dependencies(task_id, dependency_id) SELECT task_id, {dependency} FROM legacy__task_dependencies")
        if "legacy__task_events" in tables:
            conn.execute("""INSERT INTO task_events(task_id, event_type, actor, summary, payload_json, created_at)
                SELECT task_id, event_type, 'legacy-migration', message, '{}', created_at
                FROM legacy__task_events WHERE task_id IS NOT NULL""")
        if "legacy__research_references" in tables:
            conn.execute("""INSERT OR IGNORE INTO research_references(
                id, url, title, publisher, reference_type, published_at, retrieved_at,
                topics_json, summary, relevance, constraints, provenance_json,
                content_hash, review_state, created_at, updated_at)
                SELECT id, url, title, publisher, reference_type, published_at, retrieved_at,
                COALESCE(topics_json, '[]'), summary, relevance, constraints,
                COALESCE(provenance_json, '{}'), content_hash, COALESCE(review_state, 'unreviewed'),
                COALESCE(created_at, unixepoch()), COALESCE(updated_at, unixepoch())
                FROM legacy__research_references""")
        for table, target, columns_sql in (
            ("legacy__reference_intents", "reference_intents", "reference_id, intent_id"),
            ("legacy__reference_tasks", "reference_tasks", "reference_id, task_id"),
        ):
            if table in tables:
                conn.execute(f"INSERT OR IGNORE INTO {target}({columns_sql}) SELECT {columns_sql} FROM {table}")
        if "legacy__pull_capacity_leases" in tables:
            conn.execute("""INSERT OR IGNORE INTO pull_capacity_leases(
                id, stage, lane, slots, eligibility_json, required_output, owner,
                idempotency_key, status, issued_at, expires_at, renewed_at, released_at,
                created_at, updated_at)
                SELECT id, stage, lane, slots, eligibility_json, required_output, owner,
                idempotency_key, status, issued_at, expires_at, renewed_at, released_at,
                created_at, updated_at FROM legacy__pull_capacity_leases""")
        if "legacy__specialist_classes" in tables:
            conn.execute("""INSERT OR IGNORE INTO specialist_roles(id, name, purpose, description, active, created_at, updated_at)
                SELECT id, title, role_context, description, active, COALESCE(created_at, unixepoch()), COALESCE(updated_at, unixepoch())
                FROM legacy__specialist_classes""")
        if "legacy__principles" in tables:
            conn.execute("""INSERT OR IGNORE INTO guidance(id, version, guidance_type, statement, status, effective_at)
                SELECT id, 1, 'principle', statement,
                CASE WHEN status='active' THEN 'active' ELSE 'retired' END,
                COALESCE(updated_at, unixepoch()) FROM legacy__principles""")
        for row in conn.execute("SELECT id FROM tasks WHERE state_id IN (SELECT id FROM task_states WHERE assurance_on_entry = 1)"):
            ensure_assurance_checks(conn, row[0])
    conn.execute("PRAGMA foreign_keys = OFF")
    for name in sorted({row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'legacy__%' AND name <> 'legacy__sqlite_sequence'")}):
        conn.execute(f"DROP TABLE IF EXISTS {_quote_identifier(name)}")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()


def migrate_dependency_cascade(conn: sqlite3.Connection) -> None:
    """Rebuild the edge table when an older schema retained dangling edges."""
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_dependencies'").fetchone() is None:
        return
    fk_rows = conn.execute("PRAGMA foreign_key_list(task_dependencies)").fetchall()
    dependency_fk = next((row for row in fk_rows if row[3] == "dependency_id"), None)
    if dependency_fk is not None and str(dependency_fk[6]).upper() == "CASCADE":
        return
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("ALTER TABLE task_dependencies RENAME TO legacy__task_dependencies_cascade")
        conn.execute("""CREATE TABLE task_dependencies (
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            dependency_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            PRIMARY KEY (task_id, dependency_id),
            CHECK (task_id <> dependency_id)
        )""")
        conn.execute("""INSERT INTO task_dependencies(task_id, dependency_id)
                       SELECT task_id, dependency_id FROM legacy__task_dependencies_cascade""")
        conn.execute("DROP TABLE legacy__task_dependencies_cascade")
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def init_db(conn: sqlite3.Connection, schema_path: Path = DEFAULT_SCHEMA_PATH, legacy_backup: Path | None = None) -> None:
    if not schema_path.is_file():
        fail(f"Missing schema: {schema_path}")
    migrate_legacy_schema(conn, legacy_backup)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(task_states)")}
    if existing:
        with transaction(conn):
            for column, definition in STATE_POLICY_COLUMNS.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE task_states ADD COLUMN {column} {definition}")
            check_columns = {row[1] for row in conn.execute("PRAGMA table_info(task_checks)")}
            for column, definition in CHECK_COLUMNS.items():
                if column not in check_columns:
                    conn.execute(f"ALTER TABLE task_checks ADD COLUMN {column} {definition}")
            for trigger in (
                "task_state_wip_guard", "task_insert_wip_guard",
                "task_assurance_roster_guard", "task_done_checks_guard",
                "task_done_evidence_guard", "task_check_delete_guard",
                "task_reviewed_references_guard",
            ):
                conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    with transaction(conn):
        conn.executescript(schema_path.read_text(encoding="utf-8"))
    migrate_dependency_cascade(conn)
    migrate_legacy_rows(conn)


def require_task(conn: sqlite3.Connection, task_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        fail(f"Unknown task: {task_id}")
    return row


def require_intent(conn: sqlite3.Connection, intent_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM intents WHERE id = ?", (intent_id,)).fetchone()
    if row is None:
        fail(f"Unknown intent: {intent_id}")
    return row


def state_id(conn: sqlite3.Connection, value: str) -> str:
    row = conn.execute(
        "SELECT id FROM task_states WHERE (id = ? OR name = ?) AND active = 1",
        (value, value),
    ).fetchone()
    if row is None:
        fail(f"Unknown task state: {value}")
    return str(row["id"])


def state_name(conn: sqlite3.Connection, value: str) -> str:
    row = conn.execute("SELECT name FROM task_states WHERE id = ?", (value,)).fetchone()
    return str(row["name"]) if row else value


def state_add(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    previous = conn.execute("SELECT next_state_id FROM task_states WHERE id=?", (args.previous,)).fetchone() if args.previous else None
    following = conn.execute("SELECT previous_state_id FROM task_states WHERE id=?", (args.next,)).fetchone() if args.next else None
    if args.previous and previous is None:
        fail(f"Unknown previous state: {args.previous}")
    if args.next and following is None:
        fail(f"Unknown next state: {args.next}")
    if previous and previous["next_state_id"] not in (None, args.next):
        fail(f"Previous state {args.previous} already has successor {previous['next_state_id']}")
    if following and following["previous_state_id"] not in (None, args.previous):
        fail(f"Next state {args.next} already has predecessor {following['previous_state_id']}")
    required = json_list(args.required_fields, "required-fields")
    with transaction(conn):
        conn.execute(
            """INSERT INTO task_states(id, name, previous_state_id, next_state_id, position,
               wip_limit, required_fields_json, assurance_on_entry, worker_entry,
               review_queue, requires_checks, requires_evidence, requires_reviewed_references, terminal)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (args.state_id, args.name, args.previous, args.next, args.position,
             args.wip_limit, dumps(required), int(args.assurance_on_entry),
             int(args.worker_entry), int(args.review_queue), int(args.requires_checks),
             int(args.requires_evidence), int(args.requires_reviewed_references), int(args.terminal)),
        )
        if args.previous:
            conn.execute(
                "UPDATE task_states SET next_state_id=? WHERE id=?",
                (args.state_id, args.previous),
            )
        if args.next:
            conn.execute(
                "UPDATE task_states SET previous_state_id=? WHERE id=?",
                (args.state_id, args.next),
            )


def state_list(conn: sqlite3.Connection) -> None:
    for row in conn.execute("""SELECT id, name, previous_state_id, next_state_id, wip_limit,
             assurance_on_entry, worker_entry, review_queue, requires_checks,
             requires_evidence, requires_reviewed_references, terminal
             FROM task_states WHERE active=1 ORDER BY position"""):
        print("\t".join(str(row[key] or "") for key in ("id", "name", "previous_state_id", "next_state_id", "wip_limit", "assurance_on_entry", "worker_entry", "review_queue", "requires_checks", "requires_evidence", "requires_reviewed_references", "terminal")))


def state_set(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    target = state_id(conn, args.state)
    if args.unlimited:
        wip_limit = None
    elif args.wip_limit is not None:
        if args.wip_limit <= 0:
            fail("WIP limit must be positive")
        wip_limit = args.wip_limit
    else:
        fail("state set requires --wip-limit or --unlimited")
    with transaction(conn):
        updated = conn.execute(
            "UPDATE task_states SET wip_limit=? WHERE id=? AND active=1",
            (wip_limit, target),
        )
        if updated.rowcount != 1:
            fail(f"Unknown task state: {args.state}")
    label = "unlimited" if wip_limit is None else str(wip_limit)
    print(f"set {state_name(conn, target)} WIP limit to {label}")


def record_event(
    conn: sqlite3.Connection,
    task_id: str,
    event_type: str,
    summary: str,
    actor: str = "coordinator",
    payload: Any = None,
    idempotency_key: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO task_events(task_id, event_type, actor, summary, payload_json,
           idempotency_key, created_at) VALUES(?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(task_id, idempotency_key) DO NOTHING""",
        (task_id, event_type, actor, summary, dumps(payload or {}), idempotency_key, now()),
    )


def task_event_add(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    require_task(conn, args.task_id)
    payload = json_object(args.payload, "payload")
    with transaction(conn):
        record_event(conn, args.task_id, args.event_type, args.summary,
                     args.actor, payload, args.idempotency_key)
    print(f"recorded event for {args.task_id}")


def task_event_list(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    require_task(conn, args.task_id)
    rows = [dict(row) for row in conn.execute(
        """SELECT id, task_id, event_type, actor, summary, payload_json,
                  idempotency_key, created_at
           FROM task_events WHERE task_id=? ORDER BY id DESC LIMIT ?""",
        (args.task_id, args.limit),
    )]
    for row in rows:
        row["payload"] = loads(row.pop("payload_json"), {})
    if args.as_json:
        print(json.dumps(rows, indent=2, sort_keys=True))
    else:
        for row in rows:
            print(f"{row['id']}\t{row['event_type']}\t{row['actor']}\t{row['summary']}")


def ensure_assurance_checks(conn: sqlite3.Connection, task_id: str) -> None:
    roles = conn.execute("SELECT id FROM specialist_roles WHERE active = 1 ORDER BY id").fetchall()
    for role in roles:
        role_id = str(role["id"])
        conn.execute(
            """INSERT OR IGNORE INTO task_checks(
                 id, task_id, check_type, criterion, specialist_role_id, required, created_at, updated_at
               ) VALUES(?, ?, 'assurance', 'baseline assurance participation', ?, 1, ?, ?)""",
            (f"{task_id}-assurance-{role_id}", task_id, role_id, now(), now()),
        )


def intent_add(conn: sqlite3.Connection, intent_id: str, intent_type: str, summary: str, details: dict[str, Any]) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", intent_id):
        fail("Intent id must contain lowercase letters, digits, and hyphens")
    if not intent_type.strip() or not summary.strip():
        fail("Intent type and summary are required")
    timestamp = now()
    with transaction(conn):
        conn.execute(
            "INSERT INTO intents(id, intent_type, summary, details_json, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?)",
            (intent_id, intent_type, summary, dumps(details), timestamp, timestamp),
        )
    print(f"created intent {intent_id}")


def intent_list(conn: sqlite3.Connection) -> None:
    for row in conn.execute("SELECT id, intent_type, state, summary FROM intents ORDER BY id"):
        print(f"{row['id']}\t{row['intent_type']}\t{row['state']}\t{row['summary']}")


def intent_show(conn: sqlite3.Connection, intent_id: str) -> None:
    row = require_intent(conn, intent_id)
    result = dict(row)
    result["details"] = loads(result.pop("details_json"), {})
    print(json.dumps(result, indent=2, sort_keys=True))


def intent_status(conn: sqlite3.Connection, intent_id: str, status: str, closure: str | None, reason: str | None) -> None:
    require_intent(conn, intent_id)
    if status not in INTENT_STATES:
        fail(f"Invalid intent state: {status}")
    if status == "closed" and closure not in ("realized", "rejected"):
        fail("Closed intents require realized or rejected closure")
    if status != "closed" and closure is not None:
        fail("Only closed intents may have a closure")
    if status == "closed" and closure == "realized":
        unfinished = conn.execute(
            """SELECT 1 FROM tasks t JOIN task_intents ti ON ti.task_id=t.id
               JOIN task_states s ON s.id=t.state_id
               WHERE ti.intent_id=? AND s.terminal = 0 LIMIT 1""", (intent_id,)
        ).fetchone()
        if unfinished:
            fail("Intent cannot be realized while linked tasks remain unfinished")
    with transaction(conn):
        conn.execute(
            "UPDATE intents SET state=?, closure=?, updated_at=? WHERE id=?",
            (status, closure, now(), intent_id),
        )
        if reason:
            conn.execute(
                "UPDATE intents SET details_json=json_set(details_json, '$.status_reason', ?) WHERE id=?",
                (reason, intent_id),
            )


def task_add(
    conn: sqlite3.Connection,
    task_id: str,
    summary: str,
    intent_ids: list[str],
    state: str,
    task_type: str,
    owner: str,
    scope: str | None,
    acceptance: list[str],
    validation: list[str],
    details: dict[str, Any],
) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", task_id):
        fail("Task id must contain lowercase letters, digits, and hyphens")
    if not intent_ids:
        fail("A task requires at least one intent")
    for intent_id in intent_ids:
        require_intent(conn, intent_id)
    target = state_id(conn, state)
    validate_task_requirements(conn, target, scope=scope, owner=owner, acceptance=acceptance, validation=validation, details=details)
    timestamp = now()
    with transaction(conn):
        conn.execute(
            """INSERT INTO tasks(
                 id, state_id, task_type, summary, owner, scope, acceptance_json,
                 validation_status, details_json, created_at, updated_at
               ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, target, task_type, summary, owner, scope, dumps(acceptance),
             "required" if validation else "not_started", dumps({**details, "validation": validation}),
             timestamp, timestamp),
        )
        for intent_id in intent_ids:
            conn.execute("INSERT INTO task_intents(task_id, intent_id) VALUES(?, ?)", (task_id, intent_id))
        if conn.execute("SELECT assurance_on_entry FROM task_states WHERE id=?", (target,)).fetchone()[0]:
            ensure_assurance_checks(conn, task_id)
        record_event(conn, task_id, "created", "Task created", payload={"state": state_name(conn, target)})
    print(f"created task {task_id}")


def task_list(conn: sqlite3.Connection, state: str | None, task_type: str | None) -> None:
    clauses, params = [], []
    if state:
        clauses.append("s.id = ? OR s.name = ?")
        params.extend((state, state))
    if task_type:
        clauses.append("t.task_type = ?")
        params.append(task_type)
    where = " WHERE " + " AND ".join(f"({c})" for c in clauses) if clauses else ""
    for row in conn.execute(
        f"SELECT t.id, s.name AS state, t.task_type, t.owner, t.summary FROM tasks t JOIN task_states s ON s.id=t.state_id{where} ORDER BY s.position, t.priority_rank, t.id",
        params,
    ):
        print(f"{row['state']}\t{row['id']}\t{row['task_type']}\t{row['owner']}\t{row['summary']}")


def task_show(conn: sqlite3.Connection, task_id: str) -> None:
    task = dict(require_task(conn, task_id))
    for key in ("acceptance_json", "review_contract_json", "details_json", "work_units_json"):
        task[key.removesuffix("_json")] = loads(task.pop(key), [] if key in ("acceptance_json", "work_units_json") else {})
    task["state"] = state_name(conn, task["state_id"])
    task["intents"] = [r[0] for r in conn.execute("SELECT intent_id FROM task_intents WHERE task_id=? ORDER BY intent_id", (task_id,))]
    task["checks"] = [dict(r) for r in conn.execute("SELECT * FROM task_checks WHERE task_id=? ORDER BY id", (task_id,))]
    task["guidance"] = []
    guidance_rows = conn.execute(
        """SELECT g.* FROM guidance g
           JOIN (
               SELECT id, MAX(version) AS version
               FROM guidance
               WHERE status='active' AND guidance_type IN ('principle', 'tenet')
               GROUP BY id
           ) current ON current.id=g.id AND current.version=g.version
           ORDER BY g.guidance_type, g.id"""
    ).fetchall()
    for row in guidance_rows:
        item = dict(row)
        item["references"] = [reference[0] for reference in conn.execute(
            """SELECT reference_id FROM guidance_references
               WHERE guidance_id=? AND guidance_version=? ORDER BY reference_id""",
            (row["id"], row["version"]),
        )]
        task["guidance"].append(item)
    print(json.dumps(task, indent=2, sort_keys=True))


def task_refine(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    task = require_task(conn, args.task_id)
    if all(value is None for value in (args.scope, args.owner, args.acceptance, args.validation, args.details)):
        fail("task refine requires --scope, --owner, --acceptance, --validation, or --details")
    current_acceptance = loads(task["acceptance_json"], [])
    current_details = loads(task["details_json"], {})
    scope = task["scope"] if args.scope is None else args.scope
    owner = task["owner"] if args.owner is None else args.owner
    if args.owner is not None and (not owner.strip() or owner == "unassigned"):
        fail("Task refinement requires a concrete owner")
    acceptance = current_acceptance if args.acceptance is None else args.acceptance
    details = dict(current_details)
    if args.validation is not None:
        details["validation"] = args.validation
    if args.details is not None:
        details.update(json_object(args.details, "details"))
    changed = []
    if scope != task["scope"]:
        changed.append("scope")
    if owner != task["owner"]:
        changed.append("owner")
    if acceptance != current_acceptance:
        changed.append("acceptance")
    if details != current_details:
        changed.append("details")
    if not changed:
        print(f"task {args.task_id} already refined")
        return
    with transaction(conn):
        conn.execute(
            "UPDATE tasks SET scope=?, owner=?, acceptance_json=?, details_json=?, updated_at=? WHERE id=?",
            (scope, owner, dumps(acceptance), dumps(details), now(), args.task_id),
        )
        record_event(
            conn, args.task_id, "task_refined",
            f"Task refinement updated {', '.join(changed)}", args.actor,
            {"changed": changed},
        )
    print(f"refined task {args.task_id}: {', '.join(changed)}")


def task_requeue(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    task = require_task(conn, args.task_id)
    current = conn.execute("SELECT * FROM task_states WHERE id=?", (task["state_id"],)).fetchone()
    target_id = state_id(conn, args.state) if args.state else current["previous_state_id"]
    if target_id is None:
        fail(f"Task {args.task_id} has no predecessor state to requeue into")
    target = conn.execute("SELECT * FROM task_states WHERE id=?", (target_id,)).fetchone()
    if target_id == task["state_id"]:
        fail(f"Task {args.task_id} is already in {target['name']}")
    with transaction(conn):
        validate_task_requirements(conn, target_id, task=task)
        if target["assurance_on_entry"]:
            ensure_assurance_checks(conn, args.task_id)
        changed = conn.execute(
            "UPDATE tasks SET state_id=?, updated_at=? WHERE id=? AND state_id=?",
            (target_id, now(), args.task_id, task["state_id"]),
        ).rowcount
        if changed != 1:
            fail(f"Task {args.task_id} changed concurrently; retry requeue")
        record_event(
            conn, args.task_id, "requeued",
            f"Requeued from {current['name']} to {target['name']}: {args.reason}",
            args.actor, {"from": current["name"], "to": target["name"], "reason": args.reason},
        )
    print(f"requeued task {args.task_id} to {target['name']}")


def task_purge(conn: sqlite3.Connection, task_id: str, confirm: bool) -> None:
    if not confirm:
        fail("Purging a task requires --confirm")
    task = require_task(conn, task_id)
    state = conn.execute("SELECT * FROM task_states WHERE id=?", (task["state_id"],)).fetchone()
    if not state["terminal"]:
        fail(f"Task {task_id} may only be purged from a terminal state")
    gaps = task_requirement_gaps(conn, task["state_id"], task=task)
    if state["requires_checks"]:
        pending = conn.execute(
            """SELECT 1 FROM task_checks
               WHERE task_id=? AND required=1
                 AND (status IN ('pending', 'failed')
                      OR (status='not_applicable' AND (rationale IS NULL OR trim(rationale)='')))
               LIMIT 1""",
            (task_id,),
        ).fetchone()
        if pending:
            gaps.append("accepted_checks")
    if state["requires_evidence"] and not conn.execute(
        "SELECT 1 FROM evidence WHERE task_id=? LIMIT 1", (task_id,)
    ).fetchone():
        gaps.append("evidence")
    if gaps:
        fail(f"Task {task_id} is not eligible for purge; missing: {', '.join(sorted(set(gaps)))}")
    with transaction(conn):
        deleted = conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        if deleted.rowcount != 1:
            fail(f"Unknown task: {task_id}")
    print(f"purged task {task_id} and cascading records")


def task_move(conn: sqlite3.Connection, task_id: str, target: str, actor: str) -> None:
    task = require_task(conn, task_id)
    target_id = state_id(conn, target)
    target_name = state_name(conn, target_id)
    with transaction(conn):
        validate_task_requirements(conn, target_id, task=task)
        if conn.execute("SELECT assurance_on_entry FROM task_states WHERE id=?", (target_id,)).fetchone()[0]:
            ensure_assurance_checks(conn, task_id)
        conn.execute("UPDATE tasks SET state_id=?, updated_at=? WHERE id=?", (target_id, now(), task_id))
        record_event(conn, task_id, "state_changed", f"Moved from {state_name(conn, task['state_id'])} to {target_name}", actor, {"from": state_name(conn, task["state_id"]), "to": target_name})
    print(f"moved task {task_id} to {target_name}")


def task_requirement_gaps(conn, target_id, task=None, *, scope=None, owner=None, acceptance=None, validation=None, details=None):
    state = conn.execute("SELECT name, required_fields_json, requires_reviewed_references FROM task_states WHERE id=?", (target_id,)).fetchone()
    if state is None:
        return ["unknown-state"]
    if task is not None:
        scope, owner = task["scope"], task["owner"]
        details = loads(task["details_json"], {})
        acceptance = loads(task["acceptance_json"], [])
        validation = details.get("validation", [])
        task_id = task["id"]
    else:
        task_id = "new task"
    details, acceptance, validation = details or {}, acceptance or [], validation or []
    missing = []
    for field in loads(state["required_fields_json"], []):
        if field == "scope" and not (scope or "").strip(): missing.append(field)
        elif field in ("owner", "worker") and (not (owner or "").strip() or (field == "worker" and owner == "unassigned")): missing.append(field)
        elif field == "acceptance" and not acceptance: missing.append(field)
        elif field == "validation" and not validation: missing.append(field)
        elif field == "plan" and not str(details.get("plan", "")).strip(): missing.append(field)
        elif field == "completion" and not str(details.get("completion", "")).strip(): missing.append(field)
        elif field == "evidence" and (task_id == "new task" or not conn.execute("SELECT 1 FROM evidence WHERE task_id=? LIMIT 1", (task_id,)).fetchone()): missing.append(field)
        elif field == "accepted_checks" and (task_id == "new task" or conn.execute("SELECT 1 FROM task_checks WHERE task_id=? AND required=1 AND status NOT IN ('passed','not_applicable') LIMIT 1", (task_id,)).fetchone()): missing.append(field)
    if state["requires_reviewed_references"] and task_id != "new task":
        unreviewed = conn.execute(
            """SELECT 1 FROM reference_tasks rt
               JOIN research_references r ON r.id=rt.reference_id
               WHERE rt.task_id=? AND r.review_state <> 'reviewed' LIMIT 1""",
            (task_id,),
        ).fetchone()
        if unreviewed or not conn.execute("SELECT 1 FROM reference_tasks WHERE task_id=? LIMIT 1", (task_id,)).fetchone():
            missing.append("reviewed_references")
    return sorted(set(missing))


def validate_task_requirements(conn, target_id, task=None, *, scope=None, owner=None, acceptance=None, validation=None, details=None):
    state = conn.execute("SELECT name FROM task_states WHERE id=?", (target_id,)).fetchone()
    missing = task_requirement_gaps(conn, target_id, task, scope=scope, owner=owner,
                                    acceptance=acceptance, validation=validation, details=details)
    if missing:
        task_id = task["id"] if task is not None else "new task"
        fail(f"Task {task_id} is not ready for {state['name']}; missing: {', '.join(missing)}")


def dependency_blockers(conn: sqlite3.Connection, task_id: str) -> list[dict[str, Any]]:
    return [{"task_id": row["id"], "state": row["state"]} for row in conn.execute(
        """SELECT dep.id, s.name AS state FROM task_dependencies d
           JOIN tasks dep ON dep.id=d.dependency_id JOIN task_states s ON s.id=dep.state_id
           WHERE d.task_id=? AND s.terminal=0 ORDER BY dep.id""", (task_id,))]


def lease_eligibility_gaps(task: sqlite3.Row, lease: sqlite3.Row) -> list[str]:
    eligibility = loads(lease["eligibility_json"], {})
    gaps = []
    for key in ("type", "task_type", "owner"):
        expected = eligibility.get(key)
        actual = task["task_type"] if key in ("type", "task_type") else task["owner"]
        if expected is not None and actual != expected:
            gaps.append(f"eligibility:{key}={expected}")
    return gaps


def pull_candidates(conn: sqlite3.Connection, lease: sqlite3.Row | None = None) -> list[dict[str, Any]]:
    target_id = state_id(conn, lease["stage"]) if lease is not None else None
    candidates = []
    for task in conn.execute("""SELECT t.*, s.name AS state_name, s.next_state_id
        FROM tasks t JOIN task_states s ON s.id=t.state_id
        ORDER BY COALESCE(t.priority_rank, 2147483647), t.created_at, t.id"""):
        target = conn.execute("SELECT * FROM task_states WHERE id=?", (target_id or task["next_state_id"],)).fetchone()
        blockers: list[str] = []
        if target is None:
            blockers.append("no-successor")
        else:
            review_claim = bool(target["review_queue"] and task["state_id"] == target["id"])
            if not target["worker_entry"] and not review_claim:
                blockers.append("successor-not-worker-entry")
            if not review_claim and target["previous_state_id"] != task["state_id"]:
                blockers.append("not-upstream-of-target")
            if review_claim:
                reserved = conn.execute(
                    """SELECT 1 FROM pull_capacity_reservations
                       WHERE task_id=? AND status='active'
                         AND (? IS NULL OR lease_id <> ?) LIMIT 1""",
                    (task["id"], lease["id"] if lease is not None else None, lease["id"] if lease is not None else None),
                ).fetchone()
                if reserved:
                    blockers.append("review-task-already-claimed")
            blockers.extend(f"requirement:{gap}" for gap in task_requirement_gaps(conn, target["id"], task=task))
        blockers.extend(f"dependency:{item['task_id']}:{item['state']}" for item in dependency_blockers(conn, task["id"]))
        if lease is not None:
            blockers.extend(lease_eligibility_gaps(task, lease))
        candidates.append({"id": task["id"], "summary": task["summary"], "task_type": task["task_type"],
                           "owner": task["owner"], "state": task["state_name"],
                           "target_state": target["name"] if target else None,
                           "eligible": not blockers, "blockers": blockers})
    return candidates


def claim_task_in_transaction(conn: sqlite3.Connection, task_id: str, actor: str, *, target_id: str | None = None, lease_id: str | None = None):
    task = conn.execute("""SELECT t.*, s.name AS state_name, s.next_state_id
        FROM tasks t JOIN task_states s ON s.id=t.state_id WHERE t.id=?""", (task_id,)).fetchone()
    if task is None:
        fail(f"Unknown task: {task_id}")
    current = conn.execute("SELECT * FROM task_states WHERE id=?", (task["state_id"],)).fetchone()
    target_id = target_id or (task["state_id"] if current["review_queue"] else task["next_state_id"])
    target = conn.execute("SELECT * FROM task_states WHERE id=?", (target_id,)).fetchone()
    review_claim = target is not None and target["review_queue"] and target["id"] == task["state_id"]
    if target is None or (not target["worker_entry"] and not review_claim):
        fail(f"Task {task_id} has no claimable successor from {task['state_name']}")
    if not review_claim and target["previous_state_id"] != task["state_id"]:
        fail(f"Task {task_id} is not immediately upstream of {target['name']}")
    if review_claim:
        if task["owner"] == actor:
            fail("Implementation owner cannot claim review")
        reserved = conn.execute(
            """SELECT 1 FROM pull_capacity_reservations
               WHERE task_id=? AND status='active'
                 AND (? IS NULL OR lease_id <> ?) LIMIT 1""",
            (task_id, lease_id, lease_id),
        ).fetchone()
        if reserved:
            fail(f"Review task {task_id} is already claimed")
        record_event(conn, task_id, "review_claimed", f"Review claimed by {actor}", actor,
                     {"state": task["state_name"], **({"lease_id": lease_id} if lease_id else {})})
        return {"id": task_id, "state": task["state_name"], "target_state": target["name"], "review_claim": True}
    validate_task_requirements(conn, target_id, task=task)
    if target["assurance_on_entry"]:
        ensure_assurance_checks(conn, task_id)
    changed = conn.execute("UPDATE tasks SET state_id=?, owner=?, updated_at=? WHERE id=? AND state_id=?", (target_id, actor, now(), task_id, task["state_id"])).rowcount
    if changed != 1:
        fail(f"Task {task_id} was claimed concurrently; retry pull")
    payload = {"from": task["state_name"], "to": target["name"]}
    if lease_id:
        payload["lease_id"] = lease_id
    record_event(conn, task_id, "claimed", f"Task claimed by {actor}", actor, payload)
    return {"id": task_id, "state": task["state_name"], "target_state": target["name"]}


def task_claim(conn, task_id, actor, announce=True):
    with transaction(conn):
        claim_task_in_transaction(conn, task_id, actor)
    if announce:
        print(f"claimed task {task_id}")


def task_assign(conn, task_id, owner, actor):
    require_task(conn, task_id)
    if not owner.strip() or owner == "unassigned":
        fail("Task assignment requires a concrete owner")
    with transaction(conn):
        updated = conn.execute(
            "UPDATE tasks SET owner=?, updated_at=? WHERE id=?",
            (owner, now(), task_id),
        )
        if updated.rowcount != 1:
            fail(f"Unknown task: {task_id}")
        record_event(conn, task_id, "assigned", f"Task assigned to {owner}", actor,
                     {"owner": owner})
    print(f"assigned task {task_id} to {owner}")


def pull_next(conn, args):
    with transaction(conn):
        lease = None
        if args.lease:
            lease_expire(conn)
            lease = conn.execute("SELECT * FROM pull_capacity_leases WHERE id=?", (args.lease,)).fetchone()
            if lease is None:
                fail(f"Unknown pull lease: {args.lease}")
            if lease["status"] != "active":
                fail("Only active pull leases may claim work")
        candidate = next((item for item in pull_candidates(conn, lease) if item["eligible"]), None)
        if candidate is None:
            result = {"task": None}
        else:
            if args.lease:
                timestamp = now()
                reservation_id = f"{args.lease}:{candidate['id']}"
                updated = conn.execute(
                    """UPDATE pull_capacity_leases SET updated_at=?
                       WHERE id=? AND status='active' AND expires_at>=?
                         AND slots >= 1 + COALESCE((SELECT SUM(slots) FROM pull_capacity_reservations
                                                   WHERE lease_id=? AND status='active'), 0)""",
                    (timestamp, args.lease, timestamp, args.lease),
                )
                if updated.rowcount != 1:
                    fail("Pull lease has insufficient unconsumed capacity")
                claim_task_in_transaction(conn, candidate["id"], args.actor,
                                          target_id=state_id(conn, lease["stage"]), lease_id=args.lease)
                conn.execute("""INSERT INTO pull_capacity_reservations(
                    id, lease_id, task_id, slots, reserved_at) VALUES(?, ?, ?, 1, ?)""",
                    (reservation_id, args.lease, candidate["id"], timestamp))
                candidate["reservation_id"] = reservation_id
            elif args.claim:
                claim_task_in_transaction(conn, candidate["id"], args.actor)
            candidate["claimed"] = bool(args.claim or args.lease)
            result = {"task": candidate}
    if result["task"] is None:
        print(json.dumps(result, sort_keys=True) if args.as_json else "no pullable task")
    elif args.as_json:
        print(json.dumps(result, sort_keys=True))
    elif not (args.claim or args.lease):
        print("\t".join(str(result["task"].get(k) or "") for k in ("id", "task_type", "owner", "summary")))


def task_dependency(conn: sqlite3.Connection, task_id: str, dependency_id: str, remove: bool) -> None:
    require_task(conn, task_id)
    require_task(conn, dependency_id)
    with transaction(conn):
        if remove:
            conn.execute("DELETE FROM task_dependencies WHERE task_id=? AND dependency_id=?", (task_id, dependency_id))
        else:
            cycle = conn.execute(
                """WITH RECURSIVE reachable(task_id) AS (
                       SELECT dependency_id FROM task_dependencies WHERE task_id=?
                       UNION
                       SELECT d.dependency_id FROM task_dependencies d
                       JOIN reachable r ON r.task_id=d.task_id
                   )
                   SELECT 1 FROM reachable WHERE task_id=? LIMIT 1""",
                (dependency_id, task_id),
            ).fetchone()
            if cycle:
                fail(f"Dependency would create a cycle: {task_id} depends on {dependency_id}")
            conn.execute("INSERT INTO task_dependencies(task_id, dependency_id) VALUES(?, ?)", (task_id, dependency_id))


def task_demand_set(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    require_task(conn, args.task_id)
    if not (1 <= args.min_workers <= args.target_workers <= args.max_workers):
        fail("Worker demand requires 1 <= min <= target <= max")
    units = json_list(args.work_units, "work-units")
    if len({json.dumps(unit, sort_keys=True) for unit in units}) != len(units):
        fail("Work units must be unique")
    if any(not isinstance(unit, (str, dict)) or (isinstance(unit, str) and not unit.strip()) for unit in units):
        fail("Work units must be non-empty strings or objects")
    if args.parallelism == "serial":
        if (args.min_workers, args.target_workers, args.max_workers) != (1, 1, 1):
            fail("Serial work requires exactly one worker")
        if units:
            fail("Serial work cannot declare parallel work units")
    elif len(units) < args.max_workers:
        fail("Parallel worker demand cannot exceed the number of work units")
    with transaction(conn):
        conn.execute(
            """UPDATE tasks SET parallelism=?, min_workers=?, target_workers=?, max_workers=?,
               work_units_json=?, reuse_policy=?, isolation=?, aggregation=?, updated_at=? WHERE id=?""",
            (args.parallelism, args.min_workers, args.target_workers, args.max_workers,
             dumps(units), args.reuse_policy, args.isolation, args.aggregation, now(), args.task_id),
        )
        record_event(conn, args.task_id, "demand_changed", "Task worker-demand contract changed", payload={
            "parallelism": args.parallelism, "min_workers": args.min_workers,
            "target_workers": args.target_workers, "max_workers": args.max_workers,
            "work_units": units, "reuse_policy": args.reuse_policy,
            "isolation": args.isolation, "aggregation": args.aggregation,
        })


def check_add(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    require_task(conn, args.task_id)
    if args.check_type not in CHECK_TYPES:
        fail("check-type must be assurance or control")
    if args.role and conn.execute("SELECT 1 FROM specialist_roles WHERE id=?", (args.role,)).fetchone() is None:
        fail(f"Unknown specialist role: {args.role}")
    with transaction(conn):
        conn.execute(
            """INSERT INTO task_checks(id, task_id, check_type, criterion, specialist_role_id,
               required, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
            (args.check_id, args.task_id, args.check_type, args.criterion, args.role, int(not args.optional), now(), now()),
        )


def check_record(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    require_task(conn, args.task_id)
    if args.status not in ("passed", "failed", "not_applicable"):
        fail("Invalid check result")
    if args.status == "not_applicable" and not args.rationale:
        fail("not-applicable checks require a rationale")
    check = conn.execute("SELECT * FROM task_checks WHERE id=? AND task_id=?", (args.check_id, args.task_id)).fetchone()
    if check is None:
        fail(f"Unknown task check: {args.check_id}")
    reviewer_worker_id = (getattr(args, "reviewer_worker_id", None) or args.reviewer or "").strip()
    reviewer_role_id = (getattr(args, "reviewer_role", None) or check["specialist_role_id"] or "").strip()
    check_columns = {row[1] for row in conn.execute("PRAGMA table_info(task_checks)")}
    if "reviewer_worker_id" not in check_columns or "reviewer_role_id" not in check_columns:
        with transaction(conn):
            cursor = conn.execute(
                """UPDATE task_checks SET status=?, reviewer=?, finding=?, rationale=?, updated_at=?
                   WHERE id=? AND task_id=?""",
                (args.status, args.reviewer, args.finding, args.rationale, now(), args.check_id, args.task_id),
            )
            if cursor.rowcount != 1:
                fail(f"Unknown task check: {args.check_id}")
            record_event(conn, args.task_id, "check_recorded", f"Recorded {args.status} for {args.check_id}", args.reviewer or "reviewer", {"check_id": args.check_id, "status": args.status})
        return
    if not reviewer_worker_id:
        fail("Recorded checks require --reviewer-worker-id")
    if not reviewer_role_id:
        fail("Recorded checks require --reviewer-role")
    if conn.execute("SELECT 1 FROM specialist_roles WHERE id=? AND active=1", (reviewer_role_id,)).fetchone() is None:
        fail(f"Reviewer specialist role is unknown or inactive: {reviewer_role_id}")
    if check["specialist_role_id"] and reviewer_role_id != check["specialist_role_id"]:
        fail("Reviewer role must match the specialist role assigned to the check")
    task = require_task(conn, args.task_id)
    if (task["owner"] or "").strip() == reviewer_worker_id:
        fail("Implementation owner cannot perform assurance or control review")
    with transaction(conn):
        cursor = conn.execute(
            """UPDATE task_checks SET status=?, reviewer=?, reviewer_role_id=?, reviewer_worker_id=?,
               finding=?, rationale=?, updated_at=?
               WHERE id=? AND task_id=?""",
            (args.status, reviewer_worker_id, reviewer_role_id, reviewer_worker_id,
             args.finding, args.rationale, now(), args.check_id, args.task_id),
        )
        record_event(conn, args.task_id, "check_recorded", f"Recorded {args.status} for {args.check_id}", reviewer_worker_id, {"check_id": args.check_id, "status": args.status, "reviewer_role_id": reviewer_role_id})


def evidence_add(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    require_task(conn, args.task_id)
    if args.check_id and conn.execute(
        "SELECT 1 FROM task_checks WHERE id=? AND task_id=?", (args.check_id, args.task_id)
    ).fetchone() is None:
        fail(f"Unknown check {args.check_id} for task {args.task_id}")
    if args.revision:
        try:
            verified = subprocess.run(
                ["git", "rev-parse", "--verify", f"{args.revision}^{{commit}}"],
                cwd=ROOT, capture_output=True, text=True, check=False, timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            fail(f"Unable to verify revision {args.revision}: {exc}")
        if verified.returncode != 0:
            fail(f"Evidence revision is not a Git commit: {args.revision}")
    artifact_path = None
    if args.location:
        artifact_path = (ROOT / args.location).resolve() if not Path(args.location).is_absolute() else Path(args.location).resolve()
        if not artifact_path.is_file():
            fail(f"Evidence artifact location is not a file: {args.location}")
    if args.content_hash:
        if artifact_path is None:
            fail("Evidence content hash requires --location")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", args.content_hash):
            fail("Evidence content hash must be a SHA-256 hex digest")
        observed_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if observed_hash.lower() != args.content_hash.lower():
            fail(f"Evidence content hash does not match {args.location}")
    with transaction(conn):
        conn.execute(
            """INSERT INTO evidence(id, task_id, check_id, artifact, revision, probe, result,
               producer, location, content_hash, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (args.evidence_id, args.task_id, args.check_id, args.artifact, args.revision, args.probe,
             args.result, args.producer, args.location, args.content_hash, now()),
        )


def _evidence_rows(conn: sqlite3.Connection, args: argparse.Namespace) -> list[dict[str, Any]]:
    require_task(conn, args.task_id)
    filters = ["e.task_id=?"]
    values: list[Any] = [args.task_id]
    if args.check_id:
        if conn.execute("SELECT 1 FROM task_checks WHERE id=? AND task_id=?", (args.check_id, args.task_id)).fetchone() is None:
            fail(f"Unknown check {args.check_id} for task {args.task_id}")
        filters.append("e.check_id=?")
        values.append(args.check_id)
    for name in ("revision", "producer", "result", "artifact"):
        value = getattr(args, name, None)
        if value is not None:
            if not value.strip():
                fail(f"Evidence filter --{name.replace('_', '-')} cannot be empty")
            filters.append(f"e.{name}=?")
            values.append(value)
    criterion = getattr(args, "criterion", None)
    if criterion is not None:
        if not criterion.strip():
            fail("Evidence filter --criterion cannot be empty")
        filters.append("c.criterion=?")
        values.append(criterion)
    return [dict(row) for row in conn.execute(
        """SELECT e.* FROM evidence e LEFT JOIN task_checks c ON c.id=e.check_id
           WHERE """ + " AND ".join(filters) + " ORDER BY e.created_at, e.id" , values
    )]


def evidence_list(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    rows = _evidence_rows(conn, args)
    if args.as_json:
        print(json.dumps(rows, indent=2, sort_keys=True))
    else:
        for row in rows:
            print("\t".join(str(row[key] or "") for key in ("id", "check_id", "artifact", "result", "producer", "revision", "probe", "location")))


def evidence_show(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    row = conn.execute("SELECT * FROM evidence WHERE id=?", (args.evidence_id,)).fetchone()
    if row is None:
        fail(f"Unknown evidence: {args.evidence_id}")
    result = dict(row)
    if args.as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("\t".join(str(result[key] or "") for key in ("id", "task_id", "check_id", "artifact", "result", "producer", "revision", "probe", "location")))


def role_add(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    with transaction(conn):
        conn.execute(
            "INSERT INTO specialist_roles(id, name, purpose, description, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?)",
            (args.role_id, args.name, args.purpose, args.description, now(), now()),
        )


def role_set_active(conn: sqlite3.Connection, args: argparse.Namespace, active: bool) -> None:
    with transaction(conn):
        cursor = conn.execute(
            "UPDATE specialist_roles SET active=?, updated_at=? WHERE id=?",
            (int(active), now(), args.role_id),
        )
        if cursor.rowcount != 1:
            fail(f"Unknown specialist role: {args.role_id}")


def role_list(conn: sqlite3.Connection) -> None:
    for row in conn.execute("SELECT id, name, active FROM specialist_roles ORDER BY id"):
        print(f"{row['id']}\t{row['active']}\t{row['name']}")


def guidance_add(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    with transaction(conn):
        conn.execute(
            """INSERT INTO guidance(id, version, guidance_type, statement, intended_outcome,
               rationale, verification_method, authority, status, effective_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (args.guidance_id, args.version, args.guidance_type, args.statement, args.outcome,
             args.rationale, args.verification, args.authority, args.status, now()),
        )


def guidance_reference(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    with transaction(conn):
        conn.execute(
            "INSERT INTO guidance_references(guidance_id, guidance_version, reference_id, relationship) VALUES(?, ?, ?, ?)",
            (args.guidance_id, args.version, args.reference_id, args.relationship),
        )


def reference_add(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    with transaction(conn):
        conn.execute(
            """INSERT INTO research_references(id, url, title, publisher, reference_type,
               summary, relevance, constraints, content_hash, retrieved_at, created_at, updated_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (args.reference_id, args.url, args.title, args.publisher, args.reference_type,
             args.summary, args.relevance, args.constraints, args.content_hash, now(), now(), now()),
        )


def reference_link(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    with transaction(conn):
        if args.intent_id:
            require_intent(conn, args.intent_id)
            conn.execute("INSERT INTO reference_intents(reference_id, intent_id) VALUES(?, ?)", (args.reference_id, args.intent_id))
        if args.task_id:
            require_task(conn, args.task_id)
            conn.execute("INSERT INTO reference_tasks(reference_id, task_id) VALUES(?, ?)", (args.reference_id, args.task_id))


def reference_review(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    if args.review_state not in ("unreviewed", "reviewed", "rejected"):
        fail("Review state must be unreviewed, reviewed, or rejected")
    with transaction(conn):
        updated = conn.execute(
            "UPDATE research_references SET review_state=?, updated_at=? WHERE id=?",
            (args.review_state, now(), args.reference_id),
        )
        if updated.rowcount != 1:
            fail(f"Unknown research reference: {args.reference_id}")
    print(f"reference {args.reference_id} marked {args.review_state}")


def reference_list(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    values: list[Any] = []
    filters = []
    if args.review_state:
        filters.append("review_state=?")
        values.append(args.review_state)
    rows = [dict(row) for row in conn.execute(
        "SELECT * FROM research_references" + (" WHERE " + " AND ".join(filters) if filters else "") + " ORDER BY id",
        values,
    )]
    for row in rows:
        row["topics"] = loads(row.pop("topics_json"), [])
        row["provenance"] = loads(row.pop("provenance_json"), {})
    if args.as_json:
        print(json.dumps(rows, indent=2, sort_keys=True))
    else:
        for row in rows:
            print(f"{row['id']}\t{row['review_state']}\t{row['url']}\t{row.get('title') or ''}")


def reference_update(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    fields = {
        "url": args.url,
        "title": args.title,
        "publisher": args.publisher,
        "reference_type": args.reference_type,
        "summary": args.summary,
        "relevance": args.relevance,
        "constraints": args.constraints,
        "content_hash": args.content_hash,
    }
    if args.provenance is not None:
        fields["provenance_json"] = json.dumps(json_object(args.provenance, "provenance"), sort_keys=True)
    fields = {key: value for key, value in fields.items() if value is not None}
    if not fields:
        fail("Reference update requires at least one field")
    if conn.execute("SELECT 1 FROM research_references WHERE id=?", (args.reference_id,)).fetchone() is None:
        fail(f"Unknown research reference: {args.reference_id}")
    fields["updated_at"] = now()
    assignments = ", ".join(f"{key}=?" for key in fields)
    with transaction(conn):
        conn.execute(
            f"UPDATE research_references SET {assignments} WHERE id=?",
            (*fields.values(), args.reference_id),
        )
    print(f"updated reference {args.reference_id}")


def lease_expire(conn: sqlite3.Connection) -> None:
    timestamp = now()
    conn.execute("UPDATE pull_capacity_leases SET status='expired', updated_at=? WHERE status='active' AND expires_at < ?", (timestamp, timestamp))
    conn.execute(
        """UPDATE pull_capacity_reservations SET status='released', released_at=?
           WHERE status='active' AND lease_id IN (
             SELECT id FROM pull_capacity_leases WHERE status='expired'
           )""",
        (timestamp,),
    )


def lease_issue(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    eligibility = json_object(args.eligibility, "eligibility")
    timestamp = now()
    with transaction(conn):
        lease_expire(conn)
        existing = conn.execute("SELECT * FROM pull_capacity_leases WHERE idempotency_key=?", (args.idempotency_key,)).fetchone()
        if existing:
            if existing["id"] != args.lease_id:
                fail("Idempotency key already belongs to another lease")
            return
        conn.execute(
            """INSERT INTO pull_capacity_leases(id, stage, lane, slots, eligibility_json,
               required_output, owner, idempotency_key, issued_at, expires_at, created_at, updated_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (args.lease_id, args.stage, args.lane, args.slots, dumps(eligibility), args.required_output,
             args.owner, args.idempotency_key, timestamp, timestamp + args.ttl_seconds, timestamp, timestamp),
        )


def lease_update(conn: sqlite3.Connection, args: argparse.Namespace, action: str) -> None:
    with transaction(conn):
        lease_expire(conn)
        row = conn.execute("SELECT status FROM pull_capacity_leases WHERE id=?", (args.lease_id,)).fetchone()
        if row is None:
            fail(f"Unknown pull lease: {args.lease_id}")
        if action == "renew":
            if row["status"] != "active":
                fail("Only active leases may be renewed")
            conn.execute("UPDATE pull_capacity_leases SET expires_at=?, renewed_at=?, updated_at=? WHERE id=?", (now() + args.ttl_seconds, now(), now(), args.lease_id))
        else:
            conn.execute("UPDATE pull_capacity_leases SET status='released', released_at=?, updated_at=? WHERE id=?", (now(), now(), args.lease_id))
            conn.execute("UPDATE pull_capacity_reservations SET status='released', released_at=? WHERE lease_id=? AND status='active'", (now(), args.lease_id))


def lease_reserve(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Atomically bind one lease slot to the task selected for that pull."""
    task = require_task(conn, args.task_id)
    timestamp = now()
    with transaction(conn):
        lease_expire(conn)
        lease = conn.execute("SELECT * FROM pull_capacity_leases WHERE id=?", (args.lease_id,)).fetchone()
        if lease is None:
            fail(f"Unknown pull lease: {args.lease_id}")
        if lease["status"] != "active":
            fail("Only active pull leases may reserve capacity")
        target_id = state_id(conn, lease["stage"])
        target = conn.execute("SELECT * FROM task_states WHERE id=?", (target_id,)).fetchone()
        if not target["previous_state_id"]:
            fail(f"Pull stage {lease['stage']} has no upstream state")
        if task["state_id"] != target["previous_state_id"]:
            fail(f"Task must be in {state_name(conn, target['previous_state_id'])} before pulling into {lease['stage']}")
        eligibility = loads(lease["eligibility_json"], {})
        for key in ("type", "task_type", "owner"):
            expected = eligibility.get(key)
            if expected is not None and task["task_type" if key in ("type", "task_type") else "owner"] != expected:
                fail(f"Task does not satisfy pull eligibility: {key}={expected}")
        existing = conn.execute(
            "SELECT id FROM pull_capacity_reservations WHERE lease_id=? AND task_id=? AND status='active'",
            (args.lease_id, args.task_id),
        ).fetchone()
        if existing:
            print(existing["id"])
            return
        reservation_id = f"{args.lease_id}:{args.task_id}"
        updated = conn.execute(
            """UPDATE pull_capacity_leases SET updated_at=?
               WHERE id=? AND status='active' AND expires_at>=?
                 AND slots >= ? + COALESCE((
                   SELECT SUM(slots) FROM pull_capacity_reservations
                   WHERE lease_id=? AND status='active'
                 ), 0)""",
            (timestamp, args.lease_id, timestamp, args.slots, args.lease_id),
        )
        if updated.rowcount != 1:
            fail("Pull lease has insufficient unconsumed capacity")
        conn.execute(
            """INSERT INTO pull_capacity_reservations(
               id, lease_id, task_id, slots, reserved_at)
               VALUES(?, ?, ?, ?, ?)""",
            (reservation_id, args.lease_id, args.task_id, args.slots, timestamp),
        )
        print(reservation_id)


def lease_release_reservation(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    with transaction(conn):
        updated = conn.execute(
            """UPDATE pull_capacity_reservations SET status='released', released_at=?
               WHERE lease_id=? AND task_id=? AND status='active'""",
            (now(), args.lease_id, args.task_id),
        )
        if updated.rowcount != 1:
            fail("No active reservation exists for that lease and task")


def status(conn: sqlite3.Connection, as_json: bool) -> None:
    with transaction(conn):
        lease_expire(conn)
    rows = []
    for row in conn.execute("""SELECT s.id, s.name AS state, s.previous_state_id,
             p.name AS previous_state, s.next_state_id, n.name AS next_state,
             s.wip_limit, s.assurance_on_entry, s.worker_entry, s.review_queue,
             s.requires_checks, s.requires_evidence, s.terminal, COUNT(t.id) AS count
        FROM task_states s
        LEFT JOIN task_states p ON p.id=s.previous_state_id
        LEFT JOIN task_states n ON n.id=s.next_state_id
        LEFT JOIN tasks t ON t.state_id=s.id
        GROUP BY s.id ORDER BY s.position"""):
        item = dict(row)
        item["available"] = None if item["wip_limit"] is None else max(item["wip_limit"] - item["count"], 0)
        item["full"] = item["wip_limit"] is not None and item["count"] >= item["wip_limit"]
        item["overage"] = None if item["wip_limit"] is None else max(item["count"] - item["wip_limit"], 0)
        rows.append(item)
    active_leases = []
    for row in conn.execute("""SELECT l.id, l.stage, l.lane, l.slots, l.expires_at,
             COALESCE(SUM(CASE WHEN r.status='active' THEN r.slots ELSE 0 END), 0) AS reserved_slots
             FROM pull_capacity_leases l
             LEFT JOIN pull_capacity_reservations r ON r.lease_id=l.id
             WHERE l.status='active' GROUP BY l.id ORDER BY l.stage, l.id"""):
        item = dict(row)
        item["available_slots"] = max(item["slots"] - item["reserved_slots"], 0)
        lease = conn.execute("SELECT * FROM pull_capacity_leases WHERE id=?", (item["id"],)).fetchone()
        item["next_pull"] = next((candidate for candidate in pull_candidates(conn, lease) if candidate["eligible"]), None)
        active_leases.append(item)
    backpressure = [
        {"state": row["state"], "upstream": row["previous_state"], "reason": "downstream-wip-full"}
        for row in rows if row["full"] and row["previous_state"]
    ]
    worker_entry_ids = {row["id"] for row in rows if row["worker_entry"]}
    board_walk = [
        row for row in rows
        if not row["terminal"]
        and row["state"].lower() != "backlog"
        and (
            row["worker_entry"]
            or row["review_queue"]
            or row["next_state_id"] in worker_entry_ids
        )
    ]
    review = [row for row in rows if row["review_queue"]]
    review_pressure = None
    if review:
        pending = conn.execute("""SELECT COUNT(*) FROM task_checks c JOIN tasks t ON t.id=c.task_id
            WHERE t.state_id IN (SELECT id FROM task_states WHERE review_queue=1) AND c.required=1 AND c.status='pending'""").fetchone()[0]
        failed = conn.execute("""SELECT COUNT(*) FROM task_checks c JOIN tasks t ON t.id=c.task_id
            WHERE t.state_id IN (SELECT id FROM task_states WHERE review_queue=1) AND c.required=1 AND c.status='failed'""").fetchone()[0]
        oldest = conn.execute("""SELECT MIN(created_at) FROM tasks
            WHERE state_id IN (SELECT id FROM task_states WHERE review_queue=1)""").fetchone()[0]
        review_pressure = {"occupancy": sum(row["count"] for row in review),
                           "wip_limit": sum(row["wip_limit"] or 0 for row in review) or None,
                           "full": any(row["full"] for row in review), "states": [row["state"] for row in review],
                           "pending_required_checks": pending,
                           "failed_required_checks": failed,
                           "oldest_age_seconds": None if oldest is None else max(now() - oldest, 0)}
    candidates = pull_candidates(conn)
    payload = {
        "states": rows,
        "active_leases": active_leases,
        "candidates": candidates,
        "backpressure": backpressure,
        "board_walk": board_walk,
        "review_pressure": review_pressure,
        "tasks": [dict(r) for r in conn.execute("SELECT t.id, s.name AS state, t.task_type, t.owner, t.summary FROM tasks t JOIN task_states s ON s.id=t.state_id ORDER BY s.position, t.id")],
    }
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    for row in rows:
        print(f"{row['state']} ({row['count']})")
    for row in payload["tasks"]:
        print(f"- {row['id']} | {row['state']} | {row['task_type']} | {row['summary']}")


def validate(conn: sqlite3.Connection) -> None:
    errors: list[str] = []
    if conn.execute("PRAGMA foreign_key_check").fetchall():
        errors.append("foreign-key violations")
    for row in conn.execute("SELECT id, previous_state_id, next_state_id FROM task_states WHERE active=1"):
        if row["previous_state_id"]:
            predecessor = conn.execute("SELECT next_state_id FROM task_states WHERE id=?", (row["previous_state_id"],)).fetchone()
            if predecessor is None or predecessor["next_state_id"] != row["id"]:
                errors.append(f"{row['id']}: predecessor does not point back")
        if row["next_state_id"]:
            successor = conn.execute("SELECT previous_state_id FROM task_states WHERE id=?", (row["next_state_id"],)).fetchone()
            if successor is None or successor["previous_state_id"] != row["id"]:
                errors.append(f"{row['id']}: successor does not point back")
    for row in conn.execute("SELECT id, state_id FROM tasks"):
        if conn.execute("SELECT 1 FROM task_states WHERE id=? AND active=1", (row["state_id"],)).fetchone() is None:
            errors.append(f"{row['id']}: invalid task state")
        if conn.execute("SELECT assurance_on_entry FROM task_states WHERE id=?", (row["state_id"],)).fetchone()[0]:
            missing = conn.execute("""SELECT r.id FROM specialist_roles r
                WHERE r.active=1 AND NOT EXISTS (
                  SELECT 1 FROM task_checks c WHERE c.task_id=? AND c.check_type='assurance'
                    AND c.specialist_role_id=r.id AND c.required=1)""", (row["id"],)).fetchall()
            if missing:
                errors.append(f"{row['id']}: missing specialist assurance checks")
    for row in conn.execute("SELECT id, status, rationale FROM task_checks"):
        if row["status"] == "not_applicable" and not (row["rationale"] or "").strip():
            errors.append(f"{row['id']}: not-applicable check needs rationale")
    if errors:
        fail("; ".join(errors), 1)
    print(f"PASS kanban db valid tasks={conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("validate")
    p_status = sub.add_parser("status")
    p_status.add_argument("--json", action="store_true", dest="as_json")
    p_state = sub.add_parser("state"); state = p_state.add_subparsers(dest="state_command", required=True)
    q = state.add_parser("add"); q.add_argument("state_id"); q.add_argument("name"); q.add_argument("--position", type=int, required=True); q.add_argument("--previous"); q.add_argument("--next"); q.add_argument("--wip-limit", type=int); q.add_argument("--required-fields", default="[]"); q.add_argument("--assurance-on-entry", action="store_true"); q.add_argument("--worker-entry", action="store_true"); q.add_argument("--review-queue", action="store_true"); q.add_argument("--requires-checks", action="store_true"); q.add_argument("--requires-evidence", action="store_true"); q.add_argument("--requires-reviewed-references", action="store_true"); q.add_argument("--terminal", action="store_true")
    q = state.add_parser("set"); q.add_argument("state"); wip = q.add_mutually_exclusive_group(required=True); wip.add_argument("--wip-limit", type=int); wip.add_argument("--unlimited", action="store_true")
    state.add_parser("list")

    p_intent = sub.add_parser("intent"); intent = p_intent.add_subparsers(dest="intent_command", required=True)
    p = intent.add_parser("add"); p.add_argument("intent_id"); p.add_argument("summary"); p.add_argument("--type", dest="intent_type", default="problem"); p.add_argument("--details", default="{}")
    p = intent.add_parser("list")
    p = intent.add_parser("show"); p.add_argument("intent_id")
    p = intent.add_parser("status"); p.add_argument("intent_id"); p.add_argument("state"); p.add_argument("--closure"); p.add_argument("--reason")

    p_goal = sub.add_parser("goal"); goal = p_goal.add_subparsers(dest="goal_command", required=True)
    p = goal.add_parser("capture"); p.add_argument("intent_id"); p.add_argument("summary"); p.add_argument("--type", dest="intent_type", default="problem"); p.add_argument("--success-criterion", action="append", default=[]); p.add_argument("--constraint", action="append", default=[]); p.add_argument("--autonomy"); p.add_argument("--stop-condition", action="append", default=[])

    p_task = sub.add_parser("task"); task = p_task.add_subparsers(dest="task_command", required=True)
    p = task.add_parser("add"); p.add_argument("task_id"); p.add_argument("summary"); p.add_argument("--intent", action="append", dest="intents", default=[]); p.add_argument("--state", default="Backlog"); p.add_argument("--type", dest="task_type", default="work"); p.add_argument("--owner", default="unassigned"); p.add_argument("--scope"); p.add_argument("--acceptance", action="append", default=[]); p.add_argument("--validation", action="append", default=[]); p.add_argument("--details", default="{}")
    p = task.add_parser("list"); p.add_argument("--state"); p.add_argument("--type", dest="task_type")
    p = task.add_parser("show"); p.add_argument("task_id")
    p = task.add_parser("refine"); p.add_argument("task_id"); p.add_argument("--scope"); p.add_argument("--owner"); p.add_argument("--acceptance", action="append"); p.add_argument("--validation", action="append"); p.add_argument("--details"); p.add_argument("--actor", default="coordinator")
    p = task.add_parser("purge"); p.add_argument("task_id"); p.add_argument("--confirm", action="store_true")
    p = task.add_parser("move"); p.add_argument("task_id"); p.add_argument("state"); p.add_argument("--actor", default="coordinator")
    p = task.add_parser("claim"); p.add_argument("task_id"); p.add_argument("--actor", required=True)
    p = task.add_parser("assign"); p.add_argument("task_id"); p.add_argument("owner"); p.add_argument("--actor", default="coordinator")
    p = task.add_parser("requeue"); p.add_argument("task_id"); p.add_argument("--state"); p.add_argument("--reason", required=True); p.add_argument("--actor", default="coordinator")
    p = task.add_parser("event"); events = p.add_subparsers(dest="event_command", required=True); q = events.add_parser("add"); q.add_argument("task_id"); q.add_argument("event_type"); q.add_argument("summary"); q.add_argument("--actor", default="coordinator"); q.add_argument("--payload", default="{}"); q.add_argument("--idempotency-key"); q = events.add_parser("list"); q.add_argument("task_id"); q.add_argument("--limit", type=int, default=100); q.add_argument("--json", action="store_true", dest="as_json")
    p = task.add_parser("dependency"); dep = p.add_subparsers(dest="dependency_command", required=True); q = dep.add_parser("add"); q.add_argument("task_id"); q.add_argument("dependency_id"); q = dep.add_parser("remove"); q.add_argument("task_id"); q.add_argument("dependency_id")
    p = task.add_parser("demand"); demand = p.add_subparsers(dest="demand_command", required=True); q = demand.add_parser("set"); q.add_argument("task_id"); q.add_argument("--parallelism", choices=("serial", "partitionable", "fan-out"), required=True); q.add_argument("--min-workers", type=int, required=True); q.add_argument("--target-workers", type=int, required=True); q.add_argument("--max-workers", type=int, required=True); q.add_argument("--work-units", default="[]"); q.add_argument("--reuse-policy", required=True); q.add_argument("--isolation", required=True); q.add_argument("--aggregation", required=True)

    p_review = sub.add_parser("review"); review = p_review.add_subparsers(dest="review_command", required=True); p = review.add_parser("check"); checks = p.add_subparsers(dest="check_command", required=True); q = checks.add_parser("add"); q.add_argument("check_id"); q.add_argument("task_id"); q.add_argument("check_type", choices=CHECK_TYPES); q.add_argument("criterion"); q.add_argument("--role"); q.add_argument("--optional", action="store_true"); q = checks.add_parser("record"); q.add_argument("check_id"); q.add_argument("task_id"); q.add_argument("status", choices=("passed", "failed", "not_applicable")); q.add_argument("--reviewer"); q.add_argument("--reviewer-role"); q.add_argument("--reviewer-worker-id"); q.add_argument("--finding"); q.add_argument("--rationale"); q = checks.add_parser("list"); q.add_argument("task_id")
    p = sub.add_parser("evidence"); ev = p.add_subparsers(dest="evidence_command", required=True); q = ev.add_parser("add"); q.add_argument("evidence_id"); q.add_argument("task_id"); q.add_argument("artifact"); q.add_argument("--check-id"); q.add_argument("--revision"); q.add_argument("--probe"); q.add_argument("--result", required=True); q.add_argument("--producer", required=True); q.add_argument("--location"); q.add_argument("--content-hash"); q = ev.add_parser("list"); q.add_argument("task_id"); q.add_argument("--check-id"); q.add_argument("--criterion"); q.add_argument("--revision"); q.add_argument("--producer"); q.add_argument("--result"); q.add_argument("--artifact"); q.add_argument("--json", action="store_true", dest="as_json"); q = ev.add_parser("show"); q.add_argument("evidence_id"); q.add_argument("--json", action="store_true", dest="as_json")

    p_role = sub.add_parser("specialist"); role = p_role.add_subparsers(dest="specialist_command", required=True); q = role.add_parser("add"); q.add_argument("role_id"); q.add_argument("name"); q.add_argument("purpose"); q.add_argument("description"); q = role.add_parser("activate"); q.add_argument("role_id"); q = role.add_parser("deactivate"); q.add_argument("role_id"); role.add_parser("list")
    p_guidance = sub.add_parser("guidance"); guidance = p_guidance.add_subparsers(dest="guidance_command", required=True); q = guidance.add_parser("add"); q.add_argument("guidance_id"); q.add_argument("statement"); q.add_argument("--version", type=int, default=1); q.add_argument("--type", dest="guidance_type", default="principle"); q.add_argument("--outcome"); q.add_argument("--rationale"); q.add_argument("--verification"); q.add_argument("--authority"); q.add_argument("--status", choices=("draft", "active", "retired"), default="active"); q = guidance.add_parser("reference"); q.add_argument("guidance_id"); q.add_argument("reference_id"); q.add_argument("--version", type=int, default=1); q.add_argument("--relationship", default="supports")
    p_ref = sub.add_parser("reference"); refs = p_ref.add_subparsers(dest="reference_command", required=True); q = refs.add_parser("add"); q.add_argument("reference_id"); q.add_argument("url"); q.add_argument("--title"); q.add_argument("--publisher"); q.add_argument("--reference-type"); q.add_argument("--summary"); q.add_argument("--relevance"); q.add_argument("--constraints"); q.add_argument("--content-hash"); q = refs.add_parser("list"); q.add_argument("--review-state", choices=("unreviewed", "reviewed", "rejected")); q.add_argument("--json", action="store_true", dest="as_json"); q = refs.add_parser("update"); q.add_argument("reference_id"); q.add_argument("--url"); q.add_argument("--title"); q.add_argument("--publisher"); q.add_argument("--reference-type"); q.add_argument("--summary"); q.add_argument("--relevance"); q.add_argument("--constraints"); q.add_argument("--content-hash"); q.add_argument("--provenance"); q = refs.add_parser("link"); q.add_argument("reference_id"); q.add_argument("--intent-id"); q.add_argument("--task-id"); q = refs.add_parser("review"); q.add_argument("reference_id"); q.add_argument("review_state", choices=("unreviewed", "reviewed", "rejected"))

    p_pull = sub.add_parser("pull"); pull = p_pull.add_subparsers(dest="pull_command", required=True); q = pull.add_parser("next"); q.add_argument("--claim", action="store_true"); q.add_argument("--lease", help="atomically consume one lease slot and claim the next eligible task"); q.add_argument("--actor", default="coordinator"); q.add_argument("--json", action="store_true", dest="as_json"); p_lease = pull.add_parser("lease"); lease = p_lease.add_subparsers(dest="lease_command", required=True); q = lease.add_parser("issue"); q.add_argument("lease_id"); q.add_argument("--stage", required=True); q.add_argument("--lane", required=True); q.add_argument("--slots", type=int, required=True); q.add_argument("--eligibility", default="{}"); q.add_argument("--required-output", required=True); q.add_argument("--owner", required=True); q.add_argument("--ttl-seconds", type=int, required=True); q.add_argument("--idempotency-key", required=True); q = lease.add_parser("renew"); q.add_argument("lease_id"); q.add_argument("--ttl-seconds", type=int, required=True); q = lease.add_parser("release"); q.add_argument("lease_id"); q = lease.add_parser("reserve"); q.add_argument("lease_id"); q.add_argument("task_id"); q.add_argument("--slots", type=int, default=1); q = lease.add_parser("release-reservation"); q.add_argument("lease_id"); q.add_argument("task_id")
    return parser


def dispatch(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    if args.command == "init":
        return 0
    if args.command == "validate":
        validate(conn); return 0
    if args.command == "status":
        status(conn, args.as_json); return 0
    if args.command == "state":
        if args.state_command == "add": state_add(conn, args)
        elif args.state_command == "set": state_set(conn, args)
        else: state_list(conn)
        return 0
    if args.command in ("intent", "goal"):
        if args.command == "goal":
            details = {"success_criteria": args.success_criterion, "constraints": args.constraint, "autonomy": args.autonomy, "stop_conditions": args.stop_condition}
            intent_add(conn, args.intent_id, args.intent_type, args.summary, details); return 0
        if args.intent_command == "add": intent_add(conn, args.intent_id, args.intent_type, args.summary, json_object(args.details, "details"))
        elif args.intent_command == "list": intent_list(conn)
        elif args.intent_command == "show": intent_show(conn, args.intent_id)
        else: intent_status(conn, args.intent_id, args.state, args.closure, args.reason)
        return 0
    if args.command == "task":
        if args.task_command == "add": task_add(conn, args.task_id, args.summary, args.intents, args.state, args.task_type, args.owner, args.scope, args.acceptance, args.validation, json_object(args.details, "details"))
        elif args.task_command == "list": task_list(conn, args.state, args.task_type)
        elif args.task_command == "show": task_show(conn, args.task_id)
        elif args.task_command == "refine": task_refine(conn, args)
        elif args.task_command == "purge": task_purge(conn, args.task_id, args.confirm)
        elif args.task_command == "move": task_move(conn, args.task_id, args.state, args.actor)
        elif args.task_command == "claim": task_claim(conn, args.task_id, args.actor)
        elif args.task_command == "assign": task_assign(conn, args.task_id, args.owner, args.actor)
        elif args.task_command == "requeue": task_requeue(conn, args)
        elif args.task_command == "event":
            if args.event_command == "add": task_event_add(conn, args)
            else: task_event_list(conn, args)
        elif args.task_command == "dependency": task_dependency(conn, args.task_id, args.dependency_id, args.dependency_command == "remove")
        else: task_demand_set(conn, args)
        return 0
    if args.command == "review":
        if args.check_command == "add": check_add(conn, args)
        elif args.check_command == "record": check_record(conn, args)
        else:
            for row in conn.execute("SELECT id, check_type, criterion, specialist_role_id, status, reviewer, reviewer_role_id, reviewer_worker_id FROM task_checks WHERE task_id=? ORDER BY id", (args.task_id,)):
                print("\t".join(str(row[k] or "") for k in ("id", "check_type", "criterion", "specialist_role_id", "status", "reviewer", "reviewer_role_id", "reviewer_worker_id")))
        return 0
    if args.command == "evidence":
        if args.evidence_command == "add": evidence_add(conn, args)
        elif args.evidence_command == "show": evidence_show(conn, args)
        else: evidence_list(conn, args)
        return 0
    if args.command == "specialist":
        if args.specialist_command == "add": role_add(conn, args)
        elif args.specialist_command == "activate": role_set_active(conn, args, True)
        elif args.specialist_command == "deactivate": role_set_active(conn, args, False)
        else: role_list(conn)
        return 0
    if args.command == "guidance":
        if args.guidance_command == "add": guidance_add(conn, args)
        else: guidance_reference(conn, args)
        return 0
    if args.command == "reference":
        if args.reference_command == "add": reference_add(conn, args)
        elif args.reference_command == "list": reference_list(conn, args)
        elif args.reference_command == "update": reference_update(conn, args)
        elif args.reference_command == "link": reference_link(conn, args)
        else: reference_review(conn, args)
        return 0
    if args.command == "pull":
        if args.pull_command == "next": pull_next(conn, args)
        elif args.lease_command == "issue": lease_issue(conn, args)
        elif args.lease_command == "reserve": lease_reserve(conn, args)
        elif args.lease_command == "release-reservation": lease_release_reservation(conn, args)
        else: lease_update(conn, args, args.lease_command)
        return 0
    fail(f"Unknown command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conn = connect(args.db)
    try:
        init_db(conn, args.schema, args.db.with_name(args.db.stem + ".legacy.db"))
        try:
            return dispatch(args, conn)
        except sqlite3.IntegrityError as exc:
            fail(f"Database invariant rejected the operation: {exc}")
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
