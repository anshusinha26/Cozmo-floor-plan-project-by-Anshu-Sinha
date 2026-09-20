#!/usr/bin/env python
"""Freeze a set of runs as the before or after side of a fix loop.

    scripts/fix_loop_snapshot.py fix_loop/loop2_video_scale/before runs/video/*

Copies the plans, manifests and stage reports, writes the tape table, and
records provenance: the commit, whether the tree was dirty, the config hash, and
the library versions. A snapshot with a dirty tree is marked as such, because it
cannot be regenerated from the commit alone.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COPY = ("plan.json", "run_manifest.json", "plan.png", "drift_report.json")
COPY_DEBUG = ("video_report.json", "photo_report.json")


def _config_sha(runs: list[Path]) -> str | None:
    for r in runs:
        m = r / "run_manifest.json"
        if m.is_file():
            return json.loads(m.read_text()).get("config", {}).get("sha256")
    return None


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                              text=True, check=True).stdout.strip()
    except subprocess.CalledProcessError:
        return ""


def provenance(runs: list[Path], from_commit: str | None = None) -> dict:
    if from_commit:
        # The runs came from a git archive of this commit, so the state of the
        # working tree now says nothing about them.
        return {
            "commit": _git("rev-parse", from_commit) or from_commit,
            "commit_subject": _git("log", "-1", "--format=%s", from_commit),
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "tree_dirty": False,
            "note": f"Produced by a git archive of {from_commit}, so the working tree at "
                    f"snapshot time is irrelevant. regenerate.sh reproduces it the same way.",
            "config_sha256": _config_sha(runs),
            "taken_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "platform": platform.platform(),
            "runs": [r.name for r in runs],
        }
    dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    return {
        "commit": _git("rev-parse", "HEAD"),
        "commit_subject": _git("log", "-1", "--format=%s"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "tree_dirty": dirty,
        "note": ("The tree was dirty when this snapshot was taken, so the commit alone does not "
                 "reproduce it" if dirty else
                 "Clean tree: the commit reproduces this snapshot, given the cached reconstructions"),
        "config_sha256": _config_sha(runs),
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "runs": [r.name for r in runs],
    }


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    args = [a for a in argv[1:] if not a.startswith("--from-commit")]
    from_commit = next((a.split("=", 1)[1] for a in argv[1:] if a.startswith("--from-commit=")), None)
    dest = Path(args[0])
    runs = [Path(a) for a in args[1:] if (Path(a) / "plan.json").is_file()
            or (Path(a) / "run_manifest.json").is_file() or Path(a).is_dir()]
    runs = [r for r in runs if r.is_dir()]
    if not runs:
        print("no run directories given", file=sys.stderr)
        return 1
    dest.mkdir(parents=True, exist_ok=True)
    for r in runs:
        out = dest / "runs" / r.name
        out.mkdir(parents=True, exist_ok=True)
        for name in COPY:
            if (r / name).is_file():
                shutil.copy2(r / name, out / name)
        for name in COPY_DEBUG:
            if (r / "debug" / name).is_file():
                shutil.copy2(r / "debug" / name, out / name)
        if not (r / "plan.json").is_file():
            (out / "NO_PLAN.txt").write_text(
                "This clip produced no plan. That is part of the state being recorded.\n")
    (dest / "provenance.json").write_text(
        json.dumps(provenance(runs, from_commit), indent=2) + "\n")

    sys.path.insert(0, str(REPO / "scripts"))
    import video_tier_report as rep

    loaded = [x for x in (rep.load(r) for r in runs) if x]
    lines = ["# Tape table", "", rep.per_clip_table(loaded), "", "## Predicted against tape", "",
             rep.tape_table(loaded), "", "## bedroom_2 against bedroom_2_repeat", "",
             rep.repeat_table(loaded), ""]
    (dest / "tape_table.md").write_text("\n".join(lines))
    print(f"snapshot written to {dest}: {len(runs)} runs, {len(loaded)} with plans")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
