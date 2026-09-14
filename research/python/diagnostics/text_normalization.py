"""Small deterministic text helpers for safe-phrase diagnostics."""

from __future__ import annotations

import re
import unicodedata


NON_WORD_PATTERN = re.compile(r"[^\w]+", flags=re.UNICODE)
WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_text(value: object) -> str:
    """Normalize Unicode, case, punctuation and repeated whitespace."""

    if value is None:
        return ""

    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""

    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.replace("_", " ")
    text = NON_WORD_PATTERN.sub(" ", text)
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def tokenize_text(value: object) -> list[str]:
    """Return normalized whitespace-delimited tokens."""

    normalized = normalize_text(value)
    return normalized.split() if normalized else []


def token_coverage(
    candidate_text: object,
    reference_text: object,
) -> float:
    """Measure how many unique reference tokens appear in the candidate."""

    candidate_tokens = set(tokenize_text(candidate_text))
    reference_tokens = set(tokenize_text(reference_text))

    if not reference_tokens:
        return 0.0

    shared_tokens = candidate_tokens & reference_tokens
    return len(shared_tokens) / len(reference_tokens)
