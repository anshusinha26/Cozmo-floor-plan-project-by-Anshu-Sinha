# Third-party models, libraries and data

Everything this project depends on, what it is used for, and its licence.
This repository is MIT (see `LICENSE`).

## Models

Both are optional: they are used only by damage detection. **Reconstruction
uses no trained model at all**, so nothing in a reported dimension came from
a network.

| model | version | use | licence |
|---|---|---|---|
| [OWLv2](https://huggingface.co/google/owlv2-base-patch16-ensemble) | `google/owlv2-base-patch16-ensemble` | open-vocabulary damage detection from text prompts | Apache 2.0 |
| [SigLIP](https://huggingface.co/google/siglip-base-patch16-224) | `google/siglip-base-patch16-224` | zero-shot crop verifier that rejects false detections | Apache 2.0 |

Measured download sizes: OWLv2 1.2 GB, SigLIP 1.5 GB. Fetched by
`scripts/fetch_weights.sh` and never downloaded during a run.

### Models evaluated and not used

| model | why not | evidence |
|---|---|---|
| [MapAnything](https://github.com/facebookresearch/map-anything) | metric scale wrong by about 30% and consistent across runs; fused cloud does not produce straight walls | `docs/experiments/mapanything/result.json` |

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
| torch, torchvision | `damage` | runs the two models | BSD 3-Clause |
| transformers | `damage` | loads and runs OWLv2 and SigLIP | Apache 2.0 |
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
