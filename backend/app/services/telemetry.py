from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree

from backend.app.config import TELEMETRY_EXTENSIONS


LAT_RE = re.compile(
    r"(?:gps\s*)?lat(?:itude)?[:\s=]+(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
LON_RE = re.compile(
    r"(?:gps\s*)?lon(?:gitude)?[:\s=]+(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
ALT_RE = re.compile(
    r"(?:rel_alt|abs_alt|altitude|alt)[:\s=]+(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
BRACKET_RE = re.compile(
    r"\[latitude[:\s]+(-?\d+(?:\.\d+)?)\]\s*\[longitude[:\s]+(-?\d+(?:\.\d+)?)\]",
    re.IGNORECASE,
)


def find_telemetry_file(input_dir: Path) -> Optional[Path]:
    for path in sorted(input_dir.iterdir()):
        if path.suffix.lower() in TELEMETRY_EXTENSIONS:
            return path
    return None


def parse_telemetry(path: Path) -> list[dict[str, float]]:
    suffix = path.suffix.lower()
    if suffix == ".srt":
        return _parse_srt(path)
    if suffix == ".csv":
        return _parse_csv(path)
    if suffix == ".gpx":
        return _parse_gpx(path)
    if suffix == ".json":
        return _parse_json(path)
    return _parse_srt(path)


def _parse_srt(path: Path) -> list[dict[str, float]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    blocks = re.split(r"\n\s*\n", text.strip())
    points: list[dict[str, float]] = []
    for block in blocks:
        lat = lon = alt = None
        match = BRACKET_RE.search(block)
        if match:
            lat, lon = float(match.group(1)), float(match.group(2))
        else:
            lat_m = LAT_RE.search(block)
            lon_m = LON_RE.search(block)
            if lat_m and lon_m:
                lat, lon = float(lat_m.group(1)), float(lon_m.group(2))
        alt_m = ALT_RE.search(block)
        if alt_m:
            alt = float(alt_m.group(1))
        if lat is None or lon is None:
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        points.append({"lat": lat, "lon": lon, "alt": alt if alt is not None else 0.0})
    return points


def _parse_csv(path: Path) -> list[dict[str, float]]:
    with path.open(newline="", encoding="utf-8", errors="ignore") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        fields = {name.lower().strip(): name for name in reader.fieldnames}

        def pick(*names: str) -> Optional[str]:
            for name in names:
                if name in fields:
                    return fields[name]
            return None

        lat_key = pick("lat", "latitude", "gpslatitude", "y")
        lon_key = pick("lon", "lng", "longitude", "gpslongitude", "x")
        alt_key = pick("alt", "altitude", "height", "rel_alt", "z")
        if not lat_key or not lon_key:
            return []
        points: list[dict[str, float]] = []
        for row in reader:
            try:
                lat = float(row[lat_key])
                lon = float(row[lon_key])
                alt = float(row[alt_key]) if alt_key and row.get(alt_key) else 0.0
            except (TypeError, ValueError):
                continue
            points.append({"lat": lat, "lon": lon, "alt": alt})
        return points


def _parse_gpx(path: Path) -> list[dict[str, float]]:
    tree = ElementTree.parse(path)
    points: list[dict[str, float]] = []
    for node in tree.iter():
        if not node.tag.lower().endswith("trkpt") and not node.tag.lower().endswith("wpt"):
            continue
        try:
            lat = float(node.attrib["lat"])
            lon = float(node.attrib["lon"])
        except (KeyError, ValueError):
            continue
        alt = 0.0
        for child in node:
            if child.tag.lower().endswith("ele") and child.text:
                try:
                    alt = float(child.text)
                except ValueError:
                    pass
        points.append({"lat": lat, "lon": lon, "alt": alt})
    return points


def _parse_json(path: Path) -> list[dict[str, float]]:
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("points", [])
    points: list[dict[str, float]] = []
    for row in rows:
        if "lat" in row and "lon" in row:
            points.append(
                {
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "alt": float(row.get("alt", 0.0)),
                }
            )
    return points
