"""Portable representation of analytical query intent.

A Session mirrors the parameters of ``JSTDataClient.query``. It contains
no observations — only what is needed to (re)execute a query.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Mapping, Optional, Union

if TYPE_CHECKING:
    import pandas as pd

    from .client import JSTDataClient
    from .models import TimeSeries

PathLike = Union[str, Path]


@dataclass
class Session:
    """Analytical intent for a Jefferson Street query."""

    metric: list[str] = field(default_factory=list)
    entity: list[str] = field(default_factory=list)
    series: list[str] = field(default_factory=list)
    frequency: Optional[str] = None
    head: Optional[int] = None
    tail: Optional[int] = None
    as_of: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    order_by: Optional[str] = None

    def is_empty(self) -> bool:
        """True when the session has no resource selectors."""
        return not (self.metric or self.entity or self.series)

    def resource_ids(self) -> list[str]:
        """All metric, entity, and series IDs in the session."""
        return [*self.metric, *self.entity, *self.series]

    def to_query_kwargs(self) -> dict[str, Any]:
        """kwargs suitable for ``JSTDataClient.query`` / ``query_df``.

        Date/time fields are ignored: ``/query`` is head/tail/as_of only.
        """
        kwargs: dict[str, Any] = {}
        if self.metric:
            kwargs["metric"] = list(self.metric)
        if self.entity:
            kwargs["entity"] = list(self.entity)
        if self.series:
            kwargs["series"] = list(self.series)
        if self.frequency is not None:
            kwargs["frequency"] = self.frequency
        if self.head is not None:
            kwargs["head"] = self.head
        if self.tail is not None:
            kwargs["tail"] = self.tail
        if self.as_of is not None:
            kwargs["as_of"] = self.as_of
        if self.order_by is not None:
            kwargs["order_by"] = self.order_by
        return kwargs

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable dict; omits null optional fields."""
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Session:
        """Build a session from a dict.

        Accepts both query-param names (``metric``/``entity``) and the
        older plural keys (``metrics``/``entities``) used by early saves.
        Date windows from older sessions are preserved but not sent to
        ``/query``.
        """
        metric = data.get("metric")
        if metric is None:
            metric = data.get("metrics", [])
        entity = data.get("entity")
        if entity is None:
            entity = data.get("entities", [])
        series = data.get("series", [])

        return cls(
            metric=list(metric or []),
            entity=list(entity or []),
            series=list(series or []),
            frequency=data.get("frequency"),
            head=data.get("head"),
            tail=data.get("tail"),
            as_of=data.get("as_of"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            order_by=data.get("order_by"),
        )

    def save(self, path: PathLike) -> None:
        """Write this session to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: PathLike) -> Session:
        """Load a session from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def add_metric(self, resource_id: str) -> bool:
        """Append a metric ID if not already present. Returns True if added."""
        if resource_id in self.metric:
            return False
        self.metric.append(resource_id)
        return True

    def add_entity(self, resource_id: str) -> bool:
        """Append an entity ID if not already present. Returns True if added."""
        if resource_id in self.entity:
            return False
        self.entity.append(resource_id)
        return True

    def add_series(self, resource_id: str) -> bool:
        """Append a series ID if not already present. Returns True if added."""
        if resource_id in self.series:
            return False
        self.series.append(resource_id)
        return True

    def remove_id(self, resource_id: str) -> bool:
        """Remove an ID from metric/entity/series lists. Returns True if removed."""
        removed = False
        for collection in (self.metric, self.entity, self.series):
            while resource_id in collection:
                collection.remove(resource_id)
                removed = True
        return removed

    # --- Session operations ---

    def execute(
        self, client: JSTDataClient, **overrides: Any
    ) -> List[TimeSeries]:
        """Run this session against ``client.query``.

        ``overrides`` are merged on top of ``to_query_kwargs()`` (e.g.
        ``order_by="desc"`` for a display preference).
        """
        kwargs = self.to_query_kwargs()
        kwargs.update(overrides)
        return client.query(**kwargs)

    def execute_df(self, client: JSTDataClient, **overrides: Any) -> pd.DataFrame:
        """Run this session and return a flattened DataFrame."""
        kwargs = self.to_query_kwargs()
        kwargs.update(overrides)
        return client.query_df(**kwargs)

    def to_cli(self, program: str = "jst") -> str:
        """Render a reproducible CLI invocation for this session."""
        parts = [program, "query"]
        for m in self.metric:
            parts.append(f"--metric {m}")
        for e in self.entity:
            parts.append(f"--entity {e}")
        for s in self.series:
            parts.append(f"--series {s}")
        if self.frequency:
            parts.append(f"--frequency {self.frequency}")
        if self.head is not None:
            parts.append(f"--head {self.head}")
        if self.tail is not None:
            parts.append(f"--tail {self.tail}")
        if self.as_of:
            parts.append(f"--as-of {self.as_of}")
        return " ".join(parts)

    def to_python(self) -> str:
        """Render a reproducible Python snippet for this session."""
        kwargs = self.to_query_kwargs()
        if not kwargs:
            args = ""
        else:
            args = ",\n".join(f"    {key}={value!r}" for key, value in kwargs.items())
            args = f"\n{args}\n"
        return (
            "from jstdata import JSTDataClient\n"
            "\n"
            "client = JSTDataClient()\n"
            f"df = client.query_df({args})\n"
            "print(df)"
        )

    def to_csv(
        self,
        client: JSTDataClient,
        path: Optional[PathLike] = None,
        **overrides: Any,
    ) -> Path:
        """Execute this session and write observations to a CSV file.

        Returns the path written. When ``path`` is omitted, a timestamped
        ``jst_export_*.csv`` is created in the current directory.
        """
        results = self.execute(client, **overrides)
        out = Path(
            path
            if path is not None
            else f"jst_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )

        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["DATE", "LABEL", "VALUE", "UNITS", "SOURCE"])
            for ts in results:
                for obs in ts.observations:
                    writer.writerow(
                        [
                            obs.observation_timestamp.strftime("%Y-%m-%d"),
                            ts.series.label,
                            obs.value,
                            ts.series.units,
                            ts.series.source,
                        ]
                    )
        return out
