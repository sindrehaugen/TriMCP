# TriMCP Troubleshooting FAQ

This guide covers the 10 most common errors encountered when deploying and running TriMCP across Local, Multi-User, and Cloud modes.

## 1. Docker Desktop Missing (Local Mode)
**Symptom:** TriMCP installer or shim reports "Docker daemon not found" or "Docker Desktop is required."
**Resolution:** 
In Local mode, TriMCP relies on Docker to run the database stack. Install Docker Desktop for your OS. If your organization exceeds 250 employees, you may require a paid Docker license, or you can configure TriMCP to use Podman Desktop as an alternative.

## 2. Webhook 401 Unauthorized (Document Bridges)
**Symptom:** Cloud providers (SharePoint, Google Drive, Dropbox) report webhook delivery failures with `401 Unauthorized`.
**Resolution:**
This indicates a failure in signature or token validation at the FastAPI receiver.
- **SharePoint:** Verify the `clientState` in the webhook payload matches your configured secret.
- **Google Drive:** Ensure the `X-Goog-Channel-Token` header matches your `GDRIVE_TOKEN`.
- **Dropbox:** Verify your `DROPBOX_SECRET` is correct. The receiver uses this to validate the `X-Dropbox-Signature` HMAC-SHA256 header.

## 3. VPN Disconnected / Cannot Reach Server (Multi-User Mode)
**Symptom:** Client machines report "Connection refused" or "Timeout" when attempting to connect to the central TriMCP server.
**Resolution:**
Ensure the client is connected to the corporate VPN. The Multi-User server is typically hosted on-premise and is not exposed to the public internet. Verify that the client can ping the server IP and that port 9000 (or your configured API port) is accessible.

## 4. Port Conflicts (5432, 27017, 6379)
**Symptom:** `docker-compose up` fails with "bind: address already in use."
**Resolution:**
TriMCP requires specific ports for its database stack. If you already have PostgreSQL (5432), MongoDB (27017), or Redis (6379) running locally, you must either stop those services or remap the ports in your `docker-compose.yml` and `.env` files.

## 5. Out of Memory (OOM) Errors during File Extraction
**Symptom:** The RQ Worker crashes or restarts when processing large PDFs or Excel files.
**Resolution:**
File extraction (especially OCR fallback) can be memory-intensive. Ensure your worker container has at least 4GB of RAM allocated. You can also lower the `MAX_FILE_SIZE` in your configuration (default is 100 MB) to skip excessively large files.

## 6. Missing Python 3.10+
**Symptom:** "Python version 3.10 or higher is required."
**Resolution:**
While the TriMCP installer bundles Python, manual deployments or custom scripts require Python 3.10+. Install the correct version and ensure it is in your system PATH.

## 7. CUDA / Hardware Accelerator Not Detected
**Symptom:** TriMCP falls back to CPU processing, resulting in slow embedding generation.
**Resolution:**
The Go shim attempts to auto-detect hardware (NVIDIA, AMD, Intel NPU, Apple Silicon). If it fails, ensure your GPU drivers are up to date. For NVIDIA, verify that the CUDA toolkit is installed and `nvidia-smi` returns valid output. You can manually override the backend in your configuration.

## 8. SharePoint Subscription Expired
**Symptom:** New documents in SharePoint are no longer being indexed automatically.
**Resolution:**
SharePoint webhook subscriptions expire after 3 days. TriMCP includes an hourly cron job to renew these. Check the logs for the `renew_subscriptions` job. If it failed, you can manually trigger a renewal or force a resync using the `force_resync_bridge` MCP tool.

## 9. Active Directory UPN Mismatch
**Symptom:** Users cannot authenticate in Multi-User mode, or their document permissions do not match.
**Resolution:**
Ensure the User Principal Name (UPN) provided by your Identity Provider matches the UPN format expected by TriMCP. Check your AD sync configuration and ensure the `user_id` passed to the API matches the directory UPN.

## 10. Tree-sitter Grammar Compilation Fails
**Symptom:** Errors related to `tree-sitter` or missing C++ compilers during setup.
**Resolution:**
TriMCP now uses the pre-compiled `tree-sitter-language-pack`. Ensure you are using the latest version of the codebase. If you are adding custom grammars via the `add_custom_grammar` script, you must have a valid C++ build environment (e.g., Visual Studio Build Tools on Windows) installed.
