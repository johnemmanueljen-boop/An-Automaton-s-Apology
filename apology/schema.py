"""Versioned evidence identities and conservative adapters. No provider or Lean imports."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import tempfile
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

SCHEMA_VERSION = 2


def digest(value) -> str:
    raw = value if isinstance(value, bytes) else (value.encode("utf-8") if isinstance(value, str)
                                                else json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    """Atomic replacement; exclusive run directories protect historical artifacts."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def contained_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes source root: {relative}")
    return path


def declaration_id(repository: str, commit: str, module: str, name: str, environment="challenge") -> str:
    return json.dumps([repository, commit, environment, module, name], ensure_ascii=False, separators=(",", ":"))


def validate_location(decls: list[dict], name, start, end=None) -> dict:
    """Exact names only. A top-level name without a namespace is also fully qualified."""
    matches = [d for d in decls if d["name"] == name]
    end = start if end is None else end
    valid = (len(matches) == 1 and type(start) is int and type(end) is int
             and matches[0]["start_line"] <= start <= end <= matches[0]["end_line"])
    return {"location_valid": bool(valid), "citation_ok": bool(valid), "supports_claim": "unreviewed",
            "citation_status": "location_checked" if valid else "invalid_location"}


def validate_audit(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError("audit must be an object")
    out = copy.deepcopy(value)
    for key in ("flags", "glossary", "lean_claims", "paper_claims", "coverage", "lint_verdicts"):
        items = out.setdefault(key, [])
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise ValueError(f"{key} must be a list of objects")
        for item in items:
            item.pop("human_review", None)
            item["evidence_level"] = "model_proposal"
            item["supports_claim"] = "unreviewed"
            item.pop("location_valid", None)
            item.pop("citation_ok", None)
    for flag in out["flags"]:
        if flag.get("severity") not in {"high", "medium", "low"}:
            raise ValueError("invalid flag severity")
    allowed = {"equivalent", "lean_stronger", "lean_weaker", "different", "not_formalized", "unknown"}
    for row in out["coverage"]:
        if row.get("relation") not in allowed:
            raise ValueError("invalid coverage relation")
    return out


def adapt_card(card: dict) -> dict:
    """Display old cards without retroactively validating their certificates."""
    out = copy.deepcopy(card)
    if out.get("schema_version") == SCHEMA_VERSION:
        return out
    out["legacy"] = True
    for key in ("flags", "glossary", "lean_claims"):
        for item in out.get("audit", {}).get(key, []):
            item.update(location_valid=False, citation_ok=False, citation_status="legacy_unvalidated",
                        supports_claim="unreviewed", evidence_level="model_proposal")
    for row in out.get("audit", {}).get("coverage", []):
        row["evidence_level"] = "model_proposal"
    for item in out.get("restatements", []):
        item["evidence_label"] = "historical Lean result; not rechecked"
    return out


def git_revision(root: Path) -> dict:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, text=True, capture_output=True, check=True).stdout
        paths = [p for folder in ("apology", "experiments", "lean") for p in (root / folder).glob("**/*")
                 if p.is_file() and p.suffix in {".py", ".lean", ".toml"}]
        paths += [root / name for name in ("app.py", "pyproject.toml", "requirements.txt") if (root / name).exists()]
        hashes = {str(p.relative_to(root)): digest(p.read_bytes()) for p in paths}
        return {"commit": sha, "dirty": bool(dirty), "working_code_sha256": digest(hashes), "code_files": hashes}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": "unavailable", "dirty": None}


def new_run(root: Path, kind: str, inputs: dict, *, offline=True) -> tuple[Path, dict]:
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:10]
    folder = root / "results" / "runs" / run_id
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "kind": kind,
                "created_at": now.isoformat(), "code": git_revision(root), "offline": offline,
                "inputs": inputs, "actual_api_usd": 0.0, "requests": [], "python": sys.version,
                "python_executable": sys.executable, "virtual_environment": sys.prefix != sys.base_prefix}
    return folder, manifest
