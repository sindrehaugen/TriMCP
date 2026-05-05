"""
TriMCP Phase 0.1 — Pydantic V2 data models.

This is the single source of truth for all request/response shapes and internal
record types for Phase 0.1 (Multi-Tenant Namespacing + Postgres RLS).

Decisions encoded:
  [D4]  agent_id: free-text, stripped whitespace, max 128 chars, safe-ID pattern.
        Default 'default'. No FK, no agents table in v1.
  [D5]  temporal_retention_days: int | None per namespace (90 day default; None = infinite).
  [D6]  llm_payload_retention_days: int | None (None = inherits D5; 0 = no caching).
  [D8]  valid_from: ALWAYS server-assigned (now()). Any user-supplied past timestamp is
        rejected at the boundary. This model enforces that: valid_from is not an input field.
  [D9]  assertion_type: Literal['fact','opinion','preference','observation'].
        Contradiction detection fires only on fact vs fact.

Do NOT add raw DB connection or pool logic here. This module is import-only.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Optional

from pydantic import (
    UUID4,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# ── Constants ─────────────────────────────────────────────────────────────────

# Namespace slugs: lowercase alphanumeric + hyphens, 2–64 chars,
# must start and end with alphanumeric.
_SAFE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,62}[a-z0-9]$")

# agent_id / legacy user_id / session_id: alphanumeric, hyphens, underscores, 1–128 chars.
_SAFE_ID_RE = re.compile(r"^[\w\-]{1,128}$")

_MAX_SUMMARY_LEN: int = 8_192
_MAX_PAYLOAD_LEN: int = 10 * 1024 * 1024   # 10 MB hard cap [GLOBAL CONSTRAINT]
_MAX_TOP_K: int = 100
_MAX_DEPTH: int = 3


# ── Shared helpers ────────────────────────────────────────────────────────────

def _validate_agent_id(v: str) -> str:
    """[D4] Strip whitespace, enforce max 128 chars and safe-ID charset."""
    v = v.strip()
    if not v:
        raise ValueError("agent_id must not be empty or whitespace-only")
    if len(v) > 128:
        raise ValueError("agent_id must be ≤ 128 characters")
    if not _SAFE_ID_RE.match(v):
        raise ValueError(
            "agent_id may only contain alphanumerics, hyphens, and underscores"
        )
    return v


# ── Enumerations ──────────────────────────────────────────────────────────────

class AssertionType(str, Enum):
    """[D9] Fact-typing used for contradiction detection and memory classification."""
    fact = "fact"
    opinion = "opinion"
    preference = "preference"
    observation = "observation"


class MemoryType(str, Enum):
    """Classification of memory entries stored in the memories table."""
    episodic = "episodic"
    consolidated = "consolidated"
    decision = "decision"
    code_chunk = "code_chunk"


class PIIPolicy(str, Enum):
    """[Phase 0.3] Per-namespace PII handling policy."""
    redact = "redact"
    pseudonymise = "pseudonymise"
    reject = "reject"
    flag = "flag"


class SigningKeyStatus(str, Enum):
    """[Phase 0.2] Signing key lifecycle. Retired keys retained for historical verify."""
    active = "active"
    retired = "retired"


class ManageNamespaceCommand(str, Enum):
    """Commands accepted by the manage_namespace MCP admin tool."""
    create = "create"
    list = "list"
    grant = "grant"
    revoke = "revoke"
    update_metadata = "update_metadata"


# ── Namespace sub-models ──────────────────────────────────────────────────────

class NamespaceCognitiveConfig(BaseModel):
    """
    Cognitive settings nested inside NamespaceMetadata.
    Consumed in Phase 1.1 (Ebbinghaus Decay + Salience).
    """
    model_config = ConfigDict(extra="forbid")

    half_life_days: float = Field(default=30.0, gt=0.0)
    reinforcement_delta: float = Field(default=0.05, gt=0.0, le=1.0)
    alpha: float = Field(default=0.7, ge=0.0, le=1.0)

class NamespacePIIConfig(BaseModel):
    """
    PII policy block nested inside NamespaceMetadata.
    Consumed in Phase 0.3 (PII Detection and Auto-Redaction).
    Declared here so namespace creation can pre-configure it.
    """
    model_config = ConfigDict(extra="forbid")

    entity_types: list[str] = Field(
        default_factory=list,
        description="Presidio entity types to detect (e.g. PERSON, EMAIL, PHONE)",
    )
    policy: PIIPolicy = Field(
        default=PIIPolicy.redact,
        description="Action when PII is found",
    )
    reversible: bool = Field(
        default=False,
        description="If True and policy=pseudonymise, store encrypted original",
    )
    allowlist: list[str] = Field(
        default_factory=list,
        description="Entity strings explicitly exempted from redaction",
    )


class PIIEntity(BaseModel):
    """[Phase 0.3] Detected PII entity."""
    model_config = ConfigDict(extra="forbid")
    
    start: int
    end: int
    entity_type: str
    value: str
    score: float = 1.0


class PIIProcessResult(BaseModel):
    """[Phase 0.3] Result of the PII redaction pipeline."""
    model_config = ConfigDict(extra="forbid")
    
    sanitized_text: str
    redacted: bool
    entities_found: list[str]
    vault_entries: list[dict] = Field(default_factory=list)


class NamespaceConsolidationConfig(BaseModel):
    """
    Cognitive consolidation settings nested inside NamespaceMetadata.
    Consumed in Phase 1 (Cognitive Layer). Declared here to allow pre-configuration.
    """
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    # Credential reference: 'ref:env/TRIMCP_NS_<slug>_<PROVIDER>_KEY' or 'ref:vault/...' [D3]
    llm_credentials: Optional[str] = None
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    decay_sources: bool = Field(
        default=False,
        description="Mark source memories as lower-salience after consolidation",
    )


class NamespaceForkConfig(BaseModel):
    """
    Configuration for a forked namespace (Phase 2.3).
    """
    model_config = ConfigDict(extra="forbid")

    forked_from_as_of: datetime = Field(
        description="The exact UTC timestamp at which the parent namespace was forked"
    )


class NamespaceMetadata(BaseModel):
    """
    Typed representation of the namespaces.metadata JSONB column.

    extra='forbid' prevents unrecognised keys from silently entering the DB.
    Unknown future fields must be added here first (makes schema evolution explicit).
    """
    model_config = ConfigDict(extra="forbid")

    # [D5] Memory temporal retention
    temporal_retention_days: Optional[int] = Field(
        default=90,
        ge=0,
        description="Days to retain memories. None = infinite. 0 = purge immediately.",
    )
    # [D6] LLM response payload retention (MinIO)
    llm_payload_retention_days: Optional[int] = Field(
        default=None,
        ge=0,
        description=(
            "Days to retain LLM response payloads in MinIO. "
            "None = inherit temporal_retention_days. 0 = no caching, re-execute only."
        ),
    )
    consolidation: NamespaceConsolidationConfig = Field(
        default_factory=NamespaceConsolidationConfig
    )
    pii: NamespacePIIConfig = Field(default_factory=NamespacePIIConfig)
    cognitive: NamespaceCognitiveConfig = Field(default_factory=NamespaceCognitiveConfig)
    fork_config: Optional[NamespaceForkConfig] = Field(
        default=None,
        description="[Phase 2.3] Configuration if this namespace is a fork of another."
    )


# ── Namespace CRUD models ─────────────────────────────────────────────────────

class NamespaceCreate(BaseModel):
    """Input payload for manage_namespace(command='create')."""
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(
        min_length=2,
        max_length=64,
        description=(
            "URL-safe lowercase identifier. 2–64 chars. "
            "Alphanumeric + hyphens. Must start and end with alphanumeric."
        ),
    )
    parent_id: Optional[UUID4] = Field(
        default=None,
        description="Parent namespace UUID for hierarchy. None = root namespace.",
    )
    metadata: NamespaceMetadata = Field(default_factory=NamespaceMetadata)

    @field_validator("slug")
    @classmethod
    def _slug_format(cls, v: str) -> str:
        v = v.lower().strip()
        if not _SAFE_SLUG_RE.match(v):
            raise ValueError(
                "slug must be 2–64 chars, lowercase alphanumeric and hyphens, "
                "starting and ending with an alphanumeric character"
            )
        return v


class NamespaceRecord(BaseModel):
    """
    Full namespace row as returned from the database.
    extra='ignore' tolerates any additional DB columns without breaking.
    """
    model_config = ConfigDict(extra="ignore")

    id: UUID4
    slug: str
    parent_id: Optional[UUID4] = None
    created_at: datetime
    metadata: NamespaceMetadata


# ── Memory models ─────────────────────────────────────────────────────────────

class StoreMemoryRequest(BaseModel):
    """
    Input for the store_memory MCP tool (Phase 0.1).

    Decisions enforced:
      [D4]  agent_id stripped, max 128 chars, defaults to 'default'.
      [D8]  valid_from is NOT an input field — always assigned server-side (now()).
            Any attempt to supply it is rejected by extra='forbid'.
      [D9]  assertion_type defaults to AssertionType.fact. Classifier may override
            during the ingest pipeline (trimcp/pii.py::infer_assertion_type).
    """
    model_config = ConfigDict(extra="forbid")

    namespace_id: UUID4 = Field(description="Target namespace for this memory")
    agent_id: str = Field(
        default="default",
        description="[D4] Agent identifier. Free-text, max 128 chars.",
    )

    # Content
    content: str = Field(
        min_length=1,
        description="Primary text to store, embed, and graph-extract",
    )
    summary: str = Field(
        default="",
        max_length=_MAX_SUMMARY_LEN,
        description=(
            "Short synopsis used for FTS index. "
            "Auto-derived from content (first 8192 chars) if left blank."
        ),
    )
    heavy_payload: str = Field(
        default="",
        description=(
            "Full raw content (transcript, document, …). "
            "Stored in MongoDB, not embedded. "
            "Defaults to content when not supplied."
        ),
    )

    # Classification
    memory_type: MemoryType = Field(default=MemoryType.episodic)
    assertion_type: AssertionType = Field(
        default=AssertionType.fact,
        description="[D9] Classifier may override this during ingest.",
    )

    # Optional enrichment
    metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Arbitrary caller metadata stored in MongoDB alongside the payload",
    )
    derived_from: Optional[list[UUID4]] = Field(
        default=None,
        description="Source memory IDs — required when memory_type='consolidated'",
    )
    check_contradictions: bool = Field(
        default=False,
        description="Phase 1.3: If true, runs sync contradiction detection and returns result."
    )

    @field_validator("agent_id")
    @classmethod
    def _validate_agent_id(cls, v: str) -> str:
        return _validate_agent_id(v)

    @field_validator("heavy_payload")
    @classmethod
    def _payload_size(cls, v: str) -> str:
        if len(v.encode("utf-8")) > _MAX_PAYLOAD_LEN:
            raise ValueError(
                f"heavy_payload exceeds {_MAX_PAYLOAD_LEN // 1_048_576} MB limit"
            )
        return v

    @model_validator(mode="after")
    def _fill_defaults(self) -> "StoreMemoryRequest":
        """Derive summary and heavy_payload from content when not supplied."""
        if not self.summary:
            self.summary = self.content[:_MAX_SUMMARY_LEN]
        if not self.heavy_payload:
            self.heavy_payload = self.content
        return self

    @model_validator(mode="after")
    def _consolidated_requires_derived_from(self) -> "StoreMemoryRequest":
        if (
            self.memory_type == MemoryType.consolidated
            and not self.derived_from
        ):
            raise ValueError(
                "derived_from must list source memory IDs when memory_type='consolidated'"
            )
        return self


class MemoryRecord(BaseModel):
    """
    In-memory representation of a single memories table row.

    This model is produced by the orchestrator after a successful write,
    NOT constructed from raw user input.
    The `valid_from` field is always server-assigned and present here for
    downstream read paths (verify, search results, etc.).
    """
    model_config = ConfigDict(extra="ignore")

    id: UUID4
    namespace_id: UUID4
    agent_id: str
    created_at: datetime
    memory_type: MemoryType
    assertion_type: AssertionType
    payload_ref: str = Field(description="MongoDB document _id (string form)")
    embedding_model_id: Optional[UUID4] = None
    derived_from: Optional[list[UUID4]] = None
    valid_from: datetime = Field(description="[D8] Server-assigned; never user-supplied")
    valid_to: Optional[datetime] = Field(
        default=None,
        description="NULL = current row (latest version)",
    )
    signature: bytes = Field(description="[Phase 0.2] HMAC-SHA256 over JCS payload")
    signature_key_id: str = Field(description="[Phase 0.2] ID of the signing key used")
    pii_redacted: bool = False


class MemorySalienceRecord(BaseModel):
    """Represents a row in the memory_salience table."""
    model_config = ConfigDict(extra="ignore")

    memory_id: UUID4
    agent_id: str
    namespace_id: UUID4
    salience_score: float = Field(default=1.0, ge=0.0, le=1.0)
    access_count: int = Field(default=0, ge=0)
    updated_at: datetime
    created_at: datetime


# ── Knowledge Graph models ────────────────────────────────────────────────────

class KGNode(BaseModel):
    """A node (entity) in the knowledge graph."""
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    entity_type: str = Field(default="UNKNOWN")
    source_text: str
    payload_ref: Optional[str] = None

    @field_validator("label")
    @classmethod
    def _strip_label(cls, v: str) -> str:
        return v.strip()


class KGEdge(BaseModel):
    """An edge (relation) in the knowledge graph."""
    model_config = ConfigDict(extra="forbid")

    subject_label: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object_label: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    payload_ref: Optional[str] = None
    metadata: dict = Field(default_factory=dict)

    @field_validator("subject_label", "predicate", "object_label")
    @classmethod
    def _strip_labels(cls, v: str) -> str:
        return v.strip()


# ── Search / retrieval models ─────────────────────────────────────────────────

class SemanticSearchRequest(BaseModel):
    """Input for the semantic_search MCP tool."""
    model_config = ConfigDict(extra="forbid")

    namespace_id: UUID4
    agent_id: Optional[str] = Field(
        default=None,
        description="Filter by agent. None = all agents in namespace.",
    )
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=_MAX_TOP_K)
    as_of: Optional[datetime] = Field(
        default=None,
        description="Point-in-time recall: return memories valid at this timestamp",
    )

    @field_validator("agent_id")
    @classmethod
    def _validate_agent_id(cls, v: Optional[str]) -> Optional[str]:
        return _validate_agent_id(v) if v is not None else None


class SemanticSearchResult(BaseModel):
    """A single hit returned from a semantic search."""
    model_config = ConfigDict(extra="ignore")

    memory_id: UUID4
    namespace_id: UUID4
    agent_id: str
    score: float = Field(ge=0.0)
    payload_ref: str
    assertion_type: AssertionType
    memory_type: MemoryType
    valid_from: datetime
    pii_redacted: bool = False
    content_preview: Optional[str] = Field(
        default=None,
        description="Populated by the orchestrator from MongoDB; may be None if redacted",
    )


class GraphSearchRequest(BaseModel):
    """Input for the graph_search MCP tool."""
    model_config = ConfigDict(extra="forbid")

    namespace_id: UUID4
    agent_id: Optional[str] = Field(
        default=None,
        description="Filter graph traversal by agent. None = all agents in namespace.",
    )
    query: str = Field(min_length=1)
    max_depth: int = Field(default=2, ge=1, le=_MAX_DEPTH)
    as_of: Optional[datetime] = None

    @field_validator("agent_id")
    @classmethod
    def _validate_agent_id(cls, v: Optional[str]) -> Optional[str]:
        return _validate_agent_id(v) if v is not None else None


class GetRecentContextRequest(BaseModel):
    """Input for the get_recent_context MCP tool."""
    model_config = ConfigDict(extra="forbid")

    namespace_id: UUID4
    agent_id: Optional[str] = Field(
        default=None,
        description="Filter by agent. None = all agents in namespace.",
    )
    limit: int = Field(default=10, ge=1, le=_MAX_TOP_K)
    as_of: Optional[datetime] = None

    @field_validator("agent_id")
    @classmethod
    def _validate_agent_id(cls, v: Optional[str]) -> Optional[str]:
        return _validate_agent_id(v) if v is not None else None


# ── Namespace management ──────────────────────────────────────────────────────

class ManageNamespaceRequest(BaseModel):
    """
    Input for the manage_namespace MCP admin tool.

    The command field acts as a discriminator. Required sub-fields are enforced
    by the cross-field validator below.
    """
    model_config = ConfigDict(extra="forbid")

    command: ManageNamespaceCommand

    # Contextual fields — not all are used by every command.
    namespace_id: Optional[UUID4] = Field(
        default=None,
        description="Target namespace for grant/revoke/update_metadata",
    )
    create: Optional[NamespaceCreate] = Field(
        default=None,
        description="Required when command='create'",
    )
    metadata_patch: Optional[dict[str, Any]] = Field(
        default=None,
        description="Partial metadata keys to update; merged server-side",
    )
    grantee_namespace_id: Optional[UUID4] = Field(
        default=None,
        description="Child namespace that gains/loses read access in grant/revoke",
    )

    @model_validator(mode="after")
    def _command_constraints(self) -> "ManageNamespaceRequest":
        cmd = self.command
        if cmd == ManageNamespaceCommand.create and self.create is None:
            raise ValueError("'create' payload is required when command='create'")
        if cmd == ManageNamespaceCommand.update_metadata:
            if self.namespace_id is None:
                raise ValueError("namespace_id required for command='update_metadata'")
            if self.metadata_patch is None:
                raise ValueError("metadata_patch required for command='update_metadata'")
        if cmd in (ManageNamespaceCommand.grant, ManageNamespaceCommand.revoke):
            if self.namespace_id is None or self.grantee_namespace_id is None:
                raise ValueError(
                    "Both namespace_id and grantee_namespace_id are required "
                    "for command='grant' / 'revoke'"
                )
        return self


# ── Signing key (schema in Phase 0.1, signing logic in Phase 0.2) ────────────

class SigningKeyRecord(BaseModel):
    """
    Row from the signing_keys table.
    The encrypted_key (BYTEA) column is intentionally absent — never surfaced
    to application-layer models.
    """
    model_config = ConfigDict(extra="ignore")

    id: UUID4
    key_id: str = Field(min_length=1)
    status: SigningKeyStatus
    created_at: datetime
    retired_at: Optional[datetime] = Field(
        default=None,
        description="[D0.2] Set when key is retired. Never deleted.",
    )


# ── Instantiation tests ───────────────────────────────────────────────────────
# Run directly:  python -m trimcp.models
# The block below is NOT a test suite replacement; it validates that every
# model can be instantiated with valid data and rejects known-bad inputs.

if __name__ == "__main__":
    import sys

    _ns_id = uuid.uuid4()
    _mem_id = uuid.uuid4()
    _now = datetime.now(tz=timezone.utc)

    passed: list[str] = []
    failed: list[tuple[str, Exception]] = []

    def _ok(name: str) -> None:
        passed.append(name)
        print(f"  PASS  {name}")

    def _fail(name: str, exc: Exception) -> None:
        failed.append((name, exc))
        print(f"  FAIL  {name}: {exc}")

    def _expect_error(name: str, fn) -> None:
        try:
            fn()
            _fail(name, AssertionError("Expected ValidationError but none was raised"))
        except Exception:
            _ok(name)

    print("\n-- Phase 0.1 model instantiation tests --\n")

    # ── NamespaceMetadata ──
    try:
        m = NamespaceMetadata(temporal_retention_days=30)
        assert m.temporal_retention_days == 30
        assert m.consolidation.enabled is False
        _ok("NamespaceMetadata: valid construction")
    except Exception as e:
        _fail("NamespaceMetadata: valid construction", e)

    _expect_error(
        "NamespaceMetadata: extra field rejected",
        lambda: NamespaceMetadata(unknown_field="x"),
    )

    # ── NamespaceCreate ──
    try:
        nc = NamespaceCreate(slug="acme-corp", parent_id=None)
        assert nc.slug == "acme-corp"
        _ok("NamespaceCreate: valid slug")
    except Exception as e:
        _fail("NamespaceCreate: valid slug", e)

    try:
        nc_upper = NamespaceCreate(slug="ACME-Corp")
        assert nc_upper.slug == "acme-corp", f"Expected 'acme-corp', got {nc_upper.slug!r}"
        _ok("NamespaceCreate: uppercase slug normalised to lowercase")
    except Exception as e:
        _fail("NamespaceCreate: uppercase slug normalised to lowercase", e)
    _expect_error(
        "NamespaceCreate: slug starting with hyphen rejected",
        lambda: NamespaceCreate(slug="-bad"),
    )
    _expect_error(
        "NamespaceCreate: single-char slug rejected",
        lambda: NamespaceCreate(slug="a"),
    )

    # ── StoreMemoryRequest — happy path ──
    try:
        req = StoreMemoryRequest(
            namespace_id=_ns_id,
            content="User discussed multi-tenant architecture patterns.",
        )
        assert req.agent_id == "default"
        assert req.assertion_type == AssertionType.fact
        assert req.summary == req.content           # auto-derived
        assert req.heavy_payload == req.content     # auto-derived
        _ok("StoreMemoryRequest: defaults (agent_id, summary, heavy_payload)")
    except Exception as e:
        _fail("StoreMemoryRequest: defaults", e)

    try:
        req2 = StoreMemoryRequest(
            namespace_id=_ns_id,
            agent_id="  planner-bot  ",   # leading/trailing whitespace stripped
            content="Decision: use pgvector HNSW index.",
            memory_type=MemoryType.decision,
            assertion_type=AssertionType.fact,
        )
        assert req2.agent_id == "planner-bot"
        _ok("StoreMemoryRequest: agent_id whitespace stripped")
    except Exception as e:
        _fail("StoreMemoryRequest: agent_id whitespace stripped", e)

    # [D8] valid_from is not an input field
    _expect_error(
        "StoreMemoryRequest: [D8] valid_from rejected (extra='forbid')",
        lambda: StoreMemoryRequest(
            namespace_id=_ns_id,
            content="test",
            valid_from=_now,                # must be rejected
        ),
    )

    _expect_error(
        "StoreMemoryRequest: empty content rejected",
        lambda: StoreMemoryRequest(namespace_id=_ns_id, content=""),
    )

    _expect_error(
        "StoreMemoryRequest: agent_id with invalid chars rejected",
        lambda: StoreMemoryRequest(
            namespace_id=_ns_id,
            content="x",
            agent_id="bad agent!",
        ),
    )

    _expect_error(
        "StoreMemoryRequest: consolidated without derived_from rejected",
        lambda: StoreMemoryRequest(
            namespace_id=_ns_id,
            content="summary of three memories",
            memory_type=MemoryType.consolidated,
        ),
    )

    try:
        req3 = StoreMemoryRequest(
            namespace_id=_ns_id,
            content="summary",
            memory_type=MemoryType.consolidated,
            derived_from=[uuid.uuid4(), uuid.uuid4()],
        )
        _ok("StoreMemoryRequest: consolidated with derived_from accepted")
    except Exception as e:
        _fail("StoreMemoryRequest: consolidated with derived_from accepted", e)

    # ── SemanticSearchRequest ──
    try:
        sr = SemanticSearchRequest(namespace_id=_ns_id, query="HNSW indexes")
        assert sr.top_k == 5
        assert sr.agent_id is None
        _ok("SemanticSearchRequest: defaults")
    except Exception as e:
        _fail("SemanticSearchRequest: defaults", e)

    _expect_error(
        "SemanticSearchRequest: top_k=0 rejected",
        lambda: SemanticSearchRequest(namespace_id=_ns_id, query="x", top_k=0),
    )
    _expect_error(
        "SemanticSearchRequest: top_k=101 rejected",
        lambda: SemanticSearchRequest(namespace_id=_ns_id, query="x", top_k=101),
    )

    # ── GraphSearchRequest ──
    try:
        gr = GraphSearchRequest(namespace_id=_ns_id, query="architecture")
        assert gr.max_depth == 2
        _ok("GraphSearchRequest: defaults")
    except Exception as e:
        _fail("GraphSearchRequest: defaults", e)

    _expect_error(
        "GraphSearchRequest: max_depth=4 rejected",
        lambda: GraphSearchRequest(namespace_id=_ns_id, query="x", max_depth=4),
    )

    # ── ManageNamespaceRequest ──
    try:
        mr = ManageNamespaceRequest(
            command=ManageNamespaceCommand.create,
            create=NamespaceCreate(slug="test-ns"),
        )
        _ok("ManageNamespaceRequest: create command accepted")
    except Exception as e:
        _fail("ManageNamespaceRequest: create command accepted", e)

    _expect_error(
        "ManageNamespaceRequest: create without payload rejected",
        lambda: ManageNamespaceRequest(command=ManageNamespaceCommand.create),
    )

    _expect_error(
        "ManageNamespaceRequest: update_metadata without namespace_id rejected",
        lambda: ManageNamespaceRequest(
            command=ManageNamespaceCommand.update_metadata,
            metadata_patch={"temporal_retention_days": 30},
        ),
    )

    try:
        mr2 = ManageNamespaceRequest(
            command=ManageNamespaceCommand.update_metadata,
            namespace_id=_ns_id,
            metadata_patch={"temporal_retention_days": 60},
        )
        _ok("ManageNamespaceRequest: update_metadata accepted")
    except Exception as e:
        _fail("ManageNamespaceRequest: update_metadata accepted", e)

    # ── MemorySalienceRecord ──
    try:
        sal = MemorySalienceRecord(
            memory_id=_mem_id,
            agent_id="default",
            namespace_id=_ns_id,
            salience_score=0.85,
            access_count=3,
            updated_at=_now,
            created_at=_now,
        )
        assert 0.0 <= sal.salience_score <= 1.0
        _ok("MemorySalienceRecord: valid")
    except Exception as e:
        _fail("MemorySalienceRecord: valid", e)

    _expect_error(
        "MemorySalienceRecord: salience_score > 1.0 rejected",
        lambda: MemorySalienceRecord(
            memory_id=_mem_id,
            agent_id="default",
            namespace_id=_ns_id,
            salience_score=1.5,
            updated_at=_now,
            created_at=_now,
        ),
    )

    # ── SigningKeyRecord ──
    try:
        skr = SigningKeyRecord(
            id=uuid.uuid4(),
            key_id="key-2026-05-01",
            status=SigningKeyStatus.active,
            created_at=_now,
        )
        _ok("SigningKeyRecord: active key")
    except Exception as e:
        _fail("SigningKeyRecord: active key", e)

    # ── Summary ──
    print(f"\n-- Results: {len(passed)} passed, {len(failed)} failed --\n")
    if failed:
        for name, exc in failed:
            print(f"  FAILED: {name}\n    {exc}")
        sys.exit(1)
