from backend.pipeline.geo.crs import geodetic_to_ecef, telemetry_to_enu, umeyama
import numpy as np


def test_ecef_round_distance():
    a = geodetic_to_ecef(28.6139, 77.2090, 0.0)
    b = geodetic_to_ecef(28.6239, 77.2090, 0.0)
    dist = np.linalg.norm(a - b)
    assert 1000 < dist < 1300


def test_telemetry_enu_origin():
    points = [
        {"lat": 28.6139, "lon": 77.2090, "alt": 10.0},
        {"lat": 28.6149, "lon": 77.2090, "alt": 10.0},
    ]
    enu, origin = telemetry_to_enu(points)
    assert origin["lat"] == 28.6139
    assert np.linalg.norm(enu[0]) < 1e-6
    assert enu[1, 1] > 80  # ~111m north


def test_umeyama_recovers_scale():
    src = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    scale, R, t = 3.0, np.eye(3), np.array([10.0, -4.0, 2.0])
    dst = scale * src + t
    s, rot, trans = umeyama(src, dst)
    assert abs(s - 3.0) < 1e-6
    assert np.allclose(trans, t)
    assert np.allclose(rot, R)
