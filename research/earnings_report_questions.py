"""Versioned expected-question review for new financial-analysis requests.

These checks validate review completeness and repair addresses, not the truth of
an authored answer. Original-source inspection and independent review still apply.
"""
from . import earnings_runtime_common as base

VERSION = 'core-financial-report-questions-v1'
REPORT_LOCATIONS = ('demand','earnings','cash','outlook','qa')
QUESTIONS = {
    'demand': 'What changed in revenue QoQ and YoY? Explain material disclosed volume, price, mix or backlog conversion drivers; distinguish management claims from measured demand.',
    'earnings': 'What changed in diluted EPS, gross margin, R&D and diluted share count? Explain material operating profitability, dilution and recurring versus interest/other or one-off effects without repeating the table.',
    'cash': 'How much operating cash flow and FCF was generated, after what capex? What do cash/liquid assets and debt imply about funding capacity? Identify quarter versus YTD and noncomparable balance-sheet dates, missing debt totals and lease-inclusive definitions.',
    'outlook': 'What changed in guidance, on what assumptions and execution dependencies? Identify material source-backed counterevidence and unanswered earnings-call questions; distinguish guidance from aspirations.',
    'valuation': 'What is the dated current or forward earnings P/E, if supported? Require matched security, currency, share/ADR basis and annual/TTM or explicit forward annual diluted EPS. Otherwise name the missing inputs. No quarterly EPS annualization, invented forecasts, DCF, target price or other valuation.',
}


def contract():
    return {'version': VERSION, 'questions_sha256': base.digest(QUESTIONS)}


def verify(value):
    if value != contract():
        raise ValueError('Frozen expected-question contract changed')
    return value


def instructions(role):
    text = ('\n## Core financial questions\n\n' + '\n'.join(k+': '+v for k,v in QUESTIONS.items()) +
            '\nAnswer materially in the report or disclose the specific source gap. '
            'Do not demand every disclosure or fabricate missing metrics. Tables carry the core numbers; prose explains drivers and qualifications.')
    if role == 'review':
        text += (' Add exactly one top-level question_assessments object to the existing review JSON. '
                 'Its keys are demand, earnings, cash, outlook, valuation. Each value has exactly '
                 '{status:"answered|disclosed_gap|fail",evidence:"specific report answer and source-grounded reason",'
                 'unit_ids:["existing candidate unit IDs"],report_locations:["demand|earnings|cash|outlook|qa"],'
                 'gap:"specific missing input or empty string"}. Use disclosed_gap only when the report itself names '
                 'the limitation, and assess the available numbers too. Locate valuation in its actual report section, usually outlook. '
                 'A responsibly disclosed missing input alone does not force global criteria to fail or become unavailable. '
                 'Every fail must identify an affected existing unit with a revise decision or reopen finding '
                 'and a concrete source-backed repair. Read-only table arithmetic cannot be rewritten by correction.')
    return text


def validate(assessments, items, review):
    if not isinstance(assessments, dict) or set(assessments) != set(QUESTIONS):
        raise ValueError('Every expected financial question requires assessment')
    if any(not isinstance(review.get(key),list) or any(not isinstance(d,dict) for d in review[key]) for key in ('decisions','reopen')):
        raise ValueError('Question review requires structured decision and reopen lists')
    failing_units = {d.get('unit_id') for d in review['decisions'] if d.get('verdict') == 'revise'}
    failing_units.update(d.get('unit_id') for d in review['reopen'])
    for name, row in assessments.items():
        if not isinstance(row, dict) or set(row) != {'status','evidence','unit_ids','report_locations','gap'}:
            raise ValueError('Exact question assessment fields required')
        if row['status'] not in ('answered','disclosed_gap','fail'):
            raise ValueError('Known question assessment status required')
        if not isinstance(row['evidence'], str) or not row['evidence'].strip() or len(row['evidence']) > 4000:
            raise ValueError('Specific bounded question evidence required')
        if not isinstance(row['gap'], str) or (row['status'] == 'disclosed_gap' and not row['gap'].strip()):
            raise ValueError('A disclosed source gap must name the missing input')
        for field, allowed in (('unit_ids', set(items)), ('report_locations', set(REPORT_LOCATIONS))):
            values = row[field]
            if not isinstance(values, list) or any(not isinstance(v, str) or v not in allowed for v in values) or len(values) != len(set(values)):
                raise ValueError('Question assessment requires known unique '+field)
        if not row['report_locations']:
            raise ValueError('Question assessment must locate its report section')
        if row['status'] == 'fail' and not (set(row['unit_ids']) & failing_units):
            raise ValueError('Failed question requires an affected unit with a repair finding')
    return all(row['status'] != 'fail' for row in assessments.values())
