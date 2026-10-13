"""Deterministic report Markdown and a small, escaped Markdown-to-HTML renderer.

Supported syntax is explicit: headings, paragraphs, blockquotes, lists, pipe
 tables and citation footnotes. Source/author HTML is always escaped.
"""
from __future__ import annotations
import html
import re
from . import earnings_report_repair as repair, earnings_passages as passages
from . import earnings_signals as signals, earnings_mixed_pipeline as legacy

VERSION='earnings-markdown-report-v1'


def cell(value):
    return str(value).replace('\\','\\\\').replace('|','\\|').replace('\n',' ')


def refs(ids):return ' '.join('[^'+x+']' for x in ids)


def financial_markdown(financial,bundle,formatting):
    # Bridge the existing checked financial compiler into Markdown cells; never
    # reinterpret scales, periods, folded ratios or source-derived row labels.
    from html.parser import HTMLParser
    class Table(HTMLParser):
        def __init__(self):
            super().__init__();self.lines=['## Financial context'];self.rows=[];self.row=None;self.value=None;self.paragraph=None
        def handle_starttag(self,tag,attrs):
            if tag=='table':self.rows=[]
            elif tag=='tr':self.row=[]
            elif tag in ('th','td'):self.value=[]
            elif tag in ('p','caption'):self.paragraph=[]
            elif tag=='br' and self.value is not None:self.value.append('; ')
        def handle_data(self,data):
            if self.value is not None:self.value.append(data)
            elif self.paragraph is not None:self.paragraph.append(data)
        def handle_endtag(self,tag):
            if tag in ('th','td'):
                self.row.append(''.join(self.value));self.value=None
            elif tag=='tr':self.rows.append(self.row);self.row=None
            elif tag=='table':
                for i,row in enumerate(self.rows):
                    self.lines.append('| '+' | '.join(cell(x) for x in row)+' |')
                    if i==0:self.lines.append('| '+' | '.join('---' for _ in row)+' |')
                self.lines.append('')
            elif tag in ('p','caption') and self.paragraph is not None:
                self.lines.extend(['',''.join(self.paragraph),'']);self.paragraph=None
    parser=Table();parser.feed(repair.table(financial,bundle,formatting,refs));return '\n'.join(parser.lines)


def report(state,bundle,catalog,pack=None):
    hydrated=passages.hydrate('analysis',state['artifacts']['analysis'],catalog)
    out=['# '+hydrated['title'],'',hydrated['opening']+' '+refs(hydrated['opening_citations']),'']
    used=set(hydrated['opening_citations'])
    from .earnings_financial_display import build
    used.update(build(state['artifacts']['financial'],bundle)['selected_fact_ids'])
    used.update(re.findall(r'\[\^([A-Za-z0-9_-]+)\]',financial_markdown(state['artifacts']['financial'],bundle,state['format'])))
    if pack is not None:
        signals.validate(pack,state,bundle,catalog);out.extend(['## Business signals',''])
        for s in pack['signals']:
            out.extend(['### '+s['label'],'',signals.DIRECTIONS[s['direction']]+' · '+signals.BASES[s['evidence_basis']]+' · '+s['period'],'',s['summary']+' '+refs(s['citations']),''])
            used.update(s['citations'])
    out.extend([financial_markdown(state['artifacts']['financial'],bundle,state['format']),''])
    for f in hydrated['findings']:
        out.extend(['## '+f['heading'],'',f['text']+' '+refs(f['citations']),'']);used.update(f['citations'])
        for q in f['quotes']:
            out.extend(['\n'.join('> '+line for line in q['text'].splitlines())+' '+refs([q['scope_id']]),'']);used.add(q['scope_id'])
    out.extend(['## Next tests',''])
    for x in hydrated['next_tests']:out.append('- '+x['text']+' '+refs(x['citations']));used.update(x['citations'])
    out.extend(['','## Scope','',hydrated['scope'],'','## Source references',''])
    # Footnotes identify immutable source IDs. Original text stays in the bundle.
    for identifier in sorted(used):out.append('[^'+identifier+']: Original evidence '+identifier)
    return '\n'.join(out).rstrip()+'\n'


