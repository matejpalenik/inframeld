# Review a CLI task from first use to recovery

Alice has installed the CLI and wants to inspect a resource in the intended account. She should not need to read internal architecture, infer which target is active or parse human prose in a script. Follow her actual command journey and inspect the supported public interface before recommending changes.

## Authority and comparison sources

The accepted [output and automation contract](../../inframeld-application-contracts/references/cli-output-and-automation.md), [result contracts](../../inframeld-application-contracts/references/cli-result-contracts.md), [targets and accounts](../../inframeld-application-contracts/references/cli-targets-and-accounts.md) and [change review](../../inframeld-application-contracts/references/cli-change-review.md) own Inframeld behavior. Read the relevant section for the changed command. The [Rust CLI structure](../../inframeld-rust-standards/references/cli-structure.md) owns authored implementation conventions.

[Command Line Interface Guidelines](https://clig.dev/) provides general principles for discoverable help, composable output, actionable errors, non-interactive operation and safe destructive behavior. Use those principles to explain friction, not to override accepted product contracts.

The [Stripe CLI documentation](https://docs.stripe.com/cli) is a useful first-use example: installation and authentication lead to a small observable developer task. [IBM Cloud CLI documentation](https://cloud.ibm.com/docs/cli?topic=cli-ibmcloud_cli) is useful for reviewing explicit account and target context. Neither product's vocabulary, flags or hosted authentication flow is automatically right for Inframeld.

## Follow the smallest useful path

Start with the documented installation and the exact implemented command. Check offline `--help` and `--version`, parent-command discovery, examples and invalid argument feedback. An offline help request should not unexpectedly require credentials or a live server. Check that errors name the missing input and an available next action. Do not recommend aliases or command groups merely because another CLI has them.

Check target selection before an effect. The developer should understand which account, installation and scope a command will use and how an explicit override relates to stored defaults. Preserve the accepted precedence and ambiguity rules. A target display is not permission to act. Current authorization still applies on the server.

Follow one successful operation through its meaningful result. A confirmation should identify what happened, using safe identifiers and supported follow-up commands. An asynchronous admission must not be described as completed work. Empty results should be distinguishable from a failed request when the contract makes that distinction public.

## Treat automation as an interface

Inspect the actual JSON schema, exit status and output streams, not only a terminal screenshot. Human tables, color and progress belong to human presentation. Scripts must receive the documented machine result without progress lines or interactive prompts contaminating stdout. Error details and diagnostics must follow the accepted stream contract.

Check a non-TTY invocation and an invalid request where relevant. A command that requires confirmation needs a supported non-interactive outcome. Do not invent a force flag or assume that piping an answer is supported. Timeout, cancellation and retry guidance must preserve possible effects and the original operation identity.

Stable JSON means meaningful fields and values remain consistent under the accepted compatibility policy. It does not require exposing private internal state. An unresolved lookup must retain its intentionally limited public shape. Optional human prose can improve while machine contracts remain exact.

## Review failure as part of the task

Test or trace the supported failure that changes the developer's next choice: wrong target, missing permission, invalid input, connection loss, unresolved observation or failed job. Explain cause, consequence and available action. Avoid generic “try again” advice when resubmitting can create a new effect.

Inspect credential and diagnostic handling. Help, logs and error output must not disclose secrets or imply unauthorized fallback. A current account switch must not rewrite retained original request context. A useful message may deliberately omit whether protected history exists.

Check cancellation and cleanup at the relevant lifecycle boundary. Distinguish a local command ending from a server action being canceled. If the command cannot know the remote outcome, the user-facing result must preserve that uncertainty and point to the supported observation path.

## Bound the finding

A finding needs an implemented or in-scope supported task, concrete trigger, expected contract, observed or strongly inferred behavior and consequence. “Stripe has this flag” is not a finding. “JSON mode emits a progress sentence before the object, so the documented pipe fails to parse” is one when demonstrated.

Do not demand a larger framework for a single command, add a generic plugin architecture or build future Studio workflows into the CLI. Explain the smallest correction that preserves accepted behavior. Use Review's priority and report format, and identify unavailable execution evidence rather than replacing it with a guessed pass.
