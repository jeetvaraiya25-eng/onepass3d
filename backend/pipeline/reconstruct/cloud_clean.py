from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree


def clean_dense_cloud(
    xyz: np.ndarray,
    rgb: np.ndarray,
    conf: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Statistical + isolation filter, then oriented normals. No meshing here."""
    if len(xyz) < 200:
        raise RuntimeError(
            "3D reconstruction could not produce a reliable surface from this video."
        )
    xyz, rgb, conf = _confidence_filter(xyz, rgb, conf)
    xyz, rgb, conf = _statistical_outliers(xyz, rgb, conf)
    xyz, rgb, conf = _isolated(xyz, rgb, conf)
    if len(xyz) < 200:
        raise RuntimeError(
            "3D reconstruction could not produce a reliable surface from this video."
        )
    normals = _estimate_normals(xyz)
    xyz, rgb, conf, normals = _drop_inconsistent(xyz, rgb, conf, normals)
    assess_cloud(xyz, normals)
    return xyz, rgb, conf, normals


def _confidence_filter(xyz, rgb, conf):
    if len(conf) != len(xyz):
        return xyz, rgb, conf
    keep = conf >= max(float(np.percentile(conf, 18)), 0.28)
    if keep.sum() < 200:
        return xyz, rgb, conf
    return xyz[keep], rgb[keep], conf[keep]


def _statistical_outliers(xyz, rgb, conf, k: int = 12, std_mult: float = 1.6):
    tree = cKDTree(xyz)
    d, _ = tree.query(xyz, k=min(k + 1, len(xyz)))
    mean = d[:, 1:].mean(axis=1)
    mu, sd = float(np.mean(mean)), float(np.std(mean))
    keep = mean <= mu + std_mult * sd
    return xyz[keep], rgb[keep], conf[keep]


def _isolated(xyz, rgb, conf, k: int = 8):
    tree = cKDTree(xyz)
    d, _ = tree.query(xyz, k=min(k + 1, len(xyz)))
    radius = float(np.median(d[:, 1])) * 3.5
    keep = d[:, k if k < d.shape[1] else -1] < max(radius, 1e-4)
    return xyz[keep], rgb[keep], conf[keep]


def _estimate_normals(xyz, k: int = 18) -> np.ndarray:
    tree = cKDTree(xyz)
    _, idx = tree.query(xyz, k=min(k + 1, len(xyz)))
    normals = np.zeros_like(xyz)
    for i, neigh in enumerate(idx):
        pts = xyz[neigh[1:]] - xyz[i]
        if len(pts) < 3:
            continue
        cov = pts.T @ pts
        _, vecs = np.linalg.eigh(cov)
        normals[i] = vecs[:, 0]
    center = xyz.mean(axis=0)
    flip = np.einsum("ij,ij->i", normals, xyz - center) < 0
    normals[flip] *= -1
    lens = np.linalg.norm(normals, axis=1, keepdims=True)
    lens[lens < 1e-9] = 1.0
    return normals / lens


def _drop_inconsistent(xyz, rgb, conf, normals):
    tree = cKDTree(xyz)
    _, idx = tree.query(xyz, k=min(7, len(xyz)))
    agree = []
    for i, neigh in enumerate(idx):
        dots = np.abs(np.einsum("j,ij->i", normals[i], normals[neigh]))
        agree.append(float(dots.mean()))
    keep = np.asarray(agree) > 0.35
    if keep.sum() < 200:
        return xyz, rgb, conf, normals
    return xyz[keep], rgb[keep], conf[keep], normals[keep]


def assess_cloud(xyz: np.ndarray, normals: np.ndarray) -> None:
    """Refuse a sprayed noise-ball before any surface is built."""
    if len(xyz) < 200:
        raise RuntimeError(
            "3D reconstruction could not produce a reliable surface from this video."
        )
    tree = cKDTree(xyz)
    k = min(12, len(xyz))
    _, idx = tree.query(xyz, k=k)
    planar = 0
    sample = np.linspace(0, len(xyz) - 1, min(len(xyz), 2500), dtype=int)
    for i in sample:
        pts = xyz[idx[i]]
        pts = pts - pts.mean(axis=0)
        cov = pts.T @ pts
        w = np.linalg.eigvalsh(cov)
        if w[-1] > 1e-10 and w[0] / w[-1] < 0.12:
            planar += 1
    if planar / max(len(sample), 1) < 0.04:
        raise RuntimeError(
            "3D reconstruction could not produce a reliable surface from this video."
        )