def inline(text):
    escaped=html.escape(text)
    return re.sub(r'\[\^([A-Za-z0-9_-]+)\]',lambda m:'<sup><a href="#source-'+m[1]+'">'+m[1]+'</a></sup>',escaped)


def split_row(line):
    # Only the generator's escaped pipes are accepted as cell content.
    return [x.strip().replace('\\|','|').replace('\\\\','\\') for x in re.split(r'(?<!\\)\|',line.strip()[1:-1])]


def render(markdown, *, status='draft'):
    if status not in ('draft','accepted'):raise ValueError('Explicit render status required')
    lines=markdown.splitlines();parts=[];i=0
    while i<len(lines):
        line=lines[i]
        if not line.strip():i+=1;continue
        foot=re.fullmatch(r'\[\^([A-Za-z0-9_-]+)\]: (.*)',line)
        if foot:parts.append('<p id="source-'+foot[1]+'">'+inline(foot[2])+'</p>');i+=1;continue
        heading=re.match(r'^(#{1,3}) (.*)$',line)
        if heading:
            n=len(heading[1]);parts.append('<h'+str(n)+'>'+inline(heading[2])+'</h'+str(n)+'>');i+=1;continue
        if line.startswith('| ') and i+1<len(lines) and re.fullmatch(r'\|(?:\s*---\s*\|)+',lines[i+1]):
            rows=[split_row(line)];i+=2
            while i<len(lines) and lines[i].startswith('| '):rows.append(split_row(lines[i]));i+=1
            if any(len(r)!=len(rows[0]) for r in rows):raise ValueError('Markdown table column mismatch')
            parts.append('<table><thead><tr>'+''.join('<th>'+inline(x)+'</th>' for x in rows[0])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+inline(x)+'</td>' for x in row)+'</tr>' for row in rows[1:])+'</tbody></table>');continue
        if line.startswith('> '):
            rows=[]
            while i<len(lines) and lines[i].startswith('> '):rows.append(lines[i][2:]);i+=1
            parts.append('<blockquote>'+inline('\n'.join(rows))+'</blockquote>');continue
        if line.startswith('- '):
            rows=[]
            while i<len(lines) and lines[i].startswith('- '):rows.append(lines[i][2:]);i+=1
            parts.append('<ul>'+''.join('<li>'+inline(x)+'</li>' for x in rows)+'</ul>');continue
        rows=[line];i+=1
        while i<len(lines) and lines[i].strip() and not re.match(r'^(#{1,3} |> |- |\| |\[\^)',lines[i]):rows.append(lines[i]);i+=1
        parts.append('<p>'+inline('\n'.join(rows))+'</p>')
    body=''.join(parts)
    targets=set(re.findall(r'href="#([^\"]+)"',body));ids=set(re.findall(r'id="([^\"]+)"',body))
    if not targets<=ids:raise ValueError('Unresolved Markdown source reference')
    title=next((line[2:] for line in lines if line.startswith('# ')),'Earnings report')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>body{max-width:1050px;margin:32px auto;padding:0 22px;font:16px/1.55 system-ui;color:#20302a;background:#f7f7f2}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:8px;border-bottom:1px solid #ccd3cb}blockquote{border-left:3px solid #859e8c;padding-left:16px;white-space:pre-wrap}a{color:#17634d}</style><header>'+('Accepted after independent review' if status=='accepted' else 'Draft — review pending')+'</header><main>'+body+'</main></html>'


def write(path,state,bundle,catalog,pack=None,*,status='draft'):
    from pathlib import Path
    path=Path(path);content=report(state,bundle,catalog,pack)
    legacy.immutable_text(path.with_suffix('.md'),content)
    legacy.immutable_text(path.with_suffix('.html'),render(content,status=status))
    return content


def main():
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('markdown',type=Path);p.add_argument('html',type=Path);p.add_argument('--status',choices=('draft','accepted'),default='draft');a=p.parse_args()
    legacy.immutable_text(a.html,render(a.markdown.read_text(),status=a.status))

if __name__=='__main__':main()
