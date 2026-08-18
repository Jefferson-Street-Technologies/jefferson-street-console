from datetime import datetime

import pytest

from jstdata.models import Entity, Observation, Series, TimeSeries
from jstdata.workflows.base import PipelineError, get_step, resolve_pipeline
from jstdata.workflows.chart import (
    downsample,
    pick_frequency,
    pick_series_per_entity,
    render_preview,
)


def _ts(sid, freq, entities, values, units="% of GDP"):
    series = Series(
        id=sid,
        label=sid,
        frequency=freq,
        source="test",
        units=units,
        seasonal_adjustment="",
        last_updated=datetime(2024, 1, 1),
        metric_id="military-expenditure",
        entities=[Entity(id=e, label=e.title()) for e in entities],
    )
    obs = [
        Observation(
            series_id=sid,
            observation_timestamp=datetime(2020 + i, 1, 1),
            release_timestamp=datetime(2020 + i, 1, 1),
            value=v,
        )
        for i, v in enumerate(values)
    ]
    return TimeSeries(series=series, observations=obs)


def test_pick_frequency_majority_wins():
    series = [
        _ts("a", "Annual", ["fr"], [1]),
        _ts("b", "Monthly", ["fr"], [1]),
        _ts("c", "Monthly", ["de"], [1]),
    ]
    assert pick_frequency(series) == "Monthly"


def test_pick_frequency_tie_prefers_annual():
    series = [
        _ts("a", "Annual", ["fr"], [1]),
        _ts("b", "Monthly", ["de"], [1]),
    ]
    assert pick_frequency(series) == "Annual"


def test_pick_series_per_entity_most_observations_then_id():
    series = [
        _ts("z", "Annual", ["fr"], [1.0]),
        _ts("a", "Annual", ["fr"], [1.0, 2.0, 3.0]),
        _ts("m", "Monthly", ["fr"], [9.0, 9.0, 9.0, 9.0]),
        _ts("de1", "Annual", ["de"], [1.0]),
    ]
    picked = pick_series_per_entity(series, ["fr", "de", "pl"], "Annual")
    assert picked["fr"].series.id == "a"
    assert picked["de"].series.id == "de1"
    assert picked["pl"] is None


def test_downsample_keeps_short_series():
    ts = _ts("a", "Annual", ["fr"], [1.0, 2.0, 3.0])
    points = downsample(ts.observations, 10)
    assert len(points) == 3
    assert points[0][1] == 1.0


def test_downsample_bins_long_series():
    ts = _ts("a", "Annual", ["fr"], list(range(20)))
    points = downsample(ts.observations, 5)
    assert len(points) == 5
    assert all(v is not None for _, v in points)


def test_render_preview_has_time_and_entities_not_y_ticks():
    picked = {
        "fr": _ts("fr-a", "Annual", ["fr"], [1.0, 2.0, 4.0]),
        "de": _ts("de-a", "Annual", ["de"], [1.0, 1.5, 1.2]),
        "pl": None,
    }
    text = render_preview(
        "military expenditure",
        "Annual",
        "% of GDP",
        {"fr": "France", "de": "Germany", "pl": "Poland"},
        picked,
        bar_width=24,
    )
    assert "military expenditure" in text
    assert "Annual" in text
    assert "% of GDP" in text
    assert "France" in text
    assert "Germany" in text
    assert "no series" in text
    assert "2020" in text
    assert " |\n" not in text
    assert "4.0 |" not in text


def test_discover_is_registered():
    import jstdata.workflows  # noqa: F401

    spec = get_step("discover")
    assert spec.name == "Discover"
    assert spec.to_dict()["example"].startswith("jst run console")
    assert any(a["name"] == "mode" for a in spec.to_dict()["arguments"])
    keys = {b["key"] for b in spec.to_dict()["bindings"]}
    assert "/" in keys
    assert "shift+enter" in keys
    assert "tab" in keys


def test_resolve_discover_mode():
    resolved = resolve_pipeline(["discover", "--mode", "intersect"])
    assert resolved[0].spec.id == "discover"
    assert resolved[0].kwargs["mode"] == "intersect"

    defaulted = resolve_pipeline(["discover"])
    assert defaulted[0].kwargs["mode"] == "union"

    with pytest.raises(PipelineError, match="Choices"):
        resolve_pipeline(["discover", "--mode", "xor"])