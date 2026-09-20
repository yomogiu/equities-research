---
name: analyze-stock
description: Conduct question-led, primary-source public-equity research for a listed company or ticker. Use when the user asks to analyze, investigate, underwrite, compare, value, revisit, buy, sell, short, size, or build a thesis on a stock; needs a quick screen, full initiation, position review, or event update; or wants a coding agent to collect a traceable equity-research evidence packet. Do not use for private companies, credit-only work, generic company summaries without an investment decision, or personalized financial advice.
---

# Analyze Stock

Build a decision-oriented public-equity underwrite. Ask the investor only for inputs that change the work, then make the agent collect and reconcile the evidence.

## Workflow

1. **Verify the security.** Resolve issuer, ticker, exchange, security class, reporting currency, fiscal year-end, and analysis date. Do not research an ambiguous ticker.
2. **Run the investor intake.** Read [references/intake.md](references/intake.md). Ask unresolved material questions together before substantial research. Apply its stated defaults when the user explicitly delegates judgment or declines to answer.
3. **Choose the mode.** Use `quick_screen`, `full_underwrite`, `position_review`, or `event_update`. A quick screen may promote an idea to deeper work; never present it as completed diligence.
4. **Create the research plan.** Read [references/research-contract.md](references/research-contract.md). Identify the primary sources, market data, historical periods, valuation inputs, and sector-specific evidence required for the selected mode.
5. **Research current facts.** Browse or use approved data sources because prices, filings, estimates, ownership, and events are time-sensitive. Prefer primary evidence. Record source URLs, periods, units, and as-of timestamps with every decision-relevant fact.
6. **Build the common analytical spine.** Complete security identity, fully diluted capitalization, enterprise-value bridge, business model, historical financials, earnings quality, capital allocation, forecast drivers, valuation, embedded expectations, catalysts, risks, falsifiers, and scenarios.
7. **Branch by economics.** Read only the relevant sections of [references/sector-overlays.md](references/sector-overlays.md). Use more than one overlay for mixed businesses.
8. **Challenge the emerging thesis.** Seek evidence that would make the current conclusion wrong. Distinguish a good company from a mispriced security and a plausible story from a sufficiently evidenced thesis.
9. **Package the evidence.** For durable work, create `artifacts/stock-analysis/<ticker>/<YYYY-MM-DD>/` unless the user specifies another location. Copy [assets/research-packet.template.json](assets/research-packet.template.json) to `research-packet.json`, populate it, and add `source-register.md` plus the requested human-readable artifact. Do not create files for a narrow chat-only answer.
10. **Deliver the decision.** Read [references/output-contract.md](references/output-contract.md). Lead with the research posture and decision hinge, not the company description. State the data cut-off, confidence, underwriting stage, unresolved conflicts, and next diligence step.

## Analytical principles

- Start with filings and the capital structure before using valuation multiples.
- Sanity-check scale, units, share classes, splits, dilution, debt, leases, minority interests, and non-operating assets.
- Understand the product, customer, value chain, and unit economics before forecasting.
- Normalize several periods; separate organic growth, acquisitions, currency, accounting changes, and one-offs.
- Reconcile GAAP earnings, operating cash flow, capital expenditure, dilution, and economic free cash flow.
- Value the security with a method appropriate to its economics. Pair equity value with equity claims and enterprise value with enterprise claims.
- Backsolve what the current price requires. Make growth, margins, duration, reinvestment, and terminal assumptions explicit.
- Treat management quality as evidence only when linked to execution, incentives, capital allocation, or governance.
- Separate facts, company claims, consensus, calculations, assumptions, and analyst judgment.
- Apply this methodology independently. Do not cite, emulate, or import the views, language, risk preferences, or conclusions of named investors or commentators unless the user explicitly requests them as a source.
- Use scenario probabilities only when the user wants expected value; never hide uncertainty behind false precision.
- Label outputs `screen`, `watchlist`, `preliminary_underwrite`, or `underwritten_view`. Reserve the last label for work with sufficient primary evidence, valuation support, and falsifiers.

## Research boundaries

- Do not invent missing market data, estimates, clinical probabilities, or management claims.
- Do not rely on generated summaries when the underlying filing, release, transcript, or dataset is available.
- Do not turn the result into personalized financial advice. Discuss the security, thesis, and portfolio considerations for human review.
- If a key input is unavailable, state exactly which conclusion it prevents and continue with a clearly limited posture when useful.
