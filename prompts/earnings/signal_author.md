# Signal author

Read the candidate `report.md`, the structured state and finding catalogue in `artifacts.json`, and relevant original evidence. Select 1–4 material developments; do not force a colour distribution or invent a new report claim. Direction applies to the particular development, not the company or a trade.

Return `report_sha256, signals: [{id,finding_id,direction,evidence_basis,label,summary,comparison,period,rationale,citations,passage_ids}]`. IDs are `signal-1` through `signal-4`; finding IDs must come from the supplied catalogue. Directions: `improving, deteriorating, conditional, unresolved`. Evidence bases: `reported_result, management_guidance, management_commentary, analyst_inference`. Label ≤60 characters, summary ≤200, comparison/rationale ≤240, period ≤100. Preserve conditions and counterevidence. Distinguish management commentary from formal guidance. Read each cited scope and selected passage, plus the complete Markdown report, through the access API.
