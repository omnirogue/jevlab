# Security policy

Report vulnerabilities privately through [GitHub Security Advisories](https://github.com/omnirogue/jevlab/security/advisories/new). If private reporting is unavailable, request a private reporting channel from the maintainers without posting exploit details publicly. Include the affected version, impact and a minimal synthetic reproduction. Never send credentials or customer records.

During the pre-1.0 period, fixes target the latest minor release. A response or remediation SLA is not promised.

JevLab is an offline single-user toolkit, not a multi-tenant authorization boundary. The MCP server accepts bounded inline data, exposes no shell or filesystem tools, and writes only protocol responses. Run it under a minimally privileged account. Host applications are responsible for access control and consent around their data.

The legacy CLI's `--judge-cmd` runs a user-specified executable with the launching environment. Only configure trusted commands. The core never needs provider credentials. If your adapter does, pass configuration by environment variable name and never commit values. CLI output paths intentionally write to paths the invoking user supplies.

HTML reports escape labels, contain no JavaScript or external resources, and include a restrictive Content Security Policy. The React studio renders imported labels as text and makes no network requests. Reports may still contain user-supplied judge names and rubric IDs: inspect them before sharing.

Synthetic declarations and automated secret patterns are defense in depth, not proof that arbitrary input is safe to publish. Review fixture provenance and the export manifest. CI checks for excluded source types, private host identifiers, credential patterns and asset drift. No proprietary engine, customer dataset or internal compliance rubric belongs in this repository.
