from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree


OVERLAP_FAIL = (
    "Reconstruction failed because insufficient overlapping views were available."
)


def contiguous_runs(registered: np.ndarray) -> list[tuple[int, int, int]]:
    idx = np.where(registered)[0]
    if len(idx) == 0:
        return []
    runs = []
    start = prev = int(idx[0])
    for i in idx[1:]:
        i = int(i)
        if i == prev + 1:
            prev = i
        else:
            runs.append((start, prev, prev - start + 1))
            start = prev = i
    runs.append((start, prev, prev - start + 1))
    return runs


def keep_largest_run(registered: np.ndarray) -> np.ndarray:
    runs = contiguous_runs(registered)
    if not runs:
        return registered
    start, end, _ = max(runs, key=lambda r: r[2])
    out = np.zeros_like(registered)
    out[start : end + 1] = True
    out &= registered
    return out


def trajectory_is_connected(registered: np.ndarray, min_run: int = 12, min_frac: float = 0.55) -> tuple[bool, str, dict]:
    runs = contiguous_runs(registered)
    n = int(registered.size)
    nreg = int(registered.sum())
    meta = {
        "registered_indices": np.where(registered)[0].astype(int).tolist(),
        "runs": [{"start": a, "end": b, "count": c} for a, b, c in runs],
        "registered": nreg,
        "selected": n,
    }
    if nreg < min_run:
        return False, OVERLAP_FAIL, meta
    if not runs:
        return False, OVERLAP_FAIL, meta
    longest = max(r[2] for r in runs)
    meta["longest_run"] = longest
    if longest < min_run:
        return False, OVERLAP_FAIL, meta
    if longest < int(n * min_frac):
        return False, OVERLAP_FAIL, meta
    if len(runs) > 1 and longest < int(nreg * 0.85):
        return False, OVERLAP_FAIL, meta
    return True, "ok", meta


def cloud_components(xyz: np.ndarray) -> dict:
    if len(xyz) < 20:
        return {"components": 0, "largest_frac": 0.0, "sizes": []}
    tree = cKDTree(xyz)
    d, nn = tree.query(xyz, k=min(8, len(xyz)))
    radius = float(np.median(d[:, 1])) * 3.2
    ii, jj = [], []
    for i, neigh in enumerate(nn):
        for j in neigh[1:]:
            if 0 <= j < len(xyz) and np.linalg.norm(xyz[i] - xyz[j]) <= radius:
                ii.append(i)
                jj.append(int(j))
    if not ii:
        return {"components": len(xyz), "largest_frac": 1.0 / len(xyz), "sizes": [1]}
    graph = coo_matrix((np.ones(len(ii)), (ii, jj)), shape=(len(xyz), len(xyz)))
    n_comp, labels = connected_components(graph + graph.T, directed=False)
    sizes = np.bincount(labels).tolist()
    sizes.sort(reverse=True)
    return {
        "components": int(n_comp),
        "largest_frac": float(sizes[0] / len(xyz)),
        "sizes": sizes[:8],
    }


def assess_dense_cloud(xyz: np.ndarray) -> dict:
    info = cloud_components(xyz)
    if len(xyz) < 400:
        raise RuntimeError(OVERLAP_FAIL)
    if info["largest_frac"] < 0.70:
        raise RuntimeError(OVERLAP_FAIL)
    return info
