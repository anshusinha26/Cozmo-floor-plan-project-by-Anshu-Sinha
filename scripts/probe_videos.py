#!/usr/bin/env python
"""Print the container facts for every video under one or more folders.

    scripts/probe_videos.py data/own data/sample

Resolution, fps, codec, duration, rotation tag, size, and the upright
resolution ffmpeg will produce after it applies the tag.
"""

from __future__ import annotations

import sys
from pathlib import Path

from cozmo.pipeline.video.probe import VIDEO_SUFFIXES, probe_table


def main(argv: list[str]) -> int:
    roots = [Path(a) for a in argv[1:]] or [Path("data")]
    paths: list[Path] = []
    for root in roots:
        if root.is_file():
            paths.append(root)
            continue
        for suffix in VIDEO_SUFFIXES:
            paths += sorted(root.rglob(f"*{suffix}"))
    paths = sorted({p.resolve(): p for p in paths}.values())
    if not paths:
        print(f"no video files under {', '.join(str(r) for r in roots)}", file=sys.stderr)
        return 1
    print(probe_table(paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
