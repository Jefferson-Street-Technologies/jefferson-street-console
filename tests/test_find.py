"""Tests for the host find modal helpers."""

from jstdata.workflows.find import next_find_mode


def test_next_find_mode_cycles_metric_and_entity():
    assert next_find_mode("metric") == "entity"
    assert next_find_mode("entity") == "metric"
