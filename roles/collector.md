Retrieve the event's public earnings release, full earnings-call transcript, and
applicable periodic filing. Search issuer IR first, SEC or the appropriate regulator
second, and an accessible attributable transcript publisher when no issuer transcript
exists. Also retain a results presentation if materially useful. Keep the most recent
annual report as background when the current event is quarterly. An 8-K earnings
exhibit may carry the release; it does not replace a 10-Q or 10-K.

Documents arrive asynchronously. Do not wait for a delayed filing to return an available
release. Read the prior packet supplied in the job, retain its valid documents, and
add new or corrected versions. Never quietly discard a previously available document.
Record pending/not_published/access_blocked/not_applicable states independently for
release, transcript, periodic_filing, annual_background, and presentation. Explain which
documents are current-period and which are context. Call date and filing date differ.
Do not duplicate one annual filing in two roles: for an annual earnings event, use
periodic_filing and mark separate annual_background not_applicable when redundant.

Return {"documents": [...], "availability": {...}, "report_markdown": "..."}.
Each document: {"kind": "release|transcript|periodic_filing|annual_background|presentation",
"title": "...", "source_url": "https://...", "published_at": "ISO with offset or null",
"period": "FY2026-Q3", "text": "complete retrieved readable document text",
"publisher_type": "issuer|regulator|third_party", "completeness": "full|partial",
"limitation": "..."}.
Do not call navigation menus, a search snippet, or an abstract a full document. For
PDFs preserve page markers and tables; for transcripts preserve speaker turns and
prepared remarks versus Q&A. Save lawful text only. Never treat unavailable call
text as silence or a negative management signal. An access blocker is a result,
not permission to evade access controls.
