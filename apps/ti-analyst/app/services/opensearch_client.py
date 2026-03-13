import hashlib
import logging
from typing import Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)

ASSETS_INDEX = "ti_analyst_assets"
THREATS_INDEX = "ti_analyst_threats"


class OpenSearchClient:
    def __init__(self, url: str | None = None):
        self.base_url = url or settings.opensearch_url

    def _request(self, method: str, path: str, body: Any = None) -> dict:
        url = f"{self.base_url}/{path}"
        resp = requests.request(method, url, json=body, timeout=10)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def ensure_indices(self) -> None:
        """Create indices if they don't exist."""
        for index in [ASSETS_INDEX, THREATS_INDEX]:
            try:
                self._request("HEAD", index)
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    self._request("PUT", index, {
                        "mappings": {
                            "properties": {
                                "text": {"type": "text"},
                                "metadata": {"type": "object"},
                                "created_at": {"type": "date"},
                            }
                        }
                    })
                    logger.info("Created index: %s", index)

    def index_asset(self, asset_id: str, asset_data: dict) -> None:
        doc = {
            "text": (
                f"{asset_data.get('vendor', '')} {asset_data.get('model', '')} "
                f"{asset_data.get('software_version', '')}"
            ),
            "metadata": asset_data,
            "created_at": asset_data.get("created_at"),
        }
        self._request("PUT", f"{ASSETS_INDEX}/_doc/{asset_id}", doc)

    def search_assets(self, vendor: str | None = None, query: str | None = None) -> list[dict]:
        q = query or vendor or ""
        body = {
            "query": {
                "match": {
                    "text": {
                        "query": q,
                        "minimum_should_match": "75%",
                    }
                }
            },
            "size": 20,
        }
        try:
            result = self._request("POST", f"{ASSETS_INDEX}/_search", body)
            hits = result.get("hits", {}).get("hits", [])
            return [{"id": h["_id"], **h.get("_source", {}).get("metadata", {})} for h in hits]
        except Exception as exc:
            logger.warning("Asset search failed: %s", exc)
            return []

    def index_threat(self, threat_id: str, threat_data: dict) -> None:
        summary = threat_data.get("summary") or threat_data.get("title", "")
        doc = {
            "text": summary,
            "metadata": threat_data,
            "created_at": threat_data.get("created_at"),
        }
        self._request("PUT", f"{THREATS_INDEX}/_doc/{threat_id}", doc)

    def search_similar_threats(self, text: str, top_k: int = 5) -> list[dict]:
        body = {
            "query": {"match": {"text": text}},
            "size": top_k,
        }
        try:
            result = self._request("POST", f"{THREATS_INDEX}/_search", body)
            hits = result.get("hits", {}).get("hits", [])
            return [
                {"id": h["_id"], "score": h.get("_score", 0), **h.get("_source", {}).get("metadata", {})}
                for h in hits
            ]
        except Exception as exc:
            logger.warning("Threat search failed: %s", exc)
            return []

    @staticmethod
    def content_hash(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:64]
