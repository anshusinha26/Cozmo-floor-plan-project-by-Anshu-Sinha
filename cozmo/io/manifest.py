"""Provenance helpers: input hashing, config hashing, git commit, library versions.

Everything the run manifest records comes from here so that the CLI and the
pipeline compute identical hashes. Hashes are over content, never over paths
or timestamps, so the same capture copied elsewhere hashes the same.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Any

import yaml

_CHUNK = 1 << 20


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(obj: Any) -> bytes:
    """Sorted keys, no whitespace: the one encoding used for hashing dicts."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def list_input_files(input_path: Path) -> list[Path]:
    """All regular files under input_path (or the file itself), sorted by relative path."""
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"input not found: {input_path}")
    if input_path.is_file():
        return [input_path]
    files = sorted(p for p in input_path.rglob("*") if p.is_file() and not p.name.startswith("."))
    if not files:
        raise ValueError(f"no files under input directory: {input_path}")
    return files


def build_input_manifest(input_path: Path, files: list[Path] | None = None) -> dict[str, Any]:
    """Per-file SHA-256 plus a manifest-level SHA-256 over the (path, sha) list.

    The manifest hash ignores absolute location: paths are relative to the input
    root (or just the file name for a single file). ``files`` restricts the
    manifest to the files a tier may read, so provenance respects tier isolation.
    """
    input_path = Path(input_path)
    files = sorted(files) if files is not None else list_input_files(input_path)
    if not files:
        raise ValueError(f"no files to hash under {input_path}")
    root = input_path if input_path.is_dir() else input_path.parent
    entries = []
    for f in files:
        entries.append(
            {
                "path": f.relative_to(root).as_posix(),
                "sha256": sha256_file(f),
                "size_bytes": f.stat().st_size,
            }
        )
    digest = sha256_bytes(canonical_json([(e["path"], e["sha256"]) for e in entries]))
    return {"root": str(input_path), "files": entries, "sha256": digest}


def load_config(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    if not isinstance(cfg, dict):
        raise ValueError(f"config must be a mapping at top level: {path}")
    return cfg


def config_sha256(resolved_config: dict[str, Any]) -> str:
    """Hash of the resolved config dict, so equivalent YAML spellings hash equal
    and CLI overrides (seed, drift correction) are part of the hash."""
    return sha256_bytes(canonical_json(resolved_config))


def git_commit(cwd: Path | None = None) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def git_dirty(cwd: Path | None = None) -> bool | None:
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return bool(out.stdout.strip())
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


_LIBRARIES = ["pydantic", "numpy", "shapely", "typer", "pyyaml", "jsonschema", "matplotlib"]


def library_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in _LIBRARIES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "not installed"
    return versions
