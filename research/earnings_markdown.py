"""Deterministic report Markdown and a small, escaped Markdown-to-HTML renderer.

Supported syntax is explicit: headings, paragraphs, blockquotes, lists, pipe
 tables and citation footnotes. Source/author HTML is always escaped.
"""
from __future__ import annotations
import re
from .earnings_markdown_render import cell, refs, quote_markdown, inline, split_row, render
from .earnings_runtime_common import immutable_text

VERSION='earnings-markdown-report-v1'


def financial_markdown(financial,bundle,formatting):
    # Bridge the existing checked financial compiler into Markdown cells; never
    # reinterpret scales, periods, folded ratios or source-derived row labels.
    from html.parser import HTMLParser
    from . import earnings_report_repair as repair
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
    from . import earnings_passages as passages, earnings_signals as signals
    from . import earnings_report_template as template
    if state['artifacts']['analysis'].get('report_template') == template.VERSION:
        return template.report(state,bundle,catalog,pack)
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
            out.extend([quote_markdown(q,bundle),'']);used.add(q['scope_id'])
    out.extend(['## Next tests',''])
    for x in hydrated['next_tests']:out.append('- '+x['text']+' '+refs(x['citations']));used.update(x['citations'])
    out.extend(['','## Scope','',hydrated['scope'],'','## Source references',''])
    # Footnotes identify immutable source IDs. Original text stays in the bundle.
    for identifier in sorted(used):out.append('[^'+identifier+']: Original evidence '+identifier)
    return '\n'.join(out).rstrip()+'\n'


def write(path,state,bundle,catalog,pack=None,*,status='draft'):
    from pathlib import Path
    path=Path(path);content=report(state,bundle,catalog,pack)
    immutable_text(path.with_suffix('.md'),content)
    from . import earnings_report_template as template
    exchanges=template.original_exchanges(state,bundle)
    immutable_text(path.with_suffix('.html'),render(content,status=status,original_exchanges=exchanges))
    return content


def main():
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('markdown',type=Path);p.add_argument('html',type=Path);p.add_argument('--status',choices=('draft','accepted'),default='draft');a=p.parse_args()
    immutable_text(a.html,render(a.markdown.read_text(),status=a.status))

if __name__=='__main__':main()
