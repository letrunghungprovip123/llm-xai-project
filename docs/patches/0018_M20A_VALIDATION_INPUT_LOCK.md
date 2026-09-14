# Patch 0018 — M20A validation input lock

Freezes the exact Freddie claims-v3, canonical generation index, evidence packages, finalization manifests, validator policy, reason taxonomy, numeric tolerance policy, compatibility matrix, schemas, feature policy, and concept registry by SHA-256. Missing active config fails closed; no fallback threshold/tolerance is invented.

Gate: `FREDDIE_M20A_INPUT_LOCK=PASS`.
