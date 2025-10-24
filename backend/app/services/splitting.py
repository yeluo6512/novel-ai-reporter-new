from __future__ import annotations

import math
import re
from enum import Enum
from typing import Iterable, List, Sequence


class SplitStrategy(str, Enum):
    """Supported splitting strategies."""

    CHARACTER_COUNT = "character_count"
    KEYWORDS = "keywords"
    RATIO = "ratio"
    FIXED_CHAPTERS = "fixed_chapters"


def split_by_character_count(text: str, max_chars: int) -> List[str]:
    """Split text into chunks with a maximum character length."""

    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero")

    if not text:
        return []

    return [text[start : start + max_chars] for start in range(0, len(text), max_chars)]


def split_by_keywords(text: str, keywords: Sequence[str]) -> List[str]:
    """Split text by keyword occurrences.

    Each keyword acts as a boundary. Multiple occurrences of a keyword are all
    considered boundaries. Empty boundaries are skipped to avoid producing empty
    segments unless the text itself is empty.
    """

    cleaned_keywords = [keyword for keyword in keywords if keyword]

    if not text:
        return []

    if not cleaned_keywords:
        return [text]

    boundaries = set()
    for keyword in cleaned_keywords:
        for match in re.finditer(re.escape(keyword), text):
            boundaries.add(match.start())

    if not boundaries:
        return [text]

    sorted_boundaries = sorted(boundaries)
    segments: List[str] = []
    start = 0

    for boundary in sorted_boundaries:
        if boundary < start:
            continue
        segments.append(text[start:boundary])
        start = boundary

    segments.append(text[start:])

    filtered_segments = [segment for segment in segments if segment]

    return filtered_segments if filtered_segments else [text]


def split_by_ratio(text: str, ratios: Sequence[float]) -> List[str]:
    """Split text according to ratios.

    Ratios must be positive numbers. The number of returned segments equals the
    length of ``ratios``. Empty segments are returned when the ratios request
    more segments than there are characters in the text, ensuring the segment
    count remains stable.
    """

    if not ratios:
        raise ValueError("ratios must not be empty")

    cleaned_ratios = [float(ratio) for ratio in ratios]

    if any(ratio <= 0 for ratio in cleaned_ratios):
        raise ValueError("all ratios must be greater than zero")

    total_length = len(text)

    if total_length == 0:
        return ["" for _ in cleaned_ratios]

    ratio_sum = math.fsum(cleaned_ratios)
    if ratio_sum <= 0:
        raise ValueError("sum of ratios must be greater than zero")

    normalized = [ratio / ratio_sum for ratio in cleaned_ratios]
    boundaries: List[int] = []
    cumulative = 0.0
    last_boundary = 0

    for ratio in normalized[:-1]:
        cumulative += ratio
        boundary = int(round(cumulative * total_length))
        if boundary <= last_boundary:
            boundary = min(total_length, last_boundary + 1)
        boundaries.append(boundary)
        last_boundary = boundary

    return _segments_from_boundaries(text, boundaries)


def split_by_fixed_chapters(text: str, chapters: int) -> List[str]:
    """Split text into a fixed number of chapters of roughly equal length."""

    if chapters <= 0:
        raise ValueError("chapters must be greater than zero")

    if chapters == 1:
        return [text]

    return split_by_ratio(text, [1.0] * chapters)


def _segments_from_boundaries(text: str, boundaries: Iterable[int]) -> List[str]:
    """Build segments from a sequence of boundary indices."""

    sorted_boundaries = sorted(boundaries)
    indexes = [0, *sorted_boundaries, len(text)]

    segments: List[str] = []
    for start, end in zip(indexes, indexes[1:]):
        segments.append(text[start:end])

    return segments
