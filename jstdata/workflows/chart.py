"""Barebones terminal bar charts for the discover preview pane."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import mean
from typing import Iterable, Optional, Sequence

from ..models import TimeSeries

FREQ_TIEBREAK = ("Annual", "Quarterly", "Monthly", "Daily", "Intraday")
_EIGHTHS = " ▁▂▃▄▅▆▇█"
BAR_HEIGHT = 3
LABEL_WIDTH = 12


def pick_frequency(series_list: Sequence[TimeSeries]) -> Optional[str]:
    """Most common frequency; ties prefer coarser frequencies."""
    counts = Counter(
        ts.series.frequency for ts in series_list if ts.series.frequency
    )
    if not counts:
        return None
    top = max(counts.values())
    tied = [freq for freq, n in counts.items() if n == top]
    rank = {name: i for i, name in enumerate(FREQ_TIEBREAK)}
    tied.sort(key=lambda freq: rank.get(freq, 99))
    return tied[0]


def pick_series_per_entity(
    series_list: Sequence[TimeSeries],
    entity_ids: Sequence[str],
    frequency: str,
) -> dict[str, Optional[TimeSeries]]:
    """One series per entity at ``frequency`` (most in-window obs, then id)."""
    by_entity: dict[str, list[TimeSeries]] = defaultdict(list)
    wanted = set(entity_ids)
    for ts in series_list:
        if ts.series.frequency != frequency:
            continue
        matched = [ent.id for ent in ts.series.entities if ent.id in wanted]
        if not matched and len(entity_ids) == 1 and not ts.series.entities:
            matched = [entity_ids[0]]
        for eid in matched:
            by_entity[eid].append(ts)

    picked: dict[str, Optional[TimeSeries]] = {}
    for eid in entity_ids:
        candidates = by_entity.get(eid, [])
        if not candidates:
            picked[eid] = None
            continue
        candidates.sort(key=lambda ts: (-len(ts.observations), ts.series.id))
        picked[eid] = candidates[0]
    return picked


def _as_naive(ts: datetime) -> datetime:
    if ts.tzinfo is not None:
        return ts.replace(tzinfo=None)
    return ts


def downsample(
    observations: Sequence,
    n_bins: int,
) -> list[tuple[datetime, Optional[float]]]:
    """Bin observations into at most ``n_bins`` (mean per bin; gaps are None)."""
    if n_bins <= 0 or not observations:
        return []
    obs = sorted(observations, key=lambda o: _as_naive(o.observation_timestamp))
    if len(obs) <= n_bins:
        return [(_as_naive(o.observation_timestamp), o.value) for o in obs]
    start = _as_naive(obs[0].observation_timestamp)
    end = _as_naive(obs[-1].observation_timestamp)
    span = (end - start).total_seconds() or 1.0
    buckets: list[list[float]] = [[] for _ in range(n_bins)]
    for o in obs:
        t = (_as_naive(o.observation_timestamp) - start).total_seconds() / span
        idx = min(n_bins - 1, max(0, int(t * n_bins)))
        buckets[idx].append(o.value)
    out: list[tuple[datetime, Optional[float]]] = []
    for i, vals in enumerate(buckets):
        stamp = start + timedelta(seconds=span * (i + 0.5) / n_bins)
        out.append((stamp, mean(vals) if vals else None))
    return out


def _column_stack(frac: Optional[float], height: int) -> list[str]:
    """Top-to-bottom characters for one time column (no y-axis numbers)."""
    if frac is None or frac <= 0:
        return [" "] * height
    total = height * 8
    filled = max(1, min(total, int(round(frac * total))))
    cells: list[str] = []
    remaining = filled
    for _ in range(height):
        if remaining >= 8:
            cells.append("█")
            remaining -= 8
        elif remaining > 0:
            cells.append(_EIGHTHS[remaining])
            remaining = 0
        else:
            cells.append(" ")
    return list(reversed(cells))


def _scale(values: Iterable[Optional[float]]) -> tuple[float, float]:
    nums = [v for v in values if v is not None]
    if not nums:
        return 0.0, 1.0
    lo, hi = min(nums), max(nums)
    if lo >= 0:
        lo = 0.0
    if hi == lo:
        hi = lo + 1.0
    return lo, hi


def _label(text: str, width: int = LABEL_WIDTH) -> str:
    text = text or ""
    if len(text) <= width:
        return text.ljust(width)
    return text[: width - 1] + "…"


def _axis_line(
    stamps: Sequence[datetime],
    bar_width: int,
    gutter: int = LABEL_WIDTH + 1,
) -> str:
    if not stamps or bar_width <= 0:
        return ""
    years = [
        stamps[0].strftime("%Y"),
        stamps[len(stamps) // 2].strftime("%Y"),
        stamps[-1].strftime("%Y"),
    ]
    uniq: list[str] = []
    for year in years:
        if year not in uniq:
            uniq.append(year)
    if bar_width < 4:
        return " " * gutter + "–".join(uniq)
    labels = [
        (0, uniq[0]),
        (max(0, bar_width // 2 - 2), uniq[len(uniq) // 2]),
        (max(0, bar_width - 4), uniq[-1]),
    ]
    line = [" "] * bar_width
    used: set[int] = set()
    for pos, lab in labels:
        if len(lab) > bar_width:
            continue
        pos = min(max(0, pos), bar_width - len(lab))
        if any(pos + i in used for i in range(len(lab))):
            continue
        for i, ch in enumerate(lab):
            line[pos + i] = ch
            used.add(pos + i)
    return " " * gutter + "".join(line)


def render_preview(
    metric_name: str,
    frequency: str,
    units: str,
    entity_labels: dict[str, str],
    picked: dict[str, Optional[TimeSeries]],
    bar_width: int = 48,
    bar_height: int = BAR_HEIGHT,
) -> str:
    """Shared-scale unicode bars, one small-multiple per entity."""
    width = max(8, bar_width)
    binned: dict[str, list[tuple[datetime, Optional[float]]]] = {}
    all_vals: list[Optional[float]] = []
    all_stamps: list[datetime] = []
    for eid, ts in picked.items():
        if ts is None or not ts.observations:
            binned[eid] = []
            continue
        points = downsample(ts.observations, width)
        binned[eid] = points
        all_vals.extend(v for _, v in points)
        all_stamps.extend(t for t, v in points if v is not None)

    vmin, vmax = _scale(all_vals)
    span = vmax - vmin or 1.0

    header_bits = [metric_name or "metric"]
    if frequency:
        header_bits.append(frequency)
    if units:
        header_bits.append(units)
    if all_stamps:
        header_bits.append(
            f"{min(all_stamps).year}–{max(all_stamps).year}"
        )
    lines = [" · ".join(header_bits), ""]

    for eid, ts in picked.items():
        name = _label(entity_labels.get(eid, eid))
        points = binned.get(eid) or []
        if not points:
            lines.append(f"{name} (no series)")
            lines.append("")
            continue
        columns = []
        for _, value in points:
            if value is None:
                frac = None
            else:
                frac = (value - vmin) / span
            columns.append(_column_stack(frac, bar_height))
        for row in range(bar_height):
            prefix = name if row == bar_height // 2 else " " * LABEL_WIDTH
            bars = "".join(col[row] for col in columns)
            lines.append(f"{prefix} {bars}")
        lines.append("")

    if all_stamps:
        # Use the longest binned series for tick alignment.
        longest = max(binned.values(), key=len) if binned else []
        stamps = [t for t, _ in longest] or sorted(all_stamps)
        lines.append(_axis_line(stamps, min(width, len(stamps))))

    return "\n".join(lines).rstrip() + "\n"
