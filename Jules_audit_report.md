# Repository Code Integrity & Duplication Audit Report

## 1. Executive Analytics Summary
- **Total Source Files Analyzed:** 423
- **Total Syntax/Linting Anomalies:** 2540
- **Identified Duplication Redundancies:** 100
- **Highest-Risk Module Cluster:** nce/admin_handlers/fleet.py

## 2. Granular Syntax & Static Analysis Issues
### Module: `health_probe.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `20` | Warning | PY_TYPING | Missing return type hint for async function 'probe' | `async def probe():` |

---

### Module: `index_all.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `11` | Warning | PY_TYPING | Missing return type hint for function 'get_files_to_index' | `def get_files_to_index(root_dir="."):` |
| `11` | Warning | PY_TYPING | Missing type hint for argument 'root_dir' in function 'get_files_to_index' | `def get_files_to_index(root_dir="."):` |
| `36` | Warning | PY_TYPING | Missing return type hint for async function 'index_repo' | `async def index_repo(namespace_id: str = "default"):` |
| `51` | Warning | PY_TYPING | Missing return type hint for async function 'process_file' | `async def process_file(filepath):` |
| `51` | Warning | PY_TYPING | Missing type hint for argument 'filepath' in async function 'process_file' | `async def process_file(filepath):` |
| `86` | Warning | PY_TYPING | Missing return type hint for async function 'check_status' | `async def check_status(j_id):` |
| `86` | Warning | PY_TYPING | Missing type hint for argument 'j_id' in async function 'check_status' | `async def check_status(j_id):` |

---

### Module: `nce/__init__.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `57` | Warning | PY_TYPING | Missing return type hint for function '__getattr__' | `def __getattr__(name: str):` |

---

### Module: `nce/a2a.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `305` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `324` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `330` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `338` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `354` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |

---

### Module: `nce/a2a_server.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `94` | Warning | PY_GLOBAL | Implicit global declaration: _SHUTDOWN_EVENT | `global _SHUTDOWN_EVENT` |
| `118` | Warning | PY_TYPING | Missing return type hint for async function '_track_active_request' | `async def _track_active_request():` |
| `120` | Warning | PY_GLOBAL | Implicit global declaration: _ACTIVE_REQUESTS | `global _ACTIVE_REQUESTS` |
| `630` | Warning | PY_TYPING | Missing return type hint for async function 'lifespan' | `async def lifespan(app: Starlette):` |
| `631` | Warning | PY_GLOBAL | Implicit global declaration: _engine | `global _engine` |

---

### Module: `nce/active_learning.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `59` | Warning | PY_TYPING | Missing type hint for argument 'memory_orchestrator' in async function 'confirm_memory' | `async def confirm_memory(` |

---

### Module: `nce/admin_app.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `33` | Warning | PY_TYPING | Missing return type hint for async function 'admin_lifespan' | `async def admin_lifespan(app):` |
| `33` | Warning | PY_TYPING | Missing type hint for argument 'app' in async function 'admin_lifespan' | `async def admin_lifespan(app):` |
| `79` | Warning | PY_TYPING | Missing return type hint for async function 'get_healthz' | `async def get_healthz(request):` |
| `79` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'get_healthz' | `async def get_healthz(request):` |

---

### Module: `nce/admin_handlers/a2a.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `06` | Warning | PY_TYPING | Missing return type hint for async function 'api_a2a_create_grant' | `async def api_a2a_create_grant(request):` |
| `06` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_a2a_create_grant' | `async def api_a2a_create_grant(request):` |
| `62` | Warning | PY_TYPING | Missing return type hint for async function 'api_a2a_revoke_grant' | `async def api_a2a_revoke_grant(request):` |
| `62` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_a2a_revoke_grant' | `async def api_a2a_revoke_grant(request):` |
| `113` | Warning | PY_TYPING | Missing return type hint for async function 'api_a2a_list_grants' | `async def api_a2a_list_grants(request):` |
| `113` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_a2a_list_grants' | `async def api_a2a_list_grants(request):` |

---

### Module: `nce/admin_handlers/fleet.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `06` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_events' | `async def api_admin_events(request):` |
| `06` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_events' | `async def api_admin_events(request):` |
| `144` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_events_summary' | `async def api_admin_events_summary(request):` |
| `144` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_events_summary' | `async def api_admin_events_summary(request):` |
| `212` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_verify_chain' | `async def api_admin_verify_chain(request):` |
| `212` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_verify_chain' | `async def api_admin_verify_chain(request):` |
| `254` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_a2a_grants' | `async def api_admin_a2a_grants(request):` |
| `254` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_a2a_grants' | `async def api_admin_a2a_grants(request):` |
| `336` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_a2a_grants_summary' | `async def api_admin_a2a_grants_summary(request):` |
| `336` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_a2a_grants_summary' | `async def api_admin_a2a_grants_summary(request):` |
| `386` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_a2a_revoke_grant' | `async def api_admin_a2a_revoke_grant(request):` |
| `386` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_a2a_revoke_grant' | `async def api_admin_a2a_revoke_grant(request):` |
| `394` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_quotas' | `async def api_admin_quotas(request):` |
| `394` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_quotas' | `async def api_admin_quotas(request):` |
| `509` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_quotas_summary' | `async def api_admin_quotas_summary(request):` |
| `509` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_quotas_summary' | `async def api_admin_quotas_summary(request):` |
| `560` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_graph_explore' | `async def api_admin_graph_explore(request):` |
| `560` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_graph_explore' | `async def api_admin_graph_explore(request):` |
| `604` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_embedding_models' | `async def api_admin_embedding_models(request):` |
| `604` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_embedding_models' | `async def api_admin_embedding_models(request):` |
| `620` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_embedding_migration_start' | `async def api_admin_embedding_migration_start(request):` |
| `620` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_embedding_migration_start' | `async def api_admin_embedding_migration_start(request):` |
| `640` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_embedding_migration_status' | `async def api_admin_embedding_migration_status(request):` |
| `640` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_embedding_migration_status' | `async def api_admin_embedding_migration_status(request):` |
| `656` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_embedding_migration_validate' | `async def api_admin_embedding_migration_validate(request):` |
| `656` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_embedding_migration_validate' | `async def api_admin_embedding_migration_validate(request):` |
| `672` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_embedding_migration_commit' | `async def api_admin_embedding_migration_commit(request):` |
| `672` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_embedding_migration_commit' | `async def api_admin_embedding_migration_commit(request):` |
| `688` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_embedding_migration_abort' | `async def api_admin_embedding_migration_abort(request):` |
| `688` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_embedding_migration_abort' | `async def api_admin_embedding_migration_abort(request):` |
| `704` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_schema' | `async def api_admin_schema(request):` |
| `704` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_schema' | `async def api_admin_schema(request):` |
| `758` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_dlq_list' | `async def api_admin_dlq_list(request):` |
| `758` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_dlq_list' | `async def api_admin_dlq_list(request):` |
| `829` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_dlq_replay' | `async def api_admin_dlq_replay(request):` |
| `829` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_dlq_replay' | `async def api_admin_dlq_replay(request):` |
| `848` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_dlq_purge' | `async def api_admin_dlq_purge(request):` |
| `848` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_dlq_purge' | `async def api_admin_dlq_purge(request):` |
| `867` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_db_postgres_status' | `async def api_admin_db_postgres_status(request):` |
| `867` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_db_postgres_status' | `async def api_admin_db_postgres_status(request):` |
| `910` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_db_mongo_status' | `async def api_admin_db_mongo_status(request):` |
| `910` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_db_mongo_status' | `async def api_admin_db_mongo_status(request):` |
| `937` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_db_redis_status' | `async def api_admin_db_redis_status(request):` |
| `937` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_db_redis_status' | `async def api_admin_db_redis_status(request):` |
| `959` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `982` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_db_minio_status' | `async def api_admin_db_minio_status(request):` |
| `982` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_db_minio_status' | `async def api_admin_db_minio_status(request):` |
| `989` | Warning | PY_TYPING | Missing return type hint for function '_get_buckets' | `def _get_buckets():` |
| `1002` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `1017` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_connectors_status' | `async def api_admin_connectors_status(request):` |
| `1017` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_connectors_status' | `async def api_admin_connectors_status(request):` |
| `1080` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_connectors_save' | `async def api_admin_connectors_save(request):` |
| `1080` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_connectors_save' | `async def api_admin_connectors_save(request):` |
| `1142` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except ValueError:` |
| `1161` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_datastores_status' | `async def api_admin_datastores_status(request):` |
| `1161` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_datastores_status' | `async def api_admin_datastores_status(request):` |
| `1201` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_datastores_save' | `async def api_admin_datastores_save(request):` |
| `1201` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_datastores_save' | `async def api_admin_datastores_save(request):` |
| `1259` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except ValueError:` |
| `1264` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except ValueError:` |
| `1279` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except ValueError:` |
| `1284` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except ValueError:` |
| `1330` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_signing_status' | `async def api_admin_signing_status(request):` |
| `1330` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_signing_status' | `async def api_admin_signing_status(request):` |
| `1347` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_pii_redactions_list' | `async def api_admin_pii_redactions_list(request):` |
| `1347` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_pii_redactions_list' | `async def api_admin_pii_redactions_list(request):` |
| `1400` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_security_event_seq_gaps' | `async def api_admin_security_event_seq_gaps(request):` |
| `1400` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_security_event_seq_gaps' | `async def api_admin_security_event_seq_gaps(request):` |
| `1460` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_security_verify_memory_sample' | `async def api_admin_security_verify_memory_sample(request):` |
| `1460` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_security_verify_memory_sample' | `async def api_admin_security_verify_memory_sample(request):` |
| `1533` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_security_test_rls_isolation' | `async def api_admin_security_test_rls_isolation(request):` |
| `1533` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_security_test_rls_isolation' | `async def api_admin_security_test_rls_isolation(request):` |
| `1597` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_namespaces_list' | `async def api_admin_namespaces_list(request):` |
| `1597` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_namespaces_list' | `async def api_admin_namespaces_list(request):` |
| `1673` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_namespaces_get' | `async def api_admin_namespaces_get(request):` |
| `1673` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_namespaces_get' | `async def api_admin_namespaces_get(request):` |
| `1709` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_namespaces_update_metadata' | `async def api_admin_namespaces_update_metadata(request):` |
| `1709` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_namespaces_update_metadata' | `async def api_admin_namespaces_update_metadata(request):` |
| `1745` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_memory_boost' | `async def api_admin_memory_boost(request):` |
| `1745` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_memory_boost' | `async def api_admin_memory_boost(request):` |
| `1786` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_salience_map' | `async def api_admin_salience_map(request):` |
| `1786` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_salience_map' | `async def api_admin_salience_map(request):` |
| `1838` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_llm_payload' | `async def api_admin_llm_payload(request):` |
| `1838` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_llm_payload' | `async def api_admin_llm_payload(request):` |
| `1874` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_fleet_overview' | `async def api_admin_fleet_overview(request):` |
| `1874` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_fleet_overview' | `async def api_admin_fleet_overview(request):` |
| `1921` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_contradictions_recent' | `async def api_admin_contradictions_recent(request):` |
| `1921` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_contradictions_recent' | `async def api_admin_contradictions_recent(request):` |
| `1940` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_namespace_bridges' | `async def api_admin_namespace_bridges(request):` |
| `1940` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_namespace_bridges' | `async def api_admin_namespace_bridges(request):` |
| `1958` | Warning | PY_TYPING | Missing return type hint for async function 'api_admin_bridge_renew' | `async def api_admin_bridge_renew(request):` |
| `1958` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_bridge_renew' | `async def api_admin_bridge_renew(request):` |

---

### Module: `nce/admin_handlers/health.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `06` | Warning | PY_TYPING | Missing return type hint for async function 'get_health' | `async def get_health(request):` |
| `06` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'get_health' | `async def get_health(request):` |
| `22` | Warning | PY_TYPING | Missing return type hint for async function 'get_health_v1' | `async def get_health_v1(request):` |
| `22` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'get_health_v1' | `async def get_health_v1(request):` |
| `27` | Warning | PY_TYPING | Missing return type hint for async function 'trigger_gc' | `async def trigger_gc(request):` |
| `27` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'trigger_gc' | `async def trigger_gc(request):` |
| `40` | Warning | PY_TYPING | Missing return type hint for async function 'api_search' | `async def api_search(request):` |
| `40` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_search' | `async def api_search(request):` |
| `98` | Warning | PY_TYPING | Missing return type hint for async function 'serve_index' | `async def serve_index(request):` |
| `98` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'serve_index' | `async def serve_index(request):` |
| `105` | Warning | PY_TYPING | Missing return type hint for async function 'serve_styles' | `async def serve_styles(request):` |
| `105` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'serve_styles' | `async def serve_styles(request):` |

---

### Module: `nce/admin_handlers/replay.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `06` | Warning | PY_TYPING | Missing return type hint for async function 'api_replay_observe' | `async def api_replay_observe(request):` |
| `06` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_replay_observe' | `async def api_replay_observe(request):` |
| `95` | Warning | PY_TYPING | Missing return type hint for async function 'api_snapshot_export' | `async def api_snapshot_export(request):` |
| `95` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_snapshot_export' | `async def api_snapshot_export(request):` |
| `155` | Warning | PY_TYPING | Missing return type hint for async function 'api_replay_fork' | `async def api_replay_fork(request):` |
| `155` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_replay_fork' | `async def api_replay_fork(request):` |
| `266` | Warning | PY_TYPING | Missing return type hint for async function 'api_replay_status' | `async def api_replay_status(request):` |
| `266` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_replay_status' | `async def api_replay_status(request):` |
| `291` | Warning | PY_TYPING | Missing return type hint for async function 'api_event_provenance' | `async def api_event_provenance(request):` |
| `291` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_event_provenance' | `async def api_event_provenance(request):` |

---

### Module: `nce/admin_handlers/tools.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `76` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_tools' | `async def api_admin_tools(request) -> JSONResponse:` |
| `123` | Warning | PY_TYPING | Missing type hint for argument 'request' in async function 'api_admin_tools_toggle' | `async def api_admin_tools_toggle(request) -> JSONResponse:` |

---

### Module: `nce/admin_http_support.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `172` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except OSError:` |

---

### Module: `nce/ast_parser.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `200` | Warning | PY_TYPING | Missing type hint for argument 'node' in function '_extract_name' | `def _extract_name(node) -> str:` |
| `216` | Warning | PY_TYPING | Missing type hint for argument 'n' in function '_find_id' | `def _find_id(n) -> str \| None:` |
| `234` | Warning | PY_TYPING | Missing type hint for argument 'node' in function '_walk' | `def _walk(node, depth: int = 0) -> None:` |

---

### Module: `nce/auth.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `479` | Warning | PY_TYPING | Missing return type hint for function 'require_scope' | `def require_scope(scope: str):` |
| `502` | Warning | PY_TYPING | Missing return type hint for function 'decorator' | `def decorator(func):` |
| `502` | Warning | PY_TYPING | Missing type hint for argument 'func' in function 'decorator' | `def decorator(func):` |
| `504` | Warning | PY_TYPING | Missing return type hint for async function 'wrapper' | `async def wrapper(*args, **kwargs):` |
| `593` | Warning | PY_TYPING | Missing return type hint for function 'admin_rate_limit' | `def admin_rate_limit(limit: int = 10, period: int = 60):` |
| `605` | Warning | PY_TYPING | Missing return type hint for function 'decorator' | `def decorator(func):` |
| `605` | Warning | PY_TYPING | Missing type hint for argument 'func' in function 'decorator' | `def decorator(func):` |
| `607` | Warning | PY_TYPING | Missing return type hint for async function 'wrapper' | `async def wrapper(*args, **kwargs):` |
| `903` | Warning | PY_TYPING | Missing return type hint for async function 'audited_session' | `async def audited_session(` |

---

### Module: `nce/bridge_renewal.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `90` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `218` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `376` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `525` | Warning | PY_TYPING | Missing type hint for argument 'bridge_id' in async function 'mark_degraded' | `async def mark_degraded(pool: asyncpg.Pool, bridge_id, reason: str) -> None:` |

---

### Module: `nce/bridges/base.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `76` | Warning | PY_TYPING | Missing return type hint for function 'redis_client' | `def redis_client():` |

---

### Module: `nce/causal/chrono.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `28` | Warning | PY_TYPING | Missing return type hint for function 'branch_timeline' | `def branch_timeline(target_time: datetime \| str, hypothetical_states: dict[str, Any]):` |

---

### Module: `nce/causal/correlation.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `246` | Warning | PY_TYPING | Missing type hint for argument 'conn' in async function 'load_from_db' | `async def load_from_db(` |
| `916` | Warning | PY_TYPING | Missing type hint for argument 'conn' in async function 'evaluate_intervention' | `async def evaluate_intervention(` |

---

### Module: `nce/causal/synthesis.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `95` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |

---

### Module: `nce/consolidation.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `236` | Warning | PY_TYPING | Missing return type hint for async function '_store_consolidated_memory' | `async def _store_consolidated_memory(` |
| `236` | Warning | PY_TYPING | Missing type hint for argument 'conn' in async function '_store_consolidated_memory' | `async def _store_consolidated_memory(` |
| `279` | Warning | PY_TYPING | Missing return type hint for async function '_update_kg' | `async def _update_kg(` |
| `279` | Warning | PY_TYPING | Missing type hint for argument 'conn' in async function '_update_kg' | `async def _update_kg(` |
| `357` | Warning | PY_TYPING | Missing return type hint for async function 'run_consolidation' | `async def run_consolidation(self, namespace_id: UUID, since_timestamp: datetime \| None = None):` |

---

### Module: `nce/contradictions.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `36` | Warning | PY_TYPING | Missing return type hint for function '_load_nli_model' | `def _load_nli_model():` |

---

### Module: `nce/db_utils.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `38` | Warning | PY_TYPING | Missing return type hint for async function 'unmanaged_pg_connection' | `async def unmanaged_pg_connection(pool: asyncpg.Pool, *, site: str):` |
| `57` | Warning | PY_TYPING | Missing return type hint for async function 'scoped_pg_session' | `async def scoped_pg_session(` |

---

### Module: `nce/embeddings.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `219` | Warning | PY_TYPING | Missing return type hint for function '_load_sentence_transformer' | `def _load_sentence_transformer(device: str):` |
| `258` | Warning | PY_TYPING | Missing return type hint for function '_load_openvino_npu_bundle' | `def _load_openvino_npu_bundle(model_dir: str, seq_len: int):` |
| `392` | Warning | PY_TYPING | Missing return type hint for function '_mean_pool' | `def _mean_pool(last_hidden_state, attention_mask):` |
| `392` | Warning | PY_TYPING | Missing type hint for argument 'last_hidden_state' in function '_mean_pool' | `def _mean_pool(last_hidden_state, attention_mask):` |
| `392` | Warning | PY_TYPING | Missing type hint for argument 'attention_mask' in function '_mean_pool' | `def _mean_pool(last_hidden_state, attention_mask):` |
| `678` | Warning | PY_GLOBAL | Implicit global declaration: _backend | `global _backend` |
| `688` | Warning | PY_GLOBAL | Implicit global declaration: _backend | `global _backend` |

---

### Module: `nce/event_log.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `584` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except (ValueError, TypeError):` |

---

### Module: `nce/extractors/adobe_ext.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `21` | Warning | PY_TYPING | Missing type hint for argument 'psd' in function '_collect_psd_type_layers' | `def _collect_psd_type_layers(psd, texts: list[str], warnings: list[str]) -> None:` |

---

### Module: `nce/extractors/cad_ext.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `23` | Warning | PY_TYPING | Missing type hint for argument 'msp' in function '_collect_entity_texts' | `def _collect_entity_texts(msp, warnings: list[str]) -> list[str]:` |
| `36` | Warning | PY_TYPING | Missing type hint for argument 'entity' in function '_entity_text' | `def _entity_text(entity) -> str \| None:` |
| `164` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except OSError:` |
| `187` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `217` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |

---

### Module: `nce/extractors/common.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `72` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `138` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |

---

### Module: `nce/extractors/diagrams.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `78` | Warning | PY_TYPING | Missing return type hint for function '_walk' | `def _walk(s, depth: int = 0):` |
| `78` | Warning | PY_TYPING | Missing type hint for argument 's' in function '_walk' | `def _walk(s, depth: int = 0):` |
| `135` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except OSError:` |

---

### Module: `nce/extractors/dispatch.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `175` | Warning | PY_GLOBAL | Implicit global declaration: _initialized | `global _initialized` |

---

### Module: `nce/extractors/email_ext.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `38` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `44` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `68` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except OSError:` |
| `169` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |

---

### Module: `nce/extractors/encryption.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `86` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `97` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except ImportError:` |

---

### Module: `nce/extractors/ocr.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `56` | Warning | PY_TYPING | Missing return type hint for function '_open' | `def _open():` |
| `79` | Warning | PY_TYPING | Missing return type hint for function '_pages' | `def _pages():` |

---

### Module: `nce/extractors/office_excel.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `169` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `256` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `261` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |

---

### Module: `nce/extractors/office_pptx.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `22` | Warning | PY_TYPING | Missing type hint for argument 'slide' in function '_slide_hidden' | `def _slide_hidden(slide) -> bool:` |
| `30` | Warning | PY_TYPING | Missing type hint for argument 'shape' in async function '_shape_parts' | `async def _shape_parts(shape, warnings: list[str]) -> list[str]:` |
| `77` | Warning | PY_TYPING | Missing return type hint for function '_load' | `def _load():` |
| `150` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |

---

### Module: `nce/extractors/office_word.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `77` | Warning | PY_TYPING | Missing return type hint for function '_safe_parse_xml' | `def _safe_parse_xml(data: bytes):` |

---

### Module: `nce/extractors/pdf_ext.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `63` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |

---

### Module: `nce/extractors/project_ext.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `162` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except OSError:` |

---

### Module: `nce/garbage_collector.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `103` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `411` | Warning | PY_TYPING | Missing return type hint for async function 'run_gc_loop' | `async def run_gc_loop():` |
| `476` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |

---

### Module: `nce/graph_extractor.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `64` | Warning | PY_TYPING | Missing return type hint for function '_get_spacy_model' | `def _get_spacy_model(model_name: str = "en_core_web_sm"):` |

---

### Module: `nce/graph_query.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `351` | Warning | PY_TYPING | Missing type hint for argument 'embedding_fn' in function '__init__' | `def __init__(` |
| `448` | Warning | PY_TYPING | Missing return type hint for async function '_run_find_anchor' | `async def _run_find_anchor(c):` |
| `448` | Warning | PY_TYPING | Missing type hint for argument 'c' in async function '_run_find_anchor' | `async def _run_find_anchor(c):` |
| `575` | Warning | PY_TYPING | Missing return type hint for async function '_run_bfs' | `async def _run_bfs(c):` |
| `575` | Warning | PY_TYPING | Missing type hint for argument 'c' in async function '_run_bfs' | `async def _run_bfs(c):` |

---

### Module: `nce/http_resilience.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `110` | Warning | PY_TYPING | Missing return type hint for function '_wait_seconds_policy' | `def _wait_seconds_policy(` |
| `118` | Warning | PY_TYPING | Missing return type hint for function 'wait_policy' | `def wait_policy(retry_state):  # type: ignore[no-untyped-def]` |
| `118` | Warning | PY_TYPING | Missing type hint for argument 'retry_state' in function 'wait_policy' | `def wait_policy(retry_state):  # type: ignore[no-untyped-def]` |
| `151` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except ValueError:` |
| `163` | Warning | PY_TYPING | Missing return type hint for function '_make_before_sleep_safe' | `def _make_before_sleep_safe(operation_name: str):` |
| `166` | Warning | PY_TYPING | Missing type hint for argument 'retry_state' in function '_hook' | `def _hook(retry_state) -> None:  # type: ignore[no-untyped-def]` |

---

### Module: `nce/mcp_stdio_main.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `26` | Warning | PY_TYPING | Missing return type hint for async function 'list_tools' | `async def list_tools():` |
| `30` | Warning | PY_TYPING | Missing return type hint for async function 'call_tool' | `async def call_tool(name: str, arguments: dict):` |
| `102` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except asyncio.CancelledError:` |

---

### Module: `nce/mcp_stdio_rpc.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `57` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function '_consume_quota_for_mcp_tool' | `async def _consume_quota_for_mcp_tool(` |
| `57` | Warning | PY_TYPING | Missing type hint for argument 'redis_client' in async function '_consume_quota_for_mcp_tool' | `async def _consume_quota_for_mcp_tool(` |

---

### Module: `nce/models.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `1425` | Warning | PY_TYPING | Missing type hint for argument 'fn' in function '_expect_error' | `def _expect_error(name: str, fn) -> None:` |

---

### Module: `nce/mongo_bulk.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `71` | Warning | PY_TYPING | Missing type hint for argument 'collection' in async function '_fetch_field_by_refs' | `async def _fetch_field_by_refs(` |
| `110` | Warning | PY_TYPING | Missing type hint for argument 'db' in async function 'fetch_episodes_raw_by_ref' | `async def fetch_episodes_raw_by_ref(` |
| `120` | Warning | PY_TYPING | Missing type hint for argument 'db' in async function 'fetch_episode_previews_by_ref' | `async def fetch_episode_previews_by_ref(` |
| `160` | Warning | PY_TYPING | Missing type hint for argument 'db' in async function 'fetch_code_files_raw_by_ref' | `async def fetch_code_files_raw_by_ref(` |

---

### Module: `nce/mtls.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `98` | Warning | PY_TYPING | Missing type hint for argument 'app' in function '__init__' | `def __init__(` |
| `131` | Warning | PY_TYPING | Missing type hint for argument 'scope' in async function '__call__' | `async def __call__(self, scope, receive, send) -> None:` |
| `131` | Warning | PY_TYPING | Missing type hint for argument 'receive' in async function '__call__' | `async def __call__(self, scope, receive, send) -> None:` |
| `131` | Warning | PY_TYPING | Missing type hint for argument 'send' in async function '__call__' | `async def __call__(self, scope, receive, send) -> None:` |

---

### Module: `nce/notifications.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `89` | Warning | PY_TYPING | Missing return type hint for async function 'start_worker' | `async def start_worker(self):` |
| `94` | Warning | PY_TYPING | Missing return type hint for async function 'stop_worker' | `async def stop_worker(self):` |
| `99` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except asyncio.CancelledError:` |
| `118` | Warning | PY_TYPING | Missing return type hint for async function '_worker' | `async def _worker(self):` |
| `135` | Warning | PY_TYPING | Missing return type hint for async function '_send_slack' | `async def _send_slack(self, title: str, message: str):` |
| `151` | Warning | PY_TYPING | Missing return type hint for async function '_send_teams' | `async def _send_teams(self, title: str, message: str):` |
| `167` | Warning | PY_TYPING | Missing return type hint for async function '_send_email' | `async def _send_email(self, title: str, message: str):` |
| `203` | Warning | PY_TYPING | Missing return type hint for async function '_send_snmp' | `async def _send_snmp(self, title: str, message: str):` |
| `209` | Warning | PY_TYPING | Missing return type hint for async function 'dispatch_alert' | `async def dispatch_alert(self, title: str, message: str):` |

---

### Module: `nce/observability.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `72` | Warning | PY_TYPING | Missing return type hint for function '_safe_metric' | `def _safe_metric(metric_cls, name: str, *args, **kwargs):` |
| `72` | Warning | PY_TYPING | Missing type hint for argument 'metric_cls' in function '_safe_metric' | `def _safe_metric(metric_cls, name: str, *args, **kwargs):` |
| `106` | Warning | PY_TYPING | Missing return type hint for function 'start_http_server' | `def start_http_server(*args, **kwargs):` |
| `109` | Warning | PY_TYPING | Missing return type hint for function '_safe_counter' | `def _safe_counter(name, *args, **kwargs):  # type: ignore[misc]` |
| `109` | Warning | PY_TYPING | Missing type hint for argument 'name' in function '_safe_counter' | `def _safe_counter(name, *args, **kwargs):  # type: ignore[misc]` |
| `112` | Warning | PY_TYPING | Missing return type hint for function '_safe_histogram' | `def _safe_histogram(name, *args, **kwargs):  # type: ignore[misc]` |
| `112` | Warning | PY_TYPING | Missing type hint for argument 'name' in function '_safe_histogram' | `def _safe_histogram(name, *args, **kwargs):  # type: ignore[misc]` |
| `115` | Warning | PY_TYPING | Missing return type hint for function '_safe_gauge' | `def _safe_gauge(name, *args, **kwargs):  # type: ignore[misc]` |
| `115` | Warning | PY_TYPING | Missing type hint for argument 'name' in function '_safe_gauge' | `def _safe_gauge(name, *args, **kwargs):  # type: ignore[misc]` |
| `294` | Warning | PY_GLOBAL | Implicit global declaration: _tracer_initialized | `global _tracer_initialized` |
| `304` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `319` | Warning | PY_TYPING | Missing return type hint for function 'get_tracer' | `def get_tracer():` |
| `323` | Warning | PY_TYPING | Missing return type hint for function '__enter__' | `def __enter__(self):` |
| `326` | Warning | PY_TYPING | Missing return type hint for function '__exit__' | `def __exit__(self, *args):` |
| `329` | Warning | PY_TYPING | Missing return type hint for function 'set_attribute' | `def set_attribute(self, *args):` |
| `332` | Warning | PY_TYPING | Missing return type hint for function 'record_exception' | `def record_exception(self, *args):` |
| `335` | Warning | PY_TYPING | Missing return type hint for function 'set_status' | `def set_status(self, *args):` |
| `339` | Warning | PY_TYPING | Missing return type hint for function 'start_as_current_span' | `def start_as_current_span(self, *args, **kwargs):` |
| `349` | Warning | PY_TYPING | Missing return type hint for function 'instrument_tool' | `def instrument_tool(tool_name: str):` |
| `354` | Warning | PY_TYPING | Missing return type hint for async function 'wrapper' | `async def wrapper(*args, **kwargs):` |
| `384` | Warning | PY_TYPING | Missing return type hint for async function 'instrument_tool_call' | `async def instrument_tool_call(tool_name: str):` |

---

### Module: `nce/orchestrator.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `200` | Warning | PY_TYPING | Missing return type hint for async function 'connect' | `async def connect(self):` |
| `311` | Warning | PY_TYPING | Missing return type hint for async function 'disconnect' | `async def disconnect(self):` |
| `325` | Warning | PY_TYPING | Missing return type hint for function '_mongo_db' | `def _mongo_db(self):` |
| `441` | Warning | PY_TYPING | Missing return type hint for function '_init_minio_buckets' | `def _init_minio_buckets(self):` |
| `457` | Warning | PY_TYPING | Missing return type hint for function '_validate_path' | `def _validate_path(self, filepath: str):` |
| `485` | Warning | PY_TYPING | Missing return type hint for async function '_init_pg_schema' | `async def _init_pg_schema(self):` |
| `525` | Warning | PY_TYPING | Missing return type hint for async function '_verify_worm_enforcement' | `async def _verify_worm_enforcement(self):` |
| `569` | Warning | PY_TYPING | Missing return type hint for async function '_verify_rls_enforcement' | `async def _verify_rls_enforcement(self):` |
| `585` | Warning | PY_TYPING | Missing return type hint for async function '_check_global_legacy_warning' | `async def _check_global_legacy_warning(self):` |
| `642` | Warning | PY_TYPING | Missing return type hint for async function '_init_mongo_indexes' | `async def _init_mongo_indexes(self):` |
| `656` | Warning | PY_TYPING | Missing return type hint for async function 'scoped_session' | `async def scoped_session(self, namespace_id: str \| UUID):` |
| `689` | Warning | PY_TYPING | Missing return type hint for async function 'trigger_consolidation' | `async def trigger_consolidation(` |
| `841` | Warning | PY_TYPING | Missing return type hint for function '_get_queue_lengths' | `def _get_queue_lengths():` |
| `851` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except _QUEUE_PROBE_ERRORS:` |
| `883` | Warning | PY_TYPING | Missing return type hint for async function 'recall_memory' | `async def recall_memory(self, namespace_id, user_id, session_id, as_of=None):` |
| `883` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'recall_memory' | `async def recall_memory(self, namespace_id, user_id, session_id, as_of=None):` |
| `883` | Warning | PY_TYPING | Missing type hint for argument 'user_id' in async function 'recall_memory' | `async def recall_memory(self, namespace_id, user_id, session_id, as_of=None):` |
| `883` | Warning | PY_TYPING | Missing type hint for argument 'session_id' in async function 'recall_memory' | `async def recall_memory(self, namespace_id, user_id, session_id, as_of=None):` |
| `883` | Warning | PY_TYPING | Missing type hint for argument 'as_of' in async function 'recall_memory' | `async def recall_memory(self, namespace_id, user_id, session_id, as_of=None):` |
| `888` | Warning | PY_TYPING | Missing return type hint for async function 'recall_recent' | `async def recall_recent(` |
| `888` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'recall_recent' | `async def recall_recent(` |
| `888` | Warning | PY_TYPING | Missing type hint for argument 'agent_id' in async function 'recall_recent' | `async def recall_recent(` |
| `888` | Warning | PY_TYPING | Missing type hint for argument 'limit' in async function 'recall_recent' | `async def recall_recent(` |
| `888` | Warning | PY_TYPING | Missing type hint for argument 'as_of' in async function 'recall_recent' | `async def recall_recent(` |
| `888` | Warning | PY_TYPING | Missing type hint for argument 'user_id' in async function 'recall_recent' | `async def recall_recent(` |
| `888` | Warning | PY_TYPING | Missing type hint for argument 'session_id' in async function 'recall_recent' | `async def recall_recent(` |
| `888` | Warning | PY_TYPING | Missing type hint for argument 'offset' in async function 'recall_recent' | `async def recall_recent(` |
| `906` | Warning | PY_TYPING | Missing return type hint for async function 'semantic_search' | `async def semantic_search(` |
| `906` | Warning | PY_TYPING | Missing type hint for argument 'query' in async function 'semantic_search' | `async def semantic_search(` |
| `906` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'semantic_search' | `async def semantic_search(` |
| `906` | Warning | PY_TYPING | Missing type hint for argument 'agent_id' in async function 'semantic_search' | `async def semantic_search(` |
| `906` | Warning | PY_TYPING | Missing type hint for argument 'limit' in async function 'semantic_search' | `async def semantic_search(` |
| `906` | Warning | PY_TYPING | Missing type hint for argument 'offset' in async function 'semantic_search' | `async def semantic_search(` |
| `906` | Warning | PY_TYPING | Missing type hint for argument 'as_of' in async function 'semantic_search' | `async def semantic_search(` |
| `921` | Warning | PY_TYPING | Missing return type hint for async function 'unredact_memory' | `async def unredact_memory(self, memory_id, namespace_id, agent_id):` |
| `921` | Warning | PY_TYPING | Missing type hint for argument 'memory_id' in async function 'unredact_memory' | `async def unredact_memory(self, memory_id, namespace_id, agent_id):` |
| `921` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'unredact_memory' | `async def unredact_memory(self, memory_id, namespace_id, agent_id):` |
| `921` | Warning | PY_TYPING | Missing type hint for argument 'agent_id' in async function 'unredact_memory' | `async def unredact_memory(self, memory_id, namespace_id, agent_id):` |

---

### Module: `nce/orchestrators/cognitive.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `38` | Warning | PY_TYPING | Missing return type hint for async function 'scoped_session' | `async def scoped_session(self, namespace_id: str \| UUID):` |

---

### Module: `nce/orchestrators/graph.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `29` | Warning | PY_TYPING | Missing type hint for argument 'graph_traverser' in function '__init__' | `def __init__(` |
| `29` | Warning | PY_TYPING | Missing type hint for argument 'embed_fn' in function '__init__' | `def __init__(` |
| `53` | Warning | PY_TYPING | Missing return type hint for async function 'scoped_session' | `async def scoped_session(self, namespace_id: str \| UUID):` |
| `59` | Warning | PY_TYPING | Missing return type hint for function '_mongo_db' | `def _mongo_db(self):` |
| `66` | Warning | PY_TYPING | Missing type hint for argument 'payload' in async function 'graph_search' | `async def graph_search(self, payload) -> dict:` |

---

### Module: `nce/orchestrators/memory.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `71` | Warning | PY_TYPING | Missing type hint for argument 'conn' in async function '_enqueue_outbox' | `async def _enqueue_outbox(` |
| `106` | Warning | PY_TYPING | Missing return type hint for async function '_apply_pii_pipeline' | `async def _apply_pii_pipeline(self, payload: StoreMemoryRequest, *, conn=None):` |
| `113` | Warning | PY_TYPING | Missing return type hint for async function '_fetch_ns_config' | `async def _fetch_ns_config(c):` |
| `113` | Warning | PY_TYPING | Missing type hint for argument 'c' in async function '_fetch_ns_config' | `async def _fetch_ns_config(c):` |
| `143` | Warning | PY_TYPING | Missing return type hint for async function '_embed_and_insert_vectors' | `async def _embed_and_insert_vectors(` |
| `143` | Warning | PY_TYPING | Missing type hint for argument 'conn' in async function '_embed_and_insert_vectors' | `async def _embed_and_insert_vectors(` |
| `215` | Warning | PY_TYPING | Missing return type hint for async function '_insert_graph_nodes_and_edges' | `async def _insert_graph_nodes_and_edges(` |
| `215` | Warning | PY_TYPING | Missing type hint for argument 'conn' in async function '_insert_graph_nodes_and_edges' | `async def _insert_graph_nodes_and_edges(` |
| `400` | Warning | PY_TYPING | Missing return type hint for async function '_apply_rollback_on_failure' | `async def _apply_rollback_on_failure(` |
| `538` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except (ValueError, TypeError):` |
| `923` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `934` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `1138` | Warning | PY_TYPING | Missing type hint for argument 'as_of' in async function 'semantic_search' | `async def semantic_search(` |

---

### Module: `nce/orchestrators/migration.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `27` | Warning | PY_TYPING | Missing type hint for argument 'redis_client' in function '__init__' | `def __init__(` |
| `27` | Warning | PY_TYPING | Missing type hint for argument 'redis_sync_client' in function '__init__' | `def __init__(` |
| `71` | Warning | PY_TYPING | Missing type hint for argument 'payload' in async function 'index_code_file' | `async def index_code_file(self, payload, *, priority: int = 0) -> dict:` |

---

### Module: `nce/orchestrators/namespace.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `136` | Warning | PY_TYPING | Missing return type hint for async function 'scoped_session' | `async def scoped_session(self, namespace_id: str \| UUID):` |
| `145` | Warning | PY_TYPING | Missing type hint for argument 'payload' in async function 'manage_namespace' | `async def manage_namespace(` |
| `417` | Warning | PY_TYPING | Missing type hint for argument 'payload' in async function 'manage_quotas' | `async def manage_quotas(self, payload) -> dict:` |

---

### Module: `nce/orchestrators/temporal.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `152` | Warning | PY_TYPING | Missing return type hint for async function 'scoped_session' | `async def scoped_session(self, namespace_id: str \| UUID):` |
| `158` | Warning | PY_TYPING | Missing return type hint for function '_mongo_db' | `def _mongo_db(self):` |
| `204` | Warning | PY_TYPING | Missing return type hint for async function 'trigger_consolidation' | `async def trigger_consolidation(` |
| `257` | Warning | PY_TYPING | Missing type hint for argument 'payload' in async function 'create_snapshot' | `async def create_snapshot(self, payload) -> Any:` |
| `324` | Warning | PY_TYPING | Missing type hint for argument 'payload' in async function 'compare_states' | `async def compare_states(self, payload) -> Any:` |

---

### Module: `nce/outbox_relay.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `250` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `260` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `272` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |

---

### Module: `nce/pii.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `166` | Warning | PY_GLOBAL | Implicit global declaration: _ANALYZER | `global _ANALYZER` |

---

### Module: `nce/providers/_http_utils.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `75` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except (ValueError, TypeError):` |

---

### Module: `nce/providers/base.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `631` | Warning | PY_TYPING | Missing type hint for argument 'operation' in async function 'execute_with_retry' | `async def execute_with_retry(` |
| `666` | Warning | PY_TYPING | Missing return type hint for function 'wait_policy' | `def wait_policy(retry_state):  # type: ignore[no-untyped-def]` |
| `666` | Warning | PY_TYPING | Missing type hint for argument 'retry_state' in function 'wait_policy' | `def wait_policy(retry_state):  # type: ignore[no-untyped-def]` |

---

### Module: `nce/providers/google_gemini.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `128` | Warning | PY_TYPING | Missing return type hint for function '_build_contents' | `def _build_contents(` |

---

### Module: `nce/re_embedder.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `71` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except (ImportError, RuntimeError):` |
| `75` | Warning | PY_TYPING | Missing return type hint for async function 'run_re_embedding_worker' | `async def run_re_embedding_worker(pg_pool: asyncpg.Pool, mongo_client: Any):` |
| `260` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in function 'start_re_embedder' | `def start_re_embedder(pg_pool, mongo_client) -> asyncio.Task:` |
| `260` | Warning | PY_TYPING | Missing type hint for argument 'mongo_client' in function 'start_re_embedder' | `def start_re_embedder(pg_pool, mongo_client) -> asyncio.Task:` |

---

### Module: `nce/reembedding_worker.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `432` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |

---

### Module: `nce/replay.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `331` | Warning | PY_TYPING | Missing return type hint for async function '_fetch_event_log_snapshot' | `async def _fetch_event_log_snapshot(` |
| `415` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except S3Error:` |
| `1129` | Warning | PY_TYPING | Missing type hint for argument 'write_conn' in async function '_apply_single_event' | `async def _apply_single_event(` |
| `1129` | Warning | PY_TYPING | Missing type hint for argument 'src' in async function '_apply_single_event' | `async def _apply_single_event(` |
| `1129` | Warning | PY_TYPING | Missing type hint for argument 'target_namespace_id' in async function '_apply_single_event' | `async def _apply_single_event(` |
| `1129` | Warning | PY_TYPING | Missing type hint for argument 'llm_payload' in async function '_apply_single_event' | `async def _apply_single_event(` |
| `1129` | Warning | PY_TYPING | Missing type hint for argument 'config_overrides' in async function '_apply_single_event' | `async def _apply_single_event(` |
| `1147` | Warning | PY_TYPING | Missing type hint for argument 'write_conn' in async function '_dispatch_and_apply' | `async def _dispatch_and_apply(` |

---

### Module: `nce/replay_mcp_handlers.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `89` | Warning | PY_TYPING | Missing return type hint for async function '_run_fork' | `async def _run_fork():` |
| `129` | Warning | PY_TYPING | Missing return type hint for async function '_run' | `async def _run():` |

---

### Module: `nce/semantic_search.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `302` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |

---

### Module: `nce/signing.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `370` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `427` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `517` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `570` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `583` | Warning | PY_GLOBAL | Implicit global declaration: _key_cache_lock | `global _key_cache_lock` |
| `821` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except KeyError:` |
| `904` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except KeyError:` |
| `1041` | Warning | PY_GLOBAL | Implicit global declaration: _key_cache | `global _key_cache` |
| `1075` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |

---

### Module: `nce/tasks.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `33` | Warning | PY_TYPING | Missing return type hint for function 'run_async' | `def run_async(coro):` |
| `33` | Warning | PY_TYPING | Missing type hint for argument 'coro' in function 'run_async' | `def run_async(coro):` |
| `57` | Warning | PY_GLOBAL | Implicit global declaration: _redis_client | `global _redis_client` |
| `136` | Warning | PY_TYPING | Missing return type hint for function 'process_code_indexing' | `def process_code_indexing(` |
| `163` | Warning | PY_TYPING | Missing return type hint for async function '_index' | `async def _index():` |

---

### Module: `nce/vertical_modules/netbox/mtbf.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `82` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |

---

### Module: `nce/webhook_receiver/main.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `56` | Warning | PY_TYPING | Missing return type hint for async function 'health' | `async def health():` |
| `212` | Warning | PY_TYPING | Missing return type hint for async function 'webhook_rate_limit_middleware' | `async def webhook_rate_limit_middleware(request: Request, call_next):` |
| `212` | Warning | PY_TYPING | Missing type hint for argument 'call_next' in async function 'webhook_rate_limit_middleware' | `async def webhook_rate_limit_middleware(request: Request, call_next):` |
| `248` | Warning | PY_TYPING | Missing return type hint for async function 'dropbox_challenge' | `async def dropbox_challenge(challenge: str = Query(..., alias="challenge")):` |
| `254` | Warning | PY_TYPING | Missing return type hint for async function 'dropbox_webhook' | `async def dropbox_webhook(request: Request):` |
| `280` | Warning | PY_TYPING | Missing return type hint for async function 'graph_webhook' | `async def graph_webhook(` |
| `315` | Warning | PY_TYPING | Missing return type hint for async function 'drive_webhook' | `async def drive_webhook(` |

---

### Module: `run_audit.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `14` | Warning | PY_TYPING | Missing return type hint for function 'is_target_file' | `def is_target_file(path):` |
| `14` | Warning | PY_TYPING | Missing type hint for argument 'path' in function 'is_target_file' | `def is_target_file(path):` |
| `28` | Warning | PY_TYPING | Missing type hint for argument 'filename' in function '__init__' | `def __init__(self, filename, lines):` |
| `28` | Warning | PY_TYPING | Missing type hint for argument 'lines' in function '__init__' | `def __init__(self, filename, lines):` |
| `33` | Warning | PY_TYPING | Missing return type hint for function 'add_issue' | `def add_issue(self, line_no, severity, rule_id, description):` |
| `33` | Warning | PY_TYPING | Missing type hint for argument 'line_no' in function 'add_issue' | `def add_issue(self, line_no, severity, rule_id, description):` |
| `33` | Warning | PY_TYPING | Missing type hint for argument 'severity' in function 'add_issue' | `def add_issue(self, line_no, severity, rule_id, description):` |
| `33` | Warning | PY_TYPING | Missing type hint for argument 'rule_id' in function 'add_issue' | `def add_issue(self, line_no, severity, rule_id, description):` |
| `33` | Warning | PY_TYPING | Missing type hint for argument 'description' in function 'add_issue' | `def add_issue(self, line_no, severity, rule_id, description):` |
| `46` | Warning | PY_TYPING | Missing return type hint for function 'visit_FunctionDef' | `def visit_FunctionDef(self, node):` |
| `46` | Warning | PY_TYPING | Missing type hint for argument 'node' in function 'visit_FunctionDef' | `def visit_FunctionDef(self, node):` |
| `54` | Warning | PY_TYPING | Missing return type hint for function 'visit_AsyncFunctionDef' | `def visit_AsyncFunctionDef(self, node):` |
| `54` | Warning | PY_TYPING | Missing type hint for argument 'node' in function 'visit_AsyncFunctionDef' | `def visit_AsyncFunctionDef(self, node):` |
| `62` | Warning | PY_TYPING | Missing return type hint for function 'visit_ExceptHandler' | `def visit_ExceptHandler(self, node):` |
| `62` | Warning | PY_TYPING | Missing type hint for argument 'node' in function 'visit_ExceptHandler' | `def visit_ExceptHandler(self, node):` |
| `69` | Warning | PY_TYPING | Missing return type hint for function 'visit_Global' | `def visit_Global(self, node):` |
| `69` | Warning | PY_TYPING | Missing type hint for argument 'node' in function 'visit_Global' | `def visit_Global(self, node):` |
| `73` | Warning | PY_TYPING | Missing return type hint for function 'visit_Call' | `def visit_Call(self, node):` |
| `73` | Warning | PY_TYPING | Missing type hint for argument 'node' in function 'visit_Call' | `def visit_Call(self, node):` |
| `79` | Warning | PY_TYPING | Missing return type hint for function 'analyze_python' | `def analyze_python(path, lines, content):` |
| `79` | Warning | PY_TYPING | Missing type hint for argument 'path' in function 'analyze_python' | `def analyze_python(path, lines, content):` |
| `79` | Warning | PY_TYPING | Missing type hint for argument 'lines' in function 'analyze_python' | `def analyze_python(path, lines, content):` |
| `79` | Warning | PY_TYPING | Missing type hint for argument 'content' in function 'analyze_python' | `def analyze_python(path, lines, content):` |
| `95` | Warning | PY_TYPING | Missing return type hint for function 'analyze_go' | `def analyze_go(path, lines):` |
| `95` | Warning | PY_TYPING | Missing type hint for argument 'path' in function 'analyze_go' | `def analyze_go(path, lines):` |
| `95` | Warning | PY_TYPING | Missing type hint for argument 'lines' in function 'analyze_go' | `def analyze_go(path, lines):` |
| `124` | Warning | PY_TYPING | Missing return type hint for function 'analyze_shell' | `def analyze_shell(path, lines):` |
| `124` | Warning | PY_TYPING | Missing type hint for argument 'path' in function 'analyze_shell' | `def analyze_shell(path, lines):` |
| `124` | Warning | PY_TYPING | Missing type hint for argument 'lines' in function 'analyze_shell' | `def analyze_shell(path, lines):` |
| `147` | Warning | PY_TYPING | Missing return type hint for function 'analyze_frontend_iac' | `def analyze_frontend_iac(path, lines):` |
| `147` | Warning | PY_TYPING | Missing type hint for argument 'path' in function 'analyze_frontend_iac' | `def analyze_frontend_iac(path, lines):` |
| `147` | Warning | PY_TYPING | Missing type hint for argument 'lines' in function 'analyze_frontend_iac' | `def analyze_frontend_iac(path, lines):` |
| `175` | Warning | PY_TYPING | Missing return type hint for function 'tokenize_code' | `def tokenize_code(content, ext):` |
| `175` | Warning | PY_TYPING | Missing type hint for argument 'content' in function 'tokenize_code' | `def tokenize_code(content, ext):` |
| `175` | Warning | PY_TYPING | Missing type hint for argument 'ext' in function 'tokenize_code' | `def tokenize_code(content, ext):` |
| `188` | Warning | PY_TYPING | Missing return type hint for function 'extract_blocks' | `def extract_blocks(path, lines, ext):` |
| `188` | Warning | PY_TYPING | Missing type hint for argument 'path' in function 'extract_blocks' | `def extract_blocks(path, lines, ext):` |
| `188` | Warning | PY_TYPING | Missing type hint for argument 'lines' in function 'extract_blocks' | `def extract_blocks(path, lines, ext):` |
| `188` | Warning | PY_TYPING | Missing type hint for argument 'ext' in function 'extract_blocks' | `def extract_blocks(path, lines, ext):` |
| `206` | Warning | PY_TYPING | Missing return type hint for function 'main' | `def main():` |
| `207` | Warning | PY_GLOBAL | Implicit global declaration: files_analyzed, total_anomalies | `global files_analyzed, total_anomalies` |

---

### Module: `scripts/dep_report.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `145` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except (ValueError, IndexError):` |

---

### Module: `scripts/migrate_bridge_tokens.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `75` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except (json.JSONDecodeError, UnicodeDecodeError):` |
| `107` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except (json.JSONDecodeError, UnicodeDecodeError):` |

---

### Module: `scripts/render-env.sh`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `32` | Warning | SH_UNQUOTED_VAR | Unquoted variable detected | `INFRADIR="$ROOT/$INFRADIR_REL"` |
| `34` | Warning | SH_UNQUOTED_VAR | Unquoted variable detected | `echo "Missing template: $TEMPLATE" >&2` |
| `53` | Warning | SH_UNQUOTED_VAR | Unquoted variable detected | `echo "No terraform state in $dir; pass --json-file with output JSON." >&2` |
| `63` | Warning | SH_UNQUOTED_VAR | Unquoted variable detected | `*) echo "Unknown --cloud $CLOUD" >&2 ; exit 2 ;;` |

---

### Module: `server.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `76` | Warning | PY_GLOBAL | Implicit global declaration: engine | `global engine` |

---

### Module: `src/nce-netbox-plugin/nce_netbox_plugin/api/views.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `22` | Warning | PY_TYPING | Missing return type hint for function 'get' | `def get(self, request, *args, **kwargs):` |
| `22` | Warning | PY_TYPING | Missing type hint for argument 'request' in function 'get' | `def get(self, request, *args, **kwargs):` |
| `78` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |

---

### Module: `src/nce-netbox-plugin/nce_netbox_plugin/template_content.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `15` | Warning | PY_TYPING | Missing return type hint for function 'render_cognitive_panel' | `def render_cognitive_panel(self, object_type: str):` |
| `35` | Warning | PY_TYPING | Missing return type hint for function 'left_page' | `def left_page(self):` |
| `43` | Warning | PY_TYPING | Missing return type hint for function 'right_page' | `def right_page(self):` |
| `51` | Warning | PY_TYPING | Missing return type hint for function 'full_width_page' | `def full_width_page(self):` |

---

### Module: `start_worker.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `22` | Warning | PY_TYPING | Missing return type hint for function 'start_worker' | `def start_worker():` |

---

### Module: `tests/conftest.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `42` | Warning | PY_TYPING | Missing return type hint for function '_inject_mcp_tenant_api_key_for_tool_calls' | `def _inject_mcp_tenant_api_key_for_tool_calls(monkeypatch):` |
| `42` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function '_inject_mcp_tenant_api_key_for_tool_calls' | `def _inject_mcp_tenant_api_key_for_tool_calls(monkeypatch):` |
| `210` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `218` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `435` | Warning | PY_TYPING | Missing return type hint for async function 'make_namespace' | `async def make_namespace(pg_pool: asyncpg.Pool):` |

---

### Module: `tests/fixtures/fake_asyncpg.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `45` | Warning | PY_TYPING | Missing return type hint for function '__await__' | `def __await__(self):` |

---

### Module: `tests/test_a2a_mcp_handlers.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `88` | Warning | PY_TYPING | Missing return type hint for function '_unwrap' | `def _unwrap(handler):  # noqa: ANN001` |
| `88` | Warning | PY_TYPING | Missing type hint for argument 'handler' in function '_unwrap' | `def _unwrap(handler):  # noqa: ANN001` |

---

### Module: `tests/test_active_learning.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `21` | Warning | PY_TYPING | Missing return type hint for function 'mock_pg_pool' | `def mock_pg_pool():` |
| `41` | Warning | PY_TYPING | Missing return type hint for function 'mock_mongo_client' | `def mock_mongo_client():` |
| `56` | Warning | PY_TYPING | Missing return type hint for function 'mock_redis_client' | `def mock_redis_client():` |
| `64` | Warning | PY_TYPING | Missing return type hint for function 'orchestrator' | `def orchestrator(mock_pg_pool, mock_mongo_client, mock_redis_client):` |
| `64` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in function 'orchestrator' | `def orchestrator(mock_pg_pool, mock_mongo_client, mock_redis_client):` |
| `64` | Warning | PY_TYPING | Missing type hint for argument 'mock_mongo_client' in function 'orchestrator' | `def orchestrator(mock_pg_pool, mock_mongo_client, mock_redis_client):` |
| `64` | Warning | PY_TYPING | Missing type hint for argument 'mock_redis_client' in function 'orchestrator' | `def orchestrator(mock_pg_pool, mock_mongo_client, mock_redis_client):` |
| `82` | Warning | PY_TYPING | Missing return type hint for async function 'test_store_memory_bypasses_quarantine_for_high_confidence' | `async def test_store_memory_bypasses_quarantine_for_high_confidence(` |
| `82` | Warning | PY_TYPING | Missing type hint for argument 'orchestrator' in async function 'test_store_memory_bypasses_quarantine_for_high_confidence' | `async def test_store_memory_bypasses_quarantine_for_high_confidence(` |
| `82` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_store_memory_bypasses_quarantine_for_high_confidence' | `async def test_store_memory_bypasses_quarantine_for_high_confidence(` |
| `82` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_store_memory_bypasses_quarantine_for_high_confidence' | `async def test_store_memory_bypasses_quarantine_for_high_confidence(` |
| `126` | Warning | PY_TYPING | Missing return type hint for async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `126` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `126` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `140` | Warning | PY_TYPING | Missing return type hint for async function 'test_store_memory_quarantines_low_confidence' | `async def test_store_memory_quarantines_low_confidence(` |
| `140` | Warning | PY_TYPING | Missing type hint for argument 'orchestrator' in async function 'test_store_memory_quarantines_low_confidence' | `async def test_store_memory_quarantines_low_confidence(` |
| `140` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_store_memory_quarantines_low_confidence' | `async def test_store_memory_quarantines_low_confidence(` |
| `140` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_store_memory_quarantines_low_confidence' | `async def test_store_memory_quarantines_low_confidence(` |
| `161` | Warning | PY_TYPING | Missing return type hint for async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `161` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `161` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `180` | Warning | PY_TYPING | Missing return type hint for async function 'test_store_memory_parent_decay_check' | `async def test_store_memory_parent_decay_check(` |
| `180` | Warning | PY_TYPING | Missing type hint for argument 'orchestrator' in async function 'test_store_memory_parent_decay_check' | `async def test_store_memory_parent_decay_check(` |
| `180` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_store_memory_parent_decay_check' | `async def test_store_memory_parent_decay_check(` |
| `180` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_store_memory_parent_decay_check' | `async def test_store_memory_parent_decay_check(` |
| `210` | Warning | PY_TYPING | Missing return type hint for async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `210` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `210` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `229` | Warning | PY_TYPING | Missing return type hint for async function 'test_confirm_memory_promotes_and_updates_queue' | `async def test_confirm_memory_promotes_and_updates_queue(` |
| `229` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_confirm_memory_promotes_and_updates_queue' | `async def test_confirm_memory_promotes_and_updates_queue(` |
| `229` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_confirm_memory_promotes_and_updates_queue' | `async def test_confirm_memory_promotes_and_updates_queue(` |
| `247` | Warning | PY_TYPING | Missing return type hint for async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `247` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `247` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `274` | Warning | PY_TYPING | Missing return type hint for async function 'test_reject_memory_updates_status' | `async def test_reject_memory_updates_status(` |
| `274` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_reject_memory_updates_status' | `async def test_reject_memory_updates_status(` |
| `274` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_reject_memory_updates_status' | `async def test_reject_memory_updates_status(` |
| `282` | Warning | PY_TYPING | Missing return type hint for async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `282` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `282` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `296` | Warning | PY_TYPING | Missing return type hint for async function 'test_get_gamified_stats_computes_correctly' | `async def test_get_gamified_stats_computes_correctly(` |
| `296` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_get_gamified_stats_computes_correctly' | `async def test_get_gamified_stats_computes_correctly(` |
| `296` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_get_gamified_stats_computes_correctly' | `async def test_get_gamified_stats_computes_correctly(` |
| `321` | Warning | PY_TYPING | Missing return type hint for async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `321` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `321` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `344` | Warning | PY_TYPING | Missing return type hint for async function 'test_get_gamified_stats_custom_xp_config' | `async def test_get_gamified_stats_custom_xp_config(` |
| `344` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_get_gamified_stats_custom_xp_config' | `async def test_get_gamified_stats_custom_xp_config(` |
| `344` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_get_gamified_stats_custom_xp_config' | `async def test_get_gamified_stats_custom_xp_config(` |
| `362` | Warning | PY_TYPING | Missing return type hint for async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `362` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `362` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |

---

### Module: `tests/test_admin_cognitive_fleet.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `01` | Error | PY_SYNTAX | Syntax error: invalid non-printable character U+FEFF | `﻿"""Tests for cognitive (salience-map, LLM payload) and fleet admin helpers."""` |

---

### Module: `tests/test_admin_datastores_config.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `01` | Error | PY_SYNTAX | Syntax error: invalid non-printable character U+FEFF | `﻿"""Tests for Datastore Connection Parameters Config REST Endpoints."""` |

---

### Module: `tests/test_admin_db_explorers.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `17` | Warning | PY_TYPING | Missing return type hint for function 'mock_admin_engine' | `def mock_admin_engine():` |
| `75` | Warning | PY_TYPING | Missing return type hint for async function 'test_postgres_status_endpoint' | `async def test_postgres_status_endpoint(mock_admin_engine):` |
| `75` | Warning | PY_TYPING | Missing type hint for argument 'mock_admin_engine' in async function 'test_postgres_status_endpoint' | `async def test_postgres_status_endpoint(mock_admin_engine):` |
| `94` | Warning | PY_TYPING | Missing return type hint for async function 'test_mongo_status_endpoint' | `async def test_mongo_status_endpoint(mock_admin_engine):` |
| `94` | Warning | PY_TYPING | Missing type hint for argument 'mock_admin_engine' in async function 'test_mongo_status_endpoint' | `async def test_mongo_status_endpoint(mock_admin_engine):` |
| `111` | Warning | PY_TYPING | Missing return type hint for async function 'test_redis_status_endpoint' | `async def test_redis_status_endpoint(mock_admin_engine):` |
| `111` | Warning | PY_TYPING | Missing type hint for argument 'mock_admin_engine' in async function 'test_redis_status_endpoint' | `async def test_redis_status_endpoint(mock_admin_engine):` |
| `130` | Warning | PY_TYPING | Missing return type hint for async function 'test_minio_status_endpoint' | `async def test_minio_status_endpoint(mock_admin_engine):` |
| `130` | Warning | PY_TYPING | Missing type hint for argument 'mock_admin_engine' in async function 'test_minio_status_endpoint' | `async def test_minio_status_endpoint(mock_admin_engine):` |
| `148` | Warning | PY_TYPING | Missing return type hint for async function 'test_connectors_status_endpoint' | `async def test_connectors_status_endpoint():` |
| `182` | Warning | PY_TYPING | Missing return type hint for async function 'test_endpoints_unconnected_fallbacks' | `async def test_endpoints_unconnected_fallbacks():` |

---

### Module: `tests/test_admin_dotenv_persist.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `23` | Warning | PY_TYPING | Missing type hint for argument 'tmp_path' in function 'test_update_dotenv_atomic_write' | `def test_update_dotenv_atomic_write(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:` |

---

### Module: `tests/test_admin_namespaces.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `17` | Warning | PY_TYPING | Missing return type hint for async function 'test_api_admin_namespaces_list' | `async def test_api_admin_namespaces_list():` |
| `72` | Warning | PY_TYPING | Missing return type hint for async function 'test_api_admin_namespaces_get' | `async def test_api_admin_namespaces_get():` |
| `112` | Warning | PY_TYPING | Missing return type hint for async function 'test_api_admin_namespaces_get_not_found' | `async def test_api_admin_namespaces_get_not_found():` |
| `137` | Warning | PY_TYPING | Missing return type hint for async function 'test_api_admin_namespaces_update_metadata' | `async def test_api_admin_namespaces_update_metadata():` |
| `155` | Warning | PY_TYPING | Missing return type hint for async function 'receive' | `async def receive():` |
| `191` | Warning | PY_TYPING | Missing return type hint for async function 'test_api_admin_namespaces_update_metadata_invalid_pydantic' | `async def test_api_admin_namespaces_update_metadata_invalid_pydantic():` |
| `201` | Warning | PY_TYPING | Missing return type hint for async function 'receive' | `async def receive():` |

---

### Module: `tests/test_admin_rate_limiting.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `11` | Warning | PY_TYPING | Missing return type hint for async function 'test_rate_limit_error_properties' | `async def test_rate_limit_error_properties():` |
| `21` | Warning | PY_TYPING | Missing type hint for argument 'redis_client' in function '__init__' | `def __init__(self, redis_client=None):` |
| `26` | Warning | PY_TYPING | Missing return type hint for async function 'test_admin_rate_limit_within_limit' | `async def test_admin_rate_limit_within_limit():` |
| `34` | Warning | PY_TYPING | Missing return type hint for async function 'sample_tool' | `async def sample_tool(engine_inst, arguments):` |
| `34` | Warning | PY_TYPING | Missing type hint for argument 'engine_inst' in async function 'sample_tool' | `async def sample_tool(engine_inst, arguments):` |
| `34` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'sample_tool' | `async def sample_tool(engine_inst, arguments):` |
| `44` | Warning | PY_TYPING | Missing return type hint for async function 'test_admin_rate_limit_exceeded_local_fallback' | `async def test_admin_rate_limit_exceeded_local_fallback():` |
| `50` | Warning | PY_TYPING | Missing return type hint for async function 'sample_tool' | `async def sample_tool(engine_inst, arguments):` |
| `50` | Warning | PY_TYPING | Missing type hint for argument 'engine_inst' in async function 'sample_tool' | `async def sample_tool(engine_inst, arguments):` |
| `50` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'sample_tool' | `async def sample_tool(engine_inst, arguments):` |
| `67` | Warning | PY_TYPING | Missing return type hint for async function 'test_admin_rate_limit_key_resolution' | `async def test_admin_rate_limit_key_resolution():` |
| `77` | Warning | PY_TYPING | Missing return type hint for async function 'sample_tool' | `async def sample_tool(engine_inst, arguments, admin_identity=None):` |
| `77` | Warning | PY_TYPING | Missing type hint for argument 'engine_inst' in async function 'sample_tool' | `async def sample_tool(engine_inst, arguments, admin_identity=None):` |
| `77` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'sample_tool' | `async def sample_tool(engine_inst, arguments, admin_identity=None):` |
| `77` | Warning | PY_TYPING | Missing type hint for argument 'admin_identity' in async function 'sample_tool' | `async def sample_tool(engine_inst, arguments, admin_identity=None):` |
| `106` | Warning | PY_TYPING | Missing return type hint for async function 'test_admin_rate_limit_redis_success' | `async def test_admin_rate_limit_redis_success():` |
| `114` | Warning | PY_TYPING | Missing return type hint for async function 'sample_tool' | `async def sample_tool(engine_inst, arguments):` |
| `114` | Warning | PY_TYPING | Missing type hint for argument 'engine_inst' in async function 'sample_tool' | `async def sample_tool(engine_inst, arguments):` |
| `114` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'sample_tool' | `async def sample_tool(engine_inst, arguments):` |
| `124` | Warning | PY_TYPING | Missing return type hint for async function 'test_admin_rate_limit_redis_exceeded' | `async def test_admin_rate_limit_redis_exceeded():` |
| `132` | Warning | PY_TYPING | Missing return type hint for async function 'sample_tool' | `async def sample_tool(engine_inst, arguments):` |
| `132` | Warning | PY_TYPING | Missing type hint for argument 'engine_inst' in async function 'sample_tool' | `async def sample_tool(engine_inst, arguments):` |
| `132` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'sample_tool' | `async def sample_tool(engine_inst, arguments):` |
| `142` | Warning | PY_TYPING | Missing return type hint for async function 'test_admin_rate_limit_redis_failure_falls_back_to_ram' | `async def test_admin_rate_limit_redis_failure_falls_back_to_ram():` |
| `151` | Warning | PY_TYPING | Missing return type hint for async function 'sample_tool' | `async def sample_tool(engine_inst, arguments):` |
| `151` | Warning | PY_TYPING | Missing type hint for argument 'engine_inst' in async function 'sample_tool' | `async def sample_tool(engine_inst, arguments):` |
| `151` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'sample_tool' | `async def sample_tool(engine_inst, arguments):` |
| `163` | Warning | PY_TYPING | Missing return type hint for async function 'test_server_call_tool_translates_rate_limit_error' | `async def test_server_call_tool_translates_rate_limit_error():` |

---

### Module: `tests/test_admin_routes_audit.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `01` | Error | PY_SYNTAX | Syntax error: invalid non-printable character U+FEFF | `﻿"""Admin list validation, pagination bounds, and handler security filters."""` |

---

### Module: `tests/test_admin_verify_chain.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `16` | Warning | PY_TYPING | Missing return type hint for function 'mock_engine' | `def mock_engine():` |
| `29` | Warning | PY_TYPING | Missing return type hint for async function 'test_verify_chain_valid' | `async def test_verify_chain_valid(mock_engine):` |
| `29` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_verify_chain_valid' | `async def test_verify_chain_valid(mock_engine):` |
| `66` | Warning | PY_TYPING | Missing return type hint for async function 'test_verify_chain_corrupted' | `async def test_verify_chain_corrupted(mock_engine):` |
| `66` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_verify_chain_corrupted' | `async def test_verify_chain_corrupted(mock_engine):` |
| `103` | Warning | PY_TYPING | Missing return type hint for async function 'test_verify_chain_invalid_namespace' | `async def test_verify_chain_invalid_namespace(mock_engine):` |
| `103` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_verify_chain_invalid_namespace' | `async def test_verify_chain_invalid_namespace(mock_engine):` |
| `127` | Warning | PY_TYPING | Missing return type hint for async function 'test_verify_chain_missing_namespace' | `async def test_verify_chain_missing_namespace():` |
| `149` | Warning | PY_TYPING | Missing return type hint for async function 'test_verify_chain_engine_not_connected' | `async def test_verify_chain_engine_not_connected():` |

---

### Module: `tests/test_artifact_standardization.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `08` | Warning | PY_TYPING | Missing return type hint for async function 'test_store_artifact_delegation' | `async def test_store_artifact_delegation():` |
| `23` | Warning | PY_TYPING | Missing return type hint for async function 'test_orchestrator_artifact_alias' | `async def test_orchestrator_artifact_alias():` |

---

### Module: `tests/test_ast_parser_languages.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `05` | Warning | PY_TYPING | Missing return type hint for function 'test_java_parsing' | `def test_java_parsing():` |
| `27` | Warning | PY_TYPING | Missing return type hint for function 'test_elixir_parsing_dynamic' | `def test_elixir_parsing_dynamic():` |
| `51` | Warning | PY_TYPING | Missing return type hint for function 'test_zig_parsing' | `def test_zig_parsing():` |
| `66` | Warning | PY_TYPING | Missing return type hint for function 'test_fallback_unsupported' | `def test_fallback_unsupported():` |
| `74` | Warning | PY_TYPING | Missing return type hint for function 'test_semantic_fallback_chunking' | `def test_semantic_fallback_chunking():` |

---

### Module: `tests/test_audit_p0_hardening.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `01` | Error | PY_SYNTAX | Syntax error: invalid non-printable character U+FEFF | `﻿"""Regression tests for production-readiness audit P0/P1 hardening."""` |

---

### Module: `tests/test_auth.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `502` | Warning | PY_TYPING | Missing return type hint for async function 'set_side_effect' | `async def set_side_effect(key, value, **kwargs):` |
| `502` | Warning | PY_TYPING | Missing type hint for argument 'key' in async function 'set_side_effect' | `async def set_side_effect(key, value, **kwargs):` |
| `502` | Warning | PY_TYPING | Missing type hint for argument 'value' in async function 'set_side_effect' | `async def set_side_effect(key, value, **kwargs):` |
| `602` | Warning | PY_TYPING | Missing return type hint for async function 'shared_set' | `async def shared_set(key, value, **kwargs):` |
| `602` | Warning | PY_TYPING | Missing type hint for argument 'key' in async function 'shared_set' | `async def shared_set(key, value, **kwargs):` |
| `602` | Warning | PY_TYPING | Missing type hint for argument 'value' in async function 'shared_set' | `async def shared_set(key, value, **kwargs):` |
| `795` | Warning | PY_TYPING | Missing return type hint for async function '_tracked_append' | `async def _tracked_append(**kwargs):` |
| `798` | Warning | PY_TYPING | Missing return type hint for async function '_tracked_set_ctx' | `async def _tracked_set_ctx(conn, ns):` |
| `798` | Warning | PY_TYPING | Missing type hint for argument 'conn' in async function '_tracked_set_ctx' | `async def _tracked_set_ctx(conn, ns):` |
| `798` | Warning | PY_TYPING | Missing type hint for argument 'ns' in async function '_tracked_set_ctx' | `async def _tracked_set_ctx(conn, ns):` |
| `994` | Warning | PY_TYPING | Missing return type hint for function 'acquire_side_effect' | `def acquire_side_effect(*_args, **_kwargs):` |
| `1050` | Warning | PY_TYPING | Missing return type hint for async function '_tracked_write' | `async def _tracked_write(*args, **kwargs):` |
| `1053` | Warning | PY_TYPING | Missing return type hint for async function '_tracked_set_ctx' | `async def _tracked_set_ctx(conn, ns):` |
| `1053` | Warning | PY_TYPING | Missing type hint for argument 'conn' in async function '_tracked_set_ctx' | `async def _tracked_set_ctx(conn, ns):` |
| `1053` | Warning | PY_TYPING | Missing type hint for argument 'ns' in async function '_tracked_set_ctx' | `async def _tracked_set_ctx(conn, ns):` |
| `1115` | Warning | PY_TYPING | Missing return type hint for async function '_tracked_write' | `async def _tracked_write(*args, **kwargs):` |
| `1144` | Warning | PY_TYPING | Missing return type hint for async function '_tracked_write' | `async def _tracked_write(*args, **kwargs):` |
| `1314` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_admin_override_bypasses_check' | `def test_admin_override_bypasses_check(self, monkeypatch) -> None:` |
| `1319` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_missing_server_key_raises' | `def test_missing_server_key_raises(self, monkeypatch) -> None:` |
| `1325` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_missing_server_key_fails_closed_without_cfg_fallback' | `def test_missing_server_key_fails_closed_without_cfg_fallback(self, monkeypatch) -> None:` |
| `1335` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_missing_client_key_raises' | `def test_missing_client_key_raises(self, monkeypatch) -> None:` |
| `1341` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_empty_client_key_raises' | `def test_empty_client_key_raises(self, monkeypatch) -> None:` |
| `1347` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_wrong_client_key_raises' | `def test_wrong_client_key_raises(self, monkeypatch) -> None:` |
| `1353` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_correct_key_passes' | `def test_correct_key_passes(self, monkeypatch) -> None:` |
| `1359` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_tenant_scope_requires_key_when_server_key_set' | `def test_tenant_scope_requires_key_when_server_key_set(self, monkeypatch) -> None:` |
| `1367` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_tenant_scope_passes_without_server_key_in_dev' | `def test_tenant_scope_passes_without_server_key_in_dev(self, monkeypatch) -> None:` |
| `1379` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_tenant_tool_requires_mcp_key' | `def test_tenant_tool_requires_mcp_key(self, monkeypatch) -> None:` |
| `1385` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_admin_tool_requires_admin_key' | `def test_admin_tool_requires_admin_key(self, monkeypatch) -> None:` |
| `1395` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_tenant_namespace_injected_when_bound' | `def test_tenant_namespace_injected_when_bound(self, monkeypatch) -> None:` |
| `1403` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_tenant_namespace_mismatch_rejected' | `def test_tenant_namespace_mismatch_rejected(self, monkeypatch) -> None:` |
| `1415` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_admin_tool_skips_namespace_binding' | `def test_admin_tool_skips_namespace_binding(self, monkeypatch) -> None:` |
| `1427` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_admin_scope_passes_with_valid_key' | `async def test_admin_scope_passes_with_valid_key(self, monkeypatch) -> None:` |
| `1431` | Warning | PY_TYPING | Missing return type hint for async function 'handler' | `async def handler(engine, arguments, **kwargs):` |
| `1431` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'handler' | `async def handler(engine, arguments, **kwargs):` |
| `1431` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'handler' | `async def handler(engine, arguments, **kwargs):` |
| `1438` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_admin_scope_fails_without_key' | `async def test_admin_scope_fails_without_key(self, monkeypatch) -> None:` |
| `1442` | Warning | PY_TYPING | Missing return type hint for async function 'handler' | `async def handler(engine, arguments):` |
| `1442` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'handler' | `async def handler(engine, arguments):` |
| `1442` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'handler' | `async def handler(engine, arguments):` |
| `1449` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_strips_auth_keys_from_arguments' | `async def test_strips_auth_keys_from_arguments(self, monkeypatch) -> None:` |
| `1453` | Warning | PY_TYPING | Missing return type hint for async function 'handler' | `async def handler(engine, arguments):` |
| `1453` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'handler' | `async def handler(engine, arguments):` |
| `1453` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'handler' | `async def handler(engine, arguments):` |
| `1465` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_forwards_admin_identity_as_kwarg' | `async def test_forwards_admin_identity_as_kwarg(self, monkeypatch) -> None:` |
| `1469` | Warning | PY_TYPING | Missing return type hint for async function 'handler' | `async def handler(engine, arguments, admin_identity=None):` |
| `1469` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'handler' | `async def handler(engine, arguments, admin_identity=None):` |
| `1469` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'handler' | `async def handler(engine, arguments, admin_identity=None):` |
| `1469` | Warning | PY_TYPING | Missing type hint for argument 'admin_identity' in async function 'handler' | `async def handler(engine, arguments, admin_identity=None):` |
| `1479` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_admin_identity_not_in_cleaned_args' | `async def test_admin_identity_not_in_cleaned_args(self, monkeypatch) -> None:` |
| `1483` | Warning | PY_TYPING | Missing return type hint for async function 'handler' | `async def handler(engine, arguments, admin_identity=None):` |
| `1483` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'handler' | `async def handler(engine, arguments, admin_identity=None):` |
| `1483` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'handler' | `async def handler(engine, arguments, admin_identity=None):` |
| `1483` | Warning | PY_TYPING | Missing type hint for argument 'admin_identity' in async function 'handler' | `async def handler(engine, arguments, admin_identity=None):` |
| `1495` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_handler_without_admin_identity_param_works' | `async def test_handler_without_admin_identity_param_works(self, monkeypatch) -> None:` |
| `1499` | Warning | PY_TYPING | Missing return type hint for async function 'handler' | `async def handler(engine, arguments):` |
| `1499` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'handler' | `async def handler(engine, arguments):` |
| `1499` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'handler' | `async def handler(engine, arguments):` |
| `1509` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_positional_more_than_two_args' | `async def test_positional_more_than_two_args(self, monkeypatch) -> None:` |
| `1513` | Warning | PY_TYPING | Missing return type hint for async function 'handler' | `async def handler(engine, arguments, extra):` |
| `1513` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'handler' | `async def handler(engine, arguments, extra):` |
| `1513` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'handler' | `async def handler(engine, arguments, extra):` |
| `1513` | Warning | PY_TYPING | Missing type hint for argument 'extra' in async function 'handler' | `async def handler(engine, arguments, extra):` |
| `1522` | Warning | PY_TYPING | Missing return type hint for async function 'my_handler' | `async def my_handler(engine, arguments):` |
| `1522` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'my_handler' | `async def my_handler(engine, arguments):` |
| `1522` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'my_handler' | `async def my_handler(engine, arguments):` |
| `1644` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_plaintext_rejected_in_production' | `def test_plaintext_rejected_in_production(self, monkeypatch) -> None:` |

---

### Module: `tests/test_backfill_chain_hash.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `66` | Warning | PY_TYPING | Missing return type hint for function 'test_genesis_event_matches_append_event' | `def test_genesis_event_matches_append_event(self):` |
| `72` | Warning | PY_TYPING | Missing return type hint for function 'test_second_event_links_to_first' | `def test_second_event_links_to_first(self):` |
| `83` | Warning | PY_TYPING | Missing return type hint for function 'test_different_params_yield_different_hash' | `def test_different_params_yield_different_hash(self):` |
| `92` | Warning | PY_TYPING | Missing return type hint for function 'test_parent_event_id_included' | `def test_parent_event_id_included(self):` |
| `107` | Warning | PY_TYPING | Missing return type hint for async function 'test_backfills_null_chain_hashes' | `async def test_backfills_null_chain_hashes(self):` |
| `123` | Warning | PY_TYPING | Missing return type hint for async function 'test_skips_rows_with_correct_hash' | `async def test_skips_rows_with_correct_hash(self):` |
| `144` | Warning | PY_TYPING | Missing return type hint for async function 'test_empty_namespace_no_updates' | `async def test_empty_namespace_no_updates(self):` |
| `159` | Warning | PY_TYPING | Missing return type hint for function 'test_none_returns_none' | `def test_none_returns_none(self):` |
| `162` | Warning | PY_TYPING | Missing return type hint for function 'test_bytes_returns_bytes' | `def test_bytes_returns_bytes(self):` |
| `166` | Warning | PY_TYPING | Missing return type hint for function 'test_memoryview_returns_bytes' | `def test_memoryview_returns_bytes(self):` |
| `170` | Warning | PY_TYPING | Missing return type hint for function 'test_str_returns_none' | `def test_str_returns_none(self):` |

---

### Module: `tests/test_background_task_manager.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `27` | Warning | PY_TYPING | Missing return type hint for async function 'test_create_tracked_task_success' | `async def test_create_tracked_task_success():` |
| `31` | Warning | PY_TYPING | Missing return type hint for async function 'my_task' | `async def my_task():` |
| `49` | Warning | PY_TYPING | Missing return type hint for async function 'test_create_tracked_task_exception_logged' | `async def test_create_tracked_task_exception_logged(caplog):` |
| `49` | Warning | PY_TYPING | Missing type hint for argument 'caplog' in async function 'test_create_tracked_task_exception_logged' | `async def test_create_tracked_task_exception_logged(caplog):` |
| `52` | Warning | PY_TYPING | Missing return type hint for async function 'failing_task' | `async def failing_task():` |
| `66` | Warning | PY_TYPING | Missing return type hint for async function 'test_create_tracked_task_exception_metrics' | `async def test_create_tracked_task_exception_metrics(monkeypatch):` |
| `66` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_create_tracked_task_exception_metrics' | `async def test_create_tracked_task_exception_metrics(monkeypatch):` |
| `79` | Warning | PY_TYPING | Missing return type hint for async function 'failing_task' | `async def failing_task():` |
| `93` | Warning | PY_TYPING | Missing return type hint for async function 'test_create_tracked_task_cancelled' | `async def test_create_tracked_task_cancelled():` |
| `96` | Warning | PY_TYPING | Missing return type hint for async function 'long_task' | `async def long_task():` |
| `105` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except asyncio.CancelledError:` |
| `118` | Warning | PY_TYPING | Missing return type hint for async function 'test_get_active_background_tasks' | `async def test_get_active_background_tasks():` |
| `121` | Warning | PY_TYPING | Missing return type hint for async function 'slow_task' | `async def slow_task():` |
| `138` | Warning | PY_TYPING | Missing return type hint for async function 'test_get_active_background_tasks_filtered' | `async def test_get_active_background_tasks_filtered():` |
| `141` | Warning | PY_TYPING | Missing return type hint for async function 'task_a' | `async def task_a():` |
| `144` | Warning | PY_TYPING | Missing return type hint for async function 'task_b' | `async def task_b():` |
| `162` | Warning | PY_TYPING | Missing return type hint for async function 'test_get_background_task_stats' | `async def test_get_background_task_stats():` |
| `165` | Warning | PY_TYPING | Missing return type hint for async function 'quick_task' | `async def quick_task():` |
| `182` | Warning | PY_TYPING | Missing return type hint for async function 'test_task_duration_recorded' | `async def test_task_duration_recorded():` |
| `186` | Warning | PY_TYPING | Missing return type hint for async function 'timed_task' | `async def timed_task():` |
| `199` | Warning | PY_TYPING | Missing return type hint for async function 'test_multiple_tasks_with_same_name' | `async def test_multiple_tasks_with_same_name():` |
| `202` | Warning | PY_TYPING | Missing return type hint for async function 'task_gen' | `async def task_gen():` |
| `218` | Warning | PY_TYPING | Missing return type hint for async function 'test_task_exception_with_custom_name' | `async def test_task_exception_with_custom_name():` |
| `224` | Warning | PY_TYPING | Missing return type hint for async function 'fork_task' | `async def fork_task():` |
| `240` | Warning | PY_TYPING | Missing return type hint for async function 'test_background_task_reraises_to_done_callback' | `async def test_background_task_reraises_to_done_callback(caplog):` |
| `240` | Warning | PY_TYPING | Missing type hint for argument 'caplog' in async function 'test_background_task_reraises_to_done_callback' | `async def test_background_task_reraises_to_done_callback(caplog):` |
| `246` | Warning | PY_TYPING | Missing return type hint for async function 'failing_coro' | `async def failing_coro():` |

---

### Module: `tests/test_bridge_renewal.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `276` | Warning | PY_TYPING | Missing return type hint for async function 'test_acquire_refresh_lock_success' | `async def test_acquire_refresh_lock_success():` |
| `293` | Warning | PY_TYPING | Missing return type hint for async function 'test_acquire_refresh_lock_already_held' | `async def test_acquire_refresh_lock_already_held():` |
| `308` | Warning | PY_TYPING | Missing return type hint for async function 'test_release_refresh_lock_closes_client' | `async def test_release_refresh_lock_closes_client():` |
| `320` | Warning | PY_TYPING | Missing return type hint for async function 'test_release_refresh_lock_none_client_is_noop' | `async def test_release_refresh_lock_none_client_is_noop():` |

---

### Module: `tests/test_cad_ext_security.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `10` | Warning | PY_TYPING | Missing return type hint for function '_text_entity' | `def _text_entity():` |
| `17` | Warning | PY_TYPING | Missing return type hint for function 'test_dxf_entity_cap_emits_warning' | `def test_dxf_entity_cap_emits_warning(monkeypatch):` |
| `17` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_dxf_entity_cap_emits_warning' | `def test_dxf_entity_cap_emits_warning(monkeypatch):` |

---

### Module: `tests/test_check_admin_hardening.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `28` | Warning | PY_TYPING | Missing return type hint for function 'setUp' | `def setUp(self):` |
| `38` | Warning | PY_TYPING | Missing return type hint for function 'tearDown' | `def tearDown(self):` |
| `49` | Warning | PY_TYPING | Missing return type hint for function 'test_client_is_admin_true_rejected_when_no_key_set' | `def test_client_is_admin_true_rejected_when_no_key_set(self):` |
| `56` | Warning | PY_TYPING | Missing return type hint for function 'test_client_is_admin_true_rejected_when_wrong_key' | `def test_client_is_admin_true_rejected_when_wrong_key(self):` |
| `63` | Warning | PY_TYPING | Missing return type hint for function 'test_client_is_admin_false_with_correct_key_still_works' | `def test_client_is_admin_false_with_correct_key_still_works(self):` |
| `71` | Warning | PY_TYPING | Missing return type hint for function 'test_missing_admin_api_key_rejected' | `def test_missing_admin_api_key_rejected(self):` |
| `78` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_admin_api_key_rejected' | `def test_empty_admin_api_key_rejected(self):` |
| `85` | Warning | PY_TYPING | Missing return type hint for function 'test_whitespace_only_admin_api_key_rejected' | `def test_whitespace_only_admin_api_key_rejected(self):` |
| `94` | Warning | PY_TYPING | Missing return type hint for function 'test_wrong_admin_api_key_rejected' | `def test_wrong_admin_api_key_rejected(self):` |
| `101` | Warning | PY_TYPING | Missing return type hint for function 'test_case_sensitive_key_comparison' | `def test_case_sensitive_key_comparison(self):` |
| `108` | Warning | PY_TYPING | Missing return type hint for function 'test_timing_side_channel_uses_constant_time_compare' | `def test_timing_side_channel_uses_constant_time_compare(self):` |
| `120` | Warning | PY_TYPING | Missing return type hint for function 'test_correct_admin_api_key_grants_access' | `def test_correct_admin_api_key_grants_access(self):` |
| `126` | Warning | PY_TYPING | Missing return type hint for function 'test_correct_key_with_whitespace_stripping' | `def test_correct_key_with_whitespace_stripping(self):` |
| `133` | Warning | PY_TYPING | Missing return type hint for function 'test_override_grants_access_without_key' | `def test_override_grants_access_without_key(self):` |
| `141` | Warning | PY_TYPING | Missing return type hint for function 'test_override_works_when_api_key_not_set' | `def test_override_works_when_api_key_not_set(self):` |
| `150` | Warning | PY_TYPING | Missing return type hint for function 'test_no_key_and_no_override_fails_safe' | `def test_no_key_and_no_override_fails_safe(self):` |
| `159` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_api_key_env_var_fails_safe' | `def test_empty_api_key_env_var_fails_safe(self):` |
| `171` | Warning | PY_TYPING | Missing return type hint for function 'setUpClass' | `def setUpClass(cls):` |
| `178` | Warning | PY_TYPING | Missing return type hint for function '_get_tool' | `def _get_tool(self, name: str):` |
| `184` | Warning | PY_TYPING | Missing return type hint for function '_required_fields' | `def _required_fields(self, tool):` |
| `184` | Warning | PY_TYPING | Missing type hint for argument 'tool' in function '_required_fields' | `def _required_fields(self, tool):` |
| `187` | Warning | PY_TYPING | Missing return type hint for function '_properties' | `def _properties(self, tool):` |
| `187` | Warning | PY_TYPING | Missing type hint for argument 'tool' in function '_properties' | `def _properties(self, tool):` |
| `206` | Warning | PY_TYPING | Missing return type hint for function 'test_admin_tools_require_admin_api_key' | `def test_admin_tools_require_admin_api_key(self):` |
| `217` | Warning | PY_TYPING | Missing return type hint for function 'test_admin_tools_have_admin_api_key_property' | `def test_admin_tools_have_admin_api_key_property(self):` |
| `233` | Warning | PY_TYPING | Missing return type hint for function 'test_admin_tools_no_longer_require_is_admin' | `def test_admin_tools_no_longer_require_is_admin(self):` |
| `244` | Warning | PY_TYPING | Missing return type hint for function 'test_is_admin_absent_from_admin_tool_schemas' | `def test_is_admin_absent_from_admin_tool_schemas(self):` |
| `273` | Warning | PY_TYPING | Missing return type hint for function 'test_non_admin_tools_do_not_require_admin_api_key' | `def test_non_admin_tools_do_not_require_admin_api_key(self):` |
| `288` | Warning | PY_TYPING | Missing return type hint for function 'test_manage_namespace_argument_filtering' | `def test_manage_namespace_argument_filtering(self):` |
| `307` | Warning | PY_TYPING | Missing return type hint for function 'test_manage_quotas_argument_filtering' | `def test_manage_quotas_argument_filtering(self):` |

---

### Module: `tests/test_chunking_semantic.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `42` | Warning | PY_TYPING | Missing return type hint for function 'test_finds_fence_close_within_budget' | `def test_finds_fence_close_within_budget(self):` |
| `53` | Warning | PY_TYPING | Missing return type hint for function 'test_finds_newline_when_no_fence' | `def test_finds_newline_when_no_fence(self):` |
| `59` | Warning | PY_TYPING | Missing return type hint for function 'test_hard_cut_when_no_newline' | `def test_hard_cut_when_no_newline(self):` |
| `65` | Warning | PY_TYPING | Missing return type hint for function 'test_split_index_within_budget' | `def test_split_index_within_budget(self):` |
| `90` | Warning | PY_TYPING | Missing return type hint for function 'test_small_code_block_not_split' | `def test_small_code_block_not_split(self):` |
| `98` | Warning | PY_TYPING | Missing return type hint for function 'test_large_code_block_fences_not_orphaned' | `def test_large_code_block_fences_not_orphaned(self):` |
| `121` | Warning | PY_TYPING | Missing return type hint for function 'test_chunk_size_respects_budget' | `def test_chunk_size_respects_budget(self):` |
| `131` | Warning | PY_TYPING | Missing return type hint for function 'test_no_content_lost' | `def test_no_content_lost(self):` |
| `155` | Warning | PY_TYPING | Missing return type hint for function 'test_table_rows_not_split_mid_row' | `def test_table_rows_not_split_mid_row(self):` |
| `171` | Warning | PY_TYPING | Missing return type hint for function 'test_chunk_size_budget_respected_with_table' | `def test_chunk_size_budget_respected_with_table(self):` |
| `187` | Warning | PY_TYPING | Missing return type hint for function 'test_short_text_single_chunk' | `def test_short_text_single_chunk(self):` |
| `194` | Warning | PY_TYPING | Missing return type hint for function 'test_paragraphs_split_on_blank_lines' | `def test_paragraphs_split_on_blank_lines(self):` |
| `206` | Warning | PY_TYPING | Missing return type hint for function 'test_sections_never_merged' | `def test_sections_never_merged(self):` |
| `214` | Warning | PY_TYPING | Missing return type hint for function 'test_part_index_increments' | `def test_part_index_increments(self):` |
| `223` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_sections_skipped' | `def test_empty_sections_skipped(self):` |
| `235` | Warning | PY_TYPING | Missing return type hint for function 'test_no_overflow_on_single_long_line' | `def test_no_overflow_on_single_long_line(self):` |
| `243` | Warning | PY_TYPING | Missing return type hint for function 'test_prefers_newline_over_hard_cut' | `def test_prefers_newline_over_hard_cut(self):` |
| `250` | Warning | PY_TYPING | Missing return type hint for function 'test_no_content_lost' | `def test_no_content_lost(self):` |
| `265` | Warning | PY_TYPING | Missing return type hint for function 'test_single_h1' | `def test_single_h1(self):` |
| `270` | Warning | PY_TYPING | Missing return type hint for function 'test_h1_h2_chain' | `def test_h1_h2_chain(self):` |
| `276` | Warning | PY_TYPING | Missing return type hint for function 'test_h1_h2_h3_chain' | `def test_h1_h2_h3_chain(self):` |
| `282` | Warning | PY_TYPING | Missing return type hint for function 'test_h2_replaces_sibling' | `def test_h2_replaces_sibling(self):` |
| `288` | Warning | PY_TYPING | Missing return type hint for function 'test_h2_replaces_deeper' | `def test_h2_replaces_deeper(self):` |
| `294` | Warning | PY_TYPING | Missing return type hint for function 'test_h3_replaces_sibling_only' | `def test_h3_replaces_sibling_only(self):` |
| `300` | Warning | PY_TYPING | Missing return type hint for function 'test_h4_ignored' | `def test_h4_ignored(self):` |
| `307` | Warning | PY_TYPING | Missing return type hint for function 'test_h5_h6_ignored' | `def test_h5_h6_ignored(self):` |
| `313` | Warning | PY_TYPING | Missing return type hint for function 'test_no_headings' | `def test_no_headings(self):` |
| `318` | Warning | PY_TYPING | Missing return type hint for function 'test_heading_with_special_chars' | `def test_heading_with_special_chars(self):` |
| `324` | Warning | PY_TYPING | Missing return type hint for function 'test_leading_trailing_whitespace_stripped' | `def test_leading_trailing_whitespace_stripped(self):` |
| `330` | Warning | PY_TYPING | Missing return type hint for function 'test_setext_headings_ignored' | `def test_setext_headings_ignored(self):` |
| `345` | Warning | PY_TYPING | Missing return type hint for function 'test_single_level' | `def test_single_level(self):` |
| `349` | Warning | PY_TYPING | Missing return type hint for function 'test_two_levels' | `def test_two_levels(self):` |
| `353` | Warning | PY_TYPING | Missing return type hint for function 'test_three_levels' | `def test_three_levels(self):` |
| `357` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_list' | `def test_empty_list(self):` |
| `361` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_tuple' | `def test_empty_tuple(self):` |
| `377` | Warning | PY_TYPING | Missing return type hint for function 'test_context_prepended_to_chunk_text' | `def test_context_prepended_to_chunk_text(self):` |
| `385` | Warning | PY_TYPING | Missing return type hint for function 'test_context_not_prepended_when_disabled' | `def test_context_not_prepended_when_disabled(self):` |
| `392` | Warning | PY_TYPING | Missing return type hint for function 'test_single_level_path' | `def test_single_level_path(self):` |
| `398` | Warning | PY_TYPING | Missing return type hint for function 'test_document_path_no_context' | `def test_document_path_no_context(self):` |
| `404` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_structure_path_no_prefix' | `def test_empty_structure_path_no_prefix(self):` |
| `411` | Warning | PY_TYPING | Missing return type hint for function 'test_context_applied_to_all_parts' | `def test_context_applied_to_all_parts(self):` |
| `421` | Warning | PY_TYPING | Missing return type hint for function 'test_context_applied_across_sections' | `def test_context_applied_across_sections(self):` |
| `430` | Warning | PY_TYPING | Missing return type hint for function 'test_chunk_size_accounts_for_prefix' | `def test_chunk_size_accounts_for_prefix(self):` |
| `450` | Warning | PY_TYPING | Missing return type hint for function 'test_code_block_context_preserved' | `def test_code_block_context_preserved(self):` |

---

### Module: `tests/test_cognitive_decay.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `15` | Warning | PY_TYPING | Missing return type hint for function 'test_compute_decayed_score_half_life_halves_salience' | `def test_compute_decayed_score_half_life_halves_salience():` |
| `25` | Warning | PY_TYPING | Missing return type hint for function 'test_compute_decayed_score_zero_half_life_returns_unchanged' | `def test_compute_decayed_score_zero_half_life_returns_unchanged():` |
| `39` | Warning | PY_TYPING | Missing return type hint for function 'test_compute_decayed_score_future_updated_at_returns_unchanged' | `def test_compute_decayed_score_future_updated_at_returns_unchanged():` |
| `45` | Warning | PY_TYPING | Missing return type hint for function 'test_compute_decayed_score_naive_updated_at_assumed_utc' | `def test_compute_decayed_score_naive_updated_at_assumed_utc():` |
| `52` | Warning | PY_TYPING | Missing return type hint for function 'test_ranking_score_clamps_inputs_and_matches_formula' | `def test_ranking_score_clamps_inputs_and_matches_formula():` |
| `62` | Warning | PY_TYPING | Missing return type hint for function 'test_reinforce_executes_upsert_sql' | `def test_reinforce_executes_upsert_sql():` |
| `89` | Warning | PY_TYPING | Missing return type hint for function 'test_jitter_is_deterministic_for_same_memory_id' | `def test_jitter_is_deterministic_for_same_memory_id(self):` |
| `113` | Warning | PY_TYPING | Missing return type hint for function 'test_different_memory_ids_produce_different_scores' | `def test_different_memory_ids_produce_different_scores(self):` |
| `138` | Warning | PY_TYPING | Missing return type hint for function 'test_jitter_stays_within_plusminus_5_percent' | `def test_jitter_stays_within_plusminus_5_percent(self):` |
| `147` | Warning | PY_TYPING | Missing return type hint for function 'test_jitter_without_memory_id_is_backward_compatible' | `def test_jitter_without_memory_id_is_backward_compatible(self):` |
| `163` | Warning | PY_TYPING | Missing return type hint for function 'test_jitter_zero_half_life_still_returns_unchanged' | `def test_jitter_zero_half_life_still_returns_unchanged(self):` |
| `183` | Warning | PY_TYPING | Missing return type hint for function 'test_jitter_pathological_guard' | `def test_jitter_pathological_guard(self):` |

---

### Module: `tests/test_cognitive_orchestrator_rls.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `59` | Warning | PY_TYPING | Missing return type hint for async function '_patched_session' | `async def _patched_session(ns_id):` |
| `59` | Warning | PY_TYPING | Missing type hint for argument 'ns_id' in async function '_patched_session' | `async def _patched_session(ns_id):` |

---

### Module: `tests/test_contradiction_detection.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `22` | Warning | PY_TYPING | Missing return type hint for async function '_acquire' | `async def _acquire(*_args, **_kwargs):` |
| `47` | Warning | PY_TYPING | Missing return type hint for function 'mock_nli' | `def mock_nli(monkeypatch: pytest.MonkeyPatch):` |
| `67` | Warning | PY_TYPING | Missing return type hint for async function 'complete' | `async def complete(self, messages: list, response_model: type):  # noqa: ANN401` |
| `75` | Warning | PY_TYPING | Missing return type hint for function 'test_detect_skips_non_fact_assertions' | `def test_detect_skips_non_fact_assertions():` |
| `79` | Warning | PY_TYPING | Missing return type hint for async function '_run' | `async def _run():` |
| `97` | Warning | PY_TYPING | Missing return type hint for function 'test_detect_returns_none_when_no_similar_candidates' | `def test_detect_returns_none_when_no_similar_candidates():` |
| `102` | Warning | PY_TYPING | Missing return type hint for async function '_run' | `async def _run():` |
| `120` | Warning | PY_TYPING | Missing return type hint for function 'test_detect_records_contradiction_when_llm_confident' | `def test_detect_records_contradiction_when_llm_confident(` |
| `159` | Warning | PY_TYPING | Missing return type hint for async function '_run' | `async def _run():` |
| `183` | Warning | PY_TYPING | Missing return type hint for function 'test_detect_no_insert_when_llm_rejects_contradiction' | `def test_detect_no_insert_when_llm_rejects_contradiction(` |
| `205` | Warning | PY_TYPING | Missing return type hint for async function '_run' | `async def _run():` |
| `224` | Warning | PY_TYPING | Missing return type hint for function 'test_detect_inserts_on_kg_when_llm_raises' | `def test_detect_inserts_on_kg_when_llm_raises(monkeypatch: pytest.MonkeyPatch):` |
| `235` | Warning | PY_TYPING | Missing return type hint for async function '_fetchrow' | `async def _fetchrow(sql: str, *args: object):` |
| `250` | Warning | PY_TYPING | Missing return type hint for async function 'complete' | `async def complete(self, messages: list, response_model: type):  # noqa: ANN401` |
| `260` | Warning | PY_TYPING | Missing return type hint for async function '_run' | `async def _run():` |
| `282` | Warning | PY_TYPING | Missing return type hint for function 'test_prompt_injection_sanitization' | `def test_prompt_injection_sanitization():` |
| `342` | Warning | PY_TYPING | Missing return type hint for async function 'complete' | `async def complete(self, messages: list, response_model: type):  # noqa: ANN401` |
| `354` | Warning | PY_TYPING | Missing return type hint for async function 'complete' | `async def complete(self, messages: list, response_model: type):  # noqa: ANN401` |
| `366` | Warning | PY_TYPING | Missing return type hint for async function 'complete' | `async def complete(self, messages: list, response_model: type):  # noqa: ANN401` |
| `373` | Warning | PY_TYPING | Missing return type hint for function 'test_detect_contradictions_returns_none_on_llm_timeout' | `def test_detect_contradictions_returns_none_on_llm_timeout(` |
| `405` | Warning | PY_TYPING | Missing return type hint for async function '_run' | `async def _run():` |
| `430` | Warning | PY_TYPING | Missing return type hint for function 'test_detect_contradictions_returns_none_on_parse_failure' | `def test_detect_contradictions_returns_none_on_parse_failure(` |
| `461` | Warning | PY_TYPING | Missing return type hint for async function '_run' | `async def _run():` |
| `486` | Warning | PY_TYPING | Missing return type hint for function 'test_detect_contradictions_returns_none_on_mongo_failure' | `def test_detect_contradictions_returns_none_on_mongo_failure(` |
| `506` | Warning | PY_TYPING | Missing return type hint for async function '_run' | `async def _run():` |
| `523` | Warning | PY_TYPING | Missing return type hint for function 'test_detect_contradictions_returns_none_on_postgres_select_failure' | `def test_detect_contradictions_returns_none_on_postgres_select_failure():` |
| `533` | Warning | PY_TYPING | Missing return type hint for async function '_run' | `async def _run():` |
| `550` | Warning | PY_TYPING | Missing return type hint for function 'test_detect_contradictions_still_records_on_kg_signal_with_llm_timeout' | `def test_detect_contradictions_still_records_on_kg_signal_with_llm_timeout(` |
| `564` | Warning | PY_TYPING | Missing return type hint for async function '_fetchrow' | `async def _fetchrow(sql: str, *args: object):` |
| `589` | Warning | PY_TYPING | Missing return type hint for async function '_run' | `async def _run():` |
| `612` | Warning | PY_TYPING | Missing return type hint for function 'test_detect_contradictions_returns_none_when_no_signals_and_llm_fails' | `def test_detect_contradictions_returns_none_when_no_signals_and_llm_fails(` |
| `644` | Warning | PY_TYPING | Missing return type hint for async function '_run' | `async def _run():` |
| `664` | Warning | PY_TYPING | Missing return type hint for function 'test_check_nli_contradiction_empty_candidate_returns_safe_defaults' | `def test_check_nli_contradiction_empty_candidate_returns_safe_defaults():` |
| `668` | Warning | PY_TYPING | Missing return type hint for async function '_run' | `async def _run():` |

---

### Module: `tests/test_cron_lock.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `19` | Warning | PY_TYPING | Missing return type hint for async function 'test_returns_local_disabled_lock_when_redis_url_empty' | `async def test_returns_local_disabled_lock_when_redis_url_empty(self):` |
| `29` | Warning | PY_TYPING | Missing return type hint for async function 'test_returns_none_on_redis_exception' | `async def test_returns_none_on_redis_exception(self):` |
| `40` | Warning | PY_TYPING | Missing return type hint for async function 'test_returns_lock_when_set_nx_succeeds' | `async def test_returns_lock_when_set_nx_succeeds(self):` |
| `59` | Warning | PY_TYPING | Missing return type hint for async function 'test_returns_none_when_set_nx_returns_none' | `async def test_returns_none_when_set_nx_returns_none(self):` |
| `73` | Warning | PY_TYPING | Missing return type hint for async function 'test_lock_key_includes_job_id' | `async def test_lock_key_includes_job_id(self):` |

---

### Module: `tests/test_dead_letter_queue.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `09` | Warning | PY_TYPING | Missing return type hint for function 'test_passes_through_simple_values' | `def test_passes_through_simple_values(self):` |
| `14` | Warning | PY_TYPING | Missing return type hint for function 'test_redacts_sensitive_keys' | `def test_redacts_sensitive_keys(self):` |
| `29` | Warning | PY_TYPING | Missing return type hint for function 'test_truncates_long_strings' | `def test_truncates_long_strings(self):` |
| `35` | Warning | PY_TYPING | Missing return type hint for function 'test_limits_nested_dict_keys' | `def test_limits_nested_dict_keys(self):` |
| `40` | Warning | PY_TYPING | Missing return type hint for function 'test_limits_list_length' | `def test_limits_list_length(self):` |
| `45` | Warning | PY_TYPING | Missing return type hint for function 'test_recursive_dict_redaction' | `def test_recursive_dict_redaction(self):` |
| `56` | Warning | PY_TYPING | Missing return type hint for function 'test_string_in_list_truncated' | `def test_string_in_list_truncated(self):` |

---

### Module: `tests/test_dispatch_error_envelopes.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `77` | Warning | PY_TYPING | Missing return type hint for async function '_noop_instrument' | `async def _noop_instrument(_name: str):` |

---

### Module: `tests/test_email_ext_security.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `16` | Warning | PY_TYPING | Missing return type hint for async function 'test_eml_attachment_fan_out_limit' | `async def test_eml_attachment_fan_out_limit():` |
| `24` | Warning | PY_TYPING | Missing return type hint for async function '_fake_extract' | `async def _fake_extract(*_a, **_kw):` |
| `42` | Warning | PY_TYPING | Missing return type hint for async function 'test_eml_nested_depth_limit' | `async def test_eml_nested_depth_limit():` |
| `50` | Warning | PY_TYPING | Missing return type hint for async function '_fake_extract' | `async def _fake_extract(*_a, attachment_depth=0, **_kw):` |

---

### Module: `tests/test_event_log_concurrency.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `13` | Warning | PY_TYPING | Missing return type hint for async function 'test_concurrent_append_event_no_gaps' | `async def test_concurrent_append_event_no_gaps(pg_pool, namespace_id):` |
| `13` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function 'test_concurrent_append_event_no_gaps' | `async def test_concurrent_append_event_no_gaps(pg_pool, namespace_id):` |
| `13` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_concurrent_append_event_no_gaps' | `async def test_concurrent_append_event_no_gaps(pg_pool, namespace_id):` |
| `14` | Warning | PY_TYPING | Missing return type hint for async function 'write_one' | `async def write_one(i: int):` |
| `38` | Warning | PY_TYPING | Missing return type hint for async function 'test_event_sequences_are_independent_per_namespace' | `async def test_event_sequences_are_independent_per_namespace(pg_pool, make_namespace):` |
| `38` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function 'test_event_sequences_are_independent_per_namespace' | `async def test_event_sequences_are_independent_per_namespace(pg_pool, make_namespace):` |
| `38` | Warning | PY_TYPING | Missing type hint for argument 'make_namespace' in async function 'test_event_sequences_are_independent_per_namespace' | `async def test_event_sequences_are_independent_per_namespace(pg_pool, make_namespace):` |
| `42` | Warning | PY_TYPING | Missing return type hint for async function 'write' | `async def write(ns):` |
| `42` | Warning | PY_TYPING | Missing type hint for argument 'ns' in async function 'write' | `async def write(ns):` |

---

### Module: `tests/test_event_log_hardening.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `111` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function 'test_append_event_integration_writes_row' | `async def test_append_event_integration_writes_row(pg_pool, namespace_id) -> None:` |
| `111` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_append_event_integration_writes_row' | `async def test_append_event_integration_writes_row(pg_pool, namespace_id) -> None:` |
| `126` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function 'test_append_event_integration_requires_transaction' | `async def test_append_event_integration_requires_transaction(pg_pool, namespace_id) -> None:` |
| `126` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_append_event_integration_requires_transaction' | `async def test_append_event_integration_requires_transaction(pg_pool, namespace_id) -> None:` |
| `140` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function 'test_verify_merkle_chain_integration_empty_namespace' | `async def test_verify_merkle_chain_integration_empty_namespace(pg_pool) -> None:` |
| `150` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function 'test_verify_merkle_and_signature_after_append' | `async def test_verify_merkle_and_signature_after_append(pg_pool, namespace_id) -> None:` |
| `150` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_verify_merkle_and_signature_after_append' | `async def test_verify_merkle_and_signature_after_append(pg_pool, namespace_id) -> None:` |
| `180` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function 'test_append_two_events_integration_chain_valid' | `async def test_append_two_events_integration_chain_valid(pg_pool, namespace_id) -> None:` |
| `180` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_append_two_events_integration_chain_valid' | `async def test_append_two_events_integration_chain_valid(pg_pool, namespace_id) -> None:` |
| `205` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function 'test_verify_merkle_chain_partial_range' | `async def test_verify_merkle_chain_partial_range(pg_pool, namespace_id) -> None:` |
| `205` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_verify_merkle_chain_partial_range' | `async def test_verify_merkle_chain_partial_range(pg_pool, namespace_id) -> None:` |

---

### Module: `tests/test_event_log_verification.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `13` | Warning | PY_TYPING | Missing return type hint for async function 'test_verify_event_signature_tampered_record_raises_error' | `async def test_verify_event_signature_tampered_record_raises_error():` |
| `40` | Warning | PY_TYPING | Missing return type hint for async function 'test_observational_replay_yields_error_on_tampering' | `async def test_observational_replay_yields_error_on_tampering():` |
| `61` | Warning | PY_TYPING | Missing return type hint for async function 'async_generator' | `async def async_generator():` |
| `68` | Warning | PY_TYPING | Missing return type hint for async function 'mock_transaction' | `async def mock_transaction(*args, **kwargs):` |
| `74` | Warning | PY_TYPING | Missing return type hint for async function 'mock_acquire' | `async def mock_acquire(*args, **kwargs):` |

---

### Module: `tests/test_extractors_core.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `17` | Warning | PY_TYPING | Missing return type hint for function 'test_extract_with_fallback_unsupported_extension' | `def test_extract_with_fallback_unsupported_extension(mock_registry, mock_ensure):` |
| `17` | Warning | PY_TYPING | Missing type hint for argument 'mock_registry' in function 'test_extract_with_fallback_unsupported_extension' | `def test_extract_with_fallback_unsupported_extension(mock_registry, mock_ensure):` |
| `17` | Warning | PY_TYPING | Missing type hint for argument 'mock_ensure' in function 'test_extract_with_fallback_unsupported_extension' | `def test_extract_with_fallback_unsupported_extension(mock_registry, mock_ensure):` |
| `27` | Warning | PY_TYPING | Missing return type hint for function 'test_extract_with_fallback_malformed_pdf' | `def test_extract_with_fallback_malformed_pdf(mock_registry, mock_ensure):` |
| `27` | Warning | PY_TYPING | Missing type hint for argument 'mock_registry' in function 'test_extract_with_fallback_malformed_pdf' | `def test_extract_with_fallback_malformed_pdf(mock_registry, mock_ensure):` |
| `27` | Warning | PY_TYPING | Missing type hint for argument 'mock_ensure' in function 'test_extract_with_fallback_malformed_pdf' | `def test_extract_with_fallback_malformed_pdf(mock_registry, mock_ensure):` |
| `29` | Warning | PY_TYPING | Missing return type hint for async function 'mock_pdf_extractor' | `async def mock_pdf_extractor(blob):` |
| `29` | Warning | PY_TYPING | Missing type hint for argument 'blob' in async function 'mock_pdf_extractor' | `async def mock_pdf_extractor(blob):` |
| `42` | Warning | PY_TYPING | Missing return type hint for function 'test_chunk_structured_basic' | `def test_chunk_structured_basic():` |
| `51` | Warning | PY_TYPING | Missing return type hint for function 'test_chunk_structured_long_text_split' | `def test_chunk_structured_long_text_split():` |
| `70` | Warning | PY_TYPING | Missing return type hint for function 'test_chunk_structured_no_cross_section_merging' | `def test_chunk_structured_no_cross_section_merging():` |
| `100` | Warning | PY_TYPING | Missing return type hint for function 'test_small_zip_passes' | `def test_small_zip_passes(self, monkeypatch: pytest.MonkeyPatch):` |
| `108` | Warning | PY_TYPING | Missing return type hint for function 'test_total_exceeds_limit' | `def test_total_exceeds_limit(self, monkeypatch: pytest.MonkeyPatch):` |
| `118` | Warning | PY_TYPING | Missing return type hint for function 'test_entry_exceeds_limit' | `def test_entry_exceeds_limit(self, monkeypatch: pytest.MonkeyPatch):` |
| `129` | Warning | PY_TYPING | Missing return type hint for function 'test_corrupt_zip_returns_error' | `def test_corrupt_zip_returns_error(self):` |
| `139` | Warning | PY_TYPING | Missing return type hint for function 'test_small_pdf_passes' | `def test_small_pdf_passes(self, monkeypatch: pytest.MonkeyPatch):` |
| `151` | Warning | PY_TYPING | Missing return type hint for function 'test_pdf_too_large' | `def test_pdf_too_large(self, monkeypatch: pytest.MonkeyPatch):` |
| `160` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_skipped_import' | `def test_empty_skipped_import():` |
| `169` | Warning | PY_TYPING | Missing return type hint for function 'test_pymupdf_extract_hygiene' | `def test_pymupdf_extract_hygiene(monkeypatch: pytest.MonkeyPatch):` |
| `197` | Warning | PY_TYPING | Missing return type hint for function 'mock_gc_collect' | `def mock_gc_collect(*args, **kwargs):` |
| `221` | Warning | PY_TYPING | Missing return type hint for async function 'test_extract_pdf_pymupdf_fallback_to_pypdf' | `async def test_extract_pdf_pymupdf_fallback_to_pypdf(monkeypatch: pytest.MonkeyPatch):` |
| `247` | Warning | PY_TYPING | Missing return type hint for async function 'test_extract_pdf_uses_pymupdf_when_available' | `async def test_extract_pdf_uses_pymupdf_when_available(monkeypatch: pytest.MonkeyPatch):` |

---

### Module: `tests/test_extractors_security_batch_e1.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `15` | Warning | PY_TYPING | Missing return type hint for function 'test_safe_source_ext_rejects_path_segments' | `def test_safe_source_ext_rejects_path_segments(self):` |
| `19` | Warning | PY_TYPING | Missing return type hint for function 'test_libreoffice_convert_invalid_ext_returns_none' | `def test_libreoffice_convert_invalid_ext_returns_none(self):` |
| `24` | Warning | PY_TYPING | Missing return type hint for function 'test_pdf_extension_zip_magic_is_mismatch' | `def test_pdf_extension_zip_magic_is_mismatch(self):` |
| `28` | Warning | PY_TYPING | Missing return type hint for async function 'test_zip_bytes_named_pdf_skipped' | `async def test_zip_bytes_named_pdf_skipped(self):` |
| `40` | Warning | PY_TYPING | Missing return type hint for async function 'test_invalid_board_id_skipped_without_http' | `async def test_invalid_board_id_skipped_without_http(self):` |
| `54` | Warning | PY_TYPING | Missing return type hint for async function 'test_ocr_pdf_page_limit_warning' | `async def test_ocr_pdf_page_limit_warning(self, monkeypatch):` |
| `54` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_ocr_pdf_page_limit_warning' | `async def test_ocr_pdf_page_limit_warning(self, monkeypatch):` |

---

### Module: `tests/test_garbage_collector.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `28` | Warning | PY_TYPING | Missing return type hint for function 'mock_pg_pool' | `def mock_pg_pool(sample_namespaces):` |
| `28` | Warning | PY_TYPING | Missing type hint for argument 'sample_namespaces' in function 'mock_pg_pool' | `def mock_pg_pool(sample_namespaces):` |
| `52` | Warning | PY_TYPING | Missing return type hint for async function 'test_fetch_all_namespaces_returns_uuids' | `async def test_fetch_all_namespaces_returns_uuids(mock_pg_pool, sample_namespaces):` |
| `52` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_fetch_all_namespaces_returns_uuids' | `async def test_fetch_all_namespaces_returns_uuids(mock_pg_pool, sample_namespaces):` |
| `52` | Warning | PY_TYPING | Missing type hint for argument 'sample_namespaces' in async function 'test_fetch_all_namespaces_returns_uuids' | `async def test_fetch_all_namespaces_returns_uuids(mock_pg_pool, sample_namespaces):` |
| `60` | Warning | PY_TYPING | Missing return type hint for async function 'test_fetch_all_namespaces_empty' | `async def test_fetch_all_namespaces_empty():` |
| `80` | Warning | PY_TYPING | Missing return type hint for async function 'test_clean_orphaned_cascade_sets_context' | `async def test_clean_orphaned_cascade_sets_context(mock_pg_pool, sample_namespaces):` |
| `80` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_clean_orphaned_cascade_sets_context' | `async def test_clean_orphaned_cascade_sets_context(mock_pg_pool, sample_namespaces):` |
| `80` | Warning | PY_TYPING | Missing type hint for argument 'sample_namespaces' in async function 'test_clean_orphaned_cascade_sets_context' | `async def test_clean_orphaned_cascade_sets_context(mock_pg_pool, sample_namespaces):` |
| `110` | Warning | PY_TYPING | Missing return type hint for async function 'test_clean_orphaned_cascade_returns_zero_on_error' | `async def test_clean_orphaned_cascade_returns_zero_on_error():` |
| `123` | Warning | PY_TYPING | Missing return type hint for async function 'test_clean_orphaned_cascade_handles_null_row' | `async def test_clean_orphaned_cascade_handles_null_row(mock_pg_pool):` |
| `123` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_clean_orphaned_cascade_handles_null_row' | `async def test_clean_orphaned_cascade_handles_null_row(mock_pg_pool):` |
| `135` | Warning | PY_TYPING | Missing return type hint for async function 'test_clean_orphaned_cascade_passes_namespace_id_to_cte' | `async def test_clean_orphaned_cascade_passes_namespace_id_to_cte(mock_pg_pool):` |
| `135` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_clean_orphaned_cascade_passes_namespace_id_to_cte' | `async def test_clean_orphaned_cascade_passes_namespace_id_to_cte(mock_pg_pool):` |
| `178` | Warning | PY_TYPING | Missing return type hint for async function 'test_fetch_pg_refs_sets_context_per_namespace' | `async def test_fetch_pg_refs_sets_context_per_namespace():` |
| `223` | Warning | PY_TYPING | Missing return type hint for async function 'test_collect_orphans_iterates_over_all_namespaces' | `async def test_collect_orphans_iterates_over_all_namespaces(mock_pg_pool, sample_namespaces):` |
| `223` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_collect_orphans_iterates_over_all_namespaces' | `async def test_collect_orphans_iterates_over_all_namespaces(mock_pg_pool, sample_namespaces):` |
| `223` | Warning | PY_TYPING | Missing type hint for argument 'sample_namespaces' in async function 'test_collect_orphans_iterates_over_all_namespaces' | `async def test_collect_orphans_iterates_over_all_namespaces(mock_pg_pool, sample_namespaces):` |
| `234` | Warning | PY_TYPING | Missing return type hint for async function '_async_cursor' | `async def _async_cursor(docs):` |
| `234` | Warning | PY_TYPING | Missing type hint for argument 'docs' in async function '_async_cursor' | `async def _async_cursor(docs):` |
| `238` | Warning | PY_TYPING | Missing return type hint for function '_find_chain' | `def _find_chain(docs):` |
| `238` | Warning | PY_TYPING | Missing type hint for argument 'docs' in function '_find_chain' | `def _find_chain(docs):` |
| `284` | Warning | PY_TYPING | Missing return type hint for async function 'test_collect_orphans_handles_no_namespaces' | `async def test_collect_orphans_handles_no_namespaces():` |
| `303` | Warning | PY_TYPING | Missing return type hint for async function '_async_cursor' | `async def _async_cursor(docs):` |
| `303` | Warning | PY_TYPING | Missing type hint for argument 'docs' in async function '_async_cursor' | `async def _async_cursor(docs):` |
| `348` | Warning | PY_TYPING | Missing return type hint for async function 'test_clean_orphaned_cascade_sql_no_trailing_comma_before_select' | `async def test_clean_orphaned_cascade_sql_no_trailing_comma_before_select(` |
| `348` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_clean_orphaned_cascade_sql_no_trailing_comma_before_select' | `async def test_clean_orphaned_cascade_sql_no_trailing_comma_before_select(` |
| `366` | Warning | PY_TYPING | Missing return type hint for async function 'test_collect_orphans_empty_namespaces_never_deletes_mongo' | `async def test_collect_orphans_empty_namespaces_never_deletes_mongo():` |
| `380` | Warning | PY_TYPING | Missing return type hint for async function '_async_cursor' | `async def _async_cursor(docs):` |
| `380` | Warning | PY_TYPING | Missing type hint for argument 'docs' in async function '_async_cursor' | `async def _async_cursor(docs):` |
| `384` | Warning | PY_TYPING | Missing return type hint for function '_find_chain' | `def _find_chain(docs):` |
| `384` | Warning | PY_TYPING | Missing type hint for argument 'docs' in function '_find_chain' | `def _find_chain(docs):` |
| `418` | Warning | PY_TYPING | Missing return type hint for async function 'test_connect_with_retry_closes_mongo_when_pg_fails' | `async def test_connect_with_retry_closes_mongo_when_pg_fails():` |
| `451` | Warning | PY_TYPING | Missing return type hint for async function 'test_acquire_gc_lock_returns_none_when_not_acquired' | `async def test_acquire_gc_lock_returns_none_when_not_acquired():` |
| `463` | Warning | PY_TYPING | Missing return type hint for async function 'test_acquire_gc_lock_returns_client_when_acquired' | `async def test_acquire_gc_lock_returns_client_when_acquired():` |
| `475` | Warning | PY_TYPING | Missing return type hint for async function 'test_release_gc_lock_deletes_key_and_closes' | `async def test_release_gc_lock_deletes_key_and_closes():` |
| `487` | Warning | PY_TYPING | Missing return type hint for async function 'test_run_gc_loop_releases_lock_on_collect_error' | `async def test_run_gc_loop_releases_lock_on_collect_error():` |
| `498` | Warning | PY_TYPING | Missing return type hint for async function '_sleep' | `async def _sleep(_seconds):` |
| `498` | Warning | PY_TYPING | Missing type hint for argument '_seconds' in async function '_sleep' | `async def _sleep(_seconds):` |
| `534` | Warning | PY_TYPING | Missing return type hint for async function 'test_run_gc_loop_skips_collect_when_lock_not_acquired' | `async def test_run_gc_loop_skips_collect_when_lock_not_acquired():` |
| `570` | Warning | PY_TYPING | Missing return type hint for async function 'test_collect_orphans_find_uses_max_time_ms' | `async def test_collect_orphans_find_uses_max_time_ms(mock_pg_pool, sample_namespaces):` |
| `570` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_collect_orphans_find_uses_max_time_ms' | `async def test_collect_orphans_find_uses_max_time_ms(mock_pg_pool, sample_namespaces):` |
| `570` | Warning | PY_TYPING | Missing type hint for argument 'sample_namespaces' in async function 'test_collect_orphans_find_uses_max_time_ms' | `async def test_collect_orphans_find_uses_max_time_ms(mock_pg_pool, sample_namespaces):` |
| `580` | Warning | PY_TYPING | Missing return type hint for async function '_async_cursor' | `async def _async_cursor(docs):` |
| `580` | Warning | PY_TYPING | Missing type hint for argument 'docs' in async function '_async_cursor' | `async def _async_cursor(docs):` |
| `584` | Warning | PY_TYPING | Missing return type hint for function '_find_chain' | `def _find_chain(docs):` |
| `584` | Warning | PY_TYPING | Missing type hint for argument 'docs' in function '_find_chain' | `def _find_chain(docs):` |
| `626` | Warning | PY_TYPING | Missing return type hint for async function 'test_run_gc_loop_cancelled_error_propagates' | `async def test_run_gc_loop_cancelled_error_propagates():` |
| `637` | Warning | PY_TYPING | Missing return type hint for async function '_sleep' | `async def _sleep(_seconds):` |
| `637` | Warning | PY_TYPING | Missing type hint for argument '_seconds' in async function '_sleep' | `async def _sleep(_seconds):` |

---

### Module: `tests/test_graph_extractor.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `13` | Warning | PY_TYPING | Missing return type hint for function 'test_regex_extract' | `def test_regex_extract():` |
| `28` | Warning | PY_TYPING | Missing return type hint for function 'test_extract_uses_spacy' | `def test_extract_uses_spacy(mock_spacy):` |
| `28` | Warning | PY_TYPING | Missing type hint for argument 'mock_spacy' in function 'test_extract_uses_spacy' | `def test_extract_uses_spacy(mock_spacy):` |
| `43` | Warning | PY_TYPING | Missing return type hint for function 'test_extract_falls_back_to_regex' | `def test_extract_falls_back_to_regex(mock_regex, mock_spacy):` |
| `43` | Warning | PY_TYPING | Missing type hint for argument 'mock_regex' in function 'test_extract_falls_back_to_regex' | `def test_extract_falls_back_to_regex(mock_regex, mock_spacy):` |
| `43` | Warning | PY_TYPING | Missing type hint for argument 'mock_spacy' in function 'test_extract_falls_back_to_regex' | `def test_extract_falls_back_to_regex(mock_regex, mock_spacy):` |
| `67` | Warning | PY_TYPING | Missing return type hint for function 'test_redis_casing_variants_produce_single_node' | `def test_redis_casing_variants_produce_single_node(self):` |
| `76` | Warning | PY_TYPING | Missing return type hint for function 'test_postgres_casing_variants_produce_single_node' | `def test_postgres_casing_variants_produce_single_node(self):` |
| `85` | Warning | PY_TYPING | Missing return type hint for function 'test_first_occurrence_label_wins' | `def test_first_occurrence_label_wins(self):` |
| `106` | Warning | PY_TYPING | Missing return type hint for function 'test_identical_labels_collapsed_to_one' | `def test_identical_labels_collapsed_to_one(self):` |
| `112` | Warning | PY_TYPING | Missing return type hint for function 'test_case_variant_labels_collapsed' | `def test_case_variant_labels_collapsed(self):` |
| `123` | Warning | PY_TYPING | Missing return type hint for function 'test_distinct_labels_all_kept' | `def test_distinct_labels_all_kept(self):` |
| `130` | Warning | PY_TYPING | Missing return type hint for function 'test_graph_size_shrinks_after_overlapping_chunks' | `def test_graph_size_shrinks_after_overlapping_chunks(self):` |
| `142` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_input_returns_empty' | `def test_empty_input_returns_empty(self):` |
| `159` | Warning | PY_TYPING | Missing return type hint for function 'test_duplicate_edges_merged' | `def test_duplicate_edges_merged(self):` |
| `167` | Warning | PY_TYPING | Missing return type hint for function 'test_edge_confidence_accumulates' | `def test_edge_confidence_accumulates(self):` |
| `178` | Warning | PY_TYPING | Missing return type hint for function 'test_occurrence_count_tracked_in_metadata' | `def test_occurrence_count_tracked_in_metadata(self):` |
| `189` | Warning | PY_TYPING | Missing return type hint for function 'test_single_edge_has_occurrence_count_one' | `def test_single_edge_has_occurrence_count_one(self):` |
| `194` | Warning | PY_TYPING | Missing return type hint for function 'test_case_normalised_edge_keys_merged' | `def test_case_normalised_edge_keys_merged(self):` |
| `204` | Warning | PY_TYPING | Missing return type hint for function 'test_distinct_edges_all_kept' | `def test_distinct_edges_all_kept(self):` |
| `212` | Warning | PY_TYPING | Missing return type hint for function 'test_custom_max_accumulator' | `def test_custom_max_accumulator(self):` |
| `222` | Warning | PY_TYPING | Missing return type hint for function 'test_overlapping_chunks_shrink_edge_count' | `def test_overlapping_chunks_shrink_edge_count(self):` |
| `240` | Warning | PY_TYPING | Missing return type hint for async function 'test_extract_async' | `async def test_extract_async():` |

---

### Module: `tests/test_graph_orchestrator.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `17` | Warning | PY_TYPING | Missing return type hint for function '_fake_scoped' | `def _fake_scoped(mock_conn):` |
| `17` | Warning | PY_TYPING | Missing type hint for argument 'mock_conn' in function '_fake_scoped' | `def _fake_scoped(mock_conn):` |
| `19` | Warning | PY_TYPING | Missing return type hint for async function '_scoped' | `async def _scoped(_pool, _namespace_id):` |
| `19` | Warning | PY_TYPING | Missing type hint for argument '_pool' in async function '_scoped' | `async def _scoped(_pool, _namespace_id):` |
| `19` | Warning | PY_TYPING | Missing type hint for argument '_namespace_id' in async function '_scoped' | `async def _scoped(_pool, _namespace_id):` |
| `25` | Warning | PY_TYPING | Missing return type hint for function '_make_orchestrator' | `def _make_orchestrator(*, embed_fn=None, traverser=None):` |
| `37` | Warning | PY_TYPING | Missing return type hint for function '_fused_row' | `def _fused_row(memory_id: uuid.UUID, score: float):` |
| `41` | Warning | PY_TYPING | Missing return type hint for function '_memory_row' | `def _memory_row(` |
| `59` | Warning | PY_TYPING | Missing return type hint for function 'graph_orch' | `def graph_orch():` |
| `77` | Warning | PY_TYPING | Missing return type hint for async function '_fetch' | `async def _fetch(sql, *params):` |
| `77` | Warning | PY_TYPING | Missing type hint for argument 'sql' in async function '_fetch' | `async def _fetch(sql, *params):` |
| `174` | Warning | PY_TYPING | Missing return type hint for async function 'slow_embed' | `async def slow_embed(_query: str):` |
| `181` | Warning | PY_TYPING | Missing return type hint for async function 'short_wait_for' | `async def short_wait_for(coro, *, timeout=None):` |
| `181` | Warning | PY_TYPING | Missing type hint for argument 'coro' in async function 'short_wait_for' | `async def short_wait_for(coro, *, timeout=None):` |
| `277` | Warning | PY_TYPING | Missing return type hint for async function '_capture_fetch' | `async def _capture_fetch(sql, *params):` |
| `277` | Warning | PY_TYPING | Missing type hint for argument 'sql' in async function '_capture_fetch' | `async def _capture_fetch(sql, *params):` |
| `305` | Warning | PY_TYPING | Missing return type hint for async function '_capture_fetch' | `async def _capture_fetch(sql, *params):` |
| `305` | Warning | PY_TYPING | Missing type hint for argument 'sql' in async function '_capture_fetch' | `async def _capture_fetch(sql, *params):` |

---

### Module: `tests/test_graph_query.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `11` | Warning | PY_TYPING | Missing return type hint for function 'mock_pg_pool' | `def mock_pg_pool():` |
| `31` | Warning | PY_TYPING | Missing return type hint for function '__aiter__' | `def __aiter__(self):` |
| `34` | Warning | PY_TYPING | Missing return type hint for async function '__anext__' | `async def __anext__(self):` |
| `41` | Warning | PY_TYPING | Missing return type hint for function 'mock_mongo_client' | `def mock_mongo_client():` |
| `52` | Warning | PY_TYPING | Missing return type hint for function 'traverser' | `def traverser(mock_pg_pool, mock_mongo_client):` |
| `52` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in function 'traverser' | `def traverser(mock_pg_pool, mock_mongo_client):` |
| `52` | Warning | PY_TYPING | Missing type hint for argument 'mock_mongo_client' in function 'traverser' | `def traverser(mock_pg_pool, mock_mongo_client):` |
| `56` | Warning | PY_TYPING | Missing return type hint for async function 'dummy_embed' | `async def dummy_embed(query: str):` |
| `63` | Warning | PY_TYPING | Missing return type hint for async function 'test_find_anchor' | `async def test_find_anchor(traverser, mock_pg_pool):` |
| `63` | Warning | PY_TYPING | Missing type hint for argument 'traverser' in async function 'test_find_anchor' | `async def test_find_anchor(traverser, mock_pg_pool):` |
| `63` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_find_anchor' | `async def test_find_anchor(traverser, mock_pg_pool):` |
| `78` | Warning | PY_TYPING | Missing return type hint for async function 'test_bfs' | `async def test_bfs(traverser, mock_pg_pool):` |
| `78` | Warning | PY_TYPING | Missing type hint for argument 'traverser' in async function 'test_bfs' | `async def test_bfs(traverser, mock_pg_pool):` |
| `78` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_bfs' | `async def test_bfs(traverser, mock_pg_pool):` |
| `109` | Warning | PY_TYPING | Missing return type hint for async function 'test_hydrate_sources' | `async def test_hydrate_sources(traverser, mock_mongo_client):` |
| `109` | Warning | PY_TYPING | Missing type hint for argument 'traverser' in async function 'test_hydrate_sources' | `async def test_hydrate_sources(traverser, mock_mongo_client):` |
| `109` | Warning | PY_TYPING | Missing type hint for argument 'mock_mongo_client' in async function 'test_hydrate_sources' | `async def test_hydrate_sources(traverser, mock_mongo_client):` |
| `130` | Warning | PY_TYPING | Missing return type hint for async function 'test_search_full_pipeline' | `async def test_search_full_pipeline(traverser, mock_pg_pool, mock_mongo_client):` |
| `130` | Warning | PY_TYPING | Missing type hint for argument 'traverser' in async function 'test_search_full_pipeline' | `async def test_search_full_pipeline(traverser, mock_pg_pool, mock_mongo_client):` |
| `130` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_search_full_pipeline' | `async def test_search_full_pipeline(traverser, mock_pg_pool, mock_mongo_client):` |
| `130` | Warning | PY_TYPING | Missing type hint for argument 'mock_mongo_client' in async function 'test_search_full_pipeline' | `async def test_search_full_pipeline(traverser, mock_pg_pool, mock_mongo_client):` |
| `135` | Warning | PY_TYPING | Missing return type hint for async function 'mock_find_anchor' | `async def mock_find_anchor(*args, **kwargs):` |
| `141` | Warning | PY_TYPING | Missing return type hint for async function 'mock_bfs' | `async def mock_bfs(*args, **kwargs):` |
| `162` | Warning | PY_TYPING | Missing return type hint for async function 'mock_hydrate' | `async def mock_hydrate(*args, **kwargs):` |
| `179` | Warning | PY_TYPING | Missing return type hint for async function 'test_search_edge_pagination' | `async def test_search_edge_pagination(traverser, mock_pg_pool, mock_mongo_client):` |
| `179` | Warning | PY_TYPING | Missing type hint for argument 'traverser' in async function 'test_search_edge_pagination' | `async def test_search_edge_pagination(traverser, mock_pg_pool, mock_mongo_client):` |
| `179` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_search_edge_pagination' | `async def test_search_edge_pagination(traverser, mock_pg_pool, mock_mongo_client):` |
| `179` | Warning | PY_TYPING | Missing type hint for argument 'mock_mongo_client' in async function 'test_search_edge_pagination' | `async def test_search_edge_pagination(traverser, mock_pg_pool, mock_mongo_client):` |
| `183` | Warning | PY_TYPING | Missing return type hint for async function 'mock_find_anchor' | `async def mock_find_anchor(*args, **kwargs):` |
| `186` | Warning | PY_TYPING | Missing return type hint for async function 'mock_bfs' | `async def mock_bfs(*args, **kwargs):` |
| `222` | Warning | PY_TYPING | Missing return type hint for async function 'test_get_subgraph_alias' | `async def test_get_subgraph_alias(traverser, mock_pg_pool, mock_mongo_client):` |
| `222` | Warning | PY_TYPING | Missing type hint for argument 'traverser' in async function 'test_get_subgraph_alias' | `async def test_get_subgraph_alias(traverser, mock_pg_pool, mock_mongo_client):` |
| `222` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_get_subgraph_alias' | `async def test_get_subgraph_alias(traverser, mock_pg_pool, mock_mongo_client):` |
| `222` | Warning | PY_TYPING | Missing type hint for argument 'mock_mongo_client' in async function 'test_get_subgraph_alias' | `async def test_get_subgraph_alias(traverser, mock_pg_pool, mock_mongo_client):` |
| `225` | Warning | PY_TYPING | Missing return type hint for async function 'mock_find_anchor' | `async def mock_find_anchor(*args, **kwargs):` |
| `228` | Warning | PY_TYPING | Missing return type hint for async function 'mock_bfs' | `async def mock_bfs(*args, **kwargs):` |
| `247` | Warning | PY_TYPING | Missing return type hint for async function 'test_time_travel_anchor_detects_tampered_event' | `async def test_time_travel_anchor_detects_tampered_event(` |
| `247` | Warning | PY_TYPING | Missing type hint for argument 'traverser' in async function 'test_time_travel_anchor_detects_tampered_event' | `async def test_time_travel_anchor_detects_tampered_event(` |
| `247` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_time_travel_anchor_detects_tampered_event' | `async def test_time_travel_anchor_detects_tampered_event(` |
| `247` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_time_travel_anchor_detects_tampered_event' | `async def test_time_travel_anchor_detects_tampered_event(` |
| `285` | Warning | PY_TYPING | Missing return type hint for async function 'fetch_side_effect' | `async def fetch_side_effect(query, *args):` |
| `285` | Warning | PY_TYPING | Missing type hint for argument 'query' in async function 'fetch_side_effect' | `async def fetch_side_effect(query, *args):` |
| `294` | Warning | PY_TYPING | Missing return type hint for async function 'mock_verify' | `async def mock_verify(conn_arg, record):` |
| `294` | Warning | PY_TYPING | Missing type hint for argument 'conn_arg' in async function 'mock_verify' | `async def mock_verify(conn_arg, record):` |
| `294` | Warning | PY_TYPING | Missing type hint for argument 'record' in async function 'mock_verify' | `async def mock_verify(conn_arg, record):` |
| `311` | Warning | PY_TYPING | Missing return type hint for async function 'test_time_travel_bfs_detects_tampered_event' | `async def test_time_travel_bfs_detects_tampered_event(` |
| `311` | Warning | PY_TYPING | Missing type hint for argument 'traverser' in async function 'test_time_travel_bfs_detects_tampered_event' | `async def test_time_travel_bfs_detects_tampered_event(` |
| `311` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_time_travel_bfs_detects_tampered_event' | `async def test_time_travel_bfs_detects_tampered_event(` |
| `311` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_time_travel_bfs_detects_tampered_event' | `async def test_time_travel_bfs_detects_tampered_event(` |
| `348` | Warning | PY_TYPING | Missing return type hint for async function 'fetch_side_effect' | `async def fetch_side_effect(query, *args):` |
| `348` | Warning | PY_TYPING | Missing type hint for argument 'query' in async function 'fetch_side_effect' | `async def fetch_side_effect(query, *args):` |
| `360` | Warning | PY_TYPING | Missing return type hint for async function 'mock_verify' | `async def mock_verify(conn_arg, record):` |
| `360` | Warning | PY_TYPING | Missing type hint for argument 'conn_arg' in async function 'mock_verify' | `async def mock_verify(conn_arg, record):` |
| `360` | Warning | PY_TYPING | Missing type hint for argument 'record' in async function 'mock_verify' | `async def mock_verify(conn_arg, record):` |
| `375` | Warning | PY_TYPING | Missing return type hint for async function 'test_time_travel_passes_with_valid_signatures' | `async def test_time_travel_passes_with_valid_signatures(` |
| `375` | Warning | PY_TYPING | Missing type hint for argument 'traverser' in async function 'test_time_travel_passes_with_valid_signatures' | `async def test_time_travel_passes_with_valid_signatures(` |
| `375` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_time_travel_passes_with_valid_signatures' | `async def test_time_travel_passes_with_valid_signatures(` |
| `375` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_time_travel_passes_with_valid_signatures' | `async def test_time_travel_passes_with_valid_signatures(` |
| `409` | Warning | PY_TYPING | Missing return type hint for async function 'fetch_side_effect' | `async def fetch_side_effect(query, *args):` |
| `409` | Warning | PY_TYPING | Missing type hint for argument 'query' in async function 'fetch_side_effect' | `async def fetch_side_effect(query, *args):` |
| `418` | Warning | PY_TYPING | Missing return type hint for async function 'mock_verify_pass' | `async def mock_verify_pass(conn_arg, record):` |
| `418` | Warning | PY_TYPING | Missing type hint for argument 'conn_arg' in async function 'mock_verify_pass' | `async def mock_verify_pass(conn_arg, record):` |
| `418` | Warning | PY_TYPING | Missing type hint for argument 'record' in async function 'mock_verify_pass' | `async def mock_verify_pass(conn_arg, record):` |
| `440` | Warning | PY_TYPING | Missing return type hint for async function 'test_find_anchor_rejects_none_namespace_without_flag' | `async def test_find_anchor_rejects_none_namespace_without_flag(` |
| `440` | Warning | PY_TYPING | Missing type hint for argument 'traverser' in async function 'test_find_anchor_rejects_none_namespace_without_flag' | `async def test_find_anchor_rejects_none_namespace_without_flag(` |
| `440` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_find_anchor_rejects_none_namespace_without_flag' | `async def test_find_anchor_rejects_none_namespace_without_flag(` |
| `450` | Warning | PY_TYPING | Missing return type hint for async function 'test_find_anchor_allows_none_namespace_with_flag' | `async def test_find_anchor_allows_none_namespace_with_flag(` |
| `450` | Warning | PY_TYPING | Missing type hint for argument 'traverser' in async function 'test_find_anchor_allows_none_namespace_with_flag' | `async def test_find_anchor_allows_none_namespace_with_flag(` |
| `450` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_find_anchor_allows_none_namespace_with_flag' | `async def test_find_anchor_allows_none_namespace_with_flag(` |
| `466` | Warning | PY_TYPING | Missing return type hint for async function 'test_bfs_rejects_none_namespace_without_flag' | `async def test_bfs_rejects_none_namespace_without_flag(` |
| `466` | Warning | PY_TYPING | Missing type hint for argument 'traverser' in async function 'test_bfs_rejects_none_namespace_without_flag' | `async def test_bfs_rejects_none_namespace_without_flag(` |
| `466` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_bfs_rejects_none_namespace_without_flag' | `async def test_bfs_rejects_none_namespace_without_flag(` |
| `476` | Warning | PY_TYPING | Missing return type hint for async function 'test_bfs_allows_none_namespace_with_flag' | `async def test_bfs_allows_none_namespace_with_flag(` |
| `476` | Warning | PY_TYPING | Missing type hint for argument 'traverser' in async function 'test_bfs_allows_none_namespace_with_flag' | `async def test_bfs_allows_none_namespace_with_flag(` |
| `476` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_bfs_allows_none_namespace_with_flag' | `async def test_bfs_allows_none_namespace_with_flag(` |
| `495` | Warning | PY_TYPING | Missing return type hint for async function 'test_search_rejects_none_namespace_without_flag' | `async def test_search_rejects_none_namespace_without_flag(` |
| `495` | Warning | PY_TYPING | Missing type hint for argument 'traverser' in async function 'test_search_rejects_none_namespace_without_flag' | `async def test_search_rejects_none_namespace_without_flag(` |
| `495` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_search_rejects_none_namespace_without_flag' | `async def test_search_rejects_none_namespace_without_flag(` |
| `495` | Warning | PY_TYPING | Missing type hint for argument 'mock_mongo_client' in async function 'test_search_rejects_none_namespace_without_flag' | `async def test_search_rejects_none_namespace_without_flag(` |
| `506` | Warning | PY_TYPING | Missing return type hint for async function 'test_search_allows_none_namespace_with_flag' | `async def test_search_allows_none_namespace_with_flag(` |
| `506` | Warning | PY_TYPING | Missing type hint for argument 'traverser' in async function 'test_search_allows_none_namespace_with_flag' | `async def test_search_allows_none_namespace_with_flag(` |
| `506` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_search_allows_none_namespace_with_flag' | `async def test_search_allows_none_namespace_with_flag(` |
| `506` | Warning | PY_TYPING | Missing type hint for argument 'mock_mongo_client' in async function 'test_search_allows_none_namespace_with_flag' | `async def test_search_allows_none_namespace_with_flag(` |
| `518` | Warning | PY_TYPING | Missing return type hint for async function 'mock_bfs' | `async def mock_bfs(*args, **kwargs):` |
| `523` | Warning | PY_TYPING | Missing return type hint for async function 'mock_hydrate' | `async def mock_hydrate(*args, **kwargs):` |

---

### Module: `tests/test_html_heading_extraction.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `15` | Warning | PY_TYPING | Missing return type hint for function 'test_flat_html_returns_single_section' | `def test_flat_html_returns_single_section(self):` |
| `21` | Warning | PY_TYPING | Missing return type hint for function 'test_h1_sets_structure_path' | `def test_h1_sets_structure_path(self):` |
| `26` | Warning | PY_TYPING | Missing return type hint for function 'test_h2_under_h1_builds_hierarchy' | `def test_h2_under_h1_builds_hierarchy(self):` |
| `32` | Warning | PY_TYPING | Missing return type hint for function 'test_h3_under_h2_three_levels' | `def test_h3_under_h2_three_levels(self):` |
| `38` | Warning | PY_TYPING | Missing return type hint for function 'test_h2_resets_h3_context' | `def test_h2_resets_h3_context(self):` |
| `48` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_html_returns_no_crash' | `def test_empty_html_returns_no_crash(self):` |
| `52` | Warning | PY_TYPING | Missing return type hint for function 'test_section_order_is_sequential' | `def test_section_order_is_sequential(self):` |
| `58` | Warning | PY_TYPING | Missing return type hint for function 'test_headings_without_following_content_not_emitted' | `def test_headings_without_following_content_not_emitted(self):` |
| `69` | Warning | PY_TYPING | Missing return type hint for async function 'test_returns_extraction_result' | `async def test_returns_extraction_result(self):` |
| `76` | Warning | PY_TYPING | Missing return type hint for async function 'test_full_text_combines_all_sections' | `async def test_full_text_combines_all_sections(self):` |
| `83` | Warning | PY_TYPING | Missing return type hint for async function 'test_sections_carry_structure_path' | `async def test_sections_carry_structure_path(self):` |

---

### Module: `tests/test_http_resilience.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `15` | Warning | PY_TYPING | Missing return type hint for async function '_run_operation_without_retry' | `async def _run_operation_without_retry(op, **_kw):` |
| `15` | Warning | PY_TYPING | Missing type hint for argument 'op' in async function '_run_operation_without_retry' | `async def _run_operation_without_retry(op, **_kw):` |
| `39` | Warning | PY_TYPING | Missing return type hint for async function 'test_negative_max_retries_raises' | `async def test_negative_max_retries_raises(self):` |
| `40` | Warning | PY_TYPING | Missing return type hint for async function 'op' | `async def op():` |
| `47` | Warning | PY_TYPING | Missing return type hint for async function 'test_zero_base_delay_raises' | `async def test_zero_base_delay_raises(self):` |
| `48` | Warning | PY_TYPING | Missing return type hint for async function 'op' | `async def op():` |
| `55` | Warning | PY_TYPING | Missing return type hint for async function 'test_max_delay_less_than_base_raises' | `async def test_max_delay_less_than_base_raises(self):` |
| `56` | Warning | PY_TYPING | Missing return type hint for async function 'op' | `async def op():` |
| `63` | Warning | PY_TYPING | Missing return type hint for async function 'test_backoff_factor_below_one_raises' | `async def test_backoff_factor_below_one_raises(self):` |
| `64` | Warning | PY_TYPING | Missing return type hint for async function 'op' | `async def op():` |
| `71` | Warning | PY_TYPING | Missing return type hint for async function 'test_operation_name_too_long_raises' | `async def test_operation_name_too_long_raises(self):` |
| `72` | Warning | PY_TYPING | Missing return type hint for async function 'op' | `async def op():` |
| `81` | Warning | PY_TYPING | Missing return type hint for async function 'test_transient_error_retries_then_succeeds' | `async def test_transient_error_retries_then_succeeds(self):` |
| `84` | Warning | PY_TYPING | Missing return type hint for async function 'op' | `async def op():` |
| `103` | Warning | PY_TYPING | Missing return type hint for async function 'test_client_error_not_retried' | `async def test_client_error_not_retried(self):` |
| `106` | Warning | PY_TYPING | Missing return type hint for async function 'op' | `async def op():` |
| `121` | Warning | PY_TYPING | Missing return type hint for async function 'test_max_retries_3_means_4_total_attempts' | `async def test_max_retries_3_means_4_total_attempts(self):` |
| `124` | Warning | PY_TYPING | Missing return type hint for async function 'op' | `async def op():` |
| `141` | Warning | PY_TYPING | Missing return type hint for async function 'test_retry_exhaustion_raises_ExternalAPIRetriesExhaustedError' | `async def test_retry_exhaustion_raises_ExternalAPIRetriesExhaustedError(self):` |
| `142` | Warning | PY_TYPING | Missing return type hint for async function 'op' | `async def op():` |
| `159` | Warning | PY_TYPING | Missing return type hint for function 'test_integer_seconds_parsed' | `def test_integer_seconds_parsed(self):` |
| `162` | Warning | PY_TYPING | Missing return type hint for function 'test_zero_clamped_to_zero' | `def test_zero_clamped_to_zero(self):` |
| `165` | Warning | PY_TYPING | Missing return type hint for function 'test_negative_clamped_to_zero' | `def test_negative_clamped_to_zero(self):` |
| `168` | Warning | PY_TYPING | Missing return type hint for function 'test_http_date_parsed' | `def test_http_date_parsed(self):` |
| `175` | Warning | PY_TYPING | Missing return type hint for function 'test_invalid_string_returns_none' | `def test_invalid_string_returns_none(self):` |
| `178` | Warning | PY_TYPING | Missing return type hint for function 'test_none_input_returns_none' | `def test_none_input_returns_none(self):` |
| `183` | Warning | PY_TYPING | Missing return type hint for function 'test_429_raises_transient_with_retry_after' | `def test_429_raises_transient_with_retry_after(self):` |
| `190` | Warning | PY_TYPING | Missing return type hint for function 'test_500_raises_transient' | `def test_500_raises_transient(self):` |
| `196` | Warning | PY_TYPING | Missing return type hint for function 'test_404_raises_client_error' | `def test_404_raises_client_error(self):` |
| `202` | Warning | PY_TYPING | Missing return type hint for function 'test_200_does_not_raise' | `def test_200_does_not_raise(self):` |
| `206` | Warning | PY_TYPING | Missing return type hint for function 'test_204_does_not_raise' | `def test_204_does_not_raise(self):` |
| `213` | Warning | PY_TYPING | Missing return type hint for async function 'test_successful_response_returns_json' | `async def test_successful_response_returns_json(self):` |
| `229` | Warning | PY_TYPING | Missing return type hint for async function 'test_content_type_header_set' | `async def test_content_type_header_set(self):` |
| `246` | Warning | PY_TYPING | Missing return type hint for async function 'test_caller_content_type_not_overridden' | `async def test_caller_content_type_not_overridden(self):` |
| `264` | Warning | PY_TYPING | Missing return type hint for async function 'test_non_json_response_raises_client_error' | `async def test_non_json_response_raises_client_error(self):` |
| `280` | Warning | PY_TYPING | Missing return type hint for async function 'test_client_reused_across_retries' | `async def test_client_reused_across_retries(self):` |
| `288` | Warning | PY_TYPING | Missing return type hint for async function 'post' | `async def post(*_args, **_kwargs):` |
| `310` | Warning | PY_TYPING | Missing return type hint for function 'test_response_body_access_token_not_in_error_message' | `def test_response_body_access_token_not_in_error_message(self):` |
| `321` | Warning | PY_TYPING | Missing return type hint for async function 'test_dsn_in_transport_error_is_redacted_in_oauth_form' | `async def test_dsn_in_transport_error_is_redacted_in_oauth_form(self):` |
| `356` | Warning | PY_TYPING | Missing return type hint for async function 'test_successful_response_returns_json' | `async def test_successful_response_returns_json(self):` |
| `372` | Warning | PY_TYPING | Missing return type hint for async function 'test_content_type_header_set' | `async def test_content_type_header_set(self):` |

---

### Module: `tests/test_init_public_api.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `28` | Warning | PY_TYPING | Missing return type hint for function '_fresh_nce' | `def _fresh_nce():` |
| `33` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_bare_import_does_not_load_orchestrator' | `def test_bare_import_does_not_load_orchestrator(monkeypatch) -> None:` |
| `81` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_broken_import_yields_attribute_error' | `def test_broken_import_yields_attribute_error(monkeypatch) -> None:` |
| `86` | Warning | PY_TYPING | Missing return type hint for function 'blocking_import' | `def blocking_import(name, globals=None, locals=None, fromlist=(), level=0):` |
| `86` | Warning | PY_TYPING | Missing type hint for argument 'name' in function 'blocking_import' | `def blocking_import(name, globals=None, locals=None, fromlist=(), level=0):` |
| `86` | Warning | PY_TYPING | Missing type hint for argument 'globals' in function 'blocking_import' | `def blocking_import(name, globals=None, locals=None, fromlist=(), level=0):` |
| `86` | Warning | PY_TYPING | Missing type hint for argument 'locals' in function 'blocking_import' | `def blocking_import(name, globals=None, locals=None, fromlist=(), level=0):` |
| `86` | Warning | PY_TYPING | Missing type hint for argument 'fromlist' in function 'blocking_import' | `def blocking_import(name, globals=None, locals=None, fromlist=(), level=0):` |
| `86` | Warning | PY_TYPING | Missing type hint for argument 'level' in function 'blocking_import' | `def blocking_import(name, globals=None, locals=None, fromlist=(), level=0):` |
| `95` | Warning | PY_TYPING | Missing return type hint for function 'blocking_import_module' | `def blocking_import_module(name: str, package: str \| None = None):` |

---

### Module: `tests/test_integration_engine.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `25` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `55` | Warning | PY_TYPING | Missing return type hint for function 'setup_method' | `def setup_method(self):` |
| `58` | Warning | PY_TYPING | Missing return type hint for function 'test_none_returns_none' | `def test_none_returns_none(self):` |
| `63` | Warning | PY_TYPING | Missing return type hint for function 'test_uuid_object_returned_unchanged' | `def test_uuid_object_returned_unchanged(self):` |
| `69` | Warning | PY_TYPING | Missing return type hint for function 'test_string_uuid_is_parsed_to_uuid_object' | `def test_string_uuid_is_parsed_to_uuid_object(self):` |
| `81` | Warning | PY_TYPING | Missing return type hint for function 'test_string_uuid_never_produces_string_none' | `def test_string_uuid_never_produces_string_none(self):` |
| `92` | Warning | PY_TYPING | Missing return type hint for function 'test_invalid_string_raises_value_error' | `def test_invalid_string_raises_value_error(self):` |
| `105` | Warning | PY_TYPING | Missing return type hint for function 'test_on_saga_failure_empty_kwargs_does_not_raise' | `def test_on_saga_failure_empty_kwargs_does_not_raise(self):` |
| `113` | Warning | PY_TYPING | Missing return type hint for function 'test_on_saga_failure_missing_step_name_uses_default' | `def test_on_saga_failure_missing_step_name_uses_default(self, monkeypatch):` |
| `113` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_on_saga_failure_missing_step_name_uses_default' | `def test_on_saga_failure_missing_step_name_uses_default(self, monkeypatch):` |
| `120` | Warning | PY_TYPING | Missing return type hint for function '_fake_inc' | `def _fake_inc():` |
| `128` | Warning | PY_TYPING | Missing return type hint for function '_capture_labels' | `def _capture_labels(**kw):` |
| `143` | Warning | PY_TYPING | Missing return type hint for function 'test_on_saga_failure_with_step_name' | `def test_on_saga_failure_with_step_name(self, monkeypatch):` |
| `143` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_on_saga_failure_with_step_name' | `def test_on_saga_failure_with_step_name(self, monkeypatch):` |
| `153` | Warning | PY_TYPING | Missing return type hint for function '_capture_labels' | `def _capture_labels(**kw):` |
| `162` | Warning | PY_TYPING | Missing return type hint for function 'test_saga_metrics_context_fires_on_failure_callback' | `def test_saga_metrics_context_fires_on_failure_callback(self):` |
| `168` | Warning | PY_TYPING | Missing return type hint for function '_cb' | `def _cb(exc):` |
| `168` | Warning | PY_TYPING | Missing type hint for argument 'exc' in function '_cb' | `def _cb(exc):` |
| `178` | Warning | PY_TYPING | Missing return type hint for function 'test_saga_metrics_context_does_not_fire_on_success' | `def test_saga_metrics_context_does_not_fire_on_success(self):` |
| `184` | Warning | PY_TYPING | Missing return type hint for function '_cb' | `def _cb(exc):` |
| `184` | Warning | PY_TYPING | Missing type hint for argument 'exc' in function '_cb' | `def _cb(exc):` |
| `204` | Warning | PY_TYPING | Missing return type hint for async function 'engine' | `async def engine():` |
| `213` | Warning | PY_TYPING | Missing return type hint for async function 'test_store_and_recall' | `async def test_store_and_recall(engine):` |
| `213` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'test_store_and_recall' | `async def test_store_and_recall(engine):` |
| `232` | Warning | PY_TYPING | Missing return type hint for async function 'test_semantic_search' | `async def test_semantic_search(engine):` |
| `232` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'test_semantic_search' | `async def test_semantic_search(engine):` |
| `253` | Warning | PY_TYPING | Missing return type hint for async function 'test_index_and_search_code' | `async def test_index_and_search_code(engine):` |
| `253` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'test_index_and_search_code' | `async def test_index_and_search_code(engine):` |
| `273` | Warning | PY_TYPING | Missing return type hint for async function 'test_change_detection' | `async def test_change_detection(engine):` |
| `273` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'test_change_detection' | `async def test_change_detection(engine):` |
| `284` | Warning | PY_TYPING | Missing return type hint for async function 'test_graph_search' | `async def test_graph_search(engine):` |
| `284` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'test_graph_search' | `async def test_graph_search(engine):` |
| `304` | Warning | PY_TYPING | Missing return type hint for async function 'test_rollback' | `async def test_rollback(engine):` |
| `304` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'test_rollback' | `async def test_rollback(engine):` |
| `326` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |

---

### Module: `tests/test_llm_providers.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `72` | Warning | PY_TYPING | Missing return type hint for async function 'test_non_json_garbage' | `async def test_non_json_garbage(` |
| `91` | Warning | PY_TYPING | Missing return type hint for async function 'test_empty_json_object' | `async def test_empty_json_object(` |
| `110` | Warning | PY_TYPING | Missing return type hint for async function 'test_missing_tool_use_block' | `async def test_missing_tool_use_block(` |
| `132` | Warning | PY_TYPING | Missing return type hint for async function 'test_http_500_upstream_error' | `async def test_http_500_upstream_error(` |
| `151` | Warning | PY_TYPING | Missing return type hint for async function 'test_timeout' | `async def test_timeout(` |
| `178` | Warning | PY_TYPING | Missing return type hint for async function 'test_non_json_garbage' | `async def test_non_json_garbage(` |
| `197` | Warning | PY_TYPING | Missing return type hint for async function 'test_empty_json_object' | `async def test_empty_json_object(` |
| `216` | Warning | PY_TYPING | Missing return type hint for async function 'test_missing_choices' | `async def test_missing_choices(` |
| `235` | Warning | PY_TYPING | Missing return type hint for async function 'test_http_429_rate_limit' | `async def test_http_429_rate_limit(` |
| `254` | Warning | PY_TYPING | Missing return type hint for async function 'test_http_401_authentication_error' | `async def test_http_401_authentication_error(` |

---

### Module: `tests/test_master_key_buffer.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `43` | Warning | PY_TYPING | Missing return type hint for function 'test_zero_overwrites_all_bytes' | `def test_zero_overwrites_all_bytes():` |
| `51` | Warning | PY_TYPING | Missing return type hint for function 'test_zero_is_idempotent' | `def test_zero_is_idempotent():` |
| `60` | Warning | PY_TYPING | Missing return type hint for function 'test_zeroed_key_rejects_key_bytes' | `def test_zeroed_key_rejects_key_bytes():` |
| `68` | Warning | PY_TYPING | Missing return type hint for function 'test_zeroed_key_rejects_derive_aes_key' | `def test_zeroed_key_rejects_derive_aes_key():` |
| `82` | Warning | PY_TYPING | Missing return type hint for function 'test_context_manager_zeroes_on_exit' | `def test_context_manager_zeroes_on_exit():` |
| `91` | Warning | PY_TYPING | Missing return type hint for function 'test_context_manager_zeroes_on_exception' | `def test_context_manager_zeroes_on_exception():` |
| `97` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except RuntimeError:` |
| `107` | Warning | PY_TYPING | Missing return type hint for function 'test_del_zeroes_buffer' | `def test_del_zeroes_buffer():` |
| `116` | Warning | PY_TYPING | Missing return type hint for function 'test_del_does_not_raise' | `def test_del_does_not_raise():` |
| `133` | Warning | PY_TYPING | Missing return type hint for function 'test_from_env_with_valid_key' | `def test_from_env_with_valid_key(monkeypatch):` |
| `133` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_from_env_with_valid_key' | `def test_from_env_with_valid_key(monkeypatch):` |
| `142` | Warning | PY_TYPING | Missing return type hint for function 'test_from_env_with_missing_key' | `def test_from_env_with_missing_key(monkeypatch):` |
| `142` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_from_env_with_missing_key' | `def test_from_env_with_missing_key(monkeypatch):` |
| `149` | Warning | PY_TYPING | Missing return type hint for function 'test_from_env_with_empty_key' | `def test_from_env_with_empty_key(monkeypatch):` |
| `149` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_from_env_with_empty_key' | `def test_from_env_with_empty_key(monkeypatch):` |
| `161` | Warning | PY_TYPING | Missing return type hint for function 'test_init_rejects_short_key' | `def test_init_rejects_short_key():` |
| `172` | Warning | PY_TYPING | Missing return type hint for function 'test_require_master_key_returns_masterkey' | `def test_require_master_key_returns_masterkey(monkeypatch):` |
| `172` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_require_master_key_returns_masterkey' | `def test_require_master_key_returns_masterkey(monkeypatch):` |
| `189` | Warning | PY_TYPING | Missing return type hint for function 'test_encrypt_decrypt_roundtrip' | `def test_encrypt_decrypt_roundtrip():` |
| `199` | Warning | PY_TYPING | Missing return type hint for function 'test_decrypt_with_wrong_key_fails' | `def test_decrypt_with_wrong_key_fails():` |
| `211` | Warning | PY_TYPING | Missing return type hint for function 'test_encrypt_with_zeroed_key_fails' | `def test_encrypt_with_zeroed_key_fails():` |
| `219` | Warning | PY_TYPING | Missing return type hint for function 'test_decrypt_with_zeroed_key_fails' | `def test_decrypt_with_zeroed_key_fails():` |
| `233` | Warning | PY_TYPING | Missing return type hint for function 'test_bytearray_mutation_is_in_place' | `def test_bytearray_mutation_is_in_place():` |
| `243` | Warning | PY_TYPING | Missing return type hint for function 'test_key_bytes_memoryview_invalidated' | `def test_key_bytes_memoryview_invalidated():` |
| `259` | Warning | PY_TYPING | Missing return type hint for function 'test_mutable_key_buffer_creation_and_raw' | `def test_mutable_key_buffer_creation_and_raw():` |
| `270` | Warning | PY_TYPING | Missing return type hint for function 'test_mutable_key_buffer_zero_overwrites' | `def test_mutable_key_buffer_zero_overwrites():` |
| `281` | Warning | PY_TYPING | Missing return type hint for function 'test_mutable_key_buffer_zero_is_idempotent' | `def test_mutable_key_buffer_zero_is_idempotent():` |
| `293` | Warning | PY_TYPING | Missing return type hint for function 'test_mutable_key_buffer_bytes_after_zero_raises' | `def test_mutable_key_buffer_bytes_after_zero_raises():` |
| `303` | Warning | PY_TYPING | Missing return type hint for function 'test_mutable_key_buffer_bytes_before_zero' | `def test_mutable_key_buffer_bytes_before_zero():` |
| `315` | Warning | PY_TYPING | Missing return type hint for function 'test_mutable_key_buffer_del_zeroes' | `def test_mutable_key_buffer_del_zeroes():` |
| `326` | Warning | PY_TYPING | Missing return type hint for function 'test_mutable_key_buffer_del_does_not_raise' | `def test_mutable_key_buffer_del_does_not_raise():` |
| `344` | Warning | PY_TYPING | Missing return type hint for function 'test_from_env_ctypes_loads_correct_key' | `def test_from_env_ctypes_loads_correct_key(monkeypatch):` |
| `344` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_from_env_ctypes_loads_correct_key' | `def test_from_env_ctypes_loads_correct_key(monkeypatch):` |
| `353` | Warning | PY_TYPING | Missing return type hint for function 'test_from_env_ctypes_with_unicode' | `def test_from_env_ctypes_with_unicode(monkeypatch):` |
| `353` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_from_env_ctypes_with_unicode' | `def test_from_env_ctypes_with_unicode(monkeypatch):` |
| `364` | Warning | PY_TYPING | Missing return type hint for function 'test_from_env_rejects_short_key' | `def test_from_env_rejects_short_key(monkeypatch):` |
| `364` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_from_env_rejects_short_key' | `def test_from_env_rejects_short_key(monkeypatch):` |
| `371` | Warning | PY_TYPING | Missing return type hint for function 'test_from_env_strips_whitespace' | `def test_from_env_strips_whitespace(monkeypatch):` |
| `371` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_from_env_strips_whitespace' | `def test_from_env_strips_whitespace(monkeypatch):` |
| `384` | Warning | PY_TYPING | Missing return type hint for function 'test_cached_key_zero_on_replacement' | `def test_cached_key_zero_on_replacement():` |

---

### Module: `tests/test_mcp_args.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `28` | Warning | PY_TYPING | Missing return type hint for function 'test_valid_flat_metadata_accepted' | `def test_valid_flat_metadata_accepted(self):` |
| `31` | Warning | PY_TYPING | Missing return type hint for function 'test_nested_dict_rejected' | `def test_nested_dict_rejected(self):` |
| `35` | Warning | PY_TYPING | Missing return type hint for function 'test_too_many_keys_rejected' | `def test_too_many_keys_rejected(self):` |
| `39` | Warning | PY_TYPING | Missing return type hint for function 'test_key_too_long_rejected' | `def test_key_too_long_rejected(self):` |
| `43` | Warning | PY_TYPING | Missing return type hint for function 'test_string_value_too_long_rejected' | `def test_string_value_too_long_rejected(self):` |
| `47` | Warning | PY_TYPING | Missing return type hint for function 'test_list_too_large_rejected' | `def test_list_too_large_rejected(self):` |
| `51` | Warning | PY_TYPING | Missing return type hint for function 'test_list_with_invalid_item_rejected' | `def test_list_with_invalid_item_rejected(self):` |
| `55` | Warning | PY_TYPING | Missing return type hint for function 'test_valid_list_accepted' | `def test_valid_list_accepted(self):` |
| `58` | Warning | PY_TYPING | Missing return type hint for function 'test_non_dict_input_rejected' | `def test_non_dict_input_rejected(self):` |
| `64` | Warning | PY_TYPING | Missing return type hint for function 'test_valid_uuid_string_returned_canonical' | `def test_valid_uuid_string_returned_canonical(self):` |
| `67` | Warning | PY_TYPING | Missing return type hint for function 'test_valid_uuid_object_returned_as_string' | `def test_valid_uuid_object_returned_as_string(self):` |
| `70` | Warning | PY_TYPING | Missing return type hint for function 'test_absent_key_returns_none' | `def test_absent_key_returns_none(self):` |
| `73` | Warning | PY_TYPING | Missing return type hint for function 'test_none_value_returns_none' | `def test_none_value_returns_none(self):` |
| `76` | Warning | PY_TYPING | Missing return type hint for function 'test_invalid_uuid_raises_valueerror' | `def test_invalid_uuid_raises_valueerror(self):` |
| `80` | Warning | PY_TYPING | Missing return type hint for function 'test_invalid_uuid_does_not_fallback_silently' | `def test_invalid_uuid_does_not_fallback_silently(self):` |
| `86` | Warning | PY_TYPING | Missing return type hint for function 'test_uuid_converted_to_string' | `def test_uuid_converted_to_string(self):` |
| `89` | Warning | PY_TYPING | Missing return type hint for function 'test_dict_keys_sorted' | `def test_dict_keys_sorted(self):` |
| `92` | Warning | PY_TYPING | Missing return type hint for function 'test_nested_dict_keys_sorted' | `def test_nested_dict_keys_sorted(self):` |
| `95` | Warning | PY_TYPING | Missing return type hint for function 'test_list_items_normalized' | `def test_list_items_normalized(self):` |
| `98` | Warning | PY_TYPING | Missing return type hint for function 'test_primitives_unchanged' | `def test_primitives_unchanged(self):` |
| `105` | Warning | PY_TYPING | Missing return type hint for function 'test_same_args_same_key' | `def test_same_args_same_key(self):` |
| `109` | Warning | PY_TYPING | Missing return type hint for function 'test_different_dict_ordering_same_key' | `def test_different_dict_ordering_same_key(self):` |
| `114` | Warning | PY_TYPING | Missing return type hint for function 'test_uuid_object_vs_string_same_key' | `def test_uuid_object_vs_string_same_key(self):` |
| `119` | Warning | PY_TYPING | Missing return type hint for function 'test_auth_keys_excluded_from_hash' | `def test_auth_keys_excluded_from_hash(self):` |
| `128` | Warning | PY_TYPING | Missing return type hint for function 'test_tool_name_too_long_raises' | `def test_tool_name_too_long_raises(self):` |
| `132` | Warning | PY_TYPING | Missing return type hint for function 'test_arguments_too_large_raises' | `def test_arguments_too_large_raises(self):` |
| `137` | Warning | PY_TYPING | Missing return type hint for function 'test_generation_changes_key' | `def test_generation_changes_key(self):` |
| `141` | Warning | PY_TYPING | Missing return type hint for function 'test_namespace_scopes_key' | `def test_namespace_scopes_key(self):` |
| `146` | Warning | PY_TYPING | Missing return type hint for function 'test_key_format_prefix' | `def test_key_format_prefix(self):` |
| `150` | Warning | PY_TYPING | Missing return type hint for function 'test_invalid_namespace_in_args_raises' | `def test_invalid_namespace_in_args_raises(self):` |
| `156` | Warning | PY_TYPING | Missing return type hint for function 'test_valid_nested_accepted' | `def test_valid_nested_accepted(self):` |
| `162` | Warning | PY_TYPING | Missing return type hint for function 'test_does_not_mutate_original_dict' | `def test_does_not_mutate_original_dict(self):` |
| `168` | Warning | PY_TYPING | Missing return type hint for function 'test_invalid_nested_raises_valueerror' | `def test_invalid_nested_raises_valueerror(self):` |
| `173` | Warning | PY_TYPING | Missing return type hint for function 'test_non_dict_nested_raises_valueerror' | `def test_non_dict_nested_raises_valueerror(self):` |
| `178` | Warning | PY_TYPING | Missing return type hint for function 'test_absent_field_passes_through' | `def test_absent_field_passes_through(self):` |
| `184` | Warning | PY_TYPING | Missing return type hint for function 'test_no_nested_fields_returns_same_dict' | `def test_no_nested_fields_returns_same_dict(self):` |

---

### Module: `tests/test_mcp_cache.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `44` | Warning | PY_TYPING | Missing return type hint for function 'test_includes_namespace_id' | `def test_includes_namespace_id(self):` |
| `49` | Warning | PY_TYPING | Missing return type hint for function 'test_different_namespaces_different_keys' | `def test_different_namespaces_different_keys(self):` |
| `55` | Warning | PY_TYPING | Missing return type hint for function 'test_none_namespace_uses_global' | `def test_none_namespace_uses_global(self):` |
| `59` | Warning | PY_TYPING | Missing return type hint for function 'test_same_args_same_namespace_same_key' | `def test_same_args_same_namespace_same_key(self):` |
| `66` | Warning | PY_TYPING | Missing return type hint for function 'test_different_generations_different_keys' | `def test_different_generations_different_keys(self):` |
| `82` | Warning | PY_TYPING | Missing return type hint for function 'test_valid_uuid' | `def test_valid_uuid(self):` |
| `85` | Warning | PY_TYPING | Missing return type hint for function 'test_missing_key' | `def test_missing_key(self):` |
| `88` | Warning | PY_TYPING | Missing return type hint for function 'test_invalid_uuid' | `def test_invalid_uuid(self):` |
| `92` | Warning | PY_TYPING | Missing return type hint for function 'test_none_value' | `def test_none_value(self):` |
| `104` | Warning | PY_TYPING | Missing return type hint for function 'test_namespace_pattern_format' | `def test_namespace_pattern_format(self):` |
| `109` | Warning | PY_TYPING | Missing return type hint for function 'test_document_pattern_format' | `def test_document_pattern_format(self):` |
| `124` | Warning | PY_TYPING | Missing return type hint for async function 'test_deletes_matching_keys' | `async def test_deletes_matching_keys(self):` |
| `144` | Warning | PY_TYPING | Missing return type hint for async function 'test_noop_when_no_keys' | `async def test_noop_when_no_keys(self):` |
| `154` | Warning | PY_TYPING | Missing return type hint for async function 'test_multi_cursor_pagination' | `async def test_multi_cursor_pagination(self):` |
| `178` | Warning | PY_TYPING | Missing return type hint for async function 'test_deletes_matching_keys' | `async def test_deletes_matching_keys(self):` |
| `199` | Warning | PY_TYPING | Missing return type hint for function 'test_delete_is_valid' | `def test_delete_is_valid(self):` |
| `212` | Warning | PY_TYPING | Missing return type hint for function 'mock_engine' | `def mock_engine():` |
| `227` | Warning | PY_TYPING | Missing return type hint for function 'setup_server_engine' | `def setup_server_engine(mock_engine):` |
| `227` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in function 'setup_server_engine' | `def setup_server_engine(mock_engine):` |
| `237` | Warning | PY_TYPING | Missing return type hint for function 'disable_quotas' | `def disable_quotas(monkeypatch):` |
| `237` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'disable_quotas' | `def disable_quotas(monkeypatch):` |
| `245` | Warning | PY_TYPING | Missing return type hint for async function 'test_cache_miss_writes_namespace_scoped_key' | `async def test_cache_miss_writes_namespace_scoped_key(mock_engine):` |
| `245` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_cache_miss_writes_namespace_scoped_key' | `async def test_cache_miss_writes_namespace_scoped_key(mock_engine):` |
| `270` | Warning | PY_TYPING | Missing return type hint for async function 'test_cache_hit_returns_cached_value' | `async def test_cache_hit_returns_cached_value(mock_engine):` |
| `270` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_cache_hit_returns_cached_value' | `async def test_cache_hit_returns_cached_value(mock_engine):` |
| `274` | Warning | PY_TYPING | Missing return type hint for async function 'mock_get' | `async def mock_get(key):` |
| `274` | Warning | PY_TYPING | Missing type hint for argument 'key' in async function 'mock_get' | `async def mock_get(key):` |
| `296` | Warning | PY_TYPING | Missing return type hint for async function 'test_mutation_bumps_generation' | `async def test_mutation_bumps_generation(mock_engine):` |
| `296` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_mutation_bumps_generation' | `async def test_mutation_bumps_generation(mock_engine):` |
| `315` | Warning | PY_TYPING | Missing return type hint for async function 'test_forget_memory_triggers_document_purge' | `async def test_forget_memory_triggers_document_purge(mock_engine):` |
| `315` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_forget_memory_triggers_document_purge' | `async def test_forget_memory_triggers_document_purge(mock_engine):` |
| `338` | Warning | PY_TYPING | Missing return type hint for async function 'test_cacheable_search_codebase' | `async def test_cacheable_search_codebase(mock_engine):` |
| `338` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_cacheable_search_codebase' | `async def test_cacheable_search_codebase(mock_engine):` |
| `354` | Warning | PY_TYPING | Missing return type hint for async function 'test_cacheable_graph_search' | `async def test_cacheable_graph_search(mock_engine):` |
| `354` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_cacheable_graph_search' | `async def test_cacheable_graph_search(mock_engine):` |

---

### Module: `tests/test_mcp_errors.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `20` | Warning | PY_TYPING | Missing return type hint for async function 'raises_validation_error' | `async def raises_validation_error(engine, arguments):` |
| `20` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'raises_validation_error' | `async def raises_validation_error(engine, arguments):` |
| `20` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'raises_validation_error' | `async def raises_validation_error(engine, arguments):` |
| `30` | Warning | PY_TYPING | Missing return type hint for async function 'raises_quota_exceeded' | `async def raises_quota_exceeded(engine, arguments):` |
| `30` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'raises_quota_exceeded' | `async def raises_quota_exceeded(engine, arguments):` |
| `30` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'raises_quota_exceeded' | `async def raises_quota_exceeded(engine, arguments):` |
| `37` | Warning | PY_TYPING | Missing return type hint for async function 'raises_key_error' | `async def raises_key_error(engine, arguments):` |
| `37` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'raises_key_error' | `async def raises_key_error(engine, arguments):` |
| `37` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'raises_key_error' | `async def raises_key_error(engine, arguments):` |
| `42` | Warning | PY_TYPING | Missing return type hint for async function 'raises_value_error' | `async def raises_value_error(engine, arguments):` |
| `42` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'raises_value_error' | `async def raises_value_error(engine, arguments):` |
| `42` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'raises_value_error' | `async def raises_value_error(engine, arguments):` |
| `47` | Warning | PY_TYPING | Missing return type hint for async function 'raises_type_error' | `async def raises_type_error(engine, arguments):` |
| `47` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'raises_type_error' | `async def raises_type_error(engine, arguments):` |
| `47` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'raises_type_error' | `async def raises_type_error(engine, arguments):` |
| `52` | Warning | PY_TYPING | Missing return type hint for async function 'raises_generic_exception' | `async def raises_generic_exception(engine, arguments):` |
| `52` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'raises_generic_exception' | `async def raises_generic_exception(engine, arguments):` |
| `52` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'raises_generic_exception' | `async def raises_generic_exception(engine, arguments):` |
| `57` | Warning | PY_TYPING | Missing return type hint for async function 'raises_scope_error' | `async def raises_scope_error(engine, arguments):` |
| `57` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'raises_scope_error' | `async def raises_scope_error(engine, arguments):` |
| `57` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'raises_scope_error' | `async def raises_scope_error(engine, arguments):` |
| `64` | Warning | PY_TYPING | Missing return type hint for async function 'raises_mcp_error' | `async def raises_mcp_error(engine, arguments):` |
| `64` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'raises_mcp_error' | `async def raises_mcp_error(engine, arguments):` |
| `64` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'raises_mcp_error' | `async def raises_mcp_error(engine, arguments):` |
| `69` | Warning | PY_TYPING | Missing return type hint for async function 'returns_value' | `async def returns_value(engine, arguments):` |
| `69` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'returns_value' | `async def returns_value(engine, arguments):` |
| `69` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'returns_value' | `async def returns_value(engine, arguments):` |
| `75` | Warning | PY_TYPING | Missing return type hint for async function 'test_success_passes_through' | `async def test_success_passes_through(self):` |
| `80` | Warning | PY_TYPING | Missing return type hint for async function 'test_validation_error_maps_to_invalid_params' | `async def test_validation_error_maps_to_invalid_params(self):` |
| `88` | Warning | PY_TYPING | Missing return type hint for async function 'test_quota_exceeded_maps_to_quota_code' | `async def test_quota_exceeded_maps_to_quota_code(self):` |
| `95` | Warning | PY_TYPING | Missing return type hint for async function 'test_key_error_maps_to_invalid_params_missing_field' | `async def test_key_error_maps_to_invalid_params_missing_field(self):` |
| `102` | Warning | PY_TYPING | Missing return type hint for async function 'test_value_error_maps_to_invalid_params' | `async def test_value_error_maps_to_invalid_params(self):` |
| `109` | Warning | PY_TYPING | Missing return type hint for async function 'test_type_error_maps_to_invalid_params' | `async def test_type_error_maps_to_invalid_params(self):` |
| `115` | Warning | PY_TYPING | Missing return type hint for async function 'test_generic_exception_maps_to_internal_error' | `async def test_generic_exception_maps_to_internal_error(self):` |
| `121` | Warning | PY_TYPING | Missing return type hint for async function 'test_scope_error_propagates_unchanged' | `async def test_scope_error_propagates_unchanged(self):` |
| `128` | Warning | PY_TYPING | Missing return type hint for async function 'test_mcp_error_propagates_unchanged' | `async def test_mcp_error_propagates_unchanged(self):` |
| `136` | Warning | PY_TYPING | Missing return type hint for async function 'test_internal_error_does_not_leak_exception_text_in_prod' | `async def test_internal_error_does_not_leak_exception_text_in_prod(self, monkeypatch):` |
| `136` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_internal_error_does_not_leak_exception_text_in_prod' | `async def test_internal_error_does_not_leak_exception_text_in_prod(self, monkeypatch):` |
| `145` | Warning | PY_TYPING | Missing return type hint for async function 'test_internal_error_includes_detail_in_dev' | `async def test_internal_error_includes_detail_in_dev(self, monkeypatch):` |
| `145` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_internal_error_includes_detail_in_dev' | `async def test_internal_error_includes_detail_in_dev(self, monkeypatch):` |
| `152` | Warning | PY_TYPING | Missing return type hint for async function 'test_internal_error_includes_request_id' | `async def test_internal_error_includes_request_id(self, monkeypatch):` |
| `152` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_internal_error_includes_request_id' | `async def test_internal_error_includes_request_id(self, monkeypatch):` |
| `160` | Warning | PY_TYPING | Missing return type hint for async function 'test_key_error_does_not_expose_field_name' | `async def test_key_error_does_not_expose_field_name(self):` |
| `166` | Warning | PY_TYPING | Missing return type hint for async function 'test_value_error_detail_not_in_response' | `async def test_value_error_detail_not_in_response(self, monkeypatch):` |
| `166` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_value_error_detail_not_in_response' | `async def test_value_error_detail_not_in_response(self, monkeypatch):` |
| `170` | Warning | PY_TYPING | Missing return type hint for async function 'leaky' | `async def leaky(engine, arguments):` |
| `170` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'leaky' | `async def leaky(engine, arguments):` |
| `170` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'leaky' | `async def leaky(engine, arguments):` |
| `181` | Warning | PY_TYPING | Missing return type hint for async function 'test_internal_error_includes_reason_field' | `async def test_internal_error_includes_reason_field(self, monkeypatch):` |
| `181` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_internal_error_includes_reason_field' | `async def test_internal_error_includes_reason_field(self, monkeypatch):` |
| `188` | Warning | PY_TYPING | Missing return type hint for async function 'test_quota_error_includes_reason' | `async def test_quota_error_includes_reason(self):` |
| `194` | Warning | PY_TYPING | Missing return type hint for async function 'test_validation_error_includes_structured_errors' | `async def test_validation_error_includes_structured_errors(self):` |
| `205` | Warning | PY_TYPING | Missing return type hint for async function 'test_sync_handler_works' | `async def test_sync_handler_works(self):` |
| `207` | Warning | PY_TYPING | Missing return type hint for function 'sync_handler' | `def sync_handler(engine, arguments):` |
| `207` | Warning | PY_TYPING | Missing type hint for argument 'engine' in function 'sync_handler' | `def sync_handler(engine, arguments):` |
| `207` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in function 'sync_handler' | `def sync_handler(engine, arguments):` |
| `214` | Warning | PY_TYPING | Missing return type hint for async function 'test_return_value_preserved_async' | `async def test_return_value_preserved_async(self):` |
| `219` | Warning | PY_TYPING | Missing return type hint for async function 'test_every_exception_becomes_mcp_error' | `async def test_every_exception_becomes_mcp_error(self):` |
| `221` | Warning | PY_TYPING | Missing return type hint for async function 'raises_os_error' | `async def raises_os_error(engine, arguments):` |
| `221` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'raises_os_error' | `async def raises_os_error(engine, arguments):` |
| `221` | Warning | PY_TYPING | Missing type hint for argument 'arguments' in async function 'raises_os_error' | `async def raises_os_error(engine, arguments):` |

---

### Module: `tests/test_mcp_handlers_coverage.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `454` | Warning | PY_TYPING | Missing return type hint for async function '_cm' | `async def _cm():` |
| `458` | Warning | PY_TYPING | Missing return type hint for async function '_tx' | `async def _tx():` |
| `467` | Warning | PY_TYPING | Missing return type hint for async function '_append' | `async def _append(*, conn, **kwargs):` |
| `487` | Warning | PY_TYPING | Missing return type hint for async function '_gen' | `async def _gen():` |
| `492` | Warning | PY_TYPING | Missing return type hint for async function 'execute' | `async def execute(self, **kwargs):` |
| `522` | Warning | PY_TYPING | Missing return type hint for async function 'execute' | `async def execute(self, **kwargs):` |
| `833` | Warning | PY_TYPING | Missing return type hint for async function '_get_by_id' | `async def _get_by_id(_c: object, _bid: uuid.UUID):` |
| `1167` | Warning | PY_TYPING | Missing return type hint for async function '_get_by_id' | `async def _get_by_id(_c: object, _i: uuid.UUID):` |
| `1226` | Warning | PY_TYPING | Missing return type hint for async function '_get' | `async def _get(_c: object, _i: uuid.UUID):` |
| `1584` | Warning | PY_TYPING | Missing return type hint for async function '_gen' | `async def _gen():` |
| `1589` | Warning | PY_TYPING | Missing return type hint for async function 'execute' | `async def execute(self, **kwargs):` |
| `1629` | Warning | PY_TYPING | Missing return type hint for async function 'execute' | `async def execute(self, **kwargs):` |

---

### Module: `tests/test_mcp_utils.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `28` | Warning | PY_TYPING | Missing return type hint for function 'test_valid_namespace_and_agent_id_returns_namespace_context' | `def test_valid_namespace_and_agent_id_returns_namespace_context(self):` |
| `34` | Warning | PY_TYPING | Missing return type hint for function 'test_missing_namespace_id_raises_valueerror' | `def test_missing_namespace_id_raises_valueerror(self):` |
| `38` | Warning | PY_TYPING | Missing return type hint for function 'test_malformed_namespace_id_raises_valueerror' | `def test_malformed_namespace_id_raises_valueerror(self):` |
| `42` | Warning | PY_TYPING | Missing return type hint for function 'test_blank_agent_id_resolves_to_default' | `def test_blank_agent_id_resolves_to_default(self):` |
| `47` | Warning | PY_TYPING | Missing return type hint for function 'test_agent_id_over_128_chars_truncated' | `def test_agent_id_over_128_chars_truncated(self):` |
| `55` | Warning | PY_TYPING | Missing return type hint for function 'test_valid_json_string_returns_a2a_scopes' | `def test_valid_json_string_returns_a2a_scopes(self):` |
| `64` | Warning | PY_TYPING | Missing return type hint for function 'test_valid_list_input_returns_a2a_scopes' | `def test_valid_list_input_returns_a2a_scopes(self):` |
| `70` | Warning | PY_TYPING | Missing return type hint for function 'test_json_string_exceeding_max_bytes_raises' | `def test_json_string_exceeding_max_bytes_raises(self):` |
| `82` | Warning | PY_TYPING | Missing return type hint for function 'test_invalid_json_string_raises_with_not_valid_json' | `def test_invalid_json_string_raises_with_not_valid_json(self):` |
| `86` | Warning | PY_TYPING | Missing return type hint for function 'test_json_decoding_to_dict_raises' | `def test_json_decoding_to_dict_raises(self):` |
| `90` | Warning | PY_TYPING | Missing return type hint for function 'test_list_longer_than_max_items_raises' | `def test_list_longer_than_max_items_raises(self):` |
| `98` | Warning | PY_TYPING | Missing return type hint for function 'test_none_input_raises' | `def test_none_input_raises(self):` |
| `102` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_list_returns_empty' | `def test_empty_list_returns_empty(self):` |

---

### Module: `tests/test_memory_orchestrator_observability.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `53` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_duration_non_zero_with_work' | `def test_duration_non_zero_with_work(self, monkeypatch) -> None:` |
| `61` | Warning | PY_TYPING | Missing type hint for argument 'self_hist' in function '_capture_observe' | `def _capture_observe(self_hist, value: float) -> None:` |
| `83` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_duration_non_zero_with_async_work' | `async def test_duration_non_zero_with_async_work(self, monkeypatch) -> None:` |
| `90` | Warning | PY_TYPING | Missing type hint for argument 'self_hist' in function '_capture_observe' | `def _capture_observe(self_hist, value: float) -> None:` |
| `103` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_duration_near_zero_with_pass' | `def test_duration_near_zero_with_pass(self, monkeypatch) -> None:` |
| `111` | Warning | PY_TYPING | Missing type hint for argument 'self_hist' in function '_capture_observe' | `def _capture_observe(self_hist, value: float) -> None:` |
| `129` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_success_records_ok_result' | `def test_success_records_ok_result(self, monkeypatch) -> None:` |
| `138` | Warning | PY_TYPING | Missing return type hint for function '_capture_labels' | `def _capture_labels(**kw):` |
| `150` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_failure_records_failure_result' | `def test_failure_records_failure_result(self, monkeypatch) -> None:` |
| `159` | Warning | PY_TYPING | Missing return type hint for function '_capture_labels' | `def _capture_labels(**kw):` |
| `176` | Warning | PY_TYPING | Missing return type hint for function '_cb' | `def _cb(exc):` |
| `176` | Warning | PY_TYPING | Missing type hint for argument 'exc' in function '_cb' | `def _cb(exc):` |
| `191` | Warning | PY_TYPING | Missing return type hint for function '_cb' | `def _cb(exc):` |
| `191` | Warning | PY_TYPING | Missing type hint for argument 'exc' in function '_cb' | `def _cb(exc):` |
| `208` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_span_entered_and_exited' | `def test_span_entered_and_exited(self, monkeypatch) -> None:` |
| `215` | Warning | PY_TYPING | Missing return type hint for function '__enter__' | `def __enter__(self_span):` |
| `215` | Warning | PY_TYPING | Missing type hint for argument 'self_span' in function '__enter__' | `def __enter__(self_span):` |
| `219` | Warning | PY_TYPING | Missing return type hint for function '__exit__' | `def __exit__(self_span, *args):` |
| `219` | Warning | PY_TYPING | Missing type hint for argument 'self_span' in function '__exit__' | `def __exit__(self_span, *args):` |
| `222` | Warning | PY_TYPING | Missing return type hint for function 'set_attribute' | `def set_attribute(self, *args):` |
| `226` | Warning | PY_TYPING | Missing return type hint for function 'start_as_current_span' | `def start_as_current_span(self, name, **kw):` |
| `226` | Warning | PY_TYPING | Missing type hint for argument 'name' in function 'start_as_current_span' | `def start_as_current_span(self, name, **kw):` |
| `389` | Warning | PY_TYPING | Missing return type hint for function 'mock_pg_pool' | `def mock_pg_pool(self):` |
| `409` | Warning | PY_TYPING | Missing return type hint for function 'mock_mongo_client' | `def mock_mongo_client(self):` |
| `425` | Warning | PY_TYPING | Missing return type hint for function 'mock_redis_client' | `def mock_redis_client(self):` |
| `433` | Warning | PY_TYPING | Missing return type hint for function 'orchestrator' | `def orchestrator(self, mock_pg_pool, mock_mongo_client, mock_redis_client):` |
| `433` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in function 'orchestrator' | `def orchestrator(self, mock_pg_pool, mock_mongo_client, mock_redis_client):` |
| `433` | Warning | PY_TYPING | Missing type hint for argument 'mock_mongo_client' in function 'orchestrator' | `def orchestrator(self, mock_pg_pool, mock_mongo_client, mock_redis_client):` |
| `433` | Warning | PY_TYPING | Missing type hint for argument 'mock_redis_client' in function 'orchestrator' | `def orchestrator(self, mock_pg_pool, mock_mongo_client, mock_redis_client):` |
| `444` | Warning | PY_TYPING | Missing return type hint for function 'store_payload' | `def store_payload(self):` |
| `459` | Warning | PY_TYPING | Missing type hint for argument 'orchestrator' in async function 'test_store_memory_saga_metrics_records_work' | `async def test_store_memory_saga_metrics_records_work(` |
| `459` | Warning | PY_TYPING | Missing type hint for argument 'store_payload' in async function 'test_store_memory_saga_metrics_records_work' | `async def test_store_memory_saga_metrics_records_work(` |
| `459` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_store_memory_saga_metrics_records_work' | `async def test_store_memory_saga_metrics_records_work(` |
| `471` | Warning | PY_TYPING | Missing return type hint for function '_capture_labels' | `def _capture_labels(**kw):` |
| `475` | Warning | PY_TYPING | Missing return type hint for function 'observe' | `def observe(self_hist, value):` |
| `475` | Warning | PY_TYPING | Missing type hint for argument 'self_hist' in function 'observe' | `def observe(self_hist, value):` |
| `475` | Warning | PY_TYPING | Missing type hint for argument 'value' in function 'observe' | `def observe(self_hist, value):` |
| `516` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `536` | Warning | PY_TYPING | Missing type hint for argument 'orchestrator' in async function 'test_store_memory_span_entered' | `async def test_store_memory_span_entered(` |
| `536` | Warning | PY_TYPING | Missing type hint for argument 'store_payload' in async function 'test_store_memory_span_entered' | `async def test_store_memory_span_entered(` |
| `536` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_store_memory_span_entered' | `async def test_store_memory_span_entered(` |
| `544` | Warning | PY_TYPING | Missing return type hint for function '__enter__' | `def __enter__(self_span):` |
| `544` | Warning | PY_TYPING | Missing type hint for argument 'self_span' in function '__enter__' | `def __enter__(self_span):` |
| `548` | Warning | PY_TYPING | Missing return type hint for function '__exit__' | `def __exit__(self_span, *args):` |
| `548` | Warning | PY_TYPING | Missing type hint for argument 'self_span' in function '__exit__' | `def __exit__(self_span, *args):` |
| `551` | Warning | PY_TYPING | Missing return type hint for function 'set_attribute' | `def set_attribute(self, *args):` |
| `555` | Warning | PY_TYPING | Missing return type hint for function 'start_as_current_span' | `def start_as_current_span(self, name, **kw):` |
| `555` | Warning | PY_TYPING | Missing type hint for argument 'name' in function 'start_as_current_span' | `def start_as_current_span(self, name, **kw):` |
| `598` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `605` | Warning | PY_TYPING | Missing type hint for argument 'orchestrator' in async function 'test_store_media_saga_metrics_records_work' | `async def test_store_media_saga_metrics_records_work(self, orchestrator, monkeypatch) -> None:` |
| `605` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_store_media_saga_metrics_records_work' | `async def test_store_media_saga_metrics_records_work(self, orchestrator, monkeypatch) -> None:` |
| `614` | Warning | PY_TYPING | Missing return type hint for function '_capture_labels' | `def _capture_labels(**kw):` |
| `618` | Warning | PY_TYPING | Missing return type hint for function 'observe' | `def observe(self_hist, value):` |
| `618` | Warning | PY_TYPING | Missing type hint for argument 'self_hist' in function 'observe' | `def observe(self_hist, value):` |
| `618` | Warning | PY_TYPING | Missing type hint for argument 'value' in function 'observe' | `def observe(self_hist, value):` |
| `662` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `673` | Warning | PY_TYPING | Missing type hint for argument 'orchestrator' in async function 'test_store_media_span_entered' | `async def test_store_media_span_entered(self, orchestrator, monkeypatch) -> None:` |
| `673` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_store_media_span_entered' | `async def test_store_media_span_entered(self, orchestrator, monkeypatch) -> None:` |
| `679` | Warning | PY_TYPING | Missing return type hint for function '__enter__' | `def __enter__(self_span):` |
| `679` | Warning | PY_TYPING | Missing type hint for argument 'self_span' in function '__enter__' | `def __enter__(self_span):` |
| `683` | Warning | PY_TYPING | Missing return type hint for function '__exit__' | `def __exit__(self_span, *args):` |
| `683` | Warning | PY_TYPING | Missing type hint for argument 'self_span' in function '__exit__' | `def __exit__(self_span, *args):` |
| `686` | Warning | PY_TYPING | Missing return type hint for function 'set_attribute' | `def set_attribute(self, *args):` |
| `690` | Warning | PY_TYPING | Missing return type hint for function 'start_as_current_span' | `def start_as_current_span(self, name, **kw):` |
| `690` | Warning | PY_TYPING | Missing type hint for argument 'name' in function 'start_as_current_span' | `def start_as_current_span(self, name, **kw):` |
| `726` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |

---

### Module: `tests/test_memory_time_travel.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `297` | Warning | PY_TYPING | Missing return type hint for function 'time_travel_traverser' | `def time_travel_traverser(monkeypatch: pytest.MonkeyPatch):` |
| `494` | Warning | PY_TYPING | Missing return type hint for function 'now' | `def now(cls, tz=None):  # type: ignore[override]` |
| `494` | Warning | PY_TYPING | Missing type hint for argument 'tz' in function 'now' | `def now(cls, tz=None):  # type: ignore[override]` |

---

### Module: `tests/test_migration_mcp_handlers.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `26` | Warning | PY_TYPING | Missing return type hint for function '_bare_handler' | `def _bare_handler(handler):` |
| `26` | Warning | PY_TYPING | Missing type hint for argument 'handler' in function '_bare_handler' | `def _bare_handler(handler):` |
| `52` | Warning | PY_TYPING | Missing return type hint for async function '_tx' | `async def _tx():` |
| `58` | Warning | PY_TYPING | Missing return type hint for async function '_cm' | `async def _cm():` |
| `340` | Warning | PY_TYPING | Missing return type hint for async function '_append' | `async def _append(*, conn, **kwargs):` |
| `364` | Warning | PY_TYPING | Missing type hint for argument 'caplog' in async function 'test_admin_identity_truncated_in_info_log' | `async def test_admin_identity_truncated_in_info_log(self, caplog) -> None:` |
| `369` | Warning | PY_TYPING | Missing return type hint for async function '_append' | `async def _append(*, conn, **kwargs):` |

---

### Module: `tests/test_migration_orchestrator.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `185` | Warning | PY_TYPING | Missing return type hint for async function 'slow_get' | `async def slow_get(*_args, **_kwargs):` |

---

### Module: `tests/test_models.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `75` | Warning | PY_TYPING | Missing return type hint for function 'test_nested_dict_in_metadata_raises_validation_error' | `def test_nested_dict_in_metadata_raises_validation_error(self):` |
| `84` | Warning | PY_TYPING | Missing return type hint for function 'test_flat_scalar_metadata_accepted' | `def test_flat_scalar_metadata_accepted(self):` |
| `93` | Warning | PY_TYPING | Missing return type hint for function 'test_self_referential_edge_raises_validation_error' | `def test_self_referential_edge_raises_validation_error(self):` |
| `108` | Warning | PY_TYPING | Missing return type hint for function 'test_valid_uuid_strings_accepted' | `def test_valid_uuid_strings_accepted(self, model_cls):` |
| `108` | Warning | PY_TYPING | Missing type hint for argument 'model_cls' in function 'test_valid_uuid_strings_accepted' | `def test_valid_uuid_strings_accepted(self, model_cls):` |
| `125` | Warning | PY_TYPING | Missing return type hint for function 'test_invalid_uuid_string_raises_validation_error' | `def test_invalid_uuid_string_raises_validation_error(self, model_cls):` |
| `125` | Warning | PY_TYPING | Missing type hint for argument 'model_cls' in function 'test_invalid_uuid_string_raises_validation_error' | `def test_invalid_uuid_string_raises_validation_error(self, model_cls):` |
| `145` | Warning | PY_TYPING | Missing return type hint for function 'test_expected_sha256_spaces_raises_validation_error' | `def test_expected_sha256_spaces_raises_validation_error(self):` |
| `156` | Warning | PY_TYPING | Missing return type hint for function 'test_expected_sha256_uppercase_hex_raises_validation_error' | `def test_expected_sha256_uppercase_hex_raises_validation_error(self):` |
| `167` | Warning | PY_TYPING | Missing return type hint for function 'test_valid_lowercase_hex_accepted' | `def test_valid_lowercase_hex_accepted(self):` |
| `172` | Warning | PY_TYPING | Missing return type hint for function 'test_checksum_mismatch_message_sanitized' | `def test_checksum_mismatch_message_sanitized(self):` |
| `190` | Warning | PY_TYPING | Missing return type hint for function 'test_shorter_than_8_utf8_bytes_raises_validation_error' | `def test_shorter_than_8_utf8_bytes_raises_validation_error(self):` |
| `194` | Warning | PY_TYPING | Missing return type hint for function 'test_exactly_8_bytes_accepted' | `def test_exactly_8_bytes_accepted(self):` |
| `198` | Warning | PY_TYPING | Missing return type hint for function 'test_none_accepted' | `def test_none_accepted(self):` |
| `204` | Warning | PY_TYPING | Missing return type hint for function 'test_store_memory_content_over_1mb_utf8_raises_validation_error' | `def test_store_memory_content_over_1mb_utf8_raises_validation_error(self):` |
| `213` | Warning | PY_TYPING | Missing return type hint for function 'test_store_memory_single_char_content_accepted' | `def test_store_memory_single_char_content_accepted(self):` |
| `222` | Warning | PY_TYPING | Missing return type hint for function 'test_semantic_search_query_over_limit_raises_validation_error' | `def test_semantic_search_query_over_limit_raises_validation_error(self):` |
| `231` | Warning | PY_TYPING | Missing return type hint for function 'test_graph_search_query_over_limit_raises_validation_error' | `def test_graph_search_query_over_limit_raises_validation_error(self):` |
| `242` | Warning | PY_TYPING | Missing return type hint for function 'test_user_id_promoted_when_agent_id_none' | `def test_user_id_promoted_when_agent_id_none(self):` |
| `252` | Warning | PY_TYPING | Missing return type hint for function 'test_explicit_agent_id_wins_over_user_id' | `def test_explicit_agent_id_wins_over_user_id(self):` |
| `262` | Warning | PY_TYPING | Missing return type hint for function 'test_default_user_id_does_not_set_agent_id' | `def test_default_user_id_does_not_set_agent_id(self):` |

---

### Module: `tests/test_mongo_bulk.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `208` | Warning | PY_TYPING | Missing return type hint for function 'find_side_effect' | `def find_side_effect(filter_doc, projection=None, max_time_ms=None):` |
| `208` | Warning | PY_TYPING | Missing type hint for argument 'filter_doc' in function 'find_side_effect' | `def find_side_effect(filter_doc, projection=None, max_time_ms=None):` |
| `208` | Warning | PY_TYPING | Missing type hint for argument 'projection' in function 'find_side_effect' | `def find_side_effect(filter_doc, projection=None, max_time_ms=None):` |
| `208` | Warning | PY_TYPING | Missing type hint for argument 'max_time_ms' in function 'find_side_effect' | `def find_side_effect(filter_doc, projection=None, max_time_ms=None):` |

---

### Module: `tests/test_mtls.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `45` | Warning | PY_TYPING | Missing return type hint for async function 'receive' | `async def receive():` |
| `48` | Warning | PY_TYPING | Missing return type hint for async function 'send' | `async def send(message):` |
| `48` | Warning | PY_TYPING | Missing type hint for argument 'message' in async function 'send' | `async def send(message):` |
| `68` | Warning | PY_TYPING | Missing return type hint for function 'test_enabled_true_without_anchors_raises' | `def test_enabled_true_without_anchors_raises(self):` |
| `72` | Warning | PY_TYPING | Missing return type hint for function 'test_enabled_true_with_sans_ok' | `def test_enabled_true_with_sans_ok(self):` |
| `77` | Warning | PY_TYPING | Missing return type hint for function 'test_enabled_false_no_error_warns' | `def test_enabled_false_no_error_warns(self, caplog: pytest.LogCaptureFixture):` |
| `90` | Warning | PY_TYPING | Missing return type hint for function 'test_sans_lowercased' | `def test_sans_lowercased(self):` |
| `94` | Warning | PY_TYPING | Missing return type hint for function 'test_fingerprints_lowercased' | `def test_fingerprints_lowercased(self):` |
| `107` | Warning | PY_TYPING | Missing return type hint for async function 'test_protected_paths_trigger_enforcement' | `async def test_protected_paths_trigger_enforcement(self, path: str):` |
| `126` | Warning | PY_TYPING | Missing return type hint for async function 'test_non_matching_prefix_bypasses_enforcement' | `async def test_non_matching_prefix_bypasses_enforcement(self, path: str):` |
| `148` | Warning | PY_TYPING | Missing return type hint for async function 'test_opaque_reason_not_exception_string' | `async def test_opaque_reason_not_exception_string(self):` |
| `169` | Warning | PY_TYPING | Missing return type hint for async function 'test_x_request_id_propagated_to_json_id' | `async def test_x_request_id_propagated_to_json_id(self):` |
| `191` | Warning | PY_TYPING | Missing return type hint for async function 'test_missing_x_request_id_yields_null_id' | `async def test_missing_x_request_id_yields_null_id(self):` |
| `214` | Warning | PY_TYPING | Missing return type hint for async function 'test_default_error_code_is_minus_32010' | `async def test_default_error_code_is_minus_32010(self):` |
| `236` | Warning | PY_TYPING | Missing return type hint for async function 'test_oversized_header_dropped_enforce_still_called' | `async def test_oversized_header_dropped_enforce_still_called(` |
| `266` | Warning | PY_TYPING | Missing return type hint for async function 'test_headers_within_limit_passed_to_enforce' | `async def test_headers_within_limit_passed_to_enforce(self):` |
| `300` | Warning | PY_TYPING | Missing return type hint for async function 'test_disabled_skips_enforcement_entirely' | `async def test_disabled_skips_enforcement_entirely(self):` |
| `318` | Warning | PY_TYPING | Missing return type hint for async function 'test_rejection_log_contains_path_and_client_ip' | `async def test_rejection_log_contains_path_and_client_ip(` |
| `350` | Warning | PY_TYPING | Missing return type hint for async function 'test_websocket_scope_passes_through' | `async def test_websocket_scope_passes_through(self):` |
| `365` | Warning | PY_TYPING | Missing return type hint for async function 'test_valid_cert_reaches_downstream' | `async def test_valid_cert_reaches_downstream(self):` |
| `380` | Warning | PY_TYPING | Missing return type hint for function 'test_enabled_defaults_to_false' | `def test_enabled_defaults_to_false(self):` |
| `384` | Warning | PY_TYPING | Missing return type hint for function 'test_strict_defaults_to_true' | `def test_strict_defaults_to_true(self):` |
| `388` | Warning | PY_TYPING | Missing return type hint for function 'test_allowed_sans_defaults_to_empty_list' | `def test_allowed_sans_defaults_to_empty_list(self):` |
| `392` | Warning | PY_TYPING | Missing return type hint for function 'test_allowed_fingerprints_defaults_to_empty_list' | `def test_allowed_fingerprints_defaults_to_empty_list(self):` |
| `396` | Warning | PY_TYPING | Missing return type hint for function 'test_none_sans_coerced_to_empty_list' | `def test_none_sans_coerced_to_empty_list(self):` |

---

### Module: `tests/test_net_safety.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `40` | Warning | PY_TYPING | Missing return type hint for function '_require_url_matches_prefix' | `def _require_url_matches_prefix():` |
| `52` | Warning | PY_TYPING | Missing return type hint for function '_mock_getaddrinfo' | `def _mock_getaddrinfo(ip_str: str, family: int = socket.AF_INET):` |
| `55` | Warning | PY_TYPING | Missing return type hint for function 'mock_getaddrinfo' | `def mock_getaddrinfo(` |
| `89` | Warning | PY_TYPING | Missing return type hint for function 'test_max_url_len_is_4096' | `def test_max_url_len_is_4096(self):` |
| `123` | Warning | PY_TYPING | Missing return type hint for function 'test_url_matches_prefix' | `def test_url_matches_prefix(self, url: str, prefix: str, expected: bool):` |
| `136` | Warning | PY_TYPING | Missing return type hint for function '_public_dns' | `def _public_dns(self, monkeypatch: pytest.MonkeyPatch):` |
| `139` | Warning | PY_TYPING | Missing return type hint for function 'test_validate_bridge_webhook_base_url_accepts_4096_chars' | `def test_validate_bridge_webhook_base_url_accepts_4096_chars(self):` |
| `162` | Warning | PY_TYPING | Missing return type hint for function 'test_all_validators_reject_4097_chars' | `def test_all_validators_reject_4097_chars(` |
| `162` | Warning | PY_TYPING | Missing type hint for argument 'validator' in function 'test_all_validators_reject_4097_chars' | `def test_all_validators_reject_4097_chars(` |
| `192` | Warning | PY_TYPING | Missing return type hint for function 'test_assert_url_allowed_prefix_accepts_4096_chars' | `def test_assert_url_allowed_prefix_accepts_4096_chars(self):` |
| `199` | Warning | PY_TYPING | Missing return type hint for function 'test_validate_extractor_url_accepts_4096_chars' | `def test_validate_extractor_url_accepts_4096_chars(self):` |
| `203` | Warning | PY_TYPING | Missing return type hint for function 'test_validate_webhook_payload_url_accepts_4096_char_absolute_url' | `def test_validate_webhook_payload_url_accepts_4096_char_absolute_url(` |
| `215` | Warning | PY_TYPING | Missing return type hint for function 'test_validate_webhook_payload_url_accepts_4096_char_relative_path' | `def test_validate_webhook_payload_url_accepts_4096_char_relative_path(self):` |
| `229` | Warning | PY_TYPING | Missing return type hint for function '_public_dns' | `def _public_dns(self, monkeypatch: pytest.MonkeyPatch):` |
| `241` | Warning | PY_TYPING | Missing return type hint for function 'test_validate_bridge_webhook_base_url_rejects_credentials' | `def test_validate_bridge_webhook_base_url_rejects_credentials(self, url: str):` |
| `257` | Warning | PY_TYPING | Missing return type hint for function 'test_assert_url_allowed_prefix_rejects_credentials' | `def test_assert_url_allowed_prefix_rejects_credentials(self, url: str):` |
| `273` | Warning | PY_TYPING | Missing return type hint for function 'test_validate_extractor_url_rejects_credentials' | `def test_validate_extractor_url_rejects_credentials(self, url: str):` |
| `289` | Warning | PY_TYPING | Missing return type hint for function 'test_validate_webhook_payload_url_rejects_credentials' | `def test_validate_webhook_payload_url_rejects_credentials(self, url: str):` |
| `296` | Warning | PY_TYPING | Missing return type hint for function 'test_https_evil_com_passes_credential_check_only' | `def test_https_evil_com_passes_credential_check_only(self, monkeypatch: pytest.MonkeyPatch):` |
| `314` | Warning | PY_TYPING | Missing return type hint for function '_graph_public_ip' | `def _graph_public_ip(self, monkeypatch: pytest.MonkeyPatch):` |
| `319` | Warning | PY_TYPING | Missing return type hint for function 'test_assert_url_allowed_prefix_exact_match' | `def test_assert_url_allowed_prefix_exact_match(self):` |
| `322` | Warning | PY_TYPING | Missing return type hint for function 'test_assert_url_allowed_prefix_path_descent' | `def test_assert_url_allowed_prefix_path_descent(self):` |
| `326` | Warning | PY_TYPING | Missing return type hint for function 'test_assert_url_allowed_prefix_rejects_subdomain_bypass' | `def test_assert_url_allowed_prefix_rejects_subdomain_bypass(self):` |
| `331` | Warning | PY_TYPING | Missing return type hint for function 'test_assert_url_allowed_prefix_rejects_credential_bypass' | `def test_assert_url_allowed_prefix_rejects_credential_bypass(self):` |
| `336` | Warning | PY_TYPING | Missing return type hint for function 'test_assert_url_allowed_prefix_rejects_http_scheme' | `def test_assert_url_allowed_prefix_rejects_http_scheme(self):` |
| `341` | Warning | PY_TYPING | Missing return type hint for function 'test_validate_webhook_payload_url_accepts_graph_path_descent' | `def test_validate_webhook_payload_url_accepts_graph_path_descent(` |
| `350` | Warning | PY_TYPING | Missing return type hint for function 'test_validate_webhook_payload_url_rejects_subdomain_bypass' | `def test_validate_webhook_payload_url_rejects_subdomain_bypass(` |
| `358` | Warning | PY_TYPING | Missing return type hint for function 'test_validate_webhook_payload_url_rejects_credential_bypass' | `def test_validate_webhook_payload_url_rejects_credential_bypass(` |
| `373` | Warning | PY_TYPING | Missing return type hint for function 'test_dns_gaierror_raises_bridge_validation_error' | `def test_dns_gaierror_raises_bridge_validation_error(self, monkeypatch: pytest.MonkeyPatch):` |
| `382` | Warning | PY_TYPING | Missing return type hint for function 'test_dns_failure_logs_truncated_host_only' | `def test_dns_failure_logs_truncated_host_only(` |
| `429` | Warning | PY_TYPING | Missing return type hint for function 'test_accepts_valid_https_graph_url' | `def test_accepts_valid_https_graph_url(self, monkeypatch: pytest.MonkeyPatch):` |
| `436` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_http_scheme' | `def test_rejects_http_scheme(self):` |
| `440` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_loopback_resolution' | `def test_rejects_loopback_resolution(self, monkeypatch: pytest.MonkeyPatch):` |
| `445` | Warning | PY_TYPING | Missing return type hint for function 'test_accepts_relative_sites_path' | `def test_accepts_relative_sites_path(self):` |
| `449` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_relative_admin_path' | `def test_rejects_relative_admin_path(self):` |
| `453` | Warning | PY_TYPING | Missing return type hint for function 'test_dns_warning_truncates_long_hostname_in_log' | `def test_dns_warning_truncates_long_hostname_in_log(` |
| `469` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except BridgeURLValidationError:` |
| `489` | Warning | PY_TYPING | Missing return type hint for function 'test_dns_failure_raises' | `def test_dns_failure_raises(self, monkeypatch: pytest.MonkeyPatch):` |
| `494` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_private_192_168' | `def test_rejects_private_192_168(self, monkeypatch: pytest.MonkeyPatch):` |
| `501` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_link_local_metadata_ip' | `def test_rejects_link_local_metadata_ip(self, monkeypatch: pytest.MonkeyPatch):` |
| `509` | Warning | PY_TYPING | Missing return type hint for function 'test_accepts_public_https_host' | `def test_accepts_public_https_host(self, monkeypatch: pytest.MonkeyPatch):` |
| `521` | Warning | PY_TYPING | Missing return type hint for function 'test_accepts_https_public_base' | `def test_accepts_https_public_base(self, monkeypatch: pytest.MonkeyPatch):` |
| `526` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_http_for_non_loopback' | `def test_rejects_http_for_non_loopback(self, monkeypatch: pytest.MonkeyPatch):` |
| `538` | Warning | PY_TYPING | Missing return type hint for function 'test_graph_prefix_in_allowed_list' | `def test_graph_prefix_in_allowed_list(self):` |

---

### Module: `tests/test_nli_integration.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `19` | Warning | PY_TYPING | Missing return type hint for async function '_acquire' | `async def _acquire(*_args, **_kwargs):` |
| `33` | Warning | PY_TYPING | Missing return type hint for async function 'complete' | `async def complete(self, messages: list, response_model: type):` |
| `38` | Warning | PY_TYPING | Missing return type hint for async function 'test_detect_uses_nli_and_skips_llm_on_strong_agreement' | `async def test_detect_uses_nli_and_skips_llm_on_strong_agreement():` |
| `98` | Warning | PY_TYPING | Missing return type hint for async function 'test_detect_llm_tiebreaker_prefers_llm_decision' | `async def test_detect_llm_tiebreaker_prefers_llm_decision():` |
| `159` | Warning | PY_TYPING | Missing return type hint for async function 'test_nli_caching' | `async def test_nli_caching():` |

---

### Module: `tests/test_notifications.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `19` | Warning | PY_TYPING | Missing return type hint for async function 'dispatcher' | `async def dispatcher():` |
| `31` | Warning | PY_TYPING | Missing return type hint for async function 'test_slack_dispatch' | `async def test_slack_dispatch(dispatcher):` |
| `31` | Warning | PY_TYPING | Missing type hint for argument 'dispatcher' in async function 'test_slack_dispatch' | `async def test_slack_dispatch(dispatcher):` |
| `44` | Warning | PY_TYPING | Missing return type hint for async function 'test_teams_dispatch' | `async def test_teams_dispatch(dispatcher):` |
| `44` | Warning | PY_TYPING | Missing type hint for argument 'dispatcher' in async function 'test_teams_dispatch' | `async def test_teams_dispatch(dispatcher):` |
| `57` | Warning | PY_TYPING | Missing return type hint for async function 'test_email_dispatch' | `async def test_email_dispatch(dispatcher, monkeypatch):` |
| `57` | Warning | PY_TYPING | Missing type hint for argument 'dispatcher' in async function 'test_email_dispatch' | `async def test_email_dispatch(dispatcher, monkeypatch):` |
| `57` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_email_dispatch' | `async def test_email_dispatch(dispatcher, monkeypatch):` |
| `75` | Warning | PY_TYPING | Missing return type hint for async function 'test_snmp_dispatch' | `async def test_snmp_dispatch(dispatcher):` |
| `75` | Warning | PY_TYPING | Missing type hint for argument 'dispatcher' in async function 'test_snmp_dispatch' | `async def test_snmp_dispatch(dispatcher):` |
| `86` | Warning | PY_TYPING | Missing return type hint for async function 'test_worker_dispatches_to_all_channels' | `async def test_worker_dispatches_to_all_channels(dispatcher):` |
| `86` | Warning | PY_TYPING | Missing type hint for argument 'dispatcher' in async function 'test_worker_dispatches_to_all_channels' | `async def test_worker_dispatches_to_all_channels(dispatcher):` |
| `113` | Warning | PY_TYPING | Missing return type hint for async function 'test_dispatch_alert_truncates_title' | `async def test_dispatch_alert_truncates_title(dispatcher):` |
| `113` | Warning | PY_TYPING | Missing type hint for argument 'dispatcher' in async function 'test_dispatch_alert_truncates_title' | `async def test_dispatch_alert_truncates_title(dispatcher):` |
| `124` | Warning | PY_TYPING | Missing return type hint for async function 'test_dispatch_alert_truncates_message' | `async def test_dispatch_alert_truncates_message(dispatcher):` |
| `124` | Warning | PY_TYPING | Missing type hint for argument 'dispatcher' in async function 'test_dispatch_alert_truncates_message' | `async def test_dispatch_alert_truncates_message(dispatcher):` |
| `134` | Warning | PY_TYPING | Missing return type hint for async function 'test_dispatch_alert_log_excludes_message_content' | `async def test_dispatch_alert_log_excludes_message_content(dispatcher):` |
| `134` | Warning | PY_TYPING | Missing type hint for argument 'dispatcher' in async function 'test_dispatch_alert_log_excludes_message_content' | `async def test_dispatch_alert_log_excludes_message_content(dispatcher):` |
| `145` | Warning | PY_TYPING | Missing return type hint for async function 'test_send_slack_raises_on_internal_ip_webhook' | `async def test_send_slack_raises_on_internal_ip_webhook(dispatcher):` |
| `145` | Warning | PY_TYPING | Missing type hint for argument 'dispatcher' in async function 'test_send_slack_raises_on_internal_ip_webhook' | `async def test_send_slack_raises_on_internal_ip_webhook(dispatcher):` |
| `155` | Warning | PY_TYPING | Missing return type hint for async function 'test_send_email_raises_on_internal_ip_smtp_host' | `async def test_send_email_raises_on_internal_ip_smtp_host(dispatcher, monkeypatch):` |
| `155` | Warning | PY_TYPING | Missing type hint for argument 'dispatcher' in async function 'test_send_email_raises_on_internal_ip_smtp_host' | `async def test_send_email_raises_on_internal_ip_smtp_host(dispatcher, monkeypatch):` |
| `155` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_send_email_raises_on_internal_ip_smtp_host' | `async def test_send_email_raises_on_internal_ip_smtp_host(dispatcher, monkeypatch):` |
| `177` | Warning | PY_TYPING | Missing return type hint for async function 'test_send_slack_reuses_shared_http_client' | `async def test_send_slack_reuses_shared_http_client(dispatcher):` |
| `177` | Warning | PY_TYPING | Missing type hint for argument 'dispatcher' in async function 'test_send_slack_reuses_shared_http_client' | `async def test_send_slack_reuses_shared_http_client(dispatcher):` |
| `188` | Warning | PY_TYPING | Missing return type hint for async function 'test_stop_worker_closes_http_client' | `async def test_stop_worker_closes_http_client():` |
| `200` | Warning | PY_TYPING | Missing return type hint for async function 'test_send_email_passes_smtp_credentials' | `async def test_send_email_passes_smtp_credentials(dispatcher, monkeypatch):` |
| `200` | Warning | PY_TYPING | Missing type hint for argument 'dispatcher' in async function 'test_send_email_passes_smtp_credentials' | `async def test_send_email_passes_smtp_credentials(dispatcher, monkeypatch):` |
| `200` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_send_email_passes_smtp_credentials' | `async def test_send_email_passes_smtp_credentials(dispatcher, monkeypatch):` |
| `215` | Warning | PY_TYPING | Missing return type hint for async function 'test_send_email_no_auth_when_credentials_unset' | `async def test_send_email_no_auth_when_credentials_unset(dispatcher, monkeypatch):` |
| `215` | Warning | PY_TYPING | Missing type hint for argument 'dispatcher' in async function 'test_send_email_no_auth_when_credentials_unset' | `async def test_send_email_no_auth_when_credentials_unset(dispatcher, monkeypatch):` |
| `215` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_send_email_no_auth_when_credentials_unset' | `async def test_send_email_no_auth_when_credentials_unset(dispatcher, monkeypatch):` |
| `235` | Warning | PY_TYPING | Missing return type hint for async function 'test_stop_worker_drains_remaining_queue_items' | `async def test_stop_worker_drains_remaining_queue_items():` |
| `261` | Warning | PY_TYPING | Missing return type hint for async function 'test_send_slack_timeout_logged_as_warning' | `async def test_send_slack_timeout_logged_as_warning(dispatcher):` |
| `261` | Warning | PY_TYPING | Missing type hint for argument 'dispatcher' in async function 'test_send_slack_timeout_logged_as_warning' | `async def test_send_slack_timeout_logged_as_warning(dispatcher):` |
| `275` | Warning | PY_TYPING | Missing return type hint for async function 'test_send_teams_http_status_error_logs_status_code' | `async def test_send_teams_http_status_error_logs_status_code(dispatcher):` |
| `275` | Warning | PY_TYPING | Missing type hint for argument 'dispatcher' in async function 'test_send_teams_http_status_error_logs_status_code' | `async def test_send_teams_http_status_error_logs_status_code(dispatcher):` |
| `279` | Warning | PY_TYPING | Missing return type hint for async function 'raise_503' | `async def raise_503(*_args, **_kwargs):` |
| `300` | Warning | PY_TYPING | Missing return type hint for async function 'test_post_with_retry_timeout_exhausts_attempts' | `async def test_post_with_retry_timeout_exhausts_attempts():` |
| `313` | Warning | PY_TYPING | Missing return type hint for async function 'test_post_with_retry_4xx_does_not_retry' | `async def test_post_with_retry_4xx_does_not_retry():` |
| `318` | Warning | PY_TYPING | Missing return type hint for async function 'raise_400' | `async def raise_400(*_args, **_kwargs):` |
| `335` | Warning | PY_TYPING | Missing return type hint for async function 'test_post_with_retry_5xx_retries_to_limit' | `async def test_post_with_retry_5xx_retries_to_limit():` |
| `340` | Warning | PY_TYPING | Missing return type hint for async function 'raise_502' | `async def raise_502(*_args, **_kwargs):` |
| `354` | Warning | PY_TYPING | Missing return type hint for async function 'test_post_with_retry_succeeds_on_second_attempt' | `async def test_post_with_retry_succeeds_on_second_attempt():` |

---

### Module: `tests/test_openvino_npu_export.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `22` | Warning | PY_TYPING | Missing return type hint for function '_install_mock_hub' | `def _install_mock_hub():` |
| `60` | Warning | PY_TYPING | Missing return type hint for function 'test_export_raises_when_revision_unset' | `def test_export_raises_when_revision_unset():` |
| `79` | Warning | PY_TYPING | Missing return type hint for function 'test_export_succeeds_when_revision_set' | `def test_export_succeeds_when_revision_set():` |
| `107` | Warning | PY_TYPING | Missing return type hint for function 'test_revision_forwarded_to_from_pretrained' | `def test_revision_forwarded_to_from_pretrained():` |
| `142` | Warning | PY_TYPING | Missing return type hint for function 'test_batch_size_out_of_range_raises' | `def test_batch_size_out_of_range_raises(batch_size):` |
| `142` | Warning | PY_TYPING | Missing type hint for argument 'batch_size' in function 'test_batch_size_out_of_range_raises' | `def test_batch_size_out_of_range_raises(batch_size):` |
| `149` | Warning | PY_TYPING | Missing return type hint for function 'test_sequence_length_out_of_range_raises' | `def test_sequence_length_out_of_range_raises(sequence_length):` |
| `149` | Warning | PY_TYPING | Missing type hint for argument 'sequence_length' in function 'test_sequence_length_out_of_range_raises' | `def test_sequence_length_out_of_range_raises(sequence_length):` |
| `155` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_model_id_raises' | `def test_empty_model_id_raises():` |
| `161` | Warning | PY_TYPING | Missing return type hint for function 'test_non_empty_output_dir_raises' | `def test_non_empty_output_dir_raises():` |
| `171` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_output_dir_passes_validation' | `def test_empty_output_dir_passes_validation():` |
| `186` | Warning | PY_TYPING | Missing return type hint for function 'test_model_save_failure_leaves_no_output_dir' | `def test_model_save_failure_leaves_no_output_dir():` |
| `200` | Warning | PY_TYPING | Missing return type hint for function 'test_tokenizer_oserror_continues_export' | `def test_tokenizer_oserror_continues_export():` |
| `215` | Warning | PY_TYPING | Missing return type hint for function 'test_tokenizer_unexpected_exception_cleans_tmp' | `def test_tokenizer_unexpected_exception_cleans_tmp():` |
| `228` | Warning | PY_TYPING | Missing return type hint for function 'test_successful_export_writes_expected_artifacts' | `def test_successful_export_writes_expected_artifacts():` |
| `249` | Warning | PY_TYPING | Missing return type hint for function 'test_manifest_is_valid_json' | `def test_manifest_is_valid_json():` |
| `261` | Warning | PY_TYPING | Missing return type hint for function 'test_manifest_dependency_versions_structure' | `def test_manifest_dependency_versions_structure():` |
| `276` | Warning | PY_TYPING | Missing return type hint for function 'test_manifest_model_revision_none_when_env_unset' | `def test_manifest_model_revision_none_when_env_unset():` |
| `283` | Warning | PY_TYPING | Missing return type hint for function 'test_manifest_contains_truncation_note' | `def test_manifest_contains_truncation_note():` |

---

### Module: `tests/test_orchestrators_temporal.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `164` | Warning | PY_TYPING | Missing return type hint for async function 'fake_scoped' | `async def fake_scoped(_ns: object):` |

---

### Module: `tests/test_outbox.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `26` | Warning | PY_TYPING | Missing return type hint for function 'mock_pg_pool' | `def mock_pg_pool():` |
| `46` | Warning | PY_TYPING | Missing return type hint for function 'mock_mongo_client' | `def mock_mongo_client():` |
| `61` | Warning | PY_TYPING | Missing return type hint for function 'mock_redis_client' | `def mock_redis_client():` |
| `69` | Warning | PY_TYPING | Missing return type hint for function 'orchestrator' | `def orchestrator(mock_pg_pool, mock_mongo_client, mock_redis_client):` |
| `69` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in function 'orchestrator' | `def orchestrator(mock_pg_pool, mock_mongo_client, mock_redis_client):` |
| `69` | Warning | PY_TYPING | Missing type hint for argument 'mock_mongo_client' in function 'orchestrator' | `def orchestrator(mock_pg_pool, mock_mongo_client, mock_redis_client):` |
| `69` | Warning | PY_TYPING | Missing type hint for argument 'mock_redis_client' in function 'orchestrator' | `def orchestrator(mock_pg_pool, mock_mongo_client, mock_redis_client):` |
| `82` | Warning | PY_TYPING | Missing return type hint for function 'store_payload' | `def store_payload():` |
| `103` | Warning | PY_TYPING | Missing return type hint for async function 'test_outbox_event_inserted_on_success' | `async def test_outbox_event_inserted_on_success(` |
| `103` | Warning | PY_TYPING | Missing type hint for argument 'orchestrator' in async function 'test_outbox_event_inserted_on_success' | `async def test_outbox_event_inserted_on_success(` |
| `103` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_outbox_event_inserted_on_success' | `async def test_outbox_event_inserted_on_success(` |
| `103` | Warning | PY_TYPING | Missing type hint for argument 'store_payload' in async function 'test_outbox_event_inserted_on_success' | `async def test_outbox_event_inserted_on_success(` |
| `103` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_outbox_event_inserted_on_success' | `async def test_outbox_event_inserted_on_success(` |
| `145` | Warning | PY_TYPING | Missing return type hint for async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `145` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `145` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `164` | Warning | PY_TYPING | Missing return type hint for async function 'test_outbox_payload_contains_memory_id' | `async def test_outbox_payload_contains_memory_id(` |
| `164` | Warning | PY_TYPING | Missing type hint for argument 'orchestrator' in async function 'test_outbox_payload_contains_memory_id' | `async def test_outbox_payload_contains_memory_id(` |
| `164` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_outbox_payload_contains_memory_id' | `async def test_outbox_payload_contains_memory_id(` |
| `164` | Warning | PY_TYPING | Missing type hint for argument 'store_payload' in async function 'test_outbox_payload_contains_memory_id' | `async def test_outbox_payload_contains_memory_id(` |
| `164` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_outbox_payload_contains_memory_id' | `async def test_outbox_payload_contains_memory_id(` |
| `200` | Warning | PY_TYPING | Missing return type hint for async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `200` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `200` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `218` | Warning | PY_TYPING | Missing return type hint for async function 'test_outbox_rolled_back_when_pg_fails' | `async def test_outbox_rolled_back_when_pg_fails(` |
| `218` | Warning | PY_TYPING | Missing type hint for argument 'orchestrator' in async function 'test_outbox_rolled_back_when_pg_fails' | `async def test_outbox_rolled_back_when_pg_fails(` |
| `218` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_pool' in async function 'test_outbox_rolled_back_when_pg_fails' | `async def test_outbox_rolled_back_when_pg_fails(` |
| `218` | Warning | PY_TYPING | Missing type hint for argument 'store_payload' in async function 'test_outbox_rolled_back_when_pg_fails' | `async def test_outbox_rolled_back_when_pg_fails(` |
| `218` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_outbox_rolled_back_when_pg_fails' | `async def test_outbox_rolled_back_when_pg_fails(` |
| `256` | Warning | PY_TYPING | Missing return type hint for async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `256` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `256` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function '_fake_scoped' | `async def _fake_scoped(pg_pool, namespace_id):` |
| `280` | Warning | PY_TYPING | Missing return type hint for async function 'test_poll_outbox_returns_unpublished_rows' | `async def test_poll_outbox_returns_unpublished_rows(self):` |
| `306` | Warning | PY_TYPING | Missing return type hint for async function 'test_poll_outbox_uses_batch_size' | `async def test_poll_outbox_uses_batch_size(self):` |

---

### Module: `tests/test_outbox_relay.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `13` | Warning | PY_TYPING | Missing return type hint for async function 'test_outbox_relay_marks_published' | `async def test_outbox_relay_marks_published(pg_pool, namespace_id, monkeypatch):` |
| `13` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function 'test_outbox_relay_marks_published' | `async def test_outbox_relay_marks_published(pg_pool, namespace_id, monkeypatch):` |
| `13` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_outbox_relay_marks_published' | `async def test_outbox_relay_marks_published(pg_pool, namespace_id, monkeypatch):` |
| `13` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_outbox_relay_marks_published' | `async def test_outbox_relay_marks_published(pg_pool, namespace_id, monkeypatch):` |
| `16` | Warning | PY_TYPING | Missing return type hint for async function 'fake_handler' | `async def fake_handler(conn, event):` |
| `16` | Warning | PY_TYPING | Missing type hint for argument 'conn' in async function 'fake_handler' | `async def fake_handler(conn, event):` |
| `16` | Warning | PY_TYPING | Missing type hint for argument 'event' in async function 'fake_handler' | `async def fake_handler(conn, event):` |
| `46` | Warning | PY_TYPING | Missing return type hint for async function 'test_outbox_relay_failed_handler_increments_attempt_count' | `async def test_outbox_relay_failed_handler_increments_attempt_count(` |
| `46` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function 'test_outbox_relay_failed_handler_increments_attempt_count' | `async def test_outbox_relay_failed_handler_increments_attempt_count(` |
| `46` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_outbox_relay_failed_handler_increments_attempt_count' | `async def test_outbox_relay_failed_handler_increments_attempt_count(` |
| `46` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_outbox_relay_failed_handler_increments_attempt_count' | `async def test_outbox_relay_failed_handler_increments_attempt_count(` |
| `49` | Warning | PY_TYPING | Missing return type hint for async function 'failing_handler' | `async def failing_handler(conn, event):` |
| `49` | Warning | PY_TYPING | Missing type hint for argument 'conn' in async function 'failing_handler' | `async def failing_handler(conn, event):` |
| `49` | Warning | PY_TYPING | Missing type hint for argument 'event' in async function 'failing_handler' | `async def failing_handler(conn, event):` |
| `79` | Warning | PY_TYPING | Missing return type hint for async function 'test_outbox_relay_exhausted_event_moves_to_dlq' | `async def test_outbox_relay_exhausted_event_moves_to_dlq(pg_pool, namespace_id, monkeypatch):` |
| `79` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function 'test_outbox_relay_exhausted_event_moves_to_dlq' | `async def test_outbox_relay_exhausted_event_moves_to_dlq(pg_pool, namespace_id, monkeypatch):` |
| `79` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_outbox_relay_exhausted_event_moves_to_dlq' | `async def test_outbox_relay_exhausted_event_moves_to_dlq(pg_pool, namespace_id, monkeypatch):` |
| `79` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_outbox_relay_exhausted_event_moves_to_dlq' | `async def test_outbox_relay_exhausted_event_moves_to_dlq(pg_pool, namespace_id, monkeypatch):` |
| `80` | Warning | PY_TYPING | Missing return type hint for async function 'failing_handler' | `async def failing_handler(conn, event):` |
| `80` | Warning | PY_TYPING | Missing type hint for argument 'conn' in async function 'failing_handler' | `async def failing_handler(conn, event):` |
| `80` | Warning | PY_TYPING | Missing type hint for argument 'event' in async function 'failing_handler' | `async def failing_handler(conn, event):` |

---

### Module: `tests/test_pii_batch1.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `13` | Warning | PY_TYPING | Missing return type hint for function 'test_merge_overlapping_keeps_longer_span_at_same_start' | `def test_merge_overlapping_keeps_longer_span_at_same_start():` |
| `24` | Warning | PY_TYPING | Missing return type hint for async function 'test_process_overlapping_spans_only_email_in_output' | `async def test_process_overlapping_spans_only_email_in_output():` |
| `48` | Warning | PY_TYPING | Missing return type hint for async function 'test_process_adjacent_non_overlapping_spans_both_replaced' | `async def test_process_adjacent_non_overlapping_spans_both_replaced():` |
| `64` | Warning | PY_TYPING | Missing return type hint for async function 'test_process_negative_start_clears_raw_values_and_raises' | `async def test_process_negative_start_clears_raw_values_and_raises():` |
| `79` | Warning | PY_TYPING | Missing return type hint for async function 'test_process_end_beyond_text_clears_raw_values_and_raises' | `async def test_process_end_beyond_text_clears_raw_values_and_raises():` |

---

### Module: `tests/test_pii_batch2.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `21` | Warning | PY_TYPING | Missing return type hint for function 'test_scan_sync_text_over_max_bytes_raises' | `def test_scan_sync_text_over_max_bytes_raises():` |
| `28` | Warning | PY_TYPING | Missing return type hint for function 'test_scan_sync_entity_cap_clears_values_and_raises' | `def test_scan_sync_entity_cap_clears_values_and_raises():` |
| `39` | Warning | PY_TYPING | Missing return type hint for function 'block_presidio' | `def block_presidio(name: str, *args, **kwargs):` |
| `52` | Warning | PY_TYPING | Missing return type hint for function 'test_master_key_fallback_differs_by_namespace_id' | `def test_master_key_fallback_differs_by_namespace_id(monkeypatch):` |
| `52` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_master_key_fallback_differs_by_namespace_id' | `def test_master_key_fallback_differs_by_namespace_id(monkeypatch):` |
| `63` | Warning | PY_TYPING | Missing return type hint for function 'test_same_namespace_master_key_fallback_is_deterministic' | `def test_same_namespace_master_key_fallback_is_deterministic(monkeypatch):` |
| `63` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_same_namespace_master_key_fallback_is_deterministic' | `def test_same_namespace_master_key_fallback_is_deterministic(monkeypatch):` |
| `73` | Warning | PY_TYPING | Missing return type hint for async function 'test_process_same_namespace_identical_pseudonyms' | `async def test_process_same_namespace_identical_pseudonyms(monkeypatch):` |
| `73` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_process_same_namespace_identical_pseudonyms' | `async def test_process_same_namespace_identical_pseudonyms(monkeypatch):` |

---

### Module: `tests/test_pii_batch3.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `16` | Warning | PY_TYPING | Missing return type hint for function 'reset_analyzer_cache' | `def reset_analyzer_cache():` |
| `24` | Warning | PY_TYPING | Missing return type hint for function 'fake_presidio' | `def fake_presidio():` |
| `32` | Warning | PY_TYPING | Missing return type hint for function 'test_get_analyzer_returns_same_cached_instance' | `def test_get_analyzer_returns_same_cached_instance(fake_presidio):` |
| `32` | Warning | PY_TYPING | Missing type hint for argument 'fake_presidio' in function 'test_get_analyzer_returns_same_cached_instance' | `def test_get_analyzer_returns_same_cached_instance(fake_presidio):` |
| `42` | Warning | PY_TYPING | Missing return type hint for function 'test_scan_sync_allowlist_alice_blocks_lowercase_in_text' | `def test_scan_sync_allowlist_alice_blocks_lowercase_in_text(fake_presidio):` |
| `42` | Warning | PY_TYPING | Missing type hint for argument 'fake_presidio' in function 'test_scan_sync_allowlist_alice_blocks_lowercase_in_text' | `def test_scan_sync_allowlist_alice_blocks_lowercase_in_text(fake_presidio):` |
| `58` | Warning | PY_TYPING | Missing return type hint for function 'test_scan_sync_allowlist_lowercase_blocks_capitalized_in_text' | `def test_scan_sync_allowlist_lowercase_blocks_capitalized_in_text(fake_presidio):` |
| `58` | Warning | PY_TYPING | Missing type hint for argument 'fake_presidio' in function 'test_scan_sync_allowlist_lowercase_blocks_capitalized_in_text' | `def test_scan_sync_allowlist_lowercase_blocks_capitalized_in_text(fake_presidio):` |
| `76` | Warning | PY_TYPING | Missing return type hint for function 'test_scan_sync_analyzer_engine_constructed_once' | `def test_scan_sync_analyzer_engine_constructed_once(fake_presidio):` |
| `76` | Warning | PY_TYPING | Missing type hint for argument 'fake_presidio' in function 'test_scan_sync_analyzer_engine_constructed_once' | `def test_scan_sync_analyzer_engine_constructed_once(fake_presidio):` |

---

### Module: `tests/test_pii_batch4.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `14` | Warning | PY_TYPING | Missing return type hint for function 'test_luhn_valid_accepts_known_card' | `def test_luhn_valid_accepts_known_card():` |
| `18` | Warning | PY_TYPING | Missing return type hint for function 'test_luhn_invalid_sequence_rejected' | `def test_luhn_invalid_sequence_rejected():` |
| `22` | Warning | PY_TYPING | Missing return type hint for function 'test_scan_sync_invalid_luhn_not_flagged_as_credit_card' | `def test_scan_sync_invalid_luhn_not_flagged_as_credit_card():` |
| `27` | Warning | PY_TYPING | Missing return type hint for function 'block_presidio' | `def block_presidio(name: str, *args, **kwargs):` |
| `37` | Warning | PY_TYPING | Missing return type hint for function 'test_scan_sync_valid_luhn_flagged_as_credit_card' | `def test_scan_sync_valid_luhn_flagged_as_credit_card():` |
| `43` | Warning | PY_TYPING | Missing return type hint for function 'block_presidio' | `def block_presidio(name: str, *args, **kwargs):` |
| `63` | Warning | PY_TYPING | Missing return type hint for async function 'test_process_three_entity_redaction_matches_naive_slicing' | `async def test_process_three_entity_redaction_matches_naive_slicing():` |
| `104` | Warning | PY_TYPING | Missing return type hint for async function 'test_process_many_entities_redacts_correctly' | `async def test_process_many_entities_redacts_correctly():` |

---

### Module: `tests/test_pii_pseudonym.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `27` | Warning | PY_TYPING | Missing return type hint for function 'test_pseudonym_suffix_is_base64url_22_chars' | `def test_pseudonym_suffix_is_base64url_22_chars():` |
| `42` | Warning | PY_TYPING | Missing return type hint for function 'test_pseudonym_deterministic_same_inputs' | `def test_pseudonym_deterministic_same_inputs():` |
| `49` | Warning | PY_TYPING | Missing return type hint for function 'test_pseudonym_entity_type_separates_collision' | `def test_pseudonym_entity_type_separates_collision():` |
| `57` | Warning | PY_TYPING | Missing return type hint for function 'test_pseudonym_per_namespace_key_changes_output' | `def test_pseudonym_per_namespace_key_changes_output():` |
| `63` | Warning | PY_TYPING | Missing return type hint for function 'test_namespace_key_too_short_raises_at_validation' | `def test_namespace_key_too_short_raises_at_validation():` |
| `74` | Warning | PY_TYPING | Missing return type hint for async function 'test_missing_master_and_no_namespace_key_raises' | `async def test_missing_master_and_no_namespace_key_raises(monkeypatch):` |
| `74` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_missing_master_and_no_namespace_key_raises' | `async def test_missing_master_and_no_namespace_key_raises(monkeypatch):` |
| `89` | Warning | PY_TYPING | Missing return type hint for async function 'test_process_pseudonym_uses_master_when_no_namespace_key' | `async def test_process_pseudonym_uses_master_when_no_namespace_key(monkeypatch):` |
| `89` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_process_pseudonym_uses_master_when_no_namespace_key' | `async def test_process_pseudonym_uses_master_when_no_namespace_key(monkeypatch):` |
| `109` | Warning | PY_TYPING | Missing return type hint for async function 'test_process_pseudonym_with_explicit_namespace_key' | `async def test_process_pseudonym_with_explicit_namespace_key():` |
| `121` | Warning | PY_TYPING | Missing return type hint for async function 'test_reversible_pseudonym_vault_token_matches_sanitized' | `async def test_reversible_pseudonym_vault_token_matches_sanitized(monkeypatch):` |
| `121` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_reversible_pseudonym_vault_token_matches_sanitized' | `async def test_reversible_pseudonym_vault_token_matches_sanitized(monkeypatch):` |

---

### Module: `tests/test_pii_repr.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `19` | Warning | PY_TYPING | Missing return type hint for function 'test_fresh_entity_repr_shows_present_not_raw' | `def test_fresh_entity_repr_shows_present_not_raw(self):` |
| `36` | Warning | PY_TYPING | Missing return type hint for function 'test_cleared_entity_repr_shows_redacted' | `def test_cleared_entity_repr_shows_redacted(self):` |
| `54` | Warning | PY_TYPING | Missing return type hint for function 'test_entity_with_token_repr_includes_token' | `def test_entity_with_token_repr_includes_token(self):` |
| `71` | Warning | PY_TYPING | Missing return type hint for function 'test_repr_after_clear_is_idempotent' | `def test_repr_after_clear_is_idempotent(self):` |
| `87` | Warning | PY_TYPING | Missing return type hint for function 'test_model_dump_of_cleared_entity_shows_redacted' | `def test_model_dump_of_cleared_entity_shows_redacted(self):` |

---

### Module: `tests/test_project_ext_security.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `08` | Warning | PY_TYPING | Missing return type hint for function 'test_parse_mpxj_argv_rejects_shell_metacharacters' | `def test_parse_mpxj_argv_rejects_shell_metacharacters():` |
| `12` | Warning | PY_TYPING | Missing return type hint for function 'test_parse_mpxj_argv_rejects_disallowed_binary' | `def test_parse_mpxj_argv_rejects_disallowed_binary(monkeypatch):` |
| `12` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_parse_mpxj_argv_rejects_disallowed_binary' | `def test_parse_mpxj_argv_rejects_disallowed_binary(monkeypatch):` |
| `17` | Warning | PY_TYPING | Missing return type hint for function 'test_parse_mpxj_argv_accepts_allowlisted_java' | `def test_parse_mpxj_argv_accepts_allowlisted_java(monkeypatch):` |
| `17` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_parse_mpxj_argv_accepts_allowlisted_java' | `def test_parse_mpxj_argv_accepts_allowlisted_java(monkeypatch):` |
| `26` | Warning | PY_TYPING | Missing return type hint for function 'test_parse_mpxj_argv_honors_custom_allowlist' | `def test_parse_mpxj_argv_honors_custom_allowlist(monkeypatch):` |
| `26` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_parse_mpxj_argv_honors_custom_allowlist' | `def test_parse_mpxj_argv_honors_custom_allowlist(monkeypatch):` |

---

### Module: `tests/test_providers.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `33` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_key' | `def test_empty_key(self):` |
| `37` | Warning | PY_TYPING | Missing return type hint for function 'test_short_key' | `def test_short_key(self):` |
| `42` | Warning | PY_TYPING | Missing return type hint for function 'test_normal_key_preserves_first3_last4' | `def test_normal_key_preserves_first3_last4(self):` |
| `48` | Warning | PY_TYPING | Missing return type hint for function 'test_exactly_8_chars' | `def test_exactly_8_chars(self):` |
| `53` | Warning | PY_TYPING | Missing return type hint for function 'test_key_value_not_in_output' | `def test_key_value_not_in_output(self):` |
| `71` | Warning | PY_TYPING | Missing return type hint for function 'test_repr_does_not_contain_raw_key' | `def test_repr_does_not_contain_raw_key(self):` |
| `86` | Warning | PY_TYPING | Missing return type hint for function 'test_repr_does_not_contain_raw_key' | `def test_repr_does_not_contain_raw_key(self):` |
| `95` | Warning | PY_TYPING | Missing return type hint for function 'test_repr_azure_with_endpoint' | `def test_repr_azure_with_endpoint(self, monkeypatch: pytest.MonkeyPatch):` |
| `99` | Warning | PY_TYPING | Missing return type hint for function '_mock_getaddrinfo' | `def _mock_getaddrinfo(*args, **kwargs):` |
| `118` | Warning | PY_TYPING | Missing return type hint for function 'test_repr_does_not_contain_raw_key' | `def test_repr_does_not_contain_raw_key(self):` |
| `130` | Warning | PY_TYPING | Missing return type hint for function 'test_repr_contains_model_and_url' | `def test_repr_contains_model_and_url(self, monkeypatch: pytest.MonkeyPatch):` |
| `133` | Warning | PY_TYPING | Missing return type hint for function '_mock_getaddrinfo' | `def _mock_getaddrinfo(*args, **kwargs):` |
| `157` | Warning | PY_TYPING | Missing return type hint for function 'test_delays_are_non_deterministic' | `def test_delays_are_non_deterministic(self):` |
| `169` | Warning | PY_TYPING | Missing return type hint for function 'test_delay_never_exceeds_cap' | `def test_delay_never_exceeds_cap(self):` |
| `178` | Warning | PY_TYPING | Missing return type hint for function 'test_delay_never_zero' | `def test_delay_never_zero(self):` |
| `186` | Warning | PY_TYPING | Missing return type hint for function 'test_delays_increase_with_attempt' | `def test_delays_increase_with_attempt(self):` |
| `215` | Warning | PY_TYPING | Missing return type hint for async function 'test_initial_state_is_closed' | `async def test_initial_state_is_closed(self):` |
| `221` | Warning | PY_TYPING | Missing return type hint for async function 'test_consecutive_failures_open_circuit' | `async def test_consecutive_failures_open_circuit(self):` |
| `232` | Warning | PY_TYPING | Missing return type hint for async function 'test_open_circuit_rejects_all_requests' | `async def test_open_circuit_rejects_all_requests(self):` |
| `242` | Warning | PY_TYPING | Missing return type hint for async function 'test_success_resets_failure_count' | `async def test_success_resets_failure_count(self):` |
| `252` | Warning | PY_TYPING | Missing return type hint for async function 'test_half_open_transitions_after_recovery_timeout' | `async def test_half_open_transitions_after_recovery_timeout(self):` |
| `265` | Warning | PY_TYPING | Missing return type hint for async function 'test_half_open_success_closes_circuit' | `async def test_half_open_success_closes_circuit(self):` |
| `278` | Warning | PY_TYPING | Missing return type hint for async function 'test_half_open_failure_reopens_circuit' | `async def test_half_open_failure_reopens_circuit(self):` |
| `293` | Warning | PY_TYPING | Missing return type hint for async function 'test_half_open_limits_probe_requests' | `async def test_half_open_limits_probe_requests(self):` |
| `308` | Warning | PY_TYPING | Missing return type hint for async function 'test_repr_contains_state_and_failure_count' | `async def test_repr_contains_state_and_failure_count(self):` |
| `327` | Warning | PY_TYPING | Missing return type hint for async function 'complete' | `async def complete(self, messages, response_model):` |
| `327` | Warning | PY_TYPING | Missing type hint for argument 'messages' in async function 'complete' | `async def complete(self, messages, response_model):` |
| `327` | Warning | PY_TYPING | Missing type hint for argument 'response_model' in async function 'complete' | `async def complete(self, messages, response_model):` |
| `338` | Warning | PY_TYPING | Missing return type hint for async function 'test_successful_call_passthrough' | `async def test_successful_call_passthrough(self):` |
| `341` | Warning | PY_TYPING | Missing return type hint for async function 'ok_op' | `async def ok_op():` |
| `348` | Warning | PY_TYPING | Missing return type hint for async function 'test_retryable_error_triggers_retry_then_succeeds' | `async def test_retryable_error_triggers_retry_then_succeeds(self):` |
| `352` | Warning | PY_TYPING | Missing return type hint for async function 'flaky_operation' | `async def flaky_operation():` |
| `374` | Warning | PY_TYPING | Missing return type hint for async function 'test_retry_exhaustion_raises' | `async def test_retry_exhaustion_raises(self):` |
| `377` | Warning | PY_TYPING | Missing return type hint for async function 'always_fails' | `async def always_fails():` |
| `394` | Warning | PY_TYPING | Missing return type hint for async function 'test_non_retryable_error_not_retried' | `async def test_non_retryable_error_not_retried(self):` |
| `398` | Warning | PY_TYPING | Missing return type hint for async function 'auth_error' | `async def auth_error():` |
| `417` | Warning | PY_TYPING | Missing return type hint for async function 'test_circuit_breaker_opens_and_blocks' | `async def test_circuit_breaker_opens_and_blocks(self):` |
| `424` | Warning | PY_TYPING | Missing return type hint for async function 'failing_op' | `async def failing_op():` |
| `458` | Warning | PY_TYPING | Missing return type hint for async function 'test_success_closes_circuit_and_resets' | `async def test_success_closes_circuit_and_resets(self):` |
| `470` | Warning | PY_TYPING | Missing return type hint for async function 'ok_op' | `async def ok_op():` |
| `491` | Warning | PY_TYPING | Missing return type hint for async function 'test_429_raises_llm_rate_limit_error' | `async def test_429_raises_llm_rate_limit_error(self, monkeypatch):` |
| `491` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_429_raises_llm_rate_limit_error' | `async def test_429_raises_llm_rate_limit_error(self, monkeypatch):` |
| `492` | Warning | PY_TYPING | Missing return type hint for async function '_mock_post' | `async def _mock_post(*args, **kwargs):` |
| `498` | Warning | PY_TYPING | Missing return type hint for function 'json' | `def json(self):` |
| `502` | Warning | PY_TYPING | Missing return type hint for function 'text' | `def text(self):` |
| `520` | Warning | PY_TYPING | Missing return type hint for async function 'test_500_raises_llm_upstream_error' | `async def test_500_raises_llm_upstream_error(self, monkeypatch):` |
| `520` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_500_raises_llm_upstream_error' | `async def test_500_raises_llm_upstream_error(self, monkeypatch):` |
| `521` | Warning | PY_TYPING | Missing return type hint for async function '_mock_post' | `async def _mock_post(*args, **kwargs):` |
| `526` | Warning | PY_TYPING | Missing return type hint for function 'json' | `def json(self):` |
| `530` | Warning | PY_TYPING | Missing return type hint for function 'text' | `def text(self):` |
| `547` | Warning | PY_TYPING | Missing return type hint for async function 'test_401_raises_llm_authentication_error' | `async def test_401_raises_llm_authentication_error(self, monkeypatch):` |
| `547` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_401_raises_llm_authentication_error' | `async def test_401_raises_llm_authentication_error(self, monkeypatch):` |
| `548` | Warning | PY_TYPING | Missing return type hint for async function '_mock_post' | `async def _mock_post(*args, **kwargs):` |
| `553` | Warning | PY_TYPING | Missing return type hint for function 'json' | `def json(self):` |
| `557` | Warning | PY_TYPING | Missing return type hint for function 'text' | `def text(self):` |

---

### Module: `tests/test_query_catalog.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `61` | Warning | PY_TYPING | Missing return type hint for function '_make_scoped_session_patcher' | `def _make_scoped_session_patcher(conn: _FakeCatalogConnection):` |
| `65` | Warning | PY_TYPING | Missing return type hint for async function '_fake_scoped' | `async def _fake_scoped(*_args: Any, **_kwargs: Any):` |
| `156` | Warning | PY_TYPING | Missing return type hint for async function '_counted_session' | `async def _counted_session(pool: Any, ns: UUID):` |
| `198` | Warning | PY_TYPING | Missing return type hint for async function '_session' | `async def _session(pool: Any, ns: UUID):` |
| `208` | Warning | PY_TYPING | Missing return type hint for function '_capturing_compile' | `def _capturing_compile(self: CatalogManager, template_str: str, params: dict[str, Any]):` |
| `252` | Warning | PY_TYPING | Missing return type hint for async function '_session' | `async def _session(pool: Any, ns: UUID):` |
| `284` | Warning | PY_TYPING | Missing return type hint for async function '_session' | `async def _session(pool: Any, ns: UUID):` |
| `398` | Warning | PY_TYPING | Missing return type hint for async function '_session' | `async def _session(pool: Any, ns: UUID):` |

---

### Module: `tests/test_quotas.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `31` | Warning | PY_TYPING | Missing return type hint for function '_passthrough_decorator' | `def _passthrough_decorator(fn):` |
| `31` | Warning | PY_TYPING | Missing type hint for argument 'fn' in function '_passthrough_decorator' | `def _passthrough_decorator(fn):` |
| `38` | Warning | PY_TYPING | Missing return type hint for function 'list_tools' | `def list_tools(self):` |
| `41` | Warning | PY_TYPING | Missing return type hint for function 'call_tool' | `def call_tool(self):` |
| `45` | Warning | PY_TYPING | Missing return type hint for async function '_fake_stdio' | `async def _fake_stdio():` |
| `817` | Warning | PY_TYPING | Missing return type hint for async function '_boom' | `async def _boom(*_a, **_k):` |
| `873` | Warning | PY_TYPING | Missing return type hint for async function '_boom' | `async def _boom(*_a, **_k):` |
| `1178` | Warning | PY_TYPING | Missing return type hint for async function '_scan_iter' | `async def _scan_iter(*_a: object, **_k: object):` |
| `1196` | Warning | PY_TYPING | Missing return type hint for async function '_fake_scoped' | `async def _fake_scoped(pool: object, namespace_id: object):` |
| `1221` | Warning | PY_TYPING | Missing return type hint for async function '_scan_iter' | `async def _scan_iter(*_a: object, **_k: object):` |
| `1239` | Warning | PY_TYPING | Missing return type hint for async function '_fake_scoped' | `async def _fake_scoped(pool: object, namespace_id: object):` |

---

### Module: `tests/test_re_embedder.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `42` | Warning | PY_TYPING | Missing type hint for argument 'items' in function '__init__' | `def __init__(self, items):` |
| `46` | Warning | PY_TYPING | Missing return type hint for function '__aiter__' | `def __aiter__(self):` |
| `49` | Warning | PY_TYPING | Missing return type hint for async function '__anext__' | `async def __anext__(self):` |
| `63` | Warning | PY_TYPING | Missing return type hint for async function 'test_re_embedder_no_active_migrations' | `async def test_re_embedder_no_active_migrations():` |
| `79` | Warning | PY_TYPING | Missing return type hint for async function 'test_re_embedder_processes_memories_batch_successfully' | `async def test_re_embedder_processes_memories_batch_successfully(mock_embed):` |
| `79` | Warning | PY_TYPING | Missing type hint for argument 'mock_embed' in async function 'test_re_embedder_processes_memories_batch_successfully' | `async def test_re_embedder_processes_memories_batch_successfully(mock_embed):` |
| `142` | Warning | PY_TYPING | Missing return type hint for async function 'test_re_embedder_skips_invalid_payload_refs' | `async def test_re_embedder_skips_invalid_payload_refs(mock_embed):` |
| `142` | Warning | PY_TYPING | Missing type hint for argument 'mock_embed' in async function 'test_re_embedder_skips_invalid_payload_refs' | `async def test_re_embedder_skips_invalid_payload_refs(mock_embed):` |

---

### Module: `tests/test_reembedding_worker.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `99` | Warning | PY_TYPING | Missing return type hint for function 'test_current_model_uuid_is_deterministic' | `def test_current_model_uuid_is_deterministic():` |
| `111` | Warning | PY_TYPING | Missing return type hint for function 'test_fallback_text_uses_name_and_filepath' | `def test_fallback_text_uses_name_and_filepath():` |
| `119` | Warning | PY_TYPING | Missing return type hint for function 'test_fallback_text_clips_to_max_chars' | `def test_fallback_text_clips_to_max_chars():` |
| `126` | Warning | PY_TYPING | Missing return type hint for function 'test_fallback_text_empty_when_no_fields' | `def test_fallback_text_empty_when_no_fields():` |
| `137` | Warning | PY_TYPING | Missing return type hint for function 'test_fetch_memories_batch_initial_cursor' | `def test_fetch_memories_batch_initial_cursor():` |
| `151` | Warning | PY_TYPING | Missing return type hint for function 'test_fetch_memories_batch_with_cursor' | `def test_fetch_memories_batch_with_cursor():` |
| `169` | Warning | PY_TYPING | Missing return type hint for function 'test_fetch_kg_nodes_batch_initial' | `def test_fetch_kg_nodes_batch_initial():` |
| `180` | Warning | PY_TYPING | Missing return type hint for function 'test_fetch_kg_nodes_batch_with_cursor' | `def test_fetch_kg_nodes_batch_with_cursor():` |
| `196` | Warning | PY_TYPING | Missing return type hint for function 'test_update_memories_batch_calls_executemany' | `def test_update_memories_batch_calls_executemany():` |
| `223` | Warning | PY_TYPING | Missing return type hint for function 'test_update_kg_nodes_batch_calls_executemany' | `def test_update_kg_nodes_batch_calls_executemany():` |
| `244` | Warning | PY_TYPING | Missing return type hint for function 'test_resolve_texts_returns_episodic_raw_data' | `def test_resolve_texts_returns_episodic_raw_data():` |
| `256` | Warning | PY_TYPING | Missing return type hint for async function '_fake_find' | `async def _fake_find(*_, **__):` |
| `275` | Warning | PY_TYPING | Missing return type hint for function 'test_worker_run_once_no_stale_rows' | `def test_worker_run_once_no_stale_rows():` |
| `299` | Warning | PY_TYPING | Missing return type hint for function 'test_worker_processes_one_memory_batch' | `def test_worker_processes_one_memory_batch():` |
| `332` | Warning | PY_TYPING | Missing return type hint for function 'test_worker_respects_max_rows_per_run' | `def test_worker_respects_max_rows_per_run():` |
| `363` | Warning | PY_TYPING | Missing return type hint for function 'test_worker_marks_run_failed_on_embed_error' | `def test_worker_marks_run_failed_on_embed_error():` |
| `393` | Warning | PY_TYPING | Missing return type hint for function 'test_worker_processes_kg_nodes_when_enabled' | `def test_worker_processes_kg_nodes_when_enabled():` |

---

### Module: `tests/test_rls_catalog.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `08` | Warning | PY_TYPING | Missing type hint for argument 'conn' in async function '_require_current_tenant_columns' | `async def _require_current_tenant_columns(conn) -> None:` |
| `52` | Warning | PY_TYPING | Missing return type hint for async function 'test_rls_catalog_consistency' | `async def test_rls_catalog_consistency(pg_app_conn):` |
| `52` | Warning | PY_TYPING | Missing type hint for argument 'pg_app_conn' in async function 'test_rls_catalog_consistency' | `async def test_rls_catalog_consistency(pg_app_conn):` |

---

### Module: `tests/test_rls_isolation_integration.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `15` | Warning | PY_TYPING | Missing type hint for argument 'pg_pool' in async function 'test_get_nce_namespace_fails_without_context' | `async def test_get_nce_namespace_fails_without_context(pg_pool) -> None:` |
| `25` | Warning | PY_TYPING | Missing type hint for argument 'pg_app_conn' in async function 'test_resource_quotas_cross_namespace_isolation' | `async def test_resource_quotas_cross_namespace_isolation(` |
| `25` | Warning | PY_TYPING | Missing type hint for argument 'make_namespace' in async function 'test_resource_quotas_cross_namespace_isolation' | `async def test_resource_quotas_cross_namespace_isolation(` |
| `68` | Warning | PY_TYPING | Missing type hint for argument 'pg_app_conn' in async function 'test_rls_catalog_force_enabled' | `async def test_rls_catalog_force_enabled(pg_app_conn) -> None:` |

---

### Module: `tests/test_safe_async_client.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `17` | Warning | PY_TYPING | Missing return type hint for async function 'test_blocks_private_ipv4' | `async def test_blocks_private_ipv4(self, monkeypatch: pytest.MonkeyPatch):` |
| `20` | Warning | PY_TYPING | Missing return type hint for function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host, port, *args, **kwargs):` |
| `20` | Warning | PY_TYPING | Missing type hint for argument 'host' in function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host, port, *args, **kwargs):` |
| `20` | Warning | PY_TYPING | Missing type hint for argument 'port' in function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host, port, *args, **kwargs):` |
| `30` | Warning | PY_TYPING | Missing return type hint for async function 'test_blocks_loopback' | `async def test_blocks_loopback(self, monkeypatch: pytest.MonkeyPatch):` |
| `33` | Warning | PY_TYPING | Missing return type hint for function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host, port, *args, **kwargs):` |
| `33` | Warning | PY_TYPING | Missing type hint for argument 'host' in function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host, port, *args, **kwargs):` |
| `33` | Warning | PY_TYPING | Missing type hint for argument 'port' in function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host, port, *args, **kwargs):` |
| `43` | Warning | PY_TYPING | Missing return type hint for async function 'test_allows_public_ip' | `async def test_allows_public_ip(self, monkeypatch: pytest.MonkeyPatch):` |
| `46` | Warning | PY_TYPING | Missing return type hint for function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host, port, *args, **kwargs):` |
| `46` | Warning | PY_TYPING | Missing type hint for argument 'host' in function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host, port, *args, **kwargs):` |
| `46` | Warning | PY_TYPING | Missing type hint for argument 'port' in function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host, port, *args, **kwargs):` |
| `59` | Warning | PY_TYPING | Missing return type hint for async function 'test_allows_unresolvable_host' | `async def test_allows_unresolvable_host(self):` |
| `67` | Warning | PY_TYPING | Missing return type hint for async function 'test_blocks_ipv6_loopback' | `async def test_blocks_ipv6_loopback(self, monkeypatch: pytest.MonkeyPatch):` |
| `70` | Warning | PY_TYPING | Missing return type hint for function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host, port, *args, **kwargs):` |
| `70` | Warning | PY_TYPING | Missing type hint for argument 'host' in function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host, port, *args, **kwargs):` |
| `70` | Warning | PY_TYPING | Missing type hint for argument 'port' in function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host, port, *args, **kwargs):` |
| `111` | Warning | PY_TYPING | Missing return type hint for function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host: str, port: Any, *args: Any, **kwargs: Any):` |
| `145` | Warning | PY_TYPING | Missing return type hint for function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host: str, port: Any, *args: Any, **kwargs: Any):` |
| `156` | Warning | PY_TYPING | Missing return type hint for function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host: str, port: Any, *args: Any, **kwargs: Any):` |
| `167` | Warning | PY_TYPING | Missing return type hint for function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host: str, port: Any, *args: Any, **kwargs: Any):` |
| `181` | Warning | PY_TYPING | Missing return type hint for function '_slow_getaddrinfo' | `def _slow_getaddrinfo(host: str, port: Any, *args: Any, **kwargs: Any):` |
| `200` | Warning | PY_TYPING | Missing return type hint for function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host: str, port: Any, *args: Any, **kwargs: Any):` |
| `227` | Warning | PY_TYPING | Missing return type hint for function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host: str, port: Any, *args: Any, **kwargs: Any):` |
| `278` | Warning | PY_TYPING | Missing return type hint for function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host: str, port: Any, *args: Any, **kwargs: Any):` |
| `302` | Warning | PY_TYPING | Missing return type hint for function '_mock_getaddrinfo' | `def _mock_getaddrinfo(host: str, port: Any, *args: Any, **kwargs: Any):` |

---

### Module: `tests/test_saga_rollback.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `26` | Warning | PY_TYPING | Missing return type hint for function '_make_payload' | `def _make_payload(**overrides):` |
| `49` | Warning | PY_TYPING | Missing return type hint for function '_make_mongo_mock' | `def _make_mongo_mock():` |
| `63` | Warning | PY_TYPING | Missing type hint for argument 'fetchrow_result' in function '__init__' | `def __init__(self, fetchrow_result=None, fetchval_result=None, fetch_result=None):` |
| `63` | Warning | PY_TYPING | Missing type hint for argument 'fetchval_result' in function '__init__' | `def __init__(self, fetchrow_result=None, fetchval_result=None, fetch_result=None):` |
| `63` | Warning | PY_TYPING | Missing type hint for argument 'fetch_result' in function '__init__' | `def __init__(self, fetchrow_result=None, fetchval_result=None, fetch_result=None):` |
| `70` | Warning | PY_TYPING | Missing return type hint for async function 'fetch' | `async def fetch(self, query: str = "", *args):` |
| `77` | Warning | PY_TYPING | Missing return type hint for async function '__aenter__' | `async def __aenter__(self):` |
| `80` | Warning | PY_TYPING | Missing return type hint for async function '__aexit__' | `async def __aexit__(self, *a):` |
| `83` | Warning | PY_TYPING | Missing return type hint for function 'transaction' | `def transaction(self):` |
| `87` | Warning | PY_TYPING | Missing return type hint for function '_make_pg_mock' | `def _make_pg_mock():` |
| `99` | Warning | PY_TYPING | Missing return type hint for function '_pii_mock' | `def _pii_mock(sanitized="sanitized", redacted=False, entities_found=0, vault_entries=None):` |
| `99` | Warning | PY_TYPING | Missing type hint for argument 'sanitized' in function '_pii_mock' | `def _pii_mock(sanitized="sanitized", redacted=False, entities_found=0, vault_entries=None):` |
| `99` | Warning | PY_TYPING | Missing type hint for argument 'redacted' in function '_pii_mock' | `def _pii_mock(sanitized="sanitized", redacted=False, entities_found=0, vault_entries=None):` |
| `99` | Warning | PY_TYPING | Missing type hint for argument 'entities_found' in function '_pii_mock' | `def _pii_mock(sanitized="sanitized", redacted=False, entities_found=0, vault_entries=None):` |
| `99` | Warning | PY_TYPING | Missing type hint for argument 'vault_entries' in function '_pii_mock' | `def _pii_mock(sanitized="sanitized", redacted=False, entities_found=0, vault_entries=None):` |
| `124` | Warning | PY_TYPING | Missing return type hint for function 'engine' | `def engine():` |
| `136` | Warning | PY_TYPING | Missing return type hint for async function '_scoped' | `async def _scoped(_ns):` |
| `136` | Warning | PY_TYPING | Missing type hint for argument '_ns' in async function '_scoped' | `async def _scoped(_ns):` |
| `150` | Warning | PY_TYPING | Missing return type hint for async function 'test_rollback_mongo_when_pg_transaction_fails' | `async def test_rollback_mongo_when_pg_transaction_fails(engine):` |
| `150` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'test_rollback_mongo_when_pg_transaction_fails' | `async def test_rollback_mongo_when_pg_transaction_fails(engine):` |
| `168` | Warning | PY_TYPING | Missing return type hint for async function 'test_rollback_all_stores_when_post_pg_failure' | `async def test_rollback_all_stores_when_post_pg_failure(engine):` |
| `168` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'test_rollback_all_stores_when_post_pg_failure' | `async def test_rollback_all_stores_when_post_pg_failure(engine):` |
| `204` | Warning | PY_TYPING | Missing return type hint for async function 'test_no_rollback_when_failure_before_mongo' | `async def test_no_rollback_when_failure_before_mongo(engine):` |
| `204` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'test_no_rollback_when_failure_before_mongo' | `async def test_no_rollback_when_failure_before_mongo(engine):` |
| `221` | Warning | PY_TYPING | Missing return type hint for async function 'test_rollback_does_not_mask_original_exception' | `async def test_rollback_does_not_mask_original_exception(engine):` |
| `221` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'test_rollback_does_not_mask_original_exception' | `async def test_rollback_does_not_mask_original_exception(engine):` |
| `239` | Warning | PY_TYPING | Missing return type hint for async function 'test_rollback_mongo_when_embedding_fails' | `async def test_rollback_mongo_when_embedding_fails(engine):` |
| `239` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'test_rollback_mongo_when_embedding_fails' | `async def test_rollback_mongo_when_embedding_fails(engine):` |

---

### Module: `tests/test_salience_decay_resilience.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `38` | Warning | PY_TYPING | Missing return type hint for function 'test_zero_delta_returns_unmodified_score' | `def test_zero_delta_returns_unmodified_score(self):` |
| `43` | Warning | PY_TYPING | Missing return type hint for function 'test_negative_delta_clock_skew_returns_unmodified' | `def test_negative_delta_clock_skew_returns_unmodified(self):` |
| `51` | Warning | PY_TYPING | Missing return type hint for function 'test_negative_delta_large_skew_returns_unmodified' | `def test_negative_delta_large_skew_returns_unmodified(self):` |
| `57` | Warning | PY_TYPING | Missing return type hint for function 'test_zero_delta_naive_datetime_handled' | `def test_zero_delta_naive_datetime_handled(self):` |
| `68` | Warning | PY_TYPING | Missing return type hint for function 'test_negative_delta_does_not_boost_score' | `def test_negative_delta_does_not_boost_score(self):` |
| `81` | Warning | PY_TYPING | Missing return type hint for function 'test_half_life_exactly_halves_score' | `def test_half_life_exactly_halves_score(self):` |
| `88` | Warning | PY_TYPING | Missing return type hint for function 'test_fresh_memory_barely_decays' | `def test_fresh_memory_barely_decays(self):` |
| `94` | Warning | PY_TYPING | Missing return type hint for function 'test_very_old_memory_decays_close_to_zero' | `def test_very_old_memory_decays_close_to_zero(self):` |
| `100` | Warning | PY_TYPING | Missing return type hint for function 'test_zero_half_life_returns_unmodified' | `def test_zero_half_life_returns_unmodified(self):` |
| `106` | Warning | PY_TYPING | Missing return type hint for function 'test_negative_half_life_returns_unmodified' | `def test_negative_half_life_returns_unmodified(self):` |
| `119` | Warning | PY_TYPING | Missing return type hint for function 'test_epoch_timestamp_does_not_raise' | `def test_epoch_timestamp_does_not_raise(self):` |
| `125` | Warning | PY_TYPING | Missing return type hint for function 'test_extremely_large_delta_clamps_to_near_zero' | `def test_extremely_large_delta_clamps_to_near_zero(self):` |
| `132` | Warning | PY_TYPING | Missing return type hint for function 'test_tiny_half_life_does_not_raise' | `def test_tiny_half_life_does_not_raise(self):` |
| `138` | Warning | PY_TYPING | Missing return type hint for function 'test_result_always_non_negative' | `def test_result_always_non_negative(self):` |

---

### Module: `tests/test_sanitize.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `10` | Warning | PY_TYPING | Missing return type hint for function 'test_fullwidth_angle_brackets_tags_stripped' | `def test_fullwidth_angle_brackets_tags_stripped():` |
| `18` | Warning | PY_TYPING | Missing return type hint for function 'test_html_entities_tags_stripped_content_preserved' | `def test_html_entities_tags_stripped_content_preserved():` |
| `26` | Warning | PY_TYPING | Missing return type hint for function 'test_mathematical_monospace_nfkc_to_ascii_script' | `def test_mathematical_monospace_nfkc_to_ascii_script():` |
| `34` | Warning | PY_TYPING | Missing return type hint for function 'test_zero_width_char_removed_tag_stripped' | `def test_zero_width_char_removed_tag_stripped():` |
| `43` | Warning | PY_TYPING | Missing return type hint for function 'test_double_html_entities_brackets_neutralized' | `def test_double_html_entities_brackets_neutralized():` |
| `51` | Warning | PY_TYPING | Missing return type hint for function 'test_safe_plain_text_unchanged' | `def test_safe_plain_text_unchanged():` |
| `56` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_string_returns_empty' | `def test_empty_string_returns_empty():` |
| `60` | Warning | PY_TYPING | Missing return type hint for function 'test_control_chars_null_bell_backspace_removed' | `def test_control_chars_null_bell_backspace_removed():` |
| `69` | Warning | PY_TYPING | Missing return type hint for function 'test_newline_carriage_return_tab_preserved' | `def test_newline_carriage_return_tab_preserved():` |
| `74` | Warning | PY_TYPING | Missing return type hint for function 'test_payload_truncated_at_max_length' | `def test_payload_truncated_at_max_length():` |
| `81` | Warning | PY_TYPING | Missing return type hint for function 'test_payload_under_max_length_not_truncated' | `def test_payload_under_max_length_not_truncated():` |
| `92` | Warning | PY_TYPING | Missing type hint for argument 'caplog' in function '_injection_warnings' | `def _injection_warnings(caplog) -> list[logging.LogRecord]:` |
| `102` | Warning | PY_TYPING | Missing return type hint for function 'test_template_braces_doubled_system_prompt_override' | `def test_template_braces_doubled_system_prompt_override():` |
| `108` | Warning | PY_TYPING | Missing return type hint for function 'test_ignore_previous_instructions_logs_warning' | `def test_ignore_previous_instructions_logs_warning(caplog):` |
| `108` | Warning | PY_TYPING | Missing type hint for argument 'caplog' in function 'test_ignore_previous_instructions_logs_warning' | `def test_ignore_previous_instructions_logs_warning(caplog):` |
| `117` | Warning | PY_TYPING | Missing return type hint for function 'test_valid_template_warning_and_doubled_braces' | `def test_valid_template_warning_and_doubled_braces(caplog):` |
| `117` | Warning | PY_TYPING | Missing type hint for argument 'caplog' in function 'test_valid_template_warning_and_doubled_braces' | `def test_valid_template_warning_and_doubled_braces(caplog):` |
| `127` | Warning | PY_TYPING | Missing return type hint for function 'test_normal_text_no_warning_braces_unchanged' | `def test_normal_text_no_warning_braces_unchanged(caplog):` |
| `127` | Warning | PY_TYPING | Missing type hint for argument 'caplog' in function 'test_normal_text_no_warning_braces_unchanged' | `def test_normal_text_no_warning_braces_unchanged(caplog):` |
| `137` | Warning | PY_TYPING | Missing return type hint for function 'test_warning_message_omits_original_content' | `def test_warning_message_omits_original_content(caplog):` |
| `137` | Warning | PY_TYPING | Missing type hint for argument 'caplog' in function 'test_warning_message_omits_original_content' | `def test_warning_message_omits_original_content(caplog):` |

---

### Module: `tests/test_schema_bootstrap.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `10` | Warning | PY_TYPING | Missing return type hint for async function 'test_schema_applies_cleanly_on_fresh_database' | `async def test_schema_applies_cleanly_on_fresh_database(pg_admin_conn):` |
| `10` | Warning | PY_TYPING | Missing type hint for argument 'pg_admin_conn' in async function 'test_schema_applies_cleanly_on_fresh_database' | `async def test_schema_applies_cleanly_on_fresh_database(pg_admin_conn):` |

---

### Module: `tests/test_semantic_search.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `24` | Warning | PY_TYPING | Missing return type hint for function '_fake_scoped' | `def _fake_scoped(mock_conn):` |
| `24` | Warning | PY_TYPING | Missing type hint for argument 'mock_conn' in function '_fake_scoped' | `def _fake_scoped(mock_conn):` |
| `26` | Warning | PY_TYPING | Missing return type hint for async function '_scoped' | `async def _scoped(_pool, _namespace_id):` |
| `26` | Warning | PY_TYPING | Missing type hint for argument '_pool' in async function '_scoped' | `async def _scoped(_pool, _namespace_id):` |
| `26` | Warning | PY_TYPING | Missing type hint for argument '_namespace_id' in async function '_scoped' | `async def _scoped(_pool, _namespace_id):` |
| `32` | Warning | PY_TYPING | Missing return type hint for function '_pg_row' | `def _pg_row(*, payload_ref: str, memory_id, score: float):` |
| `40` | Warning | PY_TYPING | Missing return type hint for function '_base_pg_conn' | `def _base_pg_conn(rows=None):` |
| `40` | Warning | PY_TYPING | Missing type hint for argument 'rows' in function '_base_pg_conn' | `def _base_pg_conn(rows=None):` |
| `48` | Warning | PY_TYPING | Missing return type hint for function '_mongo_client' | `def _mongo_client(*, episode_docs: dict[str, dict] \| None = None):` |
| `53` | Warning | PY_TYPING | Missing return type hint for async function '_find' | `async def _find(query, projection=None):` |
| `53` | Warning | PY_TYPING | Missing type hint for argument 'query' in async function '_find' | `async def _find(query, projection=None):` |
| `53` | Warning | PY_TYPING | Missing type hint for argument 'projection' in async function '_find' | `async def _find(query, projection=None):` |
| `71` | Warning | PY_TYPING | Missing return type hint for async function '_run_search' | `async def _run_search(` |
| `83` | Warning | PY_TYPING | Missing return type hint for function '_discard_background_task' | `def _discard_background_task(coro):` |
| `83` | Warning | PY_TYPING | Missing type hint for argument 'coro' in function '_discard_background_task' | `def _discard_background_task(coro):` |
| `117` | Warning | PY_TYPING | Missing return type hint for async function 'slow_embed' | `async def slow_embed(_query: str):` |
| `126` | Warning | PY_TYPING | Missing return type hint for async function 'bad_embed' | `async def bad_embed(_query: str):` |
| `139` | Warning | PY_TYPING | Missing return type hint for async function 'embed' | `async def embed(_query: str):` |
| `161` | Warning | PY_TYPING | Missing return type hint for async function 'embed' | `async def embed(_query: str):` |
| `195` | Warning | PY_TYPING | Missing return type hint for async function 'embed' | `async def embed(_query: str):` |
| `220` | Warning | PY_TYPING | Missing return type hint for async function 'embed' | `async def embed(_query: str):` |
| `250` | Warning | PY_TYPING | Missing return type hint for async function 'embed' | `async def embed(_query: str):` |
| `271` | Warning | PY_TYPING | Missing return type hint for async function 'embed' | `async def embed(_query: str):` |
| `298` | Warning | PY_TYPING | Missing return type hint for async function 'embed' | `async def embed(_query: str):` |
| `325` | Warning | PY_TYPING | Missing return type hint for async function 'embed' | `async def embed(_query: str):` |
| `342` | Warning | PY_TYPING | Missing return type hint for async function 'embed' | `async def embed(_query: str):` |
| `367` | Warning | PY_TYPING | Missing return type hint for async function 'embed' | `async def embed(_query: str):` |
| `370` | Warning | PY_TYPING | Missing return type hint for async function 'slow_reinforce' | `async def slow_reinforce(*_args, **_kwargs):` |
| `396` | Warning | PY_TYPING | Missing return type hint for async function 'embed' | `async def embed(_query: str):` |
| `399` | Warning | PY_TYPING | Missing return type hint for async function 'failing_reinforce' | `async def failing_reinforce(*_args, **_kwargs):` |
| `429` | Warning | PY_TYPING | Missing return type hint for async function 'embed' | `async def embed(_query: str):` |
| `435` | Warning | PY_TYPING | Missing return type hint for async function 'track_reinforce' | `async def track_reinforce(_conn, memory_id, _agent_id, _namespace_id, *, delta):` |
| `435` | Warning | PY_TYPING | Missing type hint for argument '_conn' in async function 'track_reinforce' | `async def track_reinforce(_conn, memory_id, _agent_id, _namespace_id, *, delta):` |
| `435` | Warning | PY_TYPING | Missing type hint for argument 'memory_id' in async function 'track_reinforce' | `async def track_reinforce(_conn, memory_id, _agent_id, _namespace_id, *, delta):` |
| `435` | Warning | PY_TYPING | Missing type hint for argument '_agent_id' in async function 'track_reinforce' | `async def track_reinforce(_conn, memory_id, _agent_id, _namespace_id, *, delta):` |
| `435` | Warning | PY_TYPING | Missing type hint for argument '_namespace_id' in async function 'track_reinforce' | `async def track_reinforce(_conn, memory_id, _agent_id, _namespace_id, *, delta):` |

---

### Module: `tests/test_server_mcp_error_sanitization.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `23` | Warning | PY_TYPING | Missing return type hint for function 'mock_engine' | `def mock_engine():` |
| `34` | Warning | PY_TYPING | Missing return type hint for function '_server_engine' | `def _server_engine(mock_engine):` |
| `34` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in function '_server_engine' | `def _server_engine(mock_engine):` |
| `44` | Warning | PY_TYPING | Missing return type hint for function '_disable_quotas' | `def _disable_quotas(monkeypatch):` |
| `44` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function '_disable_quotas' | `def _disable_quotas(monkeypatch):` |
| `49` | Warning | PY_TYPING | Missing return type hint for function '_prod_safe_errors' | `def _prod_safe_errors(monkeypatch):` |
| `49` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function '_prod_safe_errors' | `def _prod_safe_errors(monkeypatch):` |
| `59` | Warning | PY_TYPING | Missing return type hint for async function 'test_call_tool_internal_error_hides_detail_in_prod' | `async def test_call_tool_internal_error_hides_detail_in_prod(monkeypatch, mock_engine):` |
| `59` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_call_tool_internal_error_hides_detail_in_prod' | `async def test_call_tool_internal_error_hides_detail_in_prod(monkeypatch, mock_engine):` |
| `59` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_call_tool_internal_error_hides_detail_in_prod' | `async def test_call_tool_internal_error_hides_detail_in_prod(monkeypatch, mock_engine):` |
| `64` | Warning | PY_TYPING | Missing return type hint for async function '_boom' | `async def _boom(*_a, **_k):` |
| `89` | Warning | PY_TYPING | Missing return type hint for async function 'test_call_tool_scope_error_hides_detail_in_prod' | `async def test_call_tool_scope_error_hides_detail_in_prod(monkeypatch):` |
| `89` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_call_tool_scope_error_hides_detail_in_prod' | `async def test_call_tool_scope_error_hides_detail_in_prod(monkeypatch):` |
| `96` | Warning | PY_TYPING | Missing return type hint for async function '_scoped' | `async def _scoped(*_a, **_k):` |
| `118` | Warning | PY_TYPING | Missing return type hint for function 'test_check_admin_delegates_to_validate_scope' | `def test_check_admin_delegates_to_validate_scope(monkeypatch):` |
| `118` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_check_admin_delegates_to_validate_scope' | `def test_check_admin_delegates_to_validate_scope(monkeypatch):` |

---

### Module: `tests/test_signing_cache.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `43` | Warning | PY_TYPING | Missing return type hint for function 'test_store_and_retrieve' | `def test_store_and_retrieve(self):` |
| `50` | Warning | PY_TYPING | Missing return type hint for function 'test_contains' | `def test_contains(self):` |
| `57` | Warning | PY_TYPING | Missing return type hint for function 'test_len' | `def test_len(self):` |
| `64` | Warning | PY_TYPING | Missing return type hint for function 'test_eviction_zeros_buffer_on_del' | `def test_eviction_zeros_buffer_on_del(self):` |
| `75` | Warning | PY_TYPING | Missing return type hint for function 'test_eviction_zeros_even_if_already_zeroed' | `def test_eviction_zeros_even_if_already_zeroed(self):` |
| `84` | Warning | PY_TYPING | Missing return type hint for function 'test_get_does_not_evict' | `def test_get_does_not_evict(self):` |
| `93` | Warning | PY_TYPING | Missing return type hint for function 'test_get_missing_returns_none' | `def test_get_missing_returns_none(self):` |
| `97` | Warning | PY_TYPING | Missing return type hint for function 'test_maxsize_eviction' | `def test_maxsize_eviction(self):` |
| `114` | Warning | PY_TYPING | Missing return type hint for function 'test_ttl_expiry_zeros_on_gc' | `def test_ttl_expiry_zeros_on_gc(self):` |
| `132` | Warning | PY_TYPING | Missing return type hint for function 'test_independent_buffer_copies' | `def test_independent_buffer_copies(self):` |
| `158` | Warning | PY_TYPING | Missing return type hint for async function 'test_cache_hit_returns_cached_key' | `async def test_cache_hit_returns_cached_key(self):` |
| `174` | Warning | PY_TYPING | Missing return type hint for async function 'test_cache_miss_fetches_from_db' | `async def test_cache_miss_fetches_from_db(self):` |
| `206` | Warning | PY_TYPING | Missing return type hint for async function 'test_cache_miss_no_active_key_raises' | `async def test_cache_miss_no_active_key_raises(self):` |
| `222` | Warning | PY_TYPING | Missing return type hint for async function 'test_cache_hit_does_not_refresh_expiry' | `async def test_cache_hit_does_not_refresh_expiry(self, monkeypatch):` |
| `222` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_cache_hit_does_not_refresh_expiry' | `async def test_cache_hit_does_not_refresh_expiry(self, monkeypatch):` |
| `246` | Warning | PY_TYPING | Missing return type hint for async function 'test_cache_hit_by_id' | `async def test_cache_hit_by_id(self):` |
| `259` | Warning | PY_TYPING | Missing return type hint for async function 'test_cache_miss_by_id_fetches_from_db' | `async def test_cache_miss_by_id_fetches_from_db(self):` |
| `283` | Warning | PY_TYPING | Missing return type hint for async function 'test_not_found_raises' | `async def test_not_found_raises(self):` |
| `305` | Warning | PY_TYPING | Missing return type hint for function 'test_rotate_clears_cache_and_zeros_buffers' | `def test_rotate_clears_cache_and_zeros_buffers(self, monkeypatch):` |
| `305` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_rotate_clears_cache_and_zeros_buffers' | `def test_rotate_clears_cache_and_zeros_buffers(self, monkeypatch):` |
| `320` | Error | PY_EXCEPT_PASS | Unhandled exception block (except: pass) | `except Exception:` |
| `338` | Warning | PY_TYPING | Missing return type hint for function 'test_cache_is_signing_key_cache_instance' | `def test_cache_is_signing_key_cache_instance(self):` |
| `341` | Warning | PY_TYPING | Missing return type hint for function 'test_cache_maxsize_is_1000' | `def test_cache_maxsize_is_1000(self):` |
| `344` | Warning | PY_TYPING | Missing return type hint for function 'test_cache_ttl_is_300' | `def test_cache_ttl_is_300(self):` |

---

### Module: `tests/test_signing_kdf.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `30` | Warning | PY_TYPING | Missing return type hint for function 'test_pbkdf2_iteration_count_is_at_least_100k' | `def test_pbkdf2_iteration_count_is_at_least_100k():` |
| `34` | Warning | PY_TYPING | Missing return type hint for function 'test_pbkdf2_v4_iteration_count_is_at_least_600k' | `def test_pbkdf2_v4_iteration_count_is_at_least_600k():` |
| `38` | Warning | PY_TYPING | Missing return type hint for function 'test_derive_aes_key_is_deterministic_for_same_master' | `def test_derive_aes_key_is_deterministic_for_same_master():` |
| `47` | Warning | PY_TYPING | Missing return type hint for function 'test_pbkdf2_different_salts_yield_different_keys' | `def test_pbkdf2_different_salts_yield_different_keys():` |
| `55` | Warning | PY_TYPING | Missing return type hint for function 'test_pbkdf2_rejects_short_salt' | `def test_pbkdf2_rejects_short_salt():` |
| `62` | Warning | PY_TYPING | Missing return type hint for function 'test_encrypt_emits_magic_and_unique_salts' | `def test_encrypt_emits_magic_and_unique_salts():` |
| `80` | Warning | PY_TYPING | Missing return type hint for function 'test_v2_blob_still_decrypts' | `def test_v2_blob_still_decrypts():` |
| `94` | Warning | PY_TYPING | Missing return type hint for function 'test_v3_blob_roundtrip' | `def test_v3_blob_roundtrip():` |
| `106` | Warning | PY_TYPING | Missing return type hint for function 'test_v3_blob_wrong_master_fails' | `def test_v3_blob_wrong_master_fails():` |
| `120` | Warning | PY_TYPING | Missing return type hint for function 'test_argon2id_produces_different_key_than_pbkdf2' | `def test_argon2id_produces_different_key_than_pbkdf2():` |
| `132` | Warning | PY_TYPING | Missing return type hint for function 'test_legacy_sha256_wrapped_blob_still_decrypts' | `def test_legacy_sha256_wrapped_blob_still_decrypts():` |
| `144` | Warning | PY_TYPING | Missing return type hint for function 'test_v2_blob_too_short_raises' | `def test_v2_blob_too_short_raises():` |
| `152` | Warning | PY_TYPING | Missing return type hint for function 'test_wrong_master_fails_v2' | `def test_wrong_master_fails_v2():` |
| `167` | Warning | PY_TYPING | Missing return type hint for function 'test_v4_blob_still_decrypts_v2' | `def test_v4_blob_still_decrypts_v2():` |
| `180` | Warning | PY_TYPING | Missing return type hint for function 'test_v4_blob_roundtrip_without_argon2' | `def test_v4_blob_roundtrip_without_argon2():` |
| `192` | Warning | PY_TYPING | Missing return type hint for function 'test_v4_blob_wrong_master_fails' | `def test_v4_blob_wrong_master_fails():` |
| `206` | Warning | PY_TYPING | Missing return type hint for function 'test_v4_blob_too_short_raises' | `def test_v4_blob_too_short_raises():` |
| `214` | Warning | PY_TYPING | Missing return type hint for function 'test_v4_pbkdf2_produces_different_key_than_v2' | `def test_v4_pbkdf2_produces_different_key_than_v2():` |
| `224` | Warning | PY_TYPING | Missing return type hint for function 'test_v4_derive_aes_key_rejects_short_salt' | `def test_v4_derive_aes_key_rejects_short_salt():` |

---

### Module: `tests/test_sleep_consolidation.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `30` | Warning | PY_TYPING | Missing return type hint for async function 'complete' | `async def complete(self, messages: list, response_model: type):  # noqa: ANN401` |
| `166` | Warning | PY_TYPING | Missing return type hint for function 'patch_hdbscan' | `def patch_hdbscan(monkeypatch: pytest.MonkeyPatch):` |
| `173` | Warning | PY_TYPING | Missing return type hint for function 'patch_signing' | `def patch_signing(monkeypatch: pytest.MonkeyPatch):` |
| `187` | Warning | PY_TYPING | Missing return type hint for function 'test_consolidation_no_memories_completes' | `def test_consolidation_no_memories_completes(patch_signing, monkeypatch: pytest.MonkeyPatch):` |
| `187` | Warning | PY_TYPING | Missing type hint for argument 'patch_signing' in function 'test_consolidation_no_memories_completes' | `def test_consolidation_no_memories_completes(patch_signing, monkeypatch: pytest.MonkeyPatch):` |
| `207` | Warning | PY_TYPING | Missing return type hint for function 'test_consolidation_skips_low_confidence' | `def test_consolidation_skips_low_confidence(patch_hdbscan, patch_signing):` |
| `207` | Warning | PY_TYPING | Missing type hint for argument 'patch_hdbscan' in function 'test_consolidation_skips_low_confidence' | `def test_consolidation_skips_low_confidence(patch_hdbscan, patch_signing):` |
| `207` | Warning | PY_TYPING | Missing type hint for argument 'patch_signing' in function 'test_consolidation_skips_low_confidence' | `def test_consolidation_skips_low_confidence(patch_hdbscan, patch_signing):` |
| `234` | Warning | PY_TYPING | Missing return type hint for function 'test_consolidation_skips_contradictions' | `def test_consolidation_skips_contradictions(patch_hdbscan, patch_signing):` |
| `234` | Warning | PY_TYPING | Missing type hint for argument 'patch_hdbscan' in function 'test_consolidation_skips_contradictions' | `def test_consolidation_skips_contradictions(patch_hdbscan, patch_signing):` |
| `234` | Warning | PY_TYPING | Missing type hint for argument 'patch_signing' in function 'test_consolidation_skips_contradictions' | `def test_consolidation_skips_contradictions(patch_hdbscan, patch_signing):` |
| `260` | Warning | PY_TYPING | Missing return type hint for function 'test_consolidation_skips_hallucinated_supporting_ids' | `def test_consolidation_skips_hallucinated_supporting_ids(patch_hdbscan, patch_signing):` |
| `260` | Warning | PY_TYPING | Missing type hint for argument 'patch_hdbscan' in function 'test_consolidation_skips_hallucinated_supporting_ids' | `def test_consolidation_skips_hallucinated_supporting_ids(patch_hdbscan, patch_signing):` |
| `260` | Warning | PY_TYPING | Missing type hint for argument 'patch_signing' in function 'test_consolidation_skips_hallucinated_supporting_ids' | `def test_consolidation_skips_hallucinated_supporting_ids(patch_hdbscan, patch_signing):` |
| `298` | Warning | PY_TYPING | Missing return type hint for function 'test_consolidation_happy_path_writes_memory_event_and_kg' | `def test_consolidation_happy_path_writes_memory_event_and_kg(patch_hdbscan, patch_signing):` |
| `298` | Warning | PY_TYPING | Missing type hint for argument 'patch_hdbscan' in function 'test_consolidation_happy_path_writes_memory_event_and_kg' | `def test_consolidation_happy_path_writes_memory_event_and_kg(patch_hdbscan, patch_signing):` |
| `298` | Warning | PY_TYPING | Missing type hint for argument 'patch_signing' in function 'test_consolidation_happy_path_writes_memory_event_and_kg' | `def test_consolidation_happy_path_writes_memory_event_and_kg(patch_hdbscan, patch_signing):` |
| `323` | Warning | PY_TYPING | Missing return type hint for function 'test_consolidation_decay_sources_updates_salience' | `def test_consolidation_decay_sources_updates_salience(` |
| `323` | Warning | PY_TYPING | Missing type hint for argument 'patch_hdbscan' in function 'test_consolidation_decay_sources_updates_salience' | `def test_consolidation_decay_sources_updates_salience(` |
| `323` | Warning | PY_TYPING | Missing type hint for argument 'patch_signing' in function 'test_consolidation_decay_sources_updates_salience' | `def test_consolidation_decay_sources_updates_salience(` |
| `356` | Warning | PY_TYPING | Missing return type hint for function 'test_consolidated_abstraction_roundtrip' | `def test_consolidated_abstraction_roundtrip():` |
| `369` | Warning | PY_TYPING | Missing return type hint for function 'test_prompt_injection_sanitization' | `def test_prompt_injection_sanitization():` |

---

### Module: `tests/test_smoke_stdio.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `36` | Warning | PY_TYPING | Missing return type hint for async function 'test_stdio_smoke_indexing' | `async def test_stdio_smoke_indexing():` |
| `72` | Warning | PY_TYPING | Missing return type hint for async function 'test_stdio_smoke_memory' | `async def test_stdio_smoke_memory():` |

---

### Module: `tests/test_snapshot_mcp_handlers.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `21` | Warning | PY_TYPING | Missing return type hint for async function '_collect' | `async def _collect(gen):` |
| `21` | Warning | PY_TYPING | Missing type hint for argument 'gen' in async function '_collect' | `async def _collect(gen):` |

---

### Module: `tests/test_snapshot_serializer.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `63` | Warning | PY_TYPING | Missing return type hint for function 'now' | `def now(cls, tz=None):  # type: ignore[override]` |
| `63` | Warning | PY_TYPING | Missing type hint for argument 'tz' in function 'now' | `def now(cls, tz=None):  # type: ignore[override]` |
| `73` | Warning | PY_TYPING | Missing return type hint for function 'test_missing_name_raises_valueerror' | `def test_missing_name_raises_valueerror(self):` |
| `79` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_name_raises_valueerror' | `def test_empty_name_raises_valueerror(self):` |
| `83` | Warning | PY_TYPING | Missing return type hint for function 'test_name_over_256_chars_raises_valueerror' | `def test_name_over_256_chars_raises_valueerror(self):` |
| `87` | Warning | PY_TYPING | Missing return type hint for function 'test_name_strips_whitespace' | `def test_name_strips_whitespace(self):` |
| `91` | Warning | PY_TYPING | Missing return type hint for function 'test_metadata_string_raises_valueerror' | `def test_metadata_string_raises_valueerror(self):` |
| `95` | Warning | PY_TYPING | Missing return type hint for function 'test_metadata_defaults_are_independent_dicts' | `def test_metadata_defaults_are_independent_dicts(self):` |
| `102` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_agent_id_normalized_to_default' | `def test_empty_agent_id_normalized_to_default(self):` |
| `109` | Warning | PY_TYPING | Missing return type hint for function 'test_top_k_clamps_to_max_top_k' | `def test_top_k_clamps_to_max_top_k(self):` |
| `115` | Warning | PY_TYPING | Missing return type hint for function 'test_top_k_zero_clamps_to_one' | `def test_top_k_zero_clamps_to_one(self):` |
| `119` | Warning | PY_TYPING | Missing return type hint for function 'test_as_of_a_equal_as_of_b_raises_valueerror' | `def test_as_of_a_equal_as_of_b_raises_valueerror(self):` |
| `130` | Warning | PY_TYPING | Missing return type hint for function 'test_as_of_a_after_as_of_b_raises_valueerror' | `def test_as_of_a_after_as_of_b_raises_valueerror(self):` |
| `141` | Warning | PY_TYPING | Missing return type hint for function 'test_as_of_a_before_as_of_b_succeeds' | `def test_as_of_a_before_as_of_b_succeeds(self):` |
| `146` | Warning | PY_TYPING | Missing return type hint for function 'test_query_over_max_length_raises_valueerror' | `def test_query_over_max_length_raises_valueerror(self):` |
| `152` | Warning | PY_TYPING | Missing return type hint for function 'test_query_at_max_length_succeeds' | `def test_query_at_max_length_succeeds(self):` |
| `161` | Warning | PY_TYPING | Missing return type hint for function 'test_returns_valid_json' | `def test_returns_valid_json(self):` |
| `178` | Warning | PY_TYPING | Missing return type hint for function 'test_returns_valid_json_with_uuid_and_datetime_fields' | `def test_returns_valid_json_with_uuid_and_datetime_fields(self):` |

---

### Module: `tests/test_sql_injection_temporal.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `10` | Warning | PY_TYPING | Missing return type hint for async function 'test_semantic_search_temporal_parameters_prevent_sql_injection' | `async def test_semantic_search_temporal_parameters_prevent_sql_injection(monkeypatch):` |
| `10` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_semantic_search_temporal_parameters_prevent_sql_injection' | `async def test_semantic_search_temporal_parameters_prevent_sql_injection(monkeypatch):` |

---

### Module: `tests/test_ssrf_guard.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `30` | Warning | PY_TYPING | Missing return type hint for function '_mock_getaddrinfo' | `def _mock_getaddrinfo(ip_str: str, family: int = socket.AF_INET):` |
| `33` | Warning | PY_TYPING | Missing return type hint for function 'mock_getaddrinfo' | `def mock_getaddrinfo(` |
| `96` | Warning | PY_TYPING | Missing return type hint for function 'test_scenario' | `def test_scenario(` |
| `169` | Warning | PY_TYPING | Missing return type hint for async function 'test_public_https_passes' | `async def test_public_https_passes(self, monkeypatch: pytest.MonkeyPatch):` |
| `176` | Warning | PY_TYPING | Missing return type hint for async function 'test_loopback_rejected' | `async def test_loopback_rejected(self, monkeypatch: pytest.MonkeyPatch):` |
| `194` | Warning | PY_TYPING | Missing return type hint for function 'test_accepts_sites_resource_path' | `def test_accepts_sites_resource_path(self):` |
| `200` | Warning | PY_TYPING | Missing return type hint for function 'test_accepts_users_resource_path' | `def test_accepts_users_resource_path(self):` |
| `206` | Warning | PY_TYPING | Missing return type hint for function 'test_accepts_drives_resource_path' | `def test_accepts_drives_resource_path(self):` |
| `212` | Warning | PY_TYPING | Missing return type hint for function 'test_accepts_groups_resource_path' | `def test_accepts_groups_resource_path(self):` |
| `218` | Warning | PY_TYPING | Missing return type hint for function 'test_accepts_me_resource_path' | `def test_accepts_me_resource_path(self):` |
| `221` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_arbitrary_resource_path' | `def test_rejects_arbitrary_resource_path(self):` |
| `225` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_path_traversal_resource' | `def test_rejects_path_traversal_resource(self):` |
| `231` | Warning | PY_TYPING | Missing return type hint for function 'test_accepts_public_graph_url' | `def test_accepts_public_graph_url(self, monkeypatch: pytest.MonkeyPatch):` |
| `238` | Warning | PY_TYPING | Missing return type hint for function 'test_accepts_googleapis_url' | `def test_accepts_googleapis_url(self, monkeypatch: pytest.MonkeyPatch):` |
| `243` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_http_scheme' | `def test_rejects_http_scheme(self):` |
| `247` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_private_ip_url' | `def test_rejects_private_ip_url(self, monkeypatch: pytest.MonkeyPatch):` |
| `252` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_loopback_url' | `def test_rejects_loopback_url(self, monkeypatch: pytest.MonkeyPatch):` |
| `257` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_unknown_url_prefix' | `def test_rejects_unknown_url_prefix(self, monkeypatch: pytest.MonkeyPatch):` |
| `262` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_empty_url' | `def test_rejects_empty_url(self):` |
| `266` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_blank_url' | `def test_rejects_blank_url(self):` |
| `281` | Warning | PY_TYPING | Missing return type hint for function 'test_accepts_miro_base_url' | `def test_accepts_miro_base_url(self, monkeypatch: pytest.MonkeyPatch):` |
| `286` | Warning | PY_TYPING | Missing return type hint for function 'test_accepts_lucid_base_url' | `def test_accepts_lucid_base_url(self, monkeypatch: pytest.MonkeyPatch):` |
| `291` | Warning | PY_TYPING | Missing return type hint for function 'test_accepts_generic_public_https_url' | `def test_accepts_generic_public_https_url(self, monkeypatch: pytest.MonkeyPatch):` |
| `298` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_http_scheme' | `def test_rejects_http_scheme(self):` |
| `302` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_ftp_scheme' | `def test_rejects_ftp_scheme(self):` |
| `306` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_no_scheme' | `def test_rejects_no_scheme(self):` |
| `323` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_private_ipv4' | `def test_rejects_private_ipv4(self, url: str, label: str, monkeypatch: pytest.MonkeyPatch):` |
| `342` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_loopback' | `def test_rejects_loopback(self, url: str, ip: str, monkeypatch: pytest.MonkeyPatch):` |
| `351` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_link_local' | `def test_rejects_link_local(self, monkeypatch: pytest.MonkeyPatch):` |
| `358` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_aws_metadata_hostname' | `def test_rejects_aws_metadata_hostname(self, monkeypatch: pytest.MonkeyPatch):` |
| `366` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_private_ipv6' | `def test_rejects_private_ipv6(self, monkeypatch: pytest.MonkeyPatch):` |
| `381` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_explicit_ipv6_ssrf_subnets' | `def test_rejects_explicit_ipv6_ssrf_subnets(` |
| `389` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_ipv6_zone_id_sockaddr' | `def test_rejects_ipv6_zone_id_sockaddr(self, monkeypatch: pytest.MonkeyPatch):` |
| `397` | Warning | PY_TYPING | Missing return type hint for function 'test_accepts_public_ipv6_bracket_sockaddr' | `def test_accepts_public_ipv6_bracket_sockaddr(self, monkeypatch: pytest.MonkeyPatch):` |
| `400` | Warning | PY_TYPING | Missing return type hint for function 'mock_getaddrinfo' | `def mock_getaddrinfo(` |
| `424` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_multicast' | `def test_rejects_multicast(self, monkeypatch: pytest.MonkeyPatch):` |
| `431` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_empty_url' | `def test_rejects_empty_url(self):` |
| `435` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_blank_url' | `def test_rejects_blank_url(self):` |
| `439` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_invalid_url' | `def test_rejects_invalid_url(self):` |
| `445` | Warning | PY_TYPING | Missing return type hint for function 'test_rejects_unresolvable_hostname' | `def test_rejects_unresolvable_hostname(self, monkeypatch: pytest.MonkeyPatch):` |
| `465` | Warning | PY_TYPING | Missing return type hint for async function 'test_miro_rejects_private_base_url' | `async def test_miro_rejects_private_base_url(self, monkeypatch: pytest.MonkeyPatch):` |
| `481` | Warning | PY_TYPING | Missing return type hint for async function 'test_miro_rejects_loopback_base_url' | `async def test_miro_rejects_loopback_base_url(self, monkeypatch: pytest.MonkeyPatch):` |
| `496` | Warning | PY_TYPING | Missing return type hint for async function 'test_miro_rejects_http_base_url' | `async def test_miro_rejects_http_base_url(self, monkeypatch: pytest.MonkeyPatch):` |
| `511` | Warning | PY_TYPING | Missing return type hint for async function 'test_miro_accepts_default_base_url' | `async def test_miro_accepts_default_base_url(self, monkeypatch: pytest.MonkeyPatch):` |
| `525` | Warning | PY_TYPING | Missing return type hint for async function 'test_lucid_rejects_private_base_url' | `async def test_lucid_rejects_private_base_url(self, monkeypatch: pytest.MonkeyPatch):` |
| `541` | Warning | PY_TYPING | Missing return type hint for async function 'test_lucid_rejects_aws_metadata_url' | `async def test_lucid_rejects_aws_metadata_url(self, monkeypatch: pytest.MonkeyPatch):` |
| `556` | Warning | PY_TYPING | Missing return type hint for async function 'test_lucid_rejects_http_base_url' | `async def test_lucid_rejects_http_base_url(self, monkeypatch: pytest.MonkeyPatch):` |
| `570` | Warning | PY_TYPING | Missing return type hint for async function 'test_lucid_accepts_default_base_url' | `async def test_lucid_accepts_default_base_url(self, monkeypatch: pytest.MonkeyPatch):` |

---

### Module: `tests/test_temporal_batch1.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `30` | Warning | PY_TYPING | Missing return type hint for function 'now' | `def now(cls, tz=None):  # type: ignore[override]` |
| `30` | Warning | PY_TYPING | Missing type hint for argument 'tz' in function 'now' | `def now(cls, tz=None):  # type: ignore[override]` |

---

### Module: `tests/test_temporal_batch3.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `30` | Warning | PY_TYPING | Missing return type hint for function 'now' | `def now(cls, tz=None):  # type: ignore[override]` |
| `30` | Warning | PY_TYPING | Missing type hint for argument 'tz' in function 'now' | `def now(cls, tz=None):  # type: ignore[override]` |

---

### Module: `tests/test_tool_registry.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `34` | Warning | PY_TYPING | Missing return type hint for function 'test_registry_has_54_entries' | `def test_registry_has_54_entries():` |
| `46` | Warning | PY_TYPING | Missing return type hint for function 'test_all_handlers_are_async_callables' | `def test_all_handlers_are_async_callables():` |
| `101` | Warning | PY_TYPING | Missing return type hint for function 'test_mutation_tools_exact_match' | `def test_mutation_tools_exact_match():` |
| `108` | Warning | PY_TYPING | Missing return type hint for function 'test_mutation_tools_count' | `def test_mutation_tools_count():` |
| `121` | Warning | PY_TYPING | Missing return type hint for function 'test_cacheable_tools_exact_match' | `def test_cacheable_tools_exact_match():` |
| `128` | Warning | PY_TYPING | Missing return type hint for function 'test_cacheable_tools_count' | `def test_cacheable_tools_count():` |
| `147` | Warning | PY_TYPING | Missing return type hint for function 'test_admin_only_tools_exact_match' | `def test_admin_only_tools_exact_match():` |
| `154` | Warning | PY_TYPING | Missing return type hint for function 'test_admin_only_tools_count' | `def test_admin_only_tools_count():` |
| `173` | Warning | PY_TYPING | Missing return type hint for function 'test_migration_tools_exact_match' | `def test_migration_tools_exact_match():` |
| `180` | Warning | PY_TYPING | Missing return type hint for function 'test_migration_tools_count' | `def test_migration_tools_count():` |
| `189` | Warning | PY_TYPING | Missing return type hint for function 'test_mutation_tools_subset_of_registry' | `def test_mutation_tools_subset_of_registry():` |
| `193` | Warning | PY_TYPING | Missing return type hint for function 'test_cacheable_tools_subset_of_registry' | `def test_cacheable_tools_subset_of_registry():` |
| `197` | Warning | PY_TYPING | Missing return type hint for function 'test_admin_only_tools_subset_of_registry' | `def test_admin_only_tools_subset_of_registry():` |
| `201` | Warning | PY_TYPING | Missing return type hint for function 'test_migration_tools_subset_of_registry' | `def test_migration_tools_subset_of_registry():` |
| `205` | Warning | PY_TYPING | Missing return type hint for function 'test_migration_mutations_are_in_mutation_tools' | `def test_migration_mutations_are_in_mutation_tools():` |
| `215` | Warning | PY_TYPING | Missing return type hint for function 'test_no_tool_is_cacheable_and_mutation' | `def test_no_tool_is_cacheable_and_mutation():` |
| `226` | Warning | PY_TYPING | Missing return type hint for function 'test_toolspec_is_frozen' | `def test_toolspec_is_frozen():` |
| `273` | Warning | PY_TYPING | Missing return type hint for function 'test_tool_flags' | `def test_tool_flags(tool_name: str, expected_flags: dict):` |

---

### Module: `tests/test_tools_administration.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `22` | Warning | PY_TYPING | Missing type hint for argument 'data' in function '__init__' | `def __init__(self, data=None):` |
| `29` | Warning | PY_TYPING | Missing return type hint for function '_hset' | `def _hset(self, name, key, val):` |
| `29` | Warning | PY_TYPING | Missing type hint for argument 'name' in function '_hset' | `def _hset(self, name, key, val):` |
| `29` | Warning | PY_TYPING | Missing type hint for argument 'key' in function '_hset' | `def _hset(self, name, key, val):` |
| `29` | Warning | PY_TYPING | Missing type hint for argument 'val' in function '_hset' | `def _hset(self, name, key, val):` |
| `33` | Warning | PY_TYPING | Missing return type hint for function '_hdel' | `def _hdel(self, name, key):` |
| `33` | Warning | PY_TYPING | Missing type hint for argument 'name' in function '_hdel' | `def _hdel(self, name, key):` |
| `33` | Warning | PY_TYPING | Missing type hint for argument 'key' in function '_hdel' | `def _hdel(self, name, key):` |
| `41` | Warning | PY_TYPING | Missing return type hint for function 'mock_engine' | `def mock_engine():` |
| `50` | Warning | PY_TYPING | Missing return type hint for async function 'test_api_admin_tools_list_all_enabled' | `async def test_api_admin_tools_list_all_enabled(mock_engine):` |
| `50` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_api_admin_tools_list_all_enabled' | `async def test_api_admin_tools_list_all_enabled(mock_engine):` |
| `86` | Warning | PY_TYPING | Missing return type hint for async function 'test_api_admin_tools_list_with_disabled_items' | `async def test_api_admin_tools_list_with_disabled_items(mock_engine):` |
| `86` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_api_admin_tools_list_with_disabled_items' | `async def test_api_admin_tools_list_with_disabled_items(mock_engine):` |
| `112` | Warning | PY_TYPING | Missing return type hint for async function 'test_api_admin_tools_list_redis_fail_safe' | `async def test_api_admin_tools_list_redis_fail_safe(mock_engine):` |
| `112` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_api_admin_tools_list_redis_fail_safe' | `async def test_api_admin_tools_list_redis_fail_safe(mock_engine):` |
| `130` | Warning | PY_TYPING | Missing return type hint for async function 'test_api_admin_tools_toggle_success' | `async def test_api_admin_tools_toggle_success(mock_engine):` |
| `130` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_api_admin_tools_toggle_success' | `async def test_api_admin_tools_toggle_success(mock_engine):` |
| `135` | Warning | PY_TYPING | Missing return type hint for async function 'mock_receive' | `async def mock_receive():` |
| `151` | Warning | PY_TYPING | Missing return type hint for async function 'mock_receive_enable' | `async def mock_receive_enable():` |
| `163` | Warning | PY_TYPING | Missing return type hint for async function 'test_api_admin_tools_toggle_invalid_requests' | `async def test_api_admin_tools_toggle_invalid_requests(mock_engine):` |
| `163` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_api_admin_tools_toggle_invalid_requests' | `async def test_api_admin_tools_toggle_invalid_requests(mock_engine):` |
| `170` | Warning | PY_TYPING | Missing return type hint for async function 'mock_receive_invalid_type' | `async def mock_receive_invalid_type():` |
| `178` | Warning | PY_TYPING | Missing return type hint for async function 'mock_receive_missing' | `async def mock_receive_missing():` |
| `186` | Warning | PY_TYPING | Missing return type hint for async function 'test_api_admin_tools_toggle_redis_down' | `async def test_api_admin_tools_toggle_redis_down(mock_engine):` |
| `186` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_api_admin_tools_toggle_redis_down' | `async def test_api_admin_tools_toggle_redis_down(mock_engine):` |
| `192` | Warning | PY_TYPING | Missing return type hint for async function 'mock_receive' | `async def mock_receive():` |
| `203` | Warning | PY_TYPING | Missing return type hint for async function 'test_stdio_mcp_dispatch_interception' | `async def test_stdio_mcp_dispatch_interception(mock_engine):` |
| `203` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_stdio_mcp_dispatch_interception' | `async def test_stdio_mcp_dispatch_interception(mock_engine):` |
| `223` | Warning | PY_TYPING | Missing return type hint for async function 'test_stdio_mcp_dispatch_fail_safe' | `async def test_stdio_mcp_dispatch_fail_safe(mock_engine):` |
| `223` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_stdio_mcp_dispatch_fail_safe' | `async def test_stdio_mcp_dispatch_fail_safe(mock_engine):` |
| `245` | Warning | PY_TYPING | Missing return type hint for async function 'test_a2a_skill_server_interception' | `async def test_a2a_skill_server_interception(mock_engine):` |
| `245` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_a2a_skill_server_interception' | `async def test_a2a_skill_server_interception(mock_engine):` |
| `260` | Warning | PY_TYPING | Missing return type hint for async function 'test_a2a_skill_server_fail_safe' | `async def test_a2a_skill_server_fail_safe(mock_engine):` |
| `260` | Warning | PY_TYPING | Missing type hint for argument 'mock_engine' in async function 'test_a2a_skill_server_fail_safe' | `async def test_a2a_skill_server_fail_safe(mock_engine):` |

---

### Module: `tests/test_webhook_receiver.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `22` | Warning | PY_TYPING | Missing return type hint for function 'client' | `def client():` |
| `29` | Warning | PY_TYPING | Missing return type hint for function '_webhook_test_isolation' | `def _webhook_test_isolation(monkeypatch):` |
| `29` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function '_webhook_test_isolation' | `def _webhook_test_isolation(monkeypatch):` |
| `36` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function '_stub_enqueue' | `def _stub_enqueue(monkeypatch, job_id: str) -> MagicMock:` |
| `42` | Warning | PY_TYPING | Missing return type hint for function 'test_dropbox_challenge' | `def test_dropbox_challenge(client):` |
| `42` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_dropbox_challenge' | `def test_dropbox_challenge(client):` |
| `48` | Warning | PY_TYPING | Missing return type hint for function 'test_dropbox_webhook_valid_signature' | `def test_dropbox_webhook_valid_signature(client, monkeypatch):` |
| `48` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_dropbox_webhook_valid_signature' | `def test_dropbox_webhook_valid_signature(client, monkeypatch):` |
| `48` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_dropbox_webhook_valid_signature' | `def test_dropbox_webhook_valid_signature(client, monkeypatch):` |
| `66` | Warning | PY_TYPING | Missing return type hint for function 'test_dropbox_webhook_invalid_signature' | `def test_dropbox_webhook_invalid_signature(client):` |
| `66` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_dropbox_webhook_invalid_signature' | `def test_dropbox_webhook_invalid_signature(client):` |
| `78` | Warning | PY_TYPING | Missing return type hint for function 'test_dropbox_webhook_missing_signature' | `def test_dropbox_webhook_missing_signature(client):` |
| `78` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_dropbox_webhook_missing_signature' | `def test_dropbox_webhook_missing_signature(client):` |
| `89` | Warning | PY_TYPING | Missing return type hint for function 'test_graph_webhook_challenge' | `def test_graph_webhook_challenge(client):` |
| `89` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_graph_webhook_challenge' | `def test_graph_webhook_challenge(client):` |
| `95` | Warning | PY_TYPING | Missing return type hint for function 'test_graph_webhook_valid_client_state' | `def test_graph_webhook_valid_client_state(client, monkeypatch):` |
| `95` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_graph_webhook_valid_client_state' | `def test_graph_webhook_valid_client_state(client, monkeypatch):` |
| `95` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_graph_webhook_valid_client_state' | `def test_graph_webhook_valid_client_state(client, monkeypatch):` |
| `115` | Warning | PY_TYPING | Missing return type hint for function 'test_graph_webhook_invalid_client_state' | `def test_graph_webhook_invalid_client_state(client):` |
| `115` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_graph_webhook_invalid_client_state' | `def test_graph_webhook_invalid_client_state(client):` |
| `130` | Warning | PY_TYPING | Missing return type hint for function 'test_drive_webhook_valid' | `def test_drive_webhook_valid(client, monkeypatch):` |
| `130` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_drive_webhook_valid' | `def test_drive_webhook_valid(client, monkeypatch):` |
| `130` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_drive_webhook_valid' | `def test_drive_webhook_valid(client, monkeypatch):` |
| `151` | Warning | PY_TYPING | Missing return type hint for function 'test_drive_webhook_sync_no_enqueue' | `def test_drive_webhook_sync_no_enqueue(client, monkeypatch):` |
| `151` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_drive_webhook_sync_no_enqueue' | `def test_drive_webhook_sync_no_enqueue(client, monkeypatch):` |
| `151` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_drive_webhook_sync_no_enqueue' | `def test_drive_webhook_sync_no_enqueue(client, monkeypatch):` |
| `165` | Warning | PY_TYPING | Missing return type hint for function 'test_drive_webhook_invalid_token' | `def test_drive_webhook_invalid_token(client):` |
| `165` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_drive_webhook_invalid_token' | `def test_drive_webhook_invalid_token(client):` |
| `176` | Warning | PY_TYPING | Missing return type hint for function 'test_drive_webhook_missing_state' | `def test_drive_webhook_missing_state(client):` |
| `176` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_drive_webhook_missing_state' | `def test_drive_webhook_missing_state(client):` |
| `189` | Warning | PY_TYPING | Missing return type hint for function 'test_graph_webhook_valid_sites_resource' | `def test_graph_webhook_valid_sites_resource(client, monkeypatch):` |
| `189` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_graph_webhook_valid_sites_resource' | `def test_graph_webhook_valid_sites_resource(client, monkeypatch):` |
| `189` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_graph_webhook_valid_sites_resource' | `def test_graph_webhook_valid_sites_resource(client, monkeypatch):` |
| `206` | Warning | PY_TYPING | Missing return type hint for function 'test_graph_webhook_valid_drives_resource' | `def test_graph_webhook_valid_drives_resource(client, monkeypatch):` |
| `206` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_graph_webhook_valid_drives_resource' | `def test_graph_webhook_valid_drives_resource(client, monkeypatch):` |
| `206` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_graph_webhook_valid_drives_resource' | `def test_graph_webhook_valid_drives_resource(client, monkeypatch):` |
| `222` | Warning | PY_TYPING | Missing return type hint for function 'test_graph_webhook_rejects_internal_resource' | `def test_graph_webhook_rejects_internal_resource(client):` |
| `222` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_graph_webhook_rejects_internal_resource' | `def test_graph_webhook_rejects_internal_resource(client):` |
| `238` | Warning | PY_TYPING | Missing return type hint for function 'test_graph_webhook_rejects_path_traversal_resource' | `def test_graph_webhook_rejects_path_traversal_resource(client):` |
| `238` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_graph_webhook_rejects_path_traversal_resource' | `def test_graph_webhook_rejects_path_traversal_resource(client):` |
| `254` | Warning | PY_TYPING | Missing return type hint for function 'test_graph_webhook_rejects_http_resource' | `def test_graph_webhook_rejects_http_resource(client):` |
| `254` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_graph_webhook_rejects_http_resource' | `def test_graph_webhook_rejects_http_resource(client):` |
| `269` | Warning | PY_TYPING | Missing return type hint for function 'test_dropbox_webhook_rejects_oversize_body' | `def test_dropbox_webhook_rejects_oversize_body(client, monkeypatch):` |
| `269` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_dropbox_webhook_rejects_oversize_body' | `def test_dropbox_webhook_rejects_oversize_body(client, monkeypatch):` |
| `269` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_dropbox_webhook_rejects_oversize_body' | `def test_dropbox_webhook_rejects_oversize_body(client, monkeypatch):` |
| `284` | Warning | PY_TYPING | Missing return type hint for function 'test_dropbox_webhook_dedup_skips_duplicate' | `def test_dropbox_webhook_dedup_skips_duplicate(client, monkeypatch):` |
| `284` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_dropbox_webhook_dedup_skips_duplicate' | `def test_dropbox_webhook_dedup_skips_duplicate(client, monkeypatch):` |
| `284` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_dropbox_webhook_dedup_skips_duplicate' | `def test_dropbox_webhook_dedup_skips_duplicate(client, monkeypatch):` |
| `305` | Warning | PY_TYPING | Missing return type hint for function 'test_claim_dedup_fail_closed_when_redis_unavailable' | `def test_claim_dedup_fail_closed_when_redis_unavailable(monkeypatch):` |
| `305` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_claim_dedup_fail_closed_when_redis_unavailable' | `def test_claim_dedup_fail_closed_when_redis_unavailable(monkeypatch):` |
| `314` | Warning | PY_TYPING | Missing return type hint for function 'test_claim_dedup_fail_open_when_configured' | `def test_claim_dedup_fail_open_when_configured(monkeypatch):` |
| `314` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_claim_dedup_fail_open_when_configured' | `def test_claim_dedup_fail_open_when_configured(monkeypatch):` |
| `323` | Warning | PY_TYPING | Missing return type hint for function 'test_webhook_rate_limit_returns_429' | `def test_webhook_rate_limit_returns_429(client, monkeypatch):` |
| `323` | Warning | PY_TYPING | Missing type hint for argument 'client' in function 'test_webhook_rate_limit_returns_429' | `def test_webhook_rate_limit_returns_429(client, monkeypatch):` |
| `323` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function 'test_webhook_rate_limit_returns_429' | `def test_webhook_rate_limit_returns_429(client, monkeypatch):` |

---

### Module: `tests/test_worm_db_enforcement.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `19` | Warning | PY_TYPING | Missing return type hint for async function 'test_nce_app_worm_privilege_enforcement' | `async def test_nce_app_worm_privilege_enforcement():` |

---

### Module: `tests/test_worm_probe.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `37` | Warning | PY_TYPING | Missing return type hint for async function 'test_worm_update_denied_delete_denied' | `async def test_worm_update_denied_delete_denied():` |
| `62` | Warning | PY_TYPING | Missing return type hint for async function 'test_worm_update_succeeds_raises_runtime_error' | `async def test_worm_update_succeeds_raises_runtime_error():` |
| `74` | Warning | PY_TYPING | Missing return type hint for async function 'test_worm_delete_succeeds_raises_runtime_error' | `async def test_worm_delete_succeeds_raises_runtime_error():` |
| `87` | Warning | PY_TYPING | Missing return type hint for async function 'test_worm_both_succeed_raises_on_update_first' | `async def test_worm_both_succeed_raises_on_update_first():` |
| `102` | Warning | PY_TYPING | Missing return type hint for async function 'test_table_missing_propagates_error' | `async def test_table_missing_propagates_error():` |
| `112` | Warning | PY_TYPING | Missing return type hint for async function 'test_unexpected_postgres_error_propagates' | `async def test_unexpected_postgres_error_propagates():` |
| `127` | Warning | PY_TYPING | Missing return type hint for async function 'test_probe_uses_where_false' | `async def test_probe_uses_where_false():` |
| `147` | Warning | PY_TYPING | Missing return type hint for function 'test_insufficient_privilege_is_expected_exception' | `def test_insufficient_privilege_is_expected_exception():` |

---

### Module: `tests/test_worm_registry.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `21` | Warning | PY_TYPING | Missing return type hint for function 'test_memory_salience_not_in_worm_tables' | `def test_memory_salience_not_in_worm_tables():` |
| `25` | Warning | PY_TYPING | Missing return type hint for function 'test_worm_tables_contains_expected_entries' | `def test_worm_tables_contains_expected_entries():` |
| `38` | Warning | PY_TYPING | Missing return type hint for async function 'test_worm_tables_db_role_cannot_update' | `async def test_worm_tables_db_role_cannot_update(pg_app_conn):` |
| `38` | Warning | PY_TYPING | Missing type hint for argument 'pg_app_conn' in async function 'test_worm_tables_db_role_cannot_update' | `async def test_worm_tables_db_role_cannot_update(pg_app_conn):` |
| `59` | Warning | PY_TYPING | Missing return type hint for async function 'test_worm_tables_db_role_cannot_delete' | `async def test_worm_tables_db_role_cannot_delete(pg_app_conn):` |
| `59` | Warning | PY_TYPING | Missing type hint for argument 'pg_app_conn' in async function 'test_worm_tables_db_role_cannot_delete' | `async def test_worm_tables_db_role_cannot_delete(pg_app_conn):` |

---

### Module: `tests/test_xml_entity_bomb.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `38` | Warning | PY_TYPING | Missing return type hint for async function 'test_billion_laughs_rejected' | `async def test_billion_laughs_rejected(self):` |
| `46` | Warning | PY_TYPING | Missing return type hint for async function 'test_xxe_rejected' | `async def test_xxe_rejected(self):` |
| `52` | Warning | PY_TYPING | Missing return type hint for async function 'test_safe_xml_parses_normally' | `async def test_safe_xml_parses_normally(self):` |
| `60` | Warning | PY_TYPING | Missing return type hint for function 'test_billion_laughs_returns_none' | `def test_billion_laughs_returns_none(self):` |
| `64` | Warning | PY_TYPING | Missing return type hint for function 'test_xxe_returns_none' | `def test_xxe_returns_none(self):` |
| `68` | Warning | PY_TYPING | Missing return type hint for function 'test_safe_xml_parses' | `def test_safe_xml_parses(self):` |
| `77` | Warning | PY_TYPING | Missing return type hint for function 'test_billion_laughs_falls_back_to_regex' | `def test_billion_laughs_falls_back_to_regex(self):` |
| `82` | Warning | PY_TYPING | Missing return type hint for function 'test_xxe_falls_back_to_regex' | `def test_xxe_falls_back_to_regex(self):` |
| `87` | Warning | PY_TYPING | Missing return type hint for function 'test_safe_xml_parses' | `def test_safe_xml_parses(self):` |

---

### Module: `tests/unit/test_atms.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `53` | Warning | PY_TYPING | Missing return type hint for function 'test_node_registration' | `def test_node_registration(self):` |
| `60` | Warning | PY_TYPING | Missing return type hint for function 'test_justification_creates_missing_nodes' | `def test_justification_creates_missing_nodes(self):` |
| `69` | Warning | PY_TYPING | Missing return type hint for function 'test_evaluate_premise_always_valid' | `def test_evaluate_premise_always_valid(self):` |
| `75` | Warning | PY_TYPING | Missing return type hint for function 'test_evaluate_derived_requires_justification' | `def test_evaluate_derived_requires_justification(self):` |
| `89` | Warning | PY_TYPING | Missing return type hint for function 'test_evaluate_and_justification' | `def test_evaluate_and_justification(self):` |
| `105` | Warning | PY_TYPING | Missing return type hint for function 'test_evaluate_or_justifications' | `def test_evaluate_or_justifications(self):` |
| `124` | Warning | PY_TYPING | Missing return type hint for function 'test_linear_cascade' | `def test_linear_cascade(self):` |
| `145` | Warning | PY_TYPING | Missing return type hint for function 'test_diamond_cascade_resilience' | `def test_diamond_cascade_resilience(self):` |
| `181` | Warning | PY_TYPING | Missing return type hint for function 'test_cycle_without_external_support' | `def test_cycle_without_external_support(self):` |
| `194` | Warning | PY_TYPING | Missing return type hint for function 'test_cycle_with_external_support_and_cascade' | `def test_cycle_with_external_support_and_cascade(self):` |
| `224` | Warning | PY_TYPING | Missing return type hint for function 'test_contradiction_invalidation' | `def test_contradiction_invalidation(self):` |
| `244` | Warning | PY_TYPING | Missing return type hint for function 'test_build_atms_from_causal_graph' | `def test_build_atms_from_causal_graph(self):` |
| `291` | Warning | PY_TYPING | Missing return type hint for function 'test_evaluate_300_tenants' | `def test_evaluate_300_tenants(self):` |

---

### Module: `tests/unit/test_causal.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `92` | Warning | PY_TYPING | Missing return type hint for function 'test_forward_types_correct' | `def test_forward_types_correct(self):` |
| `96` | Warning | PY_TYPING | Missing return type hint for function 'test_reverse_types_correct' | `def test_reverse_types_correct(self):` |
| `100` | Warning | PY_TYPING | Missing return type hint for function 'test_types_are_disjoint' | `def test_types_are_disjoint(self):` |
| `109` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_graph' | `def test_empty_graph(self):` |
| `114` | Warning | PY_TYPING | Missing return type hint for function 'test_single_edge_creates_two_nodes' | `def test_single_edge_creates_two_nodes(self):` |
| `120` | Warning | PY_TYPING | Missing return type hint for function 'test_multiple_edges_correct_node_count' | `def test_multiple_edges_correct_node_count(self):` |
| `124` | Warning | PY_TYPING | Missing return type hint for function 'test_outgoing_edges_correct' | `def test_outgoing_edges_correct(self):` |
| `131` | Warning | PY_TYPING | Missing return type hint for function 'test_incoming_edges_correct' | `def test_incoming_edges_correct(self):` |
| `137` | Warning | PY_TYPING | Missing return type hint for function 'test_no_edges_returns_empty_lists' | `def test_no_edges_returns_empty_lists(self):` |
| `142` | Warning | PY_TYPING | Missing return type hint for function 'test_get_node_returns_correct_type' | `def test_get_node_returns_correct_type(self):` |
| `149` | Warning | PY_TYPING | Missing return type hint for function 'test_get_node_missing_returns_none' | `def test_get_node_missing_returns_none(self):` |
| `153` | Warning | PY_TYPING | Missing return type hint for function 'test_node_type_source_wins_over_target' | `def test_node_type_source_wins_over_target(self):` |
| `174` | Warning | PY_TYPING | Missing return type hint for function 'test_node_type_deterministic_regardless_of_row_order' | `def test_node_type_deterministic_regardless_of_row_order(self):` |
| `197` | Warning | PY_TYPING | Missing return type hint for function 'test_direct_descendants' | `def test_direct_descendants(self):` |
| `204` | Warning | PY_TYPING | Missing return type hint for function 'test_leaf_has_no_descendants' | `def test_leaf_has_no_descendants(self):` |
| `208` | Warning | PY_TYPING | Missing return type hint for function 'test_ancestors_direct' | `def test_ancestors_direct(self):` |
| `214` | Warning | PY_TYPING | Missing return type hint for function 'test_ancestors_root_node_empty' | `def test_ancestors_root_node_empty(self):` |
| `218` | Warning | PY_TYPING | Missing return type hint for function 'test_fan_out_topology' | `def test_fan_out_topology(self):` |
| `222` | Warning | PY_TYPING | Missing return type hint for function 'test_diamond_topology_no_duplicates' | `def test_diamond_topology_no_duplicates(self):` |
| `236` | Warning | PY_TYPING | Missing return type hint for function 'test_connected_to_forward_propagation' | `def test_connected_to_forward_propagation(self):` |
| `243` | Warning | PY_TYPING | Missing return type hint for function 'test_depends_on_reverse_propagation' | `def test_depends_on_reverse_propagation(self):` |
| `254` | Warning | PY_TYPING | Missing return type hint for function 'test_depends_on_no_impact_on_dependency' | `def test_depends_on_no_impact_on_dependency(self):` |
| `261` | Warning | PY_TYPING | Missing return type hint for function 'test_powered_by_reverse_propagation' | `def test_powered_by_reverse_propagation(self):` |
| `269` | Warning | PY_TYPING | Missing return type hint for function 'test_host_application_forward_propagation' | `def test_host_application_forward_propagation(self):` |
| `276` | Warning | PY_TYPING | Missing return type hint for function 'test_transitive_depends_on' | `def test_transitive_depends_on(self):` |
| `287` | Warning | PY_TYPING | Missing return type hint for function 'test_mixed_edge_types_both_directions' | `def test_mixed_edge_types_both_directions(self):` |
| `298` | Warning | PY_TYPING | Missing return type hint for function 'test_leaf_node_not_impacted_by_itself' | `def test_leaf_node_not_impacted_by_itself(self):` |
| `303` | Warning | PY_TYPING | Missing return type hint for function 'test_isolated_node_impacts_nothing' | `def test_isolated_node_impacts_nothing(self):` |
| `314` | Warning | PY_TYPING | Missing return type hint for function 'test_mutilate_severs_forward_incoming_edge' | `def test_mutilate_severs_forward_incoming_edge(self):` |
| `320` | Warning | PY_TYPING | Missing return type hint for function 'test_mutilate_preserves_forward_outgoing_edge' | `def test_mutilate_preserves_forward_outgoing_edge(self):` |
| `328` | Warning | PY_TYPING | Missing return type hint for function 'test_mutilate_severs_reverse_outgoing_from_intervention' | `def test_mutilate_severs_reverse_outgoing_from_intervention(self):` |
| `336` | Warning | PY_TYPING | Missing return type hint for function 'test_mutilate_preserves_reverse_incoming_effect' | `def test_mutilate_preserves_reverse_incoming_effect(self):` |
| `348` | Warning | PY_TYPING | Missing return type hint for function 'test_mutilate_does_not_modify_original' | `def test_mutilate_does_not_modify_original(self):` |
| `353` | Warning | PY_TYPING | Missing return type hint for function 'test_mutilate_returns_new_instance' | `def test_mutilate_returns_new_instance(self):` |
| `357` | Warning | PY_TYPING | Missing return type hint for function 'test_mutilate_nonexistent_node_is_no_op' | `def test_mutilate_nonexistent_node_is_no_op(self):` |
| `362` | Warning | PY_TYPING | Missing return type hint for function 'test_mutilate_preserves_unrelated_edges' | `def test_mutilate_preserves_unrelated_edges(self):` |
| `374` | Warning | PY_TYPING | Missing return type hint for function 'test_direct_path' | `def test_direct_path(self):` |
| `378` | Warning | PY_TYPING | Missing return type hint for function 'test_two_hop_path' | `def test_two_hop_path(self):` |
| `383` | Warning | PY_TYPING | Missing return type hint for function 'test_diamond_two_paths' | `def test_diamond_two_paths(self):` |
| `387` | Warning | PY_TYPING | Missing return type hint for function 'test_no_path_returns_empty' | `def test_no_path_returns_empty(self):` |
| `391` | Warning | PY_TYPING | Missing return type hint for function 'test_same_source_target_returns_empty' | `def test_same_source_target_returns_empty(self):` |
| `395` | Warning | PY_TYPING | Missing return type hint for function 'test_paths_sorted_deterministically' | `def test_paths_sorted_deterministically(self):` |
| `399` | Warning | PY_TYPING | Missing return type hint for function 'test_max_depth_limits_paths' | `def test_max_depth_limits_paths(self):` |
| `410` | Warning | PY_TYPING | Missing return type hint for function 'test_connected_to_forward_path' | `def test_connected_to_forward_path(self):` |
| `416` | Warning | PY_TYPING | Missing return type hint for function 'test_depends_on_reverse_path' | `def test_depends_on_reverse_path(self):` |
| `424` | Warning | PY_TYPING | Missing return type hint for function 'test_powered_by_reverse_path' | `def test_powered_by_reverse_path(self):` |
| `430` | Warning | PY_TYPING | Missing return type hint for function 'test_no_causal_path_in_wrong_direction' | `def test_no_causal_path_in_wrong_direction(self):` |
| `435` | Warning | PY_TYPING | Missing return type hint for function 'test_mixed_type_transitive_path' | `def test_mixed_type_transitive_path(self):` |
| `449` | Warning | PY_TYPING | Missing return type hint for function 'test_causal_paths_sorted_deterministically' | `def test_causal_paths_sorted_deterministically(self):` |
| `467` | Warning | PY_TYPING | Missing return type hint for function 'test_no_last_verified_returns_raw_confidence' | `def test_no_last_verified_returns_raw_confidence(self):` |
| `471` | Warning | PY_TYPING | Missing return type hint for function 'test_fresh_edge_minimal_decay' | `def test_fresh_edge_minimal_decay(self):` |
| `475` | Warning | PY_TYPING | Missing return type hint for function 'test_old_edge_significantly_decayed' | `def test_old_edge_significantly_decayed(self):` |
| `479` | Warning | PY_TYPING | Missing return type hint for function 'test_confidence_never_below_min' | `def test_confidence_never_below_min(self):` |
| `483` | Warning | PY_TYPING | Missing return type hint for function 'test_naive_datetime_normalised_to_utc' | `def test_naive_datetime_normalised_to_utc(self):` |
| `495` | Warning | PY_TYPING | Missing return type hint for function 'test_path_confidence_single_edge' | `def test_path_confidence_single_edge(self):` |
| `499` | Warning | PY_TYPING | Missing return type hint for function 'test_path_confidence_two_edges' | `def test_path_confidence_two_edges(self):` |
| `504` | Warning | PY_TYPING | Missing return type hint for function 'test_path_confidence_empty_returns_zero' | `def test_path_confidence_empty_returns_zero(self):` |
| `507` | Warning | PY_TYPING | Missing return type hint for function 'test_combine_single_path' | `def test_combine_single_path(self):` |
| `510` | Warning | PY_TYPING | Missing return type hint for function 'test_combine_two_independent_paths' | `def test_combine_two_independent_paths(self):` |
| `513` | Warning | PY_TYPING | Missing return type hint for function 'test_combine_empty_returns_zero' | `def test_combine_empty_returns_zero(self):` |
| `516` | Warning | PY_TYPING | Missing return type hint for function 'test_combine_certain_path_gives_one' | `def test_combine_certain_path_gives_one(self):` |
| `519` | Warning | PY_TYPING | Missing return type hint for function 'test_combine_zero_path_ignored' | `def test_combine_zero_path_ignored(self):` |
| `528` | Warning | PY_TYPING | Missing return type hint for function 'test_single_chain_direct_and_transitive' | `def test_single_chain_direct_and_transitive(self):` |
| `535` | Warning | PY_TYPING | Missing return type hint for function 'test_leaf_node_has_no_impact' | `def test_leaf_node_has_no_impact(self):` |
| `540` | Warning | PY_TYPING | Missing return type hint for function 'test_diamond_topology_two_paths' | `def test_diamond_topology_two_paths(self):` |
| `549` | Warning | PY_TYPING | Missing return type hint for function 'test_directly_impacted_is_one_hop' | `def test_directly_impacted_is_one_hop(self):` |
| `557` | Warning | PY_TYPING | Missing return type hint for function 'test_result_is_intervention_result_namedtuple' | `def test_result_is_intervention_result_namedtuple(self):` |
| `564` | Warning | PY_TYPING | Missing return type hint for function 'test_missing_node_raises_key_error' | `def test_missing_node_raises_key_error(self):` |
| `569` | Warning | PY_TYPING | Missing return type hint for function 'test_probability_matrix_values_in_range' | `def test_probability_matrix_values_in_range(self):` |
| `575` | Warning | PY_TYPING | Missing return type hint for function 'test_determinism' | `def test_determinism(self):` |
| `583` | Warning | PY_TYPING | Missing return type hint for function 'test_higher_confidence_higher_impact' | `def test_higher_confidence_higher_impact(self):` |
| `591` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_graph_raises_key_error' | `def test_empty_graph_raises_key_error(self):` |
| `602` | Warning | PY_TYPING | Missing return type hint for function 'test_depends_on_correct_impact_direction' | `def test_depends_on_correct_impact_direction(self):` |
| `610` | Warning | PY_TYPING | Missing return type hint for function 'test_depends_on_no_reverse_impact' | `def test_depends_on_no_reverse_impact(self):` |
| `617` | Warning | PY_TYPING | Missing return type hint for function 'test_powered_by_correct_impact_direction' | `def test_powered_by_correct_impact_direction(self):` |
| `625` | Warning | PY_TYPING | Missing return type hint for function 'test_transitive_depends_on_chain' | `def test_transitive_depends_on_chain(self):` |
| `639` | Warning | PY_TYPING | Missing return type hint for function 'test_multiple_dependents_on_single_node' | `def test_multiple_dependents_on_single_node(self):` |
| `656` | Warning | PY_TYPING | Missing return type hint for function 'test_forward_and_reverse_both_impacted' | `def test_forward_and_reverse_both_impacted(self):` |
| `669` | Warning | PY_TYPING | Missing return type hint for function 'test_cascaded_mixed_types' | `def test_cascaded_mixed_types(self):` |
| `687` | Warning | PY_TYPING | Missing return type hint for function 'test_confounding_path_detected' | `def test_confounding_path_detected(self):` |
| `702` | Warning | PY_TYPING | Missing return type hint for function 'test_confounding_path_has_no_source_field' | `def test_confounding_path_has_no_source_field(self):` |
| `713` | Warning | PY_TYPING | Missing return type hint for function 'test_no_confounders_when_root_node' | `def test_no_confounders_when_root_node(self):` |
| `724` | Warning | PY_TYPING | Missing return type hint for function 'test_direct_impact_hop_distance_one' | `def test_direct_impact_hop_distance_one(self):` |
| `729` | Warning | PY_TYPING | Missing return type hint for function 'test_transitive_impact_hop_distance_two' | `def test_transitive_impact_hop_distance_two(self):` |
| `735` | Warning | PY_TYPING | Missing return type hint for function 'test_hop_distance_two_for_reverse_transitive' | `def test_hop_distance_two_for_reverse_transitive(self):` |
| `747` | Warning | PY_TYPING | Missing return type hint for function 'test_paths_count_correct_for_diamond' | `def test_paths_count_correct_for_diamond(self):` |
| `756` | Warning | PY_TYPING | Missing return type hint for function 'test_directly_impacted_sorted_by_probability_desc' | `def test_directly_impacted_sorted_by_probability_desc(self):` |
| `768` | Warning | PY_TYPING | Missing return type hint for function 'test_soft_deleted_row_handling' | `def test_soft_deleted_row_handling(self):` |
| `775` | Warning | PY_TYPING | Missing return type hint for function 'test_prune_result_non_negative_counts' | `def test_prune_result_non_negative_counts(self):` |
| `781` | Warning | PY_TYPING | Missing return type hint for function 'test_probability_matrix_excludes_intervention_node' | `def test_probability_matrix_excludes_intervention_node(self):` |

---

### Module: `tests/unit/test_chrono.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `51` | Warning | PY_TYPING | Missing return type hint for function 'test_branch_timeline_activates_and_cleans_up' | `def test_branch_timeline_activates_and_cleans_up(self):` |
| `66` | Warning | PY_TYPING | Missing return type hint for async function 'test_contextvar_isolation_across_async_tasks' | `async def test_contextvar_isolation_across_async_tasks(self):` |
| `71` | Warning | PY_TYPING | Missing return type hint for async function 'worker1' | `async def worker1():` |
| `77` | Warning | PY_TYPING | Missing return type hint for async function 'worker2' | `async def worker2():` |
| `91` | Warning | PY_TYPING | Missing return type hint for function 'test_node_addition_and_modification' | `def test_node_addition_and_modification(self):` |
| `111` | Warning | PY_TYPING | Missing return type hint for function 'test_edge_addition_and_modification' | `def test_edge_addition_and_modification(self):` |
| `147` | Warning | PY_TYPING | Missing return type hint for function 'test_node_and_edge_deletions' | `def test_node_and_edge_deletions(self):` |
| `168` | Warning | PY_TYPING | Missing return type hint for function 'test_evaluation_under_chrono_branch' | `def test_evaluation_under_chrono_branch(self):` |

---

### Module: `tests/unit/test_netbox_circuits.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `36` | Warning | PY_TYPING | Missing return type hint for async function 'test_evaluate_and_escalate_generates_ticket' | `async def test_evaluate_and_escalate_generates_ticket(self):` |
| `116` | Warning | PY_TYPING | Missing return type hint for async function 'test_evaluate_and_escalate_no_tickets_when_no_causal_impact' | `async def test_evaluate_and_escalate_no_tickets_when_no_causal_impact(self):` |

---

### Module: `tests/unit/test_netbox_contacts.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `65` | Warning | PY_TYPING | Missing return type hint for async function 'test_fetch_contacts' | `async def test_fetch_contacts(self, monkeypatch):` |
| `65` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_fetch_contacts' | `async def test_fetch_contacts(self, monkeypatch):` |
| `85` | Warning | PY_TYPING | Missing return type hint for async function 'test_ensure_on_call_schema' | `async def test_ensure_on_call_schema(self):` |
| `96` | Warning | PY_TYPING | Missing return type hint for async function 'test_evaluate_contact_stress_report' | `async def test_evaluate_contact_stress_report(self):` |
| `116` | Warning | PY_TYPING | Missing return type hint for async function 'test_sync_contacts_and_update_oncall_burnout_trigger' | `async def test_sync_contacts_and_update_oncall_burnout_trigger(self, monkeypatch):` |
| `116` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_sync_contacts_and_update_oncall_burnout_trigger' | `async def test_sync_contacts_and_update_oncall_burnout_trigger(self, monkeypatch):` |
| `135` | Warning | PY_TYPING | Missing return type hint for async function 'mock_fetch' | `async def mock_fetch(query, *args):` |
| `135` | Warning | PY_TYPING | Missing type hint for argument 'query' in async function 'mock_fetch' | `async def mock_fetch(query, *args):` |

---

### Module: `tests/unit/test_netbox_discovery.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `397` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_reconcile_custom_default_interface_type' | `async def test_reconcile_custom_default_interface_type(self, monkeypatch) -> None:` |

---

### Module: `tests/unit/test_neuromorphic.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `330` | Warning | PY_TYPING | Missing return type hint for async function 'embed_fn' | `async def embed_fn(q):` |
| `330` | Warning | PY_TYPING | Missing type hint for argument 'q' in async function 'embed_fn' | `async def embed_fn(q):` |
| `393` | Warning | PY_TYPING | Missing return type hint for async function 'embed_fn' | `async def embed_fn(q):` |
| `393` | Warning | PY_TYPING | Missing type hint for argument 'q' in async function 'embed_fn' | `async def embed_fn(q):` |
| `455` | Warning | PY_TYPING | Missing return type hint for async function 'embed_fn' | `async def embed_fn(q):` |
| `455` | Warning | PY_TYPING | Missing type hint for argument 'q' in async function 'embed_fn' | `async def embed_fn(q):` |
| `511` | Warning | PY_TYPING | Missing return type hint for async function 'embed_fn' | `async def embed_fn(q):` |
| `511` | Warning | PY_TYPING | Missing type hint for argument 'q' in async function 'embed_fn' | `async def embed_fn(q):` |
| `561` | Warning | PY_TYPING | Missing return type hint for async function 'embed_fn' | `async def embed_fn(q):` |
| `561` | Warning | PY_TYPING | Missing type hint for argument 'q' in async function 'embed_fn' | `async def embed_fn(q):` |

---

### Module: `tests/unit/test_orchestrators_init.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `45` | Warning | PY_TYPING | Missing return type hint for function '_fresh_orchestrators' | `def _fresh_orchestrators():` |

---

### Module: `tests/unit/test_pruning.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `88` | Warning | PY_TYPING | Missing return type hint for function '_make_mock_pool_and_connection' | `def _make_mock_pool_and_connection():` |
| `104` | Warning | PY_TYPING | Missing return type hint for async function '__aenter__' | `async def __aenter__(self):` |
| `106` | Warning | PY_TYPING | Missing return type hint for async function '__aexit__' | `async def __aexit__(self, *args):` |
| `117` | Warning | PY_TYPING | Missing return type hint for async function '_acquire' | `async def _acquire():` |
| `120` | Warning | PY_TYPING | Missing return type hint for async function '_release' | `async def _release(_c):` |
| `120` | Warning | PY_TYPING | Missing type hint for argument '_c' in async function '_release' | `async def _release(_c):` |
| `138` | Warning | PY_TYPING | Missing return type hint for function 'test_allowed_table_names_are_non_empty' | `def test_allowed_table_names_are_non_empty(self):` |
| `141` | Warning | PY_TYPING | Missing return type hint for function 'test_allowed_column_names_include_vector_columns' | `def test_allowed_column_names_include_vector_columns(self):` |
| `145` | Warning | PY_TYPING | Missing return type hint for function 'test_allowed_zero_expressions_include_null_and_vector' | `def test_allowed_zero_expressions_include_null_and_vector(self):` |
| `149` | Warning | PY_TYPING | Missing return type hint for function 'test_guard_table_passes_for_known_table' | `def test_guard_table_passes_for_known_table(self):` |
| `152` | Warning | PY_TYPING | Missing return type hint for function 'test_guard_table_raises_for_unknown_table' | `def test_guard_table_raises_for_unknown_table(self):` |
| `156` | Warning | PY_TYPING | Missing return type hint for function 'test_guard_column_passes_for_known_column' | `def test_guard_column_passes_for_known_column(self):` |
| `159` | Warning | PY_TYPING | Missing return type hint for function 'test_guard_column_raises_for_unknown_column' | `def test_guard_column_raises_for_unknown_column(self):` |
| `163` | Warning | PY_TYPING | Missing return type hint for function 'test_guard_zero_expr_passes_for_null' | `def test_guard_zero_expr_passes_for_null(self):` |
| `166` | Warning | PY_TYPING | Missing return type hint for function 'test_guard_zero_expr_raises_for_arbitrary_sql' | `def test_guard_zero_expr_raises_for_arbitrary_sql(self):` |
| `176` | Warning | PY_TYPING | Missing return type hint for function 'test_dry_run_rollback_is_not_asyncpg_error' | `def test_dry_run_rollback_is_not_asyncpg_error(self):` |
| `182` | Warning | PY_TYPING | Missing return type hint for async function 'test_dry_run_returns_prune_result' | `async def test_dry_run_returns_prune_result(self, namespace_id):` |
| `182` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_dry_run_returns_prune_result' | `async def test_dry_run_returns_prune_result(self, namespace_id):` |
| `190` | Warning | PY_TYPING | Missing return type hint for async function 'test_dry_run_consistency_check_runs_before_rollback' | `async def test_dry_run_consistency_check_runs_before_rollback(self, namespace_id):` |
| `190` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_dry_run_consistency_check_runs_before_rollback' | `async def test_dry_run_consistency_check_runs_before_rollback(self, namespace_id):` |
| `197` | Warning | PY_TYPING | Missing return type hint for async function 'test_dry_run_captures_in_memory_counts' | `async def test_dry_run_captures_in_memory_counts(self, namespace_id):` |
| `197` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_dry_run_captures_in_memory_counts' | `async def test_dry_run_captures_in_memory_counts(self, namespace_id):` |
| `205` | Warning | PY_TYPING | Missing return type hint for async function 'test_wet_run_does_not_raise' | `async def test_wet_run_does_not_raise(self, namespace_id):` |
| `205` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_wet_run_does_not_raise' | `async def test_wet_run_does_not_raise(self, namespace_id):` |
| `218` | Warning | PY_TYPING | Missing return type hint for async function 'test_soft_delete_sql_sets_valid_to' | `async def test_soft_delete_sql_sets_valid_to(self, namespace_id):` |
| `218` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_soft_delete_sql_sets_valid_to' | `async def test_soft_delete_sql_sets_valid_to(self, namespace_id):` |
| `226` | Warning | PY_TYPING | Missing return type hint for async function 'test_soft_delete_targets_only_non_deleted_rows' | `async def test_soft_delete_targets_only_non_deleted_rows(self, namespace_id):` |
| `226` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_soft_delete_targets_only_non_deleted_rows' | `async def test_soft_delete_targets_only_non_deleted_rows(self, namespace_id):` |
| `234` | Warning | PY_TYPING | Missing return type hint for async function 'test_soft_delete_all_four_tables' | `async def test_soft_delete_all_four_tables(self, namespace_id):` |
| `234` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_soft_delete_all_four_tables' | `async def test_soft_delete_all_four_tables(self, namespace_id):` |
| `242` | Warning | PY_TYPING | Missing return type hint for async function 'test_soft_delete_counts_sum_correctly' | `async def test_soft_delete_counts_sum_correctly(self, namespace_id):` |
| `242` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_soft_delete_counts_sum_correctly' | `async def test_soft_delete_counts_sum_correctly(self, namespace_id):` |
| `256` | Warning | PY_TYPING | Missing return type hint for async function 'test_embedding_zero_filled_to_null' | `async def test_embedding_zero_filled_to_null(self, namespace_id):` |
| `256` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_embedding_zero_filled_to_null' | `async def test_embedding_zero_filled_to_null(self, namespace_id):` |
| `265` | Warning | PY_TYPING | Missing return type hint for async function 'test_empathic_tensor_zero_filled_to_zero_vector' | `async def test_empathic_tensor_zero_filled_to_zero_vector(self, namespace_id):` |
| `265` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_empathic_tensor_zero_filled_to_zero_vector' | `async def test_empathic_tensor_zero_filled_to_zero_vector(self, namespace_id):` |
| `274` | Warning | PY_TYPING | Missing return type hint for async function 'test_vector_zero_fill_targets_soft_deleted_rows_only' | `async def test_vector_zero_fill_targets_soft_deleted_rows_only(self, namespace_id):` |
| `274` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_vector_zero_fill_targets_soft_deleted_rows_only' | `async def test_vector_zero_fill_targets_soft_deleted_rows_only(self, namespace_id):` |
| `282` | Warning | PY_TYPING | Missing return type hint for async function 'test_vectors_zeroed_count_is_sum_of_both_columns' | `async def test_vectors_zeroed_count_is_sum_of_both_columns(self, namespace_id):` |
| `282` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_vectors_zeroed_count_is_sum_of_both_columns' | `async def test_vectors_zeroed_count_is_sum_of_both_columns(self, namespace_id):` |
| `296` | Warning | PY_TYPING | Missing return type hint for async function 'test_text_nullification_total_count' | `async def test_text_nullification_total_count(self, namespace_id):` |
| `296` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_text_nullification_total_count' | `async def test_text_nullification_total_count(self, namespace_id):` |
| `304` | Warning | PY_TYPING | Missing return type hint for async function 'test_memories_value_column_nullified' | `async def test_memories_value_column_nullified(self, namespace_id):` |
| `304` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_memories_value_column_nullified' | `async def test_memories_value_column_nullified(self, namespace_id):` |
| `313` | Warning | PY_TYPING | Missing return type hint for async function 'test_event_log_plaintext_secret_nullified' | `async def test_event_log_plaintext_secret_nullified(self, namespace_id):` |
| `313` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_event_log_plaintext_secret_nullified' | `async def test_event_log_plaintext_secret_nullified(self, namespace_id):` |
| `328` | Warning | PY_TYPING | Missing return type hint for async function 'test_consistency_passes_when_no_orphans' | `async def test_consistency_passes_when_no_orphans(self, namespace_id):` |
| `328` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_consistency_passes_when_no_orphans' | `async def test_consistency_passes_when_no_orphans(self, namespace_id):` |
| `336` | Warning | PY_TYPING | Missing return type hint for async function 'test_consistency_fails_on_orphaned_embeddings' | `async def test_consistency_fails_on_orphaned_embeddings(self, namespace_id):` |
| `336` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_consistency_fails_on_orphaned_embeddings' | `async def test_consistency_fails_on_orphaned_embeddings(self, namespace_id):` |
| `344` | Warning | PY_TYPING | Missing return type hint for async function 'test_consistency_fails_on_non_zero_tensors' | `async def test_consistency_fails_on_non_zero_tensors(self, namespace_id):` |
| `344` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_consistency_fails_on_non_zero_tensors' | `async def test_consistency_fails_on_non_zero_tensors(self, namespace_id):` |
| `352` | Warning | PY_TYPING | Missing return type hint for async function 'test_consistency_uses_fetchval_not_execute' | `async def test_consistency_uses_fetchval_not_execute(self, namespace_id):` |
| `352` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_consistency_uses_fetchval_not_execute' | `async def test_consistency_uses_fetchval_not_execute(self, namespace_id):` |
| `362` | Warning | PY_TYPING | Missing return type hint for async function 'test_consistency_sql_scopes_to_namespace' | `async def test_consistency_sql_scopes_to_namespace(self, namespace_id):` |
| `362` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_consistency_sql_scopes_to_namespace' | `async def test_consistency_sql_scopes_to_namespace(self, namespace_id):` |
| `376` | Warning | PY_TYPING | Missing return type hint for async function 'test_audit_log_entry_uuid_is_set' | `async def test_audit_log_entry_uuid_is_set(self, namespace_id):` |
| `376` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_audit_log_entry_uuid_is_set' | `async def test_audit_log_entry_uuid_is_set(self, namespace_id):` |
| `383` | Warning | PY_TYPING | Missing return type hint for async function 'test_audit_log_insert_is_last_execute_call' | `async def test_audit_log_insert_is_last_execute_call(self, namespace_id):` |
| `383` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_audit_log_insert_is_last_execute_call' | `async def test_audit_log_insert_is_last_execute_call(self, namespace_id):` |
| `391` | Warning | PY_TYPING | Missing return type hint for async function 'test_audit_log_uses_on_conflict_do_nothing' | `async def test_audit_log_uses_on_conflict_do_nothing(self, namespace_id):` |
| `391` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_audit_log_uses_on_conflict_do_nothing' | `async def test_audit_log_uses_on_conflict_do_nothing(self, namespace_id):` |
| `400` | Warning | PY_TYPING | Missing return type hint for async function 'test_audit_log_receives_metadata_with_counts' | `async def test_audit_log_receives_metadata_with_counts(self, namespace_id):` |
| `400` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_audit_log_receives_metadata_with_counts' | `async def test_audit_log_receives_metadata_with_counts(self, namespace_id):` |
| `418` | Warning | PY_TYPING | Missing return type hint for async function 'test_sla_passes_for_fast_operation' | `async def test_sla_passes_for_fast_operation(self, namespace_id):` |
| `418` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_sla_passes_for_fast_operation' | `async def test_sla_passes_for_fast_operation(self, namespace_id):` |
| `426` | Warning | PY_TYPING | Missing return type hint for async function 'test_sla_field_always_present_on_prune_result' | `async def test_sla_field_always_present_on_prune_result(self, namespace_id):` |
| `426` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_sla_field_always_present_on_prune_result' | `async def test_sla_field_always_present_on_prune_result(self, namespace_id):` |
| `433` | Warning | PY_TYPING | Missing return type hint for async function 'test_duration_seconds_is_non_negative' | `async def test_duration_seconds_is_non_negative(self, namespace_id):` |
| `433` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_duration_seconds_is_non_negative' | `async def test_duration_seconds_is_non_negative(self, namespace_id):` |
| `446` | Warning | PY_TYPING | Missing return type hint for async function 'test_batch_returns_one_result_per_namespace' | `async def test_batch_returns_one_result_per_namespace(self):` |
| `455` | Warning | PY_TYPING | Missing return type hint for async function 'test_batch_results_ordered_by_input' | `async def test_batch_results_ordered_by_input(self):` |
| `464` | Warning | PY_TYPING | Missing return type hint for async function 'test_batch_all_sla_passed_for_mock_operations' | `async def test_batch_all_sla_passed_for_mock_operations(self):` |
| `477` | Warning | PY_TYPING | Missing return type hint for function 'test_is_namedtuple_with_required_fields' | `def test_is_namedtuple_with_required_fields(self, namespace_id):` |
| `477` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in function 'test_is_namedtuple_with_required_fields' | `def test_is_namedtuple_with_required_fields(self, namespace_id):` |
| `492` | Warning | PY_TYPING | Missing return type hint for async function 'test_soft_deleted_rows_non_negative' | `async def test_soft_deleted_rows_non_negative(self, namespace_id):` |
| `492` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_soft_deleted_rows_non_negative' | `async def test_soft_deleted_rows_non_negative(self, namespace_id):` |
| `498` | Warning | PY_TYPING | Missing return type hint for async function 'test_vectors_zeroed_non_negative' | `async def test_vectors_zeroed_non_negative(self, namespace_id):` |
| `498` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_vectors_zeroed_non_negative' | `async def test_vectors_zeroed_non_negative(self, namespace_id):` |
| `504` | Warning | PY_TYPING | Missing return type hint for async function 'test_text_columns_nullified_non_negative' | `async def test_text_columns_nullified_non_negative(self, namespace_id):` |
| `504` | Warning | PY_TYPING | Missing type hint for argument 'namespace_id' in async function 'test_text_columns_nullified_non_negative' | `async def test_text_columns_nullified_non_negative(self, namespace_id):` |

---

### Module: `tests/unit/test_synthesis.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `28` | Warning | PY_TYPING | Missing return type hint for function 'mock_pg_conn' | `def mock_pg_conn():` |
| `36` | Warning | PY_TYPING | Missing return type hint for function 'engine' | `def engine():` |
| `44` | Warning | PY_TYPING | Missing return type hint for async function 'test_fetch_historical_incidents' | `async def test_fetch_historical_incidents(self, engine, mock_pg_conn):` |
| `44` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'test_fetch_historical_incidents' | `async def test_fetch_historical_incidents(self, engine, mock_pg_conn):` |
| `44` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_conn' in async function 'test_fetch_historical_incidents' | `async def test_fetch_historical_incidents(self, engine, mock_pg_conn):` |
| `81` | Warning | PY_TYPING | Missing return type hint for async function 'test_fetch_netbox_mtbf_success' | `async def test_fetch_netbox_mtbf_success(self, engine, mock_pg_conn):` |
| `81` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'test_fetch_netbox_mtbf_success' | `async def test_fetch_netbox_mtbf_success(self, engine, mock_pg_conn):` |
| `81` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_conn' in async function 'test_fetch_netbox_mtbf_success' | `async def test_fetch_netbox_mtbf_success(self, engine, mock_pg_conn):` |
| `92` | Warning | PY_TYPING | Missing return type hint for async function 'test_fetch_netbox_mtbf_fallback_on_db_error' | `async def test_fetch_netbox_mtbf_fallback_on_db_error(self, engine, mock_pg_conn):` |
| `92` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'test_fetch_netbox_mtbf_fallback_on_db_error' | `async def test_fetch_netbox_mtbf_fallback_on_db_error(self, engine, mock_pg_conn):` |
| `92` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_conn' in async function 'test_fetch_netbox_mtbf_fallback_on_db_error' | `async def test_fetch_netbox_mtbf_fallback_on_db_error(self, engine, mock_pg_conn):` |
| `100` | Warning | PY_TYPING | Missing return type hint for function 'test_resolve_mtbf_for_node' | `def test_resolve_mtbf_for_node(self, engine):` |
| `100` | Warning | PY_TYPING | Missing type hint for argument 'engine' in function 'test_resolve_mtbf_for_node' | `def test_resolve_mtbf_for_node(self, engine):` |
| `114` | Warning | PY_TYPING | Missing return type hint for async function 'test_generate_predictive_fault_nodes' | `async def test_generate_predictive_fault_nodes(self, engine, mock_pg_conn, monkeypatch):` |
| `114` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'test_generate_predictive_fault_nodes' | `async def test_generate_predictive_fault_nodes(self, engine, mock_pg_conn, monkeypatch):` |
| `114` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_conn' in async function 'test_generate_predictive_fault_nodes' | `async def test_generate_predictive_fault_nodes(self, engine, mock_pg_conn, monkeypatch):` |
| `114` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in async function 'test_generate_predictive_fault_nodes' | `async def test_generate_predictive_fault_nodes(self, engine, mock_pg_conn, monkeypatch):` |
| `168` | Warning | PY_TYPING | Missing return type hint for async function 'test_sync_predictive_nodes_to_topology' | `async def test_sync_predictive_nodes_to_topology(self, engine, mock_pg_conn):` |
| `168` | Warning | PY_TYPING | Missing type hint for argument 'engine' in async function 'test_sync_predictive_nodes_to_topology' | `async def test_sync_predictive_nodes_to_topology(self, engine, mock_pg_conn):` |
| `168` | Warning | PY_TYPING | Missing type hint for argument 'mock_pg_conn' in async function 'test_sync_predictive_nodes_to_topology' | `async def test_sync_predictive_nodes_to_topology(self, engine, mock_pg_conn):` |

---

### Module: `tests/unit/test_temporal.py`
| Line | Severity | Rule ID | Description | Code Snippet Context |
| :--- | :--- | :--- | :--- | :--- |
| `54` | Warning | PY_TYPING | Missing return type hint for function 'test_incident_stability' | `def test_incident_stability(self):` |
| `57` | Warning | PY_TYPING | Missing return type hint for function 'test_configuration_stability' | `def test_configuration_stability(self):` |
| `60` | Warning | PY_TYPING | Missing return type hint for function 'test_topology_edge_stability' | `def test_topology_edge_stability(self):` |
| `63` | Warning | PY_TYPING | Missing return type hint for function 'test_consolidated_stability' | `def test_consolidated_stability(self):` |
| `66` | Warning | PY_TYPING | Missing return type hint for function 'test_code_chunk_stability' | `def test_code_chunk_stability(self):` |
| `69` | Warning | PY_TYPING | Missing return type hint for function 'test_episodic_stability' | `def test_episodic_stability(self):` |
| `72` | Warning | PY_TYPING | Missing return type hint for function 'test_string_alias_incident' | `def test_string_alias_incident(self):` |
| `75` | Warning | PY_TYPING | Missing return type hint for function 'test_string_alias_configuration' | `def test_string_alias_configuration(self):` |
| `78` | Warning | PY_TYPING | Missing return type hint for function 'test_unknown_class_defaults_to_episodic' | `def test_unknown_class_defaults_to_episodic(self):` |
| `88` | Warning | PY_TYPING | Missing return type hint for function 'test_zero_elapsed_returns_one' | `def test_zero_elapsed_returns_one(self):` |
| `93` | Warning | PY_TYPING | Missing return type hint for function 'test_incident_at_stability_boundary' | `def test_incident_at_stability_boundary(self):` |
| `101` | Warning | PY_TYPING | Missing return type hint for function 'test_configuration_at_stability_boundary' | `def test_configuration_at_stability_boundary(self):` |
| `105` | Warning | PY_TYPING | Missing return type hint for function 'test_topology_edge_at_stability_boundary' | `def test_topology_edge_at_stability_boundary(self):` |
| `109` | Warning | PY_TYPING | Missing return type hint for function 'test_code_chunk_at_stability_boundary' | `def test_code_chunk_at_stability_boundary(self):` |
| `113` | Warning | PY_TYPING | Missing return type hint for function 'test_retention_decreases_monotonically' | `def test_retention_decreases_monotonically(self):` |
| `119` | Warning | PY_TYPING | Missing return type hint for function 'test_retention_never_below_zero' | `def test_retention_never_below_zero(self):` |
| `124` | Warning | PY_TYPING | Missing return type hint for function 'test_retention_never_above_one' | `def test_retention_never_above_one(self):` |
| `128` | Warning | PY_TYPING | Missing return type hint for function 'test_returns_retention_result_namedtuple' | `def test_returns_retention_result_namedtuple(self):` |
| `132` | Warning | PY_TYPING | Missing return type hint for function 'test_naive_datetime_treated_as_utc' | `def test_naive_datetime_treated_as_utc(self):` |
| `138` | Warning | PY_TYPING | Missing return type hint for function 'test_future_timestamp_raises_value_error' | `def test_future_timestamp_raises_value_error(self):` |
| `143` | Warning | PY_TYPING | Missing return type hint for function 'test_string_memory_class_accepted' | `def test_string_memory_class_accepted(self):` |
| `153` | Warning | PY_TYPING | Missing return type hint for function 'test_prune_threshold_value' | `def test_prune_threshold_value(self):` |
| `156` | Warning | PY_TYPING | Missing return type hint for function 'test_incident_below_threshold_at_prune_age' | `def test_incident_below_threshold_at_prune_age(self):` |
| `163` | Warning | PY_TYPING | Missing return type hint for function 'test_incident_above_threshold_before_prune_age' | `def test_incident_above_threshold_before_prune_age(self):` |
| `169` | Warning | PY_TYPING | Missing return type hint for function 'test_configuration_prune_age' | `def test_configuration_prune_age(self):` |
| `175` | Warning | PY_TYPING | Missing return type hint for function 'test_topology_edge_prune_age' | `def test_topology_edge_prune_age(self):` |
| `181` | Warning | PY_TYPING | Missing return type hint for function 'test_topology_edge_not_prune_eligible_at_half_threshold' | `def test_topology_edge_not_prune_eligible_at_half_threshold(self):` |
| `187` | Warning | PY_TYPING | Missing return type hint for function 'test_fresh_memory_never_prune_eligible' | `def test_fresh_memory_never_prune_eligible(self):` |
| `197` | Warning | PY_TYPING | Missing return type hint for function 'test_age_zero_returns_one' | `def test_age_zero_returns_one(self):` |
| `200` | Warning | PY_TYPING | Missing return type hint for function 'test_age_equals_stability' | `def test_age_equals_stability(self):` |
| `208` | Warning | PY_TYPING | Missing return type hint for function 'test_negative_age_raises' | `def test_negative_age_raises(self):` |
| `212` | Warning | PY_TYPING | Missing return type hint for function 'test_string_class' | `def test_string_class(self):` |
| `221` | Warning | PY_TYPING | Missing return type hint for function 'test_already_prunable_returns_zero' | `def test_already_prunable_returns_zero(self):` |
| `226` | Warning | PY_TYPING | Missing return type hint for function 'test_incident_days_until_prune_fresh' | `def test_incident_days_until_prune_fresh(self):` |
| `232` | Warning | PY_TYPING | Missing return type hint for function 'test_configuration_days_until_prune_fresh' | `def test_configuration_days_until_prune_fresh(self):` |
| `237` | Warning | PY_TYPING | Missing return type hint for function 'test_days_until_prune_decreases_over_time' | `def test_days_until_prune_decreases_over_time(self):` |
| `242` | Warning | PY_TYPING | Missing return type hint for function 'test_days_until_prune_never_negative' | `def test_days_until_prune_never_negative(self):` |
| `260` | Warning | PY_TYPING | Missing return type hint for function 'test_adds_retention_key' | `def test_adds_retention_key(self):` |
| `266` | Warning | PY_TYPING | Missing return type hint for function 'test_adds_prune_eligible_key' | `def test_adds_prune_eligible_key(self):` |
| `271` | Warning | PY_TYPING | Missing return type hint for function 'test_default_timestamp_key_is_valid_from' | `def test_default_timestamp_key_is_valid_from(self):` |
| `277` | Warning | PY_TYPING | Missing return type hint for function 'test_none_timestamp_defaults_to_fully_retained' | `def test_none_timestamp_defaults_to_fully_retained(self):` |
| `283` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_batch_returns_empty' | `def test_empty_batch_returns_empty(self):` |
| `286` | Warning | PY_TYPING | Missing return type hint for function 'test_multiple_classes_in_batch' | `def test_multiple_classes_in_batch(self):` |
| `296` | Warning | PY_TYPING | Missing return type hint for function 'test_preserves_original_row_fields' | `def test_preserves_original_row_fields(self):` |
| `316` | Warning | PY_TYPING | Missing return type hint for function 'test_summary_contains_required_keys' | `def test_summary_contains_required_keys(self):` |
| `327` | Warning | PY_TYPING | Missing return type hint for function 'test_default_timestamp_key_is_valid_from' | `def test_default_timestamp_key_is_valid_from(self):` |
| `333` | Warning | PY_TYPING | Missing return type hint for function 'test_retention_value_correct' | `def test_retention_value_correct(self):` |
| `338` | Warning | PY_TYPING | Missing return type hint for function 'test_stability_correct_for_class' | `def test_stability_correct_for_class(self):` |
| `343` | Warning | PY_TYPING | Missing return type hint for function 'test_empty_returns_empty' | `def test_empty_returns_empty(self):` |
| `346` | Warning | PY_TYPING | Missing return type hint for function 'test_none_valid_from_returns_full_retention' | `def test_none_valid_from_returns_full_retention(self):` |
| `352` | Warning | PY_TYPING | Missing return type hint for function 'test_prune_eligible_flagged' | `def test_prune_eligible_flagged(self):` |
| `371` | Warning | PY_TYPING | Missing return type hint for function '_stub_apscheduler' | `def _stub_apscheduler(self, monkeypatch):` |
| `371` | Warning | PY_TYPING | Missing type hint for argument 'monkeypatch' in function '_stub_apscheduler' | `def _stub_apscheduler(self, monkeypatch):` |
| `396` | Warning | PY_TYPING | Missing return type hint for function 'test_register_calls_add_job_with_correct_id' | `def test_register_calls_add_job_with_correct_id(self):` |
| `401` | Warning | PY_TYPING | Missing return type hint for function 'add_job' | `def add_job(self, func, trigger, *, args, id, coalesce, max_instances, replace_existing):` |
| `401` | Warning | PY_TYPING | Missing type hint for argument 'func' in function 'add_job' | `def add_job(self, func, trigger, *, args, id, coalesce, max_instances, replace_existing):` |
| `401` | Warning | PY_TYPING | Missing type hint for argument 'trigger' in function 'add_job' | `def add_job(self, func, trigger, *, args, id, coalesce, max_instances, replace_existing):` |
| `408` | Warning | PY_TYPING | Missing return type hint for function 'test_register_passes_pool_as_arg' | `def test_register_passes_pool_as_arg(self):` |
| `413` | Warning | PY_TYPING | Missing return type hint for function 'add_job' | `def add_job(self, func, trigger, *, args, id, coalesce, max_instances, replace_existing):` |
| `413` | Warning | PY_TYPING | Missing type hint for argument 'func' in function 'add_job' | `def add_job(self, func, trigger, *, args, id, coalesce, max_instances, replace_existing):` |
| `413` | Warning | PY_TYPING | Missing type hint for argument 'trigger' in function 'add_job' | `def add_job(self, func, trigger, *, args, id, coalesce, max_instances, replace_existing):` |
| `425` | Warning | PY_TYPING | Missing return type hint for function 'test_retention_approaches_zero_as_t_increases' | `def test_retention_approaches_zero_as_t_increases(self):` |
| `431` | Warning | PY_TYPING | Missing return type hint for function 'test_ebbinghaus_half_life_at_ln2_times_stability' | `def test_ebbinghaus_half_life_at_ln2_times_stability(self):` |
| `439` | Warning | PY_TYPING | Missing return type hint for function 'test_retention_is_continuous_and_smooth' | `def test_retention_is_continuous_and_smooth(self):` |
| `451` | Warning | PY_TYPING | Missing return type hint for function 'test_prune_threshold_consistent_with_days_until_prune' | `def test_prune_threshold_consistent_with_days_until_prune(self):` |
| `498` | Warning | PY_TYPING | Missing return type hint for function 'test_uses_cte_pattern_not_direct_update' | `def test_uses_cte_pattern_not_direct_update(self, prune_sql):` |
| `498` | Warning | PY_TYPING | Missing type hint for argument 'prune_sql' in function 'test_uses_cte_pattern_not_direct_update' | `def test_uses_cte_pattern_not_direct_update(self, prune_sql):` |
| `502` | Warning | PY_TYPING | Missing return type hint for function 'test_no_update_limit_mysql_syntax' | `def test_no_update_limit_mysql_syntax(self, prune_sql):` |
| `502` | Warning | PY_TYPING | Missing type hint for argument 'prune_sql' in function 'test_no_update_limit_mysql_syntax' | `def test_no_update_limit_mysql_syntax(self, prune_sql):` |
| `516` | Warning | PY_TYPING | Missing return type hint for function 'test_uses_valid_from_not_updated_at' | `def test_uses_valid_from_not_updated_at(self, prune_sql):` |
| `516` | Warning | PY_TYPING | Missing type hint for argument 'prune_sql' in function 'test_uses_valid_from_not_updated_at' | `def test_uses_valid_from_not_updated_at(self, prune_sql):` |
| `521` | Warning | PY_TYPING | Missing return type hint for function 'test_update_joins_on_composite_pk' | `def test_update_joins_on_composite_pk(self, prune_sql):` |
| `521` | Warning | PY_TYPING | Missing type hint for argument 'prune_sql' in function 'test_update_joins_on_composite_pk' | `def test_update_joins_on_composite_pk(self, prune_sql):` |
| `526` | Warning | PY_TYPING | Missing return type hint for function 'test_prune_tick_no_duplicate_release_import' | `def test_prune_tick_no_duplicate_release_import(self):` |
| `538` | Warning | PY_TYPING | Missing return type hint for function 'test_prune_tick_filters_valid_to_is_null' | `def test_prune_tick_filters_valid_to_is_null(self, prune_sql):` |
| `538` | Warning | PY_TYPING | Missing type hint for argument 'prune_sql' in function 'test_prune_tick_filters_valid_to_is_null' | `def test_prune_tick_filters_valid_to_is_null(self, prune_sql):` |
| `542` | Warning | PY_TYPING | Missing return type hint for function 'test_prune_tick_parametrised_not_fstring' | `def test_prune_tick_parametrised_not_fstring(self, prune_sql):` |
| `542` | Warning | PY_TYPING | Missing type hint for argument 'prune_sql' in function 'test_prune_tick_parametrised_not_fstring' | `def test_prune_tick_parametrised_not_fstring(self, prune_sql):` |

---

## 3. Structural Code Duplication Ledger
### Redundancy ID: `DUP_001`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `health_probe.py` (Lines `5`-`10`)
- **Target Vector B:** `tests/test_check_admin_hardening.py` (Lines `13`-`18`)
- **Shared Code Block Profile:**
```py
"""

import asyncio
import logging
import sys

```
Remediation Vector: Extract to a shared common library/module

### Redundancy ID: `DUP_002`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `health_probe.py` (Lines `6`-`11`)
- **Target Vector B:** `nce/extractors/office_word.py` (Lines `4`-`9`)
- **Shared Code Block Profile:**
```py

import asyncio
import logging
import sys

import asyncpg
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_003`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `health_probe.py` (Lines `7`-`12`)
- **Target Vector B:** `nce/snapshot_mcp_handlers.py` (Lines `21`-`26`)
- **Shared Code Block Profile:**
```py
import asyncio
import logging
import sys

import asyncpg
from motor.motor_asyncio import AsyncIOMotorClient
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_004`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `admin_server.py` (Lines `1`-`6`)
- **Target Vector B:** `nce/mcp_stdio_dispatch.py` (Lines `3`-`8`)
- **Shared Code Block Profile:**
```py
from __future__ import annotations

import logging

from nce import admin_state
from nce.admin_app import app
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_005`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `admin_server.py` (Lines `2`-`7`)
- **Target Vector B:** `nce/replay.py` (Lines `51`-`56`)
- **Shared Code Block Profile:**
```py

import logging

from nce import admin_state
from nce.admin_app import app
from nce.admin_http_support import admin_error_response
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_006`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `admin_server.py` (Lines `3`-`8`)
- **Target Vector B:** `nce/bridge_runtime.py` (Lines `8`-`13`)
- **Shared Code Block Profile:**
```py
import logging

from nce import admin_state
from nce.admin_app import app
from nce.admin_http_support import admin_error_response
from nce.admin_http_support import update_dotenv  # noqa: F401 — re-export for tests
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_007`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `admin_server.py` (Lines `4`-`9`)
- **Target Vector B:** `nce/admin_http_support.py` (Lines `9`-`14`)
- **Shared Code Block Profile:**
```py

from nce import admin_state
from nce.admin_app import app
from nce.admin_http_support import admin_error_response
from nce.admin_http_support import update_dotenv  # noqa: F401 — re-export for tests

```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_008`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `admin_server.py` (Lines `28`-`33`)
- **Target Vector B:** `nce/mcp_stdio_dispatch.py` (Lines `37`-`42`)
- **Shared Code Block Profile:**
```py
from nce.admin_http_handlers import (
    api_admin_salience_map,
    api_admin_llm_payload,
    api_admin_fleet_overview,
    api_admin_bridge_renew,
    api_admin_memory_boost,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_009`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `admin_server.py` (Lines `29`-`34`)
- **Target Vector B:** `nce/tool_registry.py` (Lines `25`-`30`)
- **Shared Code Block Profile:**
```py
    api_admin_salience_map,
    api_admin_llm_payload,
    api_admin_fleet_overview,
    api_admin_bridge_renew,
    api_admin_memory_boost,
    api_admin_contradictions_recent,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_010`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `admin_server.py` (Lines `52`-`57`)
- **Target Vector B:** `nce/admin_http_handlers.py` (Lines `5`-`10`)
- **Shared Code Block Profile:**
```py
    api_admin_security_verify_memory_sample,
    api_admin_security_test_rls_isolation,
    api_admin_verify_chain,
    trigger_gc,
    api_search,
)
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_011`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `server.py` (Lines `17`-`22`)
- **Target Vector B:** `nce/http_resilience.py` (Lines `9`-`14`)
- **Shared Code Block Profile:**
```py
nonce ledger.
"""

from __future__ import annotations

import asyncio
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_012`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `server.py` (Lines `18`-`23`)
- **Target Vector B:** `verify_v1_launch.py` (Lines `24`-`29`)
- **Shared Code Block Profile:**
```py
"""

from __future__ import annotations

import asyncio
import importlib
```
Remediation Vector: Extract to a shared common library/module

### Redundancy ID: `DUP_013`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `server.py` (Lines `19`-`24`)
- **Target Vector B:** `verify_v1_launch.py` (Lines `25`-`30`)
- **Shared Code Block Profile:**
```py

from __future__ import annotations

import asyncio
import importlib
import logging
```
Remediation Vector: Extract to a shared common library/module

### Redundancy ID: `DUP_014`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `server.py` (Lines `20`-`25`)
- **Target Vector B:** `verify_v1_launch.py` (Lines `26`-`31`)
- **Shared Code Block Profile:**
```py
from __future__ import annotations

import asyncio
import importlib
import logging
import uuid
```
Remediation Vector: Extract to a shared common library/module

### Redundancy ID: `DUP_015`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `server.py` (Lines `21`-`26`)
- **Target Vector B:** `nce/openvino_npu_export.py` (Lines `12`-`17`)
- **Shared Code Block Profile:**
```py

import asyncio
import importlib
import logging
import uuid
from typing import Any
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_016`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `server.py` (Lines `23`-`28`)
- **Target Vector B:** `nce/code_mcp_handlers.py` (Lines `9`-`14`)
- **Shared Code Block Profile:**
```py
import importlib
import logging
import uuid
from typing import Any

from mcp.server import Server
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_017`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `server.py` (Lines `24`-`29`)
- **Target Vector B:** `nce/mcp_utils.py` (Lines `10`-`15`)
- **Shared Code Block Profile:**
```py
import logging
import uuid
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_018`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `server.py` (Lines `30`-`35`)
- **Target Vector B:** `nce/bridge_runtime.py` (Lines `9`-`14`)
- **Shared Code Block Profile:**
```py

from nce import NCEEngine
from nce.correlation import correlation_id_var
from nce.mcp_stdio_dispatch import execute_call_tool
from nce.mcp_stdio_rpc import _check_admin
from nce.mcp_stdio_tools import TOOLS
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_019`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `server.py` (Lines `48`-`53`)
- **Target Vector B:** `nce/__init__.py` (Lines `21`-`26`)
- **Shared Code Block Profile:**
```py
__all__ = [
    "app",
    "engine",
    "call_tool",
    "list_tools",
    "_check_admin",
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_020`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `verify_v1_launch.py` (Lines `27`-`32`)
- **Target Vector B:** `nce/replay.py` (Lines `40`-`45`)
- **Shared Code Block Profile:**
```py

import argparse
import asyncio
import hashlib
import hmac
import json
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_021`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `verify_v1_launch.py` (Lines `28`-`33`)
- **Target Vector B:** `nce/replay.py` (Lines `41`-`46`)
- **Shared Code Block Profile:**
```py
import argparse
import asyncio
import hashlib
import hmac
import json
import os
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_022`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `verify_v1_launch.py` (Lines `31`-`36`)
- **Target Vector B:** `nce/reembedding_worker.py` (Lines `63`-`68`)
- **Shared Code Block Profile:**
```py
import hmac
import json
import os
import sys
import time
from typing import Any
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_023`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `verify_v1_launch.py` (Lines `32`-`37`)
- **Target Vector B:** `run_audit.py` (Lines `1`-`6`)
- **Shared Code Block Profile:**
```py
import json
import os
import sys
import time
from typing import Any
from uuid import UUID
```
Remediation Vector: Extract to a shared common library/module

### Redundancy ID: `DUP_024`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `verify_v1_launch.py` (Lines `33`-`38`)
- **Target Vector B:** `nce/admin_http_support.py` (Lines `4`-`9`)
- **Shared Code Block Profile:**
```py
import os
import sys
import time
from typing import Any
from uuid import UUID

```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_025`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `verify_v1_launch.py` (Lines `74`-`79`)
- **Target Vector B:** `tests/test_auth.py` (Lines `89`-`94`)
- **Shared Code Block Profile:**
```py
    return {
        "X-NCE-Timestamp": str(ts),
        "Authorization": f"HMAC-SHA256 {sig}",
    }


```
Remediation Vector: Extract to a shared common library/module

### Redundancy ID: `DUP_026`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `verify_v1_launch.py` (Lines `154`-`159`)
- **Target Vector B:** `nce/event_log.py` (Lines `650`-`655`)
- **Shared Code Block Profile:**
```py
            row = await conn.fetchrow(
                """
                SELECT status
                FROM consolidation_runs
                WHERE namespace_id = $1
                ORDER BY started_at DESC
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_027`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `verify_v1_launch.py` (Lines `155`-`160`)
- **Target Vector B:** `nce/event_log.py` (Lines `651`-`656`)
- **Shared Code Block Profile:**
```py
                """
                SELECT status
                FROM consolidation_runs
                WHERE namespace_id = $1
                ORDER BY started_at DESC
                LIMIT 1
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_028`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `verify_v1_launch.py` (Lines `156`-`161`)
- **Target Vector B:** `nce/event_log.py` (Lines `652`-`657`)
- **Shared Code Block Profile:**
```py
                SELECT status
                FROM consolidation_runs
                WHERE namespace_id = $1
                ORDER BY started_at DESC
                LIMIT 1
                """,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_029`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `verify_v1_launch.py` (Lines `157`-`162`)
- **Target Vector B:** `nce/event_log.py` (Lines `653`-`658`)
- **Shared Code Block Profile:**
```py
                FROM consolidation_runs
                WHERE namespace_id = $1
                ORDER BY started_at DESC
                LIMIT 1
                """,
                ns_id,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_030`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `verify_v1_launch.py` (Lines `158`-`163`)
- **Target Vector B:** `nce/event_log.py` (Lines `654`-`659`)
- **Shared Code Block Profile:**
```py
                WHERE namespace_id = $1
                ORDER BY started_at DESC
                LIMIT 1
                """,
                ns_id,
            )
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_031`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `index_all.py` (Lines `1`-`6`)
- **Target Vector B:** `nce/notifications.py` (Lines `2`-`7`)
- **Shared Code Block Profile:**
```py
import asyncio
import logging
import os

from nce.orchestrator import NCEEngine

```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_032`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/mongo_bulk.py` (Lines `4`-`9`)
- **Target Vector B:** `nce/ast_parser.py` (Lines `6`-`11`)
- **Shared Code Block Profile:**
```py
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_033`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/mongo_bulk.py` (Lines `5`-`10`)
- **Target Vector B:** `nce/admin_routes.py` (Lines `22`-`27`)
- **Shared Code Block Profile:**
```py

from __future__ import annotations

import logging
from collections.abc import Iterable

```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_034`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/mongo_bulk.py` (Lines `6`-`11`)
- **Target Vector B:** `nce/ast_parser.py` (Lines `7`-`12`)
- **Shared Code Block Profile:**
```py
from __future__ import annotations

import logging
from collections.abc import Iterable

from bson import ObjectId
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_035`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/mongo_bulk.py` (Lines `105`-`110`)
- **Target Vector B:** `nce/http_resilience.py` (Lines `174`-`179`)
- **Shared Code Block Profile:**
```py
            )

    return out


async def fetch_episodes_raw_by_ref(
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_036`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/openvino_npu_export.py` (Lines `136`-`141`)
- **Target Vector B:** `nce/extractors/libreoffice.py` (Lines `76`-`81`)
- **Shared Code Block Profile:**
```py
            tok = AutoTokenizer.from_pretrained(
                model_id_or_path,
                local_files_only=local_files_only,
                trust_remote_code=True,
                revision=OPENVINO_MODEL_REVISION,
            )
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_037`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/active_learning.py` (Lines `1`-`6`)
- **Target Vector B:** `nce/atms.py` (Lines `14`-`19`)
- **Shared Code Block Profile:**
```py
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_038`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/active_learning.py` (Lines `3`-`8`)
- **Target Vector B:** `nce/salience.py` (Lines `1`-`6`)
- **Shared Code Block Profile:**
```py
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

import asyncpg
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_039`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/active_learning.py` (Lines `4`-`9`)
- **Target Vector B:** `nce/salience.py` (Lines `2`-`7`)
- **Shared Code Block Profile:**
```py
import logging
from datetime import datetime, timezone
from uuid import UUID

import asyncpg

```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_040`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/active_learning.py` (Lines `5`-`10`)
- **Target Vector B:** `nce/orchestrators/temporal.py` (Lines `14`-`19`)
- **Shared Code Block Profile:**
```py
from datetime import datetime, timezone
from uuid import UUID

import asyncpg

from nce.models import StoreMemoryRequest
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_041`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/active_learning.py` (Lines `6`-`11`)
- **Target Vector B:** `nce/quotas.py` (Lines `18`-`23`)
- **Shared Code Block Profile:**
```py
from uuid import UUID

import asyncpg

from nce.models import StoreMemoryRequest
from nce.db_utils import scoped_pg_session
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_042`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/active_learning.py` (Lines `7`-`12`)
- **Target Vector B:** `nce/migration_mcp_handlers.py` (Lines `30`-`35`)
- **Shared Code Block Profile:**
```py

import asyncpg

from nce.models import StoreMemoryRequest
from nce.db_utils import scoped_pg_session
from nce.config import cfg
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_043`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/active_learning.py` (Lines `96`-`101`)
- **Target Vector B:** `nce/reembedding_worker.py` (Lines `212`-`217`)
- **Shared Code Block Profile:**
```py
                """,
                operator_id,
                item_uuid,
                ns_uuid,
            )

```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_044`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/active_learning.py` (Lines `191`-`196`)
- **Target Vector B:** `nce/analytics/stress.py` (Lines `48`-`53`)
- **Shared Code Block Profile:**
```py
                ORDER BY created_at ASC
                """,
                ns_uuid,
            )
            results = []
            for r in rows:
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_045`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/active_learning.py` (Lines `279`-`284`)
- **Target Vector B:** `nce/tasks.py` (Lines `272`-`277`)
- **Shared Code Block Profile:**
```py
                "rejected_count": rejected_count,
                "operator_stats": {
                    "operator_id": operator_id,
                    "confirmed_count": op_confirmed,
                    "rejected_count": op_rejected,
                    "xp": xp,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_046`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/active_learning.py` (Lines `283`-`288`)
- **Target Vector B:** `nce/database/pruning.py` (Lines `303`-`308`)
- **Shared Code Block Profile:**
```py
                    "rejected_count": op_rejected,
                    "xp": xp,
                    "level": level,
                    "xp_to_next_level": next_level_xp,
                    "streak": streak,
                },
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_047`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/active_learning.py` (Lines `284`-`289`)
- **Target Vector B:** `nce/tasks.py` (Lines `274`-`279`)
- **Shared Code Block Profile:**
```py
                    "xp": xp,
                    "level": level,
                    "xp_to_next_level": next_level_xp,
                    "streak": streak,
                },
                "accuracy_rate": accuracy,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_048`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/tool_registry.py` (Lines `16`-`21`)
- **Target Vector B:** `nce/memory_mcp_handlers.py` (Lines `14`-`19`)
- **Shared Code Block Profile:**
```py
"""

from __future__ import annotations

import types
from dataclasses import dataclass
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_049`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/tool_registry.py` (Lines `23`-`28`)
- **Target Vector B:** `nce/models.py` (Lines `32`-`37`)
- **Shared Code Block Profile:**
```py

from nce import (
    a2a_mcp_handlers,
    admin_mcp_handlers,
    bridge_mcp_handlers,
    catalog_mcp_handlers,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_050`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/tool_registry.py` (Lines `24`-`29`)
- **Target Vector B:** `nce/mcp_stdio_dispatch.py` (Lines `13`-`18`)
- **Shared Code Block Profile:**
```py
from nce import (
    a2a_mcp_handlers,
    admin_mcp_handlers,
    bridge_mcp_handlers,
    catalog_mcp_handlers,
    code_mcp_handlers,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_051`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/tool_registry.py` (Lines `32`-`37`)
- **Target Vector B:** `nce/reembedding_worker.py` (Lines `177`-`182`)
- **Shared Code Block Profile:**
```py
    memory_mcp_handlers,
    migration_mcp_handlers,
    replay_mcp_handlers,
    snapshot_mcp_handlers,
)

```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_052`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/tool_registry.py` (Lines `33`-`38`)
- **Target Vector B:** `nce/bridge_repo.py` (Lines `30`-`35`)
- **Shared Code Block Profile:**
```py
    migration_mcp_handlers,
    replay_mcp_handlers,
    snapshot_mcp_handlers,
)


```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_053`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/tool_registry.py` (Lines `81`-`86`)
- **Target Vector B:** `nce/a2a.py` (Lines `149`-`154`)
- **Shared Code Block Profile:**
```py
    migration: bool = False


# ---------------------------------------------------------------------------
# Registry — one entry per tool, grouped by domain
# ---------------------------------------------------------------------------
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_054`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/tool_registry.py` (Lines `82`-`87`)
- **Target Vector B:** `nce/bridge_repo.py` (Lines `282`-`287`)
- **Shared Code Block Profile:**
```py


# ---------------------------------------------------------------------------
# Registry — one entry per tool, grouped by domain
# ---------------------------------------------------------------------------

```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_055`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/tool_registry.py` (Lines `324`-`329`)
- **Target Vector B:** `nce/replay.py` (Lines `288`-`293`)
- **Shared Code Block Profile:**
```py
}

# ---------------------------------------------------------------------------
# Derived sets — computed once at import time
# ---------------------------------------------------------------------------

```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_056`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `16`-`21`)
- **Target Vector B:** `nce/atms.py` (Lines `11`-`16`)
- **Shared Code Block Profile:**
```py
encryption flows through a single auditable code path.
"""

from __future__ import annotations

import json
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_057`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `18`-`23`)
- **Target Vector B:** `nce/temporal_decay.py` (Lines `34`-`39`)
- **Shared Code Block Profile:**
```py

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_058`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `19`-`24`)
- **Target Vector B:** `nce/temporal_decay.py` (Lines `35`-`40`)
- **Shared Code Block Profile:**
```py
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_059`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `21`-`26`)
- **Target Vector B:** `nce/bridge_renewal.py` (Lines `4`-`9`)
- **Shared Code Block Profile:**
```py
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_060`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `23`-`28`)
- **Target Vector B:** `nce/admin_routes.py` (Lines `21`-`26`)
- **Shared Code Block Profile:**
```py
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg

from nce.bridge_providers import BRIDGE_PROVIDERS
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_061`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `24`-`29`)
- **Target Vector B:** `tests/test_snapshot_mcp_handlers.py` (Lines `8`-`13`)
- **Shared Code Block Profile:**
```py
from typing import Any

import asyncpg

from nce.bridge_providers import BRIDGE_PROVIDERS
from nce.signing import (
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_062`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `25`-`30`)
- **Target Vector B:** `tests/test_snapshot_mcp_handlers.py` (Lines `9`-`14`)
- **Shared Code Block Profile:**
```py

import asyncpg

from nce.bridge_providers import BRIDGE_PROVIDERS
from nce.signing import (
    decrypt_signing_key,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_063`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `26`-`31`)
- **Target Vector B:** `tests/test_snapshot_mcp_handlers.py` (Lines `10`-`15`)
- **Shared Code Block Profile:**
```py
import asyncpg

from nce.bridge_providers import BRIDGE_PROVIDERS
from nce.signing import (
    decrypt_signing_key,
    encrypt_signing_key,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_064`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `27`-`32`)
- **Target Vector B:** `nce/replay.py` (Lines `55`-`60`)
- **Shared Code Block Profile:**
```py

from nce.bridge_providers import BRIDGE_PROVIDERS
from nce.signing import (
    decrypt_signing_key,
    encrypt_signing_key,
    require_master_key,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_065`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `29`-`34`)
- **Target Vector B:** `nce/re_embedder.py` (Lines `32`-`37`)
- **Shared Code Block Profile:**
```py
from nce.signing import (
    decrypt_signing_key,
    encrypt_signing_key,
    require_master_key,
)

```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_066`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `31`-`36`)
- **Target Vector B:** `nce/snapshot_serializer.py` (Lines `25`-`30`)
- **Shared Code Block Profile:**
```py
    encrypt_signing_key,
    require_master_key,
)

# asyncpg.Record behaves like Mapping for known keys

```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_067`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `32`-`37`)
- **Target Vector B:** `nce/snapshot_serializer.py` (Lines `26`-`31`)
- **Shared Code Block Profile:**
```py
    require_master_key,
)

# asyncpg.Record behaves like Mapping for known keys

# Columns permitted for dynamic UPDATE from ``update_subscription`` (MCP / renewal tooling).
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_068`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `38`-`43`)
- **Target Vector B:** `tests/test_init_public_api.py` (Lines `11`-`16`)
- **Shared Code Block Profile:**
```py
ALLOWED_SUBSCRIPTION_UPDATE_FIELDS = frozenset(
    {
        "resource_id",
        "subscription_id",
        "cursor",
        "status",
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_069`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `39`-`44`)
- **Target Vector B:** `nce/constants.py` (Lines `36`-`41`)
- **Shared Code Block Profile:**
```py
    {
        "resource_id",
        "subscription_id",
        "cursor",
        "status",
        "expires_at",
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_070`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `41`-`46`)
- **Target Vector B:** `nce/constants.py` (Lines `71`-`76`)
- **Shared Code Block Profile:**
```py
        "subscription_id",
        "cursor",
        "status",
        "expires_at",
        "client_state",
    }
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_071`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `42`-`47`)
- **Target Vector B:** `nce/constants.py` (Lines `72`-`77`)
- **Shared Code Block Profile:**
```py
        "cursor",
        "status",
        "expires_at",
        "client_state",
    }
)
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_072`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `43`-`48`)
- **Target Vector B:** `nce/constants.py` (Lines `73`-`78`)
- **Shared Code Block Profile:**
```py
        "status",
        "expires_at",
        "client_state",
    }
)

```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_073`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `44`-`49`)
- **Target Vector B:** `nce/contradiction_mcp_handlers.py` (Lines `28`-`33`)
- **Shared Code Block Profile:**
```py
        "expires_at",
        "client_state",
    }
)


```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_074`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `45`-`50`)
- **Target Vector B:** `nce/orchestrators/namespace.py` (Lines `46`-`51`)
- **Shared Code Block Profile:**
```py
        "client_state",
    }
)


async def insert_subscription(
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_075`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `46`-`51`)
- **Target Vector B:** `nce/orchestrators/namespace.py` (Lines `47`-`52`)
- **Shared Code Block Profile:**
```py
    }
)


async def insert_subscription(
    conn: asyncpg.Connection,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_076`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `47`-`52`)
- **Target Vector B:** `nce/event_log.py` (Lines `777`-`782`)
- **Shared Code Block Profile:**
```py
)


async def insert_subscription(
    conn: asyncpg.Connection,
    *,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_077`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `48`-`53`)
- **Target Vector B:** `nce/quotas.py` (Lines `246`-`251`)
- **Shared Code Block Profile:**
```py


async def insert_subscription(
    conn: asyncpg.Connection,
    *,
    user_id: str,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_078`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `72`-`77`)
- **Target Vector B:** `nce/replay.py` (Lines `193`-`198`)
- **Shared Code Block Profile:**
```py
        """,
        rid,
        user_id,
        namespace_id,
        provider,
        resource_id,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_079`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `79`-`84`)
- **Target Vector B:** `nce/replay.py` (Lines `206`-`211`)
- **Shared Code Block Profile:**
```py
        cursor,
        status,
        expires_at,
        client_state,
    )
    return rid
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_080`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `80`-`85`)
- **Target Vector B:** `nce/replay.py` (Lines `207`-`212`)
- **Shared Code Block Profile:**
```py
        status,
        expires_at,
        client_state,
    )
    return rid

```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_081`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `81`-`86`)
- **Target Vector B:** `nce/replay.py` (Lines `208`-`213`)
- **Shared Code Block Profile:**
```py
        expires_at,
        client_state,
    )
    return rid


```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_082`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `82`-`87`)
- **Target Vector B:** `nce/replay.py` (Lines `209`-`214`)
- **Shared Code Block Profile:**
```py
        client_state,
    )
    return rid


async def fetch_expiring(
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_083`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `83`-`88`)
- **Target Vector B:** `nce/replay.py` (Lines `210`-`215`)
- **Shared Code Block Profile:**
```py
    )
    return rid


async def fetch_expiring(
    conn: asyncpg.Connection,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_084`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `84`-`89`)
- **Target Vector B:** `nce/quotas.py` (Lines `245`-`250`)
- **Shared Code Block Profile:**
```py
    return rid


async def fetch_expiring(
    conn: asyncpg.Connection,
    *,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_085`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `101`-`106`)
- **Target Vector B:** `nce/query_catalog.py` (Lines `124`-`129`)
- **Shared Code Block Profile:**
```py
        LIMIT $2
        """,
        within,
        limit,
    )

```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_086`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `102`-`107`)
- **Target Vector B:** `nce/outbox_relay.py` (Lines `134`-`139`)
- **Shared Code Block Profile:**
```py
        """,
        within,
        limit,
    )


```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_087`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `111`-`116`)
- **Target Vector B:** `nce/replay.py` (Lines `222`-`227`)
- **Shared Code Block Profile:**
```py
        bridge_id,
    )


async def list_for_user(
    conn: asyncpg.Connection,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_088`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `112`-`117`)
- **Target Vector B:** `nce/outbox_relay.py` (Lines `120`-`125`)
- **Shared Code Block Profile:**
```py
    )


async def list_for_user(
    conn: asyncpg.Connection,
    user_id: str,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_089`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `113`-`118`)
- **Target Vector B:** `nce/quotas.py` (Lines `150`-`155`)
- **Shared Code Block Profile:**
```py


async def list_for_user(
    conn: asyncpg.Connection,
    user_id: str,
    *,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_090`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `137`-`142`)
- **Target Vector B:** `nce/replay.py` (Lines `223`-`228`)
- **Shared Code Block Profile:**
```py
    )


async def update_subscription(
    conn: asyncpg.Connection,
    bridge_id: uuid.UUID,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_091`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `167`-`172`)
- **Target Vector B:** `nce/bridge_runtime.py` (Lines `25`-`30`)
- **Shared Code Block Profile:**
```py
    provider: str,
    *,
    client_state: str | None = None,
    subscription_id: str | None = None,
    resource_id: str | None = None,
) -> bytes | None:
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_092`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `179`-`184`)
- **Target Vector B:** `nce/orchestrators/memory.py` (Lines `1083`-`1088`)
- **Shared Code Block Profile:**
```py
    if client_state:
        clauses.append(f"client_state = ${idx}")
        args.append(client_state)
        idx += 1
    if subscription_id:
        clauses.append(f"subscription_id = ${idx}")
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_093`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `180`-`185`)
- **Target Vector B:** `nce/orchestrators/memory.py` (Lines `1084`-`1089`)
- **Shared Code Block Profile:**
```py
        clauses.append(f"client_state = ${idx}")
        args.append(client_state)
        idx += 1
    if subscription_id:
        clauses.append(f"subscription_id = ${idx}")
        args.append(subscription_id)
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_094`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `181`-`186`)
- **Target Vector B:** `nce/orchestrators/memory.py` (Lines `1085`-`1090`)
- **Shared Code Block Profile:**
```py
        args.append(client_state)
        idx += 1
    if subscription_id:
        clauses.append(f"subscription_id = ${idx}")
        args.append(subscription_id)
        idx += 1
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_095`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `182`-`187`)
- **Target Vector B:** `nce/admin_handlers/fleet.py` (Lines `52`-`57`)
- **Shared Code Block Profile:**
```py
        idx += 1
    if subscription_id:
        clauses.append(f"subscription_id = ${idx}")
        args.append(subscription_id)
        idx += 1
    if resource_id:
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_096`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `256`-`261`)
- **Target Vector B:** `nce/outbox_relay.py` (Lines `133`-`138`)
- **Shared Code Block Profile:**
```py
        WHERE id = $1
        """,
        bridge_id,
        status,
    )

```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_097`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `278`-`283`)
- **Target Vector B:** `nce/bridge_mcp_handlers.py` (Lines `551`-`556`)
- **Shared Code Block Profile:**
```py


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_098`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `281`-`286`)
- **Target Vector B:** `nce/event_log.py` (Lines `719`-`724`)
- **Shared Code Block Profile:**
```py
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# OAuth token encryption (Phase 3 — Item 12)
# ---------------------------------------------------------------------------
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_099`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `286`-`291`)
- **Target Vector B:** `nce/replay.py` (Lines `1644`-`1649`)
- **Shared Code Block Profile:**
```py
# ---------------------------------------------------------------------------


async def save_token(
    conn: asyncpg.Connection,
    bridge_id: uuid.UUID,
```
Remediation Vector: Abstract into unified helper module under nce/utils.py

### Redundancy ID: `DUP_100`
- **Similarity Metric:** 100% Match
- **Target Vector A:** `nce/bridge_repo.py` (Lines `321`-`326`)
- **Target Vector B:** `nce/replay.py` (Lines `221`-`226`)
- **Shared Code Block Profile:**
```py
        bridge_id,
        ciphertext,
    )


async def get_token(
```
Remediation Vector: Abstract into unified helper module under nce/utils.py
