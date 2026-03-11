"""Claim-safety checks for generated API/UI copy."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Mapping

_UNSUPPORTED_CLAIM_PATTERNS: Dict[str, re.Pattern[str]] = {
    "direct_dopamine_measurement": re.compile(
        r"\b(directly measures dopamine|is a direct dopamine (?:meter|measurement))\b",
        re.IGNORECASE,
    ),
    "biochemical_certainty_claim": re.compile(
        r"\b(is a biochemical measurement|measures neurotransmitters)\b",
        re.IGNORECASE,
    ),
    "truth_engine_claim": re.compile(
        r"\b(is a truth engine|acts as a truth engine)\b",
        re.IGNORECASE,
    ),
    "facial_truth_claim": re.compile(
        r"\b(facial expressions? alone (?:predict|determine|prove))\b",
        re.IGNORECASE,
    ),
    "sales_certainty_claim": re.compile(
        r"\b(predicts? sales with certainty|guarantees? lift)\b",
        re.IGNORECASE,
    ),
    "protected_trait_inference_claim": re.compile(
        r"\b(infers? protected traits?|predicts? protected traits?)\b",
        re.IGNORECASE,
    ),
}


def find_claim_safety_violations(text: str) -> List[str]:
    """Return matched unsupported-claim labels for a text block."""

    payload = str(text or "")
    violations: List[str] = []
    for label, pattern in _UNSUPPORTED_CLAIM_PATTERNS.items():
        if pattern.search(payload):
            violations.append(label)
    return violations


def scan_texts_for_claim_safety(
    texts: Mapping[str, str] | Iterable[tuple[str, str]],
) -> Dict[str, List[str]]:
    """Return a map of text key -> unsupported-claim labels."""

    if isinstance(texts, Mapping):
        items = texts.items()
    else:
        items = texts
    flagged: Dict[str, List[str]] = {}
    for key, value in items:
        violations = find_claim_safety_violations(value)
        if violations:
            flagged[str(key)] = violations
    return flagged

