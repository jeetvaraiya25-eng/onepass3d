from __future__ import annotations


def _looks_technical(text: str) -> bool:
    lower = text.lower()
    needles = (
        "opencv",
        ".cpp:",
        "assertion failed",
        "traceback",
        "lkpyramid",
        "prevpyr",
        "cv2.",
        "error: (-",
    )
    return any(n in lower for n in needles)


def explain_failure(exc: BaseException) -> str:
    """Plain-language job error. Never store compiler / OpenCV dumps."""
    text = str(exc or "").strip()
    lower = text.lower()

    if "colmap is not installed" in lower:
        return "COLMAP is not installed on this machine."

    if text in {"'list'", "list"} or "keyerror" in lower:
        return (
            "The dense point cloud was created, but the mesh step could not read "
            "the OpenMVS file. Restart the job — it will resume from the dense cloud."
        )

    if "openmvs is not installed" in lower:
        return (
            "OpenMVS is not installed on this machine. "
            "This Mac needs OpenMVS for dense reconstruction because COLMAP PatchMatch requires CUDA."
        )

    if "failed quality validation" in lower:
        return text

    if "cancelled" in lower:
        return "Reconstruction was cancelled."

    if "mac slept" in lower or "app stopped" in lower:
        return (
            "The Mac slept or the app stopped before this job finished. "
            "Click Resume to continue from the last finished stage."
        )

    if "insufficient camera registration" in lower or "were registered" in lower:
        return text

    if "disconnected reconstruction components" in lower:
        return text

    if "patchmatch" in lower or "dense stereo needs a cuda" in lower:
        return text

    if "lkpyramid" in lower or "prevpyr" in lower or "lvlstep" in lower:
        return (
            "These photos didn’t line up. The pictures were mixed — some upright, "
            "some sideways, or different sizes — so the rebuild could not follow "
            "the same spots from one photo to the next. Start a new job with every "
            "photo taken the same way, each one overlapping the last."
        )

    if _looks_technical(text):
        return (
            "The 3D rebuild stopped because the photos or video could not be "
            "tracked all the way through. Start a new job with a slower pass or "
            "more overlapping photos of the same place."
        )

    return text or (
        "Reconstruction didn’t finish. Start a new job with a slow orbit or at "
        "least five overlapping photos of the same place."
    )
