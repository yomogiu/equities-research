"""Optional P/E arithmetic from explicitly supplied dated earnings inputs.

This module never retrieves prices, estimates EPS, annualizes quarters, or values
future cash flows. A snapshot file binding authenticates those supplied bytes;
URLs and source hashes inside it remain caller-provided metadata, not proof that
this module fetched, interpreted, or independently verified the cited sources.
"""
from copy import deepcopy
from datetime import date
from decimal import localcontext
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .financial_evidence import _decimal

VERSION = 'source-declared-earnings-multiples-v1'
PROVENANCE = ('Caller-provided source metadata. This calculation does not establish source '
              'authenticity, completeness, estimate quality, or that an annual EPS is the latest available.')


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Explicit ISO calendar date required')
    return date.fromisoformat(value)


def _string(value, label, limit=160):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError('Explicit bounded '+label+' required')
    return value


def _security(value):
    if not isinstance(value, dict): raise ValueError('Explicit security identity required')
    _string(value.get('id'), 'security ID')
    if not re.fullmatch('[A-Z]{3}', str(value.get('currency', ''))):
        raise ValueError('Explicit three-letter currency required')
    if value.get('earnings_unit') not in ('ordinary_share', 'adr'):
        raise ValueError('Explicit ordinary-share or ADR earnings unit required')
    shares = _decimal(value.get('ordinary_shares_per_security'))
    if shares <= 0 or value['earnings_unit'] == 'ordinary_share' and shares != 1:
        raise ValueError('Positive explicit security share ratio required; ordinary shares use one')
    _string(value.get('split_basis_id'), 'split-adjustment basis ID')


def _source(value):
    if not isinstance(value, dict): raise ValueError('Explicit source metadata required')
    _string(value.get('document_id'), 'source document ID')
    url = _string(value.get('url'), 'source URL', 2048)
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError('HTTP(S) source URL required')
    if not re.fullmatch('[0-9a-f]{64}', str(value.get('sha256', ''))):
        raise ValueError('Explicit source SHA256 required')


def _input(record, security, as_of):
    if not isinstance(record, dict): raise ValueError('Input not supplied')
    _string(record.get('id'), 'input ID')
    value = _decimal(record.get('value'))
    if record.get('security_id') != security['id']:
        raise ValueError('Price and EPS must refer to the same security')
    for field in ('currency', 'earnings_unit', 'split_basis_id'):
        if record.get(field) != security[field]:
            raise ValueError('Price and EPS '+field+' must match exactly')
    if _decimal(record.get('ordinary_shares_per_security')) != _decimal(security['ordinary_shares_per_security']):
        raise ValueError('Price and EPS ADR/share ratios must match exactly')
    observed = _date(record.get('as_of'))
    if observed > as_of: raise ValueError('Input date is after valuation as_of')
    _source(record.get('source'))
    return value, observed


def _eps(record, security, as_of, forward):
    value, observed = _input(record, security, as_of)
    if record.get('measure') != 'diluted_eps':
        raise ValueError('Explicit diluted EPS required; no quarter or YTD annualization')
    _string(record.get('accounting_basis'), 'EPS accounting basis')
    period = record.get('period')
    if not isinstance(period, dict): raise ValueError('Explicit complete EPS period required')
    expected = ('forward_annual',) if forward else ('annual', 'ttm')
    if period.get('kind') not in expected:
        raise ValueError('Annual/TTM EPS required; quarterly or YTD EPS cannot be annualized')
    start, end = _date(period.get('start')), _date(period.get('end'))
    if not 350 <= (end-start).days+1 <= 380:
        raise ValueError('Complete annual period of 350–380 days required, including 52/53-week years')
    if forward:
        if record.get('estimate_type') not in ('consensus', 'company_guidance'):
            raise ValueError('Explicit consensus or company-guidance estimate type required')
        forecast_as_of = _date(record.get('forecast_as_of'))
        if forecast_as_of > observed or forecast_as_of > as_of:
            raise ValueError('Forecast date must not be after source or valuation date')
        if end <= as_of:
            raise ValueError('Forward annual forecast period must end after valuation date')
    elif end > observed or end > as_of:
        raise ValueError('Reported annual/TTM EPS must end no later than source and valuation dates')
    return value, observed


