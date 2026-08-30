#!/usr/bin/env python3
"""SQLite-backed project kanban helper."""

from __future__ import annotations

import argparse
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
            "confidence >=99%",
            "scope_readiness >=99%",
            "success_criteria_readiness >=99%",
            "constraints_readiness >=99%",
            "implementation_plan_readiness >=99%",
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
    ("Ready", "Active", "worker available and 99% start gate satisfied"),
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
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', '5') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        ensure_default_columns(conn)
        ensure_default_wip_limits(conn)
        migrate_backfill_goals(conn)
        ensure_default_backfill_goals(conn)


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


def transition_allowed(conn: sqlite3.Connection, from_column: str, to_column: str) -> bool:
    if from_column == to_column:
        return True
    row = conn.execute(
        """
        SELECT 1 FROM column_transitions
        WHERE from_column = ? AND to_column = ?
        """,
        (from_column, to_column),
    ).fetchone()
    return row is not None


def task_exists(conn: sqlite3.Connection, task_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return row is not None


def backlog_exists(conn: sqlite3.Connection, idea_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM backlog_ideas WHERE id = ?", (idea_id,)).fetchone()
    return row is not None


def dependency_state(conn: sqlite3.Connection, dependency: str) -> tuple[str, str] | None:
    task = conn.execute(
        "SELECT column_name FROM tasks WHERE id = ?",
        (dependency,),
    ).fetchone()
    if task is not None:
        return ("task", task["column_name"])
    idea = conn.execute(
        "SELECT status FROM backlog_ideas WHERE id = ?",
        (dependency,),
    ).fetchone()
    if idea is not None:
        return ("backlog", idea["status"] or "")
    return None


def dependency_resolved(kind: str, state: str) -> bool:
    if kind == "task":
        return state == "Done"
    if kind == "backlog":
        return state == "done"
    return False


def unresolved_dependencies(conn: sqlite3.Connection, task_id: str) -> list[str]:
    unresolved: list[str] = []
    for row in conn.execute(
        "SELECT dependency FROM task_dependencies WHERE task_id = ? ORDER BY dependency",
        (task_id,),
    ):
        dependency = row["dependency"]
        state = dependency_state(conn, dependency)
        if state is None:
            continue
        kind, status = state
        if not dependency_resolved(kind, status):
            unresolved.append(f"{dependency} ({kind}:{status})")
    return unresolved


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
        from_column = row["column_name"]
        if not transition_allowed(conn, from_column, column):
            rules = column_rules(conn, column)
            suffix = f"; {column} requires: {', '.join(rules)}" if rules else ""
            fail(f"Transition not allowed: {from_column} -> {column}{suffix}")
        if column == "Active":
            blocked_by = unresolved_dependencies(conn, task_id)
            if blocked_by:
                fail("Cannot move to Active; unresolved dependencies: " + ", ".join(blocked_by))
        card = json_loads(row["raw_json"])
        card["column"] = column
        if owner is not None:
            card["owner"] = owner
        upsert_task(conn, card)
        conn.execute(
            "INSERT INTO task_events(task_id, event_type, message, created_at) VALUES(?, ?, ?, ?)",
            (task_id, "move", f"moved to {column}", now()),
        )


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


def add_task_event(conn: sqlite3.Connection, task_id: str | None, event_type: str, message: str) -> None:
    if task_id is not None and not task_exists(conn, task_id):
        fail(f"Unknown task: {task_id}")
    with write_transaction(conn):
        conn.execute(
            "INSERT INTO task_events(task_id, event_type, message, created_at) VALUES(?, ?, ?, ?)",
            (task_id, event_type, message, now()),
        )


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
        conn.execute(
            "INSERT INTO task_events(task_id, event_type, message, created_at) VALUES(?, ?, ?, ?)",
            (task_id, "dependency.add", f"blocked by {dependency}", now()),
        )


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
        conn.execute(
            "INSERT INTO task_events(task_id, event_type, message, created_at) VALUES(?, ?, ?, ?)",
            (task_id, "created", "Created with task add", now()),
        )
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


def add_principle(conn: sqlite3.Connection, theme: str, principle_id: str, statement: str) -> None:
    raw = {"id": principle_id, "statement": statement, "status": "active", "applies_to": [], "exceptions": []}
    with write_transaction(conn):
        conn.execute(
            """
            INSERT INTO principles(id, theme, statement, status, raw_json, updated_at)
            VALUES(?, ?, ?, 'active', ?, ?)
            """,
            (principle_id, theme, statement, json_dumps(raw), now()),
        )


def list_principles(conn: sqlite3.Connection) -> None:
    for row in conn.execute("SELECT theme, id, status, statement FROM principles ORDER BY theme, id"):
        print(f"{row['theme']}\t{row['id']}\t{row['status']}\t{row['statement']}")


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


def validate_db(conn: sqlite3.Connection) -> None:
    errors: list[str] = []
    columns = set(column_names(conn))
    if not columns:
        errors.append("no active columns")
    task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    if task_count == 0:
        errors.append("no tasks")
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
    intent_links_enforced = conn.execute("SELECT value FROM meta WHERE key = 'intent_links_enforced'").fetchone()
    if intent_links_enforced and intent_links_enforced["value"] == "1":
        for row in conn.execute("SELECT t.id FROM tasks t WHERE t.column_name = 'Ready' AND NOT EXISTS (SELECT 1 FROM intent_work_links l WHERE l.task_id = t.id)"):
            errors.append(f"{row['id']}: Ready task has no intent link")
    if errors:
        fail("; ".join(errors), 1)
    print(f"PASS kanban db valid tasks={task_count}")


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


def reference_add(conn: sqlite3.Connection, reference_id: str, url: str, topics: list[str], title: str | None, publisher: str | None) -> None:
    url = url.split("#", 1)[0]
    with write_transaction(conn):
        existing = conn.execute("SELECT id FROM research_references WHERE url = ? ORDER BY id LIMIT 1", (url,)).fetchone()
        if existing is not None:
            print(f"existing reference {existing['id']}")
            return
        timestamp = now()
        conn.execute("INSERT INTO research_references(id, url, title, publisher, retrieved_at, topics_json, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)", (reference_id, url, title, publisher, str(timestamp), json_dumps(topics), timestamp, timestamp))
    print(f"created reference {reference_id}")


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
    p_reference_list = reference_sub.add_parser("list")
    p_reference_list.add_argument("--review-state", choices=("needs_review", "reviewed"))
    p_reference_list.add_argument("--topic")
    p_reference_link = reference_sub.add_parser("link")
    p_reference_link.add_argument("reference_id")
    p_reference_link.add_argument("target_id")
    p_reference_link.add_argument("--task", action="store_true")

    p_clarify = sub.add_parser("clarify")
    clarify_sub = p_clarify.add_subparsers(dest="clarify_cmd", required=True)
    p_clarify_add = clarify_sub.add_parser("add")
    p_clarify_add.add_argument("question")
    p_clarify_add.add_argument("--task")
    p_clarify_add.add_argument("--default")
    p_clarify_list = clarify_sub.add_parser("list")
    p_clarify_list.add_argument("--status")

    p_principle = sub.add_parser("principle")
    principle_sub = p_principle.add_subparsers(dest="principle_cmd", required=True)
    p_principle_add = principle_sub.add_parser("add")
    p_principle_add.add_argument("theme")
    p_principle_add.add_argument("principle_id")
    p_principle_add.add_argument("statement")
    principle_sub.add_parser("list")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conn = connect(args.db)
    init_db(conn, args.schema)

    if args.cmd == "init":
        print(f"initialized {args.db}")
    elif args.cmd == "legacy-import":
        import_legacy(conn, args.path, args.kind)
    elif args.cmd == "status":
        status(conn, args.all)
    elif args.cmd == "validate":
        validate_db(conn)
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
            reference_add(conn, args.reference_id, args.url, args.topic, args.title, args.publisher)
        elif args.reference_cmd == "list":
            reference_list(conn, args.review_state, args.topic)
        elif args.reference_cmd == "link":
            reference_link(conn, args.reference_id, args.target_id, args.task)
    elif args.cmd == "clarify":
        if args.clarify_cmd == "add":
            add_clarification(conn, args.task, args.question, args.default)
        elif args.clarify_cmd == "list":
            list_clarifications(conn, args.status)
    elif args.cmd == "principle":
        if args.principle_cmd == "add":
            add_principle(conn, args.theme, args.principle_id, args.statement)
        elif args.principle_cmd == "list":
            list_principles(conn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
