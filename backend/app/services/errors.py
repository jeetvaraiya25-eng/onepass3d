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
