"""Neuro score taxonomy — public facade.

Re-exports all symbols from the decomposed submodules so that existing
callers (``from .neuro_score_taxonomy import build_neuro_score_taxonomy``)
continue to work without changes.
"""
from .neuro_score_taxonomy_core import *      # noqa: F401,F403
from .neuro_score_taxonomy_core import _SCORE_REGISTRY, _ROLLUP_REGISTRY  # noqa: F401
from .neuro_score_taxonomy_attention import *  # noqa: F401,F403
from .neuro_score_taxonomy_reward import *     # noqa: F401,F403
from .neuro_score_taxonomy_rollups import *    # noqa: F401,F403
