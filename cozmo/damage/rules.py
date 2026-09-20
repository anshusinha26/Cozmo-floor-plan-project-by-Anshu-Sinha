"""Concealed-damage rules, and the scope lookup. Both are tables, on purpose.

Every flag names the rule that produced it and the evidence it fired on, so a
reader can disagree with the rule rather than with the pipeline. These are
surveying heuristics, not measurements: each carries a confidence well below
one, and none of them asserts that concealed damage exists, only that a named
condition was observed which commonly indicates it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from cozmo.contracts.models import DamageClass


@dataclass
class Rule:
    id: str
    text: str
    confidence: float
    applies: Callable[[dict], bool]


def _cls(region: dict) -> str:
    return region["damage_class"]


RULES: list[Rule] = [
    Rule("CD-01",
         "Water stain on a ceiling indicates a leak in the floor or roof above",
         0.55,
         lambda r: _cls(r) == DamageClass.water_stain.value and r["surface_type"] == "ceiling"),
    Rule("CD-02",
         "Water stain within the lowest 0.5 m of a wall indicates moisture behind the skirting",
         0.45,
         lambda r: _cls(r) == DamageClass.water_stain.value and r["surface_type"] == "wall"
         and r.get("height_above_floor_m") is not None and r["height_above_floor_m"] <= 0.5),
    Rule("CD-03",
         "Water stain below a window indicates a failed seal or sill",
         0.50,
         lambda r: _cls(r) == DamageClass.water_stain.value and r.get("below_opening_type") == "window"),
    Rule("CD-04",
         "Diagonal crack running from the corner of an opening indicates structural movement",
         0.50,
         lambda r: _cls(r) == DamageClass.crack.value and r.get("near_opening_corner", False)
         and r.get("diagonal", False)),
    Rule("CD-05",
         "Any mould indicates a moisture source that is not visible at the surface",
         0.60,
         lambda r: _cls(r) == DamageClass.mould.value),
    Rule("CD-06",
         "Peeling paint beside a window indicates water ingress around the frame",
         0.40,
         lambda r: _cls(r) == DamageClass.peeling_paint.value and r.get("near_opening_type") == "window"),
    Rule("CD-07",
         "Burn or char marks indicate heat damage that may extend into the substrate",
         0.45,
         lambda r: _cls(r) == DamageClass.burn_char.value),
    Rule("CD-08",
         "Missing material exposes the substrate, which may be damaged behind the surface",
         0.40,
         lambda r: _cls(r) == DamageClass.missing_material.value),
]


@dataclass
class ScopeRule:
    damage_class: str
    surface_type: str | None  # None matches any
    description: str
    basis: str
    # Multiplier on the damaged extent: repairs feather out beyond the mark.
    quantity_factor: float = 1.0
    minimum_m2: float = 0.25


SCOPE_TABLE: list[ScopeRule] = [
    ScopeRule(DamageClass.water_stain.value, "wall",
              "Stain-block and repaint the affected wall area", "damage extent with feathering allowance", 1.5),
    ScopeRule(DamageClass.water_stain.value, "ceiling",
              "Trace the leak, then stain-block and repaint the ceiling area",
              "damage extent with feathering allowance", 2.0, 0.5),
    ScopeRule(DamageClass.mould.value, None,
              "Treat with fungicidal wash, then seal and redecorate",
              "damage extent plus a 0.3 m treated margin", 2.0, 0.5),
    ScopeRule(DamageClass.crack.value, "wall",
              "Rake out, fill and redecorate the cracked area", "damage extent with feathering allowance", 1.5),
    ScopeRule(DamageClass.crack.value, "ceiling",
              "Rake out, fill and redecorate the cracked ceiling area",
              "damage extent with feathering allowance", 1.5),
    ScopeRule(DamageClass.hole_puncture.value, None,
              "Cut out, patch and make good", "damage extent plus a patch margin", 2.0),
    ScopeRule(DamageClass.burn_char.value, None,
              "Cut out charred material, treat and make good", "damage extent plus a cut-back margin", 2.0),
    ScopeRule(DamageClass.missing_material.value, None,
              "Replace the missing material and make good", "damage extent plus a fixing margin", 1.5),
    ScopeRule(DamageClass.peeling_paint.value, None,
              "Scrape back, prepare and repaint", "damage extent with feathering allowance", 1.5),
]


def scope_for(damage_class: str, surface_type: str) -> ScopeRule | None:
    for rule in SCOPE_TABLE:
        if rule.damage_class == damage_class and (rule.surface_type in (None, surface_type)):
            return rule
    return None
