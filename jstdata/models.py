from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class Frequency(str, Enum):
    ANNUAL = "Annual"
    QUARTERLY = "Quarterly"
    MONTHLY = "Monthly"
    DAILY = "Daily"
    INTRADAY = "Intraday"


class RelationshipType(str, Enum):
    EQUIVALENT_TO = "equivalent_to"
    CLASSIFIED_AS = "classified_as"
    PART_OF = "part_of"
    HAS_SECURITY = "has_security"


@dataclass(frozen=True)
class Entity:
    id: str
    label: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Entity":
        return cls(id=data["id"], label=data["label"])


@dataclass(frozen=True)
class Metric:
    id: str
    name: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Metric":
        return cls(id=data["id"], name=data.get("name", data.get("label", "")))


@dataclass(frozen=True)
class Taxonomy:
    id: str
    name: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Taxonomy":
        return cls(id=data["id"], name=data.get("name", data.get("label", "")))

@dataclass(frozen=True)
class Resource:
    id: str
    label: str

@dataclass(frozen=True)
class Series:
    id: str
    label: str
    frequency: str
    source: str
    units: str
    seasonal_adjustment: str
    last_updated: datetime
    metric_id: str
    entities: List[Entity] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Series":
        # Handle datetime conversion
        last_updated = data.get("last_updated")
        if isinstance(last_updated, str):
            try:
                # API format: 2024-01-01 00:00:00 or ISO
                last_updated = datetime.fromisoformat(last_updated.replace(" ", "T"))
            except ValueError:
                # Fallback for other potential formats
                last_updated = datetime.strptime(last_updated, "%Y-%m-%d %H:%M:%S")
        
        if last_updated is None:
            last_updated = datetime.min

        entities = [Entity.from_dict(e) for e in data.get("entities", [])]

        return cls(
            id=data["id"],
            label=data.get("label", ""),
            frequency=data.get("frequency", ""),
            source=data.get("source", ""),
            units=data.get("units", ""),
            # Handle the typo 'seasonal_adjsustment' from API spec while supporting the correct spelling
            seasonal_adjustment=data.get(
                "seasonal_adjustment", data.get("seasonal_adjsustment", "")
            ),
            last_updated=last_updated,
            metric_id=data.get("metric_id", ""),
            entities=entities,
        )


@dataclass(frozen=True)
class EntityRelationship:
    id: str
    relationship: RelationshipType
    taxonomy: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EntityRelationship":
        return cls(
            id=data["id"],
            relationship=RelationshipType(data["relationship"]),
            taxonomy=data.get("taxonomy"),
        )


@dataclass(frozen=True)
class Observation:
    series_id: str
    observation_timestamp: datetime
    release_timestamp: datetime
    value: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Observation":
        obs_ts = data["observation_timestamp"]
        rel_ts = data["release_timestamp"]

        if isinstance(obs_ts, str):
            obs_ts = datetime.fromisoformat(obs_ts.replace(" ", "T"))
        if isinstance(rel_ts, str):
            rel_ts = datetime.fromisoformat(rel_ts.replace(" ", "T"))

        return cls(
            series_id=data["series_id"],
            observation_timestamp=obs_ts,
            release_timestamp=rel_ts,
            value=data["value"]
        )

@dataclass(frozen=True)
class TimeSeries:
    series: Series
    observations: List[Observation]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimeSeries":
        series = {
            "id": data.get("id", ""),
            "label": data.get("label", ""),
            "frequency": data.get("frequency", ""),
            "source": data.get("source", ""),
            "units": data.get("units", ""),
            "seasonal_adjustment": data.get("seasonal_adjustment", ""),
            "last_updated": data.get("last_updated", ""),
            "metric_id": data.get("metric_id", ""),
            "entities": data.get("entities", []),
        }
        return cls(
            series=Series.from_dict(series),
            observations=[Observation.from_dict(dict(o, series_id=data["id"])) for o in data["observations"]]
        )
