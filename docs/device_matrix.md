# Device matrix

What has actually been run on what, and what each combination delivers. Cells
that no measurement supports say so rather than carrying a number.

## Capture hardware tested

| device | tier | what was captured | how it was recorded |
|---|---|---|---|
| Nokia 8.1, Android | video | loop clips for hall, bedroom_1, bedroom_2, bedroom_2_repeat, kitchen | 3840 x 2160, H.264, about 30 fps, read from the files |
| Nokia 8.1, Android | photo | bedroom_2_repeat stills | 1200 x 1600 JPEG |
| Moto Edge 50 Neo, Android | photo | hall, bedroom_1, bedroom_2, kitchen stills | 1200 x 1600 JPEG |
| iPhone or iPad with LiDAR | lidar | the three supplied Stray Scanner scans | 1920 x 1440 HEVC at 60 fps, 256 x 192 depth |

**No iPhone was available for capture.** Every LiDAR-tier result in this
repository comes from the three Stray Scanner scans that were supplied, not
from a capture we made. The capture protocol's LiDAR route has therefore been
written from the format and the data, and has not been walked through end to
end on our own device.

Device attribution for the Android captures is the operator's record. EXIF
make and model were stripped from the supplied files, so it cannot be read
back from the images; the ground-truth files state this.

## Processing hardware tested

| machine | what runs on it | notes |
|---|---|---|
| Apple M1 Max, 32 GB, macOS | everything | LiDAR reconstruction 4 to 28 s per scan; OWLv2 about 0.2 s per image on mps |
| CPU only, macOS or Linux | everything | the reconstruction is CPU-only by design; only the damage models use a GPU when present |
| NVIDIA CUDA | damage models | supported by device order cuda, mps, cpu; not tested here |

## Accuracy by tier

| tier | capture hardware | processing | wall length | ceiling height | repeatability |
|---|---|---|---|---|---|
| lidar | iPhone or iPad with LiDAR | M1 Max, 4 to 28 s | **no tape ground truth exists for the supplied scans**; see below | measured at 3.06 to 3.08 m on the one scan that observed the ceiling, consistent to 1.5 cm across rooms | see below |
| video | Nokia 8.1 | pending | pending loop 2 results | pending loop 2 results | pending loop 2 results |
| photo | Moto Edge 50 Neo, Nokia 8.1 | pending | pending loop 2 results | pending loop 2 results | pending loop 2 results |

The video and photo rows are empty because those tiers are being built on
another branch. They will be filled from measurements against the tape
readings already recorded in `benchmarks/ground_truth/own_*.yaml`, and not
before.

### What can be said about the LiDAR tier without ground truth

Nobody measured the supplied property with a tape, so there is no accuracy
number for this tier and none is given. What exists instead is agreement
between two captures of the same flat:

| statistic | value |
|---|---|
| wall faces placed within, median | **1.9 cm** |
| face length with a counterpart in the other capture | 56% and 37% |
| registered footprint IoU | 0.61 |
| strict repeatability gate | 0 of 153 wall rows within tolerance |

The two numbers point in opposite directions and both are real. Where both
captures saw a wall, they place it to about two centimetres. But they saw
different parts of the flat, and they cut the same walls into different
polygon edges, so the strict gate fails completely. The pair is labelled
coverage-mismatched for that reason and is not presented as a valid repeat.

The official repeat pair, `bedroom_2` against `bedroom_2_repeat`, is
registered and awaiting predictions:

* **video tier: same device** (Nokia 8.1 for both captures). This is the
  primary repeatability evidence once the tier lands.
* **photo tier: cross-device** (Moto Edge 50 Neo against Nokia 8.1). Any
  disagreement there mixes pipeline repeatability with camera differences, so
  it is weaker evidence and is labelled as such in the benchmark report.

## Damage detection by tier

| tier | what the detector can say | measured |
|---|---|---|
| lidar | class, surface and a metric extent interval | 0 false regions on a clean scan after filtering |
| video | pending: needs the tier's reconstruction for depth | not run |
| photo | class only, extent explicitly unbounded | 9 false regions in a room with 2 marks |

Two of the four precision filters need depth and poses, so the photo tier
gets no benefit from them. Details in `damage_eval/README.md`.
