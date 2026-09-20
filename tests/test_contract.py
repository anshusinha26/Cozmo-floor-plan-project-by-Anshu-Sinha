"""Output contract: referential integrity, geometry conventions, schema round trip."""

from __future__ import annotations

import json
import math

import jsonschema
import pytest
from pydantic import ValidationError

from cozmo.contracts.export_schema import build_schema
from cozmo.contracts.models import SCHEMA_VERSION, DamageClass, Plan


def test_fixture_is_valid(plan_dict):
    plan = Plan.model_validate(plan_dict)
    assert [r.id for r in plan.rooms] == ["living", "hall"]


def test_schema_version_mismatch_rejected(plan_dict):
    plan_dict["schema_version"] = "0.9.0"
    with pytest.raises(ValidationError, match="schema_version"):
        Plan.model_validate(plan_dict)


def test_clockwise_room_polygon_rejected(plan_dict):
    plan_dict["rooms"][0]["polygon"] = list(reversed(plan_dict["rooms"][0]["polygon"]))
    with pytest.raises(ValidationError, match="CCW"):
        Plan.model_validate(plan_dict)


def test_polygon_needs_three_vertices(plan_dict):
    plan_dict["rooms"][0]["polygon"] = [[0.0, 0.0], [1.0, 0.0]]
    with pytest.raises(ValidationError):
        Plan.model_validate(plan_dict)


def test_duplicate_room_ids_rejected(plan_dict):
    plan_dict["rooms"][1]["id"] = "living"
    with pytest.raises(ValidationError, match="duplicate"):
        Plan.model_validate(plan_dict)


def test_duplicate_wall_ids_rejected(plan_dict):
    plan_dict["rooms"][0]["walls"][1]["id"] = "w1"
    with pytest.raises(ValidationError, match="duplicate"):
        Plan.model_validate(plan_dict)


def test_opening_must_reference_wall_in_same_room(plan_dict):
    plan_dict["rooms"][0]["openings"][0]["wall_id"] = "h1"
    with pytest.raises(ValidationError, match="wall_id"):
        Plan.model_validate(plan_dict)


def test_adjacency_must_reference_known_rooms(plan_dict):
    plan_dict["adjacency"][0]["room_b"] = "kitchen"
    with pytest.raises(ValidationError, match="kitchen"):
        Plan.model_validate(plan_dict)


def test_adjacency_must_reference_known_opening(plan_dict):
    plan_dict["adjacency"][0]["via_opening_id"] = "o99"
    with pytest.raises(ValidationError, match="o99"):
        Plan.model_validate(plan_dict)


def test_adjacency_self_edge_rejected(plan_dict):
    plan_dict["adjacency"][0]["room_b"] = "living"
    with pytest.raises(ValidationError, match="itself"):
        Plan.model_validate(plan_dict)


def test_placement_required_for_every_room(plan_dict):
    plan_dict["stitched_plan"]["placements"].pop()
    with pytest.raises(ValidationError, match="placement"):
        Plan.model_validate(plan_dict)


def test_wall_surface_requires_existing_wall(plan_dict):
    plan_dict["surfaces"][0]["wall_id"] = "w9"
    with pytest.raises(ValidationError, match="w9"):
        Plan.model_validate(plan_dict)


def test_floor_surface_must_not_carry_wall_id(plan_dict):
    plan_dict["surfaces"][1]["wall_id"] = "w1"
    with pytest.raises(ValidationError, match="wall_id"):
        Plan.model_validate(plan_dict)


def test_damage_region_must_reference_surface(plan_dict):
    plan_dict["damage_regions"][0]["surface_id"] = "nope"
    with pytest.raises(ValidationError, match="nope"):
        Plan.model_validate(plan_dict)


def test_scope_item_must_reference_damage_regions(plan_dict):
    plan_dict["scope_items"][0]["damage_region_ids"] = ["d1", "d7"]
    with pytest.raises(ValidationError, match="d7"):
        Plan.model_validate(plan_dict)


def test_unknown_damage_class_rejected(plan_dict):
    plan_dict["damage_regions"][0]["damage_class"] = "rust"
    with pytest.raises(ValidationError):
        Plan.model_validate(plan_dict)


def test_damage_class_enum_is_the_single_source():
    assert {c.value for c in DamageClass} == {
        "water_stain",
        "mould",
        "crack",
        "hole_puncture",
        "burn_char",
        "missing_material",
        "peeling_paint",
    }


def test_confidence_out_of_range_rejected(plan_dict):
    plan_dict["damage_regions"][0]["confidence"] = 1.2
    with pytest.raises(ValidationError):
        Plan.model_validate(plan_dict)


def test_json_bytes_are_deterministic_and_newline_terminated(plan_dict):
    a = Plan.model_validate(plan_dict).to_json_bytes()
    b = Plan.model_validate(json.loads(a)).to_json_bytes()
    assert a == b
    assert a.endswith(b"\n")


def test_schema_round_trip(plan_dict):
    plan = Plan.model_validate(plan_dict)
    schema = build_schema()
    assert schema["$schema"].startswith("https://json-schema.org/draft/2020-12")
    assert schema["title"] == "Plan"
    assert schema["version"] == SCHEMA_VERSION
    instance = json.loads(plan.to_json_bytes())
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(instance)
    assert Plan.model_validate(instance) == plan


def test_schema_rejects_bare_float_dimension(plan_dict):
    instance = json.loads(Plan.model_validate(plan_dict).to_json_bytes())
    instance["rooms"][0]["ceiling_height_m"] = 2.7
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(build_schema()).validate(instance)


DIMENSION_SUFFIXES = ("_m", "_m2", "_deg")
MEASUREMENT_KEYS = {"value", "ci_low", "ci_high", "unit", "method", "ci_level"}


def _walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, node


def assert_no_bare_dimensions(instance: dict) -> None:
    """Fail if any key ending in _m, _m2 or _deg maps to a bare number.

    Used by the contract test here and by the CLI test on real emitted output.
    """
    offenders = []

    def visit(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                p = f"{path}.{k}"
                if k.endswith(DIMENSION_SUFFIXES):
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        offenders.append(p)
                    elif isinstance(v, dict) and not MEASUREMENT_KEYS.issubset(v):
                        offenders.append(p)
                visit(v, p)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                visit(v, f"{path}[{i}]")

    visit(instance, "$")
    assert not offenders, f"bare dimensions found: {offenders}"


def test_no_bare_float_dimensions_in_fixture(plan_dict):
    assert_no_bare_dimensions(json.loads(Plan.model_validate(plan_dict).to_json_bytes()))


def test_bare_dimension_walker_catches_offender(plan_dict):
    instance = json.loads(Plan.model_validate(plan_dict).to_json_bytes())
    instance["rooms"][0]["walls"][0]["length_m"] = 4.0
    with pytest.raises(AssertionError, match="length_m"):
        assert_no_bare_dimensions(instance)


def test_room_area_helper_matches_shoelace(plan_dict):
    plan = Plan.model_validate(plan_dict)
    assert math.isclose(plan.rooms[0].polygon_area(), 12.0)
