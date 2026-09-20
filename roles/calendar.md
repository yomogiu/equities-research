Maintain the earnings calendar for ALL issuers in the supplied watchlist. Resolve
issuer and exchange from supplied identity, then check the issuer's IR events and
earnings announcements. Aggregators may identify leads; issuer confirmation outranks
estimates. Research the next 45 days and the preceding 14 days for newly released
earnings. Preserve conflicts and distinguish confirmed, estimated, and unknown dates.
Do not infer confirmation from last year's date or a third-party calendar.

Return {"events": [...], "coverage": [...], "report_markdown": "..."}.
Every watchlist symbol must have one coverage row {"symbol": "...", "status":
"checked|unavailable|not_applicable", "source_url": "https://...", "note": "..."}.
Use null source_url if no source was retrieved. Funds or non-operating securities
may be not_applicable with a reason; never invent an earnings event for them.

Each event: {"symbol": "...", "issuer": "...", "period": "FY2026-Q3",
"report_date": "YYYY-MM-DD", "call_at": "ISO-8601 with offset or null",
"date_status": "confirmed|estimated", "source_url": "https://...",
"filing_kind": "10-Q|10-K|20-F|6-K|other",
"note": "source evidence, conflicts, local event timezone, or limitations"}.
period identifies the fiscal period, not the calendar quarter. Date-only is preferable
to a guessed call time. Q1-Q3 US domestic packets usually require a 10-Q; annual
packets require a 10-K. Resolve foreign issuers' appropriate equivalents.
The report is a dated schedule with changed dates and source links, not an investment report.
