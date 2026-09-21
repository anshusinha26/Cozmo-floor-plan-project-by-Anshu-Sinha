# Hazards seen in real captures

One section per hazard: what it does, what the evidence says, and what the
pipeline does about it. Where the pipeline does nothing yet, that is written
down rather than left out.

Every number names the file it comes from. Regenerate with
`scripts/regenerate_all.sh`.

---

## Glass: the shower screen

**What it does.** A glass shower screen returns depth from the glass, from
what is behind it, and from reflections in it. The scanner records wall faces
for a room that does not exist.

**Evidence.** `fix_loop/evidence/evidence.json`, key `d_ghost_faces`, from
`fix_loop/evidence_run.py`:

| scan | wall-face length outside the room envelope |
|---|---|
| c7d28f72c6 | 34.9 m of 216.2 m, 16% |
| 1a8384c3f6 | 16.8 m of 102.5 m, 16% |
| c00a170fe1 | 0.0 m of 10.4 m, 0% |

That 16% was the first measurement and it **over-counts**, because the
envelope it tests against is built from the room polygons the segmentation
produced, and those polygons are themselves inflated. A visibility test that
asks whether anyone stood beside the face is the better measure and puts the
real figure near 1%: ghost rejection drops 2 faces (1.0 m) on c7d28f72c6 and
3 faces (2.0 m) on 1a8384c3f6
(`fix_loop/experiments/ghost_only/result.json`).

**What the pipeline does.** `cozmo/lidar/ghosts.py` keeps a wall face only
when observed floor lies within 25 cm of at least a quarter of its length, on
either side. A real wall has floor beside it because somebody stood there;
glass returns outside the property do not. Rejected faces produce a warning
naming the count and the length.

For damage detection the same hazard is handled much better, by geometry and
multi-view rather than by the prompts. On the scan containing the shower
screen the filter chain runs 106 raw regions to 72 after geometry, 26 after
multi-view and **0** after the crop verifier
(`docs/damage_eval/ablation.json`).

**What still breaks.** Mirrored geometry that sits inside the property
envelope still contributes wall faces, because floor was observed beside it.
Ghost rejection is a visibility test, not a reflection detector.

---

## Mirrors: the wardrobe mirror in bedroom_2

**What it does.** A wardrobe mirror shows a second copy of the room, at the
correct depth for the reflection, so the sensor reports a room extending
beyond the wall. Unlike the shower screen, the reflected geometry usually
falls inside the building envelope, which is what makes it harder.

**Evidence.** The mirror is visible to the detector and harmless to the
measurement. Running the detector's distractor prompts over the nine
bedroom_2 photos
(`docs/damage_eval/mirror_glass_detections.json`):

| prompt | detections in bedroom_2 | best confidence |
|---|---|---|
| a glass panel | 73 | 0.467 |
| a mirror | 10 | 0.534 |
| a reflection on a glossy surface | 1 | 0.105 |

Despite that, the photo tier measured bedroom_2's walls to within
**3.6 cm and 4.4 cm of tape** (`docs/benchmark/eval.json`, rebuilt by `scripts/benchmark_all.py`), which is
the best of any room the photo tier measured. The mirror did not pull the
wall out of place.

The reason is the mirror's position: it is on a wardrobe against a wall, so
the reflected geometry sits behind a surface that was itself observed from a
metre away. Wall fitting takes the strongest plane along each axis, and the
real wall has far more support than the reflection behind it.

**What the pipeline does.** Nothing specific about mirrors. It survives this
one by luck of geometry, not by handling it.

**What would fix it.** A mirror produces geometry that is a reflection of
observed geometry about the mirror plane. Detecting that symmetry is
tractable and is not implemented.

---

## Wet-look and glossy surfaces: floor tiles

**What it does.** Glossy tiles return light from the reflection as well as
from the surface, so the floor comes back as two overlapping populations a
few centimetres apart. The floor peak thickens rather than moving.

**Evidence.** Floor plane residual spread, from the run manifests and level
detection on the supplied scans: 10 to 13 mm, against a depth quantisation of
1 mm. The floor is still found as a single sharp peak in every scan, and the
regression test that pins the floor of c00a170fe1 at y = -1.48 m holds to
within 2 cm (`tests/test_stray.py`).

**What the pipeline does.** The floor and ceiling are fitted with a trimmed
least-squares plane that discards points beyond 2 sigma over two passes
(`cozmo/lidar/levels.py`), so a reflection population that sits off the
surface is trimmed rather than averaged in.

**What still breaks.** A mirror-finish floor would put a full reflected room
below the floor plane. The supplied captures do not contain one, so this is
untested rather than handled.

