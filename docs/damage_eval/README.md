# Damage detection: what it finds and what it invents

Detector: OWLv2 (`google/owlv2-base-patch16-ensemble`, Apache 2.0) with text
prompts per damage class, two or three phrases each. Weights are fetched by
`scripts/fetch_damage_weights.py`; nothing downloads during a run.
Device order is cuda, then mps, then cpu. On an M1 Max it runs about 0.2 s per
image on mps after a 25 s model load.

Reproduce: `.venv/bin/python scripts/run_damage_eval.py`

## The headline

**Recall is fine. Precision is bad.** Both staged damage classes are found,
but only at a confidence threshold where the detector also reports dozens of
marks that are not there.

### Staged damage, `data/own/bedroom_2_repeat`, 9 photos

Two A4 sheets were taped up: a water stain on wall B, a crack on wall D.
Nothing else in the room is damaged.

| threshold | regions reported | water_stain | crack | other classes |
|---|---|---|---|---|
| 0.15 | 103 | 22 | 10 | 71 |
| 0.20 | 52 | 12 | 2 | 38 |
| 0.25 | 24 | 7 | 0 | 17 |
| 0.30 | 14 | 4 | 0 | 10 |
| 0.35 | 6 | 1 | 0 | 5 |
| 0.40 | 3 | 1 | 0 | 2 |

* **Hits:** both planted classes, water_stain and crack, at 0.15 and 0.20.
* **Misses:** none at 0.20 or below. The crack disappears entirely at 0.25.
* **False positives:** heavy at every useful threshold. At 0.20, 38 of 52
  regions are classes that are not present at all (missing_material,
  hole_puncture, peeling_paint, mould, burn_char). Two marks in the room
  produced 52 regions.

The default threshold is 0.20, the only setting measured that keeps both
planted classes. That choice buys recall with precision, and the numbers above
are the price.

These photos carry no depth, so every extent is emitted with method
`unbounded_no_metric_depth`, a nominal value and an interval from 0 to 4 m2,
plus a warning on the result. Nothing in that output should be read as a
measured area.

### LiDAR scan, `data/sample/c7d28f72c6`, 25 frames with depth

No known damage in this property. Everything reported is therefore either
real damage nobody recorded or a false positive.

| quantity | value |
|---|---|
| detections | 146 |
| merged regions | 121 |
| regions with a measured extent | 97 |
| extent range | 0.0015 to 2.58 m2 |
| classes reported | missing_material 61, water_stain 26, hole_puncture 13, mould 10, crack 5, peeling_paint 4, burn_char 2 |

A 2.58 m2 region is the size of a wall, not a mark, which is a clear sign the
box bounds far more than any damage. The glass shower screen was flagged as a
hazard before the run and the results are consistent with that: reflective
and transparent surfaces produce confident boxes of nothing.

## What is honest about this output

* Extents without depth are unbounded and labelled as such.
* With depth, the extent is an interval from a colour-contrast estimate to the
  box projected on the surface, because the box bounds the mark rather than
  being the mark.
* Concealed-damage flags name the rule and the evidence, and no rule carries
  a confidence above 0.6.
* Detections of the same mark across frames merge into one region when they
  land within 0.35 m in world coordinates.

## What this is not ready for

Do not put this in front of a client. At the precision measured here, a
surveyor would spend longer dismissing false positives than finding damage
themselves. The useful next steps, in order:

1. Restrict detections to the wall plane. Most false positives are furniture,
   fittings and reflections, and a depth-based planarity test would remove
   them without touching recall.
2. Require agreement across frames before emitting a region. A mark seen from
   one angle only is usually a reflection or a shadow.
3. Calibrate the confidence against these staged captures rather than trusting
   the raw model score.
