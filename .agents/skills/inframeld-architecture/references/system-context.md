# Inframeld in its surroundings

<a id="inframeld-in-its-surroundings"></a>

Alice wants private answers from Support's handbook. SupportBot needs an application identity to ask the same product questions. The operator needs to install and recover the server. These are different relationships with one software system.

This is the **accepted system context**. The Inframeld box means the product as a whole, not one process. External boxes describe dependencies or callers. Some may run on the same server. Their position here does not prescribe hosting or public network access.

```mermaid
---
title: "Inframeld system context - accepted scope"
---
flowchart TB
    Alice["Human users<br/>Browser and Rust CLI"] -->|"Manage permitted resources and ask questions"| Product["Inframeld<br/>Private knowledge, answers, evidence and release control"]
    Bot["Application clients<br/>For example SupportBot"] -->|"Use explicit application permissions"| Product
    Operator["Installation operator"] -->|"Install, configure and recover the host"| Product
    Product -->|"Human identity, sessions and CLI OAuth"| Ory["Ory Kratos and Hydra"]
    Ory -->|"Optional configured sign-in"| IdP["Organisation identity provider"]
    Product -->|"Approved remote model requests"| Models["Model providers<br/>Hosted or operator-controlled endpoints"]
    Product -->|"Explicit bounded read-only sync"| Sources["S3-compatible source storage"]
```

Arrows name interactions across the product boundary. They do not grant permission or show code imports. Application keys identify a separate local application account. Human browser and CLI credentials identify the same existing human. Host administration is separate from authority through product APIs.

<a id="what-the-system-promises-to-coordinate"></a>

## What the system promises to coordinate

Knowledge records exact source versions. Indexing prepares verified search data. Pipelines executes captured settings against currently permitted evidence. Evaluation supplies offline comparisons. Releases controls serving selection. Access checks who may do each protected operation now.

A useful answer needs these owners to cooperate. Uploading a file does not itself make it searchable. A ready build does not itself change traffic. A successful historical result does not preserve permission after a grant is removed.

External model calls pass through the shared ModelGateway boundary. Selecting an endpoint does not permit a fallback provider after failure. Source sync uses reviewed saved scope and explicit credentials. Importing configuration does not contact a source automatically.

<a id="where-to-zoom-next"></a>

## Where to zoom next

- Read [System overview](system-overview.md) for processes, storage and trust boundaries.
- Read [Module map](module-map.md) for responsibilities and the owning domain's architecture.
- Read [Document to answer](document-to-answer.md) for Alice's complete product journey.

<a id="status-and-sources"></a>

## Status and sources

This view describes accepted product scope. V1 targets the Rust CLI and small Ory account UI. Full Studio is deferred. The diagram does not establish delivered clients, production identity qualification or measured capacity.

[The product introduction](../../../../docs/ARCHITECTURE.md), [deployment design](runtime-deployment-and-storage.md), [Access](../../inframeld-access-models/references/authorization.md) and [source synchronisation](../../inframeld-knowledge/references/uploads-and-source-sync.md#source-sync) own the details. PostgreSQL, Chroma and SeaweedFS appear in the runtime view because they are parts of the installation rather than independent product users.
