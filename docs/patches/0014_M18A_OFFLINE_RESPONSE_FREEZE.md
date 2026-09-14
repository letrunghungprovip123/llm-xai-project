# Patch 0014 — M18A offline response freeze

Freezes the 447 manually supplied provider-level responses as a deterministic, separately identified offline lineage. Historical provider attempts and failures are read-only inputs. Every payload is revalidated through the authoritative TypeScript atomic-claim parser against the canonical generation document.

Gate: `FREDDIE_M18A_OFFLINE_RESPONSE_FREEZE=PASS`.
