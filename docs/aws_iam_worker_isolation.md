# TriMCP AWS IAM & Network Boundaries — Fargate Worker Isolation

**Date:** 2026-05-08  
**Status:** Implemented  
**Phase:** 2 — Infrastructure Hardening

---

## Overview

The Fargate worker pool previously shared a single IAM task role with full S3 bucket access and all database secrets. A compromised MCP integration executing on a worker would have gained the same privileges as the control plane. This hardening splits the IAM roles into two distinct trust boundaries:

| Role | Purpose | Privilege Level |
|------|---------|-----------------|
| `trimcp-*-ecs-orchestrator` | Control plane / task orchestration | Full data-plane access |
| `trimcp-*-ecs-worker` | Untrusted MCP integration execution | Scoped, minimal access |

---

## Architecture Diagram

```mermaid
graph TB
    subgraph "AWS Cloud"
        subgraph "VPC — Private Subnets"
            subgraph "ECS Fargate Cluster"
                ORCH[🟢 Orchestrator Task<br/>trimcp-*-ecs-orchestrator<br/>Full IAM]
                WKR[🟡 Worker Task<br/>trimcp-*-ecs-worker<br/>Restricted IAM]
            end

            subgraph "Data Layer"
                RDS[(RDS Postgres<br/>memory_meta)]
                DOCDB[(DocumentDB<br/>MongoDB)]
                REDIS[(ElastiCache<br/>Redis)]
            end
        end

        S3[("S3 Bucket<br/>trimcp-*")]
        SM["AWS Secrets Manager<br/>DB credentials"]
    end

    %% IAM boundaries
    ORCH -->|"secretsmanager:GetSecretValue<br/>ALL secrets"| SM
    ORCH -->|"s3:GetObject, PutObject, ListBucket<br/>FULL bucket"| S3
    ORCH -->|"Master credentials"| RDS
    ORCH -->|"Master credentials"| DOCDB
    ORCH -->|"Auth token"| REDIS

    WKR -->|"s3:GetObject, PutObject<br/>worker/ PREFIX ONLY"| S3
    WKR -.->|"❌ NO ACCESS"| SM
    WKR -.->|"❌ NO DIRECT ACCESS<br/>(via orchestrator API only)"| RDS
    WKR -.->|"❌ NO DIRECT ACCESS<br/>(via orchestrator API only)"| DOCDB
    WKR -.->|"❌ NO DIRECT ACCESS"| REDIS

    %% Network — same security group, same subnets, DIFFERENT IAM
    ORCH -.->|"Network: same SG + subnet"| WKR

    style ORCH fill:#2e7d32,color:#fff,stroke:#1b5e20
    style WKR fill:#f57f17,color:#fff,stroke:#e65100
    style SM fill:#1565c0,color:#fff
    style S3 fill:#6a1b9a,color:#fff
    style RDS fill:#00838f,color:#fff
    style DOCDB fill:#00838f,color:#fff
    style REDIS fill:#00838f,color:#fff
```

---

## IAM Policy Details

### Orchestrator Role (`trimcp-*-ecs-orchestrator`)

```json
{
  "Statement": [
    {
      "Sid": "ReadAllSecrets",
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": [
        "arn:aws:secretsmanager:*:*:secret:trimcp-*-rds-*",
        "arn:aws:secretsmanager:*:*:secret:trimcp-*-docdb-*",
        "arn:aws:secretsmanager:*:*:secret:trimcp-*-redis-*"
      ]
    },
    {
      "Sid": "S3FullAccess",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::trimcp-*-blobs",
        "arn:aws:s3:::trimcp-*-blobs/*"
      ]
    }
  ]
}
```

### Worker Role (`trimcp-*-ecs-worker`)

```json
{
  "Statement": [
    {
      "Sid": "S3WorkerPrefix",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": ["arn:aws:s3:::trimcp-*-blobs/worker/*"]
    },
    {
      "Sid": "S3ListBucket",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": ["arn:aws:s3:::trimcp-*-blobs"],
      "Condition": {
        "StringLike": {
          "s3:prefix": ["worker/*"]
        }
      }
    }
  ]
}
```

### Execution Role (shared — both tasks)

- `AmazonECSTaskExecutionRolePolicy` (managed): ECR pull, CloudWatch Logs write

---

## Blast Radius Analysis

| Scenario | Before (shared role) | After (isolated roles) |
|----------|---------------------|----------------------|
| **Compromised MCP integration** | Attacker reads ALL DB secrets, R/W entire S3 bucket | Attacker accesses only `worker/*` S3 prefix, zero DB secrets |
| **Orchestrator compromise** | Same as above (identical blast radius) | Attacker gets full data-plane (unchanged — orchestrator needs it) |
| **Credential leak via env vars** | All DB credentials exposed | Workers have no DB credentials in env |
| **Lateral movement** | Worker → RDS/DocDB/Redis direct | Worker → orchestrator API (authenticated, audited) → DB |

---

## Deployment Notes

1. **Worker secrets** (`worker_secrets_arns`) defaults to `[]`. If workers need a scoped DocumentDB user, create a dedicated secret with read-only or collection-scoped credentials and add its ARN to this list.
2. **S3 prefix** (`worker_s3_prefix`) defaults to `"worker/"`. Workers can only read/write objects under this prefix. The `ListBucket` permission is conditioned on the same prefix.
3. **Same cluster, different roles** — both services run on the same ECS cluster and share the same security group and subnets. The isolation is purely at the IAM boundary.

---

## Related

- `trimcp-infra/aws/modules/fargate-worker/main.tf` — Module implementation
- `trimcp-infra/aws/modules/fargate-worker/variables.tf` — Variable definitions
- `trimcp-infra/aws/main.tf` — Root module call with split configuration
- `to-do-v1-phase2.md` — Kaizen entry for this hardening
