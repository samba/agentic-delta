#!/usr/bin/env python3
"""Install and update skills from a federated skill catalog.

The catalog is YAML-compatible JSON so this script can run with only the Python
standard library. Runtime logs are written to the user-scope skill path by
default, not into this repository.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_CATALOG = Path(__file__).resolve().parents[1] / "skill-federation.yaml"


def expand(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def load_catalog(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            catalog = json.load(fh)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"{path} must remain JSON-compatible YAML for stdlib parsing: {exc}"
        ) from exc
    if not isinstance(catalog, dict) or "sources" not in catalog:
        raise SystemExit(f"{path} is missing a top-level sources list")
    return catalog


def configured_log_path(catalog: dict[str, Any], override: str | None) -> Path:
    raw = override or catalog.get(
        "default_log",
        "~/.codex/skills/.skill-federation/logs/skill-federation.ndjson",
    )
    return expand(raw)


def append_log(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        **event,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def cache_root(catalog: dict[str, Any], override: str | None) -> Path:
    raw = override or catalog.get("default_cache_dir", ".cache/skill-federation")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = DEFAULT_CATALOG.parent / path
    return path.resolve()


def target_dir(catalog: dict[str, Any], agent: str | None, override: str | None) -> Path:
    if override:
        return expand(override)
    selected = agent or "codex"
    for item in catalog.get("default_install_targets", []):
        if item.get("agent") == selected:
            return expand(item["skills_dir"])
    raise SystemExit(f"No install target configured for agent {selected!r}")


def normalize_repo_url(url: str) -> str:
    if url.startswith("git@github.com:") and url.endswith(".git"):
        return "https://github.com/" + url.removeprefix("git@github.com:").removesuffix(".git")
    if url.startswith("https://github.com/") and url.endswith(".git"):
        return url.removesuffix(".git")
    return url


def skill_records(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source in catalog.get("sources", []):
        for skill in source.get("skills", []):
            records.append({"source": source, "skill": skill})
    return records


def source_policy(catalog: dict[str, Any], source: dict[str, Any]) -> dict[str, str]:
    defaults = catalog.get("policy_defaults", {}).get(source.get("kind"), {})
    return {
        "trust_status": source.get("trust_status", defaults.get("trust_status", "candidate")),
        "install_policy": source.get(
            "install_policy", defaults.get("install_policy", "review-required")
        ),
        "review_status": source.get("review_status", defaults.get("review_status", "unreviewed")),
    }


def searchable_text(record: dict[str, Any]) -> str:
    source = record["source"]
    skill = record["skill"]
    parts: list[str] = [
        source.get("id", ""),
        source.get("name", ""),
        skill.get("name", ""),
        skill.get("status", ""),
    ]
    for key in ("keywords", "capabilities"):
        parts.extend(source.get(key, []))
        parts.extend(skill.get(key, []))
    return " ".join(str(part).lower() for part in parts)


def select_records(
    catalog: dict[str, Any],
    query: str | None,
    skill_names: list[str],
    source_id: str | None,
    installed_only: bool = False,
) -> list[dict[str, Any]]:
    records = skill_records(catalog)
    if source_id:
        records = [r for r in records if r["source"].get("id") == source_id]
    if installed_only:
        records = [r for r in records if r["skill"].get("status") == "installed"]
    if skill_names:
        wanted = {name.lower() for name in skill_names}
        records = [r for r in records if r["skill"].get("name", "").lower() in wanted]
    if query:
        needles = [part.lower() for part in query.split() if part.strip()]
        records = [r for r in records if all(n in searchable_text(r) for n in needles)]
    return records


def run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def git_cache_path(root: Path, source: dict[str, Any]) -> Path:
    token = source.get("repo_url") or source.get("url") or source["id"]
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
    return root / f"{source['id']}-{digest}"


def materialize_source(
    source: dict[str, Any],
    cache: Path,
    update: bool,
    dry_run: bool = False,
) -> Path | None:
    kind = source.get("kind")
    if kind != "git_repo":
        return None
    repo_url = source.get("repo_url")
    if not repo_url:
        return None
    revision = source.get("revision")
    if source.get("revision_required") and not revision:
        raise SystemExit(
            f"Source {source.get('id')} requires a pinned revision; publish the current suite and update the catalog first"
        )
    dest = git_cache_path(cache, source)
    if dry_run:
        return dest
    if dest.exists():
        if update:
            run(["git", "fetch", "--all", "--prune"], cwd=dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", repo_url, str(dest)])
    if revision:
        run(["git", "checkout", "--detach", revision], cwd=dest)
    return dest


def source_skill_path(
    record: dict[str, Any],
    cache: Path,
    update: bool,
    dry_run: bool = False,
) -> Path | None:
    source = record["source"]
    skill = record["skill"]
    root = materialize_source(source, cache, update, dry_run=dry_run)
    rel = skill.get("path")
    if not rel and source.get("skills_path") and skill.get("name"):
        rel = str(Path(source["skills_path"]) / skill["name"])
    if not root or not rel:
        return None
    path = root / rel
    if dry_run:
        return path
    if (path / "SKILL.md").is_file():
        return path
    return None


def copy_skill(src: Path, target_root: Path, dry_run: bool) -> Path:
    dest = target_root / src.name
    if dry_run:
        return dest
    target_root.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_root = target_root / ".skill-federation-backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        backup = backup_root / f"{src.name}-{stamp}"
        if backup.exists():
            raise SystemExit(f"Backup destination already exists: {backup}")
        shutil.move(str(dest), str(backup))
    shutil.copytree(src, dest)
    return dest


def target_skill_path(target_root: Path, skill_name: str) -> Path:
    dest = (target_root / skill_name).resolve()
    root = target_root.resolve()
    if dest.parent != root:
        raise SystemExit(f"Refusing to remove path outside target skill root: {dest}")
    return dest


def remove_skill(dest: Path, dry_run: bool, missing_ok: bool) -> str:
    if not dest.exists():
        if missing_ok:
            return "missing"
        raise SystemExit(f"Skill is not installed: {dest}")
    if not dest.is_dir():
        raise SystemExit(f"Refusing to remove non-directory skill path: {dest}")
    if not (dest / "SKILL.md").is_file():
        raise SystemExit(f"Refusing to remove directory without SKILL.md: {dest}")
    if dry_run:
        return "would-remove"
    shutil.rmtree(dest)
    return "removed"


def cmd_list(args: argparse.Namespace) -> int:
    catalog = load_catalog(expand(args.catalog))
    records = select_records(catalog, args.query, args.skill, args.source)
    for record in records:
        source = record["source"]
        skill = record["skill"]
        policy = source_policy(catalog, source)
        locator = source.get("repo_url") or source.get("url", "")
        print(
            f"{skill.get('name')} [{skill.get('status', 'unknown')}] "
            f"source={source.get('id')} "
            f"trust={policy['trust_status']} "
            f"policy={policy['install_policy']} "
            f"review={policy['review_status']} "
            f"locator={normalize_repo_url(locator)}"
        )
    return 0


def enforce_install_policy(
    catalog: dict[str, Any],
    record: dict[str, Any],
    allow_review_required: bool,
) -> str | None:
    source = record["source"]
    policy = source_policy(catalog, source)
    install_policy = policy["install_policy"]
    if install_policy == "installable":
        return None
    if install_policy == "review-required" and allow_review_required:
        return None
    return (
        f"source policy {install_policy!r} blocks install/update"
        if install_policy != "review-required"
        else "source requires review; pass --allow-review-required to proceed"
    )


def install_or_update(args: argparse.Namespace, update_mode: bool) -> int:
    catalog = load_catalog(expand(args.catalog))
    cache = cache_root(catalog, args.cache_dir)
    log_path = configured_log_path(catalog, args.log)
    target = target_dir(catalog, args.agent, args.target_dir)
    records = select_records(
        catalog,
        args.query,
        args.skill,
        args.source,
        installed_only=update_mode and args.installed_only,
    )
    if not records:
        raise SystemExit("No matching skills found")
    installed = 0
    skipped = 0
    for record in records:
        source = record["source"]
        skill = record["skill"]
        policy = source_policy(catalog, source)
        blocked_reason = enforce_install_policy(catalog, record, args.allow_review_required)
        if blocked_reason:
            skipped += 1
            append_log(
                log_path,
                {
                    "event": "skip",
                    "reason": blocked_reason,
                    "source": source.get("id"),
                    "skill": skill.get("name"),
                    **policy,
                },
            )
            print(f"skipped {skill.get('name')}: {blocked_reason}")
            continue
        src = source_skill_path(record, cache, update=True, dry_run=args.dry_run)
        if not src:
            skipped += 1
            reason = "source does not expose a local skill path"
            append_log(
                log_path,
                {
                    "event": "skip",
                    "reason": reason,
                    "source": source.get("id"),
                    "skill": skill.get("name"),
                    **policy,
                },
            )
            print(f"skipped {skill.get('name')}: {reason}")
            continue
        dest = copy_skill(src, target, args.dry_run)
        installed += 1
        append_log(
            log_path,
            {
                "event": "update" if update_mode else "install",
                "dry_run": args.dry_run,
                "source": source.get("id"),
                "skill": skill.get("name"),
                "src": str(src),
                "dest": str(dest),
                **policy,
            },
        )
        print(f"{'would install' if args.dry_run else 'installed'} {skill.get('name')} -> {dest}")
    print(f"matched={len(records)} installed={installed} skipped={skipped} log={log_path}")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    return install_or_update(args, update_mode=False)


def cmd_update(args: argparse.Namespace) -> int:
    return install_or_update(args, update_mode=True)


def cmd_remove(args: argparse.Namespace) -> int:
    catalog = load_catalog(expand(args.catalog))
    log_path = configured_log_path(catalog, args.log)
    target = target_dir(catalog, args.agent, args.target_dir)
    records = select_records(catalog, args.query, args.skill, args.source)
    if not records:
        raise SystemExit("No matching skills found")
    removed = 0
    missing = 0
    for record in records:
        source = record["source"]
        skill = record["skill"]
        name = skill.get("name")
        policy = source_policy(catalog, source)
        if not name:
            continue
        dest = target_skill_path(target, name)
        result = remove_skill(dest, args.dry_run, args.missing_ok)
        if result == "missing":
            missing += 1
        else:
            removed += 1
        append_log(
            log_path,
            {
                "event": "remove",
                "dry_run": args.dry_run,
                "result": result,
                "source": source.get("id"),
                "skill": name,
                "dest": str(dest),
                **policy,
            },
        )
        print(f"{result} {name} at {dest}")
    print(f"matched={len(records)} removed={removed} missing={missing} log={log_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_selectors(p: argparse.ArgumentParser) -> None:
        p.add_argument("--query", help="Keyword query matched against skills and sources")
        p.add_argument("--skill", action="append", default=[], help="Specific skill name")
        p.add_argument("--source", help="Specific source id")

    list_p = sub.add_parser("list", help="List cataloged skills")
    add_selectors(list_p)
    list_p.set_defaults(func=cmd_list)

    for name, func in (("install", cmd_install), ("update", cmd_update)):
        p = sub.add_parser(name, help=f"{name.title()} matching skills")
        add_selectors(p)
        p.add_argument("--agent", default="codex", help="Configured install target agent")
        p.add_argument("--target-dir", help="Override target skills directory")
        p.add_argument("--cache-dir", help="Override remote repository cache directory")
        p.add_argument("--log", help="Override NDJSON operation log path")
        p.add_argument("--dry-run", action="store_true")
        p.add_argument(
            "--allow-review-required",
            action="store_true",
            help="Allow install/update from review-required candidate sources",
        )
        p.add_argument(
            "--installed-only",
            action="store_true",
            help="Only update records marked installed in the catalog",
        )
        p.set_defaults(func=func)

    remove_p = sub.add_parser("remove", help="Remove matching installed skills")
    add_selectors(remove_p)
    remove_p.add_argument("--agent", default="codex", help="Configured install target agent")
    remove_p.add_argument("--target-dir", help="Override target skills directory")
    remove_p.add_argument("--log", help="Override NDJSON operation log path")
    remove_p.add_argument("--dry-run", action="store_true")
    remove_p.add_argument(
        "--missing-ok",
        action="store_true",
        help="Log missing matches instead of failing",
    )
    remove_p.set_defaults(func=cmd_remove)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