---

## Low light

**LiDAR is active sensing and does not depend on room light.** The sensor
emits its own infrared pulses and times their return, so a dark room and a
bright room give the same depth. Nothing in the LiDAR reconstruction path
reads the RGB stream at all: it uses `depth/`, `confidence/` and
`odometry.csv` only. A capture in the dark measures the same as a capture with
the lights on. The one thing that does degrade is the operator's ability to
walk the room safely, which the capture protocol covers by saying lights on.

**The image-based damage detector is a different matter**, because it reads
pixels. Measured by `scripts/hazard_lowlight.py`, which darkens frames by
gamma and re-runs the full detector and filter chain
(`docs/damage_eval/lowlight_lidar.json`):

| level | mean brightness, 0 to 255 | regions reported |
|---|---|---|
| bright, original | 150.6 | 5 |
| dim, gamma 1.8 | 105.2 | 6 |
| dark, gamma 3.0 | 65.5 | 4 |

Detection volume is roughly flat from bright to dark on this material. That
says the detector does not collapse in low light; it does not say the right
things survive, because this property has no known damage.

**The staged marks survive darkening.** Measured on the nine
`bedroom_2_repeat` photos, darkened by gamma and put through the full
detector and filter chain (`docs/damage_eval/lowlight_own.json`,
`scripts/hazard_lowlight.py --source own`):

| level | mean brightness, 0 to 255 | regions | false regions | found | missed |
|---|---|---|---|---|---|
| bright (original) | 134.3 | 44 | 8 | crack, water_stain | none |
| dim (gamma 1.8) | 91.9 | 47 | 15 | crack, water_stain | none |
| dark (gamma 3.0) | 58.4 | 31 | 11 | crack, water_stain | none |

**Both staged classes survive at every level**, down to a mean brightness of
58 out of 255, which is a room lit by one lamp at dusk. False regions do not
climb with darkness either: 8, 15, then 11.

What this does not show is that low light is free. The detector was given
photographs taken in good light and then darkened, which removes information
but adds no sensor noise. A photograph actually taken in the dark carries
motion blur and high-ISO grain as well, and neither is simulated here.

---

## Also seen

### A moving dog

A dog walked through one capture. Moving objects break the assumption every
stage relies on, that the scene is static: the same world point gets different
depths at different times, so the dog appears as a smear of points along the
path it took.

**What the pipeline does.** Nothing directly. Two things limit the damage
indirectly: voxel averaging at 2 cm dilutes points seen once, and the wall
face extractor needs at least 150 points in a 2 cm histogram bin before it
calls something a face, so a passing animal does not usually become a wall.

**What still breaks.** A pet that settles in one place for part of the capture
is indistinguishable from furniture, and furniture that reaches above 1.6 m is
treated as a wall.

### Textureless white walls

Plain white walls near the sensor's range limit return sparse, noisy depth.
This is a strong contributor to the coverage problem that fix loop 1 ended on:
only **56% and 37%** of each capture's wall-face length has any counterpart in
the other capture of the same flat
(`fix_loop/evidence/evidence.json`). Two people walking the same flat do not
come back with the same walls.

**What the pipeline does.** Rooms whose outline is under 80% backed by
observed wall are flagged `partially_observed`, and their length and area
intervals are doubled. On the largest supplied scan that is 10 of 11 rooms.
The plan says so in a warning per room.

For the image tiers this matters differently: a textureless wall gives feature
matching nothing to work with, which is a known limit of the SfM route rather
than something this branch measures.

### A ceiling never observed

The commonest single cause of a wide interval, and entirely a capture problem.

**Evidence.** `fix_loop/evidence/evidence.json`, key `e_height_coverage`: two
of the three supplied scans never observed enough ceiling. Median wall-point
height is 0.87 m and 0.97 m in those two, against 1.42 m in the one that did.
People point phones downward.

**What the pipeline does.** Where the ceiling covers under 15% of floor cells,
it refuses to measure: method `prior_no_ceiling_observed`, a 2.2 to 3.2 m
interval, and a warning. The scan that did observe its ceiling measured
3.06 to 3.08 m across rooms, consistent to 1.5 cm.

**The fix is in the protocol, not the code.** One deliberate tilt upward per
room, which `docs/capture_protocol.md` asks for and explains.

---

## Note on data access

`data/own` was unreadable for part of this work under macOS quarantine, which
is why an earlier version of this document carried two PENDING items. Access
was restored and both were measured: the mirror section and the low-light
table above are real results, not estimates. The photographs are now the
camera originals rather than the compressed copies used earlier, which is why
false-region counts here differ from `docs/damage_eval/README.md`.
