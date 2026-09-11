from __future__ import annotations


def reconstruction_quality_score(sparse: dict, dense: dict | None = None, mesh: dict | None = None) -> dict:
    score = 0.0
    notes = []

    ratio = float(sparse.get("registrationRatio") or 0)
    if ratio >= 0.85:
        score += 22
    elif ratio >= 0.75:
        score += 16
    elif ratio >= 0.60:
        score += 10
        notes.append("Camera registration is only acceptable.")
    else:
        notes.append("Too few cameras registered.")

    if int(sparse.get("components") or 99) == 1:
        score += 18
    else:
        notes.append("More than one reconstruction component.")

    reproj = float(sparse.get("meanReprojectionError") or 99)
    if reproj <= 1.6:
        score += 12
    elif reproj <= 3.0:
        score += 8
    else:
        notes.append("Reprojection error is high.")

    if int(sparse.get("sparsePoints") or 0) >= 3000:
        score += 8
    elif int(sparse.get("sparsePoints") or 0) >= 800:
        score += 4

    if dense:
        if dense.get("ok"):
            score += 16
        largest = float(dense.get("largestFraction") or 0)
        if largest >= 0.85:
            score += 8
        elif largest >= 0.70:
            score += 4
            notes.append("Dense cloud has some fragments.")
        if int(dense.get("densePoints") or 0) >= 200000:
            score += 6
        elif int(dense.get("densePoints") or 0) >= 20000:
            score += 3

    if mesh:
        if mesh.get("ok"):
            score += 10
        largest = float(mesh.get("largestFraction") or 0)
        if largest >= 0.90:
            score += 6
        elif largest >= 0.65:
            score += 3
            notes.append("Mesh is not fully connected.")

    score = int(min(100, round(score)))
    gate = "GOOD"
    if dense and dense.get("status") == "FAILED":
        gate = "FAILED"
    elif mesh and mesh.get("status") == "FAILED":
        gate = "FAILED"
    elif (dense and dense.get("status") == "WARNING") or (mesh and mesh.get("status") == "WARNING"):
        gate = "WARNING"
        notes.append("Some regions are incomplete or disconnected.")
    if gate == "FAILED" or score < 50:
        status = "FAILED"
    elif gate == "WARNING" or score < 75:
        status = "WARNING"
    else:
        status = "GOOD"
    return {
        "score": score,
        "status": status,
        "notes": notes,
        "label": f"{score}/100",
    }
