from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np


def _pad4(data: bytes, fill: bytes = b"\x00") -> bytes:
    pad = (4 - (len(data) % 4)) % 4
    return data + (fill * pad)


def glb_json_has_null_padding(path: Path) -> bool:
    with Path(path).open("rb") as handle:
        header = handle.read(20)
        if len(header) < 20:
            return False
        chunk_len, chunk_type = struct.unpack_from("<II", header, 12)
        if chunk_type != 0x4E4F534A:
            return False
        return b"\x00" in handle.read(chunk_len)


def fix_glb_json_padding(path: Path) -> bool:
    """Replace illegal NUL padding in the GLB JSON chunk with spaces.

    glTF requires JSON chunks to be padded with 0x20. Trailing 0x00 makes
    browser JSON.parse throw: Unrecognized token ''.
    """
    blob = bytearray(Path(path).read_bytes())
    if len(blob) < 20:
        return False
    chunk_len, chunk_type = struct.unpack_from("<II", blob, 12)
    if chunk_type != 0x4E4F534A or 20 + chunk_len > len(blob):
        return False
    raw = bytes(blob[20 : 20 + chunk_len])
    if b"\x00" not in raw:
        return False
    body = raw.rstrip(b"\x00")
    blob[20 : 20 + chunk_len] = body + (b" " * (chunk_len - len(body)))
    Path(path).write_bytes(blob)
    return True


def _normals(xyz: np.ndarray, faces: np.ndarray) -> np.ndarray:
    normals = np.zeros_like(xyz, dtype=np.float32)
    if len(faces) == 0:
        return normals
    a = xyz[faces[:, 0]]
    b = xyz[faces[:, 1]]
    c = xyz[faces[:, 2]]
    n = np.cross(b - a, c - a)
    for i in range(3):
        np.add.at(normals, faces[:, i], n)
    lens = np.linalg.norm(normals, axis=1, keepdims=True)
    lens[lens < 1e-8] = 1.0
    return (normals / lens).astype(np.float32)


def glb_is_valid(path: Path) -> tuple[bool, str]:
    data = Path(path).read_bytes()
    if len(data) < 20:
        return False, "GLB is too small"
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67:
        return False, f"GLB magic is {data[:4]!r}, not glTF"
    if version != 2:
        return False, f"Unsupported GLB version {version}"
    if length != len(data):
        return False, f"GLB length header {length} != file size {len(data)}"
    chunk_len, chunk_type = struct.unpack_from("<II", data, 12)
    if chunk_type != 0x4E4F534A:
        return False, "First GLB chunk is not JSON"
    raw = data[20 : 20 + chunk_len]
    if b"\x00" in raw:
        return False, "GLB JSON chunk is padded with nulls (browsers cannot JSON.parse that)"
    try:
        parsed = json.loads(raw.decode("utf-8"), parse_constant=lambda name: (_ for _ in ()).throw(ValueError(name)))
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        return False, f"GLB JSON chunk is invalid: {exc}"
    meshes = parsed.get("meshes") or []
    accessors = parsed.get("accessors") or []
    triangles = 0
    has_tri = False
    for mesh in meshes:
        for prim in mesh.get("primitives") or []:
            if int(prim.get("mode", 4)) != 4:
                continue
            idx = prim.get("indices")
            if idx is None or idx >= len(accessors):
                continue
            count = int(accessors[idx].get("count") or 0)
            if count >= 3 and count % 3 == 0:
                has_tri = True
                triangles += count // 3
    if not has_tri or triangles < 1:
        return False, "GLB has no triangle mesh"
    pos = None
    for acc in accessors:
        if acc.get("type") == "VEC3" and acc.get("min") and acc.get("max"):
            pos = acc
            break
    if pos:
        mins = np.asarray(pos["min"], dtype=np.float64)
        maxs = np.asarray(pos["max"], dtype=np.float64)
        if not np.isfinite(mins).all() or not np.isfinite(maxs).all() or float((maxs - mins).max()) <= 1e-6:
            return False, "GLB mesh bounding box is empty"
    return True, "ok"


