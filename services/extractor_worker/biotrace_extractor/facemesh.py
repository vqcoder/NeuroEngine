"""MediaPipe FaceMesh wrapper with a small typed interface.

TODO(D12): Migrate from legacy ``mp.solutions.face_mesh.FaceMesh`` to the
task-based ``mediapipe.tasks.vision.FaceLandmarker`` API before Google
fully sunsets the solutions module.

Migration notes:
  - Only this class uses mediapipe directly; downstream modules (au_proxy,
    blink, head_pose, quality) consume the ``List[Point]`` output, so the
    swap is contained here.
  - The new FaceLandmarker returns Protocol-Buffer results rather than
    NormalizedLandmarkList — adapt ``process()`` to produce the same
    ``List[Point]`` pixel-coordinate output.
  - Validate that the 468 landmark indices remain anatomically stable
    across old and new models (critical for hardcoded AU indices in
    au_proxy.py and EAR indices in blink.py).
  - Consider pinning a narrow mediapipe version range until migration is
    complete to avoid surprise breakage.
"""

from __future__ import annotations

from typing import List, Optional

from .geometry import Point

try:
    import cv2
except Exception as exc:  # pragma: no cover - import guarded for runtime environments
    cv2 = None
    _cv2_import_error = exc
else:
    _cv2_import_error = None

try:
    import mediapipe as mp
except Exception as exc:  # pragma: no cover - import guarded for runtime environments
    mp = None
    _mp_import_error = exc
else:
    _mp_import_error = None


class FaceMeshProcessor:
    """Thin wrapper around `mediapipe.solutions.face_mesh.FaceMesh`."""

    def __init__(self) -> None:
        if cv2 is None:
            raise RuntimeError(
                "opencv-python is required for face extraction. "
                "Install package dependencies before running extraction."
            ) from _cv2_import_error

        if mp is None:
            raise RuntimeError(
                "mediapipe is required for landmark extraction. "
                "Install package dependencies before running extraction."
            ) from _mp_import_error

        self._mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def close(self) -> None:
        """Release FaceMesh resources."""

        self._mesh.close()

    def __enter__(self) -> "FaceMeshProcessor":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        self.close()

    def process(self, frame_bgr) -> Optional[List[Point]]:
        """Return first-face landmarks in pixel coordinates, or None."""

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self._mesh.process(rgb)

        if not result.multi_face_landmarks:
            return None

        landmarks = result.multi_face_landmarks[0].landmark
        frame_h, frame_w = frame_bgr.shape[:2]

        return [(landmark.x * frame_w, landmark.y * frame_h) for landmark in landmarks]
