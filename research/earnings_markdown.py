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


def quote_markdown(quote, bundle):
    """Render exact quotation bytes and an independently indexed turn speaker.

    Passage hydration supplies the original turn ID and offsets. Document
    selections have no turn speaker; never infer one from adjacent prose.
    """
    block='\n'.join('> '+line for line in quote['text'].splitlines())
    turns=[t for t in bundle['transcript_index']['turns'] if t['id']==quote['scope_id']]
    if turns:
        if len(turns)!=1 or not turns[0]['start']<=quote['start']<quote['end']<=turns[0]['end']:
            raise ValueError('Quotation attribution requires exact original turn bounds')
        speaker=turns[0]['speaker']
        if not isinstance(speaker,str) or not speaker.strip() or '\n' in speaker or '\r' in speaker:
            raise ValueError('Quotation attribution requires one indexed speaker')
        block+='\n>\n> — '+speaker
    return block+' '+refs([quote['scope_id']])


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


def inline(text):
    escaped=html.escape(text)
    return re.sub(r'\[\^([A-Za-z0-9_-]+)\]',lambda m:'<sup><a href="#source-'+m[1]+'">'+m[1]+'</a></sup>',escaped)


def split_row(line):
    # Only the generator's escaped pipes are accepted as cell content.
    return [x.strip().replace('\\|','|').replace('\\\\','\\') for x in re.split(r'(?<!\\)\|',line.strip()[1:-1])]


