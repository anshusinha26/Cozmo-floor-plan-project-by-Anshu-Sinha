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

| tier | capture hardware | processing | wall length, median error | worst wall | ceiling height | interval coverage |
|---|---|---|---|---|---|---|
| lidar | iPhone or iPad with LiDAR | M1 Max, 4 to 28 s | **no tape ground truth exists**, see below | n/a | 3.06 to 3.08 m on the one scan that saw its ceiling | n/a |
| photo | Moto Edge 50 Neo, Nokia 8.1 | M1 Max, 77 s for four rooms | **1.4%** over 12 walls | 21.5% | 11.9 to 85.8 cm error | 0.94 at 43% mean width |
| video | Nokia 8.1 | M1 Max, about 8 min a clip | **32.9%** over 16 walls | 137.4% | 27.2 to 63.3 cm error | 1.00 at 409% mean width |

From `docs/benchmark/eval.json`, rebuilt by `scripts/benchmark_all.py`.

**Read the coverage column with the width column.** The video tier covers
every tape reading because its intervals average four times the value it is
reporting. That is not calibration, it is an interval too wide to be wrong.
The photo tier's 0.94 at 43% width is the meaningful number of the two.

**The photo tier is an order of magnitude better than the video tier** on the
same rooms, with the same scale cue and the same room fitter. Nine deliberate
stills beat fifty seconds of walking video. That is a capture difference, not
an algorithm difference, and it is why the capture protocol now recommends
photos over video where both are possible.

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
| photo | class only, extent explicitly unbounded | 8 false regions in a room with 2 marks, both marks found |
| video | as photo; the tier's own depth is not yet wired into the detector | not run |

Two of the four precision filters need depth and poses, so the photo tier
gets no benefit from them. Details in `damage_eval/README.md`.
