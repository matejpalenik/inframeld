# Place documentation around the user's journey

Alice may be installing Inframeld, using an existing installation or adding an API integration. The home page gives her these choices. It then routes her into the stable sections below. Readers should not need to understand backend modules or the delivery backlog to find a useful task.

This is the approved information architecture. Preserve the section names, entry names and ordering. The actual routes live in `apps/docs/src/lib/navigation.json`. Add detailed pages beneath or through these entries instead of inventing a competing top-level tree.

```text
Documentation home
│
├── Get started
│   ├── Choose your starting point
│   ├── Install Inframeld
│   ├── Install the CLI
│   ├── Connect and sign in
│   └── Quickstart: get an answer from your documents
│
├── Product
│   ├── What is Inframeld?
│   ├── How Inframeld works
│   ├── Projects, people and permissions
│   ├── Documents, versions and collections
│   ├── Models, processing and search
│   ├── Pipelines and builds
│   ├── Evaluation and comparisons
│   ├── Deployments and releases
│   └── Glossary
│
├── Guides
│   ├── Add and manage knowledge
│   ├── Configure models and processing
│   ├── Configure pipelines and ask questions
│   ├── Evaluate answer quality
│   ├── Publish, update and roll back
│   ├── Manage Projects and access
│   └── Automate tasks and recover operations
│
├── CLI and SDKs
│   ├── CLI
│   │   ├── Overview and setup
│   │   ├── Configuration
│   │   ├── Command reference
│   │   └── JSON output, exit codes and automation
│   ├── HTTP and cURL
│   ├── Python SDK
│   ├── TypeScript SDK
│   └── Rust SDK
│
├── API reference
│   ├── Overview and authentication
│   ├── Discovery and health
│   ├── Projects and access
│   ├── Documents, collections and sources
│   ├── Processing and search
│   ├── Pipelines, queries and builds
│   ├── Evaluation
│   ├── Deployments and releases
│   └── Operations, results and errors
│
├── Self-hosting
│   ├── Requirements and deployment configuration
│   ├── Secure your installation
│   ├── Monitoring and troubleshooting
│   ├── Backup and restore
│   └── Upgrades and compatibility
│
└── Changelog and support
```

## Choose the right home

| Reader need | Location | Example |
| --- | --- | --- |
| Reach a first supported result | Get started | Install the CLI, then register a connection. |
| Understand the product model | Product | Explain why a Project ID survives a rename. |
| Complete an ongoing task | Guides | Rename a Project using its current metadata revision. |
| Set up a client or look up its behavior | CLI and SDKs | Build the unpublished TypeScript package or inspect version JSON fields. |
| Find an exact delivered HTTP operation | API reference | Find the metadata PATCH parameters and native request schema. |
| Operate an installation | Self-hosting | Find the maintained backup procedure and its limits. |
| Find releases or get help | Changelog and support | Report a problem with a safe version and error code. |

The page's purpose and the navigation taxonomy are separate decisions. A task guide uses the task pattern regardless of its domain. A concept page explains the model without becoming a list of endpoint fields. The API reference uses native generated shapes and links back to a task that teaches their use.

The home page needs a brief purpose, starting-point choices and clear routes to the major sections. Keep advanced recovery details in Guides. Keep machine schemas in reference. Do not copy the entire navigation tree into the opening paragraph.

## Extend without duplicating

The seven guide entries are topic hubs. Link detailed delivered tasks from their hub and the relevant client/reference pages. Existing detailed guide URLs remain useful. The four CLI entries likewise link to focused command details such as version output. A shared model catalog supports all API sections without adding another top-level category.

For example, a delivered upload workflow would update the knowledge guide hub, add a focused upload task, replace the first-answer availability notice only when its whole path works, and add the actual operation to the documents API section. Its client examples use the central setup pages. It does not need a new Uploads top-level group or five copies of installation instructions.

Update a section's explanatory page and navigation together. Retain stable task routes and anchors, or supply an explicit route-preservation plan when authorized scope requires a move. Internal architecture, ADRs and developer setup remain in their existing owners. Link them where a preview user needs a maintained operator procedure rather than copying the manual.

## Represent unfinished capabilities honestly

The approved hierarchy includes capabilities still being delivered. A useful availability page states what is missing, explains the relevant model and links to a supported action. It contains no imaginary commands, public issue-by-issue progress log or empty code tabs. A visible preview boundary is better than a walkthrough that cannot be completed.

For example, the first-answer page can explain documents → collection → processing → pipeline → answer and point to working installation/health tasks until upload and query are delivered. Concept pages may explain accepted behavior with a clear availability statement. They must not claim that a complete runtime or user journey was tested.

## Check the reader's path

Follow three routes: a new installer, a user connecting to an existing installation and a developer choosing an SDK. Each should reach prerequisites, an action and an interpretable result without guessing a command or package source. Also check a reader who searches directly for a detailed guide, since they may not have visited the home page.

Use existing navigation, `CodeGroup`, metadata layouts and content checks. The sidebar supports the single child level needed by CLI. Do not introduce a generic navigation platform, a second API specification or a new documentation test runner. `pnpm check:docs` owns the maintained gate. Actual request execution and visual inspection remain distinct evidence.
