# Source-of-truth hierarchy

The repository uses different sources of truth for different responsibilities.

1. A certified release manifest is authoritative for a published research result.
2. A versioned machine-readable contract is authoritative for structure and invariants.
3. Source code at the commit recorded by the manifest is authoritative for implementation.
4. Test and certification evidence is authoritative for acceptance claims.
5. Human documentation explains the system but cannot override a contract or manifest.
6. Historical and legacy material is non-authoritative unless explicitly referenced.

When implementation intentionally changes a frozen contract, the change requires:

- a new contract version or an explicit composition contract;
- an Architecture Decision Record;
- deterministic validation;
- migration and compatibility notes;
- release evidence before the new definition becomes authoritative.

Database rows are operational indexes and state. They do not replace immutable
artifact manifests or certified analytical releases.
