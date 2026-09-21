# Third-party models, libraries and data

Everything this project depends on, what it is used for, and its licence.
This repository is MIT (see `LICENSE`).

## Models

**The lidar tier uses none of these.** It is classical geometry, so nothing in
a lidar dimension came from a trained model. The video and photo tiers do use
trained models, and every dimension they report passed through one.

| model | version | used by | use | licence |
|---|---|---|---|---|
| [Depth Pro](https://huggingface.co/apple/DepthPro) | `apple/DepthPro`, `depth_pro.pt` | video, photo | monocular metric depth, one of the scale cues | weights `apple-amlr` (Apple ML Research Model licence); code Apple Sample Code licence |
| [Depth Anything V2 Metric Indoor Large](https://huggingface.co/depth-anything/Depth-Anything-V2-Metric-Indoor-Large-hf) | `depth-anything/Depth-Anything-V2-Metric-Indoor-Large-hf` | video, photo | second monocular metric depth cue, cross-checked against Depth Pro | CC BY-NC 4.0 (the V2 Large variants; only V2 Small is Apache 2.0) |
| [MapAnything](https://huggingface.co/facebook/map-anything-apache) | `facebook/map-anything-apache` | video, photo | poses across a chunk boundary; the photo tier's reconstruction | Apache 2.0 checkpoint, chosen over the default weights for that reason; code Apache 2.0 |
| [OWLv2](https://huggingface.co/google/owlv2-base-patch16-ensemble) | `google/owlv2-base-patch16-ensemble` | damage | open-vocabulary damage detection from text prompts | Apache 2.0 |
| [SigLIP](https://huggingface.co/google/siglip-base-patch16-224) | `google/siglip-base-patch16-224` | damage | zero-shot crop verifier that rejects false detections | Apache 2.0 |

**CC BY-NC 4.0 is non-commercial.** Depth Anything V2 Large is the only
component here that is not usable commercially. A commercial build would drop
to the Apache-licensed V2 Small checkpoint, or to Depth Pro alone, and would
need re-measuring; nothing in this repository has been evaluated that way.

Measured sizes on disk, from `scripts/fetch_weights.sh`: Depth Pro 1.90 GB,
Depth Anything V2 1.34 GB, MapAnything 4.91 GB, OWLv2 0.62 GB, SigLIP 0.82 GB,
9.60 GB in total. Nothing is downloaded during a run.

### Models evaluated and not used

| model | why not | evidence |
|---|---|---|
| [MapAnything](https://github.com/facebookresearch/map-anything), fused-cloud route | metric scale wrong by about 30% and consistent across runs; the fused cloud does not produce straight walls. Kept for poses and for the photo tier's reconstruction, where the focal is supplied from EXIF | `docs/experiments/mapanything/result.json`, `fix_loop/loop2_video_scale/photo_ablation.md` |

## Runtime libraries

Installed by `uv sync` from `pyproject.toml`. These carry the reconstruction.

| library | use | licence |
|---|---|---|
| pydantic | the output contract and all validation | MIT |
| numpy | all numeric work | BSD 3-Clause |
| scipy | plane fits, assignment, morphology, rotations | BSD 3-Clause |
| opencv-python-headless | image and video decoding, image operations | Apache 2.0 |
| shapely | polygon geometry, areas, unions, intersections | BSD 3-Clause |
| scikit-image | watershed segmentation | BSD 3-Clause |
| matplotlib | plan rendering and debug images | Matplotlib licence, BSD-style |
| typer | the command line | MIT |
| pyyaml | config, ground truth, the capture registry | MIT |
| jsonschema | validating emitted plans against the published schema | MIT |
| pillow-heif | reading iPhone HEIC stills | LGPL 3.0 or later |

`pillow-heif` is the only copyleft dependency. It is used as an unmodified
library through its public API, which LGPL permits without affecting this
project's licence.

## Optional libraries

| library | extra | use | licence |
|---|---|---|---|
| torch, torchvision | `damage`, `video`, `photo` | runs every model above | BSD 3-Clause |
| pycolmap | `video`, `photo` | COLMAP structure from motion, run in its own subprocess | BSD 3-Clause |
| depth-pro | `video`, `photo` | Depth Pro inference | Apple Sample Code licence |
| mapanything | `video`, `photo` | MapAnything inference | Apache 2.0 |
| imageio-ffmpeg | `video`, `photo` | bundled ffmpeg for decoding clips | BSD 2-Clause |
| transformers | `damage`, `video`, `photo` | loads and runs OWLv2, SigLIP and Depth Anything V2 | Apache 2.0 |
| sentencepiece | `damage` | SigLIP's tokenizer | Apache 2.0 |
| protobuf | `damage` | SigLIP's tokenizer | BSD 3-Clause |
| pytest | `dev` | tests | MIT |
| gdown | `dev` | `scripts/fetch_sample_data.sh` | MIT |
| reportlab | `dev` | PDF fallback in `scripts/md_to_pdf.py` | BSD 3-Clause |
| pypdf | `dev` | page-count check in `scripts/build_report.sh` | BSD 3-Clause |

## External tools

| tool | use | licence |
|---|---|---|
| [Stray Scanner](https://apps.apple.com/app/stray-scanner/id1557051662) | iOS app that produces the LiDAR captures this project reads | proprietary, free to use; no code from it is included |
| pandoc, optional | preferred PDF renderer in `scripts/build_report.sh` | GPL 2.0 or later; invoked as an external program, not linked |
| uv | dependency management | Apache 2.0 or MIT |

## Data

| data | origin | in this repository |
|---|---|---|
| `data/sample/` three Stray Scanner scans | supplied by the assessors | **no**; gitignored, fetched by `scripts/fetch_sample_data.sh`. Not ours to redistribute |
| `data/own/` five hand-measured rooms | captured by the author on a Nokia 8.1 and a Moto Edge 50 Neo | **no**; gitignored |
| `data/own/app_comparision/` rival app screenshots | screenshots of AR Plan 3D (Grymala) and magicplan, taken by the author | **no**; gitignored. Used for comparison and identified by name |
| `benchmarks/ground_truth/*.yaml` | tape measurements by the author | yes |
| `benchmarks/captures/EXAMPLE*` | placeholder text files, not images | yes |
| `fix_loop/`, `docs/` figures and JSON | derived from the above by scripts in this repository | yes |

No third-party dataset is redistributed here. AR Plan 3D and magicplan are
referred to by name for comparison; no code or asset of theirs is included.

## AI coding assistance

This repository was written with AI coding assistance (Claude). Every design
decision, threshold and reported number was reviewed and, where it mattered,
re-measured; the negative results in `fix_loop/` and `docs/damage_eval/` are
reported as they came out.
