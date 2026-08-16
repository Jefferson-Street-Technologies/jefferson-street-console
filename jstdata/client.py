import hashlib
import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import requests

from .models import (
    Entity,
    EntityRelationship,
    Metric,
    Observation,
    Series,
    TimeSeries,
    Resource,
    Taxonomy,
)

APP_DIR = Path.home() / ".jstdata"
CONFIG_FILE = APP_DIR / "config.json"


class ApiKeyNotSetError(Exception):
    pass


class InvalidApiKeyError(Exception):
    pass


class InvalidInputError(Exception):
    pass


@dataclass
class JSTDataClientConfig:
    api_key: Optional[str] = None
    base_url: Optional[str] = None

    def __post_init__(self):
        APP_DIR.mkdir(exist_ok=True)
        
        # 1. Start with defaults
        default_url = "https://api.jeffersonst.io"
        
        # 2. Layer on config file if it exists
        file_api_key = None
        file_base_url = None
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    cfg = json.load(f)
                    file_api_key = cfg.get("api_key")
                    file_base_url = cfg.get("base_url")
            except (json.JSONDecodeError, IOError):
                pass

        # Precedence: Env > Arg > File > Default
        # self.api_key and self.base_url contain 'Arg' if passed, else None.
        
        self.api_key = os.environ.get("JSTDATA_API_KEY") or self.api_key or file_api_key
        self.base_url = os.environ.get("JSTDATA_BASE_URL") or self.base_url or file_base_url or default_url

    def write(self, **kwargs) -> None:
        """Write configuration to the config file."""
        # Read current to preserve keys we aren't updating
        current = {}
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    current = json.load(f)
            except:
                pass

        current["api_key"] = kwargs.get("api_key") or current.get("api_key") or self.api_key
        current["base_url"] = kwargs.get("base_url") or current.get("base_url") or self.base_url

        with open(CONFIG_FILE, "w") as f:
            json.dump(current, f, indent=2)
        
        # Restrict permissions to owner read/write
        CONFIG_FILE.chmod(0o600)

    def read(self) -> Dict[str, Any]:
        """Read the current configuration from file."""
        if not CONFIG_FILE.exists():
            return {}
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)


@dataclass
class JSTDataCache:
    endpoint: str
    params: Optional[Dict[str, Any]]

    def __post_init__(self):
        if self.params is None:
            self.params = {}

        # Normalize params for hashing
        sorted_items = sorted(
            [(k, str(v)) for k, v in self.params.items() if v is not None]
        )
        self.params = dict(sorted_items)

        self._cache_dir = APP_DIR / "cache"
        self._cache_dir.mkdir(exist_ok=True)

        json_data = json.dumps(
            {
                "endpoint": self.endpoint,
                "params": self.params,
            }
        )

        key = hashlib.sha256(json_data.encode()).hexdigest()
        self._cache_file = self._cache_dir / f"{key}.parquet"

    def read(self):
        if not self._cache_file.exists():
            return None
        return pd.read_parquet(self._cache_file)

    def write(self, df: pd.DataFrame):
        df.to_parquet(self._cache_file)


