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

**Evidence.** The bedroom_2 captures could not be re-read during this session
(see the note at the end of this document), so no number is given for this
room. What is measured is the general case above: faces without observed
floor beside them are rejected, faces with it are not, and a mirror on a wall
somebody stood next to is in the second group.

**What the pipeline does.** Nothing specific. This is a known gap.

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

**PENDING: whether the staged stain and crack survive darkening.** This is the
measurement the hazard section actually needs, and it could not be taken. The
staged-damage photos in `data/own/bedroom_2_repeat` carry
`com.apple.quarantine` and `com.apple.macl` extended attributes and are
blocked by macOS at the time of writing: the directory lists but every file
read fails with `PermissionError: Operation not permitted`. Earlier results in
`docs/damage_eval/` were taken from these photos before the restriction
appeared. Once file access is restored, one command answers it:

```bash
.venv/bin/python scripts/hazard_lowlight.py --source own
```

The script already handles this case: it reports the permission problem and
exits rather than silently reporting nothing.

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

## Note on data access during this session

`data/own` became unreadable partway through this work: the files carry macOS
quarantine attributes and every read returns `Operation not permitted`, while
`data/sample` is unaffected. Results already derived from those photos stand
and are in `docs/damage_eval/`. Measurements that needed a fresh read of them
are marked PENDING above with the command that produces them. Nothing was
substituted silently.
