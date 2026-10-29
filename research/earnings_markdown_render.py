"""Escaped Markdown rendering and citation formatting, independent of orchestration.

Supported syntax is explicit. Source and author HTML is always escaped; numerical
cells, citations and original-exchange text are preserved without interpretation.
"""
from __future__ import annotations
import html
import re

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
        fence=re.fullmatch(r'(`{3,})(?:text)?',line)
        if fence:
            close=fence[1];rows=[];i+=1
            while i<len(lines) and lines[i]!=close:rows.append(lines[i]);i+=1
            if i==len(lines):raise ValueError('Unclosed original-layout block')
            parts.append('<div class="table-scroll"><pre class="source-layout">'+html.escape('\n'.join(rows))+'</pre></div>')
            i+=1;continue
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
        while i<len(lines) and lines[i].strip() and not re.match(r'^(#{1,3} |> |- |\| |\[\^|:::original-qa |`{3,})',lines[i]):rows.append(lines[i]);i+=1
        text='\n'.join(rows)
        tone=next((key for name,key in [('Improving','up'),('Deteriorating','down'),('Conditional','conditional'),('Unresolved','flat')] if text.startswith(name+' · ')),None)
        parts.append('<p'+(' class="signal-label '+tone+'"' if tone else '')+'>'+inline(text)+'</p>')
    body=''.join(parts)
    targets=set(re.findall(r'href="#([^\"]+)"',body));ids=set(re.findall(r'id="([^\"]+)"',body))
    if not targets<=ids:raise ValueError('Unresolved Markdown source reference')
    title=next((line[2:] for line in lines if line.startswith('# ')),'Earnings report')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>body{max-width:1050px;margin:32px auto;padding:0 22px;font:16px/1.55 system-ui;color:#20302a;background:#f7f7f2}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:8px;border-bottom:1px solid #ccd3cb}blockquote{border-left:3px solid #859e8c;padding-left:16px;white-space:pre-wrap}a{color:#17634d}.direction{display:inline-block;font-size:12px;font-weight:650;white-space:nowrap;margin-left:6px}.direction.up,.signal-label.up{color:#14532d;background:#dcfce7}.direction.down,.signal-label.down{color:#991b1b;background:#fee2e2}.direction.flat,.signal-label.flat{color:#475569;background:#f1f5f9}.signal-label.conditional{color:#854d0e;background:#fef3c7}.direction{padding:3px 7px;border-radius:5px}.signal-label{padding:8px 12px;border-radius:6px;font-size:14px;font-weight:650}.original-qa{margin:18px 0;padding:14px 18px;border:1px solid #ccd3cb;border-radius:8px;background:#fff}.original-qa summary{cursor:pointer;font-weight:650}.qa-speaker{font-weight:650;margin-bottom:5px}.qa-original{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;margin-top:0}.source-note{font-size:12px;color:#52605a}.table-scroll{overflow-x:auto;margin:18px 0}h1{font-size:32px;line-height:1.15}h2{margin-top:40px;padding-top:14px;border-top:2px solid #ccd3cb;font-size:23px}h3{font-size:18px}th[scope=row]{font-weight:550}td{font-variant-numeric:tabular-nums}thead{background:#e8ede9}header{font-size:12px;color:#52605a}@media(max-width:650px){body{padding:0 14px}table{min-width:620px}h1{font-size:26px}}</style><header>'+('Accepted after independent review' if status=='accepted' else 'Draft — review pending')+'</header><main>'+body+'</main></html>'
