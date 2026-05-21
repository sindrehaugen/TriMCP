# TriMCP IT Admin Guide

This guide provides IT administrators with the necessary instructions to deploy, configure, and maintain TriMCP in an enterprise environment. It focuses on infrastructure-as-code (IaC) deployments, network security, and identity integration.

## 1. Infrastructure Deployment (Cloud Mode)

TriMCP supports automated deployment to major cloud providers using Terraform (AWS/GCP) or Bicep (Azure).

### 1.1 AWS Deployment (Terraform)

The AWS deployment provisions RDS (PostgreSQL), DocumentDB (MongoDB), ElastiCache (Redis), S3 (Blob storage), and Fargate (Container Apps).

**Prerequisites:**
- Terraform v1.5+
- AWS CLI configured with appropriate permissions

**Steps:**
1. Navigate to the AWS infrastructure directory:
   ```bash
   cd trimcp-infra/aws
   ```
2. Copy the example variables file and configure your parameters:
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   ```
3. Initialize and apply the Terraform configuration:
   ```bash
   terraform init
   terraform apply
   ```

### 1.2 Azure Deployment (Bicep)

The Azure deployment provisions Azure Database for PostgreSQL, Cosmos DB (MongoDB API), Azure Cache for Redis, Azure Blob Storage, and Azure Container Apps.

**Prerequisites:**
- Azure CLI
- Bicep CLI

**Steps:**
1. Navigate to the Azure infrastructure directory:
   ```bash
   cd trimcp-infra/azure
   ```
2. Update the `parameters.example.json` with your specific values and rename it to `parameters.json`.
3. Deploy the Bicep template:
   ```bash
   az deployment group create \
     --resource-group <Your-Resource-Group> \
     --template-file main.bicep \
     --parameters @parameters.json
   ```

## 2. Network Security & Firewall Rules

Whether deploying on-premise (Multi-User Mode) or in the cloud, specific ports must be accessible for TriMCP components to communicate.

### 2.1 Internal Database Ports
These ports should **only** be accessible to the TriMCP application servers and workers. They must **never** be exposed to the public internet.

| Service | Port | Protocol | Description |
|---------|------|----------|-------------|
| PostgreSQL | `5432` | TCP | Relational database (Vector data via pgvector) |
| MongoDB | `27017` | TCP | Document database (Graph data) |
| Redis | `6379` | TCP | Queue and caching (RQ) |

### 2.2 Application Ports
These ports handle client traffic and webhook callbacks.

| Service | Port | Protocol | Description |
|---------|------|----------|-------------|
| TriMCP API | `9000` | TCP | Main MCP API endpoint. Expose to internal network/VPN for client access. |
| Webhook Receiver | `443` | TCP | Must be exposed to the public internet to receive callbacks from SharePoint, Google Drive, and Dropbox. |

*Note: In Local mode, all services run on `localhost` and do not require inbound firewall rules.*

## 3. Active Directory & Identity Integration

TriMCP relies on accurate user identity to enforce document-level permissions and access controls.

### 3.1 UPN Resolution
TriMCP uses the User Principal Name (UPN) as the primary identifier (`user_id`). 
- Ensure that the UPN provided by your SAML/OIDC Identity Provider exactly matches the UPN used in your document libraries (e.g., SharePoint/OneDrive).
- If your organization uses alternate login IDs or email addresses that differ from the UPN, you must configure a mapping rule in your IdP to pass the correct UPN in the authentication token.

### 3.2 OAuth Configuration for Document Bridges
To enable the Document Bridge System (Push Architecture), you must register TriMCP as an application in your respective cloud providers.

**Microsoft Entra ID (SharePoint/OneDrive):**
1. Register a new application in the Entra ID portal.
2. Grant the following Application permissions: `Sites.Read.All`, `Files.Read.All`.
3. Grant admin consent for the tenant.
4. Configure the Webhook Receiver URL (`https://<your-domain>/webhooks/sharepoint`) in the application settings.

**Google Workspace:**
1. Create a Service Account in the Google Cloud Console.
2. Enable Domain-Wide Delegation.
3. Grant the `https://www.googleapis.com/auth/drive.readonly` scope.

Provide the resulting client IDs and secrets to the TriMCP configuration via the `.env` file or your cloud provider's secret management service (e.g., AWS Secrets Manager, Azure Key Vault).

## 4. Dynamic Tools & Skills Management Console

TriMCP features a dynamic administration console within the Starlette Admin panel (`admin/index.html` serviced by `admin_server.py`) for managing local stdio Model Context Protocol (MCP) tools and public Agent-to-Agent (A2A) network skills.

### 4.1 System Architecture
- **Control Plane**: Administrators mutate toggle states via Basic/HMAC-secured REST endpoints `/api/admin/tools` and `/api/admin/tools/toggle`.
- **Data Plane (Redis Registry)**: Toggle states are stored inside the Redis hash key `trimcp:tools:disabled`.
  - When a tool is **disabled**, its name is registered in the hash with a value of `1`.
  - When a tool is **enabled**, its key is deleted from the hash.
- **Routing Interceptors**:
  - **Stdio MCP Layer**: Calls are intercepted inside `mcp_stdio_dispatch.py`. Disabled tools return JSON-RPC error code `-32005` (Scope forbidden).
  - **A2A Network Layer**: Skills are intercepted in `a2a_server.py`. Disabled skills raise `A2AScopeViolationError`, returning RPC code `-32011` / HTTP 403 (Scope violation).

### 4.2 High-Availability & Resiliency Guarantees
- **Fail-Safe Defaults**: If the Redis cluster is offline, unreachable, or throws read timeouts, the dynamic interceptor catches the exception, logs a warning (`Redis toggle check failed`), and defaults to **allowed/enabled**.
- **No Cascade Breakages**: This fail-safe architecture prevents temporary database or network issues from bricking active microservice integrations.

### 4.3 Administration Operations
1. **Accessing the Console**: Open the Starlette Admin panel (default port `8003`) and click the **Tools** tab in the sidebar navigation.
2. **Reviewing Operational Impact**: Each tool card displays a customized description alongside an amber warning block explaining downstream consequences (e.g., disabling `store_memory` disables agent write paths and entity extraction pipelines, resulting in potential data loss for new sessions).
3. **Toggling States**: Toggling a dynamic switch immediately propagates the configuration to all active workers and servers via Redis hash check, returning a real-time visual success toast to the administrator.
