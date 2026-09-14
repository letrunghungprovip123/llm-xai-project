# Patch 0017 — M19B Freddie finalization release

Runs the existing stored-response replay finalizer on the effective M18 artifacts, proves replay idempotence, then migrates the resulting `claims_v2` artifact to `claims_v3` using the active semantic classifier and compatibility matrix. The Freddie migration deliberately does **not** import the historical Home Credit 260-row manual semantic-correction fixture.

Both replay and semantic migration are deterministic and provider-free. No Freddie final claim count is hard-coded.

Gate: `FREDDIE_M19_FINALIZATION=PASS`.
