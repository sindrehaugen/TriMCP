"""
nce/vertical_modules/dynamics365/client.py
==========================================
Dataverse Web API HTTP client (OData v4).

Handles bearer token injection, paginated entity list fetches, and
single-entity GET.  Token lifecycle (refresh / cache) is the caller's
responsibility — pass a fresh token per request or use DataverseTokenManager.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

log = logging.getLogger("nce.vertical_modules.dynamics365.client")

_ODATA_HEADERS = {
    "Accept": "application/json",
    "OData-MaxVersion": "4.0",
    "OData-Version": "4.0",
    "Prefer": "odata.include-annotations=OData.Community.Display.V1.FormattedValue",
}


class DataverseClient:
    """
    Async HTTP client for the Dataverse Web API (OData v4).

    Parameters
    ----------
    org_url:
        Organisation root, e.g. ``https://contoso.crm.dynamics.com``.
        Trailing slash is stripped automatically.
    access_token:
        Bearer token for the Dataverse scope.  Obtain via
        ``DataverseTokenManager.get_access_token()``.
    client:
        Optional shared ``httpx.AsyncClient``.  When *None* a temporary
        client is created per request (fine for infrequent cron calls).
    api_version:
        Dataverse Web API version string (default ``"9.2"``).
    """

    def __init__(
        self,
        org_url: str,
        access_token: str,
        client: httpx.AsyncClient | None = None,
        api_version: str = "9.2",
    ) -> None:
        self._base = org_url.rstrip("/")
        self._token = access_token
        self._client = client
        self._api_version = api_version

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def list_entities(
        self,
        entity_set: str,
        *,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        top: int = 1000,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """
        GET a single page of *entity_set* records.

        Returns a dict with keys:
            ``"value"``           — list of entity records
            ``"@odata.nextLink"`` — continuation URL or ``None``
        """
        params: dict[str, str] = {"$top": str(top)}
        if select:
            params["$select"] = ",".join(select)
        if filter_expr:
            params["$filter"] = filter_expr
        if page_token:
            # page_token is the full nextLink URL from a previous response
            url = page_token
            params = {}
        else:
            url = self._entity_url(entity_set)

        return await self._send("GET", url, params=params)

    async def get_entity(
        self,
        entity_set: str,
        entity_id: str,
        *,
        select: list[str] | None = None,
    ) -> dict[str, Any]:
        """GET a single entity record by GUID."""
        params: dict[str, str] = {}
        if select:
            params["$select"] = ",".join(select)
        url = f"{self._entity_url(entity_set)}({entity_id})"
        return await self._send("GET", url, params=params)

    async def paginate(
        self,
        entity_set: str,
        *,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        page_size: int = 1000,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Async generator that yields individual entity records across all pages.

        Usage::

            async for record in client.paginate("accounts", select=["name", "accountid"]):
                process(record)
        """
        page_token: str | None = None
        while True:
            page = await self.list_entities(
                entity_set,
                select=select,
                filter_expr=filter_expr,
                top=page_size,
                page_token=page_token,
            )
            for record in page.get("value", []):
                yield record
            next_link = page.get("@odata.nextLink")
            if not next_link:
                break
            page_token = next_link

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _entity_url(self, entity_set: str) -> str:
        return f"{self._base}/api/data/v{self._api_version}/{entity_set}"

    def _auth_headers(self) -> dict[str, str]:
        return {**_ODATA_HEADERS, "Authorization": f"Bearer {self._token}"}

    async def _send(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = self._auth_headers()
        if self._client is not None:
            return await self._do_request(self._client, method, url, headers, params, json_body)
        async with httpx.AsyncClient(timeout=30.0) as tmp:
            return await self._do_request(tmp, method, url, headers, params, json_body)

    @staticmethod
    async def _do_request(
        client: httpx.AsyncClient,
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, str] | None,
        json_body: dict[str, Any] | None,
    ) -> dict[str, Any]:
        from nce.http_resilience import ExternalAPIClientError, request_with_retry

        try:
            resp = await request_with_retry(
                client,
                method,
                url,
                headers=headers,
                params=params,
                json=json_body,
                follow_redirects=True,
                operation_name="dynamics365:odata",
            )
        except ExternalAPIClientError as exc:
            if exc.status_code == 404:
                return {}
            raise

        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        if resp.content:
            return resp.json()
        return {}
