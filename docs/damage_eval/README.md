# Damage detection: what it finds, what it invents, and what the filters fix

Detector: OWLv2 (`google/owlv2-base-patch16-ensemble`, Apache 2.0) with text
prompts per damage class. Crop verifier: SigLIP
(`google/siglip-base-patch16-224`, Apache 2.0). Weights come from
`scripts/fetch_weights.sh`; nothing downloads during a run. Device order is
cuda, mps, cpu. About 0.2 s per image on an M1 Max after a 25 s load.

Reproduce:

```bash
.venv/bin/python scripts/damage_ablation.py     # the tables below
.venv/bin/python scripts/run_damage_eval.py     # a single end-to-end run
```

## The four precision filters, measured one at a time

Detections are computed once per frame and replayed for every row, so the only
thing changing down a column is the filter.

### Staged damage, `data/own/bedroom_2_repeat`, 9 photos, no depth

Two A4 sheets: a water stain on wall B, a crack on wall D. Nothing else in the
room is damaged, so every other region is a false positive.

Threshold 0.15, the shipped default:

| stage | regions | false regions | hits |
|---|---|---|---|
| raw | 93 | 63 | water_stain, crack |
| 1 distractor prompts | 91 | 61 | water_stain, crack |
| 2 + geometry | 91 | 61 | water_stain, crack |
| 3 + multi-view | 91 | 61 | water_stain, crack |
| 4 + crop verifier | **27** | **9** | water_stain, crack |

Threshold 0.20:

| stage | regions | false regions | hits | misses |
|---|---|---|---|---|
| raw | 50 | 36 | water_stain, crack | none |
| 4 + all filters | 11 | 4 | water_stain | **crack** |

Threshold 0.25: the crack is already gone before any filter runs.

### Clean LiDAR scan, `data/sample/c7d28f72c6`, 25 frames with depth and poses

No known damage, so every region is a false positive.

| stage | regions at 0.15 | at 0.20 | at 0.25 |
|---|---|---|---|
| raw | 106 | 44 | 21 |
| 1 distractor prompts | 104 | 42 | 21 |
| 2 + geometry | 72 | 31 | 13 |
| 3 + multi-view | 26 | 10 | 3 |
| 4 + crop verifier | **0** | **0** | **0** |

## Against the targets

| target | result |
|---|---|
| both staged marks still found | **met** at threshold 0.15 |
| under 5 false regions in bedroom_2_repeat | **not met: 9** |
| under 5 false regions on the clean LiDAR scan | **met: 0** |

Two of three. The photo case is the one that misses, and the reason is
structural rather than a tuning failure: two of the four filters cannot run on
it at all.

## What each filter is actually worth

**1. Distractor prompts: almost nothing.** 93 to 91 on photos, 106 to 104 on
LiDAR. The idea was that a shadow would score higher as "a shadow on the wall"
than as damage. It does, occasionally, but OWLv2 rarely puts the two labels on
the same box, so the overlap rule seldom fires. Two rejections in each case.
Kept because it costs one forward pass over more text and does no harm, but it
is not carrying the result.

**2. Geometry: strong where it can run, absent where it cannot.** 106 to 72 on
LiDAR, a third of the boxes removed for being too large a share of their
surface or too far off any plane. On photos it does nothing at all, because
without depth there is no size and no plane to test against.

**3. Multi-view: the strongest geometric filter.** 72 to 26 on LiDAR. Most
false positives are seen once, from one angle, which is what a reflection or a
shadow does. On photos it does nothing, for the reason in the next section.

**4. Crop verifier: the one that does the work.** 26 to 0 on LiDAR and 91 to
27 on photos. A second model asked whether the crop reads as damage or as a
clean wall, a shadow, furniture or glass disagrees with OWLv2 most of the
time, and it is usually right to.

## Known failure modes

* **The multi-view rule cannot be applied to photo folders as specified.** The
  brief asked for a region to be kept only if seen in two or more photos when
  it is visible in two or more. Without poses or depth there is no way to know
  whether a mark was in the frame of another photo, so a single sighting
  cannot be distinguished from a mark that was only ever photographed once.
  The rule therefore allows single sightings when there is no geometry, and
  the photo case gets no benefit. A weaker class-level version was considered
  and rejected as meaningless.
* **The crop verifier trades recall for precision, and the crack is the
  casualty.** At threshold 0.20 the verifier removes the crack along with the
  false positives. A thin dark line on a painted wall reads as "a clean
  painted wall" to SigLIP more often than as "a wall with a crack". Cracks are
  the class most at risk in this pipeline.
* **Reflective and transparent surfaces still generate confident boxes**, but
  after the filters they no longer survive on the LiDAR scan. The glass shower
  screen was the known hazard and it is now handled, by geometry and
  multi-view rather than by the prompts.
* **Nine false regions remain in a room with two marks.** They are mostly
  furniture edges and fittings that the verifier accepts. A surveyor would
  still be dismissing more than they confirm.
* **Extents without depth stay unbounded.** Method
  `unbounded_no_metric_depth`, interval 0 to 4 m2, plus a warning. Nothing in
  that output is a measured area.

## Honest summary

The filters turned an unusable detector into one that is clean on a LiDAR
capture and noisy on a photo capture. The gap between the two is not tuning:
it is that half the filtering depends on depth and poses, which the photo tier
does not have. If damage detection has to work from photos alone, the next
step is not another threshold but a plane estimate from the photo tier's own
reconstruction, which is being built elsewhere.
