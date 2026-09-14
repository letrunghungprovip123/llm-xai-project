# Patch 0015 — M18B offline replay and extraction closure

Builds a new effective extraction artifact. The original `full/` artifacts remain untouched. The 447 frozen responses are replayed through the same authoritative parser/postprocessor and represented by deterministic synthetic replay attempts so the existing stored-response finalizer can reproduce them without a provider call.

Gate: `FREDDIE_M18_EXTRACTION_CLOSURE=PASS` with 648/645/3 and 645/645 usable claim coverage.
