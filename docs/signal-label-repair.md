# Bounded signal-label repair

`earnings_signal_label_repair` creates a separately authorized private edition from
independently blocked signal annotations. It replays both the original signal
verifier and the original accepted-report exporter at their frozen code identities.
Only labels on explicitly rejected signals can change. The plan binds original
signal bytes, exact old/new labels and existing source references; every other
signal field and the accepted report remain unchanged.

There is no author call. One new independent reviewer assesses the entire signal
pack with the accepted report and original sources. Acceptance requires all signal
decisions and rubric criteria to pass. A blocked, uncertain or oversized review
stops; it cannot create another review or author round. A sibling exclusive claim
prevents a second successor. Historical measured signal usage and fresh review
usage are retained separately. Sources with unknown usage require a different
explicitly supported policy and are rejected here.

The caller must persist the reservation and use the shared execution guard before
model execution. Acceptance is not production completion: private import and a
later fresh remote-byte verification remain required. The pipeline's global enable
flag and source/report artifacts are unaffected.
