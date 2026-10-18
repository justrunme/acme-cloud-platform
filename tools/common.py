"""Shared helpers: repository paths, canonical JSON, sha256 digests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import yaml

ROOT = Path(__file__).resolve().parent.parent

DIGEST_PREFIX = "sha256:"


def canonical_json(obj: Any) -> bytes:
    """Deterministic JSON bytes: sorted keys, no insignificant whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return DIGEST_PREFIX + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def sha256_obj(obj: Any) -> str:
    return sha256_bytes(canonical_json(obj))


def load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def load_doc(path: Path) -> Any:
    p = Path(path)
    if p.suffix == ".json":
        return load_json(p)
    return load_yaml(p)


def write_json(path: Path, obj: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def repo_path(root: Path, rel: str) -> Path:
    """Resolve a repository-relative path and refuse anything that escapes the root."""
    candidate = (root / rel).resolve()
    root_resolved = root.resolve()
    if root_resolved != candidate and root_resolved not in candidate.parents:
        raise ValueError(f"path escapes repository root: {rel}")
    return candidate


# Files whose bytes determine every generated result. Generated outputs are excluded.
INPUT_DIRS = ("agents", "apps", "cluster", "evidence", "graphs", "infra", "policies", "rehearsals", "restore", "tools",
              "scripts")


def inputs_digest(root: Path = ROOT, dirs: Iterable[str] = INPUT_DIRS) -> str:
    """Content digest over all input files (path + bytes), independent of git metadata."""
    entries = []
    for d in dirs:
        base = root / d
        if not base.exists():
            continue
        for f in sorted(base.rglob("*")):
            if not f.is_file() or "__pycache__" in f.parts or f.suffix == ".pyc":
                continue
            rel = f.relative_to(root).as_posix()
            entries.append({"path": rel, "sha256": sha256_file(f)})
    return sha256_obj(entries)