def render(markdown, *, status='draft', original_exchanges=None):
    if status not in ('draft','accepted'):raise ValueError('Explicit render status required')
    lines=markdown.splitlines();parts=[];i=0
    while i<len(lines):
        line=lines[i]
        if not line.strip():i+=1;continue
        exchange=re.fullmatch(r':::original-qa ([A-Za-z0-9_-]+)',line)
        if exchange:
            identifier=exchange[1]
            item=(original_exchanges or {}).get(identifier)
            if item is None:
                raise ValueError('Original Q&A requires its verified source bundle: '+identifier)
            parts.append('<details class="original-qa"><summary>Read the original exchange</summary>')
            parts.append('<p class="source-note">Original transcript · '+html.escape(identifier)+'</p>')
            for turn in item['turns']:
                parts.append('<p class="qa-speaker">'+html.escape(turn['speaker'])+' · '+html.escape(turn['role'])+'</p>')
                parts.append('<pre class="qa-original">'+html.escape(turn['text'])+'</pre>')
            parts.append('</details>');i+=1;continue
        foot=re.fullmatch(r'\[\^([A-Za-z0-9_-]+)\]: (.*)',line)
        if foot:parts.append('<p id="source-'+foot[1]+'">'+inline(foot[2])+'</p>');i+=1;continue
        heading=re.match(r'^(#{1,3}) (.*)$',line)
        if heading:
            n=len(heading[1]);parts.append('<h'+str(n)+'>'+inline(heading[2])+'</h'+str(n)+'>');i+=1;continue
        if line.startswith('| ') and i+1<len(lines) and re.fullmatch(r'\|(?:\s*---\s*\|)+',lines[i+1]):
            rows=[split_row(line)];i+=2
            while i<len(lines) and lines[i].startswith('| '):rows.append(split_row(lines[i]));i+=1
            if any(len(r)!=len(rows[0]) for r in rows):raise ValueError('Markdown table column mismatch')
            from .earnings_visual_signals import badges, comparison_badges
            sectioned = rows[0][-2:] == ['QoQ','YoY']
            computed = rows[0][:2] == ['Metric','Unit / basis']
            def cells(row):
                labels = ['']*len(row) if computed else comparison_badges(rows[0],row) if sectioned else badges(rows[0],row)
                result = []
                for n,(x,label) in enumerate(zip(row,labels)):
                    if sectioned and label:
                        citations = ' '.join(re.findall(r'\[\^[A-Za-z0-9_-]+\]',x))
                        content = label + (' '+inline(citations) if citations else '')
                    else:content = inline(x)+(' '+label if label else '')
                    tag = 'th scope="row"' if n==0 else 'td'
                    result.append('<'+tag+'>'+content+'</'+tag.split()[0]+'>')
                return ''.join(result)
            parts.append('<div class="table-scroll"><table><thead><tr>'+''.join('<th scope="col">'+inline(x)+'</th>' for x in rows[0])+'</tr></thead><tbody>'+''.join('<tr>'+cells(row)+'</tr>' for row in rows[1:])+'</tbody></table></div>');continue
        if line.startswith('> '):
            rows=[]
            while i<len(lines) and lines[i].startswith('> '):rows.append(lines[i][2:]);i+=1
            parts.append('<blockquote>'+inline('\n'.join(rows))+'</blockquote>');continue
        if line.startswith('- '):
            rows=[]
            while i<len(lines) and lines[i].startswith('- '):rows.append(lines[i][2:]);i+=1
            parts.append('<ul>'+''.join('<li>'+inline(x)+'</li>' for x in rows)+'</ul>');continue
        rows=[line];i+=1
        while i<len(lines) and lines[i].strip() and not re.match(r'^(#{1,3} |> |- |\| |\[\^|:::original-qa )',lines[i]):rows.append(lines[i]);i+=1
        text='\n'.join(rows)
        tone=next((key for name,key in [('Improving','up'),('Deteriorating','down'),('Conditional','conditional'),('Unresolved','flat')] if text.startswith(name+' · ')),None)
        parts.append('<p'+(' class="signal-label '+tone+'"' if tone else '')+'>'+inline(text)+'</p>')
    body=''.join(parts)
    targets=set(re.findall(r'href="#([^\"]+)"',body));ids=set(re.findall(r'id="([^\"]+)"',body))
    if not targets<=ids:raise ValueError('Unresolved Markdown source reference')
    title=next((line[2:] for line in lines if line.startswith('# ')),'Earnings report')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>body{max-width:1050px;margin:32px auto;padding:0 22px;font:16px/1.55 system-ui;color:#20302a;background:#f7f7f2}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:8px;border-bottom:1px solid #ccd3cb}blockquote{border-left:3px solid #859e8c;padding-left:16px;white-space:pre-wrap}a{color:#17634d}.direction{display:inline-block;font-size:12px;font-weight:650;white-space:nowrap;margin-left:6px}.direction.up,.signal-label.up{color:#14532d;background:#dcfce7}.direction.down,.signal-label.down{color:#991b1b;background:#fee2e2}.direction.flat,.signal-label.flat{color:#475569;background:#f1f5f9}.signal-label.conditional{color:#854d0e;background:#fef3c7}.direction{padding:3px 7px;border-radius:5px}.signal-label{padding:8px 12px;border-radius:6px;font-size:14px;font-weight:650}.original-qa{margin:18px 0;padding:14px 18px;border:1px solid #ccd3cb;border-radius:8px;background:#fff}.original-qa summary{cursor:pointer;font-weight:650}.qa-speaker{font-weight:650;margin-bottom:5px}.qa-original{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;margin-top:0}.source-note{font-size:12px;color:#52605a}.table-scroll{overflow-x:auto;margin:18px 0}h1{font-size:32px;line-height:1.15}h2{margin-top:40px;padding-top:14px;border-top:2px solid #ccd3cb;font-size:23px}h3{font-size:18px}th[scope=row]{font-weight:550}td{font-variant-numeric:tabular-nums}thead{background:#e8ede9}header{font-size:12px;color:#52605a}@media(max-width:650px){body{padding:0 14px}table{min-width:620px}h1{font-size:26px}}</style><header>'+('Accepted after independent review' if status=='accepted' else 'Draft — review pending')+'</header><main>'+body+'</main></html>'


def write(path,state,bundle,catalog,pack=None,*,status='draft'):
    from pathlib import Path
    path=Path(path);content=report(state,bundle,catalog,pack)
    legacy.immutable_text(path.with_suffix('.md'),content)
    from . import earnings_report_template as template
    exchanges=template.original_exchanges(state,bundle)
    legacy.immutable_text(path.with_suffix('.html'),render(content,status=status,original_exchanges=exchanges))
    return content


def main():
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('markdown',type=Path);p.add_argument('html',type=Path);p.add_argument('--status',choices=('draft','accepted'),default='draft');a=p.parse_args()
    legacy.immutable_text(a.html,render(a.markdown.read_text(),status=a.status))

if __name__=='__main__':main()
