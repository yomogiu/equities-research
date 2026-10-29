"""Issuer-linked public disclosure archives; no company-specific source URLs."""
from datetime import datetime,timedelta,timezone
from html import escape
import json,re
from urllib.parse import urlsplit,urlunsplit,parse_qs,urljoin
from .source_parse import page


def discover(body,url,as_of,fetch):
    """Resolve CNINFO's published stock/archive interface before report selection.

    The endpoint and public form mirror the archive's own disclosure widget.
    Stock and organization IDs must come from an actual issuer-owned link. Two
    pages and the caller's existing request/byte ceiling bound discovery.
    """
    links=[x['url'] for x in page(body,url).links]
    links=[u for u in links if urlsplit(u).hostname=='www.cninfo.com.cn'
           and urlsplit(u).path=='/new/disclosure/stock']
    # Older issuer sites still print HTTP archive links. Use the verified
    # provider's HTTPS endpoint with the same path/query; never weaken TLS.
    links=[urlunsplit(('https',urlsplit(u).netloc,urlsplit(u).path,urlsplit(u).query,'')) for u in links]
    if len(set(links))!=1:raise ValueError('No unique issuer-linked disclosure archive')
    archive=links[0];query=parse_qs(urlsplit(archive).query)
    stock=query.get('stockCode',[''])[0];org=query.get('orgId',[''])[0]
    if not re.fullmatch(r'\d{6}',stock) or not re.fullmatch(r'\d+',org):raise ValueError('Explicit archive issuer IDs required')
    raw,_=fetch(archive,'official_disclosure_archive')
    match=re.search(rb'\bvar\s+plate\s*=\s*[\x27\x22](szse|sse)[\x27\x22]',raw)
    column=match[1].decode() if match else query.get('plate',[''])[0]
    if column not in ('szse','sse'):raise ValueError('Official archive exchange column unavailable')
    selected=[]
    for number in (1,2):
        form={'stock':stock+','+org,'tabName':'fulltext','pageSize':30,'pageNum':number,'column':column,
              'category':'','plate':'','seDate':(as_of-timedelta(days=150)).isoformat()+'~'+as_of.isoformat(),
              'searchkey':'','secid':'','sortName':'','sortType':'','isHLtitle':'true'}
        data,_=fetch('https://www.cninfo.com.cn/new/hisAnnouncement/query','official_disclosure_entries',form=form)
        result=json.loads(data);rows=result.get('announcements')
        if not isinstance(rows,list):raise ValueError('Disclosure archive entries unavailable')
        for row in rows:
            if row.get('secCode')!=stock or row.get('orgId')!=org:raise ValueError('Disclosure archive returned another issuer')
            if datetime.fromtimestamp(row['announcementTime']/1000,timezone.utc).date()>as_of:continue
            adjunct=row.get('adjunctUrl','')
            if not re.fullmatch(r'finalpage/20\d{2}-\d{2}-\d{2}/\d+\.PDF',adjunct,re.I):continue
            selected.append({'url':urljoin('https://static.cninfo.com.cn/',adjunct),'title':row['announcementTitle']})
        if len(rows)<30:break
    html=''.join('<a href="'+escape(x['url'],quote=True)+'">'+escape(x['title'])+'</a>' for x in selected)
    return html.encode(),archive
