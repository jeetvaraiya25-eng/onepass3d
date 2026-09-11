import numpy as np

from backend.pipeline.reconstruct.diagnostics import keep_largest_run, trajectory_is_connected


def test_keeps_longest_contiguous_run():
    reg = np.zeros(20, dtype=bool)
    reg[0:4] = True
    reg[8:18] = True
    kept = keep_largest_run(reg)
    assert kept.sum() == 10
    assert kept[8:18].all()
    assert not kept[0]


def test_disconnected_trajectory_fails():
    reg = np.zeros(30, dtype=bool)
    reg[0:8] = True
    reg[20:28] = True
    ok, why, meta = trajectory_is_connected(reg)
    assert not ok
    assert "overlapping" in why.lower()
    assert len(meta["runs"]) == 2


def test_short_run_on_long_sequence_fails():
    reg = np.zeros(80, dtype=bool)
    reg[0:23] = True
    ok, why, _ = trajectory_is_connected(reg)
    assert not ok
