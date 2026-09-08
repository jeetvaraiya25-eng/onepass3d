from pathlib import Path

from backend.app.services.telemetry import parse_telemetry


def test_parse_dji_style_srt(tmp_path: Path):
    srt = tmp_path / "flight.srt"
    srt.write_text(
        """1
00:00:00,000 --> 00:00:01,000
[latitude: 28.613900] [longitude: 77.209000] [rel_alt: 80.000]

2
00:00:01,000 --> 00:00:02,000
[latitude: 28.614000] [longitude: 77.209100] [rel_alt: 81.200]
""",
        encoding="utf-8",
    )
    points = parse_telemetry(srt)
    assert len(points) == 2
    assert abs(points[0]["lat"] - 28.6139) < 1e-6
    assert points[1]["alt"] == 81.2
