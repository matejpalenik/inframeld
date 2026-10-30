# Sources behind the writing guide

These are Inframeld editorial observations of public documentation checked on 2026-10-29. They are not an official OpenAI writing guide, copied product instructions or a requirement to imitate page appearance. The reusable pattern is purpose, setup, a small working example, an interpretable result and a useful next step.

| Primary source | Observed technique | Inframeld adaptation |
| --- | --- | --- |
| [API documentation overview](https://developers.openai.com/api/docs) | Introduces a useful API task before routing readers into focused capabilities. | Open a section with what the reader can accomplish. Link to focused guides rather than listing internal modules. |
| [Developer quickstart](https://developers.openai.com/api/docs/quickstart) | Puts setup before a small executable example and connects language choices to the same first result. | Name the file, supply imports and lifecycle, show the run command and explain the output. Verify our actual local SDK setup. |
| [Streaming responses](https://developers.openai.com/api/docs/guides/streaming-responses) | Explains why streaming changes the reading experience, then shows the enabling option and incremental consumption. | Explain the purpose of an option before its mechanics. Preserve transport and product outcome boundaries. |
| [Error codes](https://developers.openai.com/api/docs/guides/error-codes) | Groups recognizable errors with causes and corrective actions. | Connect an observable failure to a supported next step. Our authorization, uncertainty and retry rules remain authoritative. |
| [API reference overview](https://developers.openai.com/api/reference/overview) | Separates exact interface details from task learning and conceptual guides. | Keep exact delivered shapes in native OpenAPI and generated clients, with focused explanatory examples in MDX. |

The guide also draws on [Diátaxis](https://diataxis.fr/) to distinguish learning, task completion, understanding and exact lookup. It does not require a separate page of every kind for each feature. Use the page that serves the actual need and link to existing material.

[Next.js MDX documentation](https://nextjs.org/docs/app/guides/mdx) describes the supported App Router approach. The copied Protocol source and its installed versions own our actual component names, metadata exports and build behavior. The guide must be revised when that pipeline changes.

The following boundaries are deliberate:

- Public OpenAI credential setup is not an Inframeld credential contract.
- An OpenAI retry suggestion does not authorize an Inframeld write or paid provider retry.
- A concise example does not justify omitting a current authorization or partial-effects condition.
- A shared page style does not make unimplemented CLI commands or unpublished packages available.
- Source observations are editorial evidence, not evidence that an Inframeld example ran.

Use original examples and describe observed techniques in your own words. Recheck sources when a linked behavior or external capability matters, or when revising this editorial guide. Ordinary prose edits can apply the stable patterns without a new browsing pass for every page.
