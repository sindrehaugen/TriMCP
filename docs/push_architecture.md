# TriMCP Push Architecture

Subscription renewal for long-lived bridges is handled by the **`trimcp.cron`** scheduler (see [architecture-v1.md](./architecture-v1.md)). The flow below shows ingest from provider webhooks through the worker.

This diagram illustrates the Document Bridge System (Push Architecture) as defined in Section 10.2 of the TriMCP Enterprise Deployment Plan.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Provider as Cloud Provider<br/>(SharePoint / GDrive / Dropbox)
    participant Webhook as Webhook Receiver<br/>(FastAPI)
    participant Redis as Redis Queue<br/>(RQ)
    participant Worker as RQ Worker
    participant DB as TriMCP Database<br/>(Vector/Graph)

    User->>Provider: Edits a file
    Provider->>Webhook: Sends webhook notification
    
    rect rgb(240, 248, 255)
        Note over Webhook: Validation Phase
        Webhook->>Webhook: Validates signature/token
        Webhook->>Provider: Returns 200 OK (within 3 seconds)
        Webhook->>Redis: Enqueues processing job
    end
    
    rect rgb(245, 245, 245)
        Note over Worker: Processing Phase
        Redis-->>Worker: Job dequeued
        Worker->>Provider: Fetches changes via delta API
        Provider-->>Worker: Returns modified files list
        Worker->>Provider: Downloads modified files
        Worker->>Worker: Extracts text (docx/pdf/xlsx)
        Worker->>DB: Calls store_memory + chunks
        Worker->>Redis: Updates last_sync cursor
    end
```
