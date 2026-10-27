# Authenticated listing header transition

The explicit `stockanalysis-authenticated-listing-header-currentness-v7` proof
qualifies only a single exact publisher listing header from NYSE to TXSE. Ordinary
creation still uses v6, and v1–v6 replay keeps its original rules. No report model,
financial fact, archived source or source qualification is changed.

The caller must bind an `authenticated-nyse-txse-primary-listing-v1` authority
artifact. It identifies the original SEC issuer, publisher URL, registrant name,
unchanged ticker/currency and effective date, plus exact original fetch receipt
and raw hashes for two sources. Replay checks actual same-URL HTTP200 HTML
receipts, the issuer's SEC filing CIK and explicit unchanged-ticker transfer
statement, and the destination exchange's completed primary listing announcement.
The effective date must precede the transcript observation. This deliberately
supports a narrow statement/route grammar; other cases fail closed.

Only one exact `mt-px text-tiny text-faded` listing-header div before all call
blocks may change. The registrant label, ticker, USD currency, original source URL
and every other part of the strict v6 signature remain bound. No general exchange
or metadata mask is added. The archived and observed full bytes/text retain their
own hashes, and the comparison records the explicit transition. Every authority
artifact, fetch receipt and raw primary document becomes an immutable request
input through the existing source-currentness bindings.

Use a new explicit proof and derived refresh receipt, preserving original failed
receipts. Independent old/new source qualification must still pass before report
admission. This is listing-metadata qualification only, never new fiscal evidence
or report acceptance. Fresh full independent review and remote-byte completion
proof remain required.
