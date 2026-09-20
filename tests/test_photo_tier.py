"""Photo tier: stitching, merging and door placement.

Model free. MapAnything and OWLv2 are not exercised here; what is under test is
what happens to their output, which is where the assumptions live.
"""

from __future__ import annotations

import numpy as np
import pytest
from shapely.geometry import Polygon as SPoly

from cozmo.contracts.models import Measurement, Plan, Room, Wall
from cozmo.pipeline import pipeline_for
from cozmo.pipeline.photo.openings import DoorDetection, attach_doors
from cozmo.pipeline.photo.room import normals_from_world_pointmap
from cozmo.pipeline.photo.stitch import CONNECTOR_NAMES, choose_connector, stitch


def _rect(w: float, d: float):
    return [(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)]


# ------------------------------------------------------------------ connector

def test_the_connector_is_the_one_named_like_a_hall():
    ids = ["bedroom_1", "hall", "kitchen"]
    assert choose_connector(ids, {"bedroom_1": 20.0, "hall": 4.0, "kitchen": 9.0}, None) == "hall"


def test_without_a_named_connector_the_biggest_room_wins():
    ids = ["bedroom_1", "study", "kitchen"]
    assert choose_connector(ids, {"bedroom_1": 20.0, "study": 4.0, "kitchen": 9.0}, None) == "bedroom_1"


def test_an_explicit_connector_must_exist():
    with pytest.raises(ValueError):
        choose_connector(["a", "b"], {}, "c")


def test_every_connector_name_is_recognised():
    for name in CONNECTOR_NAMES:
        assert choose_connector([f"{name}_01", "other"], {"other": 99.0}, None) == f"{name}_01"


# -------------------------------------------------------------------- stitch

def test_stitched_rooms_never_overlap():
    rooms = {"hall": _rect(2, 5), "bedroom_1": _rect(4, 3), "kitchen": _rect(3, 2.5),
             "bedroom_2": _rect(3.5, 3)}
    r = stitch(rooms, {}, "hall")
    assert r.overlap_m2 == pytest.approx(0.0, abs=1e-6)
    polys = [SPoly(p.polygon) for p in r.placed]
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            assert polys[i].intersection(polys[j]).area == pytest.approx(0.0, abs=1e-6)


def test_the_footprint_is_the_sum_when_nothing_overlaps():
    rooms = {"hall": _rect(2, 5), "bedroom_1": _rect(4, 3)}
    r = stitch(rooms, {}, "hall")
    assert r.footprint_area_m2 == pytest.approx(10.0 + 12.0, abs=0.01)


def test_every_room_is_adjacent_to_the_connector_and_only_to_it():
    rooms = {"hall": _rect(2, 5), "a": _rect(3, 3), "b": _rect(3, 3)}
    r = stitch(rooms, {}, "hall")
    assert sorted((x, y) for x, y, _ in r.adjacency) == [("hall", "a"), ("hall", "b")]
    assert all(x == "hall" for x, _, _ in r.adjacency)


def test_room_shapes_survive_the_stitch_unchanged():
    """The stitch may move and turn a room; it must never resize one."""
    rooms = {"hall": _rect(2, 5), "bedroom_1": _rect(4, 3)}
    r = stitch(rooms, {}, "hall")
    placed = {p.room_id: SPoly(p.polygon).area for p in r.placed}
    assert placed["bedroom_1"] == pytest.approx(12.0, abs=1e-6)
    assert placed["hall"] == pytest.approx(10.0, abs=1e-6)


def test_a_door_pair_is_preferred_over_a_wall():
    rooms = {"hall": _rect(2, 5), "bedroom_1": _rect(4, 3)}
    doors = {"hall": [{"id": "hall_d1", "width_m": 0.9, "centre": (2.0, 2.5)}],
             "bedroom_1": [{"id": "b1_d1", "width_m": 0.9, "centre": (0.0, 1.5)}]}
    r = stitch(rooms, doors, "hall")
    attached = {p.room_id: p.attached_by for p in r.placed}
    assert attached["bedroom_1"] == "door"
    assert r.adjacency[0][2] == "hall_d1"


# -------------------------------------------------------------------- doors

def _room_with_walls():
    def m(v):
        return Measurement(value=v, ci_low=v - 0.1, ci_high=v + 0.1, unit="m", method="t",
                           ci_level=0.95)

    walls = [Wall(id="w1", start=(0.0, 0.0), end=(4.0, 0.0), length_m=m(4.0), height_m=m(2.7)),
             Wall(id="w2", start=(4.0, 0.0), end=(4.0, 3.0), length_m=m(3.0), height_m=m(2.7)),
             Wall(id="w3", start=(4.0, 3.0), end=(0.0, 3.0), length_m=m(4.0), height_m=m(2.7)),
             Wall(id="w4", start=(0.0, 3.0), end=(0.0, 0.0), length_m=m(3.0), height_m=m(2.7))]
    return Room(id="room_01", label="room", polygon=_rect(4, 3), walls=walls,
                ceiling_height_m=m(2.7), floor_area_m2=m(12.0), openings=[])


def test_a_door_lands_on_the_wall_its_points_lie_on():
    room = _room_with_walls()
    det = DoorDetection("room_01", "p.jpg", 0.4, (1.5, 1.0, 0.02), 0.91, 2.0, 1, (1.05, 1.96), 400)
    doors, dropped = attach_doors(room, [det], 0.95)
    assert dropped == 0 and len(doors) == 1
    assert doors[0].wall_id == "w1"
    assert doors[0].width_m.value == pytest.approx(0.91)
    # The offset runs from the wall's start to the door's leading edge.
    assert doors[0].offset_along_wall_m.value == pytest.approx(1.5 - 0.91 / 2, abs=0.05)


def test_a_door_that_lands_on_no_wall_is_dropped_not_forced():
    room = _room_with_walls()
    det = DoorDetection("room_01", "p.jpg", 0.4, (2.0, 1.0, 1.5), 0.9, 2.0, 1, (1.5, 2.4), 400)
    doors, dropped = attach_doors(room, [det], 0.95)
    assert doors == [] and dropped == 1


# ------------------------------------------------------------------- normals

def test_world_pointmap_normals_face_the_camera():
    h = w = 16
    y, x = np.mgrid[0:h, 0:w]
    P = np.stack([x / 10.0, y / 10.0, np.full((h, w), 3.0)], axis=-1)
    valid = np.ones((h, w), dtype=bool)
    n, ok = normals_from_world_pointmap(P, valid, np.array([0.8, 0.8, 0.0]))
    assert ok[4:-4, 4:-4].all()
    assert np.allclose(np.abs(n[ok][:, 2]), 1.0, atol=1e-6)
    assert (n[ok][:, 2] < 0).all()      # the camera is at z = 0, the plane at z = 3


# ------------------------------------------------------------------- wiring

def test_the_photo_tier_is_registered():
    assert pipeline_for("photo") == "photo"
