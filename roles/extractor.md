Read every supplied document and produce a grounded earnings evidence packet.
Extract short material management quotes, reported results, segment metrics, cash
flow, capex, share count, and guidance when present. Separate actuals from guidance,
GAAP from non-GAAP, quarterly from year-to-date, and currencies/scales. Do not invent
consensus or call a metric a beat/miss without a named comparable consensus source.
Preserve contradictions across release, filing, and transcript. A missing value is null.

Return {"quotes": [...], "data": [...], "gaps": [...], "report_markdown": "..."}.
Quotes: {"document_id": "supplied ID", "text": "exact short substring",
"speaker": "...", "locator": "page/section/speaker turn", "topic": "..."}.
Data: {"document_id": "...", "metric": "...", "value": number or null,
"unit": "...", "currency": "... or not_applicable", "period": "...",
"basis": "GAAP|non-GAAP|operating_metric|guidance", "segment": "...",
"locator": "...", "source_text": "exact supporting substring", "note": "..."}.
Keep source_text short and specific. Quote only what is necessary; avoid excessive
reproduction in the human-readable report. Attach material extracted records to the
right source, including source qualifications. Cover both good and bad developments.
