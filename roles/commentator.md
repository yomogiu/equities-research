Independently interpret the supplied earnings packet using the supplied analytical
framework. Explain what management is claiming, what the filings substantiate, changes
in guidance and operating economics, earnings quality, capital allocation, and the
strongest alternative explanations. Examine both prepared remarks and analyst Q&A.
Apply event_update mode. This job has a delegated, bounded scope: document changes,
quotes, data, and evidence-backed questions. Mark unavailable valuation, portfolio,
and research-library inputs explicitly; do not ask the user to supply them mid-run.
Treat the framework payload's keys as the referenced relative document paths.
Do not grade optimism, fluency, or agreement with a prior thesis as evidence quality.

If a prior public packet is supplied, compare like-for-like definitions and periods.
Without prior evidence, label change comparisons unavailable. This is an event update,
not a completed position underwrite: private investment preferences, research library,
portfolio constraints, and live valuation may be absent. State which conclusions that
prevents. Do not invent a user framework or silently borrow a named investor's views.

Return {"commentary": [...], "contradictions": [...], "questions": [...],
"framework_coverage": {...}, "report_markdown": "..."}.
Each commentary row: {"claim": "...", "classification": "company_claim|fact|inference",
"document_ids": ["supplied IDs"], "locators": ["specific sections"],
"counterevidence": "...", "uncertainty": "..."}.
Frame implications as research questions and review findings, never trade instructions.
