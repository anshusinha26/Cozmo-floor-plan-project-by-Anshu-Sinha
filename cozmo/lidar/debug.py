"""Debug images for one LiDAR run: density, wall faces, room masks, openings."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return path


def write_debug_images(out_dir: Path, cloud, levels, frame, faces, rooms, openings, cfg) -> list[str]:
    out_dir = Path(out_dir)
    written: list[str] = []
    xz = frame.to_frame(cloud.points[:, [0, 2]])
    cell = rooms.grid.cell
    extent = [rooms.grid.origin[1], rooms.grid.origin[1] + rooms.grid.shape[1] * cell,
              rooms.grid.origin[0], rooms.grid.origin[0] + rooms.grid.shape[0] * cell]

    fig, ax = plt.subplots(figsize=(8, 8))
    h, xe, ye = np.histogram2d(xz[:, 0], xz[:, 1], bins=[240, 240])
    ax.imshow(np.log1p(h), origin="lower", extent=[ye[0], ye[-1], xe[0], xe[-1]], cmap="magma")
    if len(cloud.camera_path):
        p = frame.to_frame(cloud.camera_path[:, [0, 2]])
        ax.plot(p[:, 1], p[:, 0], color="cyan", lw=0.8, label="camera path")
        ax.legend(loc="upper right", fontsize=7)
    ax.set_title("point density (log) in the Manhattan frame")
    written.append(str(_save(fig, out_dir / "density.png").name))

    fig, ax = plt.subplots(figsize=(8, 8))
    for f in faces:
        structural = f.is_structural(cfg["wall"]["wall_min_top_m"])
        for a, b in f.segments:
            xs, ys = ([f.pos, f.pos], [a, b]) if f.axis == 0 else ([a, b], [f.pos, f.pos])
            ax.plot(ys, xs, color="black" if structural else "orange",
                    lw=2.0 if structural else 1.0, alpha=0.9)
    ax.set_aspect("equal")
    ax.set_title("wall faces (black structural, orange furniture height)")
    written.append(str(_save(fig, out_dir / "wall_faces.png").name))

    fig, ax = plt.subplots(figsize=(8, 8))
    img = np.zeros(rooms.grid.shape)
    for i, r in enumerate(rooms.rooms, start=1):
        img[r.mask] = i
    ax.imshow(np.ma.masked_equal(img, 0), origin="lower", extent=extent, cmap="tab20", interpolation="nearest")
    for r in rooms.rooms:
        poly = np.array(r.polygon_frame + r.polygon_frame[:1])
        ax.plot(poly[:, 1], poly[:, 0], color="black", lw=1.2)
        c = np.array(r.polygon_frame).mean(axis=0)
        ax.text(c[1], c[0], f"{r.id}\n{r.area_m2:.1f} m2", ha="center", va="center", fontsize=7)
    ax.set_title("room masks and polygons")
    written.append(str(_save(fig, out_dir / "room_masks.png").name))

    fig, ax = plt.subplots(figsize=(8, 8))
    for f in faces:
        for a, b in f.segments:
            xs, ys = ([f.pos, f.pos], [a, b]) if f.axis == 0 else ([a, b], [f.pos, f.pos])
            ax.plot(ys, xs, color="0.6", lw=1.2)
    for o in openings:
        xs, ys = ([o.face.pos] * 2, [o.a0, o.a1]) if o.face.axis == 0 else ([o.a0, o.a1], [o.face.pos] * 2)
        ax.plot(ys, xs, color="red" if o.type == "door" else "blue", lw=3.5)
        c0 = (o.a0 + o.a1) / 2
        pt = (o.face.pos, c0) if o.face.axis == 0 else (c0, o.face.pos)
        ax.text(pt[1], pt[0], f"{o.width_m:.2f}", fontsize=6, color="red")
    ax.set_aspect("equal")
    ax.set_title("openings (red door, blue pass-through)")
    written.append(str(_save(fig, out_dir / "openings.png").name))
    return written
