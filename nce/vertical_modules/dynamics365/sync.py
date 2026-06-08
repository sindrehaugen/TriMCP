"""
nce/vertical_modules/dynamics365/sync.py
=========================================
Deterministic Track: Dataverse entity sync → kg_edges.

Polls Customer Service + Field Service entities from the Dataverse Web API
and writes structured graph edges into NCE's ``kg_edges`` table using
idempotent UNNEST upserts.  Follows the same ``(conn, namespace_id, client)``
constructor pattern as the NetBox modules.

Covered entity sets
-------------------
Core CRM:
  - Accounts, Contacts, Opportunities, Incidents (Cases)
Field Service:
  - Work Orders, Customer Assets, Functional Locations, Agreements
Knowledge:
  - Knowledge Articles (published, latest version only)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import asyncpg
from nce.config import cfg
from nce.vertical_modules.dynamics365.client import DataverseClient

log = logging.getLogger("nce.vertical_modules.dynamics365.sync")

# OData $select fields — fetch only what we need to keep payloads small.
_ACCOUNT_FIELDS = ["accountid", "name", "websiteurl", "telephone1", "address1_city"]
_CONTACT_FIELDS = [
    "contactid",
    "fullname",
    "emailaddress1",
    "_parentcustomerid_value",
    "_parentcustomerid_value@OData.Community.Display.V1.FormattedValue",
]
_OPPORTUNITY_FIELDS = [
    "opportunityid",
    "name",
    "stagename",
    "_parentaccountid_value",
    "_parentaccountid_value@OData.Community.Display.V1.FormattedValue",
]
_INCIDENT_FIELDS = [
    "incidentid",
    "ticketnumber",
    "title",
    "prioritycode",
    "prioritycode@OData.Community.Display.V1.FormattedValue",
    "statuscode@OData.Community.Display.V1.FormattedValue",
    "_customerid_value@OData.Community.Display.V1.FormattedValue",
    "_ownerid_value",
    "_ownerid_value@OData.Community.Display.V1.FormattedValue",
]

_PRIORITY_LABELS = {1: "High", 2: "Normal", 3: "Low"}

# ---------------------------------------------------------------------------
# Field Service entity field lists
# ---------------------------------------------------------------------------
_WORK_ORDER_FIELDS = [
    "msdyn_workorderid",
    "msdyn_name",
    "_msdyn_serviceaccount_id_value",
    "_msdyn_serviceaccount_id_value@OData.Community.Display.V1.FormattedValue",
    "msdyn_systemstatus",
    "msdyn_systemstatus@OData.Community.Display.V1.FormattedValue",
    "_ownerid_value",
    "_ownerid_value@OData.Community.Display.V1.FormattedValue",
    "_msdyn_primaryincidenttype_value@OData.Community.Display.V1.FormattedValue",
    "_msdyn_workordertype_value@OData.Community.Display.V1.FormattedValue",
]

_AGREEMENT_FIELDS = [
    "msdyn_agreementid",
    "msdyn_name",
    "_msdyn_serviceaccount_id_value",
    "_msdyn_serviceaccount_id_value@OData.Community.Display.V1.FormattedValue",
    "msdyn_startdate",
    "msdyn_enddate",
    "statecode",
    "statecode@OData.Community.Display.V1.FormattedValue",
]

_CUSTOMER_ASSET_FIELDS = [
    "msdyn_customerassetid",
    "msdyn_name",
    "_msdyn_account_id_value",
    "_msdyn_account_id_value@OData.Community.Display.V1.FormattedValue",
    "_msdyn_functionallocations_value",
    "_msdyn_functionallocations_value@OData.Community.Display.V1.FormattedValue",
    "_msdyn_product_value",
    "_msdyn_product_value@OData.Community.Display.V1.FormattedValue",
]

_FUNCTIONAL_LOCATION_FIELDS = [
    "msdyn_functionallocationid",
    "msdyn_name",
    "_msdyn_parentfunctionallocation_value",
    "_msdyn_parentfunctionallocation_value@OData.Community.Display.V1.FormattedValue",
    "_msdyn_account_id_value",
    "_msdyn_account_id_value@OData.Community.Display.V1.FormattedValue",
]

_KNOWLEDGE_ARTICLE_FIELDS = [
    "knowledgearticleid",
    "title",
    "description",
    "statecode",
    "statecode@OData.Community.Display.V1.FormattedValue",
    "islatestversion",
    "keywords",
]

# msdyn_systemstatus values for Work Orders (for filtering / labelling)
_WO_STATUS_LABELS: dict[int, str] = {
    690970000: "Unscheduled",
    690970001: "Scheduled",
    690970002: "In Progress",
    690970003: "Completed",
    690970004: "Posted",
    690970005: "Canceled",
}


def _safe_label(value: str) -> str:
    """Strip characters unsafe for kg_edges label columns (keep printable ASCII)."""
    if not value:
        return "unknown"
    return "".join(c if c.isalnum() or c in " _-.()" else "_" for c in value).strip()[:200]


class DataverseSyncEngine:
    """
    Polls Dataverse entities and writes graph topology to NCE ``kg_edges``.

    Parameters
    ----------
    conn:
        RLS-scoped asyncpg connection (already within a namespace session).
    namespace_id:
        Tenant namespace UUID for ``kg_edges.namespace_id``.
    client:
        Authenticated ``DataverseClient`` instance.
    """

    def __init__(
        self,
        conn: asyncpg.Connection,
        namespace_id: uuid.UUID,
        client: DataverseClient,
    ) -> None:
        self._conn = conn
        self._ns = namespace_id
        self._client = client
        self._page_size = cfg.NCE_D365_SYNC_PAGE_SIZE

    # ------------------------------------------------------------------
    # Entity sync methods
    # ------------------------------------------------------------------

    async def sync_accounts(self) -> dict[str, Any]:
        """Fetch all Accounts and upsert them as kg_nodes (entity_type='D365_Account')."""
        count = 0
        async for record in self._client.paginate(
            "accounts", select=_ACCOUNT_FIELDS, page_size=self._page_size
        ):
            name = _safe_label(record.get("name") or record.get("accountid", ""))
            if not name or name == "unknown":
                continue
            await self._upsert_kg_node(
                f"Account:{name}", "D365_Account", {"account_id": record.get("accountid")}
            )
            count += 1

        log.info("[D365-SYNC] sync_accounts namespace=%s count=%d", self._ns, count)
        return {"entity": "accounts", "upserted": count}

    async def sync_contacts(self) -> dict[str, Any]:
        """Fetch Contacts and write HAS_CONTACT / WORKS_AT edges to parent Account."""
        edges: list[tuple[str, str, str, float]] = []
        async for record in self._client.paginate(
            "contacts", select=_CONTACT_FIELDS, page_size=self._page_size
        ):
            fullname = _safe_label(record.get("fullname") or record.get("contactid", ""))
            account_name = _safe_label(
                record.get("_parentcustomerid_value@OData.Community.Display.V1.FormattedValue")
                or ""
            )
            if not fullname or fullname == "unknown":
                continue
            if account_name and account_name != "unknown":
                edges.append((f"Account:{account_name}", "HAS_CONTACT", f"Contact:{fullname}", 1.0))
                edges.append((f"Contact:{fullname}", "WORKS_AT", f"Account:{account_name}", 1.0))

        written = await self._upsert_kg_edges_batch(edges)
        log.info("[D365-SYNC] sync_contacts namespace=%s edges=%d", self._ns, written)
        return {"entity": "contacts", "edges_written": written}

    async def sync_opportunities(self) -> dict[str, Any]:
        """Fetch Opportunities and write HAS_OPPORTUNITY / HAS_STAGE edges."""
        edges: list[tuple[str, str, str, float]] = []
        async for record in self._client.paginate(
            "opportunities", select=_OPPORTUNITY_FIELDS, page_size=self._page_size
        ):
            opp_name = _safe_label(record.get("name") or record.get("opportunityid", ""))
            account_name = _safe_label(
                record.get("_parentaccountid_value@OData.Community.Display.V1.FormattedValue") or ""
            )
            stage = _safe_label(record.get("stagename") or "Unknown")

            if not opp_name or opp_name == "unknown":
                continue
            if account_name and account_name != "unknown":
                edges.append(
                    (f"Account:{account_name}", "HAS_OPPORTUNITY", f"Opportunity:{opp_name}", 1.0)
                )
            edges.append((f"Opportunity:{opp_name}", "HAS_STAGE", f"PipelineStage:{stage}", 1.0))

        written = await self._upsert_kg_edges_batch(edges)
        log.info("[D365-SYNC] sync_opportunities namespace=%s edges=%d", self._ns, written)
        return {"entity": "opportunities", "edges_written": written}

    async def sync_incidents(self) -> dict[str, Any]:
        """Fetch open Incidents (Cases) and write REPORTED_BY / ASSIGNED_TO / HAS_PRIORITY edges."""
        edges: list[tuple[str, str, str, float]] = []
        async for record in self._client.paginate(
            "incidents",
            select=_INCIDENT_FIELDS,
            filter_expr="statecode eq 0",  # active cases only
            page_size=self._page_size,
        ):
            ticket = _safe_label(record.get("ticketnumber") or record.get("incidentid", ""))
            account_name = _safe_label(
                record.get("_customerid_value@OData.Community.Display.V1.FormattedValue") or ""
            )
            owner = _safe_label(
                record.get("_ownerid_value@OData.Community.Display.V1.FormattedValue")
                or record.get("_ownerid_value")
                or "unassigned"
            )
            priority_code = record.get("prioritycode") or 2
            priority_label = _safe_label(
                record.get("prioritycode@OData.Community.Display.V1.FormattedValue")
                or _PRIORITY_LABELS.get(priority_code, "Normal")
            )

            if not ticket or ticket == "unknown":
                continue

            if account_name and account_name != "unknown":
                edges.append((f"Incident:{ticket}", "REPORTED_BY", f"Account:{account_name}", 1.0))
            edges.append((f"Incident:{ticket}", "ASSIGNED_TO", f"User:{owner}", 1.0))
            edges.append((f"Incident:{ticket}", "HAS_PRIORITY", f"Priority:{priority_label}", 1.0))

            # Boost salience for high-priority incidents
            if priority_code == 1:
                log.debug("[D365-SYNC] High-priority incident %s — will boost salience", ticket)

        written = await self._upsert_kg_edges_batch(edges)
        log.info("[D365-SYNC] sync_incidents namespace=%s edges=%d", self._ns, written)
        return {"entity": "incidents", "edges_written": written}

    # ------------------------------------------------------------------
    # Field Service entity sync methods
    # ------------------------------------------------------------------

    async def sync_work_orders(self) -> dict[str, Any]:
        """Fetch active Work Orders and write graph edges.

        Edges:
          Account → HAS_WORK_ORDER → WorkOrder
          WorkOrder → ASSIGNED_TO → User
          WorkOrder → HAS_STATUS → WOStatus
          WorkOrder → HAS_INCIDENT_TYPE → IncidentType  (if present)
        """
        edges: list[tuple[str, str, str, float]] = []
        async for record in self._client.paginate(
            "msdyn_workorders",
            select=_WORK_ORDER_FIELDS,
            # exclude Canceled (690970005) and Posted (690970004)
            filter_expr="msdyn_systemstatus ne 690970005 and msdyn_systemstatus ne 690970004",
            page_size=self._page_size,
        ):
            wo_name = _safe_label(record.get("msdyn_name") or record.get("msdyn_workorderid", ""))
            if not wo_name or wo_name == "unknown":
                continue

            account_name = _safe_label(
                record.get(
                    "_msdyn_serviceaccount_id_value@OData.Community.Display.V1.FormattedValue"
                )
                or ""
            )
            owner = _safe_label(
                record.get("_ownerid_value@OData.Community.Display.V1.FormattedValue")
                or record.get("_ownerid_value")
                or "unassigned"
            )
            status_code = record.get("msdyn_systemstatus")
            status_label = _safe_label(
                record.get("msdyn_systemstatus@OData.Community.Display.V1.FormattedValue")
                or _WO_STATUS_LABELS.get(status_code, "Unknown")
            )
            incident_type = _safe_label(
                record.get(
                    "_msdyn_primaryincidenttype_value@OData.Community.Display.V1.FormattedValue"
                )
                or ""
            )
            wo_type = _safe_label(
                record.get("_msdyn_workordertype_value@OData.Community.Display.V1.FormattedValue")
                or ""
            )

            if account_name and account_name != "unknown":
                edges.append(
                    (f"Account:{account_name}", "HAS_WORK_ORDER", f"WorkOrder:{wo_name}", 1.0)
                )
            edges.append((f"WorkOrder:{wo_name}", "ASSIGNED_TO", f"User:{owner}", 1.0))
            edges.append((f"WorkOrder:{wo_name}", "HAS_STATUS", f"WOStatus:{status_label}", 1.0))
            if incident_type and incident_type != "unknown":
                edges.append(
                    (
                        f"WorkOrder:{wo_name}",
                        "HAS_INCIDENT_TYPE",
                        f"IncidentType:{incident_type}",
                        1.0,
                    )
                )
            if wo_type and wo_type != "unknown":
                edges.append((f"WorkOrder:{wo_name}", "HAS_TYPE", f"WOType:{wo_type}", 1.0))

        written = await self._upsert_kg_edges_batch(edges)
        log.info("[D365-SYNC] sync_work_orders namespace=%s edges=%d", self._ns, written)
        return {"entity": "work_orders", "edges_written": written}

    async def sync_agreements(self) -> dict[str, Any]:
        """Fetch active Agreements and write HAS_AGREEMENT / agreement status edges.

        Edges:
          Account → HAS_AGREEMENT → Agreement
          Agreement → HAS_STATUS → AgreementStatus
        """
        edges: list[tuple[str, str, str, float]] = []
        async for record in self._client.paginate(
            "msdyn_agreements",
            select=_AGREEMENT_FIELDS,
            filter_expr="statecode eq 0",  # active only
            page_size=self._page_size,
        ):
            ag_name = _safe_label(record.get("msdyn_name") or record.get("msdyn_agreementid", ""))
            if not ag_name or ag_name == "unknown":
                continue

            account_name = _safe_label(
                record.get(
                    "_msdyn_serviceaccount_id_value@OData.Community.Display.V1.FormattedValue"
                )
                or ""
            )
            status = _safe_label(
                record.get("statecode@OData.Community.Display.V1.FormattedValue") or "Active"
            )

            if account_name and account_name != "unknown":
                edges.append(
                    (f"Account:{account_name}", "HAS_AGREEMENT", f"Agreement:{ag_name}", 1.0)
                )
            edges.append((f"Agreement:{ag_name}", "HAS_STATUS", f"AgreementStatus:{status}", 1.0))

        written = await self._upsert_kg_edges_batch(edges)
        log.info("[D365-SYNC] sync_agreements namespace=%s edges=%d", self._ns, written)
        return {"entity": "agreements", "edges_written": written}

    async def sync_customer_assets(self) -> dict[str, Any]:
        """Fetch Customer Assets and write HAS_ASSET / LOCATED_AT / IS_PRODUCT edges.

        Edges:
          Account → HAS_ASSET → CustomerAsset
          CustomerAsset → LOCATED_AT → FunctionalLocation  (if set)
          CustomerAsset → IS_PRODUCT → Product  (if set)
        """
        edges: list[tuple[str, str, str, float]] = []
        async for record in self._client.paginate(
            "msdyn_customerassets",
            select=_CUSTOMER_ASSET_FIELDS,
            page_size=self._page_size,
        ):
            asset_name = _safe_label(
                record.get("msdyn_name") or record.get("msdyn_customerassetid", "")
            )
            if not asset_name or asset_name == "unknown":
                continue

            account_name = _safe_label(
                record.get("_msdyn_account_id_value@OData.Community.Display.V1.FormattedValue")
                or ""
            )
            location = _safe_label(
                record.get(
                    "_msdyn_functionallocations_value@OData.Community.Display.V1.FormattedValue"
                )
                or ""
            )
            product = _safe_label(
                record.get("_msdyn_product_value@OData.Community.Display.V1.FormattedValue") or ""
            )

            if account_name and account_name != "unknown":
                edges.append(
                    (f"Account:{account_name}", "HAS_ASSET", f"CustomerAsset:{asset_name}", 1.0)
                )
            if location and location != "unknown":
                edges.append(
                    (
                        f"CustomerAsset:{asset_name}",
                        "LOCATED_AT",
                        f"FunctionalLocation:{location}",
                        1.0,
                    )
                )
            if product and product != "unknown":
                edges.append(
                    (f"CustomerAsset:{asset_name}", "IS_PRODUCT", f"Product:{product}", 1.0)
                )

        written = await self._upsert_kg_edges_batch(edges)
        log.info("[D365-SYNC] sync_customer_assets namespace=%s edges=%d", self._ns, written)
        return {"entity": "customer_assets", "edges_written": written}

    async def sync_functional_locations(self) -> dict[str, Any]:
        """Fetch Functional Locations and write hierarchy / account membership edges.

        Edges:
          FunctionalLocation → CHILD_OF → FunctionalLocation  (parent-child tree)
          Account → HAS_LOCATION → FunctionalLocation  (if account linked)
        """
        edges: list[tuple[str, str, str, float]] = []
        async for record in self._client.paginate(
            "msdyn_functionallocations",
            select=_FUNCTIONAL_LOCATION_FIELDS,
            page_size=self._page_size,
        ):
            loc_name = _safe_label(
                record.get("msdyn_name") or record.get("msdyn_functionallocationid", "")
            )
            if not loc_name or loc_name == "unknown":
                continue

            parent = _safe_label(
                record.get(
                    "_msdyn_parentfunctionallocation_value@OData.Community.Display.V1.FormattedValue"
                )
                or ""
            )
            account_name = _safe_label(
                record.get("_msdyn_account_id_value@OData.Community.Display.V1.FormattedValue")
                or ""
            )

            if parent and parent != "unknown":
                edges.append(
                    (
                        f"FunctionalLocation:{loc_name}",
                        "CHILD_OF",
                        f"FunctionalLocation:{parent}",
                        1.0,
                    )
                )
            if account_name and account_name != "unknown":
                edges.append(
                    (
                        f"Account:{account_name}",
                        "HAS_LOCATION",
                        f"FunctionalLocation:{loc_name}",
                        1.0,
                    )
                )

        written = await self._upsert_kg_edges_batch(edges)
        log.info("[D365-SYNC] sync_functional_locations namespace=%s edges=%d", self._ns, written)
        return {"entity": "functional_locations", "edges_written": written}

    async def sync_knowledge_articles(self) -> dict[str, Any]:
        """Fetch published Knowledge Articles and upsert as kg_nodes.

        Only published, latest-version articles are synced.
        Node label: ``KnowledgeArticle:{title}``
        The full text content is intentionally NOT fetched here — the Semantic Track
        (ingestion.py) should be used to embed article body text.
        """
        count = 0
        async for record in self._client.paginate(
            "knowledgearticles",
            select=_KNOWLEDGE_ARTICLE_FIELDS,
            # published (statecode=3) and latest version
            filter_expr="statecode eq 3 and islatestversion eq true",
            page_size=self._page_size,
        ):
            title = _safe_label(record.get("title") or record.get("knowledgearticleid", ""))
            if not title or title == "unknown":
                continue

            await self._upsert_kg_node(
                f"KnowledgeArticle:{title}",
                "D365_KnowledgeArticle",
                {
                    "article_id": record.get("knowledgearticleid"),
                    "description": (record.get("description") or "")[:500],
                    "keywords": record.get("keywords") or "",
                },
            )
            count += 1

        log.info("[D365-SYNC] sync_knowledge_articles namespace=%s count=%d", self._ns, count)
        return {"entity": "knowledge_articles", "upserted": count}

    async def run_full_sync(
        self,
        entity_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Orchestrate all sync steps and return aggregated stats.

        Parameters
        ----------
        entity_types:
            Optional subset to sync (e.g. ``["accounts", "contacts"]``).
            When *None* all four entity types are synced.
        """
        all_types = {
            "accounts",
            "contacts",
            "opportunities",
            "incidents",
            "work_orders",
            "agreements",
            "customer_assets",
            "functional_locations",
            "knowledge_articles",
        }
        requested = set(entity_types) if entity_types else all_types

        # Core CRM — run first so that Account nodes exist before field service edges
        results: list[dict[str, Any]] = []
        if "accounts" in requested:
            results.append(await self.sync_accounts())
        if "contacts" in requested:
            results.append(await self.sync_contacts())
        if "opportunities" in requested:
            results.append(await self.sync_opportunities())
        if "incidents" in requested:
            results.append(await self.sync_incidents())

        # Field Service — order: locations before assets (assets reference locations)
        if "functional_locations" in requested:
            results.append(await self.sync_functional_locations())
        if "work_orders" in requested:
            results.append(await self.sync_work_orders())
        if "agreements" in requested:
            results.append(await self.sync_agreements())
        if "customer_assets" in requested:
            results.append(await self.sync_customer_assets())

        # Knowledge base
        if "knowledge_articles" in requested:
            results.append(await self.sync_knowledge_articles())

        total_edges = sum(r.get("edges_written", 0) + r.get("upserted", 0) for r in results)
        return {
            "namespace_id": str(self._ns),
            "entity_results": results,
            "total_records": total_edges,
        }

    # ------------------------------------------------------------------
    # Internal DB helpers
    # ------------------------------------------------------------------

    async def _upsert_kg_node(
        self,
        label: str,
        entity_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Upsert a single kg_node row (no-op if already present)."""
        import json as _json

        await self._conn.execute(
            """
            INSERT INTO kg_nodes (label, entity_type, namespace_id, metadata)
            VALUES ($1, $2, $3::uuid, $4::jsonb)
            ON CONFLICT (label, namespace_id) DO UPDATE
                SET entity_type = EXCLUDED.entity_type,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
            """,
            label,
            entity_type,
            str(self._ns),
            _json.dumps(metadata or {}),
        )

    async def _upsert_kg_edges_batch(
        self,
        edges: list[tuple[str, str, str, float]],
    ) -> int:
        """
        Batch-upsert ``kg_edges`` rows using UNNEST for efficiency.

        Each tuple is ``(subject_label, predicate, object_label, confidence)``.
        Returns the number of rows affected.
        """
        if not edges:
            return 0

        subjects = [e[0] for e in edges]
        predicates = [e[1] for e in edges]
        objects = [e[2] for e in edges]
        confidences = [e[3] for e in edges]

        result = await self._conn.execute(
            """
            INSERT INTO kg_edges (subject_label, predicate, object_label, confidence, namespace_id)
            SELECT unnest($1::text[]),
                   unnest($2::text[]),
                   unnest($3::text[]),
                   unnest($4::float[]),
                   $5::uuid
            ON CONFLICT (subject_label, predicate, object_label, namespace_id) DO UPDATE
                SET confidence = EXCLUDED.confidence,
                    updated_at = NOW()
            """,
            subjects,
            predicates,
            objects,
            confidences,
            str(self._ns),
        )
        # asyncpg returns "INSERT 0 N" as a string
        try:
            return int(result.split()[-1])
        except (IndexError, ValueError):
            return len(edges)
