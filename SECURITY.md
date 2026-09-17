# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security vulnerability. Report it privately through [GitHub Security Advisories](https://github.com/Inframeld/inframeld/security/advisories/new).

Include the affected component, reproduction steps, impact, and any suggested mitigation. Remove credentials, personal data, and other secrets from the report. If GitHub's private reporting form is unavailable, contact a repository maintainer privately through GitHub before disclosing the issue publicly.

## Scope and support

The default branch is the supported development line. Inframeld is an early MVP and is not presented as a production-ready hosted service. Security fixes are prioritized according to severity, reproducibility, and whether the issue crosses a documented trust boundary.

## Security expectations for contributors

- Never commit credentials, API keys, tokens, or real customer data.
- Keep dependency lockfiles and security updates reviewable.
- Preserve tenant, authorization, correlation, and audit boundaries described in the architecture specification.
- Add a regression test for security-sensitive behavior when practical.