def _row(snapshot, security, as_of, forward):
    slot = 'forward_eps' if forward else 'current_eps'
    price, eps = snapshot.get('price'), snapshot.get(slot)
    row = {'metric_id': 'forward_pe' if forward else 'current_pe',
           'label': 'Forward annual P/E' if forward else 'Reported annual/TTM P/E',
           'status': 'unavailable', 'value': None, 'unit': 'times', 'reason': None,
           'formula': 'price_per_security / annual_diluted_eps_per_same_security',
           'input_ids': [x['id'] for x in (price, eps) if isinstance(x, dict) and isinstance(x.get('id'), str)],
           'price_id': price.get('id') if isinstance(price, dict) else None,
           'eps_id': eps.get('id') if isinstance(eps, dict) else None,
           'price_as_of': price.get('as_of') if isinstance(price, dict) else None,
           'eps_as_of': eps.get('as_of') if isinstance(eps, dict) else None,
           'earnings_period': deepcopy(eps.get('period')) if isinstance(eps, dict) else None,
           'accounting_basis': eps.get('accounting_basis') if isinstance(eps, dict) else None,
           'estimate_type': eps.get('estimate_type') if isinstance(eps, dict) and forward else None,
           'forecast_as_of': eps.get('forecast_as_of') if isinstance(eps, dict) and forward else None}
    try:
        _security(security)
        if price is None: raise ValueError('Dated price input not supplied')
        amount, quoted = _input(price, security, as_of)
        if amount <= 0: raise ValueError('Positive trading price required')
        if quoted != as_of:
            raise ValueError('Price is not dated at valuation as_of; select its actual quote date explicitly')
        if eps is None: raise ValueError('Forward annual EPS input not supplied' if forward else 'Reported annual/TTM EPS input not supplied')
        denominator, published = _eps(eps, security, as_of, forward)
        row['earnings_age_days'] = (as_of-_date(eps['period']['end'])).days if not forward else None
        row['source_age_days'] = (as_of-published).days
        row['label'] = ('Forward annual P/E ('+eps['estimate_type']+')' if forward else
                        ('Reported TTM P/E' if eps['period']['kind']=='ttm' else 'Reported fiscal-year P/E'))
        if denominator <= 0:
            row.update(status='not_meaningful', reason='P/E is not meaningful with zero or negative EPS')
            return row
        with localcontext() as ctx:
            ctx.prec = 50
            result = amount / denominator
        row.update(status='available', value=format(result, 'f'), precision=50,
                   operands={'price': price['value'], 'annual_diluted_eps': eps['value']})
    except (ValueError, TypeError, KeyError) as exc:
        row['reason'] = str(exc)
    return row


def build(snapshot, *, as_of):
    """Compute only two optional multiples from unchanged caller inputs.

    The explicit price date must equal as_of. Missing, stale, misaligned, or
    quarterly inputs yield unavailable rows; nonpositive qualified EPS is N/M.
    A forward fiscal-year forecast is labelled with its exact horizon, never NTM.
    No share, ADR, split, FX, quarterly, or YTD conversion is performed.
    """
    if not isinstance(snapshot, dict) or snapshot.get('version') != VERSION:
        raise ValueError('Supported earnings-multiple snapshot version required')
    valuation_date = _date(as_of)
    records = [snapshot.get(k) for k in ('price', 'current_eps', 'forward_eps')]
    ids = [x['id'] for x in records if isinstance(x, dict) and isinstance(x.get('id'), str)]
    if len(ids) != len(set(ids)): raise ValueError('Distinct price and EPS input IDs required')
    security = snapshot.get('security')
    rows = [_row(snapshot, security, valuation_date, forward) for forward in (False, True)]
    return {'version': VERSION, 'as_of': as_of, 'security': deepcopy(security), 'rows': rows,
            'inputs': deepcopy(snapshot), 'provenance': PROVENANCE,
            'gaps': [{'metric_id': r['metric_id'], 'reason': r['reason'], 'input_ids': r['input_ids']}
                     for r in rows if r['status'] != 'available'],
            'scope': 'Price divided by supplied annual diluted EPS only; no DCF, target price, forecast model, or recommendation.'}


def load(path, *, as_of, expected_sha256=None):
    """Read a bounded optional snapshot; verify an external file binding if given."""
    path = Path(path).resolve()
    if path.stat().st_size > 1024*1024: raise ValueError('Earnings snapshot exceeds 1 MiB')
    raw = path.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and expected_sha256 != digest:
        raise ValueError('Earnings snapshot file binding changed')
    result = build(json.loads(raw), as_of=as_of)
    result['snapshot_binding'] = {'path': str(path), 'sha256': digest,
                                  'external_hash_verified': expected_sha256 is not None}
    return result