def embed_glb_external_images(path: Path, search_dirs: list[Path] | None = None) -> bool:
    """Pack external texture URIs into the GLB so the viewer and downloads stay textured."""
    path = Path(path)
    data = bytearray(path.read_bytes())
    if len(data) < 20:
        return False
    json_len, json_type = struct.unpack_from("<II", data, 12)
    if json_type != 0x4E4F534A:
        return False
    json_raw = bytes(data[20 : 20 + json_len])
    try:
        gltf = json.loads(json_raw.rstrip(b" \x00").decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    images = gltf.get("images") or []
    if not images:
        return False
    json_end = 20 + json_len
    json_end += (4 - (json_end % 4)) % 4
    if json_end + 8 > len(data):
        return False
    bin_len, bin_type = struct.unpack_from("<II", data, json_end)
    if bin_type != 0x004E4942:
        return False
    bin_start = json_end + 8
    bin_blob = bytearray(data[bin_start : bin_start + bin_len])
    folders = [path.parent]
    for extra in search_dirs or []:
        if extra and extra not in folders:
            folders.append(Path(extra))
    views = gltf.setdefault("bufferViews", [])
    changed = False
    for image in images:
        if image.get("bufferView") is not None:
            continue
        uri = str(image.get("uri") or "").strip()
        if not uri or uri.startswith("data:"):
            continue
        name = Path(uri).name
        found = next((folder / name for folder in folders if (folder / name).is_file()), None)
        if found is None:
            continue
        blob = found.read_bytes()
        offset = len(bin_blob)
        bin_blob.extend(blob)
        pad = (4 - (len(bin_blob) % 4)) % 4
        bin_blob.extend(b"\x00" * pad)
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(blob)})
        image["bufferView"] = len(views) - 1
        image.pop("uri", None)
        suffix = found.suffix.lower()
        image["mimeType"] = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
        changed = True
    if not changed:
        return False
    if gltf.get("buffers"):
        gltf["buffers"][0]["byteLength"] = len(bin_blob)
    else:
        gltf["buffers"] = [{"byteLength": len(bin_blob)}]
    json_blob = _pad4(json.dumps(gltf, separators=(",", ":"), allow_nan=False).encode("utf-8"), b" ")
    json_chunk = struct.pack("<I", len(json_blob)) + struct.pack("<I", 0x4E4F534A) + json_blob
    bin_chunk = struct.pack("<I", len(bin_blob)) + struct.pack("<I", 0x004E4942) + bytes(bin_blob)
    total = 12 + len(json_chunk) + len(bin_chunk)
    header = struct.pack("<I", 0x46546C67) + struct.pack("<I", 2) + struct.pack("<I", total)
    path.write_bytes(header + json_chunk + bin_chunk)
    return True


def _read_glb(path: Path) -> tuple[dict, bytearray]:
    data = Path(path).read_bytes()
    if len(data) < 20:
        raise RuntimeError("GLB is too small")
    json_len, json_type = struct.unpack_from("<II", data, 12)
    if json_type != 0x4E4F534A:
        raise RuntimeError("First GLB chunk is not JSON")
    gltf = json.loads(bytes(data[20 : 20 + json_len]).rstrip(b" \x00 ").decode("utf-8"))
    json_end = 20 + json_len
    json_end += (4 - (json_end % 4)) % 4
    if json_end + 8 > len(data):
        raise RuntimeError("GLB is missing a BIN chunk")
    bin_len, bin_type = struct.unpack_from("<II", data, json_end)
    if bin_type != 0x004E4942:
        raise RuntimeError("Second GLB chunk is not BIN")
    bin_start = json_end + 8
    return gltf, bytearray(data[bin_start : bin_start + bin_len])


def _write_glb_parts(path: Path, gltf: dict, bin_blob: bytes) -> None:
    if gltf.get("buffers"):
        gltf["buffers"][0]["byteLength"] = len(bin_blob)
    else:
        gltf["buffers"] = [{"byteLength": len(bin_blob)}]
    json_blob = _pad4(json.dumps(gltf, separators=(",", ":"), allow_nan=False).encode("utf-8"), b" ")
    json_chunk = struct.pack("<I", len(json_blob)) + struct.pack("<I", 0x4E4F534A) + json_blob
    padded_bin = _pad4(bin_blob, b"\x00")
    bin_chunk = struct.pack("<I", len(padded_bin)) + struct.pack("<I", 0x004E4942) + padded_bin
    total = 12 + len(json_chunk) + len(bin_chunk)
    header = struct.pack("<I", 0x46546C67) + struct.pack("<I", 2) + struct.pack("<I", total)
    Path(path).write_bytes(header + json_chunk + bin_chunk)


