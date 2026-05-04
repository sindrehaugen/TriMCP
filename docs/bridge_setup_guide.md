# Bridge Setup Guide

This guide details the configuration of the Document Bridge System (Push Architecture) for TriMCP. The push architecture ensures that document changes trigger near-instant indexing (seconds, not hours) without polling waste, as only changed files are processed. This requires a publicly-reachable HTTPS endpoint to receive webhook callbacks from cloud providers.

## 1. SharePoint / OneDrive (Microsoft Graph)

### OAuth Application Setup
1. Navigate to the Azure Active Directory (Entra ID) portal.
2. Create a new App Registration.
3. Add the following Microsoft Graph API permissions (Application permissions for service-level access):
   - `Sites.Read.All`
   - `Files.Read.All`
4. Grant admin consent for the tenant.

### Webhook Registration
- **Endpoint:** `POST /v1.0/subscriptions`
- **Payload:**
  ```json
  {
    "changeType": "updated",
    "notificationUrl": "https://<YOUR_PUBLIC_URL>/webhooks/graph",
    "resource": "/sites/root/drives/<DRIVE_ID>/root",
    "expirationDateTime": "<TIMESTAMP_MAX_3_DAYS>",
    "clientState": "<YOUR_SECURE_CLIENT_STATE>"
  }
  ```
- **Subscription Lifetime:** Maximum 3 days. A cron job must be configured to renew the subscription before expiration.
- **Validation:** Microsoft Graph will send a `validationToken` query parameter upon creation. The receiver automatically echoes this token within 10 seconds to confirm the endpoint.

## 2. Google Workspace / Drive

### OAuth Application Setup
1. Navigate to the Google Cloud Console.
2. Enable the Google Drive API.
3. Create credentials:
   - **Service Account** with Domain-Wide Delegation (recommended for enterprise-wide access).
   - Alternatively, configure an OAuth 2.0 Client ID for user consent.

### Webhook Registration
- **Endpoint:** `POST https://www.googleapis.com/drive/v3/files/<FOLDER_ID>/watch` (or `/drive/v3/changes/watch` for org-wide changes).
- **Payload:**
  ```json
  {
    "id": "<UNIQUE_CHANNEL_ID>",
    "type": "web_hook",
    "address": "https://<YOUR_PUBLIC_URL>/webhooks/drive",
    "token": "<YOUR_SECURE_CHANNEL_TOKEN>"
  }
  ```
- **Subscription Lifetime:** Up to 7 days. A cron job must be configured to renew the channel.
- **Validation:** Google sends an `X-Goog-Resource-State: sync` header on initial subscription. The receiver validates the `X-Goog-Channel-Token` header on every callback to ensure authenticity.

## 3. Dropbox

### OAuth Application Setup
1. Navigate to the Dropbox App Console.
2. Create a new app (Scoped access).
3. Under the **Permissions** tab, enable the following scopes:
   - `files.metadata.read`
   - `files.content.read`

### Webhook Registration
- **Configuration:** In the Dropbox App Console, navigate to the **Webhooks** section.
- **Webhook URI:** Enter `https://<YOUR_PUBLIC_URL>/webhooks/dropbox` and click "Add".
- **Subscription Lifetime:** Permanent (no renewal required).
- **Validation:** Dropbox will send a `GET` request with a `challenge` parameter. The receiver automatically echoes this challenge to verify the endpoint.
- **Security:** All incoming `POST` notifications are verified using the `X-Dropbox-Signature` header, which contains an HMAC-SHA256 hash of the request body using your App Secret.

## 4. Webhook Receiver Configuration

The FastAPI webhook receiver (`trimcp/webhook_receiver/main.py`) requires specific environment variables to validate incoming payloads from the cloud providers.

Configure the following environment variables in your deployment environment:

- `DROPBOX_APP_SECRET`: The App Secret from your Dropbox App Console. Used to verify the `X-Dropbox-Signature` HMAC-SHA256 hash.
- `GRAPH_CLIENT_STATE`: A secure, random string generated during the MS Graph subscription creation. Used to validate the `clientState` field in incoming Microsoft Graph payloads.
- `DRIVE_CHANNEL_TOKEN`: A secure, random string provided as the `token` during Google Drive channel creation. Used to validate the `X-Goog-Channel-Token` header in incoming Google Drive webhooks.

Ensure the webhook receiver is exposed via a publicly accessible HTTPS URL to receive these payloads. Local deployments without public ingress will fall back to scheduled pull mechanisms.