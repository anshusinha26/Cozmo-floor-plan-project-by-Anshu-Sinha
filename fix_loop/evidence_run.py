"""Evidence for the repeatability fix loop. Writes figures and evidence.json.

Run: .venv/bin/python fix_loop/evidence_run.py
Reads data/sample and the BEFORE plans; writes fix_loop/evidence/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy import ndimage  # noqa: E402
from shapely.geometry import Polygon as SPoly  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

from cozmo.contracts.models import Plan  # noqa: E402
from cozmo.eval.registration import _wall_line, register_plans, transform_xy  # noqa: E402
from cozmo.io.manifest import load_config  # noqa: E402
from cozmo.io.stray import StrayScan  # noqa: E402
from cozmo.lidar.cloud import build_cloud  # noqa: E402
from cozmo.lidar.levels import detect_levels  # noqa: E402
from cozmo.lidar.rooms import merge_open_regions, segment_rooms  # noqa: E402
from cozmo.lidar.walls import ManhattanFrame, extract_faces, wall_points  # noqa: E402
from skimage.segmentation import watershed  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "fix_loop" / "evidence"
BEFORE = ROOT / "fix_loop" / "before" / "bench" / "runs"
SCANS = ["c00a170fe1", "1a8384c3f6", "c7d28f72c6"]
APARTMENT = ("1a8384c3f6", "c7d28f72c6")
CFG = load_config(ROOT / "config" / "gates.yaml")["pipeline"]["lidar"]


def build(scan_id: str):
    scan = StrayScan(ROOT / "data" / "sample" / scan_id, "lidar")
    cloud = build_cloud(scan, stride=CFG["frame_stride"], voxel_m=CFG["voxel_m"],
                        min_depth=CFG["min_depth_m"], max_depth=CFG["max_depth_m"])
    levels = detect_levels(cloud, CFG)
    sel = wall_points(cloud, levels, CFG)
    frame = ManhattanFrame.fit(cloud.normals[sel], cloud.points[sel][:, [0, 2]])
    h = cloud.points[sel][:, 1] - levels.floor.height_at(cloud.points[sel][:, [0, 2]])
    faces = extract_faces(frame.to_frame(cloud.points[sel][:, [0, 2]]),
                          frame.rotate_normals(cloud.normals[sel]), h, CFG)
    return cloud, levels, frame, faces, sel, h


def face_segments_world(faces, frame, structural_only=True):
    """Wall faces as world-frame segments with their direction."""
    segs = []
    for f in faces:
        if structural_only and not f.is_structural(CFG["wall"]["wall_min_top_m"]):
            continue
        for a, b in f.segments:
            p0 = (f.pos, a) if f.axis == 0 else (a, f.pos)
            p1 = (f.pos, b) if f.axis == 0 else (b, f.pos)
            w = frame.to_world(np.array([p0, p1]))
            segs.append((w[0], w[1], f))
    return segs


# ---------------------------------------------------------------- evidence a

def evidence_a(built, out: dict) -> None:
    """Share of wall-face length in one apartment scan with a counterpart in the other."""
    a_id, b_id = APARTMENT
    pa = Plan.from_json_bytes((BEFORE / a_id / "plan.json").read_bytes())
    pb = Plan.from_json_bytes((BEFORE / b_id / "plan.json").read_bytes())
    reg = register_plans(pa, pb)

    segs_a = face_segments_world(built[a_id][3], built[a_id][2])
    segs_b_raw = face_segments_world(built[b_id][3], built[b_id][2])
    segs_b = [(transform_xy(np.array([s]), reg)[0], transform_xy(np.array([e]), reg)[0], f)
              for s, e, f in segs_b_raw]

    def coverage(src, dst, tol_m=0.05, tol_deg=2.0):
        total = matched = 0.0
        rows = []
        for s, e, _ in src:
            L = float(np.linalg.norm(e - s))
            if L < 0.2:
                continue
            total += L
            u = (e - s) / L
            n = np.array([-u[1], u[0]])
            best = None
            for s2, e2, _ in dst:
                L2 = float(np.linalg.norm(e2 - s2))
                if L2 < 0.2:
                    continue
                u2 = (e2 - s2) / L2
                ang = float(np.degrees(np.arccos(np.clip(abs(float(u @ u2)), -1, 1))))
                if ang > tol_deg:
                    continue
                off = abs(float((s2 - s) @ n))
                if off > tol_m:
                    continue
                t = sorted([float((s2 - s) @ u), float((e2 - s) @ u)])
                ov = min(L, t[1]) - max(0.0, t[0])
                if ov <= 0:
                    continue
                if best is None or off < best[0]:
                    best = (off, ang, ov)
            if best is not None:
                matched += L
                rows.append({"length_m": L, "offset_m": best[0], "angle_deg": best[1], "overlap_m": best[2]})
        return total, matched, rows

    tot_ab, mat_ab, rows_ab = coverage(segs_a, segs_b)
    tot_ba, mat_ba, rows_ba = coverage(segs_b, segs_a)
    out["a_wall_face_repeatability"] = {
        "tolerance_m": 0.05, "tolerance_deg": 2.0,
        "registration": {"rotation_deg": reg.rotation_deg, "footprint_iou": reg.iou},
        f"{a_id}_total_face_length_m": tot_ab,
        f"{a_id}_matched_length_m": mat_ab,
        f"{a_id}_matched_share": mat_ab / tot_ab if tot_ab else None,
        f"{b_id}_total_face_length_m": tot_ba,
        f"{b_id}_matched_length_m": mat_ba,
        f"{b_id}_matched_share": mat_ba / tot_ba if tot_ba else None,
        "median_offset_m_matched": float(np.median([r["offset_m"] for r in rows_ab])) if rows_ab else None,
    }

    # The gate compares polygon edge lengths. Contrast that with how well the
    # underlying faces agree, which is what tells geometry apart from partition.
    from cozmo.eval.self_consistency import cross_plan_repeat_pairs

    rows, summary = cross_plan_repeat_pairs(pa, pb, "sample_apartment", "lidar")
    matched_rows = [r for r in rows if r["matched"]]
    dls = [abs(r["a"] - r["b"]) for r in matched_rows]
    out["a2_edge_length_vs_face_offset"] = {
        "gate_rows_total": len(rows),
        "gate_rows_matched": len(matched_rows),
        "median_abs_edge_length_difference_m": float(np.median(dls)) if dls else None,
        "median_face_offset_m_matched": out["a_wall_face_repeatability"]["median_offset_m_matched"],
        "note": "Faces that both captures saw sit within a couple of centimetres of each "
                "other, but the polygon edges built from them differ by most of a metre, "
                "because the two captures cut the same wall into different edges.",
    }

    fig, ax = plt.subplots(figsize=(9, 9))
    for s, e, _ in segs_a:
        ax.plot([s[0], e[0]], [s[1], e[1]], color="tab:blue", lw=2.0, alpha=0.8)
    for s, e, _ in segs_b:
        ax.plot([s[0], e[0]], [s[1], e[1]], color="tab:red", lw=1.2, alpha=0.8)
    ax.set_aspect("equal")
    ax.set_title(f"wall faces after registration: {a_id} (blue) and {b_id} (red)\n"
                 f"length-weighted match within 5 cm and 2 deg: "
                 f"{mat_ab / tot_ab:.0%} / {mat_ba / tot_ba:.0%}")
    fig.savefig(OUT / "a_wall_faces_overlay.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- evidence b

def evidence_b(built, out: dict) -> None:
    """Room count and total area against the erosion radius."""
    radii = [0.3, 0.4, 0.5, 0.6, 0.7]
    table = {}
    for sid in SCANS:
        cloud, levels, frame, faces, _, _ = built[sid]
        row = []
        for r in radii:
            cfg = json.loads(json.dumps(CFG))
            cfg["room"]["erode_m"] = r
            res = segment_rooms(cloud, levels, frame, faces, cfg)
            row.append({"erode_m": r, "n_rooms": len(res.rooms),
                        "total_area_m2": float(sum(x.area_m2 for x in res.rooms)),
                        "n_connectors": sum(1 for x in res.rooms if x.kind == "connector")})
        table[sid] = row
    out["b_erosion_sensitivity"] = table

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for sid in SCANS:
        axes[0].plot(radii, [r["n_rooms"] for r in table[sid]], marker="o", label=sid)
        axes[1].plot(radii, [r["total_area_m2"] for r in table[sid]], marker="o", label=sid)
    axes[0].set_xlabel("erosion radius (m)"); axes[0].set_ylabel("rooms found"); axes[0].legend(fontsize=8)
    axes[0].set_title("room count against erosion radius")
    axes[1].set_xlabel("erosion radius (m)"); axes[1].set_ylabel("total room area (m2)"); axes[1].legend(fontsize=8)
    axes[1].set_title("total room area against erosion radius")
    fig.savefig(OUT / "b_erosion_sensitivity.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- evidence c

def evidence_c(built, out: dict) -> None:
    """Free-space fragmentation before erosion, and how much of the envelope is observed."""
    table = {}
    for sid in SCANS:
        cloud, levels, frame, faces, _, _ = built[sid]
        res = segment_rooms(cloud, levels, frame, faces, CFG)
        cell = res.grid.cell
        lab_raw, n_raw = ndimage.label(res.free)
        sizes = np.bincount(lab_raw.ravel())[1:] * cell * cell
        dist = ndimage.distance_transform_edt(res.free) * cell
        seeds, n_seeds = ndimage.label(dist > CFG["room"]["erode_m"])
        polys = [SPoly(r.polygon_frame) for r in res.rooms if len(r.polygon_frame) >= 4]
        envelope = unary_union([p.buffer(0.25, join_style=2) for p in polys]).buffer(-0.25, join_style=2) \
            if polys else None
        env_area = float(envelope.area) if envelope is not None and not envelope.is_empty else 0.0
        free_area = float(res.free.sum()) * cell * cell
        table[sid] = {
            "free_components_before_erosion": int(n_raw),
            "largest_free_component_m2": float(sizes.max()) if len(sizes) else 0.0,
            "free_components_over_1m2": int((sizes > 1.0).sum()),
            "seeds_after_erosion": int(n_seeds),
            "rooms_after_merge": len(res.rooms),
            "free_area_m2": free_area,
            "envelope_area_m2": env_area,
            "free_share_of_envelope": free_area / env_area if env_area else None,
        }
    out["c_fragmentation"] = table


# ---------------------------------------------------------------- evidence d

def evidence_d(built, out: dict) -> None:
    """Wall-face length lying outside the envelope of the main structure."""
    table = {}
    for sid in SCANS:
        cloud, levels, frame, faces, _, _ = built[sid]
        res = segment_rooms(cloud, levels, frame, faces, CFG)
        polys = [SPoly(r.polygon_frame) for r in res.rooms if len(r.polygon_frame) >= 4]
        if not polys:
            continue
        env = unary_union([p.buffer(0.35, join_style=2) for p in polys])
        inside_len = outside_len = 0.0
        outside_segs = []
        for f in faces:
            if not f.is_structural(CFG["wall"]["wall_min_top_m"]):
                continue
            for a, b in f.segments:
                p0 = (f.pos, a) if f.axis == 0 else (a, f.pos)
                p1 = (f.pos, b) if f.axis == 0 else (b, f.pos)
                mid = np.array([(p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2])
                L = float(np.hypot(p1[0] - p0[0], p1[1] - p0[1]))
                from shapely.geometry import Point
                if env.contains(Point(mid)):
                    inside_len += L
                else:
                    outside_len += L
                    outside_segs.append((p0, p1))
        table[sid] = {"inside_envelope_m": inside_len, "outside_envelope_m": outside_len,
                      "outside_share": outside_len / (inside_len + outside_len) if (inside_len + outside_len) else None,
                      "n_outside_segments": len(outside_segs)}
        if sid == APARTMENT[1]:
            fig, ax = plt.subplots(figsize=(9, 9))
            for p in polys:
                x, y = p.exterior.xy
                ax.fill(y, x, alpha=0.25, color="0.6")
            for f in faces:
                if not f.is_structural(CFG["wall"]["wall_min_top_m"]):
                    continue
                for a, b in f.segments:
                    p0 = (f.pos, a) if f.axis == 0 else (a, f.pos)
                    p1 = (f.pos, b) if f.axis == 0 else (b, f.pos)
                    ax.plot([p0[1], p1[1]], [p0[0], p1[0]], color="black", lw=1.5)
            for p0, p1 in outside_segs:
                ax.plot([p0[1], p1[1]], [p0[0], p1[0]], color="red", lw=2.5)
            ax.set_aspect("equal")
            ax.set_title(f"{sid}: wall faces, red lies outside the room envelope\n"
                         f"{outside_len:.1f} m outside of {inside_len + outside_len:.1f} m total")
            fig.savefig(OUT / "d_ghost_faces.png", dpi=110, bbox_inches="tight")
            plt.close(fig)
    out["d_ghost_faces"] = table


# ---------------------------------------------------------------- evidence e

def evidence_e(built, out: dict) -> None:
    """Height distribution of wall points, to find a band that is actually covered."""
    bands = [(0.3, 1.0), (1.0, 1.6), (1.0, 2.2), (1.6, 2.2), (2.2, 3.0)]
    table = {}
    fig, ax = plt.subplots(figsize=(10, 5))
    for sid in SCANS:
        cloud, levels, frame, faces, sel, h = built[sid]
        hist, edges = np.histogram(h, bins=np.arange(0, 3.2, 0.05))
        ax.plot((edges[:-1] + edges[1:]) / 2, hist / hist.sum(), label=sid)
        total = len(h)
        table[sid] = {
            "n_wall_points": int(total),
            "median_height_m": float(np.median(h)),
            "p90_height_m": float(np.percentile(h, 90)),
            "share_by_band": {f"{lo}-{hi}": float(((h >= lo) & (h < hi)).mean()) for lo, hi in bands},
            "ceiling_observed": levels.height.method != "prior_no_ceiling_observed",
        }
    ax.set_xlabel("height above floor (m)")
    ax.set_ylabel("share of wall points")
    ax.set_title("wall-point height distribution per scan")
    ax.legend(fontsize=8)
    for lo, hi in [(1.0, 2.2)]:
        ax.axvspan(lo, hi, color="tab:green", alpha=0.12)
    fig.savefig(OUT / "e_height_coverage.png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    out["e_height_coverage"] = table


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    built = {}
    for sid in SCANS:
        print("building", sid, flush=True)
        built[sid] = build(sid)
    out: dict = {}
    for fn in (evidence_a, evidence_b, evidence_c, evidence_d, evidence_e):
        print("running", fn.__name__, flush=True)
        fn(built, out)
    (OUT / "evidence.json").write_text(json.dumps(out, indent=2, default=float) + "\n")
    print(json.dumps(out, indent=2, default=float))


if __name__ == "__main__":
    sys.exit(main())
