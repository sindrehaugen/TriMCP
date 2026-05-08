# TriMCP Observability — VRAM Metrics (Item 49)

## Overview

The re-embedding background worker (`trimcp/re_embedder.py`) runs PyTorch/CUDA operations during embedding migrations. After fixing an OOM leak, we now actively monitor VRAM consumption via Prometheus gauges to detect memory pressure before it causes OOM kills.

## Metrics Exposed

| Metric Name | Type | Labels | Description |
|---|---|---|---|
| `trimcp_reembedder_vram_allocated_bytes` | Gauge | `worker_id` | Current VRAM allocated to PyTorch tensors (`torch.cuda.memory_allocated()`) |
| `trimcp_reembedder_vram_reserved_bytes` | Gauge | `worker_id` | Current VRAM reserved by the CUDA caching allocator (`torch.cuda.memory_reserved()`) |
| `trimcp_reembedder_vram_peak_bytes` | Gauge | `worker_id` | Peak VRAM allocated since last measurement reset (`torch.cuda.max_memory_allocated()`) |

## Measurement Cadence

Metrics are recorded after every embedding batch (memories and KG nodes) inside `_release_embedding_batch_memory()`. Peak is reset after each measurement via `torch.cuda.reset_peak_memory_stats()`, giving per-batch peak windows.

## Graceful Degradation

- **CPU-only**: When `torch.cuda.is_available()` returns `False`, `_record_vram_metrics()` returns immediately — no metrics emitted.
- **torch missing**: `ImportError` is caught silently; metrics are skipped.
- **prometheus_client missing**: The `_StubMetric` fallback in `observability.py` handles missing Prometheus — `.set()` is a no-op.

## Alert Thresholds (Recommended)

| Condition | Alert | Severity |
|---|---|---|
| `trimcp_reembedder_vram_allocated_bytes > 80% GPU total` | Re-embedder nearing OOM | Warning |
| `trimcp_reembedder_vram_peak_bytes > 90% GPU total` | High-water mark critical | Critical |
| `trimcp_reembedder_vram_reserved_bytes - trimcp_reembedder_vram_allocated_bytes > 2GB` | CUDA allocator fragmentation | Warning |

### Example Prometheus Alert Rule

```yaml
groups:
  - name: trimcp_vram
    rules:
      - alert: TrimcpReembedderHighVRAM
        expr: trimcp_reembedder_vram_allocated_bytes / 1024 / 1024 / 1024 > 0.8 * nvidia_gpu_memory_total_bytes
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Re-embedder VRAM usage > 80% of GPU total"
```

## Docker GPU Configuration

Both `docker-compose.yml` and `deploy/multiuser/docker-compose.yml` now include GPU resource reservations for the `worker` service:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

**Local testing with GPU:** `docker compose --profile gpu up worker`

For Docker Compose V2 with NVIDIA runtime, ensure `nvidia-container-toolkit` is installed and `/etc/docker/daemon.json` has:

```json
{
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  }
}
```

## Grafana Dashboard Panel

Add a timeseries panel with queries:

```
trimcp_reembedder_vram_allocated_bytes{worker_id=~"$worker"}
trimcp_reembedder_vram_reserved_bytes{worker_id=~"$worker"}
trimcp_reembedder_vram_peak_bytes{worker_id=~"$worker"}
```

Display in GiB: divide by `1024*1024*1024`.
