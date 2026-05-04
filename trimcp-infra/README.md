# TriMCP cloud infrastructure (Phase 3)

Infrastructure-as-code for **TriMCP Cloud mode** per the Enterprise Deployment Plan — **Section 5** and **Appendix I**.

## Layout

| Path | Stack |
|------|--------|
| `azure/` | Azure Bicep (subscription-level orchestration) |
| `aws/` | Terraform (`>= 1.6`, AWS provider `~> 5`) |
| `gcp/` | Terraform (`>= 1.6`, Google provider `~> 5`) |
| `shared/` | Cross-cloud `.env` template and post-deploy checklist |

## Network security (Appendix I.6)

- **Data plane:** PostgreSQL, MongoDB-compatible stores, and Redis are provisioned with **private networking only** (no Internet-routable endpoints). Ingress is restricted to application security groups / firewall rules from the **VPC/VNet** (and optional **VPN / admin CIDR** where applicable).
- **Control plane:** Object storage (S3 / Blob / GCS) is reached from workers via **VPC endpoints** or **private service connectivity** (see module comments); buckets are never `public-read`.
- **Single intentional public surface:** The **webhook receiver** path is exposed through Front Door / API Gateway+Lambda / external HTTPS LB → webhooks service only. Workers have **no** inbound public listeners.

## Secrets (Appendix I.7)

Terraform/Bicep **must not** output generated passwords. Credentials live in **Key Vault / Secrets Manager / Secret Manager**. Outputs expose **resource IDs, hostnames, and secret references** only. Operators (or CI) resolve secrets when running `scripts/render-env.sh`.

## Deploy

See `shared/post-deploy-checklist.md`. Per-cloud scripts live under `azure/scripts/`, `aws/scripts/`, `gcp/scripts/`.

## Client installer

After `terraform apply` / `az deployment sub create`, run:

```bash
./scripts/render-env.sh --cloud aws --infra-dir trimcp-infra/aws
```

(or `gcp` / `azure`) to emit a `.env` fragment for the TriMCP client bundle. Requires cloud CLI and credentials that can **read** the provisioned secrets.
