from __future__ import annotations

import numpy as np


def _value_noise(shape: tuple[int, int], rng: np.random.Generator, cell: int) -> np.ndarray:
    gh = shape[0] // cell + 3
    gw = shape[1] // cell + 3
    grid = rng.random((gh, gw))
    ys = np.linspace(0, gh - 2, shape[0])
    xs = np.linspace(0, gw - 2, shape[1])
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    fy = (ys - y0)[:, None]
    fx = (xs - x0)[None, :]
    y1 = y0 + 1
    x1 = x0 + 1
    n00 = grid[y0[:, None], x0[None, :]]
    n10 = grid[y0[:, None], x1[None, :]]
    n01 = grid[y1[:, None], x0[None, :]]
    n11 = grid[y1[:, None], x1[None, :]]
    return n00 * (1 - fy) * (1 - fx) + n10 * (1 - fy) * fx + n01 * fy * (1 - fx) + n11 * fy * fx


def _grid_surface(origin, u, v, nu, nv, colors, conf=0.93) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    xs, ys = np.meshgrid(np.linspace(0, 1, nu), np.linspace(0, 1, nv), indexing="ij")
    pts = origin + xs.reshape(-1, 1) * u + ys.reshape(-1, 1) * v
    if colors.ndim == 1:
        rgb = np.tile(colors.astype(np.uint8), (len(pts), 1))
    else:
        rgb = colors.reshape(-1, 3).astype(np.uint8)
    faces = []
    for i in range(nu - 1):
        for j in range(nv - 1):
            a = i * nv + j
            b = (i + 1) * nv + j
            c = (i + 1) * nv + (j + 1)
            d = i * nv + (j + 1)
            faces.append((a, b, c))
            faces.append((a, c, d))
    return pts, rgb, np.full(len(pts), conf, dtype=np.float32), np.asarray(faces, dtype=np.int32)


def _append(store, xyz, rgb, conf, faces, offset: int) -> int:
    store["xyz"].append(xyz)
    store["rgb"].append(rgb)
    store["conf"].append(conf)
    if len(faces):
        store["faces"].append(faces + offset)
    return offset + len(xyz)


def _cone(cx, cy, z0, radius, height, n, color, rng) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ring = np.column_stack(
        [cx + radius * np.cos(angles), cy + radius * np.sin(angles), np.full(n, z0)]
    )
    apex = np.array([[cx, cy, z0 + height]])
    xyz = np.vstack([apex, ring])
    rgb = np.clip(
        np.tile(np.asarray(color, dtype=np.int16), (len(xyz), 1)) + rng.integers(-10, 11, (len(xyz), 3)),
        0,
        255,
    ).astype(np.uint8)
    faces = [(0, i, 1 + (i % n)) for i in range(1, n + 1)]
    for i in range(2, n):
        faces.append((1, i, i + 1))
    return xyz, rgb, np.full(len(xyz), 0.7, dtype=np.float32), np.asarray(faces, dtype=np.int32)


def _wall_with_windows(origin, u, v, nu, nv, base, window, conf=0.84):
    xs, ys = np.meshgrid(np.linspace(0, 1, nu), np.linspace(0, 1, nv), indexing="ij")
    pts = origin + xs.reshape(-1, 1) * u + ys.reshape(-1, 1) * v
    rgb = np.tile(np.asarray(base, dtype=np.uint8), (len(pts), 1))
    for i in range(nu):
        for j in range(nv):
            # window bays: skip edges, every other cell
            if 2 <= j < nv - 2 and 2 <= i < nu - 1 and (i % 3 == 1) and (j % 2 == 0):
                rgb[i * nv + j] = window
    faces = []
    for i in range(nu - 1):
        for j in range(nv - 1):
            a = i * nv + j
            b = (i + 1) * nv + j
            c = (i + 1) * nv + (j + 1)
            d = i * nv + (j + 1)
            faces.append((a, b, c))
            faces.append((a, c, d))
    return pts, rgb, np.full(len(pts), conf, dtype=np.float32), np.asarray(faces, dtype=np.int32)


