"""Presentation-only direction labels for comparable quarterly table cells.

No prose inference, input mutation, accounting conversion or source fetching.
Unknown metrics, periods, units and nonpositive growth denominators are neutral.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

POSITIVE = ('Revenue','Gross profit','Operating income','Net income','Diluted EPS','Earnings Per Share Diluted','Operating cash flow')

def plain(value):
    return re.sub(r'\[\^[^]]+\]','',value).strip()

def quarter(value):
    m=re.fullmatch(r'([A-Z][a-z]{2} \d{1,2}, \d{4}) – ([A-Z][a-z]{2} \d{1,2}, \d{4})',plain(value))
    if not m:return None
    a,z=(datetime.strptime(x,'%b %d, %Y').date() for x in m.groups())
    return (a,z) if 70<=(z-a).days<=100 else None

def value(cell):
    text=plain(cell).replace(',','')
    if not re.fullmatch(r'-?\d+(?:\.\d+)?|\(\d+(?:\.\d+)?\)',text):return None
    try:return Decimal(text.strip('()'))*(-1 if text.startswith('(') else 1)
    except InvalidOperation:return None

def badges(headers,row):
    out=['']*len(row)
    if not row or not plain(row[0]).startswith(POSITIVE):return out
    periods=[quarter(x) for x in headers]
    candidates=[i for i,p in enumerate(periods) if p and value(row[i]) is not None]
    if len(candidates)<2:return out
    current=max(candidates,key=lambda i:periods[i][1]);a,z=periods[current];v=value(row[current]);labels=[]
    for i in candidates:
        if i==current:continue
        pa,pz=periods[i]
        if (a-pz).days==1:kind='QoQ'
        elif a.year==pa.year+1 and (a.month,a.day,z.month,z.day)==(pa.month,pa.day,pz.month,pz.day):kind='YoY'
        else:continue
        prior=value(row[i]);delta=v-prior
        if prior<=0:continue  # Growth percentages from zero/losses are not comparable.
        change=delta/prior*100
        if change.quantize(Decimal('0.1'))==0:label='→ 0.0% '+kind;cls='flat'
        else:label=('↑ +' if change>0 else '↓ ')+f'{change:.1f}% '+kind;cls='up' if change>0 else 'down'
        labels.append('<span class="direction '+cls+'">'+label+'</span>')
    out[current]=' '.join(labels)
    return out
