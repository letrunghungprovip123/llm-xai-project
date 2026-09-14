# 0021 — M21B Freddie research data mart

Builds the 648-row Freddie generation mart from the M20 deterministic validation release.
The common Home Credit default path is unchanged. Freddie explicitly opts into the
`causal` aggregate column, validates the frozen 645/3 usability topology, preserves all
three unusable rows, and atomically promotes only a fully validated output directory.
No provider execution, model training, or SHAP recomputation is permitted.
