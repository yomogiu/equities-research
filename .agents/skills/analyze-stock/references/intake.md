# Investor intake

Ask only questions whose answers change research scope, valuation, scenarios, or action. Do not ask the user for facts the agent can research.

## Required identity

Confirm the ticker, exchange, and security class. Ask a direct question when any of these is ambiguous.

## Core questions

Ask unresolved questions together. Use at most three questions in a bounded input tool call; combine compatible choices or use one compact plain-text prompt when more context is materially required.

1. **Decision:** Is this a new long, current holding, possible short, watchlist idea, or learning exercise?
2. **Horizon:** Is the decision event-driven, 3–12 months, 1–3 years, or 3–5+ years?
3. **Exposure:** Do you own it? If relevant, ask for direction, approximate portfolio weight, and cost basis. Make this optional.
4. **Depth:** Choose a quick screen, full underwrite, position review, or event update.
5. **Hinge:** What question, concern, or existing thesis should the analysis try hardest to resolve?
6. **Artifact:** Ask only when unclear whether the user wants chat, a durable report, an evidence packet, or a model.

## Defaults

When the user delegates choices or declines to answer, use:

- Decision: new long/watchlist candidate
- Horizon: 3–5 years
- Exposure: no position information supplied
- Depth: full underwrite for “analyze”; quick screen for “take a quick look”
- Hinge: determine what is priced in, whether the market is wrong, and what falsifies the thesis
- Artifact: concise chat for narrow questions; durable report plus evidence packet for substantive research

State defaults once and continue. Do not repeatedly ask for optional portfolio context.

## Default question form

For a bare request such as “Analyze TICKER,” ask:

> Before I underwrite it: is this a new position, existing holding, possible short, or watchlist idea; what is your time horizon; and do you want a quick screen or full underwrite? If you have a thesis or concern, include it. Otherwise I’ll focus on what is priced in and what would falsify the case.

If the user already supplied some answers, ask only for the missing choices that materially change the work. After the response, begin research; do not turn the intake into an interview.

## Adaptive examples

- “Quick look at PLTR” already resolves depth. Ask only for decision/horizon when material, then research.
- “Review my 5% MSFT position at a $410 basis after earnings” resolves decision, exposure, and mode. Ask only for horizon or a specific concern if it changes the recommendation.
- “Analyze NVDA; use your judgment” invokes the defaults. State them briefly and proceed without another question.

## Adaptive follow-ups

After the first evidence pass, ask a follow-up only when the answer would change the valuation method, scenario definition, or investment action. Examples:

- Whether to evaluate consolidated equity or a sum-of-the-parts case
- Whether a current position can be increased, held, trimmed, hedged, or exited
- Whether the user permits a high-uncertainty outcome such as pre-revenue biotech or distressed dilution risk
- Whether benchmark, tax, liquidity, ethical, or mandate constraints matter

Never ask the user to provide revenue, margins, filings, competitive data, or current price when the agent can collect them.