def shrink_glb_textures(path: Path, max_edge: int = 4096) -> bool:
    """Downscale oversized atlas images so the viewer can actually show FINAL."""
    from io import BytesIO

    from PIL import Image

    path = Path(path)
    try:
        gltf, bin_blob = _read_glb(path)
    except RuntimeError:
        return False
    images = gltf.get("images") or []
    views = gltf.setdefault("bufferViews", [])
    if not images:
        return False
    replacements: dict[int, tuple[bytes, str]] = {}
    for image in images:
        view_i = image.get("bufferView")
        if view_i is None or view_i >= len(views):
            continue
        view = views[view_i]
        start = int(view.get("byteOffset") or 0)
        length = int(view.get("byteLength") or 0)
        blob = bytes(bin_blob[start : start + length])
        try:
            im = Image.open(BytesIO(blob))
            im.load()
        except Exception:
            continue
        if max(im.size) <= max_edge:
            continue
        im = im.convert("RGB")
        im.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        out = BytesIO()
        im.save(out, format="JPEG", quality=88, optimize=True)
        replacements[int(view_i)] = (out.getvalue(), "image/jpeg")
        image["mimeType"] = "image/jpeg"
        image.pop("uri", None)
    if not replacements:
        return False
    packed = bytearray()
    new_views = []
    for i, view in enumerate(views):
        if i in replacements:
            blob = replacements[i][0]
        else:
            start = int(view.get("byteOffset") or 0)
            length = int(view.get("byteLength") or 0)
            blob = bytes(bin_blob[start : start + length])
        packed.extend(b"\x00" * ((4 - (len(packed) % 4)) % 4))
        offset = len(packed)
        packed.extend(blob)
        next_view = {"buffer": 0, "byteOffset": offset, "byteLength": len(blob)}
        if view.get("name"):
            next_view["name"] = view["name"]
        if view.get("byteStride"):
            next_view["byteStride"] = view["byteStride"]
        if view.get("target"):
            next_view["target"] = view["target"]
        new_views.append(next_view)
    gltf["bufferViews"] = new_views
    _write_glb_parts(path, gltf, bytes(packed))
    return True


