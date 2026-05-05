"""
trimcp.providers.factory
~~~~~~~~~~~~~~~~~~~~~~~~~
Resolves and instantiates an ``LLMProvider`` from either namespace metadata
or global environment configuration.

Resolution order
----------------
1. ``namespace_metadata["consolidation"]["llm_provider"]``   (per-namespace)
2. ``namespace_metadata["consolidation"]["llm_model"]``      (per-namespace)
3. ``namespace_metadata["consolidation"]["llm_credentials"]`` (per-namespace)
4. ``cfg.TRIMCP_LLM_PROVIDER``                               (global default, [D2])

Credential references (per D3 — BYO keys, no shared platform key)
------------------------------------------------------------------
Credential strings follow the pattern:
  ``ref:env/<ENV_VAR_NAME>``  — read from the named environment variable
  ``ref:vault/<path>``        — reserved for Phase 3 Vault integration (not yet implemented)
  ``<literal>``               — used as-is (only in development; warn in prod)

Provider labels
---------------
  ``local-cognitive-model``   — LocalCognitiveProvider (default [D2])
  ``openai``                  — OpenAICompatProvider (OpenAI)
  ``azure_openai``            — OpenAICompatProvider (Azure)
  ``deepseek``                — OpenAICompatProvider (DeepSeek)
  ``moonshot_kimi``           — OpenAICompatProvider (Moonshot Kimi)
  ``openai_compatible``       — OpenAICompatProvider (arbitrary endpoint)
  ``anthropic``               — AnthropicProvider
  ``google_gemini``           — GoogleGeminiProvider
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from trimcp.providers.base import LLMProvider, LLMProviderError

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def get_provider(namespace_metadata: Optional[Dict[str, Any]] = None) -> LLMProvider:
    """Return the correct ``LLMProvider`` for a namespace / global config.

    Parameters
    ----------
    namespace_metadata:
        The ``metadata`` JSONB column value from the ``namespaces`` table.
        May be ``None`` (uses global defaults).

    Raises
    ------
    LLMProviderError
        If the resolved provider label is unknown or required credentials
        are missing.
    """
    consolidation_cfg = (namespace_metadata or {}).get("consolidation", {})

    provider_label = (
        consolidation_cfg.get("llm_provider")
        or _global_provider_label()
    )
    model          = consolidation_cfg.get("llm_model") or None
    cred_ref       = consolidation_cfg.get("llm_credentials") or None

    log.debug("Resolving LLM provider: label=%r model=%r", provider_label, model)
    return _build_provider(provider_label, model=model, cred_ref=cred_ref)


# ---------------------------------------------------------------------------
# Internal builder
# ---------------------------------------------------------------------------

def _build_provider(
    label: str,
    *,
    model: Optional[str],
    cred_ref: Optional[str],
) -> LLMProvider:
    # Deferred imports to avoid loading unused heavy dependencies.
    from trimcp.providers.local_cognitive  import LocalCognitiveProvider
    from trimcp.providers.openai_compat    import OpenAICompatProvider
    from trimcp.providers.anthropic_provider import AnthropicProvider
    from trimcp.providers.google_gemini    import GoogleGeminiProvider
    from trimcp.config import cfg

    if label == "local-cognitive-model":
        base_url = cfg.TRIMCP_COGNITIVE_BASE_URL or "http://localhost:11435"
        return LocalCognitiveProvider(
            base_url=base_url,
            model=model or "local-cognitive-model",
        )

    if label == "anthropic":
        api_key = _resolve_credential(
            cred_ref, env_fallback="TRIMCP_ANTHROPIC_API_KEY"
        )
        return AnthropicProvider(
            api_key=api_key,
            model=model or "claude-opus-4-6",
        )

    if label == "openai":
        api_key = _resolve_credential(
            cred_ref, env_fallback="TRIMCP_OPENAI_API_KEY"
        )
        return OpenAICompatProvider(
            base_url="https://api.openai.com/v1",
            api_key=api_key,
            model=model or "gpt-5",
            provider_name="openai",
        )

    if label == "azure_openai":
        api_key  = _resolve_credential(
            cred_ref, env_fallback="TRIMCP_AZURE_OPENAI_API_KEY"
        )
        endpoint = os.getenv("TRIMCP_AZURE_OPENAI_ENDPOINT", "")
        if not endpoint:
            raise LLMProviderError(
                "azure_openai provider requires TRIMCP_AZURE_OPENAI_ENDPOINT",
                provider=f"azure_openai/{model}",
            )
        deployment = os.getenv("TRIMCP_AZURE_OPENAI_DEPLOYMENT", model or "gpt-5")
        return OpenAICompatProvider(
            base_url=f"{endpoint.rstrip('/')}/openai/deployments/{deployment}",
            api_key=api_key,
            model=deployment,
            provider_name="azure_openai",
            is_azure=True,
        )

    if label == "deepseek":
        api_key = _resolve_credential(
            cred_ref, env_fallback="TRIMCP_DEEPSEEK_API_KEY"
        )
        return OpenAICompatProvider(
            base_url="https://api.deepseek.com/v1",
            api_key=api_key,
            model=model or "deepseek-v4",
            provider_name="deepseek",
        )

    if label == "moonshot_kimi":
        api_key = _resolve_credential(
            cred_ref, env_fallback="TRIMCP_MOONSHOT_API_KEY"
        )
        return OpenAICompatProvider(
            base_url="https://api.moonshot.cn/v1",
            api_key=api_key,
            model=model or "kimi-2.6",
            provider_name="moonshot_kimi",
        )

    if label == "google_gemini":
        api_key = _resolve_credential(
            cred_ref, env_fallback="TRIMCP_GEMINI_API_KEY"
        )
        return GoogleGeminiProvider(
            api_key=api_key,
            model=model or "gemini-2.0-flash",
        )

    if label == "openai_compatible":
        api_key  = _resolve_credential(
            cred_ref, env_fallback="TRIMCP_OPENAI_COMPAT_API_KEY"
        )
        base_url = os.getenv("TRIMCP_OPENAI_COMPAT_BASE_URL", "")
        if not base_url:
            raise LLMProviderError(
                "openai_compatible provider requires TRIMCP_OPENAI_COMPAT_BASE_URL",
                provider="openai_compatible",
            )
        compat_model = (
            model
            or os.getenv("TRIMCP_OPENAI_COMPAT_MODEL")
            or "default"
        )
        return OpenAICompatProvider(
            base_url=base_url,
            api_key=api_key,
            model=compat_model,
            provider_name="openai_compatible",
        )

    raise LLMProviderError(
        f"Unknown LLM provider label: {label!r}.  "
        "Valid values: local-cognitive-model, openai, azure_openai, deepseek, "
        "moonshot_kimi, google_gemini, anthropic, openai_compatible",
        provider=label,
    )


# ---------------------------------------------------------------------------
# Credential resolution helpers
# ---------------------------------------------------------------------------

def _resolve_credential(cred_ref: Optional[str], *, env_fallback: str) -> str:
    """Resolve a credential string to a plain API key.

    Supports:
      * ``None`` / empty → fall back to *env_fallback* environment variable
      * ``"ref:env/<ENV_VAR>"`` → read the named env var
      * ``"ref:vault/<path>"`` → not yet implemented; raises
      * Anything else → treat as a literal key (logs a warning)
    """
    if not cred_ref:
        value = os.getenv(env_fallback, "")
        if not value:
            log.warning(
                "LLM provider credential not set.  "
                "Set the %s environment variable.",
                env_fallback,
            )
        return value

    if cred_ref.startswith("ref:env/"):
        var_name = cred_ref[len("ref:env/"):]
        value    = os.getenv(var_name, "")
        if not value:
            log.warning("Credential reference %r resolved to empty string.", cred_ref)
        return value

    if cred_ref.startswith("ref:vault/"):
        raise LLMProviderError(
            f"Vault credential references ({cred_ref!r}) are not yet implemented. "
            "Use ref:env/ for now.",
            provider="factory",
        )

    # Literal — warn in case it ends up in logs.
    log.warning(
        "LLM credential is a literal string, not a ref:env/ reference.  "
        "Avoid storing keys directly in namespace metadata.",
    )
    return cred_ref


def _global_provider_label() -> str:
    from trimcp.config import cfg
    return cfg.TRIMCP_LLM_PROVIDER or "local-cognitive-model"
