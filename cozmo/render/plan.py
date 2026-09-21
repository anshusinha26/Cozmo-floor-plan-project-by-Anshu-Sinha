"""Draw a stitched plan to PNG. Plain and readable on purpose.

The stitched plan is the product surface: a reader who never opens the JSON
still has to be able to see which room is which, how long each wall is, and
where the doors are. Three rules follow from that.

**One frame.** Fills, walls, openings and labels are all drawn from the same
placed coordinates. Drawing the fill from the polygon and the walls from an
untransformed copy is how three rooms once ended up stacked on each other
while every number in the file was right.

**Upright.** The drawing is rotated into the plan's own Manhattan frame, so
walls run along the page rather than at whatever angle the capture started
at. This changes the picture only; `plan.json` is untouched.

**Say what is uncertain.** A side the pipeline never observed is dashed, and a
plan carrying a warning that its numbers are unreliable says so in the title.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from cozmo.contracts.models import Plan  # noqa: E402
from cozmo.eval.gates import place_polygon  # noqa: E402

MIN_LABELLED_WALL_M = 0.6
# Two wall labels closer than this on the page are unreadable together.
LABEL_CLEARANCE_M = 0.42
UNRELIABLE_MARKERS = ("STUB PIPELINE", "unreliable", "not a real reconstruction")
OPENING_STYLE = {
    "door": ("#1f77b4", "-", 3.0),
    "pass_through": ("#7f7f7f", ":", 2.5),
    "window": ("#2ca02c", "--", 2.5),
}


def drawing_yaw(plan: Plan) -> float:
    """Angle to rotate the drawing by so walls run along the page.

    Length-weighted circular mean of wall directions taken modulo 90 degrees,
    the same trick the Manhattan frame uses: quadruple the angles so the two
    orientations of a rectangular room reinforce instead of cancelling.
    """
    angles, weights = [], []
    for room in plan.rooms:
        placement = _placement(plan, room.id)
        for wall in room.walls:
            (x0, y0), (x1, y1) = place_polygon([wall.start, wall.end], placement)
            length = math.hypot(x1 - x0, y1 - y0)
            if length < 1e-6:
                continue
            angles.append(math.atan2(y1 - y0, x1 - x0))
            weights.append(length)
    if not angles:
        return 0.0
    a = np.asarray(angles)
    w = np.asarray(weights)
    mean = math.atan2(float(np.sum(w * np.sin(4 * a))), float(np.sum(w * np.cos(4 * a)))) / 4.0
    return -mean


def _placement(plan: Plan, room_id: str):
    return next(p for p in plan.stitched_plan.placements if p.room_id == room_id)


def _rot(yaw: float) -> np.ndarray:
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, -s], [s, c]])


def _to_page(points, placement, R: np.ndarray) -> np.ndarray:
    """Room coordinates to page coordinates: placement first, then the page rotation."""
    placed = np.asarray(place_polygon(list(points), placement), dtype=float)
    return placed @ R.T


def _is_unreliable(plan: Plan) -> bool:
    text = " ".join(plan.warnings).lower()
    return any(m.lower() in text for m in UNRELIABLE_MARKERS)


def _partially_observed(room) -> bool:
    return any("partially_observed" in w.length_m.method for w in room.walls)


def _wall_label(wall) -> str:
    half = wall.length_m.width / 2
    return f"{wall.length_m.value:.2f} ±{half:.2f}"


def render_plan_png(plan: Plan, out_path: Path, dpi: int = 150) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    R = _rot(drawing_yaw(plan))

    rooms = []
    for room in plan.rooms:
        placement = _placement(plan, room.id)
        rooms.append({
            "room": room,
            "poly": _to_page(room.polygon, placement, R),
            "walls": [(w, _to_page([w.start, w.end], placement, R)) for w in room.walls],
            "placement": placement,
            "partial": _partially_observed(room),
        })

    all_pts = np.vstack([r["poly"] for r in rooms])
    span = max(float(np.ptp(all_pts[:, 0])), float(np.ptp(all_pts[:, 1])), 1.0)
    fig_side = float(np.clip(span * 1.1, 7.0, 14.0))
    fig, ax = plt.subplots(figsize=(fig_side, fig_side))

    for entry in rooms:
        room, poly = entry["room"], entry["poly"]
        ax.fill(poly[:, 0], poly[:, 1], color="#f2f2f2", zorder=1)
        for wall, seg in entry["walls"]:
            (x0, y0), (x1, y1) = seg
            dashed = entry["partial"]
            ax.plot([x0, x1], [y0, y1], color="black", linewidth=2.4, zorder=3,
                    solid_capstyle="butt", linestyle=(0, (6, 4)) if dashed else "-")

        # Openings sit on their wall, drawn as a gap with a coloured marker.
        walls_by_id = {w.id: (w, seg) for w, seg in entry["walls"]}
        for opening in room.openings:
            found = walls_by_id.get(opening.wall_id)
            if found is None:
                continue
            _, ((x0, y0), (x1, y1)) = found
            length = math.hypot(x1 - x0, y1 - y0)
            if length < 1e-6:
                continue
            ux, uy = (x1 - x0) / length, (y1 - y0) / length
            a = min(max(opening.offset_along_wall_m.value, 0.0), length)
            b = min(a + opening.width_m.value, length)
            colour, style, width = OPENING_STYLE.get(opening.type, OPENING_STYLE["pass_through"])
            ax.plot([x0 + ux * a, x0 + ux * b], [y0 + uy * a, y0 + uy * b],
                    color="white", linewidth=5.0, zorder=4, solid_capstyle="butt")
            ax.plot([x0 + ux * a, x0 + ux * b], [y0 + uy * a, y0 + uy * b],
                    color=colour, linestyle=style, linewidth=width, zorder=5,
                    solid_capstyle="butt")

    # Wall labels last, so they sit over the fills and under nothing. They are
    # gathered first and placed longest wall first: where a cluster of short
    # connector walls would stack their labels on top of each other, the
    # longest wall keeps its number and the rest go unlabelled. An unreadable
    # pile of overlapping figures tells a reader less than one clear figure.
    candidates = []
    for entry in rooms:
        centre = entry["poly"].mean(axis=0)
        room_span = max(float(np.ptp(entry["poly"][:, 0])), float(np.ptp(entry["poly"][:, 1])), 0.5)
        font = float(np.clip(room_span * 1.6, 5.0, 8.0))
        for wall, seg in entry["walls"]:
            if wall.length_m.value < MIN_LABELLED_WALL_M:
                continue
            (x0, y0), (x1, y1) = seg
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            length = math.hypot(x1 - x0, y1 - y0)
            if length < 1e-6:
                continue
            # Push the label to the outside of the wall, away from the room.
            nx, ny = -(y1 - y0) / length, (x1 - x0) / length
            if (mx + nx * 0.01 - centre[0]) ** 2 + (my + ny * 0.01 - centre[1]) ** 2 < \
               (mx - nx * 0.01 - centre[0]) ** 2 + (my - ny * 0.01 - centre[1]) ** 2:
                nx, ny = -nx, -ny
            offset = 0.12 + font * 0.012
            angle = math.degrees(math.atan2(y1 - y0, x1 - x0))
            if angle > 90 or angle < -90:
                angle += 180
            candidates.append((length, (mx + nx * offset, my + ny * offset),
                               _wall_label(wall), font, angle))

    placed: list[tuple[float, float]] = []
    for _, (lx, ly), text, font, angle in sorted(candidates, key=lambda c: -c[0]):
        if any(math.hypot(lx - px, ly - py) < LABEL_CLEARANCE_M for px, py in placed):
            continue
        placed.append((lx, ly))
        ax.text(lx, ly, text, fontsize=font * 0.82, ha="center", va="center", rotation=angle,
                rotation_mode="anchor", zorder=6, color="#333333")

    for entry in rooms:
        centre = entry["poly"].mean(axis=0)
        room_span = max(float(np.ptp(entry["poly"][:, 0])), float(np.ptp(entry["poly"][:, 1])), 0.5)
        font = float(np.clip(room_span * 1.6, 5.0, 8.0))
        room = entry["room"]
        height = room.ceiling_height_m
        prior = height.method.startswith("prior")
        lines = [room.label or room.id,
                 f"{room.floor_area_m2.value:.1f} m² ±{room.floor_area_m2.width / 2:.1f}",
                 f"h {height.value:.2f} m" + (" (prior)" if prior else "")]
        if entry["partial"]:
            lines.append("partially observed")
        ax.text(centre[0], centre[1], "\n".join(lines), ha="center", va="center",
                fontsize=font, zorder=7,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#cccccc", alpha=0.85))

    lo = all_pts.min(axis=0)
    hi = all_pts.max(axis=0)
    pad = max(0.6, span * 0.06)
    ax.set_xlim(lo[0] - pad, hi[0] + pad)
    ax.set_ylim(lo[1] - pad - 0.7, hi[1] + pad)
    ax.set_aspect("equal")
    ax.axis("off")

    ax.plot([lo[0], lo[0] + 1.0], [lo[1] - pad + 0.25] * 2, color="black", linewidth=3)
    ax.text(lo[0] + 0.5, lo[1] - pad + 0.3, "1 m", ha="center", va="bottom", fontsize=8)

    legend = [
        plt.Line2D([], [], color=OPENING_STYLE["door"][0], linestyle=OPENING_STYLE["door"][1],
                   linewidth=OPENING_STYLE["door"][2], label="door"),
        plt.Line2D([], [], color=OPENING_STYLE["pass_through"][0],
                   linestyle=OPENING_STYLE["pass_through"][1],
                   linewidth=OPENING_STYLE["pass_through"][2], label="pass-through"),
        plt.Line2D([], [], color=OPENING_STYLE["window"][0], linestyle=OPENING_STYLE["window"][1],
                   linewidth=OPENING_STYLE["window"][2], label="window"),
        plt.Line2D([], [], color="black", linestyle=(0, (6, 4)), linewidth=2.4,
                   label="partially observed"),
    ]
    ax.legend(handles=legend, loc="lower right", fontsize=7, framealpha=0.9)

    title = f"{plan.capture.id}  |  {plan.capture.tier}  |  {plan.run.pipeline_version}"
    if _is_unreliable(plan):
        title += "  |  UNRELIABLE"
        ax.set_title(title, fontsize=11, color="red", fontweight="bold")
        stub = next((w for w in plan.warnings if "STUB" in w.upper()), None)
        if stub:
            fig.text(0.5, 0.02, stub, ha="center", color="red", fontsize=11, fontweight="bold")
    else:
        ax.set_title(title, fontsize=10)

    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out_path
