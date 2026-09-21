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
| photo | Moto Edge 50 Neo, Nokia 8.1 | M1 Max, 78 s one room, 1378 s for four | **13.0%** over 12 walls | 31.9% | 2.1 to 10.7 cm error | 0.88 at 46% mean width |
| video | Nokia 8.1 | M1 Max, about 8 min a clip | **32.9%** over 16 walls | 137.4% | 27.2 to 63.3 cm error | 1.00 at 409% mean width |

Neither image tier is accurate enough to ship. Photo is much the better of
the two and now meets its 8% budget on 6 of 12 walls.

From `docs/benchmark/eval.json`, rebuilt by `scripts/benchmark_all.py`.

**Read the coverage column with the width column.** The video tier covers
every tape reading because its intervals average four times the value it
reports: too wide to be wrong. The photo tier is the opposite, covering only
0.88 against a nominal 0.95, with two confident-garbage cases.

**The photo tier briefly scored worse on the camera originals than on
compressed copies of the same photographs, and the cause was found**:
MapAnything was estimating the focal length instead of being given it, and
guessed 464 px against a true 332 px. Giving it the EXIF focal took the tier
from 22.4% to 13.0% median wall error. Evidence in
`fix_loop/loop2_video_scale/photo_ablation.md`.

Photographs still beat video on the same rooms with the same scale cue and
room fitter, which is why the capture protocol recommends them.

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
