# Merge plan: video-tier into main

Written from `main` while `video-tier` was still running, so the merge is
mechanical when it lands. Nothing here has been merged.

Merge base: `4c564f3`. At the time of writing `video-tier` is 8 commits ahead
and has touched 30 files; `main` is 51 commits and has touched 45.

Regenerate this list:

```bash
B=$(git merge-base main video-tier)
comm -12 <(git diff --name-only $B main | sort) <(git diff --name-only $B video-tier | sort)
```

## Files only one branch touched: no conflict

`video-tier` owns everything under `cozmo/pipeline/video/` and
`cozmo/pipeline/photo/` (25 new modules). `main` never touched either
directory, deliberately. `main` owns `cozmo/lidar/`, `cozmo/damage/`,
`cozmo/eval/registration.py`, `cozmo/eval/self_consistency.py`,
`cozmo/eval/head_to_head.py`, `fix_loop/` and `docs/`. Take both sides whole.

## Files both branches touched: eight, all resolvable

### 1. `cozmo/io/inputs.py` — the one that needs care

Both branches extended the same two functions for different reasons.

| change | branch | keep |
|---|---|---|
| `VIDEO_EXT` gains `.avi`, `.mkv` | video-tier | yes |
| `VIDEO_EXT` gains `.hevc`; `IMAGE_EXT` gains `.heic`, `.heif` | main | yes |
| `KNOWN_JUNK` for `.DS_Store` and `.AAE`, case-insensitive matching | main | yes |
| `InputSpec.skipped`: name non-room subfolders and carry on | video-tier | yes |
| a folder of photos is one room named after the folder | main | yes |
| `_video` accepts a scan folder or a folder holding one clip | both, independently | either; they are the same behaviour |
| error messages naming what was found and what is accepted | main | yes |

**Resolution: union.** Take the extension sets as a union, keep `skipped` from
video-tier, keep `KNOWN_JUNK` and the error-message text from main. The two
`_video` implementations agree on behaviour, so keep whichever reads better
and check both sides' tests pass against it.

**Watch for:** video-tier's `_photo` raises only when *no* subfolder has
enough images, where main raises on the first thin one. Video-tier's is the
better behaviour for a real capture folder that also holds a PDF. Keep it, and
keep main's message text inside it.

### 2. `cozmo/pipeline/__init__.py`

`main` has `REAL_BY_TIER = {"lidar": "lidar"}`; video-tier has all three tiers
and the two extra `get_pipeline` branches.

**Resolution: take video-tier whole.** It is a strict superset. Main's version
exists only because the other tiers did not.

### 3. `cozmo/cli.py`

Both added options and neither touched the other's.

| addition | branch |
|---|---|
| `--segmentation erosion\|cells`, repeat-kind labelling, no-ground-truth reporting, the shared-wall statistic | main |
| `--video-rotation auto\|0\|90\|180\|270`, `RoomModeOpt`, room-mode handling | video-tier |

**Resolution: take both.** Two functions need hand-merging because both sides
edited them: `resolve_config`, which must carry both `segmentation` and the
video options into the resolved dict, and the `run` command signature, which
takes the union of options. Both feed the config hash, so check
`run_manifest.json` still records every flag after merging.

### 4. `cozmo/io/ground_truth.py`

Purely additive on both sides and to different models.

* video-tier: `video_rotation` and `pipeline` on the capture entry.
* main: `truth_uncertainty_m`, `present_unmeasured`, `score_walls`, `GTDamage`,
  `device`, `repeat_kind`.

**Resolution: take both.** No overlap.

### 5. `config/gates.yaml`

video-tier adds 183 lines in its own block; main added `cells:` and `ghost:`
blocks and changed `segmentation` to `erosion`.

**Resolution: take both blocks.** Keep `segmentation: erosion` from main: fix
loop 1 measured both and erosion is the default for the reasons in
`fix_loop/POSTMORTEM.md`. The config hash changes, so any run artifact
regenerated after the merge will carry a new `config_sha256`. That is correct,
not a regression.

### 6. `benchmarks/captures.yaml`

video-tier adds 3 lines; main added the twelve hand-measured captures with
`device` and `repeat_kind`.

**Resolution: take both.** Then check video-tier's three entries carry a
`device`, since main added that field and the registry model now expects it to
be meaningful for the repeat-pair labelling.

### 7. `scripts/fetch_weights.sh`

video-tier adds 59 lines fetching its depth-model weights; main fetches OWLv2
and SigLIP.

**Resolution: union the fetch steps.** Then update `THIRD_PARTY.md` with the
video tier's model and its licence, and update the measured download sizes in
`docs/rehearsal.md`, which currently cover only the two damage models.

### 8. `tests/test_inputs.py` and `tests/test_runner.py`

Small edits on both sides, no shared assertions.

**Resolution: take both.** Then run the whole suite: main's
`tests/test_iphone_inputs.py` asserts behaviour that the merged `_photo` and
`_video` must still satisfy, and it is the fastest check that the union in
item 1 came out right.

## After the merge

1. `uv run pytest -q`. Main is at 168 passing; the sum should pass.
2. `scripts/regenerate_all.sh`. The config hash changes, so every run artifact
   is rebuilt and the fix-loop numbers should be re-read, not assumed.
3. `.venv/bin/python scripts/head_to_head.py --plans <runs dir>` to fill the
   column that reads "not yet" today. That is the headline the merge unlocks.
4. Update these, which carry PENDING cells waiting on the video tier:
   `docs/device_matrix.md`, `docs/technical_report.md` (tiers, calibration),
   `docs/STATUS_main.md`, `docs/compliance_matrix.md`.
5. Re-run `.venv/bin/python fix_loop/evidence_run.py` only if the LiDAR path
   changed. The merge should not touch it.

## Do not merge these by accident

* `fix_loop/before/` and `fix_loop/after/` are a matched pair produced at named
  commits recorded in their `PROVENANCE.txt`. If both branches regenerated
  them, keep main's: they belong to fix loop 1, whose story is told in
  `fix_loop/POSTMORTEM.md`. Video-tier's loop 2 artifacts live in
  `fix_loop/loop2_video_scale/` and do not collide.
* `docs/damage_eval/` numbers were measured with the damage extras at a pinned
  threshold. They do not depend on the video tier and should not be
  regenerated as part of the merge.
