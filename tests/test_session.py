"""Tests for the Session model."""

import json
from pathlib import Path

import pytest

from jstdata.session import Session


def test_to_query_kwargs_omits_empty_and_none():
    session = Session(metric=["gdp"], entity=["usa"])
    assert session.to_query_kwargs() == {
        "metric": ["gdp"],
        "entity": ["usa"],
    }


def test_to_query_kwargs_includes_filters():
    session = Session(
        metric=["gdp"],
        frequency="Annual",
        start_date="2020-01-01",
        end_date="2024-01-01",
        order_by="desc",
    )
    assert session.to_query_kwargs() == {
        "metric": ["gdp"],
        "frequency": "Annual",
        "start_date": "2020-01-01",
        "end_date": "2024-01-01",
        "order_by": "desc",
    }


def test_from_dict_accepts_query_param_names():
    session = Session.from_dict(
        {
            "metric": ["gdp"],
            "entity": ["usa"],
            "series": ["s1"],
            "frequency": "Monthly",
        }
    )
    assert session.metric == ["gdp"]
    assert session.entity == ["usa"]
    assert session.series == ["s1"]
    assert session.frequency == "Monthly"


def test_from_dict_accepts_legacy_plural_keys():
    """Early console saves used metrics/entities."""
    session = Session.from_dict(
        {
            "metrics": ["gross-domestic-product"],
            "entities": ["united-states", "germany"],
            "series": [],
        }
    )
    assert session.metric == ["gross-domestic-product"]
    assert session.entity == ["united-states", "germany"]
    assert session.series == []


def test_round_trip_save_load(tmp_path: Path):
    path = tmp_path / "session.json"
    original = Session(
        metric=["gdp"],
        entity=["usa"],
        frequency="Annual",
        start_date="2010-01-01",
    )
    original.save(path)

    loaded = Session.load(path)
    assert loaded == original

    raw = json.loads(path.read_text())
    assert "metric" in raw
    assert "metrics" not in raw
    assert "frequency" in raw
    assert "order_by" not in raw  # nulls omitted


def test_is_empty_and_resource_ids():
    empty = Session()
    assert empty.is_empty()
    assert empty.resource_ids() == []

    session = Session(metric=["a"], entity=["b"], series=["c"])
    assert not session.is_empty()
    assert session.resource_ids() == ["a", "b", "c"]


def test_add_and_remove_ids():
    session = Session()
    assert session.add_metric("gdp") is True
    assert session.add_metric("gdp") is False
    assert session.add_entity("usa") is True
    assert session.remove_id("gdp") is True
    assert session.metric == []
    assert session.entity == ["usa"]
    assert session.remove_id("missing") is False


def test_to_cli_and_to_python():
    session = Session(
        metric=["gdp"],
        entity=["usa", "gbr"],
        frequency="Annual",
        start_date="2020-01-01",
    )
    cli = session.to_cli()
    assert cli.startswith("jst query ")
    assert "--metric gdp" in cli
    assert "--entity usa" in cli
    assert "--entity gbr" in cli
    assert "--frequency Annual" in cli
    assert "--start-date 2020-01-01" in cli
    assert "order-by" not in cli

    py = session.to_python()
    assert "from jstdata import JSTDataClient" in py
    assert "client.query_df(" in py
    assert "metric=['gdp']" in py
    assert "entity=['usa', 'gbr']" in py
    assert "frequency='Annual'" in py


def test_to_python_empty_session():
    py = Session().to_python()
    assert "df = client.query_df()" in py


def test_execute_and_execute_df():
    session = Session(metric=["gdp"], entity=["usa"])
    calls = []

    class FakeClient:
        def query(self, **kwargs):
            calls.append(("query", kwargs))
            return ["ts"]

        def query_df(self, **kwargs):
            calls.append(("query_df", kwargs))
            return "df"

    client = FakeClient()
    assert session.execute(client) == ["ts"]
    assert session.execute(client, order_by="desc") == ["ts"]
    assert session.execute_df(client) == "df"

    assert calls[0] == ("query", {"metric": ["gdp"], "entity": ["usa"]})
    assert calls[1] == (
        "query",
        {"metric": ["gdp"], "entity": ["usa"], "order_by": "desc"},
    )
    assert calls[2] == ("query_df", {"metric": ["gdp"], "entity": ["usa"]})


def test_to_csv(tmp_path: Path):
    from datetime import datetime

    from jstdata.models import Observation, Series, TimeSeries

    session = Session(metric=["gdp"], entity=["usa"])
    series = Series(
        id="s1",
        label="GDP USA",
        frequency="Annual",
        source="JST",
        units="USD",
        seasonal_adjustment="",
        last_updated=datetime(2024, 1, 1),
        metric_id="gdp",
    )
    ts = TimeSeries(
        series=series,
        observations=[
            Observation(
                series_id="s1",
                observation_timestamp=datetime(2020, 1, 1),
                release_timestamp=datetime(2020, 2, 1),
                value=1.5,
            )
        ],
    )

    class FakeClient:
        def query(self, **kwargs):
            assert kwargs["metric"] == ["gdp"]
            return [ts]

    out = tmp_path / "out.csv"
    path = session.to_csv(FakeClient(), path=out)
    assert path == out
    content = out.read_text()
    assert "DATE,LABEL,VALUE,UNITS,SOURCE" in content
    assert "2020-01-01,GDP USA,1.5,USD,JST" in content


def test_load_existing_repo_session_fixture():
    """The checked-in example session.json uses legacy plural keys."""
    fixture = Path(__file__).resolve().parents[1] / "session.json"
    if not fixture.exists():
        pytest.skip("session.json not present")
    session = Session.load(fixture)
    assert "gross-domestic-product" in session.metric
    assert "united-states" in session.entity
    assert session.to_query_kwargs()["metric"] == session.metric
