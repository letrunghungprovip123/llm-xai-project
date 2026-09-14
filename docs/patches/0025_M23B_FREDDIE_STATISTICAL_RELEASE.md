# Patch 0025 — M23B Freddie statistical release

This patch executes the existing repeated-measures/Wilcoxon core on the
certified 648-row Freddie analytical mart.  It validates the exact M21 frozen
missingness identities, matches the 33-contrast registry, computes 18 option
and 33 contrast case-bootstrap intervals, and performs two clean builds whose
artifact hashes must match before atomic promotion.

Primary inference uses all 36 canonical cases because unusable primary E2E
cells are operational zeros.  Complete-case semantic sensitivity is derived
from the frozen usability matrix (33 cases for the current Freddie release),
not hard-coded in the common engine.