def atlas_pixels_usable(arr: np.ndarray, max_unused: float = 0.28) -> bool:
    """Reject packer backgrounds. `arr` is HxWx3 RGB.

    OpenMVS leaves a large flat fill (often orange) around tiny UV islands.
    A real photo atlas has no single colour covering that much of the image.
    """
    if arr.ndim != 3 or arr.shape[2] < 3 or arr.shape[0] < 8 or arr.shape[1] < 8:
        return False
    rgb = arr[..., :3].astype(np.int16)
    quant = (rgb.reshape(-1, 3) // 16) * 16
    keys, counts = np.unique(quant, axis=0, return_counts=True)
    mode = keys[int(np.argmax(counts))].astype(np.int16)
    mode_frac = float(counts.max()) / max(len(quant), 1)
    if mode_frac < 0.18:
        return True
    unused = float((np.abs(rgb - mode).mean(axis=2) < 18).mean())
    return unused < max_unused


def glb_photo_atlas_usable(path: Path, max_unused: float = 0.28) -> bool:
    """Reject OpenMVS island atlases that minify into colorful static."""
    from io import BytesIO

    from PIL import Image

    path = Path(path)
    try:
        gltf, bin_blob = _read_glb(path)
    except RuntimeError:
        return False
    images = gltf.get("images") or []
    views = gltf.get("bufferViews") or []
    if not images:
        return False
    image = images[0]
    view_i = image.get("bufferView")
    if view_i is None or view_i >= len(views):
        return False
    view = views[view_i]
    start = int(view.get("byteOffset") or 0)
    length = int(view.get("byteLength") or 0)
    blob = bytes(bin_blob[start : start + length])
    try:
        im = Image.open(BytesIO(blob)).convert("RGB")
        im.load()
    except Exception:
        return False
    small = im.resize((96, 96), Image.Resampling.BOX)
    return atlas_pixels_usable(np.asarray(small), max_unused=max_unused)


def write_glb(
    path: Path,
    xyz: np.ndarray,
    faces: np.ndarray,
    rgb: np.ndarray | None = None,
) -> Path:
    """Write a vertex-colored triangle mesh as GLB (glTF 2.0)."""
    if len(xyz) < 3 or len(faces) < 1:
        raise RuntimeError("Mesh is empty — cannot write a GLB model.")

    finite = np.isfinite(xyz).all(axis=1)
    remap = np.full(len(xyz), -1, dtype=np.int32)
    remap[finite] = np.arange(int(finite.sum()), dtype=np.int32)
    positions = np.ascontiguousarray(xyz[finite], dtype=np.float32)
    rgb_f = None
    if rgb is not None and len(rgb) == len(xyz):
        rgb_f = rgb[finite]
    faces = remap[faces.astype(np.int32)]
    faces = faces[(faces >= 0).all(axis=1)]
    if len(positions) < 3 or len(faces) < 1:
        raise RuntimeError("Mesh is empty — cannot write a GLB model.")
    indices = np.ascontiguousarray(faces, dtype=np.uint32)
    colors = np.ones((len(positions), 4), dtype=np.float32)
    if rgb_f is not None and len(rgb_f) == len(positions):
        colors[:, :3] = np.clip(rgb_f.astype(np.float32) / 255.0, 0, 1)
    normals = np.ascontiguousarray(_normals(positions, indices), dtype=np.float32)

    pos_b = positions.tobytes()
    nrm_b = normals.tobytes()
    col_b = colors.tobytes()
    idx_b = indices.tobytes()

    pos_off = 0
    nrm_off = pos_off + len(pos_b)
    col_off = nrm_off + len(nrm_b)
    idx_off = col_off + len(col_b)
    bin_blob = _pad4(pos_b + nrm_b + col_b + idx_b)

    mins = [float(v) for v in positions.min(axis=0)]
    maxs = [float(v) for v in positions.max(axis=0)]
    gltf = {
        "asset": {"version": "2.0", "generator": "OnePass3D"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1, "COLOR_0": 2},
                        "indices": 3,
                        "mode": 4,
                        "material": 0,
                    }
                ]
            }
        ],
        "materials": [
            {
                "name": "vertex-color",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [1, 1, 1, 1],
                    "metallicFactor": 0,
                    "roughnessFactor": 0.9,
                },
                "doubleSided": True,
            }
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": int(len(positions)),
                "type": "VEC3",
                "min": mins,
                "max": maxs,
            },
            {"bufferView": 1, "componentType": 5126, "count": int(len(normals)), "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": int(len(colors)), "type": "VEC4"},
            {"bufferView": 3, "componentType": 5125, "count": int(indices.size), "type": "SCALAR"},
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": pos_off, "byteLength": len(pos_b), "target": 34962},
            {"buffer": 0, "byteOffset": nrm_off, "byteLength": len(nrm_b), "target": 34962},
            {"buffer": 0, "byteOffset": col_off, "byteLength": len(col_b), "target": 34962},
            {"buffer": 0, "byteOffset": idx_off, "byteLength": len(idx_b), "target": 34963},
        ],
        "buffers": [{"byteLength": len(bin_blob)}],
    }
    json_blob = _pad4(json.dumps(gltf, separators=(",", ":"), allow_nan=False).encode("utf-8"), b" ")
    json_chunk = struct.pack("<I", len(json_blob)) + struct.pack("<I", 0x4E4F534A) + json_blob
    bin_chunk = struct.pack("<I", len(bin_blob)) + struct.pack("<I", 0x004E4942) + bin_blob
    total = 12 + len(json_chunk) + len(bin_chunk)
    header = struct.pack("<I", 0x46546C67) + struct.pack("<I", 2) + struct.pack("<I", total)
    path = Path(path)
    path.write_bytes(header + json_chunk + bin_chunk)
    ok, reason = glb_is_valid(path)
    if not ok:
        raise RuntimeError(f"Wrote an invalid GLB: {reason}")
    return path
