#!/usr/bin/env python3
"""SQLite-backed project kanban helper."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path.cwd().resolve()
KANBAN_DIR = ROOT / ".kanban"
DEFAULT_DB = KANBAN_DIR / "kanban.db"
DEFAULT_SCHEMA_PATH = SCRIPT_DIR / "schema.sql"
HANDOFF_SCHEMA_PATH = SCRIPT_DIR.parent / "references" / "specialist-handoff.schema.json"
DEFAULT_COLUMN_WIP_LIMITS = {
    "Active": 1,
    "Review": 3,
}
DEFAULT_BACKFILL_GOALS = {
    "Active": {
        "target_value": 2,
        "description": "Target number of active worker lanes to backfill when safe.",
    },
    "Ready": {
        "target_value": 10,
        "description": "Target number of Ready cards to maintain for worker backfill.",
    },
}
LEGACY_PARALLEL_WORKERS = {
    "none": 0,
    "conservative": 2,
    "moderate": 4,
    "aggressive": 8,
}
DEFAULT_COLUMNS = (
    {
        "name": "Backlog",
        "position": 10,
        "description": "Known work not ready to pull.",
        "required_rules": ["captured goal or idea"],
        "direction": "forward",
    },
    {
        "name": "Ready",
        "position": 20,
        "description": "Clear, unblocked work with owner, scope, exit criteria, and validation.",
        "required_rules": ["scope", "owner", "exit_criteria", "validation"],
        "direction": "forward",
    },
    {
        "name": "Active",
        "position": 30,
        "description": "Work currently being executed.",
        "required_rules": [
            "scope and non-goals are explicit",
            "acceptance criteria are observable",
            "constraints and authority boundaries are resolved",
            "implementation and rollback plan are confirmed",
            "design validation and proof strategy are satisfied",
            "plan_confirmed",
        ],
        "direction": "forward",
    },
    {
        "name": "Blocked",
        "position": 35,
        "description": "Work waiting on a named unblock condition.",
        "required_rules": ["blocker owner", "unblock condition", "resume priority"],
        "direction": "neutral",
    },
    {
        "name": "Review",
        "position": 40,
        "description": "Completed output waiting for acceptance or validation review.",
        "required_rules": ["completion payload", "validation evidence or explicit no-run reason"],
        "direction": "forward",
    },
    {
        "name": "Done",
        "position": 50,
        "description": "Accepted work with proof.",
        "required_rules": ["proof", "accepted_review"],
        "direction": "terminal",
    },
    {
        "name": "Deferred",
        "position": 60,
        "description": "Intentionally postponed work with a resume condition.",
        "required_rules": ["resume condition", "expected proof", "risk if left deferred"],
        "direction": "terminal",
    },
)
DEFAULT_TRANSITIONS = (
    ("Backlog", "Ready", "scope, owner, dependencies, and exit criteria are clear"),
    ("Ready", "Active", "worker available and evidence-backed start gate satisfied"),
    ("Active", "Blocked", "concrete dependency prevents next action"),
    ("Active", "Review", "deliverable exists and lane validation ran or has no-run reason"),
    ("Active", "Done", "small/read-only card has accepted proof"),
    ("Active", "Deferred", "work intentionally postponed with resume condition"),
    ("Blocked", "Ready", "blocker cleared and work is pullable"),
    ("Blocked", "Active", "blocker cleared and worker resumes immediately"),
    ("Blocked", "Deferred", "blocked work intentionally postponed"),
    ("Review", "Done", "completion payload accepted and integration risks closed or queued"),
    ("Review", "Active", "review returned bounded follow-up"),
    ("Ready", "Deferred", "ready work intentionally postponed"),
    ("Backlog", "Deferred", "unplanned idea intentionally postponed"),
    ("Deferred", "Backlog", "deferred work resumed for replanning"),
    ("Deferred", "Ready", "resume condition satisfied and card is pullable"),
)
BACKLOG_STATUSES = ("new", "ready", "active", "done", "rejected", "deferred")
INTENT_KINDS = ("idea", "problem", "concern", "opportunity", "question")
INTENT_STATES = ("captured", "researching", "refining", "planned", "deferred", "closed")
INTENT_CLOSURES = ("realized", "rejected")
CANONICAL_REWORK_STAGES = {"Discover", "Design", "Implement", "Verify", "Deliver", "Observe"}
RUN_STATUSES = ("active", "paused", "cancelled", "complete", "failed")
RUN_WORKER_STATES = ("working", "waiting", "blocked", "stalled", "complete")


def fail(message: str, code: int = 2) -> None:
    print(f"FAIL {message}", file=sys.stderr)
    raise SystemExit(code)


def require_backlog_status(status: str, context: str = "backlog status") -> None:
    if status not in BACKLOG_STATUSES:
        fail(f"Invalid {context} {status}; expected one of {', '.join(BACKLOG_STATUSES)}")


def require_intent_kind(kind: str) -> None:
    if kind not in INTENT_KINDS:
        fail(f"Invalid intent kind {kind}; expected one of {', '.join(INTENT_KINDS)}")


def require_intent_state(state: str) -> None:
    if state not in INTENT_STATES:
        fail(f"Invalid intent state {state}; expected one of {', '.join(INTENT_STATES)}")


def require_intent_closure(state: str, closure: str | None) -> None:
    if state == "closed" and closure not in INTENT_CLOSURES:
        fail(f"Closed intents require closure={','.join(INTENT_CLOSURES)}")
    if state != "closed" and closure is not None:
        fail("Only closed intents may have a closure reason")


def now() -> int:
    return int(time.time())


def json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def json_loads(value: str | None, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    return json.loads(value)


def slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or fallback


def connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def write_transaction(conn: sqlite3.Connection) -> Any:
    class Transaction:
        def __enter__(self) -> sqlite3.Connection:
            conn.execute("BEGIN IMMEDIATE")
            return conn

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            if exc_type is None:
                conn.commit()
            else:
                conn.rollback()
            return False

    return Transaction()


def init_db(conn: sqlite3.Connection, schema_path: Path) -> None:
    if not schema_path.is_file():
        fail(f"Missing schema: {schema_path}")
    with write_transaction(conn):
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        cursor = conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', '15') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        ensure_default_columns(conn)
        ensure_default_wip_limits(conn)
        migrate_backfill_goals(conn)
        migrate_principle_versions(conn)
        migrate_specialist_enrollments(conn)
        ensure_default_backfill_goals(conn)
        conn.execute(
            "INSERT OR IGNORE INTO learning_events(occurred_at, event_type, reason_summary, task_id, source_task_event_id) "
            "SELECT created_at, event_type, message, task_id, event_id FROM task_events"
        )


def legacy_wip_limit(conn: sqlite3.Connection, key: str, default: int) -> int:
    row = conn.execute("SELECT value_json FROM constraints_kv WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    value = json_loads(row["value_json"])
    if isinstance(value, int) and value > 0:
        return value
    return default


def ensure_default_wip_limits(conn: sqlite3.Connection) -> None:
    defaults = {
        "Active": legacy_wip_limit(conn, "active_wip_limit", DEFAULT_COLUMN_WIP_LIMITS["Active"]),
        "Review": legacy_wip_limit(conn, "review_wip_limit", DEFAULT_COLUMN_WIP_LIMITS["Review"]),
    }
    for column, limit in defaults.items():
        conn.execute(
            """
            INSERT INTO column_wip_limits(column_name, limit_value)
            VALUES(?, ?)
            ON CONFLICT(column_name) DO NOTHING
            """,
            (column, limit),
        )
    conn.execute(
        "DELETE FROM constraints_kv WHERE key IN ('active_wip_limit', 'review_wip_limit')"
    )


def legacy_parallel_workers(conn: sqlite3.Connection, default: int) -> int:
    row = conn.execute(
        "SELECT value_json FROM constraints_kv WHERE key = 'parallel_workers'"
    ).fetchone()
    if row is None:
        return default
    value = json_loads(row["value_json"])
    if isinstance(value, int) and value >= 0:
        return value
    return LEGACY_PARALLEL_WORKERS.get(str(value), default)


def legacy_ready_buffer(conn: sqlite3.Connection, default: int) -> int:
    row = conn.execute(
        "SELECT value_json FROM constraints_kv WHERE key = 'ready_buffer_target'"
    ).fetchone()
    if row is None:
        return default
    value = json_loads(row["value_json"])
    if isinstance(value, int) and value >= 0:
        return value
    return default


def ensure_default_backfill_goals(conn: sqlite3.Connection) -> None:
    defaults = {
        "Active": legacy_parallel_workers(
            conn,
            DEFAULT_BACKFILL_GOALS["Active"]["target_value"],
        ),
        "Ready": legacy_ready_buffer(
            conn,
            DEFAULT_BACKFILL_GOALS["Ready"]["target_value"],
        ),
    }
    for column_name, goal in DEFAULT_BACKFILL_GOALS.items():
        conn.execute(
            """
            INSERT INTO backfill_goals(column_name, target_value, description)
            VALUES(?, ?, ?)
            ON CONFLICT(column_name) DO NOTHING
            """,
            (column_name, defaults[column_name], goal["description"]),
        )
    conn.execute(
        "DELETE FROM constraints_kv WHERE key IN ('parallel_workers', 'ready_buffer_target')"
    )


def migrate_backfill_goals(conn: sqlite3.Connection) -> None:
    info = conn.execute("PRAGMA table_info(backfill_goals)").fetchall()
    names = {row["name"] for row in info}
    if "goal_name" not in names:
        return
    existing_columns = set(column_names(conn))
    legacy_map = {
        "worker_parallelism": "Active",
        "ready_preparation": "Ready",
    }
    rows = conn.execute(
        "SELECT goal_name, target_value, description FROM backfill_goals"
    ).fetchall()
    conn.execute("ALTER TABLE backfill_goals RENAME TO backfill_goals_legacy")
    conn.execute(
        """
        CREATE TABLE backfill_goals (
            column_name TEXT PRIMARY KEY REFERENCES columns(name) ON DELETE CASCADE,
            target_value INTEGER NOT NULL CHECK (target_value >= 0),
            description TEXT
        )
        """
    )
    for row in rows:
        column_name = legacy_map.get(row["goal_name"], row["goal_name"])
        if column_name not in existing_columns:
            continue
        description = row["description"]
        if row["goal_name"] in legacy_map:
            description = DEFAULT_BACKFILL_GOALS[column_name]["description"]
        conn.execute(
            """
            INSERT INTO backfill_goals(column_name, target_value, description)
            VALUES(?, ?, ?)
            ON CONFLICT(column_name) DO UPDATE SET
                target_value=excluded.target_value,
                description=COALESCE(excluded.description, backfill_goals.description)
            """,
            (column_name, row["target_value"], description),
        )
    conn.execute("DROP TABLE backfill_goals_legacy")


def migrate_principle_versions(conn: sqlite3.Connection) -> None:
    """Give legacy principle statements a durable first version without rewriting them."""
    conn.execute(
        """
        INSERT OR IGNORE INTO principle_versions(
            principle_id, version, statement, intended_outcome, scope_type,
            authority_class, rationale, status, effective_at, created_at
        )
        SELECT id, 1, statement, statement, 'project', 'local-policy',
               'Migrated from the legacy principle record.',
               CASE WHEN status = 'active' THEN 'active' ELSE 'retired' END,
               updated_at, updated_at
        FROM principles
        """
    )


def migrate_specialist_enrollments(conn: sqlite3.Connection) -> None:
    """Enroll active classes in unfinished legacy projects without inventing consultations."""
    conn.execute(
        """
        INSERT OR IGNORE INTO project_specialist_enrollments(
            intent_id, specialist_class_id, specialist_class_version, status,
            rationale, enrolled_at, updated_at
        )
        SELECT i.id, c.id, c.version, 'enrolled',
               'Schema 14 migration: active specialist enrolled in unfinished project.',
               i.updated_at, i.updated_at
        FROM intents i CROSS JOIN specialist_classes c
        WHERE i.state <> 'closed' AND c.active=1
        """
    )


def ensure_default_columns(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) FROM columns").fetchone()[0]
    if count:
        return
    for column in DEFAULT_COLUMNS:
        conn.execute(
            """
            INSERT INTO columns(name, position, description, required_rules_json, direction, active)
            VALUES(?, ?, ?, ?, ?, 1)
            """,
            (
                column["name"],
                column["position"],
                column["description"],
                json_dumps(column["required_rules"]),
                column["direction"],
            ),
        )
    for from_column, to_column, rule in DEFAULT_TRANSITIONS:
        conn.execute(
            """
            INSERT INTO column_transitions(from_column, to_column, rule)
            VALUES(?, ?, ?)
            """,
            (from_column, to_column, rule),
        )


def column_names(conn: sqlite3.Connection) -> list[str]:
    return [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM columns WHERE active = 1 ORDER BY position, name"
        )
    ]


def require_column(conn: sqlite3.Connection, column: str) -> None:
    row = conn.execute(
        "SELECT name FROM columns WHERE name = ? AND active = 1",
        (column,),
    ).fetchone()
    if row is None:
        names = ", ".join(column_names(conn))
        fail(f"Invalid column {column}; expected one of {names}")


def column_rules(conn: sqlite3.Connection, column: str) -> list[str]:
    row = conn.execute(
        "SELECT required_rules_json FROM columns WHERE name = ?",
        (column,),
    ).fetchone()
    if row is None:
        return []
    rules = json_loads(row["required_rules_json"], [])
    return [str(rule) for rule in rules or []]


def task_exists(conn: sqlite3.Connection, task_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return row is not None


def backlog_exists(conn: sqlite3.Connection, idea_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM backlog_ideas WHERE id = ?", (idea_id,)).fetchone()
    return row is not None


def scalar_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float)):
        return str(value)
    return json_dumps(value)


def validation_status(card: dict[str, Any]) -> str | None:
    validation = card.get("validation")
    if isinstance(validation, dict):
        status = validation.get("status")
        return str(status) if status is not None else None
    return None


def plan_status(card: dict[str, Any]) -> str | None:
    plan = card.get("plan")
    if isinstance(plan, dict):
        status = plan.get("status")
        return str(status) if status is not None else None
    return None


def upsert_task(conn: sqlite3.Connection, card: dict[str, Any]) -> None:
    task_id = str(card.get("id") or "")
    if not task_id:
        fail("Card without id cannot be imported")
    timestamp = now()
    conn.execute(
        """
        INSERT INTO tasks (
            id, column_name, owner, scope, goal, blocker_json, priority,
            value_score, effort_score, wsjf, complexity, ambiguity, review_rigor,
            validation_status, readiness_json, plan_status, raw_json, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            column_name=excluded.column_name,
            owner=excluded.owner,
            scope=excluded.scope,
            goal=excluded.goal,
            blocker_json=excluded.blocker_json,
            priority=excluded.priority,
            value_score=excluded.value_score,
            effort_score=excluded.effort_score,
            wsjf=excluded.wsjf,
            complexity=excluded.complexity,
            ambiguity=excluded.ambiguity,
            review_rigor=excluded.review_rigor,
            validation_status=excluded.validation_status,
            readiness_json=excluded.readiness_json,
            plan_status=excluded.plan_status,
            raw_json=excluded.raw_json,
            updated_at=excluded.updated_at
        """,
        (
            task_id,
            str(card.get("column") or "Backlog"),
            str(card.get("owner") or "unassigned"),
            scalar_text(card.get("scope")),
            scalar_text(card.get("goal")),
            json_dumps(card.get("blocker")),
            scalar_text(card.get("priority")),
            card.get("value") if isinstance(card.get("value"), (int, float)) else None,
            card.get("effort") if isinstance(card.get("effort"), (int, float)) else None,
            scalar_text(card.get("wsjf")),
            scalar_text(card.get("complexity")),
            scalar_text(card.get("ambiguity")),
            scalar_text(card.get("review_rigor")),
            validation_status(card),
            json_dumps(card.get("readiness")),
            plan_status(card),
            json_dumps(card),
            timestamp,
        ),
    )
    conn.execute("DELETE FROM task_themes WHERE task_id = ?", (task_id,))
    for theme in card.get("themes") or []:
        conn.execute(
            "INSERT OR IGNORE INTO task_themes(task_id, theme) VALUES(?, ?)",
            (task_id, str(theme)),
        )
    conn.execute("DELETE FROM task_dependencies WHERE task_id = ?", (task_id,))
    for dependency in card.get("dependencies") or []:
        conn.execute(
            "INSERT OR IGNORE INTO task_dependencies(task_id, dependency) VALUES(?, ?)",
            (task_id, str(dependency)),
        )


def load_legacy_document(path: Path) -> Any:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError:
            fail("Reading legacy YAML requires PyYAML; install it or convert the file to JSON first")
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    fail("Legacy import accepts only .yaml, .yml, or .json input files")


def normalize_legacy_task(item: Any, default_column: str | None = None) -> dict[str, Any]:
    if not isinstance(item, dict):
        fail("Legacy task entries must be mappings")
    card = dict(item)
    if "id" not in card and "task_id" in card:
        card["id"] = card["task_id"]
    if "goal" not in card:
        for key in ("summary", "title", "description"):
            if key in card:
                card["goal"] = card[key]
                break
    if "column" not in card:
        card["column"] = default_column or card.get("status") or "Backlog"
    card.setdefault("owner", "unassigned")
    card.setdefault("themes", [])
    card.setdefault("dependencies", [])
    return card


def normalize_legacy_backlog_item(item: Any, index: int) -> dict[str, Any]:
    if isinstance(item, str):
        summary = item
        idea_id = slugify(summary, f"legacy-{index}")
        return {"id": idea_id, "summary": summary, "status": "new", "themes": []}
    if not isinstance(item, dict):
        fail("Legacy backlog entries must be strings or mappings")
    idea = dict(item)
    summary = str(idea.get("summary") or idea.get("title") or idea.get("goal") or "")
    if not summary:
        fail("Legacy backlog entry missing summary/title/goal")
    idea_id = str(idea.get("id") or idea.get("idea_id") or slugify(summary, f"legacy-{index}"))
    themes = idea.get("themes") or idea.get("theme") or []
    if isinstance(themes, str):
        themes = [themes]
    idea["id"] = idea_id
    idea["summary"] = summary
    idea["status"] = str(idea.get("status") or "new")
    require_backlog_status(idea["status"], "legacy backlog status")
    idea["themes"] = [str(theme) for theme in themes]
    return idea


def legacy_task_items(document: Any, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return [normalize_legacy_task(item) for item in document]
    if not isinstance(document, dict):
        fail("Legacy task document must be a mapping or list")
    for key in ("tasks", "cards", "queue"):
        value = document.get(key)
        if isinstance(value, list):
            return [normalize_legacy_task(item) for item in value]
    items: list[dict[str, Any]] = []
    columns = set(column_names(conn))
    for key, value in document.items():
        if key in columns and isinstance(value, list):
            items.extend(normalize_legacy_task(item, key) for item in value)
    if items:
        return items
    fail("Legacy task document has no tasks/cards/queue list or column-grouped task lists")


def legacy_backlog_items(document: Any) -> list[dict[str, Any]]:
    source = document
    if isinstance(document, dict):
        for key in ("backlog", "ideas", "items"):
            if isinstance(document.get(key), list):
                source = document[key]
                break
    if not isinstance(source, list):
        fail("Legacy backlog document must be a list or contain backlog/ideas/items")
    return [normalize_legacy_backlog_item(item, index) for index, item in enumerate(source, 1)]


def upsert_backlog_idea(conn: sqlite3.Connection, idea: dict[str, Any]) -> None:
    idea_id = str(idea["id"])
    summary = str(idea["summary"])
    status = str(idea.get("status") or "new")
    require_backlog_status(status)
    themes = [str(theme) for theme in idea.get("themes") or []]
    conn.execute(
        """
        INSERT INTO backlog_ideas(id, summary, status, themes_json, raw_json, updated_at)
        VALUES(?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            summary=excluded.summary,
            status=excluded.status,
            themes_json=excluded.themes_json,
            raw_json=excluded.raw_json,
            updated_at=excluded.updated_at
        """,
        (idea_id, summary, status, json_dumps(themes), json_dumps(idea), now()),
    )


def import_legacy(conn: sqlite3.Connection, path: Path, kind: str) -> None:
    document = load_legacy_document(path)
    with write_transaction(conn):
        task_count = 0
        backlog_count = 0
        selected_kind = kind
        if selected_kind == "auto":
            if isinstance(document, dict) and any(key in document for key in ("backlog", "ideas", "items")):
                selected_kind = "backlog"
            else:
                selected_kind = "tasks"
        if selected_kind == "tasks":
            for card in legacy_task_items(document, conn):
                upsert_task(conn, card)
                task_count += 1
        elif selected_kind == "backlog":
            for idea in legacy_backlog_items(document):
                upsert_backlog_idea(conn, idea)
                backlog_count += 1
        else:
            fail(f"Unknown legacy import kind: {kind}")
    print(f"imported tasks={task_count} backlog={backlog_count} from {path}")


def list_config(conn: sqlite3.Connection) -> None:
    for row in conn.execute(
        """
        SELECT c.name, w.limit_value
        FROM column_wip_limits w
        JOIN columns c ON c.name = w.column_name
        ORDER BY c.position, c.name
        """
    ):
        print(f"wip_limit\t{row['name']}\t{row['limit_value']}")
    for row in conn.execute(
        """
        SELECT column_name, target_value, description
        FROM backfill_goals
        ORDER BY COALESCE((SELECT position FROM columns WHERE name = column_name), 9999),
                 column_name
        """
    ):
        description = f"\t{row['description']}" if row["description"] else ""
        print(f"backfill_goal\t{row['column_name']}\t{row['target_value']}{description}")
    for row in conn.execute("SELECT key, value_json FROM constraints_kv ORDER BY key"):
        print(f"constraint\t{row['key']}\t{json_loads(row['value_json'])}")


def set_column_wip_limit(conn: sqlite3.Connection, column: str, limit: int) -> None:
    require_column(conn, column)
    if limit < 1:
        fail("WIP limit must be a positive integer")
    with write_transaction(conn):
        conn.execute(
            """
            INSERT INTO column_wip_limits(column_name, limit_value)
            VALUES(?, ?)
            ON CONFLICT(column_name) DO UPDATE SET limit_value=excluded.limit_value
            """,
            (column, limit),
        )


def set_backfill_goal(conn: sqlite3.Connection, column: str, target: int, description: str | None) -> None:
    require_column(conn, column)
    if target < 0:
        fail("Backfill goal target must be a non-negative integer")
    with write_transaction(conn):
        conn.execute(
            """
            INSERT INTO backfill_goals(column_name, target_value, description)
            VALUES(?, ?, ?)
            ON CONFLICT(column_name) DO UPDATE SET
                target_value=excluded.target_value,
                description=COALESCE(excluded.description, backfill_goals.description)
            """,
            (column, target, description),
        )


def update_task_raw(conn: sqlite3.Connection, task_id: str, mutate: Any) -> None:
    with write_transaction(conn):
        row = conn.execute("SELECT raw_json FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            fail(f"Unknown task: {task_id}")
        card = json_loads(row["raw_json"])
        mutate(card)
        upsert_task(conn, card)


def task_move(conn: sqlite3.Connection, task_id: str, column: str, owner: str | None) -> None:
    require_column(conn, column)
    with write_transaction(conn):
        row = conn.execute(
            "SELECT column_name, raw_json FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            fail(f"Unknown task: {task_id}")
        card = json_loads(row["raw_json"])
        card["column"] = column
        if owner is not None:
            card["owner"] = owner
        upsert_task(conn, card)
        insert_task_learning_event(conn, task_id, "move", f"moved to {column}")


def task_set_validation(conn: sqlite3.Connection, task_id: str, status: str, evidence: str | None) -> None:
    def mutate(card: dict[str, Any]) -> None:
        validation = card.setdefault("validation", {})
        if not isinstance(validation, dict):
            validation = {}
            card["validation"] = validation
        validation["status"] = status
        if evidence:
            items = validation.setdefault("evidence", [])
            if not isinstance(items, list):
                items = [str(items)]
                validation["evidence"] = items
            items.append(evidence)

    update_task_raw(conn, task_id, mutate)


def append_unique(values: Any, item: str) -> list[str]:
    if values is None:
        items: list[str] = []
    elif isinstance(values, list):
        items = [str(value) for value in values]
    else:
        items = [str(values)]
    if item not in items:
        items.append(item)
    return items


def insert_task_learning_event(
    conn: sqlite3.Connection, task_id: str | None, event_type: str, message: str
) -> None:
    conn.execute(
        "INSERT INTO learning_events(occurred_at, event_type, reason_summary, task_id) VALUES(?, ?, ?, ?)",
        (now(), event_type, message, task_id),
    )


def add_task_event(conn: sqlite3.Connection, task_id: str | None, event_type: str, message: str) -> None:
    if task_id is not None and not task_exists(conn, task_id):
        fail(f"Unknown task: {task_id}")
    with write_transaction(conn):
        insert_task_learning_event(conn, task_id, event_type, message)


def task_add_blocker(conn: sqlite3.Connection, task_id: str, blocked_by: str, reason: str | None) -> None:
    if not task_exists(conn, task_id):
        fail(f"Unknown task: {task_id}")

    def mutate(card: dict[str, Any]) -> None:
        blocker = card.get("blocker")
        if not isinstance(blocker, dict):
            blocker = {}
            card["blocker"] = blocker
        blocker["blocked_by"] = append_unique(blocker.get("blocked_by"), blocked_by)
        if reason:
            reasons = blocker.setdefault("reasons", {})
            if not isinstance(reasons, dict):
                reasons = {}
                blocker["reasons"] = reasons
            reasons[blocked_by] = reason
        card["blocked_by"] = append_unique(card.get("blocked_by"), blocked_by)

    update_task_raw(conn, task_id, mutate)
    add_task_event(conn, task_id, "blocker.add", f"blocked by {blocked_by}" + (f": {reason}" if reason else ""))


def task_remove_blocker(conn: sqlite3.Connection, task_id: str, blocked_by: str) -> None:
    if not task_exists(conn, task_id):
        fail(f"Unknown task: {task_id}")

    def mutate(card: dict[str, Any]) -> None:
        blocker = card.get("blocker")
        if isinstance(blocker, dict):
            blocked_by_values = [item for item in append_unique(blocker.get("blocked_by"), "") if item and item != blocked_by]
            if blocked_by_values:
                blocker["blocked_by"] = blocked_by_values
            else:
                blocker.pop("blocked_by", None)
            reasons = blocker.get("reasons")
            if isinstance(reasons, dict):
                reasons.pop(blocked_by, None)
                if not reasons:
                    blocker.pop("reasons", None)
            if not blocker:
                card["blocker"] = None
        card_blocked_by = [item for item in append_unique(card.get("blocked_by"), "") if item and item != blocked_by]
        if card_blocked_by:
            card["blocked_by"] = card_blocked_by
        else:
            card.pop("blocked_by", None)

    update_task_raw(conn, task_id, mutate)
    add_task_event(conn, task_id, "blocker.remove", f"removed blocker {blocked_by}")


def task_add_metadata(conn: sqlite3.Connection, task_id: str, key: str, value: str) -> None:
    if not task_exists(conn, task_id):
        fail(f"Unknown task: {task_id}")
    try:
        parsed_value: Any = json.loads(value)
    except json.JSONDecodeError:
        parsed_value = value

    def mutate(card: dict[str, Any]) -> None:
        card[key] = parsed_value

    update_task_raw(conn, task_id, mutate)
    add_task_event(conn, task_id, "metadata.add", f"set {key}")


def task_remove_metadata(conn: sqlite3.Connection, task_id: str, key: str) -> None:
    if not task_exists(conn, task_id):
        fail(f"Unknown task: {task_id}")

    def mutate(card: dict[str, Any]) -> None:
        card.pop(key, None)

    update_task_raw(conn, task_id, mutate)
    add_task_event(conn, task_id, "metadata.remove", f"removed {key}")


def task_review_start(conn: sqlite3.Connection, task_id: str, worker: str, agent_id: str | None, note: str | None) -> None:
    if not task_exists(conn, task_id):
        fail(f"Unknown task: {task_id}")

    def mutate(card: dict[str, Any]) -> None:
        card["review_worker"] = worker
        if agent_id:
            card["review_worker_agent_id"] = agent_id
        card["review_status"] = "in_progress"
        card.pop("review_recommendation", None)
        if note:
            card["review_note"] = note

    update_task_raw(conn, task_id, mutate)
    add_task_event(conn, task_id, "review.started", f"review started by {worker}" + (f": {note}" if note else ""))


def task_review_accept(conn: sqlite3.Connection, task_id: str, worker: str | None, agent_id: str | None, evidence: list[str]) -> None:
    if not task_exists(conn, task_id):
        fail(f"Unknown task: {task_id}")

    def mutate(card: dict[str, Any]) -> None:
        if worker:
            card["review_worker"] = worker
        if agent_id:
            card["review_worker_agent_id"] = agent_id
        card["review_status"] = "done"
        card["review_recommendation"] = "Done"
        if evidence:
            notes = card.setdefault("review_notes", [])
            if not isinstance(notes, list):
                notes = [str(notes)]
                card["review_notes"] = notes
            notes.extend(evidence)
        validation = card.setdefault("validation", {})
        if isinstance(validation, dict):
            validation["status"] = "pass"
            if evidence:
                items = validation.setdefault("evidence", [])
                if not isinstance(items, list):
                    items = [str(items)]
                    validation["evidence"] = items
                items.extend(evidence)

    update_task_raw(conn, task_id, mutate)
    add_task_event(conn, task_id, "review.accepted", "independent review accepted task")


def task_review_rework(conn: sqlite3.Connection, task_id: str, worker: str | None, agent_id: str | None, finding: list[str]) -> None:
    if not task_exists(conn, task_id):
        fail(f"Unknown task: {task_id}")

    def mutate(card: dict[str, Any]) -> None:
        if worker:
            card["review_worker"] = worker
        if agent_id:
            card["review_worker_agent_id"] = agent_id
        card["review_status"] = "needs_rework"
        card["review_recommendation"] = "Rework"
        if finding:
            items = card.setdefault("rework_needed", [])
            if not isinstance(items, list):
                items = [str(items)]
                card["rework_needed"] = items
            items.extend(finding)
        validation = card.setdefault("validation", {})
        if isinstance(validation, dict):
            validation["status"] = "needs_rework"
            if finding:
                items = validation.setdefault("evidence", [])
                if not isinstance(items, list):
                    items = [str(items)]
                    validation["evidence"] = items
                items.extend(finding)

    update_task_raw(conn, task_id, mutate)
    add_task_event(conn, task_id, "review.rework", "independent review requested rework")


def task_add_dependency(conn: sqlite3.Connection, task_id: str, dependency: str) -> None:
    if not task_exists(conn, task_id):
        fail(f"Unknown task: {task_id}")
    if dependency == task_id:
        fail("Task cannot depend on itself")
    with write_transaction(conn):
        row = conn.execute("SELECT raw_json FROM tasks WHERE id = ?", (task_id,)).fetchone()
        card = json_loads(row["raw_json"])
        dependencies = card.setdefault("dependencies", [])
        if not isinstance(dependencies, list):
            dependencies = [str(dependencies)]
            card["dependencies"] = dependencies
        if dependency not in [str(item) for item in dependencies]:
            dependencies.append(dependency)
        upsert_task(conn, card)
        insert_task_learning_event(conn, task_id, "dependency.add", f"blocked by {dependency}")


def task_remove_dependency(conn: sqlite3.Connection, task_id: str, dependency: str) -> None:
    if not task_exists(conn, task_id):
        fail(f"Unknown task: {task_id}")

    def mutate(card: dict[str, Any]) -> None:
        dependencies = card.get("dependencies") or []
        if not isinstance(dependencies, list):
            dependencies = [str(dependencies)]
        card["dependencies"] = [str(item) for item in dependencies if str(item) != dependency]

    update_task_raw(conn, task_id, mutate)
    add_task_event(conn, task_id, "dependency.remove", f"removed dependency {dependency}")


def task_list_dependencies(conn: sqlite3.Connection, task_id: str) -> None:
    if not task_exists(conn, task_id):
        fail(f"Unknown task: {task_id}")
    for row in conn.execute(
        "SELECT dependency FROM task_dependencies WHERE task_id = ? ORDER BY dependency",
        (task_id,),
    ):
        dependency = row["dependency"]
        state = dependency_state(conn, dependency)
        if state is None:
            print(f"{dependency}\treference\tnon-blocking")
            continue
        kind, status = state
        resolved = "resolved" if dependency_resolved(kind, status) else "unresolved"
        print(f"{dependency}\t{kind}:{status}\t{resolved}")


def status(conn: sqlite3.Connection, show_all: bool) -> None:
    print("config:")
    list_config(conn)
    telemetry = list(conn.execute(
        """
        SELECT r.id, r.worker, r.attempt, r.status, r.heartbeat_at,
               c.state,
               (SELECT MAX(progress_at) FROM run_checkins WHERE run_id = r.id) AS progress_at,
               c.progress_summary, c.next_action,
               c.expected_next_at, c.blocker, c.created_at
        FROM runs r
        LEFT JOIN run_checkins c ON c.id = (
            SELECT latest.id FROM run_checkins latest
            WHERE latest.run_id = r.id ORDER BY latest.created_at DESC, latest.id DESC LIMIT 1
        )
        WHERE r.status = 'active'
        ORDER BY r.id
        """
    ))
    if telemetry:
        timestamp = now()
        print("\nWorker telemetry")
        for row in telemetry:
            heartbeat_age = "unknown" if row["heartbeat_at"] is None else str(max(0, timestamp - row["heartbeat_at"])) + "s"
            progress_age = "unknown" if row["progress_at"] is None else str(max(0, timestamp - row["progress_at"])) + "s"
            state = row["state"] or "unreported"
            detail = row["progress_summary"] or "no check-in recorded"
            print(
                f"- run={row['id']} worker={row['worker']} attempt={row['attempt']} "
                f"state={state} heartbeat_age={heartbeat_age} progress_age={progress_age} "
                f"progress={detail[:160]}"
            )
            if row["next_action"]:
                print(f"  next={row['next_action'][:160]}")
            if row["expected_next_at"]:
                print(f"  expected_next_at={row['expected_next_at']}")
            if row["blocker"]:
                print(f"  blocker={row['blocker'][:160]}")
    for column in column_names(conn):
        rows = list(
            conn.execute(
                """
                SELECT id, owner, goal, validation_status
                FROM tasks
                WHERE column_name = ?
                ORDER BY id
                """,
                (column,),
            )
        )
        if not rows and not show_all:
            continue
        print(f"\n{column} ({len(rows)})")
        for row in rows:
            goal = (row["goal"] or "").replace("\n", " ")
            suffix = f" | validation={row['validation_status']}" if row["validation_status"] else ""
            print(f"- {row['id']} | owner={row['owner']}{suffix} | {goal[:140]}")


def list_tasks(conn: sqlite3.Connection, column: str | None, theme: str | None) -> None:
    sql = "SELECT DISTINCT t.id, t.column_name, t.owner, t.goal FROM tasks t"
    params: list[Any] = []
    where: list[str] = []
    if column:
        require_column(conn, column)
    if theme:
        sql += " JOIN task_themes tt ON tt.task_id = t.id"
        where.append("tt.theme = ?")
        params.append(theme)
    if column:
        where.append("t.column_name = ?")
        params.append(column)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += """
        ORDER BY COALESCE((SELECT c.position FROM columns c WHERE c.name = t.column_name), 9999),
                 t.column_name,
                 t.id
    """
    for row in conn.execute(sql, params):
        print(f"{row['column_name']}\t{row['id']}\t{row['owner']}\t{(row['goal'] or '')[:120]}")


def show_task(conn: sqlite3.Connection, task_id: str) -> None:
    row = conn.execute("SELECT raw_json FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        fail(f"Unknown task: {task_id}")
    print(json.dumps(json_loads(row["raw_json"]), indent=2, sort_keys=True))


def add_task(
    conn: sqlite3.Connection,
    task_id: str,
    goal: str,
    column: str,
    owner: str,
    scope: str | None,
    themes: list[str],
    dependencies: list[str],
    intent_links: list[str],
    exit_criteria: list[str],
    validation: list[str],
    plan: str | None,
) -> None:
    require_column(conn, column)
    if not task_id.strip() or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", task_id):
        fail("Task id must contain lowercase letters, digits, and hyphens")
    if not goal.strip():
        fail("Task goal cannot be empty")
    if not owner.strip():
        fail("Task owner cannot be empty")
    if not intent_links:
        fail("Task creation requires at least one intent link")
    if any(conn.execute("SELECT 1 FROM intents WHERE id = ?", (intent_id,)).fetchone() is None for intent_id in intent_links):
        fail("All task intent links must reference existing intents")
    if task_exists(conn, task_id):
        fail(f"Task already exists: {task_id}")

    card: dict[str, Any] = {
        "id": task_id,
        "column": column,
        "owner": owner,
        "scope": scope or "",
        "goal": goal,
        "themes": themes,
        "dependencies": dependencies,
        "intent_links": intent_links,
        "exit_criteria": exit_criteria,
        "validation": {"required": validation, "status": "not_started"},
        "plan": {"summary": plan} if plan else {},
        "blocker": "none",
    }
    if column == "Ready":
        if owner == "unassigned":
            fail("Ready task requires an assigned worker")
        required = {"scope": card["scope"], "exit_criteria": exit_criteria, "validation": validation}
        missing = [name for name, value in required.items() if not value]
        if missing:
            fail("Ready task requires: " + ", ".join(missing))

    with write_transaction(conn):
        upsert_task(conn, card)
        for intent_id in intent_links:
            conn.execute(
                "INSERT OR IGNORE INTO intent_work_links(intent_id, task_id) VALUES(?, ?)",
                (intent_id, task_id),
            )
        insert_task_learning_event(conn, task_id, "created", "Created with task add")
    print(f"created task {task_id}")


def list_backlog(conn: sqlite3.Connection) -> None:
    for row in conn.execute("SELECT id, summary, status FROM backlog_ideas ORDER BY id"):
        status = row["status"] or ""
        print(f"{row['id']}\t{status}\t{row['summary'] or ''}")


def add_backlog(conn: sqlite3.Connection, idea_id: str, summary: str, themes: list[str]) -> None:
    idea = {"id": idea_id, "summary": summary, "themes": themes, "status": "new", "dependencies": []}
    with write_transaction(conn):
        conn.execute(
            """
            INSERT INTO backlog_ideas(id, summary, status, themes_json, raw_json, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                summary=excluded.summary,
                themes_json=excluded.themes_json,
                raw_json=excluded.raw_json,
                updated_at=excluded.updated_at
            """,
            (idea_id, summary, "new", json_dumps(themes), json_dumps(idea), now()),
        )


def require_backlog_idea(conn: sqlite3.Connection, idea_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT id, summary, status, themes_json, raw_json FROM backlog_ideas WHERE id = ?",
        (idea_id,),
    ).fetchone()
    if row is None:
        fail(f"Unknown backlog idea: {idea_id}")
    return row


def update_backlog(
    conn: sqlite3.Connection,
    idea_id: str,
    status_value: str | None,
    summary: str | None,
    reason: str | None,
    note: str | None,
) -> None:
    if status_value is not None:
        require_backlog_status(status_value)
    if summary is not None and not summary.strip():
        fail("Backlog summary cannot be empty")
    if status_value in {"done", "rejected", "deferred"} and not reason:
        fail(f"Backlog status {status_value} requires --reason")
    with write_transaction(conn):
        row = require_backlog_idea(conn, idea_id)
        raw = json_loads(row["raw_json"], {})
        if not isinstance(raw, dict):
            raw = {"id": idea_id}
        new_summary = summary if summary is not None else row["summary"]
        new_status = status_value if status_value is not None else row["status"]
        raw["id"] = idea_id
        raw["summary"] = new_summary
        raw["status"] = new_status
        if reason:
            if new_status == "done":
                raw["completion"] = reason
            elif new_status == "rejected":
                raw["decision"] = reason
            elif new_status == "deferred":
                raw["decision"] = reason
            else:
                raw["reason"] = reason
        if note:
            notes = raw.setdefault("notes", [])
            if not isinstance(notes, list):
                notes = [str(notes)]
                raw["notes"] = notes
            notes.append({"text": note, "created_at": now()})
        themes = json_loads(row["themes_json"], [])
        conn.execute(
            """
            UPDATE backlog_ideas
            SET summary = ?, status = ?, themes_json = ?, raw_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_summary, new_status, json_dumps(themes), json_dumps(raw), now(), idea_id),
        )


def show_backlog(conn: sqlite3.Connection, idea_id: str) -> None:
    row = require_backlog_idea(conn, idea_id)
    print(json.dumps(json_loads(row["raw_json"], {}), indent=2, sort_keys=True))


def backlog_update_raw(conn: sqlite3.Connection, idea_id: str, mutate: Any) -> None:
    with write_transaction(conn):
        row = require_backlog_idea(conn, idea_id)
        idea = json_loads(row["raw_json"], {})
        if not isinstance(idea, dict):
            idea = {"id": idea_id}
        mutate(idea)
        status = str(idea.get("status") or row["status"] or "new")
        require_backlog_status(status)
        summary = scalar_text(idea.get("summary")) or row["summary"]
        themes = idea.get("themes") or json_loads(row["themes_json"], [])
        if not isinstance(themes, list):
            themes = [str(themes)]
        conn.execute(
            """
            UPDATE backlog_ideas
            SET summary = ?, status = ?, themes_json = ?, raw_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (summary, status, json_dumps(themes), json_dumps(idea), now(), idea_id),
        )


def backlog_add_dependency(conn: sqlite3.Connection, idea_id: str, dependency: str) -> None:
    if not backlog_exists(conn, idea_id):
        fail(f"Unknown backlog idea: {idea_id}")
    if dependency == idea_id:
        fail("Backlog idea cannot depend on itself")

    def mutate(idea: dict[str, Any]) -> None:
        dependencies = idea.setdefault("dependencies", [])
        if not isinstance(dependencies, list):
            dependencies = [str(dependencies)]
            idea["dependencies"] = dependencies
        if dependency not in [str(item) for item in dependencies]:
            dependencies.append(dependency)

    backlog_update_raw(conn, idea_id, mutate)


def backlog_remove_dependency(conn: sqlite3.Connection, idea_id: str, dependency: str) -> None:
    def mutate(idea: dict[str, Any]) -> None:
        dependencies = idea.get("dependencies") or []
        if not isinstance(dependencies, list):
            dependencies = [str(dependencies)]
        idea["dependencies"] = [str(item) for item in dependencies if str(item) != dependency]

    backlog_update_raw(conn, idea_id, mutate)


def backlog_list_dependencies(conn: sqlite3.Connection, idea_id: str) -> None:
    row = require_backlog_idea(conn, idea_id)
    idea = json_loads(row["raw_json"], {})
    for dependency in idea.get("dependencies") or []:
        dependency = str(dependency)
        state = dependency_state(conn, dependency)
        if state is None:
            print(f"{dependency}\treference\tnon-blocking")
            continue
        kind, status = state
        resolved = "resolved" if dependency_resolved(kind, status) else "unresolved"
        print(f"{dependency}\t{kind}:{status}\t{resolved}")


def set_priority(raw: dict[str, Any], value: int, reason: str) -> None:
    raw["priority_rank"] = value
    raw["priority"] = f"rank {value}: {reason}"
    history = raw.setdefault("priority_history", [])
    if not isinstance(history, list):
        history = [str(history)]
        raw["priority_history"] = history
    history.append({"rank": value, "reason": reason, "created_at": now()})


def backlog_set_priority(conn: sqlite3.Connection, idea_id: str, value: int, reason: str) -> None:
    if value < 0:
        fail("Priority value must be non-negative")
    row = require_backlog_idea(conn, idea_id)
    if row["status"] not in {"new", "ready"}:
        fail("Backlog priority can only be changed for new or ready ideas")

    def mutate(idea: dict[str, Any]) -> None:
        set_priority(idea, value, reason)

    backlog_update_raw(conn, idea_id, mutate)


def backlog_bump_priority(conn: sqlite3.Connection, idea_id: str, reason: str) -> None:
    row = require_backlog_idea(conn, idea_id)
    raw = json_loads(row["raw_json"], {})
    current = raw.get("priority_rank")
    value = int(current) - 1 if isinstance(current, int) and current > 0 else 0
    backlog_set_priority(conn, idea_id, value, reason)


def task_set_priority(conn: sqlite3.Connection, task_id: str, value: int, reason: str) -> None:
    if value < 0:
        fail("Priority value must be non-negative")
    with write_transaction(conn):
        row = conn.execute("SELECT column_name, raw_json FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            fail(f"Unknown task: {task_id}")
        if row["column_name"] != "Ready":
            fail("Task priority can only be changed for Ready tasks")
        card = json_loads(row["raw_json"])
        set_priority(card, value, reason)
        upsert_task(conn, card)


def task_bump_priority(conn: sqlite3.Connection, task_id: str, reason: str) -> None:
    row = conn.execute("SELECT raw_json FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        fail(f"Unknown task: {task_id}")
    raw = json_loads(row["raw_json"], {})
    current = raw.get("priority_rank")
    value = int(current) - 1 if isinstance(current, int) and current > 0 else 0
    task_set_priority(conn, task_id, value, reason)


def add_clarification(conn: sqlite3.Connection, task_id: str | None, question: str, default: str | None) -> None:
    with write_transaction(conn):
        conn.execute(
            """
            INSERT INTO clarifications(task_id, question, default_answer, created_at)
            VALUES(?, ?, ?, ?)
            """,
            (task_id, question, default, now()),
        )


def answer_clarification(conn: sqlite3.Connection, clarification_id: int, answer: str) -> None:
    with write_transaction(conn):
        row = conn.execute(
            "SELECT status FROM clarifications WHERE id = ?", (clarification_id,)
        ).fetchone()
        if row is None:
            fail(f"Unknown clarification: {clarification_id}")
        if row["status"] != "open":
            fail(f"Clarification {clarification_id} is already {row['status']}")
        conn.execute(
            "UPDATE clarifications SET status = 'resolved', answer = ?, resolved_at = ? WHERE id = ?",
            (answer, now(), clarification_id),
        )


def capture_goal(
    conn: sqlite3.Connection,
    intent_id: str,
    objective: str,
    kind: str,
    success_criteria: list[str],
    constraints: list[str],
    non_goals: list[str],
    autonomy: str,
    stop_conditions: list[str],
) -> None:
    require_intent_kind(kind)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", intent_id):
        fail("Goal id must contain lowercase letters, digits, and hyphens")
    if not objective.strip():
        fail("Goal objective cannot be empty")
    if conn.execute("SELECT 1 FROM intents WHERE id = ?", (intent_id,)).fetchone():
        fail(f"Intent already exists: {intent_id}")
    timestamp = now()
    raw = {
        "id": intent_id,
        "summary": objective,
        "kind": kind,
        "state": "captured",
        "goal_contract": {
            "objective": objective,
            "success_criteria": success_criteria,
            "constraints": constraints,
            "non_goals": non_goals,
            "autonomy": autonomy,
            "stop_conditions": stop_conditions,
        },
    }
    with write_transaction(conn):
        conn.execute(
            "INSERT INTO intents(id, summary, kind, state, raw_json, created_at, updated_at) "
            "VALUES(?, ?, ?, 'captured', ?, ?, ?)",
            (intent_id, objective, kind, json_dumps(raw), timestamp, timestamp),
        )
    print(f"captured goal {intent_id}")


def decision_add(
    conn: sqlite3.Connection,
    decision_id: str,
    question: str,
    intent_id: str | None,
    task_id: str | None,
    options: list[str],
    default_option: str | None,
    impact: str | None,
) -> None:
    with write_transaction(conn):
        conn.execute(
            "INSERT INTO decisions(id, intent_id, task_id, question, options_json, default_option, impact, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (decision_id, intent_id, task_id, question, json_dumps(options), default_option, impact, now()),
        )
    print(f"created decision {decision_id}")


def decision_list(conn: sqlite3.Connection, status_filter: str | None) -> None:
    sql = "SELECT id, status, intent_id, task_id, question, default_option FROM decisions"
    params: list[Any] = []
    if status_filter:
        sql += " WHERE status = ?"
        params.append(status_filter)
    sql += " ORDER BY created_at, id"
    for row in conn.execute(sql, params):
        target = row["task_id"] or row["intent_id"] or "-"
        default = f" | default={row['default_option']}" if row["default_option"] else ""
        print(f"{row['status']}\t{row['id']}\t{target}\t{row['question']}{default}")


def decision_resolve(
    conn: sqlite3.Connection,
    decision_id: str,
    answer: str,
    rationale: str,
    decided_by: str,
) -> None:
    with write_transaction(conn):
        row = conn.execute(
            "SELECT status, options_json FROM decisions WHERE id = ?", (decision_id,)
        ).fetchone()
        if row is None:
            fail(f"Unknown decision: {decision_id}")
        conn.execute(
            "UPDATE decisions SET status = 'resolved', answer = ?, rationale = ?, decided_by = ?, resolved_at = ? WHERE id = ?",
            (answer, rationale, decided_by, now(), decision_id),
        )
    print(f"resolved decision {decision_id}")


def list_clarifications(conn: sqlite3.Connection, status_filter: str | None) -> None:
    sql = "SELECT id, task_id, status, question, default_answer FROM clarifications"
    params: list[Any] = []
    if status_filter:
        sql += " WHERE status = ?"
        params.append(status_filter)
    sql += " ORDER BY id"
    for row in conn.execute(sql, params):
        default = f" | default={row['default_answer']}" if row["default_answer"] else ""
        print(f"{row['id']}\t{row['status']}\t{row['task_id'] or '-'}\t{row['question']}{default}")


def add_principle(
    conn: sqlite3.Connection,
    theme: str,
    principle_id: str,
    statement: str,
    intended_outcome: str,
    authority_class: str,
    rationale: str,
    reference_ids: list[str],
) -> None:
    raw = {"id": principle_id, "statement": statement, "status": "active", "applies_to": [], "exceptions": []}
    with write_transaction(conn):
        if conn.execute("SELECT 1 FROM principles WHERE id = ?", (principle_id,)).fetchone():
            fail("Principle already exists; create a new version instead of overwriting history")
        conn.execute(
            """
            INSERT INTO principles(id, theme, statement, status, raw_json, updated_at)
            VALUES(?, ?, ?, 'active', ?, ?)
            """,
            (principle_id, theme, statement, json_dumps(raw), now()),
        )
        conn.execute(
            "INSERT INTO principle_versions(principle_id, version, statement, intended_outcome, scope_type, "
            "authority_class, rationale, status, effective_at, created_at) "
            "VALUES(?, 1, ?, ?, 'project', ?, ?, 'active', ?, ?)",
            (principle_id, statement, intended_outcome, authority_class, rationale, now(), now()),
        )
        for reference_id in reference_ids:
            conn.execute(
                "INSERT INTO principle_references(principle_id, principle_version, reference_id, relationship, interpretation) "
                "VALUES(?, 1, ?, 'supports', ?)",
                (principle_id, reference_id, rationale),
            )


def list_principles(conn: sqlite3.Connection) -> None:
    for row in conn.execute(
        "SELECT p.theme, p.id, v.status, v.version, v.statement, v.intended_outcome, v.authority_class "
        "FROM principles p JOIN principle_versions v ON v.principle_id = p.id "
        "WHERE v.version = (SELECT MAX(v2.version) FROM principle_versions v2 WHERE v2.principle_id = p.id) "
        "ORDER BY p.theme, p.id"
    ):
        print(f"{row['theme']}\t{row['id']}\t{row['status']}\t{row['statement']}")


def enrollment_list(conn: sqlite3.Connection, intent_id: str) -> None:
    for row in conn.execute(
        "SELECT e.*, c.title FROM project_specialist_enrollments e JOIN specialist_classes c "
        "ON c.id=e.specialist_class_id WHERE e.intent_id=? ORDER BY e.specialist_class_id",
        (intent_id,),
    ):
        print(json.dumps(dict(row), sort_keys=True))


def guidance_proposal_list(conn: sqlite3.Connection, intent_id: str, status: str | None) -> None:
    sql = "SELECT * FROM specialist_guidance_proposals WHERE intent_id=?"
    params: list[Any] = [intent_id]
    if status:
        sql += " AND status=?"
        params.append(status)
    for row in conn.execute(sql + " ORDER BY created_at, id", params):
        print(json.dumps(dict(row), sort_keys=True))


def guidance_proposal_resolve(
    conn: sqlite3.Connection, proposal_id: str, status: str,
    adopted_id: str | None, decision_id: str | None,
) -> None:
    with write_transaction(conn):
        row = conn.execute(
            "SELECT guidance_kind FROM specialist_guidance_proposals WHERE id=? AND status='proposed'",
            (proposal_id,),
        ).fetchone()
        if row is None:
            fail("Unknown or already resolved guidance proposal")
        if status == "accepted" and not adopted_id:
            fail("Accepted guidance requires the adopted principle or tenet id")
        if status == "rejected" and not decision_id:
            fail("Rejected specialist guidance requires an attributable decision")
        if status == "accepted":
            target_table = "principles" if row["guidance_kind"] == "principle" else "tenets"
            if conn.execute(f"SELECT 1 FROM {target_table} WHERE id=?", (adopted_id,)).fetchone() is None:
                fail(f"Adopted {row['guidance_kind']} must be stored before resolving its proposal")
        conn.execute(
            "UPDATE specialist_guidance_proposals SET status=?, adopted_principle_id=?, adopted_tenet_id=?, "
            "decision_id=?, updated_at=? WHERE id=?",
            (status, adopted_id if row["guidance_kind"] == "principle" else None,
             adopted_id if row["guidance_kind"] == "tenet" else None,
             decision_id, now(), proposal_id),
        )
    print(f"resolved guidance proposal {proposal_id} status={status}")


def codebase_review_start(
    conn: sqlite3.Connection, review_id: str, intent_id: str,
    scope: str, objective: str, owner: str,
) -> None:
    add_task(
        conn, review_id, objective, "Backlog", owner, scope,
        ["existing-codebase-review"], [], [intent_id],
        ["Every enrolled specialist returned findings or an attributable not-applicable disposition",
         "Risks and deficiencies are linked to the project goal and follow-up work"],
        ["frozen all-specialist review plan", "revision-bound codebase evidence"],
        "Review existing work against the project goal and effective project guidance",
    )
    review_profile_set(
        conn, review_id, "existing-codebase-review", "Verify",
        ["source-code", "repository"], ["existing-work", "goal-fit"],
        "coordinator", "User requested a comprehensive existing-codebase review",
    )
    review_plan_create(conn, f"{review_id}-plan", review_id, "standard-excellence", 1)
    print(f"started all-specialist codebase review {review_id}")


def bug_register(
    conn: sqlite3.Connection, bug_id: str, intent_id: str, summary: str,
    observed: str, expected: str, reporter: str, reproduction: str | None,
    environment: str | None, evidence: list[str],
) -> None:
    timestamp = now()
    with write_transaction(conn):
        conn.execute(
            "INSERT INTO bugs(id, intent_id, summary, observed_behavior, expected_behavior, reproduction, environment, "
            "evidence_json, reporter, status, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 'registered', ?, ?)",
            (bug_id, intent_id, summary, observed, expected, reproduction, environment,
             json_dumps(evidence), reporter, timestamp, timestamp),
        )
    print(f"registered bug {bug_id}")


def bug_assess(
    conn: sqlite3.Connection, bug_id: str, class_id: str, applicability: str,
    rationale: str, assessed_by: str, goal_impact: int | None,
    urgency: int | None, risk_summary: str | None,
) -> None:
    with write_transaction(conn):
        cursor = conn.execute(
            "UPDATE bug_specialist_assessments SET applicability=?, goal_impact=?, urgency=?, risk_summary=?, "
            "rationale=?, assessed_by=?, assessed_at=? WHERE bug_id=? AND specialist_class_id=? AND applicability='pending'",
            (applicability, goal_impact, urgency, risk_summary, rationale, assessed_by, now(), bug_id, class_id),
        )
        if cursor.rowcount != 1:
            fail("Unknown, unassigned, or already assessed bug specialist disposition")
        conn.execute("UPDATE bugs SET status='triaging', updated_at=? WHERE id=? AND status='registered'", (now(), bug_id))
    print(f"assessed bug {bug_id} class={class_id} applicability={applicability}")


def bug_prioritize(conn: sqlite3.Connection, bug_id: str, rank: int, rationale: str) -> None:
    if rank < 0:
        fail("Bug priority rank must be non-negative")
    with write_transaction(conn):
        cursor = conn.execute(
            "UPDATE bugs SET priority_rank=?, priority_rationale=?, status='prioritized', updated_at=? WHERE id=?",
            (rank, rationale, now(), bug_id),
        )
        if cursor.rowcount != 1:
            fail(f"Unknown bug: {bug_id}")
    print(f"prioritized bug {bug_id} rank={rank}")


def bug_action(conn: sqlite3.Connection, bug_id: str, task_id: str, owner: str) -> None:
    bug = conn.execute("SELECT * FROM bugs WHERE id=? AND status='prioritized'", (bug_id,)).fetchone()
    if bug is None:
        fail("Bug must be prioritized before actioning")
    add_task(
        conn, task_id, f"Correct bug: {bug['summary']}", "Backlog", owner,
        f"Observed: {bug['observed_behavior']} Expected: {bug['expected_behavior']}",
        ["bug", bug_id], [], [bug["intent_id"]],
        [bug["expected_behavior"], "Regression evidence prevents recurrence"],
        ["reproduction fails before correction", "regression and affected-scope tests pass"],
        f"Correct {bug_id} at the earliest responsible stage",
    )
    with write_transaction(conn):
        row = conn.execute("SELECT raw_json FROM tasks WHERE id=?", (task_id,)).fetchone()
        card = json_loads(row["raw_json"])
        set_priority(card, bug["priority_rank"], f"Bug priority: {bug['priority_rationale']}")
        upsert_task(conn, card)
        conn.execute(
            "UPDATE bugs SET status='actioned', action_task_id=?, updated_at=? WHERE id=?",
            (task_id, now(), bug_id),
        )
    print(f"actioned bug {bug_id} as task {task_id}")


def bug_list(conn: sqlite3.Connection, intent_id: str | None) -> None:
    sql = "SELECT id, intent_id, status, priority_rank, summary, action_task_id FROM bugs"
    params: tuple[Any, ...] = ()
    if intent_id:
        sql += " WHERE intent_id=?"
        params = (intent_id,)
    for row in conn.execute(sql + " ORDER BY COALESCE(priority_rank, 2147483647), created_at", params):
        print(json.dumps(dict(row), sort_keys=True))


def bug_show(conn: sqlite3.Connection, bug_id: str) -> None:
    row = conn.execute("SELECT * FROM bugs WHERE id=?", (bug_id,)).fetchone()
    if row is None:
        fail(f"Unknown bug: {bug_id}")
    print(json.dumps(dict(row), sort_keys=True))
    for assessment in conn.execute(
        "SELECT * FROM bug_specialist_assessments WHERE bug_id=? ORDER BY specialist_class_id",
        (bug_id,),
    ):
        print(json.dumps(dict(assessment), sort_keys=True))


def tenet_list(conn: sqlite3.Connection) -> None:
    for row in conn.execute(
        "SELECT t.id, t.theme, t.title, t.current_version, v.strength, v.status, v.instruction "
        "FROM tenets t JOIN tenet_versions v ON v.tenet_id=t.id AND v.version=t.current_version "
        "ORDER BY t.theme, t.id"
    ):
        print(json.dumps(dict(row), sort_keys=True))


def tenet_add_version(
    conn: sqlite3.Connection, tenet_id: str, theme: str, title: str,
    instruction: str, intended_effect: str, strength: str,
    exception_authority: str, verification: str, principle_ids: list[str],
    reference_ids: list[str], experiment_eligible: bool, version_status: str,
) -> None:
    timestamp = now()
    with write_transaction(conn):
        current = conn.execute("SELECT current_version FROM tenets WHERE id=?", (tenet_id,)).fetchone()
        latest = conn.execute("SELECT MAX(version) AS version FROM tenet_versions WHERE tenet_id=?", (tenet_id,)).fetchone()
        version = 1 if latest is None or latest["version"] is None else latest["version"] + 1
        if current is None:
            conn.execute(
                "INSERT INTO tenets(id, theme, title, current_version, active, created_at, updated_at) "
                "VALUES(?, ?, ?, 1, 1, ?, ?)",
                (tenet_id, theme, title, timestamp, timestamp),
            )
        elif version_status == "active":
            conn.execute(
                "UPDATE tenet_versions SET status='superseded', superseded_at=? "
                "WHERE tenet_id=? AND version=? AND status='active'",
                (timestamp, tenet_id, current["current_version"]),
            )
            conn.execute(
                "UPDATE tenets SET theme=?, title=?, current_version=?, updated_at=? WHERE id=?",
                (theme, title, version, timestamp, tenet_id),
            )
        conn.execute(
            "INSERT INTO tenet_versions(tenet_id, version, instruction, intended_effect, strength, "
            "exception_authority, verification_strategy, experiment_eligible, status, effective_at, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tenet_id, version, instruction, intended_effect, strength, exception_authority,
             verification, int(experiment_eligible), version_status, timestamp if version_status == "active" else None, timestamp),
        )
        for principle_id in principle_ids:
            principle = conn.execute(
                "SELECT MAX(version) AS version FROM principle_versions WHERE principle_id=? AND status='active'",
                (principle_id,),
            ).fetchone()
            if principle is None or principle["version"] is None:
                fail(f"Unknown active principle: {principle_id}")
            conn.execute(
                "INSERT INTO tenet_principles(tenet_id, tenet_version, principle_id, principle_version) VALUES(?, ?, ?, ?)",
                (tenet_id, version, principle_id, principle["version"]),
            )
        for reference_id in reference_ids:
            conn.execute(
                "INSERT INTO tenet_references(tenet_id, tenet_version, reference_id, relationship, interpretation) "
                "VALUES(?, ?, ?, 'supports', ?)",
                (tenet_id, version, reference_id, intended_effect),
            )
    print(f"stored tenet {tenet_id} version={version}")


def tenet_override_add(
    conn: sqlite3.Connection, override_id: str, tenet_id: str, disposition: str,
    scope_json: str, rationale: str, authorized_by: str,
    decision_id: str | None, expires_at: int | None, rollback_condition: str | None,
) -> None:
    scope = json.loads(scope_json)
    if not isinstance(scope, dict):
        fail("Tenet override scope must be a JSON object")
    row = conn.execute("SELECT current_version FROM tenets WHERE id=? AND active=1", (tenet_id,)).fetchone()
    if row is None:
        fail(f"Unknown active tenet: {tenet_id}")
    with write_transaction(conn):
        conn.execute(
            "INSERT INTO project_tenet_overrides(id, tenet_id, tenet_version, disposition, scope_json, rationale, "
            "decision_id, authorized_by, effective_at, expires_at, rollback_condition, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (override_id, tenet_id, row["current_version"], disposition, json_dumps(scope), rationale,
             decision_id, authorized_by, now(), expires_at, rollback_condition, now()),
        )
    print(f"stored tenet override {override_id}")


def experiment_add(
    conn: sqlite3.Connection, experiment_id: str, principle_id: str,
    baseline_tenet: str, variant_tenet: str, problem: str, hypothesis: str,
    scope_json: str, exclusions_json: str, metrics_json: str, owner: str,
    rollback_condition: str,
) -> None:
    documents = [json.loads(value) for value in (scope_json, exclusions_json, metrics_json)]
    if not isinstance(documents[0], dict) or not isinstance(documents[1], list) or not isinstance(documents[2], list):
        fail("Experiment scope must be an object; exclusions and metrics must be arrays")
    baseline = conn.execute("SELECT current_version FROM tenets WHERE id=?", (baseline_tenet,)).fetchone()
    variant = conn.execute("SELECT MAX(version) AS version FROM tenet_versions WHERE tenet_id=?", (variant_tenet,)).fetchone()
    if baseline is None or variant is None or variant["version"] is None:
        fail("Experiment requires known baseline and variant tenets")
    variant_status = conn.execute(
        "SELECT status FROM tenet_versions WHERE tenet_id=? AND version=?",
        (variant_tenet, variant["version"]),
    ).fetchone()["status"]
    if variant_status != "draft":
        fail("Experiment variant must be a draft tenet version so it cannot affect unassigned work")
    versions = {baseline_tenet: baseline["current_version"], variant_tenet: variant["version"]}
    with write_transaction(conn):
        conn.execute(
            "INSERT INTO improvement_experiments(id, principle_id, baseline_tenet_id, baseline_tenet_version, "
            "variant_tenet_id, variant_tenet_version, problem_statement, hypothesis, assignment_scope_json, "
            "exclusions_json, metrics_json, owner, status, rollback_condition, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)",
            (experiment_id, principle_id, baseline_tenet, versions[baseline_tenet], variant_tenet,
             versions[variant_tenet], problem, hypothesis, json_dumps(documents[0]), json_dumps(documents[1]),
             json_dumps(documents[2]), owner, rollback_condition, now()),
        )
    print(f"created improvement experiment {experiment_id}")


def experiment_status(
    conn: sqlite3.Connection, experiment_id: str, status: str,
    outcome: str | None, decision_id: str | None,
) -> None:
    if status in {"promoted", "revised", "rolled-back", "cancelled"} and not decision_id:
        fail("A terminal experiment decision requires --decision")
    timestamp = now()
    with write_transaction(conn):
        cursor = conn.execute(
            "UPDATE improvement_experiments SET status=?, outcome=COALESCE(?, outcome), decision_id=COALESCE(?, decision_id), "
            "observation_start=CASE WHEN ?='running' AND observation_start IS NULL THEN ? ELSE observation_start END, "
            "observation_end=CASE WHEN ? IN ('promoted','revised','rolled-back','cancelled') THEN ? ELSE observation_end END "
            "WHERE id=?",
            (status, outcome, decision_id, status, timestamp, status, timestamp, experiment_id),
        )
        if cursor.rowcount != 1:
            fail(f"Unknown experiment: {experiment_id}")
    print(f"set experiment {experiment_id} status={status}")


def experiment_assign(conn: sqlite3.Connection, experiment_id: str, task_id: str, arm: str) -> None:
    with write_transaction(conn):
        experiment = conn.execute(
            "SELECT status FROM improvement_experiments WHERE id=?", (experiment_id,)
        ).fetchone()
        if experiment is None or experiment["status"] != "running":
            fail("Assignments require a running experiment")
        if conn.execute("SELECT 1 FROM guidance_snapshots WHERE task_id=?", (task_id,)).fetchone():
            fail("Assign the experiment before freezing task guidance")
        conn.execute(
            "INSERT INTO experiment_assignments(experiment_id, task_id, arm, assigned_at) VALUES(?, ?, ?, ?)",
            (experiment_id, task_id, arm, now()),
        )
    print(f"assigned task {task_id} to {experiment_id}/{arm}")


def flow_constraint_set(
    conn: sqlite3.Connection, constraint_id: str, goal_ref: str,
    constraint_type: str, constraint_ref: str, evidence: str,
    exploit: str, subordinate: str, owner: str,
    elevate: str | None, buffer_target: float | None,
    buffer_current: float | None, review_at: int | None,
) -> None:
    timestamp = now()
    with write_transaction(conn):
        conn.execute(
            "UPDATE flow_constraints SET status='superseded', updated_at=? WHERE goal_ref=? AND status='active' AND id<>?",
            (timestamp, goal_ref, constraint_id),
        )
        conn.execute(
            "INSERT INTO flow_constraints(id, goal_ref, constraint_type, constraint_ref, evidence_summary, "
            "buffer_target, buffer_current, exploit_action, subordinate_action, elevate_action, owner, status, "
            "review_at, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET evidence_summary=excluded.evidence_summary, buffer_target=excluded.buffer_target, "
            "buffer_current=excluded.buffer_current, exploit_action=excluded.exploit_action, "
            "subordinate_action=excluded.subordinate_action, elevate_action=excluded.elevate_action, owner=excluded.owner, "
            "status='active', review_at=excluded.review_at, updated_at=excluded.updated_at",
            (constraint_id, goal_ref, constraint_type, constraint_ref, evidence, buffer_target, buffer_current,
             exploit, subordinate, elevate, owner, review_at, timestamp, timestamp),
        )
    print(f"set active flow constraint {constraint_id}")


def quality_signal_open(
    conn: sqlite3.Connection, signal_id: str, task_id: str, signal_type: str,
    severity: str, summary: str, containment: str, owner: str,
    obligation_id: str | None,
) -> None:
    with write_transaction(conn):
        conn.execute(
            "INSERT INTO quality_signals(id, task_id, obligation_id, signal_type, severity, summary, containment, "
            "owner, status, opened_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)",
            (signal_id, task_id, obligation_id, signal_type, severity, summary, containment, owner, now()),
        )
    print(f"opened quality signal {signal_id}")


def quality_signal_resolve(
    conn: sqlite3.Connection, signal_id: str, occurrence_cause: str,
    escape_cause: str, systemic_cause: str, countermeasure: str,
    recurrence_test: str,
) -> None:
    with write_transaction(conn):
        cursor = conn.execute(
            "UPDATE quality_signals SET occurrence_cause=?, escape_cause=?, systemic_cause=?, countermeasure=?, "
            "recurrence_test=?, status='resolved', resolved_at=? WHERE id=? AND status IN ('open', 'contained')",
            (occurrence_cause, escape_cause, systemic_cause, countermeasure, recurrence_test, now(), signal_id),
        )
        if cursor.rowcount == 0:
            fail(f"Unknown or resolved quality signal: {signal_id}")
    print(f"resolved quality signal {signal_id}")


def guidance_show(conn: sqlite3.Connection, snapshot_id: str) -> None:
    row = conn.execute("SELECT * FROM guidance_snapshots WHERE id = ?", (snapshot_id,)).fetchone()
    if row is None:
        fail(f"Unknown guidance snapshot: {snapshot_id}")
    print(json.dumps(dict(row), sort_keys=True))
    for item in conn.execute(
        "SELECT s.*, v.instruction, v.intended_effect, v.verification_strategy "
        "FROM guidance_snapshot_tenets s JOIN tenet_versions v "
        "ON v.tenet_id=s.tenet_id AND v.version=s.tenet_version "
        "WHERE s.guidance_snapshot_id=? ORDER BY s.tenet_id",
        (snapshot_id,),
    ):
        print(json.dumps(dict(item), sort_keys=True))
    for obligation in conn.execute(
        "SELECT * FROM assurance_obligations WHERE guidance_snapshot_id=? ORDER BY id",
        (snapshot_id,),
    ):
        print(json.dumps(dict(obligation), sort_keys=True))


def obligation_add(
    conn: sqlite3.Connection, obligation_id: str, snapshot_id: str, tenet_id: str,
    obligation_type: str, summary: str, lifecycle_stage: str,
    verification_method: str, owner: str, artifact: str | None,
    review_plan_item_id: str | None,
) -> None:
    timestamp = now()
    with write_transaction(conn):
        conn.execute(
            "INSERT INTO assurance_obligations(id, guidance_snapshot_id, tenet_id, review_plan_item_id, "
            "obligation_type, summary, affected_artifact, lifecycle_stage, verification_method, owner, status, created_at, updated_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'planned', ?, ?)",
            (obligation_id, snapshot_id, tenet_id, review_plan_item_id, obligation_type,
             summary, artifact, lifecycle_stage, verification_method, owner, timestamp, timestamp),
        )
        conn.execute(
            "UPDATE guidance_snapshot_tenets SET resolution='materialized', applicability_source='specialist', "
            "updated_at=? WHERE guidance_snapshot_id=? AND tenet_id=?",
            (timestamp, snapshot_id, tenet_id),
        )
    print(f"added assurance obligation {obligation_id}")


def obligation_satisfy(conn: sqlite3.Connection, obligation_id: str, evidence_id: str) -> None:
    with write_transaction(conn):
        row = conn.execute(
            "SELECT s.task_id FROM assurance_obligations o JOIN guidance_snapshots s "
            "ON s.id=o.guidance_snapshot_id WHERE o.id=?", (obligation_id,)
        ).fetchone()
        evidence = conn.execute("SELECT task_id, result FROM evidence WHERE id=?", (evidence_id,)).fetchone()
        if row is None or evidence is None or evidence["task_id"] != row["task_id"] or evidence["result"] != "pass":
            fail("Obligation satisfaction requires passing evidence for the same task")
        conn.execute(
            "UPDATE assurance_obligations SET status='satisfied', evidence_id=?, updated_at=? WHERE id=?",
            (evidence_id, now(), obligation_id),
        )
    print(f"satisfied assurance obligation {obligation_id}")


def list_columns(conn: sqlite3.Connection) -> None:
    for row in conn.execute(
        """
        SELECT name, position, direction, active, required_rules_json, description
        FROM columns
        ORDER BY position, name
        """
    ):
        active = "active" if row["active"] else "inactive"
        rules = ", ".join(column_rules(conn, row["name"]))
        description = row["description"] or ""
        print(
            f"{row['position']}\t{row['name']}\t{row['direction']}\t{active}\t{description}\t{rules}"
        )


def add_column(
    conn: sqlite3.Connection,
    name: str,
    position: int,
    description: str | None,
    rules: list[str],
    direction: str,
) -> None:
    if not name:
        fail("Column name is required")
    with write_transaction(conn):
        conn.execute(
            """
            INSERT INTO columns(name, position, description, required_rules_json, direction, active)
            VALUES(?, ?, ?, ?, ?, 1)
            ON CONFLICT(name) DO UPDATE SET
                position=excluded.position,
                description=excluded.description,
                required_rules_json=excluded.required_rules_json,
                direction=excluded.direction,
                active=1
            """,
            (name, position, description, json_dumps(rules), direction),
        )


def list_transitions(conn: sqlite3.Connection) -> None:
    for row in conn.execute(
        """
        SELECT from_column, to_column, rule
        FROM column_transitions
        ORDER BY
            COALESCE((SELECT position FROM columns WHERE name = from_column), 9999),
            from_column,
            COALESCE((SELECT position FROM columns WHERE name = to_column), 9999),
            to_column
        """
    ):
        rule = f"\t{row['rule']}" if row["rule"] else ""
        print(f"{row['from_column']}\t{row['to_column']}{rule}")


def add_transition(conn: sqlite3.Connection, from_column: str, to_column: str, rule: str | None) -> None:
    require_column(conn, from_column)
    require_column(conn, to_column)
    with write_transaction(conn):
        conn.execute(
            """
            INSERT INTO column_transitions(from_column, to_column, rule)
            VALUES(?, ?, ?)
            ON CONFLICT(from_column, to_column) DO UPDATE SET rule=excluded.rule
            """,
            (from_column, to_column, rule),
        )


def require_linked_target(conn: sqlite3.Connection, intent_id: str | None, task_id: str | None) -> None:
    if not intent_id and not task_id:
        fail("A run requires --intent or --task")
    if intent_id and conn.execute("SELECT 1 FROM intents WHERE id = ?", (intent_id,)).fetchone() is None:
        fail(f"Unknown intent: {intent_id}")
    if task_id and not task_exists(conn, task_id):
        fail(f"Unknown task: {task_id}")


def run_start(
    conn: sqlite3.Connection,
    run_id: str,
    intent_id: str | None,
    task_id: str | None,
    worker: str,
    attempt: int,
) -> None:
    require_linked_target(conn, intent_id, task_id)
    if attempt < 1:
        fail("Run attempt must be positive")
    timestamp = now()
    with write_transaction(conn):
        conn.execute(
            "INSERT INTO runs(id, intent_id, task_id, status, attempt, worker, heartbeat_at, created_at, updated_at) "
            "VALUES(?, ?, ?, 'active', ?, ?, ?, ?, ?)",
            (run_id, intent_id, task_id, attempt, worker, timestamp, timestamp, timestamp),
        )
    print(f"started run {run_id}")


def envelope_set(conn: sqlite3.Connection, run_id: str, policy_text: str, granted_by: str) -> None:
    if conn.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone() is None:
        fail(f"Unknown run: {run_id}")
    try:
        policy = json.loads(policy_text)
    except json.JSONDecodeError as exc:
        fail(f"Envelope must be valid JSON: {exc}")
    if not isinstance(policy, dict):
        fail("Envelope must be a JSON object")
    required = {
        "mode", "allowed_tools", "allowed_paths", "network_policy", "max_steps",
        "max_duration_seconds", "max_retries", "max_concurrency", "approval_required",
        "stop_conditions",
    }
    missing = sorted(required - set(policy))
    if missing:
        fail("Envelope missing fields: " + ", ".join(missing))
    if policy["network_policy"] not in {"deny", "allowlist"}:
        fail("network_policy must be deny or allowlist")
    for key in ("max_steps", "max_duration_seconds", "max_retries", "max_concurrency"):
        if not isinstance(policy[key], int) or policy[key] < (0 if key == "max_retries" else 1):
            fail(f"{key} has an invalid budget")
    canonical = json_dumps(policy)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    with write_transaction(conn):
        conn.execute(
            "INSERT INTO autonomy_envelopes(run_id, policy_json, policy_hash, granted_by, created_at) "
            "VALUES(?, ?, ?, ?, ?)",
            (run_id, canonical, digest, granted_by, now()),
        )
    print(f"set envelope {run_id} sha256:{digest}")


def run_checkpoint(conn: sqlite3.Connection, run_id: str, checkpoint: str) -> None:
    with write_transaction(conn):
        cursor = conn.execute(
            "UPDATE runs SET checkpoint = ?, heartbeat_at = ?, updated_at = ? WHERE id = ? AND status = 'active'",
            (checkpoint, now(), now(), run_id),
        )
        if cursor.rowcount != 1:
            fail(f"Run is unknown or not active: {run_id}")


def run_checkin(
    conn: sqlite3.Connection,
    run_id: str,
    state: str,
    progress: str,
    next_action: str | None,
    expected_next_at: int | None,
    blocker: str | None,
    evidence: str | None,
    idempotency_key: str,
) -> None:
    if state not in RUN_WORKER_STATES:
        fail("Invalid worker state")
    if not progress.strip():
        fail("Progress summary is required")
    if state in {"waiting", "blocked"} and not (blocker or "").strip():
        fail(f"Worker state {state} requires --blocker")
    if state == "working" and not (next_action or "").strip():
        fail("Worker state working requires --next-action")
    row = conn.execute(
        "SELECT worker, attempt, status FROM runs WHERE id = ?", (run_id,)
    ).fetchone()
    if row is None:
        fail(f"Unknown run: {run_id}")
    if row["status"] != "active":
        fail(f"Run is not active: {run_id}")
    timestamp = now()
    progress_at = timestamp if state not in {"waiting", "blocked", "stalled"} else None
    with write_transaction(conn):
        cursor = conn.execute(
            """
            INSERT INTO run_checkins(
                run_id, worker, attempt, state, heartbeat_at, progress_at,
                progress_summary, next_action, expected_next_at, blocker,
                evidence, idempotency_key, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, idempotency_key) DO NOTHING
            """,
            (
                run_id, row["worker"] or "unknown", row["attempt"], state,
                timestamp, progress_at, progress.strip(), next_action,
                expected_next_at, blocker, evidence, idempotency_key, timestamp,
            ),
        )
        if cursor.rowcount == 0:
            existing = conn.execute(
                """
                SELECT worker, attempt, state, progress_summary, next_action,
                       expected_next_at, blocker, evidence
                FROM run_checkins
                WHERE run_id = ? AND idempotency_key = ?
                """,
                (run_id, idempotency_key),
            ).fetchone()
            proposed = (
                row["worker"] or "unknown", row["attempt"], state, progress.strip(),
                next_action, expected_next_at, blocker, evidence,
            )
            if tuple(existing) != proposed:
                fail("Idempotency key already records a different check-in")
        else:
            conn.execute(
                "UPDATE runs SET heartbeat_at = ?, checkpoint = ?, updated_at = ? WHERE id = ?",
                (timestamp, progress.strip(), timestamp, run_id),
            )
    action = "already recorded" if cursor.rowcount == 0 else "recorded"
    print(f"{action} check-in {run_id} {state}")


def run_cancel(conn: sqlite3.Connection, run_id: str, acknowledge: bool) -> None:
    timestamp = now()
    field = "cancellation_acknowledged_at" if acknowledge else "cancellation_requested_at"
    with write_transaction(conn):
        cursor = conn.execute(
            f"UPDATE runs SET {field} = ?, status = ?, updated_at = ? WHERE id = ?",
            (timestamp, "cancelled" if acknowledge else "paused", timestamp, run_id),
        )
        if cursor.rowcount != 1:
            fail(f"Unknown run: {run_id}")


def run_set_status(conn: sqlite3.Connection, run_id: str, status: str) -> None:
    if status not in RUN_STATUSES:
        fail("Invalid run status")
    with write_transaction(conn):
        cursor = conn.execute(
            "UPDATE runs SET status = ?, updated_at = ? WHERE id = ?", (status, now(), run_id)
        )
        if cursor.rowcount != 1:
            fail(f"Unknown run: {run_id}")


def gate_require(
    conn: sqlite3.Connection, gate_id: str, task_id: str, gate_type: str,
    applicability: str, rationale: str | None = None,
) -> None:
    if not task_exists(conn, task_id):
        fail(f"Unknown task: {task_id}")
    if applicability not in {"applicable", "not-applicable", "undetermined"}:
        fail("Invalid gate applicability")
    if applicability == "not-applicable" and not (rationale or "").strip():
        fail("A not-applicable gate requires rationale")
    recommendation = "not-applicable" if applicability == "not-applicable" else "pending"
    execution_status = "not-applicable" if applicability == "not-applicable" else "pending"
    with write_transaction(conn):
        conn.execute(
            "INSERT INTO gates(id, task_id, gate_type, applicability, recommendation, "
            "execution_status, rationale, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (gate_id, task_id, gate_type, applicability, recommendation,
             execution_status, rationale, now()),
        )


def gate_record(
    conn: sqlite3.Connection,
    gate_id: str,
    status: str,
    evaluator: str,
    independent: bool,
    rationale: str | None,
    rework_destination: str | None,
) -> None:
    if status not in {"pass", "fail", "blocked", "not-applicable"}:
        fail("Invalid gate result")
    if status == "not-applicable" and not (rationale or "").strip():
        fail("A not-applicable gate requires rationale")
    execution_status = {"pass": "complete", "fail": "rework", "blocked": "blocked", "not-applicable": "not-applicable"}[status]
    with write_transaction(conn):
        conn.execute(
            "UPDATE gates SET recommendation = ?, execution_status = ?, evaluator = ?, independent = ?, rationale = ?, "
            "rework_destination = ?, updated_at = ? WHERE id = ?",
            (status, execution_status, evaluator, int(independent), rationale,
             rework_destination, now(), gate_id),
        )


def specialist_class_add(
    conn: sqlite3.Connection,
    class_id: str,
    title: str,
    role_context: str,
    description: str | None,
) -> None:
    timestamp = now()
    with write_transaction(conn):
        conn.execute(
            "INSERT INTO specialist_classes(id, title, role_context, description, version, active, created_at, updated_at) "
            "VALUES(?, ?, ?, ?, 1, 1, ?, ?)",
            (class_id, title, role_context, description, timestamp, timestamp),
        )
        conn.execute(
            "INSERT INTO specialist_class_versions(specialist_class_id, version, title, role_context, description, created_at) "
            "VALUES(?, 1, ?, ?, ?, ?)",
            (class_id, title, role_context, description, timestamp),
        )
    print(f"registered specialist class {class_id}")


def specialist_class_update(
    conn: sqlite3.Connection,
    class_id: str,
    title: str,
    role_context: str,
    description: str | None,
) -> None:
    with write_transaction(conn):
        row = conn.execute("SELECT version FROM specialist_classes WHERE id = ?", (class_id,)).fetchone()
        if row is None:
            fail(f"Unknown specialist class: {class_id}")
        next_version = row["version"] + 1
        conn.execute(
            "UPDATE specialist_classes SET title = ?, role_context = ?, description = ?, "
            "version = ?, updated_at = ? WHERE id = ?",
            (title, role_context, description, next_version, now(), class_id),
        )
        conn.execute(
            "INSERT INTO specialist_class_versions(specialist_class_id, version, title, role_context, description, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (class_id, next_version, title, role_context, description, now()),
        )
        conn.execute(
            "UPDATE project_specialist_enrollments SET specialist_class_version=?, updated_at=? "
            "WHERE specialist_class_id=? AND status='enrolled'",
            (next_version, now(), class_id),
        )
    print(f"updated specialist class {class_id}")


def specialist_class_list(conn: sqlite3.Connection, active_only: bool) -> None:
    query = "SELECT id, title, role_context, description, version, active FROM specialist_classes"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY id"
    for row in conn.execute(query):
        print(json.dumps(dict(row), sort_keys=True))


def specialist_class_show(conn: sqlite3.Connection, class_id: str, context_only: bool, version: int | None) -> None:
    if version is None:
        row = conn.execute("SELECT * FROM specialist_classes WHERE id = ?", (class_id,)).fetchone()
    else:
        row = conn.execute(
            "SELECT specialist_class_id AS id, title, role_context, description, version, created_at "
            "FROM specialist_class_versions WHERE specialist_class_id = ? AND version = ?",
            (class_id, version),
        ).fetchone()
    if row is None:
        fail(f"Unknown specialist class: {class_id}")
    print(row["role_context"] if context_only else json.dumps(dict(row), sort_keys=True))


def gate_specialist_require(
    conn: sqlite3.Connection,
    gate_id: str,
    class_id: str,
    engagement_role: str,
    rationale: str,
) -> None:
    specialist = conn.execute(
        "SELECT version FROM specialist_classes WHERE id = ?", (class_id,)
    ).fetchone()
    if specialist is None:
        fail(f"Unknown specialist class: {class_id}")
    with write_transaction(conn):
        conn.execute(
            "INSERT INTO gate_specialist_requirements(gate_id, specialist_class_id, specialist_class_version, engagement_role, rationale, status, created_at, updated_at) "
            "VALUES(?, ?, ?, ?, ?, 'pending', ?, ?)",
            (gate_id, class_id, specialist["version"], engagement_role, rationale, now(), now()),
        )
    print(f"required specialist class {class_id} role={engagement_role} gate={gate_id}")


def gate_specialist_list(conn: sqlite3.Connection, gate_id: str) -> None:
    if conn.execute("SELECT 1 FROM gates WHERE id = ?", (gate_id,)).fetchone() is None:
        fail(f"Unknown gate: {gate_id}")
    for row in conn.execute(
        "SELECT r.gate_id, r.specialist_class_id, v.title, v.role_context, r.specialist_class_version, "
        "r.engagement_role, r.rationale, r.status, r.satisfied_by_handoff_id "
        "FROM gate_specialist_requirements r JOIN specialist_class_versions v "
        "ON v.specialist_class_id = r.specialist_class_id AND v.version = r.specialist_class_version "
        "WHERE r.gate_id = ? ORDER BY r.engagement_role, r.specialist_class_id",
        (gate_id,),
    ):
        print(json.dumps(dict(row), sort_keys=True))


def review_profile_set(
    conn: sqlite3.Connection,
    task_id: str,
    work_type: str,
    lifecycle_stage: str,
    artifact_kinds: list[str],
    risk_attributes: list[str],
    classified_by: str,
    rationale: str,
) -> None:
    payload = {
        "task_id": task_id,
        "work_type": work_type,
        "lifecycle_stage": lifecycle_stage,
        "artifact_kinds": sorted(set(artifact_kinds)),
        "risk_attributes": sorted(set(risk_attributes)),
    }
    scope_hash = "sha256:" + hashlib.sha256(json_dumps(payload).encode("utf-8")).hexdigest()
    with write_transaction(conn):
        conn.execute(
            "INSERT INTO task_work_profiles(task_id, work_type_id, lifecycle_stage, scope_hash, "
            "artifact_kinds_json, risk_attributes_json, classified_by, rationale, updated_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(task_id) DO UPDATE SET work_type_id=excluded.work_type_id, "
            "lifecycle_stage=excluded.lifecycle_stage, scope_hash=excluded.scope_hash, "
            "artifact_kinds_json=excluded.artifact_kinds_json, risk_attributes_json=excluded.risk_attributes_json, "
            "classified_by=excluded.classified_by, rationale=excluded.rationale, updated_at=excluded.updated_at",
            (task_id, work_type, lifecycle_stage, scope_hash, json_dumps(payload["artifact_kinds"]),
             json_dumps(payload["risk_attributes"]), classified_by, rationale, now()),
        )
    print(f"profiled task {task_id} scope={scope_hash}")


def review_profile_show(conn: sqlite3.Connection, task_id: str) -> None:
    row = conn.execute("SELECT * FROM task_work_profiles WHERE task_id = ?", (task_id,)).fetchone()
    if row is None:
        fail(f"Unknown review work profile: {task_id}")
    print(json.dumps(dict(row), sort_keys=True))


def review_condition_result(condition: dict[str, Any] | None, profile: sqlite3.Row) -> bool | None:
    if not condition or not isinstance(condition, dict):
        return None
    supported = {"artifact_kinds_any", "risk_attributes_any", "risk_attributes_all"}
    if set(condition) - supported:
        return None
    artifacts = set(json_loads(profile["artifact_kinds_json"], []))
    risks = set(json_loads(profile["risk_attributes_json"], []))
    outcomes: list[bool] = []
    if "artifact_kinds_any" in condition:
        if not isinstance(condition["artifact_kinds_any"], list) or not all(isinstance(item, str) for item in condition["artifact_kinds_any"]):
            return None
        outcomes.append(bool(artifacts & set(condition["artifact_kinds_any"])))
    if "risk_attributes_any" in condition:
        if not isinstance(condition["risk_attributes_any"], list) or not all(isinstance(item, str) for item in condition["risk_attributes_any"]):
            return None
        outcomes.append(bool(risks & set(condition["risk_attributes_any"])))
    if "risk_attributes_all" in condition:
        if not isinstance(condition["risk_attributes_all"], list) or not all(isinstance(item, str) for item in condition["risk_attributes_all"]):
            return None
        outcomes.append(set(condition["risk_attributes_all"]) <= risks)
    return all(outcomes) if outcomes else None


def matching_review_rule(
    conn: sqlite3.Connection,
    policy_id: str,
    policy_version: int,
    profile: sqlite3.Row,
    class_id: str,
    purpose: str,
) -> sqlite3.Row | None:
    rows = conn.execute(
        "SELECT *, (work_type_id IS NOT NULL) + (lifecycle_stage IS NOT NULL) + "
        "(specialist_class_id IS NOT NULL) AS specificity "
        "FROM review_policy_rules WHERE policy_id = ? AND policy_version = ? AND purpose = ? "
        "AND (work_type_id IS NULL OR work_type_id = ?) "
        "AND (lifecycle_stage IS NULL OR lifecycle_stage = ?) "
        "AND (specialist_class_id IS NULL OR specialist_class_id = ?) "
        "ORDER BY specificity DESC, priority DESC, id",
        (policy_id, policy_version, purpose, profile["work_type_id"], profile["lifecycle_stage"], class_id),
    ).fetchall()
    if not rows:
        return None
    top = rows[0]
    tied = [row for row in rows if row["specificity"] == top["specificity"] and row["priority"] == top["priority"]]
    if len(tied) > 1:
        fail(f"Ambiguous review policy rules for {class_id}/{purpose}: " + ", ".join(row["id"] for row in tied))
    return top


def create_guidance_snapshot(
    conn: sqlite3.Connection,
    snapshot_id: str,
    plan_id: str,
    task_id: str,
    profile: sqlite3.Row,
    timestamp: int,
) -> None:
    tenets = conn.execute(
        "SELECT t.id, t.current_version, v.strength, v.instruction FROM tenets t "
        "JOIN tenet_versions v ON v.tenet_id=t.id AND v.version=t.current_version "
        "WHERE t.active=1 AND v.status='active' ORDER BY t.id"
    ).fetchall()
    assignment = conn.execute(
        "SELECT a.arm, e.baseline_tenet_id, e.variant_tenet_id, e.variant_tenet_version "
        "FROM experiment_assignments a JOIN improvement_experiments e ON e.id=a.experiment_id "
        "WHERE a.task_id=? AND e.status='running'",
        (task_id,),
    ).fetchall()
    if len(assignment) > 1:
        fail("A task may have only one active tenet experiment assignment")
    replacement = assignment[0] if assignment and assignment[0]["arm"] == "variant" else None
    frozen = []
    for tenet in tenets:
        if replacement and tenet["id"] == replacement["baseline_tenet_id"]:
            tenet = conn.execute(
                "SELECT t.id, v.version AS current_version, v.strength, v.instruction "
                "FROM tenets t JOIN tenet_versions v ON v.tenet_id=t.id "
                "WHERE t.id=? AND v.version=?",
                (replacement["variant_tenet_id"], replacement["variant_tenet_version"]),
            ).fetchone()
        disposition = tenet["strength"]
        resolution = "pending"
        source = "tenet"
        rationale = "Active suite or project tenet"
        if tenet["id"] == "stop-on-abnormality":
            resolution = "inherited"
            rationale = "Inherited database stop-signal and completion guards; task-specific abnormalities still require a quality signal"
        elif tenet["id"] == "experiment-from-standard" and profile["work_type_id"] != "workflow-reflection":
            disposition, resolution, source = "not-applicable", "not-applicable", "policy"
            rationale = "Tenet changes are not part of this task's work profile"
        overrides = conn.execute(
            "SELECT * FROM project_tenet_overrides WHERE tenet_id=? AND tenet_version=? "
            "AND effective_at <= ? AND (expires_at IS NULL OR expires_at > ?) ORDER BY effective_at DESC, id",
            (tenet["id"], tenet["current_version"], timestamp, timestamp),
        ).fetchall()
        matching = []
        artifacts = set(json_loads(profile["artifact_kinds_json"], []))
        risks = set(json_loads(profile["risk_attributes_json"], []))
        for override in overrides:
            scope = json_loads(override["scope_json"], {})
            if scope.get("work_type") not in (None, profile["work_type_id"]):
                continue
            if scope.get("lifecycle_stage") not in (None, profile["lifecycle_stage"]):
                continue
            if scope.get("artifact_kinds_any") and not artifacts.intersection(scope["artifact_kinds_any"]):
                continue
            if scope.get("risk_attributes_any") and not risks.intersection(scope["risk_attributes_any"]):
                continue
            matching.append(override)
        if len(matching) > 1:
            fail(f"Ambiguous active tenet overrides for {tenet['id']}: " + ", ".join(row["id"] for row in matching))
        if matching:
            override = matching[0]
            disposition = override["disposition"]
            resolution = "exception" if disposition == "exception" else (
                "not-applicable" if disposition == "not-applicable" else "pending"
            )
            source = "human" if disposition in {"exception", "not-applicable"} else "policy"
            rationale = override["rationale"]
        frozen.append({
            "tenet_id": tenet["id"], "version": tenet["current_version"],
            "disposition": disposition, "resolution": resolution,
            "source": source, "rationale": rationale,
            "override_id": matching[0]["id"] if matching else None,
        })
    guidance_hash = "sha256:" + hashlib.sha256(json_dumps({
        "scope_hash": profile["scope_hash"], "tenets": frozen,
    }).encode("utf-8")).hexdigest()
    conn.execute(
        "INSERT INTO guidance_snapshots(id, task_id, review_plan_id, scope_hash, guidance_hash, status, created_at) "
        "VALUES(?, ?, ?, ?, ?, 'draft', ?)",
        (snapshot_id, task_id, plan_id, profile["scope_hash"], guidance_hash, timestamp),
    )
    for item in frozen:
        conn.execute(
            "INSERT INTO guidance_snapshot_tenets(guidance_snapshot_id, tenet_id, tenet_version, disposition, "
            "resolution, applicability_source, rationale, override_id, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (snapshot_id, item["tenet_id"], item["version"], item["disposition"], item["resolution"],
             item["source"], item["rationale"], item["override_id"], timestamp, timestamp),
        )
    conn.execute(
        "UPDATE guidance_snapshots SET status='frozen', frozen_at=? WHERE id=?",
        (timestamp, snapshot_id),
    )


def review_plan_create(
    conn: sqlite3.Connection,
    plan_id: str,
    task_id: str,
    policy_id: str,
    policy_version: int,
) -> None:
    profile = conn.execute("SELECT * FROM task_work_profiles WHERE task_id = ?", (task_id,)).fetchone()
    if profile is None:
        fail("Review planning requires a task work profile")
    policy = conn.execute(
        "SELECT status FROM review_policies WHERE id = ? AND version = ?",
        (policy_id, policy_version),
    ).fetchone()
    if policy is None or policy["status"] != "active":
        fail("Review planning requires an active policy version")
    classes = conn.execute(
        "SELECT id, version FROM specialist_classes WHERE active = 1 ORDER BY id"
    ).fetchall()
    timestamp = now()
    assurance_gate = f"{plan_id}-assurance"
    control_gate = f"{plan_id}-control"
    with write_transaction(conn):
        for gate_id, gate_type in ((assurance_gate, "assurance-readiness"), (control_gate, "independent-review")):
            conn.execute(
                "INSERT INTO gates(id, task_id, gate_type, applicability, recommendation, execution_status, updated_at) "
                "VALUES(?, ?, ?, 'applicable', 'pending', 'pending', ?)",
                (gate_id, task_id, gate_type, timestamp),
            )
        conn.execute(
            "INSERT INTO review_plans(id, task_id, policy_id, policy_version, scope_hash, assurance_gate_id, "
            "control_gate_id, status, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, 'draft', ?)",
            (plan_id, task_id, policy_id, policy_version, profile["scope_hash"], assurance_gate, control_gate, timestamp),
        )
        create_guidance_snapshot(conn, f"{plan_id}-guidance", plan_id, task_id, profile, timestamp)
        for specialist in classes:
            for purpose, role, gate_id in (
                ("assurance", "inform", assurance_gate),
                ("control", "review", control_gate),
            ):
                rule = matching_review_rule(
                    conn, policy_id, policy_version, profile, specialist["id"], purpose
                )
                disposition = rule["disposition"] if rule else "required"
                rule_id = rule["id"] if rule else None
                rationale = rule["rationale"] if rule else "Invariant default: every specialist class is applicable"
                condition = json_loads(rule["condition_json"], None) if rule else None
                condition_result = review_condition_result(condition, profile) if disposition == "conditional" else None
                if disposition == "normally-not-applicable" or (disposition == "conditional" and condition_result is False):
                    applicability, source, status = "not-applicable", "policy", "not-applicable"
                elif disposition == "reviewer-determined" or (disposition == "conditional" and condition_result is None):
                    applicability, source, status = "undetermined", "policy", "pending"
                else:
                    applicability, source, status = "applicable", "invariant" if rule is None else "policy", "pending"
                if rule_id:
                    conn.execute(
                        "INSERT OR IGNORE INTO review_plan_rule_bindings(review_plan_id, rule_id, policy_id, policy_version) "
                        "VALUES(?, ?, ?, ?)",
                        (plan_id, rule_id, policy_id, policy_version),
                    )
                item_id = f"{plan_id}-{specialist['id']}-{purpose}"
                conn.execute(
                    "INSERT INTO review_plan_items(id, review_plan_id, gate_id, specialist_class_id, "
                    "specialist_class_version, purpose, engagement_role, policy_disposition, applicability, "
                    "applicability_source, policy_rule_id, rationale, status, created_at, updated_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (item_id, plan_id, gate_id, specialist["id"], specialist["version"], purpose, role,
                     disposition, applicability, source, rule_id, rationale, status, timestamp, timestamp),
                )
                if status == "pending":
                    conn.execute(
                        "INSERT INTO gate_specialist_requirements(gate_id, specialist_class_id, specialist_class_version, "
                        "engagement_role, rationale, status, created_at, updated_at) "
                        "VALUES(?, ?, ?, ?, ?, 'pending', ?, ?)",
                        (gate_id, specialist["id"], specialist["version"], role, rationale, timestamp, timestamp),
                    )
        conn.execute(
            "UPDATE review_plans SET status='frozen', frozen_at=? WHERE id=?",
            (timestamp, plan_id),
        )
    print(f"created review plan {plan_id} classes={len(classes)} items={len(classes) * 2}")


def review_plan_show(conn: sqlite3.Connection, plan_id: str) -> None:
    plan = conn.execute("SELECT * FROM review_plans WHERE id = ?", (plan_id,)).fetchone()
    if plan is None:
        fail(f"Unknown review plan: {plan_id}")
    print(json.dumps(dict(plan), sort_keys=True))
    for row in conn.execute(
        "SELECT id, gate_id, specialist_class_id, specialist_class_version, purpose, engagement_role, "
        "policy_disposition, applicability, applicability_source, policy_rule_id, rationale, status, "
        "satisfied_by_handoff_id FROM review_plan_items WHERE review_plan_id = ? "
        "ORDER BY purpose, specialist_class_id",
        (plan_id,),
    ):
        print(json.dumps(dict(row), sort_keys=True))


def review_plan_list(conn: sqlite3.Connection, task_id: str | None) -> None:
    query = "SELECT id, task_id, policy_id, policy_version, scope_hash, status, assurance_gate_id, control_gate_id FROM review_plans"
    params: tuple[Any, ...] = ()
    if task_id:
        query += " WHERE task_id = ?"
        params = (task_id,)
    query += " ORDER BY created_at, id"
    for row in conn.execute(query, params):
        print(json.dumps(dict(row), sort_keys=True))


def schema_target(schema: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        fail(f"Unsupported schema reference: {reference}")
    value: Any = schema
    for part in reference[2:].split("/"):
        value = value[part.replace("~1", "/").replace("~0", "~")]
    return value


def schema_errors(value: Any, rule: dict[str, Any], schema: dict[str, Any], path: str = "$") -> list[str]:
    if "$ref" in rule:
        return schema_errors(value, schema_target(schema, rule["$ref"]), schema, path)
    errors: list[str] = []
    if "const" in rule and value != rule["const"]:
        errors.append(f"{path}: must equal {rule['const']!r}")
    if "enum" in rule and value not in rule["enum"]:
        errors.append(f"{path}: must be one of {rule['enum']}")
    expected = rule.get("type")
    if expected is not None:
        expected_types = expected if isinstance(expected, list) else [expected]
        matches = any({
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "null": value is None,
        }.get(item, False) for item in expected_types)
        if not matches:
            return errors + [f"{path}: expected type {expected}"]
    if isinstance(value, str) and len(value) < rule.get("minLength", 0):
        errors.append(f"{path}: string is too short")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and "minimum" in rule and value < rule["minimum"]:
        errors.append(f"{path}: must be at least {rule['minimum']}")
    if isinstance(value, dict):
        required = rule.get("required", [])
        for name in required:
            if name not in value:
                errors.append(f"{path}: missing required property {name}")
        properties = rule.get("properties", {})
        if rule.get("additionalProperties") is False:
            for name in value:
                if name not in properties:
                    errors.append(f"{path}: unexpected property {name}")
        for name, child in value.items():
            if name in properties:
                errors.extend(schema_errors(child, properties[name], schema, f"{path}.{name}"))
    if isinstance(value, list):
        item_rule = rule.get("items")
        if item_rule:
            for index, item in enumerate(value):
                errors.extend(schema_errors(item, item_rule, schema, f"{path}[{index}]"))
        if rule.get("uniqueItems"):
            rendered = [json_dumps(item) for item in value]
            if len(rendered) != len(set(rendered)):
                errors.append(f"{path}: items must be unique")
    return errors


def load_handoff_document(path: Path) -> tuple[dict[str, Any], str]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Cannot read handoff document: {exc}")
    if not isinstance(document, dict):
        fail("Handoff document must be a JSON object")
    schema = json.loads(HANDOFF_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = schema_errors(document, schema, schema)
    if errors:
        fail("Handoff schema validation failed: " + "; ".join(errors))
    canonical = json_dumps(document)
    return document, "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def handoff_semantic_errors(
    conn: sqlite3.Connection,
    document: dict[str, Any],
    expected_task: str | None = None,
    expected_run: str | None = None,
) -> list[str]:
    errors: list[str] = []
    task_id = document["task_id"]
    intent_id = document["intent_id"]
    run_id = document["run_id"]
    gate_id = document["gate_id"]
    specialist = conn.execute(
        "SELECT active FROM specialist_classes WHERE id = ?",
        (document["specialist_class"],),
    ).fetchone()
    if specialist is None or not specialist["active"]:
        errors.append(f"unknown or inactive specialist class: {document['specialist_class']}")
    if task_id is None and intent_id is None:
        errors.append("handoff must link to an intent or task")
    if expected_task is not None and task_id != expected_task:
        errors.append("task does not match --expected-task")
    if expected_run is not None and run_id != expected_run:
        errors.append("run does not match --expected-run")
    if task_id is not None and not task_exists(conn, task_id):
        errors.append(f"unknown task: {task_id}")
    if intent_id is not None and conn.execute("SELECT 1 FROM intents WHERE id = ?", (intent_id,)).fetchone() is None:
        errors.append(f"unknown intent: {intent_id}")
    run = None
    if run_id is not None:
        run = conn.execute("SELECT intent_id, task_id, attempt FROM runs WHERE id = ?", (run_id,)).fetchone()
        if run is None:
            errors.append(f"unknown run: {run_id}")
        else:
            if task_id is not None and run["task_id"] != task_id:
                errors.append("run does not belong to handoff task")
            if intent_id is not None and run["intent_id"] not in {None, intent_id}:
                errors.append("run does not belong to handoff intent")
            if document["attempt_id"] is not None and str(document["attempt_id"]) != str(run["attempt"]):
                errors.append("attempt does not match run attempt")
    gate = None
    if gate_id is not None:
        gate = conn.execute("SELECT task_id, gate_type FROM gates WHERE id = ?", (gate_id,)).fetchone()
        if gate is None:
            errors.append(f"unknown gate: {gate_id}")
        else:
            if task_id is None or gate["task_id"] != task_id:
                errors.append("gate does not belong to handoff task")
            requirement = conn.execute(
                "SELECT engagement_role, specialist_class_version FROM gate_specialist_requirements "
                "WHERE gate_id = ? AND specialist_class_id = ? AND engagement_role = ?",
                (gate_id, document["specialist_class"], document["engagement_role"]),
            ).fetchone()
            if requirement is None:
                errors.append(
                    f"specialist class {document['specialist_class']} is not assigned to gate {gate_id}"
                )
            elif requirement["specialist_class_version"] != document["specialist_class_version"]:
                errors.append(
                    "handoff specialist class version does not match the assigned role context"
                )
            elif document["engagement_role"] == "review" and not document["independent"]:
                errors.append("a review specialist requirement requires an independent handoff")
            if gate["gate_type"] == "independent-review" and not document["independent"]:
                errors.append("independent review requires an independent specialist")
    plan_item_id = document.get("review_plan_item_id")
    review_purpose = document.get("review_purpose")
    if plan_item_id is not None:
        item = conn.execute(
            "SELECT i.*, p.task_id FROM review_plan_items i JOIN review_plans p ON p.id = i.review_plan_id "
            "WHERE i.id = ?",
            (plan_item_id,),
        ).fetchone()
        if item is None:
            errors.append(f"unknown review plan item: {plan_item_id}")
        else:
            expected = (
                item["specialist_class_id"], item["specialist_class_version"], item["engagement_role"],
                item["purpose"], item["gate_id"], item["task_id"],
            )
            actual = (
                document["specialist_class"], document["specialist_class_version"], document["engagement_role"],
                review_purpose, gate_id, task_id,
            )
            if actual != expected:
                errors.append("handoff identity does not match the review plan item")
            if item["status"] != "pending":
                errors.append("review plan item is not pending")
            if item["purpose"] == "control" and not document["independent"]:
                errors.append("control review requires an independent specialist")
    elif review_purpose is not None:
        errors.append("review_purpose requires review_plan_item_id")
    elif gate_id is not None and conn.execute(
        "SELECT 1 FROM review_plan_items WHERE gate_id = ? AND specialist_class_id = ? "
        "AND engagement_role = ? AND status = 'pending'",
        (gate_id, document["specialist_class"], document["engagement_role"]),
    ).fetchone() is not None:
        errors.append("planned review handoff requires review_plan_item_id and review_purpose")
    applicability = document["applicability"]
    recommendation = document["gate_recommendation"]
    status = document["status"]
    required_tuple = {
        "pass": ("applicable", "complete"),
        "fail": ("applicable", "rework"),
        "blocked": ("applicable", "blocked"),
        "not-applicable": ("not-applicable", "not-applicable"),
    }[recommendation]
    if (applicability, status) != required_tuple:
        errors.append(
            f"{recommendation} requires applicability/status {required_tuple}, got {(applicability, status)}"
        )
    if recommendation == "pass" and not document["evidence"]:
        errors.append("a passing handoff requires evidence")
    if recommendation == "not-applicable" and not document["findings"]:
        errors.append("a not-applicable handoff requires a rationale finding")
    if recommendation == "pass" and any(item["severity"] == "blocker" for item in document["findings"]):
        errors.append("a passing handoff cannot contain a blocker finding")
    if recommendation == "pass" and any(item["authority_required"] for item in document["open_decisions"]):
        errors.append("a passing handoff cannot leave an authority decision open")
    destination = document["rework_destination"]
    if destination is not None and destination not in CANONICAL_REWORK_STAGES:
        errors.append(f"invalid rework destination: {destination}")
    if recommendation == "fail" and destination is None:
        errors.append("a failed handoff requires a rework destination")
    for item in document["sources"]:
        reference_id = item.get("reference_id")
        if reference_id and conn.execute("SELECT 1 FROM research_references WHERE id = ?", (reference_id,)).fetchone() is None:
            errors.append(f"unknown research reference: {reference_id}")
    for item in document["open_decisions"]:
        decision_id = item.get("decision_id")
        if decision_id and conn.execute("SELECT 1 FROM decisions WHERE id = ?", (decision_id,)).fetchone() is None:
            errors.append(f"unknown decision: {decision_id}")
    if document["evidence"] and task_id is None:
        errors.append("handoff evidence requires a task")
    obligations = document.get("obligations", [])
    if obligations and review_purpose != "assurance":
        errors.append("only an assurance handoff may materialize production obligations")
    if obligations:
        snapshot = conn.execute(
            "SELECT s.id FROM guidance_snapshots s JOIN review_plan_items i "
            "ON i.review_plan_id=s.review_plan_id WHERE i.id=? AND s.status='frozen'",
            (plan_item_id,),
        ).fetchone()
        if snapshot is None:
            errors.append("assurance obligations require a matching frozen guidance snapshot")
        else:
            for obligation in obligations:
                if conn.execute(
                    "SELECT 1 FROM guidance_snapshot_tenets WHERE guidance_snapshot_id=? AND tenet_id=?",
                    (snapshot["id"], obligation["tenet_id"]),
                ).fetchone() is None:
                    errors.append(f"obligation references a tenet outside the frozen snapshot: {obligation['tenet_id']}")
    proposals = document.get("guidance_proposals", [])
    if proposals and intent_id is None:
        errors.append("project guidance proposals require an intent")
    if proposals and review_purpose == "control":
        errors.append("control review cannot propose governing project guidance")
    for proposal in proposals:
        if proposal["guidance_kind"] == "principle" and proposal.get("verification_strategy") is not None:
            errors.append("a principle proposal must express an outcome, not a verification strategy")
        if proposal["guidance_kind"] == "tenet" and not (proposal.get("verification_strategy") or "").strip():
            errors.append("a tenet proposal requires a verification strategy")
    if run_id is not None and document["permissions_used"]:
        envelope = conn.execute("SELECT policy_json FROM autonomy_envelopes WHERE run_id = ?", (run_id,)).fetchone()
        if envelope is None:
            errors.append("permissions were reported but the run has no autonomy envelope")
        else:
            policy = json_loads(envelope["policy_json"], {})
            allowed_permissions = set(policy.get("allowed_permissions", []))
            ungranted = sorted(set(document["permissions_used"]) - allowed_permissions)
            if ungranted:
                errors.append("permissions exceed autonomy envelope: " + ", ".join(ungranted))
    return errors


def handoff_validate(conn: sqlite3.Connection, path: Path, expected_task: str | None, expected_run: str | None) -> tuple[dict[str, Any], str]:
    document, document_hash = load_handoff_document(path)
    errors = handoff_semantic_errors(conn, document, expected_task, expected_run)
    if errors:
        fail("Handoff semantic validation failed: " + "; ".join(errors))
    return document, document_hash


def refresh_gate_from_specialists(conn: sqlite3.Connection, gate_id: str, timestamp: int) -> None:
    requirements = conn.execute(
        "SELECT status, satisfied_by_handoff_id FROM gate_specialist_requirements WHERE gate_id = ?",
        (gate_id,),
    ).fetchall()
    if not requirements or any(row["status"] == "pending" for row in requirements):
        return
    handoffs = conn.execute(
        "SELECT h.recommendation, h.worker_id, h.independent, h.rework_destination "
        "FROM specialist_handoffs h JOIN gate_specialist_requirements r "
        "ON r.satisfied_by_handoff_id = h.id WHERE r.gate_id = ?",
        (gate_id,),
    ).fetchall()
    recommendations = {row["recommendation"] for row in handoffs}
    if "blocked" in recommendations:
        recommendation, execution_status = "blocked", "blocked"
    elif "fail" in recommendations:
        recommendation, execution_status = "fail", "rework"
    elif recommendations and recommendations <= {"pass", "not-applicable"}:
        recommendation, execution_status = "pass", "complete"
    else:
        return
    workers = ",".join(sorted({row["worker_id"] for row in handoffs}))
    destinations = sorted({row["rework_destination"] for row in handoffs if row["rework_destination"]})
    destination = destinations[0] if len(destinations) == 1 else ("Design" if destinations else None)
    conn.execute(
        "UPDATE gates SET recommendation = ?, execution_status = ?, evaluator = ?, independent = ?, "
        "rework_destination = ?, rationale = ?, updated_at = ? WHERE id = ?",
        (recommendation, execution_status, workers, int(any(row["independent"] for row in handoffs)),
         destination, f"aggregated {len(handoffs)} specialist handoff(s)", timestamp, gate_id),
    )


def handoff_ingest(conn: sqlite3.Connection, path: Path, expected_task: str | None, expected_run: str | None) -> None:
    document, document_hash = handoff_validate(conn, path, expected_task, expected_run)
    existing = conn.execute("SELECT document_hash FROM specialist_handoffs WHERE id = ?", (document["handoff_id"],)).fetchone()
    if existing is not None:
        if existing["document_hash"] != document_hash:
            fail("Handoff id already exists with different content")
        receipt = conn.execute("SELECT id FROM handoff_receipts WHERE handoff_id = ?", (document["handoff_id"],)).fetchone()
        print(f"handoff already committed {document['handoff_id']} receipt={receipt['id']}")
        return
    timestamp = now()
    receipt_id = f"receipt-{document['handoff_id']}"
    rationale = "; ".join(item["summary"] for item in document["findings"]) or f"handoff {document['handoff_id']}"
    with write_transaction(conn):
        conn.execute(
            "INSERT INTO specialist_handoffs(id, document_hash, contract_version, specialist_class_id, specialist_class_version, engagement_role, review_purpose, review_plan_item_id, worker_id, "
            "gate_id, intent_id, task_id, run_id, attempt_id, scope, applicability, recommendation, execution_status, "
            "independent, rework_destination, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (document["handoff_id"], document_hash, document["contract_version"], document["specialist_class"],
             document["specialist_class_version"], document["engagement_role"], document.get("review_purpose"),
             document.get("review_plan_item_id"), document["worker_id"],
             document["gate_id"], document["intent_id"], document["task_id"],
             document["run_id"], None if document["attempt_id"] is None else str(document["attempt_id"]),
             document["scope"], document["applicability"], document["gate_recommendation"], document["status"],
             int(document["independent"]), document["rework_destination"], timestamp),
        )
        conn.executemany(
            "INSERT INTO handoff_permissions(handoff_id, permission) VALUES(?, ?)",
            [(document["handoff_id"], item) for item in document["permissions_used"]],
        )
        for ordinal, item in enumerate(document["sources"]):
            conn.execute(
                "INSERT INTO handoff_sources(handoff_id, ordinal, reference_id, title, publisher, url, retrieved_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (document["handoff_id"], ordinal, item.get("reference_id"), item["title"], item["publisher"], item["url"], item.get("retrieved_at")),
            )
        for kind, key in (("observed", "artifacts_observed"), ("changed", "artifacts_changed")):
            for ordinal, item in enumerate(document[key]):
                conn.execute(
                    "INSERT INTO handoff_artifacts(handoff_id, kind, ordinal, artifact_ref, revision, digest) VALUES(?, ?, ?, ?, ?, ?)",
                    (document["handoff_id"], kind, ordinal, item["artifact_ref"], item.get("revision"), item.get("digest")),
                )
        for ordinal, item in enumerate(document["findings"]):
            conn.execute(
                "INSERT INTO handoff_findings(handoff_id, ordinal, severity, summary, rework_destination) VALUES(?, ?, ?, ?, ?)",
                (document["handoff_id"], ordinal, item["severity"], item["summary"], item.get("rework_destination")),
            )
        for proposal in document.get("guidance_proposals", []):
            conn.execute(
                "INSERT INTO specialist_guidance_proposals(id, intent_id, specialist_class_id, specialist_class_version, "
                "handoff_id, guidance_kind, theme, title, statement, intended_outcome, rationale, applicability_json, "
                "verification_strategy, status, created_at, updated_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?, ?)",
                (proposal["proposal_id"], document["intent_id"], document["specialist_class"],
                 document["specialist_class_version"], document["handoff_id"], proposal["guidance_kind"],
                 proposal["theme"], proposal["title"], proposal["statement"], proposal["intended_outcome"],
                 proposal["rationale"], json_dumps(proposal["applicability"]), proposal.get("verification_strategy"),
                 timestamp, timestamp),
            )
        if document["intent_id"] is not None:
            conn.execute(
                "UPDATE project_specialist_enrollments SET status='consulted', updated_at=? "
                "WHERE intent_id=? AND specialist_class_id=?",
                (timestamp, document["intent_id"], document["specialist_class"]),
            )
        if document.get("obligations"):
            snapshot_id = conn.execute(
                "SELECT s.id FROM guidance_snapshots s JOIN review_plan_items i "
                "ON i.review_plan_id=s.review_plan_id WHERE i.id=?",
                (document.get("review_plan_item_id"),),
            ).fetchone()["id"]
            for item in document["obligations"]:
                conn.execute(
                    "INSERT INTO assurance_obligations(id, guidance_snapshot_id, tenet_id, review_plan_item_id, "
                    "obligation_type, summary, affected_artifact, lifecycle_stage, verification_method, owner, status, created_at, updated_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'planned', ?, ?)",
                    (item["obligation_id"], snapshot_id, item["tenet_id"], document.get("review_plan_item_id"),
                     item["obligation_type"], item["summary"], item.get("affected_artifact"), item["lifecycle_stage"],
                     item["verification_method"], item["owner"], timestamp, timestamp),
                )
                conn.execute(
                    "UPDATE guidance_snapshot_tenets SET resolution='materialized', applicability_source='specialist', "
                    "resolved_by_handoff_id=?, updated_at=? WHERE guidance_snapshot_id=? AND tenet_id=?",
                    (document["handoff_id"], timestamp, snapshot_id, item["tenet_id"]),
                )
        for item in document["evidence"]:
            evidence_add(
                conn, item["evidence_id"], document["task_id"], document["gate_id"], item["criterion_id"],
                item["artifact"], item["revision"], item["probe"], item["result"], item["producer"],
                item.get("environment"), item.get("location"), item.get("content_hash"), transactional=False,
            )
            conn.execute("INSERT INTO handoff_evidence(handoff_id, evidence_id) VALUES(?, ?)", (document["handoff_id"], item["evidence_id"]))
        for ordinal, item in enumerate(document["residual_risks"]):
            conn.execute(
                "INSERT INTO handoff_risks(handoff_id, ordinal, summary, owner, acceptance_required) VALUES(?, ?, ?, ?, ?)",
                (document["handoff_id"], ordinal, item["summary"], item.get("owner"), int(item["acceptance_required"])),
            )
        for ordinal, item in enumerate(document["open_decisions"]):
            conn.execute(
                "INSERT INTO handoff_decisions(handoff_id, ordinal, decision_id, question, authority_required) VALUES(?, ?, ?, ?, ?)",
                (document["handoff_id"], ordinal, item.get("decision_id"), item["question"], int(item["authority_required"])),
            )
        if document["gate_id"] is not None:
            conn.execute(
                "UPDATE gate_specialist_requirements SET status = ?, satisfied_by_handoff_id = ?, updated_at = ? "
                "WHERE gate_id = ? AND specialist_class_id = ? AND engagement_role = ?",
                ("not-applicable" if document["gate_recommendation"] == "not-applicable" else "satisfied",
                 document["handoff_id"], timestamp, document["gate_id"], document["specialist_class"], document["engagement_role"]),
            )
            if document.get("review_plan_item_id") is not None:
                item_status = (
                    "not-applicable" if document["gate_recommendation"] == "not-applicable"
                    else "blocked" if document["gate_recommendation"] == "blocked"
                    else "satisfied"
                )
                conn.execute(
                    "UPDATE review_plan_items SET status = ?, applicability = ?, applicability_source = "
                    "CASE WHEN ? = 'not-applicable' THEN 'reviewer' ELSE applicability_source END, "
                    "satisfied_by_handoff_id = ?, updated_at = ? WHERE id = ?",
                    (item_status, document["applicability"], document["gate_recommendation"],
                     document["handoff_id"], timestamp, document["review_plan_item_id"]),
                )
            refresh_gate_from_specialists(conn, document["gate_id"], timestamp)
            conn.execute(
                "UPDATE review_plans SET status = 'complete' WHERE id = ("
                "SELECT review_plan_id FROM review_plan_items WHERE id = ?"
                ") AND status = 'frozen' AND NOT EXISTS ("
                "SELECT 1 FROM review_plan_items i WHERE i.review_plan_id = review_plans.id "
                "AND i.status IN ('pending', 'blocked')"
                ") AND (SELECT recommendation FROM gates WHERE id = assurance_gate_id) = 'pass' "
                "AND (SELECT recommendation FROM gates WHERE id = control_gate_id) = 'pass'",
                (document.get("review_plan_item_id"),),
            )
        conn.execute(
            "INSERT INTO handoff_receipts(id, handoff_id, document_hash, status, created_at) VALUES(?, ?, ?, 'committed', ?)",
            (receipt_id, document["handoff_id"], document_hash, timestamp),
        )
        conn.execute(
            "INSERT INTO learning_events(occurred_at, event_type, outcome, reason_summary, intent_id, task_id, run_id, gate_id, attempt_id, payload_json) "
            "VALUES(?, 'handoff.ingested', ?, ?, ?, ?, ?, ?, ?, ?)",
            (timestamp, document["gate_recommendation"], rationale, document["intent_id"], document["task_id"],
             document["run_id"], document["gate_id"], None if document["attempt_id"] is None else str(document["attempt_id"]),
             json_dumps({"handoff_id": document["handoff_id"], "receipt_id": receipt_id, "document_hash": document_hash})),
        )
    print(f"ingested handoff {document['handoff_id']} receipt={receipt_id} hash={document_hash}")


def handoff_show(conn: sqlite3.Connection, handoff_id: str) -> None:
    row = conn.execute("SELECT * FROM specialist_handoffs WHERE id = ?", (handoff_id,)).fetchone()
    if row is None:
        fail(f"Unknown handoff: {handoff_id}")
    print(json.dumps(dict(row), sort_keys=True))


def handoff_list(conn: sqlite3.Connection, task_id: str | None) -> None:
    query = "SELECT id, specialist_class_id, engagement_role, worker_id, gate_id, task_id, recommendation, execution_status, created_at FROM specialist_handoffs"
    params: tuple[Any, ...] = ()
    if task_id:
        query += " WHERE task_id = ?"
        params = (task_id,)
    query += " ORDER BY created_at, id"
    for row in conn.execute(query, params):
        print(json.dumps(dict(row), sort_keys=True))


def evidence_add(
    conn: sqlite3.Connection,
    evidence_id: str,
    task_id: str,
    gate_id: str | None,
    criterion_id: str,
    artifact: str,
    revision: str,
    probe: str,
    result: str,
    producer: str,
    environment: str | None,
    location: str | None,
    content_hash: str | None,
    transactional: bool = True,
) -> None:
    if not task_exists(conn, task_id):
        fail(f"Unknown task: {task_id}")
    if result not in {"pass", "fail", "inconclusive"}:
        fail("Invalid evidence result")
    context = write_transaction(conn) if transactional else contextlib.nullcontext()
    with context:
        conn.execute(
            "INSERT INTO evidence(id, task_id, gate_id, criterion_id, artifact, revision, probe, result, "
            "producer, environment, location, content_hash, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (evidence_id, task_id, gate_id, criterion_id, artifact, revision, probe, result,
             producer, environment, location, content_hash, now()),
        )


def receipt_add(
    conn: sqlite3.Connection,
    receipt_id: str,
    run_id: str,
    idempotency_key: str,
    action_class: str,
    target: str,
    status: str,
    receipt: str | None,
) -> None:
    if conn.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone() is None:
        fail(f"Unknown run: {run_id}")
    if status not in {"planned", "applied", "failed", "compensated"}:
        fail("Invalid receipt status")
    with write_transaction(conn):
        conn.execute(
            "INSERT INTO side_effect_receipts(id, run_id, idempotency_key, action_class, target, status, receipt, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (receipt_id, run_id, idempotency_key, action_class, target, status, receipt, now()),
        )


def conformance_errors(conn: sqlite3.Connection, task_id: str) -> list[str]:
    if not task_exists(conn, task_id):
        fail(f"Unknown task: {task_id}")
    errors: list[str] = []
    for row in conn.execute(
        "SELECT id, gate_type, recommendation FROM gates WHERE task_id = ? AND applicability = 'applicable'",
        (task_id,),
    ):
        if row["recommendation"] != "pass":
            errors.append(f"gate {row['id']} ({row['gate_type']}) is {row['recommendation']}")
    criteria = json_loads(conn.execute("SELECT raw_json FROM tasks WHERE id = ?", (task_id,)).fetchone()[0]).get("exit_criteria", [])
    passed = {row["criterion_id"] for row in conn.execute(
        "SELECT criterion_id FROM evidence WHERE task_id = ? AND result = 'pass'", (task_id,)
    )}
    for index, criterion in enumerate(criteria, start=1):
        if str(index) not in passed and str(criterion) not in passed:
            errors.append(f"criterion lacks passing evidence: {criterion}")
    return errors


def task_conformance(conn: sqlite3.Connection, task_id: str) -> None:
    errors = conformance_errors(conn, task_id)
    if errors:
        fail("; ".join(errors), 1)
    print(f"PASS task conformant {task_id}")


def learning_event_add(
    conn: sqlite3.Connection,
    event_type: str,
    reason: str,
    context_track: str,
    outcome: str | None,
    payload: str,
    redaction_state: str,
    intent_id: str | None,
    task_id: str | None,
    run_id: str | None,
    decision_id: str | None,
    gate_id: str | None,
    evidence_id: str | None,
    reference_id: str | None,
    attempt_id: str | None,
    artifact_ref: str | None,
    commit_ref: str | None,
    reviewer_id: str | None,
    occurred_at: int | None,
) -> None:
    try:
        payload_value = json.loads(payload)
    except json.JSONDecodeError as exc:
        fail(f"Event payload must be valid JSON: {exc}")
    if context_track not in {"execution", "reflection"}:
        fail("Invalid context track")
    if redaction_state not in {"redacted", "not-sensitive", "needs-review"}:
        fail("Invalid redaction state")
    with write_transaction(conn):
        cursor = conn.execute(
            "INSERT INTO learning_events(occurred_at, event_type, context_track, outcome, reason_summary, "
            "payload_json, redaction_state, intent_id, task_id, run_id, decision_id, gate_id, evidence_id, "
            "reference_id, attempt_id, artifact_ref, commit_ref, reviewer_id) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (occurred_at or now(), event_type, context_track, outcome, reason,
             json_dumps(payload_value), redaction_state, intent_id, task_id, run_id,
             decision_id, gate_id, evidence_id, reference_id, attempt_id,
             artifact_ref, commit_ref, reviewer_id),
        )
    print(f"created learning event {cursor.lastrowid}")


def query_learning_events(
    conn: sqlite3.Connection,
    event_type: str | None,
    context_track: str | None,
    task_id: str | None,
    intent_id: str | None,
    since: int | None,
    until: int | None,
    limit: int | None,
 ) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for column, value in (("event_type", event_type), ("context_track", context_track),
                          ("task_id", task_id), ("intent_id", intent_id)):
        if value:
            clauses.append(f"{column} = ?")
            params.append(value)
    if since is not None:
        clauses.append("occurred_at >= ?")
        params.append(since)
    if until is not None:
        clauses.append("occurred_at <= ?")
        params.append(until)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    sql = "SELECT * FROM learning_events" + where + " ORDER BY occurred_at, id"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    records: list[dict[str, Any]] = []
    for row in conn.execute(sql, params):
        record = dict(row)
        record["payload"] = json_loads(record.pop("payload_json"), {})
        records.append(record)
    return records


def learning_event_list(
    conn: sqlite3.Connection,
    event_type: str | None,
    context_track: str | None,
    task_id: str | None,
    intent_id: str | None,
    since: int | None,
    until: int | None,
    limit: int | None,
    as_json: bool,
) -> None:
    for record in query_learning_events(
        conn, event_type, context_track, task_id, intent_id, since, until, limit
    ):
        if as_json:
            print(json_dumps(record))
        else:
            print(f"{record['occurred_at']}\t{record['context_track']}\t{record['event_type']}\t{record['reason_summary']}")


def metric_snapshot(conn: sqlite3.Connection, scope_type: str, scope_id: str) -> None:
    timestamp = now()
    active = conn.execute("SELECT COUNT(*) FROM tasks WHERE column_name = 'Active'").fetchone()[0]
    done = conn.execute("SELECT COUNT(*) FROM tasks WHERE column_name = 'Done'").fetchone()[0]
    rework = conn.execute("SELECT COUNT(*) FROM learning_events WHERE event_type = 'review.rework'").fetchone()[0]
    accepted = conn.execute("SELECT COUNT(DISTINCT task_id) FROM learning_events WHERE event_type = 'review.accepted'").fetchone()[0]
    accepted_after_rework = conn.execute(
        "SELECT COUNT(DISTINCT a.task_id) FROM learning_events a WHERE a.event_type = 'review.accepted' "
        "AND EXISTS (SELECT 1 FROM learning_events r WHERE r.task_id = a.task_id AND r.event_type = 'review.rework' AND r.occurred_at <= a.occurred_at)"
    ).fetchone()[0]
    oldest = conn.execute(
        "SELECT MIN(updated_at) FROM tasks WHERE column_name NOT IN ('Done', 'Deferred')"
    ).fetchone()[0]
    average_cycle = conn.execute(
        "SELECT AVG(done_at - active_at) FROM ("
        "SELECT task_id, MIN(CASE WHEN reason_summary = 'moved to Active' THEN occurred_at END) AS active_at, "
        "MIN(CASE WHEN reason_summary = 'moved to Done' THEN occurred_at END) AS done_at "
        "FROM learning_events GROUP BY task_id) WHERE active_at IS NOT NULL AND done_at IS NOT NULL AND done_at >= active_at"
    ).fetchone()[0]
    values = {
        "wip_active": (float(active), "items"),
        "completed_items": (float(done), "items"),
        "rework_events": (float(rework), "events"),
        "first_pass_acceptance": (
            float(accepted - accepted_after_rework) / accepted if accepted else 0.0, "ratio"
        ),
        "gate_failures": (float(conn.execute("SELECT COUNT(*) FROM gates WHERE recommendation = 'fail'").fetchone()[0]), "gates"),
        "max_open_item_age_seconds": (float(timestamp - oldest) if oldest else 0.0, "seconds"),
        "average_cycle_time_seconds": (float(average_cycle) if average_cycle is not None else 0.0, "seconds"),
        "cancellations": (float(conn.execute("SELECT COUNT(*) FROM runs WHERE cancellation_requested_at IS NOT NULL").fetchone()[0]), "runs"),
    }
    with write_transaction(conn):
        for name, (value, unit) in values.items():
            conn.execute(
                "INSERT INTO metric_snapshots(measured_at, scope_type, scope_id, metric_name, metric_value, unit, derivation_version) "
                "VALUES(?, ?, ?, ?, ?, ?, '1') ON CONFLICT(measured_at, scope_type, scope_id, metric_name, derivation_version) "
                "DO UPDATE SET metric_value = excluded.metric_value, unit = excluded.unit",
                (timestamp, scope_type, scope_id, name, value, unit),
            )
    print(f"created metric snapshot {timestamp} metrics={len(values)}")


def query_metric_snapshots(
    conn: sqlite3.Connection,
    metric_name: str | None = None,
    scope_id: str | None = None,
    since: int | None = None,
    until: int | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if metric_name:
        clauses.append("metric_name = ?")
        params.append(metric_name)
    if scope_id is not None:
        clauses.append("scope_id = ?")
        params.append(scope_id)
    if since is not None:
        clauses.append("measured_at >= ?")
        params.append(since)
    if until is not None:
        clauses.append("measured_at <= ?")
        params.append(until)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return [dict(row) for row in conn.execute(
        "SELECT measured_at, scope_type, scope_id, metric_name, metric_value, unit, derivation_version "
        "FROM metric_snapshots" + where + " ORDER BY measured_at, metric_name", params
    )]


def metric_list(conn: sqlite3.Connection, metric_name: str | None, scope_id: str | None) -> None:
    for row in query_metric_snapshots(conn, metric_name, scope_id):
        print("\t".join(str(row[key]) for key in row))


def learning_archive_add(
    conn: sqlite3.Connection,
    event_start_id: int | None,
    event_end_id: int | None,
    event_count: int,
    artifact_location: str,
    content_hash: str,
    policy_version: str,
    preserved_signal: str,
    dropped_detail: str,
) -> None:
    path = Path(artifact_location)
    if path.is_absolute() or ".." in path.parts:
        fail("Archive location must be project-relative")
    with write_transaction(conn):
        conn.execute(
            "INSERT INTO learning_archives(created_at, event_start_id, event_end_id, event_count, artifact_location, "
            "content_hash, policy_version, preserved_signal, dropped_detail) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now(), event_start_id, event_end_id, event_count, artifact_location, content_hash,
             policy_version, preserved_signal, dropped_detail),
        )


def learning_archive_hash_exists(conn: sqlite3.Connection, content_hash: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM learning_archives WHERE content_hash = ? LIMIT 1", (content_hash,)
    ).fetchone() is not None


def learning_event_import(
    conn: sqlite3.Connection,
    records: list[dict[str, Any]],
    artifact_location: str,
    content_hash: str,
) -> None:
    if learning_archive_hash_exists(conn, content_hash):
        fail(f"Archive already imported: {content_hash}")
    link_tables = {
        "intent_id": "intents", "task_id": "tasks", "run_id": "runs",
        "decision_id": "decisions", "gate_id": "gates", "evidence_id": "evidence",
        "reference_id": "research_references",
    }
    normalized: list[dict[str, Any]] = []
    for original in records:
        record = dict(original)
        for field, table in link_tables.items():
            value = record.get(field)
            if value is not None and conn.execute(
                f"SELECT 1 FROM {table} WHERE id = ?", (value,)
            ).fetchone() is None:
                record[field] = None
        normalized.append(record)
    with write_transaction(conn):
        for record in normalized:
            conn.execute(
                "INSERT INTO learning_events(occurred_at, event_type, context_track, outcome, reason_summary, "
                "payload_json, redaction_state, intent_id, task_id, run_id, decision_id, gate_id, evidence_id, "
                "reference_id, attempt_id, artifact_ref, commit_ref, reviewer_id) "
                "VALUES(?, ?, ?, ?, ?, ?, 'redacted', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record["occurred_at"], record["event_type"], record["context_track"],
                    record.get("outcome"), record["reason_summary"], record["payload_json"],
                    record.get("intent_id"), record.get("task_id"), record.get("run_id"),
                    record.get("decision_id"), record.get("gate_id"), record.get("evidence_id"),
                    record.get("reference_id"), record.get("attempt_id"),
                    record.get("artifact_ref"), record.get("commit_ref"), record.get("reviewer_id"),
                ),
            )
        conn.execute(
            "INSERT INTO learning_archives(created_at, event_count, artifact_location, content_hash, policy_version, "
            "preserved_signal, dropped_detail) VALUES(?, ?, ?, ?, 'legacy-import-1', ?, ?)",
            (now(), len(normalized), artifact_location, content_hash,
             "validated legacy structured events imported into the canonical database",
             "unresolvable optional foreign-key links were omitted"),
        )


def validate_db(conn: sqlite3.Connection) -> None:
    errors: list[str] = []
    foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        errors.append(f"foreign key violations={len(foreign_key_errors)}")
    columns = set(column_names(conn))
    if not columns:
        errors.append("no active columns")
    task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    for row in conn.execute("SELECT id, column_name FROM tasks"):
        if row["column_name"] not in columns:
            errors.append(f"{row['id']}: invalid column {row['column_name']}")
    for row in conn.execute("SELECT name, required_rules_json FROM columns"):
        try:
            rules = json_loads(row["required_rules_json"], [])
        except json.JSONDecodeError:
            errors.append(f"{row['name']}: invalid required_rules_json")
            continue
        if not isinstance(rules, list):
            errors.append(f"{row['name']}: required rules must be a list")
    for row in conn.execute("SELECT from_column, to_column FROM column_transitions"):
        if row["from_column"] not in columns:
            errors.append(f"transition from inactive/unknown column {row['from_column']}")
        if row["to_column"] not in columns:
            errors.append(f"transition to inactive/unknown column {row['to_column']}")
    for row in conn.execute("SELECT column_name, limit_value FROM column_wip_limits"):
        if row["column_name"] not in columns:
            errors.append(f"WIP limit for inactive/unknown column {row['column_name']}")
        if row["limit_value"] < 1:
            errors.append(f"{row['column_name']}: WIP limit must be a positive integer")
    for row in conn.execute("SELECT column_name, target_value FROM backfill_goals"):
        if row["column_name"] not in columns:
            errors.append(f"backfill goal for inactive/unknown column {row['column_name']}")
        if row["target_value"] < 0:
            errors.append(f"{row['column_name']}: backfill goal target must be non-negative")
    for row in conn.execute("SELECT id, status FROM backlog_ideas"):
        if row["status"] not in BACKLOG_STATUSES:
            errors.append(f"{row['id']}: invalid backlog status {row['status']}")
    duplicate_themes = conn.execute(
        """
        SELECT task_id, theme, COUNT(*) AS n
        FROM task_themes GROUP BY task_id, theme HAVING n > 1
        """
    ).fetchall()
    if duplicate_themes:
        errors.append("duplicate task themes")
    for row in conn.execute("SELECT id, kind, state, closure FROM intents"):
        try:
            require_intent_kind(row["kind"])
            require_intent_state(row["state"])
            require_intent_closure(row["state"], row["closure"])
        except SystemExit:
            errors.append(f"{row['id']}: invalid intent lifecycle")
    for row in conn.execute("SELECT id, status, intent_id, task_id, options_json, default_option FROM decisions"):
        if row["status"] not in {"open", "resolved", "withdrawn"}:
            errors.append(f"{row['id']}: invalid decision status {row['status']}")
        try:
            options = json_loads(row["options_json"], [])
        except json.JSONDecodeError:
            errors.append(f"{row['id']}: invalid decision options_json")
            continue
        if not isinstance(options, list):
            errors.append(f"{row['id']}: decision options must be a list")
        if row["default_option"] and options and row["default_option"] not in options:
            errors.append(f"{row['id']}: decision default is not a declared option")
        if row["intent_id"] is None and row["task_id"] is None:
            errors.append(f"{row['id']}: decision must link to an intent or task")
    intent_links_enforced = conn.execute("SELECT value FROM meta WHERE key = 'intent_links_enforced'").fetchone()
    if intent_links_enforced and intent_links_enforced["value"] == "1":
        for row in conn.execute("SELECT t.id FROM tasks t WHERE t.column_name = 'Ready' AND NOT EXISTS (SELECT 1 FROM intent_work_links l WHERE l.task_id = t.id)"):
            errors.append(f"{row['id']}: Ready task has no intent link")
    for row in conn.execute(
        "SELECT id, payload_json, storage_class, redaction_state FROM learning_events"
    ):
        try:
            payload = json_loads(row["payload_json"], {})
        except json.JSONDecodeError:
            errors.append(f"learning event {row['id']}: invalid payload_json")
            continue
        if not isinstance(payload, dict):
            errors.append(f"learning event {row['id']}: payload must be an object")
        if row["storage_class"] not in {"database", "external-artifact"}:
            errors.append(f"learning event {row['id']}: invalid storage class")
        if row["redaction_state"] not in {"redacted", "not-sensitive", "needs-review"}:
            errors.append(f"learning event {row['id']}: invalid redaction state")
    for row in conn.execute("SELECT id, artifact_location FROM learning_archives"):
        location = Path(row["artifact_location"])
        if location.is_absolute() or ".." in location.parts:
            errors.append(f"learning archive {row['id']}: location is not project-relative")
    if errors:
        fail("; ".join(errors), 1)
    intent_count = conn.execute("SELECT COUNT(*) FROM intents").fetchone()[0]
    print(f"PASS kanban db valid intents={intent_count} tasks={task_count}")


def intent_add(conn: sqlite3.Connection, intent_id: str, summary: str, kind: str) -> None:
    require_intent_kind(kind)
    timestamp = now()
    raw = {"id": intent_id, "summary": summary, "kind": kind, "state": "captured"}
    with write_transaction(conn):
        conn.execute("INSERT INTO intents(id, summary, kind, state, raw_json, created_at, updated_at) VALUES(?, ?, ?, 'captured', ?, ?, ?)", (intent_id, summary, kind, json_dumps(raw), timestamp, timestamp))
    print(f"created intent {intent_id}")


def intent_list(conn: sqlite3.Connection, state: str | None, kind: str | None) -> None:
    if state:
        require_intent_state(state)
    if kind:
        require_intent_kind(kind)
    clauses, params = [], []
    if state:
        clauses.append("state = ?")
        params.append(state)
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    for row in conn.execute(f"SELECT id, kind, state, summary FROM intents{where} ORDER BY id", params):
        print(f"{row['state']}\t{row['id']}\t{row['kind']}\t{row['summary']}")


def intent_show(conn: sqlite3.Connection, intent_id: str) -> None:
    row = conn.execute("SELECT * FROM intents WHERE id = ?", (intent_id,)).fetchone()
    if row is None:
        fail(f"Unknown intent: {intent_id}")
    print(json.dumps(dict(row), indent=2, sort_keys=True))


def intent_status(conn: sqlite3.Connection, intent_id: str, state: str, closure: str | None, reason: str | None) -> None:
    require_intent_state(state)
    require_intent_closure(state, closure)
    with write_transaction(conn):
        row = conn.execute("SELECT raw_json FROM intents WHERE id = ?", (intent_id,)).fetchone()
        if row is None:
            fail(f"Unknown intent: {intent_id}")
        raw = json_loads(row["raw_json"], {})
        raw.update({"state": state, "closure": closure})
        if reason:
            raw["closure_reason"] = reason
        conn.execute("UPDATE intents SET state = ?, closure = ?, raw_json = ?, updated_at = ? WHERE id = ?", (state, closure, json_dumps(raw), now(), intent_id))


def intent_link(conn: sqlite3.Connection, intent_id: str, task_id: str, remove: bool = False) -> None:
    if conn.execute("SELECT 1 FROM intents WHERE id = ?", (intent_id,)).fetchone() is None:
        fail(f"Unknown intent: {intent_id}")
    if conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone() is None:
        fail(f"Unknown task: {task_id}")
    with write_transaction(conn):
        if remove:
            conn.execute("DELETE FROM intent_work_links WHERE intent_id = ? AND task_id = ?", (intent_id, task_id))
        else:
            conn.execute("INSERT OR IGNORE INTO intent_work_links(intent_id, task_id) VALUES(?, ?)", (intent_id, task_id))


def intent_work(conn: sqlite3.Connection, intent_id: str) -> None:
    if conn.execute("SELECT 1 FROM intents WHERE id = ?", (intent_id,)).fetchone() is None:
        fail(f"Unknown intent: {intent_id}")
    for row in conn.execute("SELECT t.id, t.column_name, t.goal FROM tasks t JOIN intent_work_links l ON l.task_id = t.id WHERE l.intent_id = ? ORDER BY t.id", (intent_id,)):
        print(f"{row['column_name']}\t{row['id']}\t{row['goal'] or ''}")


def reference_add(
    conn: sqlite3.Connection,
    reference_id: str,
    url: str,
    topics: list[str],
    title: str | None,
    publisher: str | None,
    published_at: str | None,
    reference_type: str | None,
    content_hash: str | None,
) -> None:
    url = url.split("#", 1)[0]
    with write_transaction(conn):
        existing = conn.execute(
            "SELECT id FROM research_references WHERE url = ? AND COALESCE(content_hash, '') = COALESCE(?, '') ORDER BY id LIMIT 1",
            (url, content_hash),
        ).fetchone()
        if existing is not None:
            print(f"existing reference {existing['id']}")
            return
        timestamp = now()
        conn.execute(
            "INSERT INTO research_references(id, url, title, publisher, published_at, reference_type, retrieved_at, topics_json, content_hash, created_at, updated_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (reference_id, url, title, publisher, published_at, reference_type, str(timestamp), json_dumps(topics), content_hash, timestamp, timestamp),
        )
    print(f"created reference {reference_id}")


def reference_review(
    conn: sqlite3.Connection,
    reference_id: str,
    summary: str,
    relevance: str,
    constraints: str | None,
) -> None:
    with write_transaction(conn):
        row = conn.execute(
            "SELECT 1 FROM research_references WHERE id = ?", (reference_id,)
        ).fetchone()
        if row is None:
            fail(f"Unknown reference: {reference_id}")
        conn.execute(
            "UPDATE research_references SET summary = ?, relevance = ?, constraints = ?, review_state = 'reviewed', updated_at = ? WHERE id = ?",
            (summary, relevance, constraints, now(), reference_id),
        )
    print(f"reviewed reference {reference_id}")


def reference_list(conn: sqlite3.Connection, review_state: str | None, topic: str | None) -> None:
    clauses, params = [], []
    if review_state:
        clauses.append("review_state = ?")
        params.append(review_state)
    if topic:
        clauses.append("topics_json LIKE ?")
        params.append(f"%{topic}%")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    for row in conn.execute(f"SELECT id, url, review_state, retrieved_at FROM research_references{where} ORDER BY id", params):
        print(f"{row['review_state']}\t{row['id']}\t{row['retrieved_at']}\t{row['url']}")


def reference_link(conn: sqlite3.Connection, reference_id: str, target_id: str, task: bool) -> None:
    if conn.execute("SELECT 1 FROM research_references WHERE id = ?", (reference_id,)).fetchone() is None:
        fail(f"Unknown reference: {reference_id}")
    table = "reference_tasks" if task else "reference_intents"
    target_table = "tasks" if task else "intents"
    target_column = "task_id" if task else "intent_id"
    if conn.execute(f"SELECT 1 FROM {target_table} WHERE id = ?", (target_id,)).fetchone() is None:
        fail(f"Unknown {'task' if task else 'intent'}: {target_id}")
    with write_transaction(conn):
        conn.execute(f"INSERT OR IGNORE INTO {table}(reference_id, {target_column}) VALUES(?, ?)", (reference_id, target_id))


def migrate_references(conn: sqlite3.Connection) -> None:
    url_pattern = re.compile(r"https?://[^\s)>\]\"']+")
    sources = [
        ("backlog_ideas", "backlog_idea", "id", "raw_json", ""),
        ("tasks", "task", "id", "raw_json", ""),
        ("learning_events", "learning_event", "id", "payload_json", "task_id"),
        ("task_events", "task_event", "event_id", "message", "task_id"),
        ("clarifications", "clarification", "id", "question", "task_id"),
        ("principles", "principle", "id", "raw_json", ""),
    ]
    discovered = 0
    created = 0
    linked = 0
    for table, label, id_column, text_column, task_column in sources:
        for row in conn.execute(f"SELECT * FROM {table}"):
            text_value = str(row[text_column] or "")
            for raw_url in url_pattern.findall(text_value):
                url = raw_url.rstrip(".,;:")
                discovered += 1
                reference_id = "legacy-ref-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
                with write_transaction(conn):
                    existing = conn.execute("SELECT id FROM research_references WHERE url = ?", (url.split("#", 1)[0],)).fetchone()
                    if existing is None:
                        timestamp = now()
                        provenance = {"discovered_from": label, "source_id": str(row[id_column]), "discovery_method": "legacy-url-scan"}
                        conn.execute("INSERT OR IGNORE INTO research_references(id, url, retrieved_at, provenance_json, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?)", (reference_id, url.split("#", 1)[0], str(timestamp), json_dumps(provenance), timestamp, timestamp))
                        created += 1
                        reference_id = reference_id
                    else:
                        reference_id = existing["id"]
                    if task_column and row[task_column] is not None:
                        conn.execute("INSERT OR IGNORE INTO reference_tasks(reference_id, task_id) VALUES(?, ?)", (reference_id, row[task_column]))
                        linked += 1
    print(f"references discovered={discovered} created={created} linked={linked}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")

    p_legacy_import = sub.add_parser(
        "legacy-import",
        help="Read a legacy YAML/JSON backlog or queue file and migrate it into SQLite.",
    )
    p_legacy_import.add_argument("path", type=Path)
    p_legacy_import.add_argument("--kind", choices=("auto", "tasks", "backlog"), default="auto")

    p_status = sub.add_parser("status")
    p_status.add_argument("--all", action="store_true")

    p_validate = sub.add_parser("validate")

    p_goal = sub.add_parser("goal")
    goal_sub = p_goal.add_subparsers(dest="goal_cmd", required=True)
    p_goal_capture = goal_sub.add_parser("capture")
    p_goal_capture.add_argument("intent_id")
    p_goal_capture.add_argument("objective")
    p_goal_capture.add_argument("--kind", choices=INTENT_KINDS, default="opportunity")
    p_goal_capture.add_argument("--success-criterion", action="append", default=[])
    p_goal_capture.add_argument("--constraint", action="append", default=[])
    p_goal_capture.add_argument("--non-goal", action="append", default=[])
    p_goal_capture.add_argument(
        "--autonomy", choices=("plan-only", "background", "queue-drain"), default="background"
    )
    p_goal_capture.add_argument("--stop-condition", action="append", default=[])

    p_migrate = sub.add_parser("migrate")
    migrate_sub = p_migrate.add_subparsers(dest="migrate_cmd", required=True)
    migrate_sub.add_parser("references")

    p_config = sub.add_parser("config")
    config_sub = p_config.add_subparsers(dest="config_cmd", required=True)
    config_sub.add_parser("list")
    p_config_set = config_sub.add_parser("set")
    config_set_sub = p_config_set.add_subparsers(dest="config_set_cmd", required=True)
    p_config_set_wip = config_set_sub.add_parser("wip_limit")
    p_config_set_wip.add_argument("-C", "--column", required=True)
    p_config_set_wip.add_argument("-L", "--limit", required=True, type=int)
    p_config_set_backfill = config_set_sub.add_parser("backfill_goal")
    p_config_set_backfill.add_argument("-C", "--column", required=True)
    p_config_set_backfill.add_argument("-T", "--target", required=True, type=int)
    p_config_set_backfill.add_argument("--description")

    p_task = sub.add_parser("task")
    task_sub = p_task.add_subparsers(dest="task_cmd", required=True)
    p_task_list = task_sub.add_parser("list")
    p_task_list.add_argument("--column")
    p_task_list.add_argument("--theme")
    p_task_show = task_sub.add_parser("show")
    p_task_show.add_argument("task_id")
    p_task_add = task_sub.add_parser(
        "add",
        help="Create an executable task and link it to one or more existing intents.",
    )
    p_task_add.add_argument("task_id")
    p_task_add.add_argument("goal")
    p_task_add.add_argument("--column", default="Backlog")
    p_task_add.add_argument("--owner", default="unassigned")
    p_task_add.add_argument("--scope")
    p_task_add.add_argument("--theme", action="append", default=[])
    p_task_add.add_argument("--dependency", action="append", default=[])
    p_task_add.add_argument("--intent", action="append", required=True)
    p_task_add.add_argument("--exit-criterion", action="append", default=[])
    p_task_add.add_argument("--validation", action="append", default=[])
    p_task_add.add_argument("--plan")
    p_task_move = task_sub.add_parser("move")
    p_task_move.add_argument("task_id")
    p_task_move.add_argument("column")
    p_task_move.add_argument("--owner")
    p_task_validation = task_sub.add_parser("validation")
    p_task_validation.add_argument("task_id")
    p_task_validation.add_argument("status")
    p_task_validation.add_argument("--evidence")
    p_task_blocker = task_sub.add_parser("blocker")
    task_blocker_sub = p_task_blocker.add_subparsers(dest="task_blocker_cmd", required=True)
    p_task_blocker_add = task_blocker_sub.add_parser("add")
    p_task_blocker_add.add_argument("task_id")
    p_task_blocker_add.add_argument("blocked_by")
    p_task_blocker_add.add_argument("--reason")
    p_task_blocker_remove = task_blocker_sub.add_parser("remove")
    p_task_blocker_remove.add_argument("task_id")
    p_task_blocker_remove.add_argument("blocked_by")
    p_task_review = task_sub.add_parser("review")
    task_review_sub = p_task_review.add_subparsers(dest="task_review_cmd", required=True)
    p_task_review_start = task_review_sub.add_parser("start")
    p_task_review_start.add_argument("task_id")
    p_task_review_start.add_argument("--worker", required=True)
    p_task_review_start.add_argument("--agent-id")
    p_task_review_start.add_argument("--note")
    p_task_review_accept = task_review_sub.add_parser("accept")
    p_task_review_accept.add_argument("task_id")
    p_task_review_accept.add_argument("--worker")
    p_task_review_accept.add_argument("--agent-id")
    p_task_review_accept.add_argument("--evidence", action="append", default=[])
    p_task_review_rework = task_review_sub.add_parser("rework")
    p_task_review_rework.add_argument("task_id")
    p_task_review_rework.add_argument("--worker")
    p_task_review_rework.add_argument("--agent-id")
    p_task_review_rework.add_argument("--finding", action="append", default=[])
    p_task_event = task_sub.add_parser("event")
    task_event_sub = p_task_event.add_subparsers(dest="task_event_cmd", required=True)
    p_task_event_add = task_event_sub.add_parser("add")
    p_task_event_add.add_argument("task_id")
    p_task_event_add.add_argument("--type", required=True)
    p_task_event_add.add_argument("--message", required=True)
    p_task_metadata = task_sub.add_parser("metadata")
    task_metadata_sub = p_task_metadata.add_subparsers(dest="task_metadata_cmd", required=True)
    p_task_metadata_add = task_metadata_sub.add_parser("add")
    p_task_metadata_add.add_argument("task_id")
    p_task_metadata_add.add_argument("key")
    p_task_metadata_add.add_argument("value")
    p_task_metadata_remove = task_metadata_sub.add_parser("remove")
    p_task_metadata_remove.add_argument("task_id")
    p_task_metadata_remove.add_argument("key")
    p_task_dependency = task_sub.add_parser("dependency")
    task_dependency_sub = p_task_dependency.add_subparsers(dest="task_dependency_cmd", required=True)
    p_task_dependency_add = task_dependency_sub.add_parser("add")
    p_task_dependency_add.add_argument("task_id")
    p_task_dependency_add.add_argument("dependency")
    p_task_dependency_remove = task_dependency_sub.add_parser("remove")
    p_task_dependency_remove.add_argument("task_id")
    p_task_dependency_remove.add_argument("dependency")
    p_task_dependency_list = task_dependency_sub.add_parser("list")
    p_task_dependency_list.add_argument("task_id")
    p_task_priority = task_sub.add_parser("priority")
    task_priority_sub = p_task_priority.add_subparsers(dest="task_priority_cmd", required=True)
    p_task_priority_set = task_priority_sub.add_parser("set")
    p_task_priority_set.add_argument("task_id")
    p_task_priority_set.add_argument("--value", required=True, type=int)
    p_task_priority_set.add_argument("--reason", required=True)
    p_task_priority_bump = task_priority_sub.add_parser("bump")
    p_task_priority_bump.add_argument("task_id")
    p_task_priority_bump.add_argument("--reason", required=True)
    p_task_conformance = task_sub.add_parser("conformance")
    p_task_conformance.add_argument("task_id")

    p_run = sub.add_parser("run")
    run_sub = p_run.add_subparsers(dest="run_cmd", required=True)
    p_run_start = run_sub.add_parser("start")
    p_run_start.add_argument("run_id")
    p_run_start.add_argument("--intent")
    p_run_start.add_argument("--task")
    p_run_start.add_argument("--worker", required=True)
    p_run_start.add_argument("--attempt", type=int, default=1)
    p_run_envelope = run_sub.add_parser("envelope")
    p_run_envelope.add_argument("run_id")
    p_run_envelope.add_argument("policy_json")
    p_run_envelope.add_argument("--granted-by", required=True)
    p_run_checkpoint = run_sub.add_parser("checkpoint")
    p_run_checkpoint.add_argument("run_id")
    p_run_checkpoint.add_argument("checkpoint")
    p_run_checkin = run_sub.add_parser("checkin")
    p_run_checkin.add_argument("run_id")
    p_run_checkin.add_argument("state", choices=RUN_WORKER_STATES)
    p_run_checkin.add_argument("--progress", required=True)
    p_run_checkin.add_argument("--next-action")
    p_run_checkin.add_argument("--expected-next-at", type=int)
    p_run_checkin.add_argument("--blocker")
    p_run_checkin.add_argument("--evidence")
    p_run_checkin.add_argument("--idempotency-key", required=True)
    p_run_cancel = run_sub.add_parser("cancel")
    p_run_cancel.add_argument("run_id")
    p_run_cancel.add_argument("--acknowledge", action="store_true")
    p_run_status = run_sub.add_parser("status")
    p_run_status.add_argument("run_id")
    p_run_status.add_argument("status", choices=RUN_STATUSES)

    p_gate = sub.add_parser("gate")
    gate_sub = p_gate.add_subparsers(dest="gate_cmd", required=True)
    p_gate_require = gate_sub.add_parser("require")
    p_gate_require.add_argument("gate_id")
    p_gate_require.add_argument("task_id")
    p_gate_require.add_argument("gate_type")
    p_gate_require.add_argument("--not-applicable", action="store_true")
    p_gate_require.add_argument("--undetermined", action="store_true")
    p_gate_require.add_argument("--rationale")
    p_gate_record = gate_sub.add_parser("record")
    p_gate_record.add_argument("gate_id")
    p_gate_record.add_argument("status", choices=("pass", "fail", "blocked", "not-applicable"))
    p_gate_record.add_argument("--evaluator", required=True)
    p_gate_record.add_argument("--independent", action="store_true")
    p_gate_record.add_argument("--rationale")
    p_gate_record.add_argument("--rework-destination")

    p_handoff = sub.add_parser("handoff")
    handoff_sub = p_handoff.add_subparsers(dest="handoff_cmd", required=True)
    p_handoff_validate = handoff_sub.add_parser("validate")
    p_handoff_validate.add_argument("document", type=Path)
    p_handoff_validate.add_argument("--expected-task")
    p_handoff_validate.add_argument("--expected-run")
    p_handoff_ingest = handoff_sub.add_parser("ingest")
    p_handoff_ingest.add_argument("document", type=Path)
    p_handoff_ingest.add_argument("--expected-task")
    p_handoff_ingest.add_argument("--expected-run")
    p_handoff_show = handoff_sub.add_parser("show")
    p_handoff_show.add_argument("handoff_id")
    p_handoff_list = handoff_sub.add_parser("list")
    p_handoff_list.add_argument("--task")

    p_specialist = sub.add_parser("specialist")
    specialist_sub = p_specialist.add_subparsers(dest="specialist_cmd", required=True)
    p_specialist_class = specialist_sub.add_parser("class")
    specialist_class_sub = p_specialist_class.add_subparsers(dest="specialist_class_cmd", required=True)
    p_specialist_class_add = specialist_class_sub.add_parser("add")
    p_specialist_class_add.add_argument("class_id")
    p_specialist_class_add.add_argument("title")
    p_specialist_class_add.add_argument("role_context")
    p_specialist_class_add.add_argument("--description")
    p_specialist_class_update = specialist_class_sub.add_parser("update")
    p_specialist_class_update.add_argument("class_id")
    p_specialist_class_update.add_argument("title")
    p_specialist_class_update.add_argument("role_context")
    p_specialist_class_update.add_argument("--description")
    p_specialist_class_list = specialist_class_sub.add_parser("list")
    p_specialist_class_list.add_argument("--all", action="store_true")
    p_specialist_class_show = specialist_class_sub.add_parser("show")
    p_specialist_class_show.add_argument("class_id")
    p_specialist_class_show.add_argument("--context-only", action="store_true")
    p_specialist_class_show.add_argument("--version", type=int)
    p_specialist_gate = specialist_sub.add_parser("gate")
    specialist_gate_sub = p_specialist_gate.add_subparsers(dest="specialist_gate_cmd", required=True)
    p_specialist_gate_require = specialist_gate_sub.add_parser("require")
    p_specialist_gate_require.add_argument("gate_id")
    p_specialist_gate_require.add_argument("class_id")
    p_specialist_gate_require.add_argument("engagement_role", choices=("inform", "produce", "review"))
    p_specialist_gate_require.add_argument("--rationale", required=True)
    p_specialist_gate_list = specialist_gate_sub.add_parser("list")
    p_specialist_gate_list.add_argument("gate_id")

    p_review = sub.add_parser("review")
    review_sub = p_review.add_subparsers(dest="review_cmd", required=True)
    p_review_profile = review_sub.add_parser("profile")
    review_profile_sub = p_review_profile.add_subparsers(dest="review_profile_cmd", required=True)
    p_review_profile_set = review_profile_sub.add_parser("set")
    p_review_profile_set.add_argument("task_id")
    p_review_profile_set.add_argument("work_type")
    p_review_profile_set.add_argument("lifecycle_stage", choices=("Discover", "Design", "Implement", "Verify", "Deliver", "Observe"))
    p_review_profile_set.add_argument("--artifact-kind", action="append", default=[])
    p_review_profile_set.add_argument("--risk-attribute", action="append", default=[])
    p_review_profile_set.add_argument("--classified-by", required=True)
    p_review_profile_set.add_argument("--rationale", required=True)
    p_review_profile_show = review_profile_sub.add_parser("show")
    p_review_profile_show.add_argument("task_id")
    p_review_plan = review_sub.add_parser("plan")
    review_plan_sub = p_review_plan.add_subparsers(dest="review_plan_cmd", required=True)
    p_review_plan_create = review_plan_sub.add_parser("create")
    p_review_plan_create.add_argument("plan_id")
    p_review_plan_create.add_argument("task_id")
    p_review_plan_create.add_argument("--policy", default="standard-excellence")
    p_review_plan_create.add_argument("--policy-version", type=int, default=1)
    p_review_plan_show = review_plan_sub.add_parser("show")
    p_review_plan_show.add_argument("plan_id")
    p_review_plan_list = review_plan_sub.add_parser("list")
    p_review_plan_list.add_argument("--task")

    p_guidance = sub.add_parser("guidance")
    guidance_sub = p_guidance.add_subparsers(dest="guidance_cmd", required=True)
    p_guidance_show = guidance_sub.add_parser("show")
    p_guidance_show.add_argument("snapshot_id")

    p_obligation = sub.add_parser("obligation")
    obligation_sub = p_obligation.add_subparsers(dest="obligation_cmd", required=True)
    p_obligation_add = obligation_sub.add_parser("add")
    p_obligation_add.add_argument("obligation_id")
    p_obligation_add.add_argument("snapshot_id")
    p_obligation_add.add_argument("tenet_id")
    p_obligation_add.add_argument("obligation_type", choices=(
        "acceptance-criterion", "design-constraint", "decision", "fitness-function", "test",
        "policy-control", "delivery-safeguard", "observability", "operational-readiness", "risk-disposition",
    ))
    p_obligation_add.add_argument("summary")
    p_obligation_add.add_argument("lifecycle_stage", choices=("Discover", "Design", "Implement", "Verify", "Deliver", "Observe"))
    p_obligation_add.add_argument("--verification", required=True)
    p_obligation_add.add_argument("--owner", required=True)
    p_obligation_add.add_argument("--artifact")
    p_obligation_add.add_argument("--review-plan-item")
    p_obligation_satisfy = obligation_sub.add_parser("satisfy")
    p_obligation_satisfy.add_argument("obligation_id")
    p_obligation_satisfy.add_argument("evidence_id")

    p_evidence = sub.add_parser("evidence")
    evidence_sub = p_evidence.add_subparsers(dest="evidence_cmd", required=True)
    p_evidence_add = evidence_sub.add_parser("add")
    p_evidence_add.add_argument("evidence_id")
    p_evidence_add.add_argument("task_id")
    p_evidence_add.add_argument("criterion_id")
    p_evidence_add.add_argument("artifact")
    p_evidence_add.add_argument("revision")
    p_evidence_add.add_argument("probe")
    p_evidence_add.add_argument("result", choices=("pass", "fail", "inconclusive"))
    p_evidence_add.add_argument("--producer", required=True)
    p_evidence_add.add_argument("--gate")
    p_evidence_add.add_argument("--environment")
    p_evidence_add.add_argument("--location")
    p_evidence_add.add_argument("--content-hash")

    p_receipt = sub.add_parser("receipt")
    receipt_sub = p_receipt.add_subparsers(dest="receipt_cmd", required=True)
    p_receipt_add = receipt_sub.add_parser("add")
    p_receipt_add.add_argument("receipt_id")
    p_receipt_add.add_argument("run_id")
    p_receipt_add.add_argument("idempotency_key")
    p_receipt_add.add_argument("action_class")
    p_receipt_add.add_argument("target")
    p_receipt_add.add_argument("status", choices=("planned", "applied", "failed", "compensated"))
    p_receipt_add.add_argument("--receipt")

    p_event = sub.add_parser("event")
    event_sub = p_event.add_subparsers(dest="event_cmd", required=True)
    p_event_add = event_sub.add_parser("add")
    p_event_add.add_argument("event_type")
    p_event_add.add_argument("reason")
    p_event_add.add_argument("--context-track", choices=("execution", "reflection"), default="execution")
    p_event_add.add_argument("--outcome")
    p_event_add.add_argument("--payload", default="{}")
    p_event_add.add_argument("--redaction-state", choices=("redacted", "not-sensitive", "needs-review"), default="redacted")
    p_event_add.add_argument("--intent")
    p_event_add.add_argument("--task")
    p_event_add.add_argument("--run")
    p_event_add.add_argument("--decision")
    p_event_add.add_argument("--gate")
    p_event_add.add_argument("--evidence")
    p_event_add.add_argument("--reference")
    p_event_add.add_argument("--attempt-id")
    p_event_add.add_argument("--artifact-ref")
    p_event_add.add_argument("--commit-ref")
    p_event_add.add_argument("--reviewer")
    p_event_add.add_argument("--occurred-at", type=int)
    p_event_list = event_sub.add_parser("list")
    p_event_list.add_argument("--event-type")
    p_event_list.add_argument("--context-track", choices=("execution", "reflection"))
    p_event_list.add_argument("--task")
    p_event_list.add_argument("--intent")
    p_event_list.add_argument("--since", type=int)
    p_event_list.add_argument("--until", type=int)
    p_event_list.add_argument("--limit", type=int)
    p_event_list.add_argument("--json", action="store_true")

    p_metric = sub.add_parser("metric")
    metric_sub = p_metric.add_subparsers(dest="metric_cmd", required=True)
    p_metric_snapshot = metric_sub.add_parser("snapshot")
    p_metric_snapshot.add_argument("--scope-type", default="project")
    p_metric_snapshot.add_argument("--scope-id", default="")
    p_metric_list = metric_sub.add_parser("list")
    p_metric_list.add_argument("--name")
    p_metric_list.add_argument("--scope-id")

    p_archive = sub.add_parser("archive")
    archive_sub = p_archive.add_subparsers(dest="archive_cmd", required=True)
    p_archive_add = archive_sub.add_parser("add")
    p_archive_add.add_argument("artifact_location")
    p_archive_add.add_argument("content_hash")
    p_archive_add.add_argument("--event-start-id", type=int)
    p_archive_add.add_argument("--event-end-id", type=int)
    p_archive_add.add_argument("--event-count", type=int, required=True)
    p_archive_add.add_argument("--policy-version", required=True)
    p_archive_add.add_argument("--preserved-signal", required=True)
    p_archive_add.add_argument("--dropped-detail", required=True)

    p_column = sub.add_parser("column")
    column_sub = p_column.add_subparsers(dest="column_cmd", required=True)
    column_sub.add_parser("list")
    p_column_add = column_sub.add_parser("add")
    p_column_add.add_argument("name")
    p_column_add.add_argument("--position", type=int, required=True)
    p_column_add.add_argument("--description")
    p_column_add.add_argument("--required-rule", action="append", default=[])
    p_column_add.add_argument(
        "--direction",
        choices=("forward", "backward", "neutral", "terminal"),
        default="forward",
    )
    p_transition = column_sub.add_parser("transition")
    transition_sub = p_transition.add_subparsers(dest="transition_cmd", required=True)
    transition_sub.add_parser("list")
    p_transition_add = transition_sub.add_parser("add")
    p_transition_add.add_argument("from_column")
    p_transition_add.add_argument("to_column")
    p_transition_add.add_argument("--rule")

    p_backlog = sub.add_parser("backlog")
    backlog_sub = p_backlog.add_subparsers(dest="backlog_cmd", required=True)
    backlog_sub.add_parser("list")
    p_backlog_add = backlog_sub.add_parser("add")
    p_backlog_add.add_argument("idea_id")
    p_backlog_add.add_argument("summary")
    p_backlog_add.add_argument("--theme", action="append", default=[])
    p_backlog_show = backlog_sub.add_parser("show")
    p_backlog_show.add_argument("idea_id")
    p_backlog_status = backlog_sub.add_parser("status")
    p_backlog_status.add_argument("idea_id")
    p_backlog_status.add_argument("status", choices=BACKLOG_STATUSES)
    p_backlog_status.add_argument("--reason")
    p_backlog_status.add_argument("--note")
    p_backlog_update = backlog_sub.add_parser("update")
    p_backlog_update.add_argument("idea_id")
    p_backlog_update.add_argument("--summary")
    p_backlog_update.add_argument("--status", choices=BACKLOG_STATUSES)
    p_backlog_update.add_argument("--reason")
    p_backlog_update.add_argument("--note")
    p_backlog_dependency = backlog_sub.add_parser("dependency")
    backlog_dependency_sub = p_backlog_dependency.add_subparsers(dest="backlog_dependency_cmd", required=True)
    p_backlog_dependency_add = backlog_dependency_sub.add_parser("add")
    p_backlog_dependency_add.add_argument("idea_id")
    p_backlog_dependency_add.add_argument("dependency")
    p_backlog_dependency_remove = backlog_dependency_sub.add_parser("remove")
    p_backlog_dependency_remove.add_argument("idea_id")
    p_backlog_dependency_remove.add_argument("dependency")
    p_backlog_dependency_list = backlog_dependency_sub.add_parser("list")
    p_backlog_dependency_list.add_argument("idea_id")
    p_backlog_priority = backlog_sub.add_parser("priority")
    backlog_priority_sub = p_backlog_priority.add_subparsers(dest="backlog_priority_cmd", required=True)
    p_backlog_priority_set = backlog_priority_sub.add_parser("set")
    p_backlog_priority_set.add_argument("idea_id")
    p_backlog_priority_set.add_argument("--value", required=True, type=int)
    p_backlog_priority_set.add_argument("--reason", required=True)
    p_backlog_priority_bump = backlog_priority_sub.add_parser("bump")
    p_backlog_priority_bump.add_argument("idea_id")
    p_backlog_priority_bump.add_argument("--reason", required=True)

    p_intent = sub.add_parser("intent")
    intent_sub = p_intent.add_subparsers(dest="intent_cmd", required=True)
    p_intent_add = intent_sub.add_parser("add")
    p_intent_add.add_argument("intent_id")
    p_intent_add.add_argument("summary")
    p_intent_add.add_argument("--kind", choices=INTENT_KINDS, default="question")
    p_intent_list = intent_sub.add_parser("list")
    p_intent_list.add_argument("--state", choices=INTENT_STATES)
    p_intent_list.add_argument("--kind", choices=INTENT_KINDS)
    p_intent_show = intent_sub.add_parser("show")
    p_intent_show.add_argument("intent_id")
    p_intent_status = intent_sub.add_parser("status")
    p_intent_status.add_argument("intent_id")
    p_intent_status.add_argument("state", choices=INTENT_STATES)
    p_intent_status.add_argument("--closure", choices=INTENT_CLOSURES)
    p_intent_status.add_argument("--reason")
    p_intent_work = intent_sub.add_parser("work")
    p_intent_work.add_argument("intent_id")
    p_intent_link = intent_sub.add_parser("link")
    p_intent_link.add_argument("intent_id")
    p_intent_link.add_argument("task_id")
    p_intent_unlink = intent_sub.add_parser("unlink")
    p_intent_unlink.add_argument("intent_id")
    p_intent_unlink.add_argument("task_id")

    p_reference = sub.add_parser("reference")
    reference_sub = p_reference.add_subparsers(dest="reference_cmd", required=True)
    p_reference_add = reference_sub.add_parser("add")
    p_reference_add.add_argument("reference_id")
    p_reference_add.add_argument("url")
    p_reference_add.add_argument("--topic", action="append", default=[])
    p_reference_add.add_argument("--title")
    p_reference_add.add_argument("--publisher")
    p_reference_add.add_argument("--published-at")
    p_reference_add.add_argument("--type")
    p_reference_add.add_argument("--content-hash")
    p_reference_list = reference_sub.add_parser("list")
    p_reference_list.add_argument("--review-state", choices=("needs_review", "reviewed"))
    p_reference_list.add_argument("--topic")
    p_reference_link = reference_sub.add_parser("link")
    p_reference_link.add_argument("reference_id")
    p_reference_link.add_argument("target_id")
    p_reference_link.add_argument("--task", action="store_true")
    p_reference_review = reference_sub.add_parser("review")
    p_reference_review.add_argument("reference_id")
    p_reference_review.add_argument("--summary", required=True)
    p_reference_review.add_argument("--relevance", required=True)
    p_reference_review.add_argument("--constraints")

    p_clarify = sub.add_parser("clarify")
    clarify_sub = p_clarify.add_subparsers(dest="clarify_cmd", required=True)
    p_clarify_add = clarify_sub.add_parser("add")
    p_clarify_add.add_argument("question")
    p_clarify_add.add_argument("--task")
    p_clarify_add.add_argument("--default")
    p_clarify_list = clarify_sub.add_parser("list")
    p_clarify_list.add_argument("--status")
    p_clarify_answer = clarify_sub.add_parser("answer")
    p_clarify_answer.add_argument("clarification_id", type=int)
    p_clarify_answer.add_argument("answer")

    p_decision = sub.add_parser("decision")
    decision_sub = p_decision.add_subparsers(dest="decision_cmd", required=True)
    p_decision_add = decision_sub.add_parser("add")
    p_decision_add.add_argument("decision_id")
    p_decision_add.add_argument("question")
    p_decision_add.add_argument("--intent")
    p_decision_add.add_argument("--task")
    p_decision_add.add_argument("--option", action="append", default=[])
    p_decision_add.add_argument("--default")
    p_decision_add.add_argument("--impact")
    p_decision_list = decision_sub.add_parser("list")
    p_decision_list.add_argument("--status", choices=("open", "resolved", "withdrawn"))
    p_decision_resolve = decision_sub.add_parser("resolve")
    p_decision_resolve.add_argument("decision_id")
    p_decision_resolve.add_argument("answer")
    p_decision_resolve.add_argument("--rationale", required=True)
    p_decision_resolve.add_argument("--decided-by", default="user")

    p_principle = sub.add_parser("principle")
    principle_sub = p_principle.add_subparsers(dest="principle_cmd", required=True)
    p_principle_add = principle_sub.add_parser("add")
    p_principle_add.add_argument("theme")
    p_principle_add.add_argument("principle_id")
    p_principle_add.add_argument("statement")
    p_principle_add.add_argument("--outcome", required=True)
    p_principle_add.add_argument("--authority", choices=("normative", "methodological", "local-policy", "experimental"), default="local-policy")
    p_principle_add.add_argument("--rationale", required=True)
    p_principle_add.add_argument("--reference", action="append", default=[])
    principle_sub.add_parser("list")

    p_project = sub.add_parser("project")
    project_sub = p_project.add_subparsers(dest="project_cmd", required=True)
    p_project_specialists = project_sub.add_parser("specialists")
    p_project_specialists.add_argument("intent_id")

    p_guidance_proposal = sub.add_parser("guidance-proposal")
    guidance_proposal_sub = p_guidance_proposal.add_subparsers(dest="guidance_proposal_cmd", required=True)
    p_guidance_proposal_list = guidance_proposal_sub.add_parser("list")
    p_guidance_proposal_list.add_argument("intent_id")
    p_guidance_proposal_list.add_argument("--status", choices=("proposed", "accepted", "rejected", "superseded"))
    p_guidance_proposal_resolve = guidance_proposal_sub.add_parser("resolve")
    p_guidance_proposal_resolve.add_argument("proposal_id")
    p_guidance_proposal_resolve.add_argument("status", choices=("accepted", "rejected"))
    p_guidance_proposal_resolve.add_argument("--adopted-id")
    p_guidance_proposal_resolve.add_argument("--decision")

    p_codebase_review = sub.add_parser("codebase-review")
    codebase_review_sub = p_codebase_review.add_subparsers(dest="codebase_review_cmd", required=True)
    p_codebase_review_start = codebase_review_sub.add_parser("start")
    p_codebase_review_start.add_argument("review_id")
    p_codebase_review_start.add_argument("intent_id")
    p_codebase_review_start.add_argument("scope")
    p_codebase_review_start.add_argument("--objective", default="Review the existing codebase against the project goal and identify risks or deficiencies")
    p_codebase_review_start.add_argument("--owner", default="coordinator")

    p_bug = sub.add_parser("bug")
    bug_sub = p_bug.add_subparsers(dest="bug_cmd", required=True)
    p_bug_register = bug_sub.add_parser("register")
    p_bug_register.add_argument("bug_id")
    p_bug_register.add_argument("intent_id")
    p_bug_register.add_argument("summary")
    p_bug_register.add_argument("--observed", required=True)
    p_bug_register.add_argument("--expected", required=True)
    p_bug_register.add_argument("--reporter", required=True)
    p_bug_register.add_argument("--reproduction")
    p_bug_register.add_argument("--environment")
    p_bug_register.add_argument("--evidence", action="append", default=[])
    p_bug_assess = bug_sub.add_parser("assess")
    p_bug_assess.add_argument("bug_id")
    p_bug_assess.add_argument("class_id")
    p_bug_assess.add_argument("applicability", choices=("applicable", "not-applicable"))
    p_bug_assess.add_argument("--rationale", required=True)
    p_bug_assess.add_argument("--assessed-by", required=True)
    p_bug_assess.add_argument("--goal-impact", type=int)
    p_bug_assess.add_argument("--urgency", type=int)
    p_bug_assess.add_argument("--risk-summary")
    p_bug_prioritize = bug_sub.add_parser("prioritize")
    p_bug_prioritize.add_argument("bug_id")
    p_bug_prioritize.add_argument("rank", type=int)
    p_bug_prioritize.add_argument("--rationale", required=True)
    p_bug_action = bug_sub.add_parser("action")
    p_bug_action.add_argument("bug_id")
    p_bug_action.add_argument("task_id")
    p_bug_action.add_argument("--owner", required=True)
    p_bug_list = bug_sub.add_parser("list")
    p_bug_list.add_argument("--intent")
    p_bug_show = bug_sub.add_parser("show")
    p_bug_show.add_argument("bug_id")

    p_tenet = sub.add_parser("tenet")
    tenet_sub = p_tenet.add_subparsers(dest="tenet_cmd", required=True)
    tenet_sub.add_parser("list")
    p_tenet_store = tenet_sub.add_parser("store")
    p_tenet_store.add_argument("tenet_id")
    p_tenet_store.add_argument("theme")
    p_tenet_store.add_argument("title")
    p_tenet_store.add_argument("instruction")
    p_tenet_store.add_argument("--effect", required=True)
    p_tenet_store.add_argument("--strength", choices=("required", "advisory"), default="required")
    p_tenet_store.add_argument("--exception-authority", choices=("policy", "specialist", "human"), default="human")
    p_tenet_store.add_argument("--verification", required=True)
    p_tenet_store.add_argument("--principle", action="append", default=[])
    p_tenet_store.add_argument("--reference", action="append", default=[])
    p_tenet_store.add_argument("--not-experiment-eligible", action="store_true")
    p_tenet_store.add_argument("--draft", action="store_true")
    p_tenet_override = tenet_sub.add_parser("override")
    p_tenet_override.add_argument("override_id")
    p_tenet_override.add_argument("tenet_id")
    p_tenet_override.add_argument("disposition", choices=("required", "advisory", "not-applicable", "exception"))
    p_tenet_override.add_argument("scope_json")
    p_tenet_override.add_argument("--rationale", required=True)
    p_tenet_override.add_argument("--authorized-by", required=True)
    p_tenet_override.add_argument("--decision")
    p_tenet_override.add_argument("--expires-at", type=int)
    p_tenet_override.add_argument("--rollback-condition")

    p_experiment = sub.add_parser("experiment")
    experiment_sub = p_experiment.add_subparsers(dest="experiment_cmd", required=True)
    p_experiment_add = experiment_sub.add_parser("add")
    p_experiment_add.add_argument("experiment_id")
    p_experiment_add.add_argument("principle_id")
    p_experiment_add.add_argument("baseline_tenet")
    p_experiment_add.add_argument("variant_tenet")
    p_experiment_add.add_argument("problem")
    p_experiment_add.add_argument("hypothesis")
    p_experiment_add.add_argument("scope_json")
    p_experiment_add.add_argument("exclusions_json")
    p_experiment_add.add_argument("metrics_json")
    p_experiment_add.add_argument("--owner", required=True)
    p_experiment_add.add_argument("--rollback-condition", required=True)
    p_experiment_status = experiment_sub.add_parser("status")
    p_experiment_status.add_argument("experiment_id")
    p_experiment_status.add_argument("status", choices=("running", "evaluating", "promoted", "revised", "rolled-back", "cancelled"))
    p_experiment_status.add_argument("--outcome")
    p_experiment_status.add_argument("--decision")
    p_experiment_assign = experiment_sub.add_parser("assign")
    p_experiment_assign.add_argument("experiment_id")
    p_experiment_assign.add_argument("task_id")
    p_experiment_assign.add_argument("arm", choices=("baseline", "variant"))

    p_constraint = sub.add_parser("constraint")
    constraint_sub = p_constraint.add_subparsers(dest="constraint_cmd", required=True)
    p_constraint_set = constraint_sub.add_parser("set")
    p_constraint_set.add_argument("constraint_id")
    p_constraint_set.add_argument("goal_ref")
    p_constraint_set.add_argument("constraint_type", choices=("resource", "policy", "capability", "market", "unknown"))
    p_constraint_set.add_argument("constraint_ref")
    p_constraint_set.add_argument("--evidence", required=True)
    p_constraint_set.add_argument("--exploit", required=True)
    p_constraint_set.add_argument("--subordinate", required=True)
    p_constraint_set.add_argument("--elevate")
    p_constraint_set.add_argument("--owner", required=True)
    p_constraint_set.add_argument("--buffer-target", type=float)
    p_constraint_set.add_argument("--buffer-current", type=float)
    p_constraint_set.add_argument("--review-at", type=int)

    p_quality = sub.add_parser("quality-signal")
    quality_sub = p_quality.add_subparsers(dest="quality_cmd", required=True)
    p_quality_open = quality_sub.add_parser("open")
    p_quality_open.add_argument("signal_id")
    p_quality_open.add_argument("task_id")
    p_quality_open.add_argument("signal_type", choices=("abnormality", "escaped-defect", "process-failure", "constraint-starvation", "constraint-overload"))
    p_quality_open.add_argument("severity", choices=("advisory", "stop-affected-work", "stop-value-stream"))
    p_quality_open.add_argument("summary")
    p_quality_open.add_argument("--containment", required=True)
    p_quality_open.add_argument("--owner", required=True)
    p_quality_open.add_argument("--obligation")
    p_quality_resolve = quality_sub.add_parser("resolve")
    p_quality_resolve.add_argument("signal_id")
    p_quality_resolve.add_argument("--occurrence-cause", required=True)
    p_quality_resolve.add_argument("--escape-cause", required=True)
    p_quality_resolve.add_argument("--systemic-cause", required=True)
    p_quality_resolve.add_argument("--countermeasure", required=True)
    p_quality_resolve.add_argument("--recurrence-test", required=True)

    return parser


def dispatch(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    if args.cmd == "init":
        print(f"initialized {args.db}")
    elif args.cmd == "legacy-import":
        import_legacy(conn, args.path, args.kind)
    elif args.cmd == "status":
        status(conn, args.all)
    elif args.cmd == "validate":
        validate_db(conn)
    elif args.cmd == "goal":
        if args.goal_cmd == "capture":
            capture_goal(
                conn, args.intent_id, args.objective, args.kind,
                args.success_criterion, args.constraint, args.non_goal,
                args.autonomy, args.stop_condition,
            )
    elif args.cmd == "migrate":
        if args.migrate_cmd == "references":
            migrate_references(conn)
    elif args.cmd == "config":
        if args.config_cmd == "list":
            list_config(conn)
        elif args.config_cmd == "set":
            if args.config_set_cmd == "wip_limit":
                set_column_wip_limit(conn, args.column, args.limit)
            elif args.config_set_cmd == "backfill_goal":
                set_backfill_goal(conn, args.column, args.target, args.description)
    elif args.cmd == "task":
        if args.task_cmd == "add":
            add_task(
                conn,
                args.task_id,
                args.goal,
                args.column,
                args.owner,
                args.scope,
                args.theme,
                args.dependency,
                args.intent,
                args.exit_criterion,
                args.validation,
                args.plan,
            )
        elif args.task_cmd == "list":
            list_tasks(conn, args.column, args.theme)
        elif args.task_cmd == "show":
            show_task(conn, args.task_id)
        elif args.task_cmd == "move":
            task_move(conn, args.task_id, args.column, args.owner)
        elif args.task_cmd == "validation":
            task_set_validation(conn, args.task_id, args.status, args.evidence)
        elif args.task_cmd == "blocker":
            if args.task_blocker_cmd == "add":
                task_add_blocker(conn, args.task_id, args.blocked_by, args.reason)
            elif args.task_blocker_cmd == "remove":
                task_remove_blocker(conn, args.task_id, args.blocked_by)
        elif args.task_cmd == "review":
            if args.task_review_cmd == "start":
                task_review_start(conn, args.task_id, args.worker, args.agent_id, args.note)
            elif args.task_review_cmd == "accept":
                task_review_accept(conn, args.task_id, args.worker, args.agent_id, args.evidence)
            elif args.task_review_cmd == "rework":
                task_review_rework(conn, args.task_id, args.worker, args.agent_id, args.finding)
        elif args.task_cmd == "event":
            if args.task_event_cmd == "add":
                add_task_event(conn, args.task_id, args.type, args.message)
        elif args.task_cmd == "metadata":
            if args.task_metadata_cmd == "add":
                task_add_metadata(conn, args.task_id, args.key, args.value)
            elif args.task_metadata_cmd == "remove":
                task_remove_metadata(conn, args.task_id, args.key)
        elif args.task_cmd == "dependency":
            if args.task_dependency_cmd == "add":
                task_add_dependency(conn, args.task_id, args.dependency)
            elif args.task_dependency_cmd == "remove":
                task_remove_dependency(conn, args.task_id, args.dependency)
            elif args.task_dependency_cmd == "list":
                task_list_dependencies(conn, args.task_id)
        elif args.task_cmd == "priority":
            if args.task_priority_cmd == "set":
                task_set_priority(conn, args.task_id, args.value, args.reason)
            elif args.task_priority_cmd == "bump":
                task_bump_priority(conn, args.task_id, args.reason)
        elif args.task_cmd == "conformance":
            task_conformance(conn, args.task_id)
    elif args.cmd == "run":
        if args.run_cmd == "start":
            run_start(conn, args.run_id, args.intent, args.task, args.worker, args.attempt)
        elif args.run_cmd == "envelope":
            envelope_set(conn, args.run_id, args.policy_json, args.granted_by)
        elif args.run_cmd == "checkpoint":
            run_checkpoint(conn, args.run_id, args.checkpoint)
        elif args.run_cmd == "checkin":
            run_checkin(conn, args.run_id, args.state, args.progress, args.next_action,
                        args.expected_next_at, args.blocker, args.evidence,
                        args.idempotency_key)
        elif args.run_cmd == "cancel":
            run_cancel(conn, args.run_id, args.acknowledge)
        elif args.run_cmd == "status":
            run_set_status(conn, args.run_id, args.status)
    elif args.cmd == "gate":
        if args.gate_cmd == "require":
            if args.not_applicable and args.undetermined:
                fail("Choose only one applicability override")
            applicability = "not-applicable" if args.not_applicable else (
                "undetermined" if args.undetermined else "applicable"
            )
            gate_require(conn, args.gate_id, args.task_id, args.gate_type,
                         applicability, args.rationale)
        elif args.gate_cmd == "record":
            gate_record(conn, args.gate_id, args.status, args.evaluator, args.independent,
                        args.rationale, args.rework_destination)
    elif args.cmd == "handoff":
        if args.handoff_cmd == "validate":
            document, document_hash = handoff_validate(
                conn, args.document, args.expected_task, args.expected_run
            )
            print(f"valid handoff {document['handoff_id']} hash={document_hash}")
        elif args.handoff_cmd == "ingest":
            handoff_ingest(conn, args.document, args.expected_task, args.expected_run)
        elif args.handoff_cmd == "show":
            handoff_show(conn, args.handoff_id)
        elif args.handoff_cmd == "list":
            handoff_list(conn, args.task)
    elif args.cmd == "specialist":
        if args.specialist_cmd == "class":
            if args.specialist_class_cmd == "add":
                specialist_class_add(
                    conn, args.class_id, args.title, args.role_context, args.description
                )
            elif args.specialist_class_cmd == "update":
                specialist_class_update(
                    conn, args.class_id, args.title, args.role_context, args.description
                )
            elif args.specialist_class_cmd == "list":
                specialist_class_list(conn, not args.all)
            elif args.specialist_class_cmd == "show":
                specialist_class_show(conn, args.class_id, args.context_only, args.version)
        elif args.specialist_cmd == "gate":
            if args.specialist_gate_cmd == "require":
                gate_specialist_require(
                    conn, args.gate_id, args.class_id, args.engagement_role, args.rationale
                )
            elif args.specialist_gate_cmd == "list":
                gate_specialist_list(conn, args.gate_id)
    elif args.cmd == "review":
        if args.review_cmd == "profile":
            if args.review_profile_cmd == "set":
                review_profile_set(
                    conn, args.task_id, args.work_type, args.lifecycle_stage,
                    args.artifact_kind, args.risk_attribute, args.classified_by, args.rationale,
                )
            elif args.review_profile_cmd == "show":
                review_profile_show(conn, args.task_id)
        elif args.review_cmd == "plan":
            if args.review_plan_cmd == "create":
                review_plan_create(conn, args.plan_id, args.task_id, args.policy, args.policy_version)
            elif args.review_plan_cmd == "show":
                review_plan_show(conn, args.plan_id)
            elif args.review_plan_cmd == "list":
                review_plan_list(conn, args.task)
    elif args.cmd == "guidance":
        if args.guidance_cmd == "show":
            guidance_show(conn, args.snapshot_id)
    elif args.cmd == "obligation":
        if args.obligation_cmd == "add":
            obligation_add(
                conn, args.obligation_id, args.snapshot_id, args.tenet_id,
                args.obligation_type, args.summary, args.lifecycle_stage,
                args.verification, args.owner, args.artifact, args.review_plan_item,
            )
        elif args.obligation_cmd == "satisfy":
            obligation_satisfy(conn, args.obligation_id, args.evidence_id)
    elif args.cmd == "evidence":
        if args.evidence_cmd == "add":
            evidence_add(conn, args.evidence_id, args.task_id, args.gate, args.criterion_id,
                         args.artifact, args.revision, args.probe, args.result, args.producer,
                         args.environment, args.location, args.content_hash)
    elif args.cmd == "receipt":
        if args.receipt_cmd == "add":
            receipt_add(conn, args.receipt_id, args.run_id, args.idempotency_key,
                        args.action_class, args.target, args.status, args.receipt)
    elif args.cmd == "event":
        if args.event_cmd == "add":
            learning_event_add(
                conn, args.event_type, args.reason, args.context_track, args.outcome,
                args.payload, args.redaction_state, args.intent, args.task, args.run,
                args.decision, args.gate, args.evidence, args.reference, args.attempt_id, args.artifact_ref,
                args.commit_ref, args.reviewer, args.occurred_at,
            )
        elif args.event_cmd == "list":
            learning_event_list(conn, args.event_type, args.context_track, args.task,
                                args.intent, args.since, args.until, args.limit, args.json)
    elif args.cmd == "metric":
        if args.metric_cmd == "snapshot":
            metric_snapshot(conn, args.scope_type, args.scope_id)
        elif args.metric_cmd == "list":
            metric_list(conn, args.name, args.scope_id)
    elif args.cmd == "archive":
        if args.archive_cmd == "add":
            learning_archive_add(
                conn, args.event_start_id, args.event_end_id, args.event_count,
                args.artifact_location, args.content_hash, args.policy_version,
                args.preserved_signal, args.dropped_detail,
            )
    elif args.cmd == "column":
        if args.column_cmd == "list":
            list_columns(conn)
        elif args.column_cmd == "add":
            add_column(
                conn,
                args.name,
                args.position,
                args.description,
                args.required_rule,
                args.direction,
            )
        elif args.column_cmd == "transition":
            if args.transition_cmd == "list":
                list_transitions(conn)
            elif args.transition_cmd == "add":
                add_transition(conn, args.from_column, args.to_column, args.rule)
    elif args.cmd == "backlog":
        if args.backlog_cmd == "list":
            list_backlog(conn)
        elif args.backlog_cmd == "add":
            add_backlog(conn, args.idea_id, args.summary, args.theme)
        elif args.backlog_cmd == "show":
            show_backlog(conn, args.idea_id)
        elif args.backlog_cmd == "status":
            update_backlog(conn, args.idea_id, args.status, None, args.reason, args.note)
        elif args.backlog_cmd == "update":
            if args.summary is None and args.status is None and args.reason is None and args.note is None:
                fail("backlog update requires at least one of --summary, --status, --reason, or --note")
            update_backlog(conn, args.idea_id, args.status, args.summary, args.reason, args.note)
        elif args.backlog_cmd == "dependency":
            if args.backlog_dependency_cmd == "add":
                backlog_add_dependency(conn, args.idea_id, args.dependency)
            elif args.backlog_dependency_cmd == "remove":
                backlog_remove_dependency(conn, args.idea_id, args.dependency)
            elif args.backlog_dependency_cmd == "list":
                backlog_list_dependencies(conn, args.idea_id)
        elif args.backlog_cmd == "priority":
            if args.backlog_priority_cmd == "set":
                backlog_set_priority(conn, args.idea_id, args.value, args.reason)
            elif args.backlog_priority_cmd == "bump":
                backlog_bump_priority(conn, args.idea_id, args.reason)
    elif args.cmd == "intent":
        if args.intent_cmd == "add":
            intent_add(conn, args.intent_id, args.summary, args.kind)
        elif args.intent_cmd == "list":
            intent_list(conn, args.state, args.kind)
        elif args.intent_cmd == "show":
            intent_show(conn, args.intent_id)
        elif args.intent_cmd == "status":
            intent_status(conn, args.intent_id, args.state, args.closure, args.reason)
        elif args.intent_cmd == "work":
            intent_work(conn, args.intent_id)
        elif args.intent_cmd == "link":
            intent_link(conn, args.intent_id, args.task_id)
        elif args.intent_cmd == "unlink":
            intent_link(conn, args.intent_id, args.task_id, remove=True)
    elif args.cmd == "reference":
        if args.reference_cmd == "add":
            reference_add(
                conn, args.reference_id, args.url, args.topic, args.title,
                args.publisher, args.published_at, args.type, args.content_hash,
            )
        elif args.reference_cmd == "list":
            reference_list(conn, args.review_state, args.topic)
        elif args.reference_cmd == "link":
            reference_link(conn, args.reference_id, args.target_id, args.task)
        elif args.reference_cmd == "review":
            reference_review(conn, args.reference_id, args.summary, args.relevance, args.constraints)
    elif args.cmd == "clarify":
        if args.clarify_cmd == "add":
            add_clarification(conn, args.task, args.question, args.default)
        elif args.clarify_cmd == "list":
            list_clarifications(conn, args.status)
        elif args.clarify_cmd == "answer":
            answer_clarification(conn, args.clarification_id, args.answer)
    elif args.cmd == "decision":
        if args.decision_cmd == "add":
            decision_add(
                conn, args.decision_id, args.question, args.intent, args.task,
                args.option, args.default, args.impact,
            )
        elif args.decision_cmd == "list":
            decision_list(conn, args.status)
        elif args.decision_cmd == "resolve":
            decision_resolve(conn, args.decision_id, args.answer, args.rationale, args.decided_by)
    elif args.cmd == "principle":
        if args.principle_cmd == "add":
            add_principle(
                conn, args.theme, args.principle_id, args.statement, args.outcome,
                args.authority, args.rationale, args.reference,
            )
        elif args.principle_cmd == "list":
            list_principles(conn)
    elif args.cmd == "project":
        if args.project_cmd == "specialists":
            enrollment_list(conn, args.intent_id)
    elif args.cmd == "guidance-proposal":
        if args.guidance_proposal_cmd == "list":
            guidance_proposal_list(conn, args.intent_id, args.status)
        elif args.guidance_proposal_cmd == "resolve":
            guidance_proposal_resolve(
                conn, args.proposal_id, args.status, args.adopted_id, args.decision,
            )
    elif args.cmd == "codebase-review":
        if args.codebase_review_cmd == "start":
            codebase_review_start(
                conn, args.review_id, args.intent_id, args.scope,
                args.objective, args.owner,
            )
    elif args.cmd == "bug":
        if args.bug_cmd == "register":
            bug_register(
                conn, args.bug_id, args.intent_id, args.summary, args.observed,
                args.expected, args.reporter, args.reproduction, args.environment,
                args.evidence,
            )
        elif args.bug_cmd == "assess":
            bug_assess(
                conn, args.bug_id, args.class_id, args.applicability,
                args.rationale, args.assessed_by, args.goal_impact,
                args.urgency, args.risk_summary,
            )
        elif args.bug_cmd == "prioritize":
            bug_prioritize(conn, args.bug_id, args.rank, args.rationale)
        elif args.bug_cmd == "action":
            bug_action(conn, args.bug_id, args.task_id, args.owner)
        elif args.bug_cmd == "list":
            bug_list(conn, args.intent)
        elif args.bug_cmd == "show":
            bug_show(conn, args.bug_id)
    elif args.cmd == "tenet":
        if args.tenet_cmd == "list":
            tenet_list(conn)
        elif args.tenet_cmd == "store":
            tenet_add_version(
                conn, args.tenet_id, args.theme, args.title, args.instruction,
                args.effect, args.strength, args.exception_authority,
                args.verification, args.principle, args.reference,
                not args.not_experiment_eligible, "draft" if args.draft else "active",
            )
        elif args.tenet_cmd == "override":
            tenet_override_add(
                conn, args.override_id, args.tenet_id, args.disposition,
                args.scope_json, args.rationale, args.authorized_by,
                args.decision, args.expires_at, args.rollback_condition,
            )
    elif args.cmd == "experiment":
        if args.experiment_cmd == "add":
            experiment_add(
                conn, args.experiment_id, args.principle_id, args.baseline_tenet,
                args.variant_tenet, args.problem, args.hypothesis, args.scope_json,
                args.exclusions_json, args.metrics_json, args.owner,
                args.rollback_condition,
            )
        elif args.experiment_cmd == "status":
            experiment_status(conn, args.experiment_id, args.status, args.outcome, args.decision)
        elif args.experiment_cmd == "assign":
            experiment_assign(conn, args.experiment_id, args.task_id, args.arm)
    elif args.cmd == "constraint":
        if args.constraint_cmd == "set":
            flow_constraint_set(
                conn, args.constraint_id, args.goal_ref, args.constraint_type,
                args.constraint_ref, args.evidence, args.exploit, args.subordinate,
                args.owner, args.elevate, args.buffer_target, args.buffer_current,
                args.review_at,
            )
    elif args.cmd == "quality-signal":
        if args.quality_cmd == "open":
            quality_signal_open(
                conn, args.signal_id, args.task_id, args.signal_type, args.severity,
                args.summary, args.containment, args.owner, args.obligation,
            )
        elif args.quality_cmd == "resolve":
            quality_signal_resolve(
                conn, args.signal_id, args.occurrence_cause, args.escape_cause,
                args.systemic_cause, args.countermeasure, args.recurrence_test,
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conn = connect(args.db)
    try:
        init_db(conn, args.schema)
        try:
            return dispatch(args, conn)
        except sqlite3.IntegrityError as exc:
            fail(f"Database invariant rejected the operation: {exc}")
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
