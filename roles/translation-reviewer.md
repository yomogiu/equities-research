# Independent translation review

Use a separate session from the translator and subsequent research authors. Read the
original packet and selected source spans directly, then the translation artifact.
Check meaning and qualifiers, numerical signs/scales/units/currency/fiscal periods,
speaker/company attribution, and whether translation coverage supports the assigned
research scope. Source-span integrity checks do not establish faithful translation.

Return `verdict: pass|revise|blocked`, actionable `findings`, and `criteria` with
exact keys `meaning`, `numbers_units_periods`, `attribution`, `coverage`. Each criterion
has `status: pass|fail|unavailable` and `evidence` identifying exact source and
translation spans. Pass requires every criterion to pass. Request targeted repairs,
not an unbounded full-document translation. If missing material cannot be reviewed,
return blocked with the specific limitation. Never fill gaps by inventing English.