class JSTDataClient:
    def __init__(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ):
        """
        Initializes the JSTDataClient.

        Args:
            api_key: The API key for authenticating with the Jefferson Street REST API.
            base_url: The base URL of the API.
        """
        # Pass non-None values to override defaults/config/env
        kwargs = {}
        if api_key: kwargs["api_key"] = api_key
        if base_url: kwargs["base_url"] = base_url
        self._cfg = JSTDataClientConfig(**kwargs)

    @property
    def api_key(self):
        if not self._cfg.api_key:
            raise ApiKeyNotSetError("API key is not set. Run 'jstdata login' or set JSTDATA_API_KEY.")
        return self._cfg.api_key

    @property
    def base_url(self):
        return self._cfg.base_url

    def validate_key(self, api_key: Optional[str] = None) -> bool:
        """
        Validates the API key by making a lightweight request.
        """
        original_key = self._cfg.api_key
        if api_key:
            self._cfg.api_key = api_key
        
        try:
            # Simple lightweight request to verify the key
            self.make_request("metric", params={"limit": 1})
            return True
        except InvalidApiKeyError:
            return False
        except Exception:
            raise
        finally:
            self._cfg.api_key = original_key

    def make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        enable_cache: bool = False,
    ) -> Dict[str, Any]:
        """
        Low-level method to make a request to the API.
        """
        if endpoint[0] != "/":
            endpoint = f"/{endpoint}"

        url = f"{self.base_url}{endpoint}"

        # Caching logic could be more sophisticated, but keeping it simple for now
        if enable_cache:
            cache = JSTDataCache(endpoint, params)
            cached_df = cache.read()
            if cached_df is not None:
                return {"records": cached_df.to_dict("records")}

        api_key = self.api_key
        with requests.Session() as session:
            session.params = {"api-key": api_key}
            response = session.get(url, params=params)

        if response.status_code == 403:
            raise InvalidApiKeyError("Invalid API key")
        response.raise_for_status()

        data = response.json()
        if enable_cache and "records" in data:
            cache.write(pd.DataFrame(data["records"]))

        return data

    # --- Metrics ---

    def list_metrics(
        self, limit: int = 100, offset: int = 0, sort_order: str = "asc"
    ) -> List[Metric]:
        """List all available metrics."""
        data = self.make_request(
            "metric", {"limit": limit, "offset": offset, "sort_order": sort_order}
        )
        return [Metric.from_dict(m) for m in data["records"]]

    def get_metric(self, metric_id: str) -> Metric:
        """Get details for a specific metric."""
        data = self.make_request(f"metric/{metric_id}")
        return Metric.from_dict(data)

    def get_metric_series(
        self, metric_id: str, limit: int = 100, offset: int = 0
    ) -> List[Series]:
        """Get all series associated with a metric."""
        data = self.make_request(f"metric/{metric_id}/series", {"limit": limit, "offset": offset})
        return [Series.from_dict(s) for s in data["records"]]

    # --- Series ---

    def list_series(
        self, limit: int = 100, offset: int = 0, sort_order: str = "asc"
    ) -> List[Series]:
        """List all available series."""
        data = self.make_request(
            "series", {"limit": limit, "offset": offset, "sort_order": sort_order}
        )
        return [Series.from_dict(s) for s in data["records"]]

    def get_series(self, series_id: str) -> Series:
        """Get details for a specific series."""
        data = self.make_request(f"series/{series_id}")
        return Series.from_dict(data)

    # --- Entities ---

    def get_entity(self, entity_id: str) -> Entity:
        """Get details for a specific entity."""
        data = self.make_request(f"entity/{entity_id}")
        return Entity.from_dict(data)

    def get_entity_series(
        self, entity_id: str, limit: int = 100, offset: int = 0
    ) -> List[Series]:
        """Get all series associated with an entity."""
        data = self.make_request(f"entity/{entity_id}/series", {"limit": limit, "offset": offset})
        return [Series.from_dict(s) for s in data["records"]]

    def get_entity_relations(
        self, entity_id: str, limit: int = 100, offset: int = 0
    ) -> List[EntityRelationship]:
        """Get relationships for an entity (the graph view)."""
        data = self.make_request(
            f"entity/{entity_id}/relations", {"limit": limit, "offset": offset}
        )
        return [EntityRelationship.from_dict(r) for r in data["records"]]

    # --- Taxonomies ---

    def list_taxonomies(
        self, limit: int = 100, offset: int = 0, sort_order: str = "asc"
    ) -> List[Taxonomy]:
        """List taxonomies that have identity (membership) relationships."""
        data = self.make_request(
            "taxonomy", {"limit": limit, "offset": offset, "sort_order": sort_order}
        )
        return [Taxonomy.from_dict(t) for t in data["records"]]

    def get_taxonomy(self, taxonomy_id: str) -> Taxonomy:
        """Get details for a specific taxonomy."""
        data = self.make_request(f"taxonomy/{taxonomy_id}")
        return Taxonomy.from_dict(data)

    def get_taxonomy_entities(
        self, taxonomy_id: str, limit: int = 100, offset: int = 0
    ) -> List[Entity]:
        """List entities that themselves participate in a taxonomy."""
        data = self.make_request(
            f"taxonomy/{taxonomy_id}/entities", {"limit": limit, "offset": offset}
        )
        return [Entity.from_dict(e) for e in data["records"]]

    def get_taxonomy_metrics(
        self, taxonomy_id: str, limit: int = 100, offset: int = 0
    ) -> List[Metric]:
        """List metrics with series on entities in a taxonomy."""
        data = self.make_request(
            f"taxonomy/{taxonomy_id}/metrics", {"limit": limit, "offset": offset}
        )
        return [Metric.from_dict(m) for m in data["records"]]

    # --- Search ---

    def search(
        self, query: str, limit: int = 15, offset: int = 0
    ) -> List[Union[Entity, Metric, Series]]:
        """Unified search across all resource types."""
        data = self.make_request(
            "search", {"query": query, "limit": limit, "offset": offset}
        )
        results = []
        for r in data["records"]:
            res_type = r.get("type")
            if res_type == "entity":
                results.append(Entity.from_dict(r))
            elif res_type == "metric":
                results.append(Metric.from_dict(r))
            elif res_type == "series":
                results.append(Series.from_dict(r))
        return results

    def search_entities(
        self,
        query: str,
        metric: Optional[str] = None,
        taxonomy: Optional[str] = None,
        limit: int = 5,
        offset: int = 0,
    ) -> List[Entity]:
        """Search for entities."""
        params = {"query": query, "limit": limit, "offset": offset}
        if metric:
            params["metric"] = metric
        if taxonomy:
            params["taxonomy"] = taxonomy
        data = self.make_request(
            "search/entities", params
        )
        return [Entity.from_dict(e) for e in data["records"]]

    def search_metrics(
        self,
        query: str,
        entity: Optional[str] = None,
        taxonomy: Optional[str] = None,
        limit: int = 5,
        offset: int = 0,
    ) -> List[Metric]:
        """Search for metrics."""
        params = {"query": query, "limit": limit, "offset": offset}
        if entity:
            params["entity"] = entity
        if taxonomy:
            params["taxonomy"] = taxonomy
        data = self.make_request(
            "search/metrics", params
        )
        return [Metric.from_dict(m) for m in data["records"]]

    def search_series(
        self, query: str, limit: int = 5, offset: int = 0
    ) -> List[Series]:
        """Search for series."""
        data = self.make_request(
            "search/series", {"query": query, "limit": limit, "offset": offset}
        )
        return [Series.from_dict(s) for s in data["records"]]

    # --- Query ---

    def query(
        self,
        metric: Optional[Union[str, List[str]]] = None,
        entity: Optional[Union[str, List[str]]] = None,
        series: Optional[Union[str, List[str]]] = None,
        frequency: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[TimeSeries]:
        """
        Query for observations. This is the main data extraction method.
        """
        params = {
            "metric": metric,
            "entity": entity,
            "series": series,
            "frequency": frequency,
            "start_date": start_date,
            "end_date": end_date,
            "order_by": order_by,
            "start_time": start_time,
            "end_time": end_time,
            "limit": limit,
            "offset": offset,
        }
        # Filter out None values
        params = {k: v for k, v in params.items() if v is not None}

        data = self.make_request("query", params)
        series = [TimeSeries.from_dict(record) for record in data.get("records", [])]
        return series

    def get_resources(self, resource: Union[str, List[str]]) -> List[Resource]:
        """Get details for a specific metric."""
        data = self.make_request("resource", params={"resource": resource})
        records = []
        for r in data["records"]:
            records.append(Resource(id=r["id"], label=r["label"]))
        return records


    def query_df(self, **kwargs) -> pd.DataFrame:
        """
        Convenience method that returns the query results as a single flattened pandas DataFrame.
        Excellent for notebook usage.
        """
        observations = self.query(**kwargs)
        if not observations:
            return pd.DataFrame()

        df = pd.DataFrame([asdict(o) for o in observations])
        df["observation_timestamp"] = pd.to_datetime(df["observation_timestamp"])
        df["release_timestamp"] = pd.to_datetime(df["release_timestamp"])
        return df
