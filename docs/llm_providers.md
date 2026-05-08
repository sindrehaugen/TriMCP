# LLM Providers and Structured Output

TriMCP is architected to be Large Language Model (LLM) provider-agnostic. It supports a diverse range of backends for embeddings, semantic search, memory consolidation, and reasoning, with mandatory schema validation for all outputs.

## Supported Providers

TriMCP currently supports the following provider labels:

| Label | Engine | Typical Use Case |
| :--- | :--- | :--- |
| `google_gemini` | Google Gemini API | Primary reasoning and consolidation. |
| `anthropic` | Anthropic Claude API | High-accuracy research and extraction. |
| `openai` | OpenAI API | General purpose reasoning. |
| `azure_openai` | Microsoft Azure | Enterprise-grade managed endpoints. |
| `deepseek` | DeepSeek API | Cost-sensitive high-performance tasks. |
| `local-cognitive-model` | llama.cpp / OpenVINO | Airgapped and edge deployments. |
| `openai_compatible` | Custom Endpoints | Self-hosted vLLM or Ollama instances. |

## Structured Output Strategy (Pydantic V2)

A core mandate of TriMCP is that LLMs must never return "loose" text for cognitive operations. Every response that modifies the system state (e.g., creating a Knowledge Graph edge) is validated against a Pydantic V2 model.

### Validation Signal Flow

```mermaid
sequenceDiagram
    participant Engine as TriMCP Core
    participant Factory as ProviderFactory
    participant Provider as LLM Provider (e.g., Gemini)
    participant LLM as External API

    Engine->>Factory: get_provider(config)
    Factory-->>Engine: ProviderInstance
    Engine->>Provider: complete(messages, response_model=ConsolidatedAbstraction)
    Provider->>LLM: POST /chat/completions (with schema instructions)
    LLM-->>Provider: Raw JSON Payload
    
    alt Strict Schema Support (OpenAI/Azure)
        Provider->>LLM: Use response_format: json_schema
    else System Prompt Fallback
        Provider->>Provider: Inject Schema into System Message
    end

    Provider->>Provider: Pydantic model_validate_json()
    
    alt Validation Pass
        Provider-->>Engine: Validated Python Object
    else Validation Fail
        Provider-->>Engine: raise LLMValidationError
    end
```

## Provider Configuration

Providers are resolved in the following order:
1.  **Namespace Metadata**: `metadata["consolidation"]["llm_provider"]` allows for per-tenant model selection.
2.  **Global Default**: `TRIMCP_LLM_PROVIDER` in the environment configuration.

### Credential Resolution (BYO Keys)
TriMCP follows a "Bring Your Own Key" (BYO) model. Credentials can be provided as:
-   **Environment Variables**: `TRIMCP_GEMINI_API_KEY`, etc.
-   **References**: `ref:env/MY_CUSTOM_KEY` in namespace metadata.
-   **Vault (Phase 3)**: Secure retrieval from a secret manager (planned).

## Local Embedding Backend

For high-security or low-latency requirements, TriMCP can run embedding models locally using **Sentence-Transformers** or **Intel OpenVINO**, avoiding any external API calls for the semantic search hot path.
