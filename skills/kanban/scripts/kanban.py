#!/usr/bin/env python3
"""SQLite-backed project kanban helper."""

from __future__ import annotations

import argparse
import json
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


def fail(message: str, code: int = 2) -> None:
    print(f"FAIL {message}", file=sys.stderr)
    raise SystemExit(code)


def now() -> int:
    return int(time.time())


def json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def json_loads(value: str | None, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    return json.loads(value)


def connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(conn: sqlite3.Connection, schema_path: Path) -> None:
    if not schema_path.is_file():
        fail(f"Missing schema: {schema_path}")
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO meta(key, value) VALUES('schema_version', '5') "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
    )
    ensure_default_columns(conn)
    ensure_default_wip_limits(conn)
    migrate_backfill_goals(conn)
    ensure_default_backfill_goals(conn)
    conn.commit()


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
    with conn:
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
    with conn:
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
    row = conn.execute("SELECT raw_json FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        fail(f"Unknown task: {task_id}")
    card = json_loads(row["raw_json"])
    mutate(card)
    with conn:
        upsert_task(conn, card)


def task_move(conn: sqlite3.Connection, task_id: str, column: str, owner: str | None) -> None:
    require_column(conn, column)
    row = conn.execute("SELECT column_name FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        fail(f"Unknown task: {task_id}")
    from_column = row["column_name"]
    if not transition_allowed(conn, from_column, column):
        rules = column_rules(conn, column)
        suffix = f"; {column} requires: {', '.join(rules)}" if rules else ""
        fail(f"Transition not allowed: {from_column} -> {column}{suffix}")

    def mutate(card: dict[str, Any]) -> None:
        card["column"] = column
        if owner is not None:
            card["owner"] = owner

    update_task_raw(conn, task_id, mutate)
    conn.execute(
        "INSERT INTO task_events(task_id, event_type, message, created_at) VALUES(?, ?, ?, ?)",
        (task_id, "move", f"moved to {column}", now()),
    )
    conn.commit()


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


def list_backlog(conn: sqlite3.Connection) -> None:
    for row in conn.execute("SELECT id, summary, status FROM backlog_ideas ORDER BY id"):
        status = row["status"] or ""
        print(f"{row['id']}\t{status}\t{row['summary'] or ''}")


def add_backlog(conn: sqlite3.Connection, idea_id: str, summary: str, themes: list[str]) -> None:
    idea = {"id": idea_id, "summary": summary, "themes": themes, "status": "new"}
    with conn:
        conn.execute(
            """
            INSERT INTO backlog_ideas(id, summary, status, themes_json, raw_json, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (idea_id, summary, "new", json_dumps(themes), json_dumps(idea), now()),
        )


def add_clarification(conn: sqlite3.Connection, task_id: str | None, question: str, default: str | None) -> None:
    with conn:
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
    with conn:
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
    with conn:
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
    with conn:
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
    duplicate_themes = conn.execute(
        """
        SELECT task_id, theme, COUNT(*) AS n
        FROM task_themes GROUP BY task_id, theme HAVING n > 1
        """
    ).fetchall()
    if duplicate_themes:
        errors.append("duplicate task themes")
    if errors:
        fail("; ".join(errors), 1)
    print(f"PASS kanban db valid tasks={task_count}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")

    p_status = sub.add_parser("status")
    p_status.add_argument("--all", action="store_true")

    p_validate = sub.add_parser("validate")

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
    p_task_move = task_sub.add_parser("move")
    p_task_move.add_argument("task_id")
    p_task_move.add_argument("column")
    p_task_move.add_argument("--owner")
    p_task_validation = task_sub.add_parser("validation")
    p_task_validation.add_argument("task_id")
    p_task_validation.add_argument("status")
    p_task_validation.add_argument("--evidence")

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
    elif args.cmd == "status":
        status(conn, args.all)
    elif args.cmd == "validate":
        validate_db(conn)
    elif args.cmd == "config":
        if args.config_cmd == "list":
            list_config(conn)
        elif args.config_cmd == "set":
            if args.config_set_cmd == "wip_limit":
                set_column_wip_limit(conn, args.column, args.limit)
            elif args.config_set_cmd == "backfill_goal":
                set_backfill_goal(conn, args.column, args.target, args.description)
    elif args.cmd == "task":
        if args.task_cmd == "list":
            list_tasks(conn, args.column, args.theme)
        elif args.task_cmd == "show":
            show_task(conn, args.task_id)
        elif args.task_cmd == "move":
            task_move(conn, args.task_id, args.column, args.owner)
        elif args.task_cmd == "validation":
            task_set_validation(conn, args.task_id, args.status, args.evidence)
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
