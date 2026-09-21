# Clean-machine rehearsal

The walk-in test is someone cloning this repository and following the README
without help. This is that rehearsal, run on a fresh clone into a temporary
directory, timing each step.

Machine: Apple M1 Max, 32 GB, macOS. Connection is fast; a slower one moves
the two download steps and nothing else.

## README to first plan

| step | command | time |
|---|---|---|
| 1. clone | `git clone <repo> cozmo` | 0.5 s |
| 2. install | `uv sync` (cold uv cache) | 11.2 s |
| 3. tests | `uv run pytest -q` | 43.5 s |
| 4. capture data | `scripts/fetch_sample_data.sh` | 96.4 s |
| 5. first plan | `cozmo run --input data/sample/c00a170fe1 --tier lidar --out runs/first` | 19.0 s |

**Total, clone to first plan: 2 minutes 51 seconds**, including the optional
test run. Without the tests it is 2 minutes 7 seconds. The target was 15
minutes.

Step 2 was measured with `UV_CACHE_DIR` pointed at an empty directory, so the
wheels were genuinely downloaded. Step 4 is the real Google Drive download of
all three scans, 1715, 5251 and 9745 frames, each verified for the Stray
Scanner layout before the script reports success.

The largest scan, `c7d28f72c6`, takes 33.5 s from the same clone.

## Runs with the network off

A reconstruction must not phone home. Checked by running the same command
with the proxy pointed at a dead port and `HF_HUB_OFFLINE=1`:

```
env http_proxy=http://127.0.0.1:9 https_proxy=http://127.0.0.1:9 \
    HF_HUB_OFFLINE=1 cozmo run --input data/sample/c00a170fe1 --tier lidar --out runs/offline
```

It completed in 5.6 s, and the plan is **byte-identical** to the one produced
with the network up. The 19.0 s in the table above is a cold first run:
imports and the matplotlib font cache. Subsequent runs are about 5.6 s.

## The full profile, everything installed

Rehearsed the same way: fresh clone, cold uv cache, empty Hugging Face cache.

| step | command | time | size |
|---|---|---|---|
| 1. clone | `git clone` | 1.1 s | |
| 2. install everything | `uv sync --extra all` | 44.0 s | 1.6 GB venv |
| 3. fetch every weight | `scripts/fetch_weights.sh` | **929 s, 15 min 30 s** | 9.60 GB |

Weights, measured from a cold cache rather than estimated:

| model | used by | size |
|---|---|---|
| Depth Pro | video, photo | 1.90 GB |
| Depth Anything V2 Metric Indoor Large | video, photo | 1.34 GB |
| MapAnything, Apache checkpoint | video, photo, chunk-boundary poses only | 4.91 GB |
| OWLv2 | damage | 0.62 GB |
| SigLIP | damage | 0.82 GB |
| **total** | | **9.60 GB** |

MapAnything is half the download on its own, and the video and photo tiers use
it for one job: the relative pose across a chunk boundary.

**The 15-minute target applies to the lidar path only**, and the lidar path
needs none of this. The full profile is dominated by two downloads, 1.6 GB of
packages and the model weights, so the time you see is your connection rather
than anything this repository does.

**The lidar tier needs no weights, no torch and no network.**

### What the rehearsal broke in the full profile

**The `all` extra could not be installed at all.** `depth-pro` pins
`numpy<2` while `mapanything`, through `rerun-sdk`, needs `numpy>=2`, so
resolution failed outright. depth-pro runs correctly on numpy 2 and the whole
image path was developed and measured on 2.4.6 with both packages imported,
so the pin is overridden in `[tool.uv]` with the reason written next to it.
The two git-sourced packages also needed
`tool.hatch.metadata.allow-direct-references`. Neither problem is visible
without installing from a clean clone, because a working venv built up by
hand hides both.

## What the rehearsal broke, and what was fixed

Three real failures, all found by following the README as a stranger would
rather than by reading it:

1. **A test failed on a fresh clone.** `test_own_ground_truth_files_load...`
   asserted that the hand-measured capture folders exist, but `data/` is
   gitignored, so a clone has the ground-truth YAML and none of the images.
   Fixed: the folders are checked only when `data/` is present.
2. **The data fetch stopped before it started.** `scripts/fetch_sample_data.sh`
   needs `gdown`, which `uv sync` did not install. A stranger hit a dead end
   two steps into the README. Fixed: `gdown` is now a dev dependency, so
   `uv sync` provides it.
3. **The fetch script used a flag gdown 6 removed.** `--remaining-ok` is gone,
   so the download failed with a usage error. Fixed: the flag is not passed.
4. **The damage dependencies were not declared at all.** torch and
   transformers had been installed by hand during development and were never
   added to `pyproject.toml`, so `uv sync` on a clean clone produced a venv
   where `scripts/fetch_weights.sh` failed on `No module named 'transformers'`.
   Fixed: a `damage` extra, and the README now says `uv sync --extra damage`.

The first three were found in the first pass, the fourth when the rehearsal
reached the weights step. All four are committed.

## Reproduce this

```bash
git clone <repo> /tmp/rehearsal/cozmo && cd /tmp/rehearsal/cozmo
UV_CACHE_DIR=/tmp/rehearsal/uvcache uv sync
uv run pytest -q
scripts/fetch_sample_data.sh
uv run cozmo run --input data/sample/c00a170fe1 --tier lidar --out runs/first
```
