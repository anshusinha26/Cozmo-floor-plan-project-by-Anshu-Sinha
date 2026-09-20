"""Abstract pipeline interface.

A pipeline turns one capture into one :class:`Plan`. The CLI owns writing
files and the run manifest; the pipeline owns geometry and provenance fields
inside the plan. Stage timings are collected on the instance so they can go
to run_manifest.json without polluting plan.json (which must be byte-stable).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Any, ClassVar, Iterator

from cozmo.contracts.models import Capture, Plan, RunInfo, Tier
from cozmo.io import manifest as prov


class Pipeline(ABC):
    name: ClassVar[str] = "abstract"
    version: ClassVar[str] = "0"

    def __init__(self) -> None:
        self.stage_timings_s: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        """Time a named stage; timings land in run_manifest.json."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.stage_timings_s[name] = time.perf_counter() - t0

    def provenance(self, input_path: Path, tier: Tier, config: dict[str, Any], seed: int) -> tuple[Capture, RunInfo]:
        """Capture and run blocks computed the same way the CLI computes them."""
        input_path = Path(input_path)
        capture = Capture(
            id=input_path.stem if input_path.is_file() else input_path.name,
            tier=tier,
            device=None,
            captured_at=None,
            input_manifest_sha256=prov.build_input_manifest(input_path)["sha256"],
        )
        run = RunInfo(
            pipeline_version=f"{self.name}-{self.version}",
            git_commit=prov.git_commit(),
            config_sha256=prov.config_sha256(config),
            seed=seed,
        )
        return capture, run

    @abstractmethod
    def run(self, input_path: Path, tier: Tier, config: dict[str, Any], seed: int) -> Plan:
        """Produce a Plan for one capture. Must be deterministic in (input, config, seed)."""
