"""Shared runtime statistics — decouples route modules from cross-importing
mutable state.

Both ``routes_prediction`` and ``routes_assets`` update these counters while
``routes_observability`` reads them.  Keeping the dicts and their locks in a
dedicated module eliminates route-to-route import coupling.
"""

from __future__ import annotations

from threading import Lock

# ---------------------------------------------------------------------------
# Predict-job stats (written by routes_prediction, read by routes_observability)
# ---------------------------------------------------------------------------
predict_stats_lock = Lock()
predict_stats: dict[str, int] = {"queued": 0, "active": 0, "completed": 0, "failed": 0}

# ---------------------------------------------------------------------------
# GitHub-upload stats (written by routes_assets, read by routes_observability)
# ---------------------------------------------------------------------------
github_upload_stats_lock = Lock()
github_upload_stats: dict[str, int] = {"attempts": 0, "successes": 0, "failures": 0}