def build_sample_site() -> dict:
    """Detailed single-corridor site: terrain, road, several buildings, trees, court."""
    rng = np.random.default_rng(21)
    store = {"xyz": [], "rgb": [], "conf": [], "faces": []}
    offset = 0

    def add(xyz, rgb, conf, faces):
        nonlocal offset
        offset = _append(store, xyz, rgb, conf, faces, offset)

    nx, ny = 180, 128
    n1 = _value_noise((nx, ny), rng, 18)
    n2 = _value_noise((nx, ny), rng, 7)
    height = n1 * 2.4 + n2 * 0.55
    # flatten a road corridor through the middle
    road_mask = np.zeros((nx, ny), dtype=bool)
    j0, j1 = int(ny * 0.44), int(ny * 0.56)
    road_mask[:, j0:j1] = True
    height[road_mask] = 0.12
    # parking pad
    pad = np.zeros((nx, ny), dtype=bool)
    pad[int(nx * 0.62) : int(nx * 0.88), int(ny * 0.18) : int(ny * 0.40)] = True
    height[pad] = 0.14

    grass_a = np.array([72, 118, 64])
    grass_b = np.array([98, 138, 70])
    dirt = np.array([118, 96, 62])
    asphalt = np.array([54, 54, 58])
    paint = np.array([210, 210, 204])
    colors = np.zeros((nx, ny, 3), dtype=np.uint8)
    mix = n1[..., None]
    colors[...] = (grass_a * (1 - mix) + grass_b * mix).astype(np.uint8)
    dry = n2 > 0.72
    colors[dry] = dirt
    colors[road_mask] = asphalt
    colors[pad] = np.array([62, 64, 70], dtype=np.uint8)
    # lane dashes on the road
    for i in range(8, nx - 8, 10):
        colors[i : i + 5, (j0 + j1) // 2] = paint
    # parking stalls
    for j in range(int(ny * 0.18), int(ny * 0.40), 4):
        colors[int(nx * 0.62) : int(nx * 0.88), j] = paint

    origin = np.array([-48.0, -32.0, 0.0])
    u = np.array([96.0, 0.0, 0.0])
    v = np.array([0.0, 64.0, 0.0])
    xs, ys = np.meshgrid(np.linspace(0, 1, nx), np.linspace(0, 1, ny), indexing="ij")
    terrain = origin + xs.reshape(-1, 1) * u + ys.reshape(-1, 1) * v
    terrain[:, 2] = height.reshape(-1)
    faces = []
    for i in range(nx - 1):
        for j in range(ny - 1):
            a = i * ny + j
            b = (i + 1) * ny + j
            c = (i + 1) * ny + (j + 1)
            d = i * ny + (j + 1)
            faces.append((a, b, c))
            faces.append((a, c, d))
    add(terrain, colors.reshape(-1, 3), np.full(len(terrain), 0.94, dtype=np.float32), np.asarray(faces, dtype=np.int32))

    buildings = [
        # x, y, w, d, h, roof, wall
        (-18.0, 10.0, 18.0, 12.0, 10.5, (196, 92, 72), (186, 168, 148)),
        (8.0, 12.0, 14.0, 10.0, 7.2, (210, 210, 214), (168, 176, 186)),
        (16.0, -18.0, 16.0, 11.0, 8.8, (92, 104, 118), (150, 156, 164)),
        (-22.0, -16.0, 12.0, 9.0, 5.5, (176, 132, 92), (170, 150, 128)),
    ]
    for x, y, w, d, h, roof, wall in buildings:
        roof_c = np.array(roof, dtype=np.uint8)
        wall_c = np.array(wall, dtype=np.uint8)
        window = np.clip(wall_c.astype(int) - 55, 20, 255).astype(np.uint8)
        # roof
        add(*_grid_surface(np.array([x, y, h]), np.array([w, 0, 0]), np.array([0, d, 0]), 28, 20, roof_c, 0.96))
        # south facade (visible in a northbound corridor looking slightly down)
        add(*_wall_with_windows(np.array([x, y, 0.15]), np.array([w, 0, 0]), np.array([0, 0, h - 0.15]), 26, 16, wall_c, window, 0.86))
        # west facade
        add(*_wall_with_windows(np.array([x, y, 0.15]), np.array([0, d, 0]), np.array([0, 0, h - 0.15]), 18, 16, wall_c, window, 0.78))

    # sports court
    add(
        *_grid_surface(
            np.array([-8.0, -6.0, 0.22]),
            np.array([14.0, 0, 0]),
            np.array([0, 8.0, 0]),
            22,
            14,
            np.array([46, 92, 168], dtype=np.uint8),
            0.95,
        )
    )

    tree_spots = [
        (-38, 22, 3.4, 1.6),
        (-36, -22, 3.1, 1.5),
        (36, 24, 3.6, 1.7),
        (38, -20, 3.2, 1.5),
        (34, 8, 2.8, 1.3),
        (-40, 4, 3.0, 1.4),
        (22, 26, 2.6, 1.2),
        (-6, 26, 3.3, 1.5),
    ]
    for cx, cy, h, r in tree_spots:
        add(*_cone(cx, cy, 0.2, r * 0.28, h * 0.35, 10, (92, 68, 42), rng))
        add(*_cone(cx, cy, 1.1, r, h, 12, (36, 102, 48), rng))

    mesh_xyz = np.concatenate(store["xyz"], axis=0)
    mesh_rgb = np.concatenate(store["rgb"], axis=0)
    mesh_conf = np.concatenate(store["conf"], axis=0)
    faces = np.concatenate(store["faces"], axis=0)

    return {
        "xyz": mesh_xyz,
        "rgb": mesh_rgb,
        "conf": mesh_conf,
        "mesh_xyz": mesh_xyz,
        "mesh_rgb": mesh_rgb,
        "mesh_conf": mesh_conf,
        "faces": faces,
        "meta": {
            "metric": True,
            "origin": {"lat": 28.6139, "lon": 77.2090, "alt": 216.0},
            "note": "Simulated single-corridor drone pass over a small campus. Click the mesh to fly there. Far walls are open on purpose.",
            "demo": True,
            "drone_pass": True,
        },
    }


def render_drone_frames(scene: dict, count: int = 12) -> list:
    """Orthophoto-style crops along one corridor — stands in for a single-take drone video."""
    import cv2

    xyz, rgb = scene["mesh_xyz"], scene["mesh_rgb"]
    mins = xyz[:, :2].min(axis=0)
    span = np.maximum(xyz[:, :2].max(axis=0) - mins, 1e-6)
    w, h = 720, 420
    canvas = np.zeros((h, w, 3), dtype=np.uint8)
    canvas[:] = (118, 168, 214)  # BGR sky-ish edge
    px = ((xyz[:, 0] - mins[0]) / span[0] * (w - 1)).astype(int)
    py = ((1.0 - (xyz[:, 1] - mins[1]) / span[1]) * (h - 1)).astype(int)
    order = np.argsort(xyz[:, 2])
    for i in order:
        canvas[py[i], px[i]] = (int(rgb[i, 2]), int(rgb[i, 1]), int(rgb[i, 0]))
    canvas = cv2.medianBlur(canvas, 3)
    frames = []
    for k in range(count):
        t = k / max(count - 1, 1)
        x0 = int(40 + t * 180)
        y0 = int(60 + np.sin(t * np.pi) * 20)
        crop = canvas[y0 : y0 + 280, x0 : x0 + 400]
        if crop.size == 0:
            crop = canvas[:280, :400]
        frame = cv2.resize(crop, (640, 360), interpolation=cv2.INTER_LINEAR)
        cv2.putText(frame, "ONE-PASS UAV", (16, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (240, 240, 240), 1, cv2.LINE_AA)
        frames.append(frame)
    return frames
