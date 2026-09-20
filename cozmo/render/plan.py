"""Draw a stitched plan to PNG with matplotlib. Plain and readable on purpose.

Shows: placed room polygons, wall length labels with their interval, openings
as gaps in the wall line, room labels, a 1 m scale bar and the capture tier.
If the plan carries a STUB warning it is printed in red on the figure so a
rendered stub can never pass as a result.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from cozmo.contracts.models import Plan  # noqa: E402
from cozmo.eval.gates import place_polygon, placed_rooms  # noqa: E402


def _placed_segment(room, wall, placement):
    s, e = place_polygon([wall.start, wall.end], placement)
    return s, e


def render_plan_png(plan: Plan, out_path: Path, dpi: int = 150) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    placements = {p.room_id: p for p in plan.stitched_plan.placements}
    rooms = placed_rooms(plan)

    fig, ax = plt.subplots(figsize=(9, 8))
    for room in plan.rooms:
        pl = placements[room.id]
        poly = rooms[room.id]
        xs = [p[0] for p in poly] + [poly[0][0]]
        ys = [p[1] for p in poly] + [poly[0][1]]
        ax.fill(xs, ys, color="#f2f2f2", zorder=1)
        walls_by_id = {w.id: w for w in room.walls}
        for w in room.walls:
            (x1, y1), (x2, y2) = _placed_segment(room, w, pl)
            ax.plot([x1, x2], [y1, y2], color="black", linewidth=2.5, zorder=2, solid_capstyle="butt")
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
            if ang > 90 or ang < -90:
                ang += 180
            half = w.length_m.width / 2
            ax.text(mx, my, f"{w.length_m.value:.2f} m (±{half:.2f})", fontsize=7, ha="center", va="bottom",
                    rotation=ang, rotation_mode="anchor", zorder=4,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))
        for o in room.openings:
            w = walls_by_id[o.wall_id]
            (x1, y1), (x2, y2) = _placed_segment(room, w, pl)
            L = math.hypot(x2 - x1, y2 - y1) or 1.0
            ux, uy = (x2 - x1) / L, (y2 - y1) / L
            a = o.offset_along_wall_m.value
            b = a + o.width_m.value
            ax.plot([x1 + ux * a, x1 + ux * b], [y1 + uy * a, y1 + uy * b], color="white", linewidth=4, zorder=3)
            style = {"door": ("#1f77b4", "-"), "window": ("#2ca02c", "--"), "pass_through": ("#7f7f7f", ":")}[o.type]
            ax.plot([x1 + ux * a, x1 + ux * b], [y1 + uy * a, y1 + uy * b], color=style[0], linestyle=style[1], linewidth=1.5, zorder=4)
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        ax.text(cx, cy, f"{room.label}\n{room.floor_area_m2.value:.1f} m² (±{room.floor_area_m2.width / 2:.1f})\nh {room.ceiling_height_m.value:.2f} m",
                ha="center", va="center", fontsize=9, zorder=5)

    all_pts = [p for poly in rooms.values() for p in poly]
    minx, maxx = min(p[0] for p in all_pts), max(p[0] for p in all_pts)
    miny, maxy = min(p[1] for p in all_pts), max(p[1] for p in all_pts)
    pad = 0.6
    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad - 0.5, maxy + pad)
    ax.set_aspect("equal")
    ax.axis("off")

    # Scale bar: 1 m at bottom left.
    ax.plot([minx, minx + 1.0], [miny - pad + 0.1] * 2, color="black", linewidth=3)
    ax.text(minx + 0.5, miny - pad + 0.15, "1 m", ha="center", va="bottom", fontsize=8)

    title = f"{plan.capture.id}  |  tier: {plan.capture.tier}  |  {plan.run.pipeline_version}"
    ax.set_title(title, fontsize=10)
    stub = [w for w in plan.warnings if "STUB" in w.upper()]
    if stub:
        fig.text(0.5, 0.02, stub[0], ha="center", color="red", fontsize=11, fontweight="bold")
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out_path
