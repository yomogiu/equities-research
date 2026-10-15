"""Hash-bound evidence files and a paged IPython access API; no model calls."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from . import earnings_compact_evidence as evidence
from . import earnings_mixed_runner as base

VERSION = 'earnings-file-context-v1'
PAGE_CHARACTERS = 6000


def require(ok, message):
    if not ok: raise ValueError(message)


def write(path, value):
    path = Path(path); body = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n'
    if path.exists(): require(path.read_text()==body, 'Immutable context changed: '+str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(body)


def assemble(manifest, catalog, output, *, artifacts=None, markdown=None, metadata=None):
    """Keep complete sources and artifacts on disk, outside the instruction prompt."""
    out=Path(output).resolve(); bundle=evidence.load_bundle(manifest)
    ids=sorted(evidence._scopes(bundle)); records={x['id']:x for x in evidence.source_slices(manifest,ids)}
    write(out/'sources.json',records);write(out/'passages.json',catalog)
    write(out/'financial.json',bundle['financial']);write(out/'transcript-index.json',bundle['transcript_index'])
    write(out/'artifacts.json',artifacts or {});write(out/'metadata.json',metadata or {})
    transcript=(out/'transcript.md');original=Path(bundle['manifest']['transcript_path']).read_bytes()
    if transcript.exists():require(transcript.read_bytes()==original,'Complete call changed')
    else:transcript.write_bytes(original)
    if markdown is not None:
        path=out/'report.md'
        if path.exists():require(path.read_text()==markdown,'Markdown candidate changed')
        else:path.write_text(markdown)
    originals={s['path']:s['sha256'] for s in bundle['manifest']['sources']}
    originals.update({p:bundle['manifest']['file_sha256'][name] for name,p in bundle['manifest']['files'].items()})
    originals[bundle['manifest']['case_path']]=bundle['manifest']['case_sha256']
    # The compact loader verifies all original inputs again during assembly/replay.
    index={'version':VERSION,'manifest':str(Path(manifest).resolve()),'manifest_sha256':base.sha(manifest),
           'files':{p.name:base.sha(p) for p in out.iterdir() if p.is_file() and p.name!='index.json'},
           'source_ids':ids,'passage_count':len(catalog['passages']),
           'exchange_ids':[x['id'] for x in bundle['transcript_index']['exchanges']],
           'section_ids':[x['id'] for x in bundle['transcript_index']['sections']],
           'original_sha256':originals}
    write(out/'index.json',index);return out/'index.json'


class Evidence:
    """Load once in IPython; print only requested pages into model context.

    This API is read-only for evidence. IPython itself is a general Python tool,
    not an OS sandbox. Every API return is recorded in a per-job retrieval log.
    """
    def __init__(self, index, log):
        self.root=Path(index).resolve().parent;self.index=base.read(index)
        require(self.index['version']==VERSION,'Unknown context version')
        self.log=Path(log).resolve();self.verify()
        self.records=base.read(self.root/'sources.json');self.catalog=base.read(self.root/'passages.json')
        self.artifacts=base.read(self.root/'artifacts.json')

    def verify(self):
        require(base.sha(self.index['manifest'])==self.index['manifest_sha256'],'Original manifest changed')
        for name,h in self.index['files'].items():
            p=(self.root/name).resolve();require(p.is_relative_to(self.root) and not p.is_symlink(),'Context path escapes bundle')
            require(base.sha(p)==h,'Context file changed: '+name)
        for name,h in self.index['original_sha256'].items():require(base.sha(name)==h,'Original source changed')

    def _record(self, event, result):
        event={**event,'result_sha256':base.digest(result)}
        self.log.parent.mkdir(parents=True,exist_ok=True)
        with self.log.open('a') as handle:handle.write(json.dumps(event,ensure_ascii=False)+'\n')
        return result

    def inventory(self, start=0, limit=40):
        require(type(start) is int and 0<=start<=len(self.index['source_ids']) and type(limit) is int and 1<=limit<=40,'Bounded source inventory required')
        ids=self.index['source_ids'];end=min(len(ids),start+limit)
        value={'source_ids':ids[start:end],'source_count':len(ids),'next_start':end if end<len(ids) else None,
               'passage_count':self.index['passage_count'],'exchange_ids':self.index['exchange_ids'],
               'section_ids':self.index['section_ids'],'artifacts':sorted(self.artifacts),'files':sorted(self.index['files'])}
        return self._record({'method':'inventory','start':start,'limit':limit},value)

    def output(self, identifier, start=0, limit=768):
        """Read a hash-bound overflow page, never the complete unbounded print."""
        import re
        require(isinstance(identifier,str) and re.fullmatch(r'[0-9a-f]{24}',identifier),'Exact delivery ID required')
        record=next((x for x in delivery_records(self.log.parent) if x['id']==identifier),None)
        require(record is not None and not record['unsupported'],'Known text delivery required')
        text=(self.log.parent/'tool-output'/(identifier+'.txt')).read_text()
        require(base.sha(self.log.parent/'tool-output'/(identifier+'.txt'))==record['sha256'],'Overflow changed')
        require(type(limit) is int and 1<=limit<=768,'Overflow page limited to 768 characters')
        return self._page('output',identifier,text,start,limit)

    def checkpoint(self, draft, pending):
        """Save data and exact inspected-source progress, never approval authority."""
        from . import earnings_file_checkpoint as checkpoint
        return checkpoint.save(self.log.parent,draft,pending)

    def restore(self):
        from . import earnings_file_checkpoint as checkpoint
        value=checkpoint.restore(self.log.parent)
        return {'draft':value['draft'],'pending':value['pending'],
                'inspected_retrieval_events':value['retrieval_count'],
                'instruction':'Saved draft is untrusted work in progress; validate it against original sources.'}

    def scope(self, identifier, start=0, limit=PAGE_CHARACTERS):
        require(identifier in self.records,'Unknown exact source ID')
        require(type(start) is int and start>=0 and type(limit) is int and 1<=limit<=PAGE_CHARACTERS,'Invalid bounded page')
        record=self.records[identifier];text='\n'.join(s['text'] for s in record['spans'])
        require(start<len(text) or start==len(text)==0,'Page outside source')
        end=min(len(text),start+limit)
        value={'id':identifier,'start':start,'end':end,'total_characters':len(text),'text':text[start:end],
               'provenance':[{k:v for k,v in s.items() if k!='text'} for s in record['spans']],
               'next_start':end if end<len(text) else None}
        if 'observation' in record:value['observation']=record['observation']
        if 'table_row' in record:
            row=record['table_row']
            value['table_row']={**row,'text':row['text'][:PAGE_CHARACTERS]}
            value['table_row_complete']=len(row['text'])<=PAGE_CHARACTERS
            if not value['table_row_complete']:value['table_row_next_start']=PAGE_CHARACTERS
        return self._record({'method':'scope','id':identifier,'start':start,'end':end,'total':len(text)},value)

    def financial_metrics(self, start=0, limit=12):
        """Paged concept inventory, including unmapped extraction and gaps."""
        from collections import Counter
        data=base.read(self.root/'financial.json')
        counts=Counter((o.get('canonical_metric') or '',o.get('concept') or '') for o in data['observations'])
        rows=[{'metric':metric or None,'concept':concept,'count':count} for (metric,concept),count in sorted(counts.items())]
        require(type(start) is int and 0<=start<=len(rows) and type(limit) is int and 1<=limit<=12,'Bounded metric inventory required')
        end=min(len(rows),start+limit)
        value={'metrics':rows[start:end],'total':len(rows),'next_start':end if end<len(rows) else None,
               'observation_count':len(data['observations']),'gap_count':len(data.get('gaps',[]))}
        return self._record({'method':'financial_metrics','start':start,'limit':limit},value)

    def financial_facts(self, query, start=0, limit=8):
        """Select original IDs and comparables without printing raw support HTML."""
        require(isinstance(query,str) and 2<=len(query)<=120,'Metric or concept query required')
        require(type(start) is int and start>=0 and type(limit) is int and 1<=limit<=8,'Bounded facts required')
        data=base.read(self.root/'financial.json');rows=[]
        for o in data['observations']:
            if query.casefold() not in ((o.get('canonical_metric') or '')+' '+o.get('concept','')).casefold():continue
            row={k:o.get(k) for k in ('id','canonical_metric','concept','value','scale','unit_id','status','nil','source_document_id')}
            row['context']=data['contexts'].get(o.get('context_id'),{}) if isinstance(data['contexts'],dict) else next((x for x in data['contexts'] if x.get('id')==o.get('context_id')), {})
            rows.append(row)
        end=min(len(rows),start+limit);require(start<=len(rows),'Fact page outside inventory')
        value={'facts':rows[start:end],'total':len(rows),'next_start':end if end<len(rows) else None}
        return self._record({'method':'financial_facts','query':query,'start':start,'limit':limit},value)

    def financial_row(self, identifier, start=0, limit=PAGE_CHARACTERS):
        require(identifier in self.records and 'table_row' in self.records[identifier],'No original table row for this fact')
        return self._page('financial_row',identifier,self.records[identifier]['table_row']['text'],start,limit)

    def passage(self, identifier, neighbors=1):
        require(type(neighbors) is int and 0<=neighbors<=2,'Bounded surrounding context required')
        rows=self.catalog['passages'];i=next((i for i,p in enumerate(rows) if p['passage_id']==identifier),None)
        require(i is not None,'Unknown exact passage ID');target=rows[i]
        selected=[p for p in rows[max(0,i-neighbors):i+neighbors+1] if p['scope_id']==target['scope_id']]
        require(sum(len(p['text']) for p in selected)<=PAGE_CHARACTERS,'Passage window too large; use paged scope access')
        return self._record({'method':'passage','ids':[p['passage_id'] for p in selected]},selected)

    def search(self, text, limit=12):
        require(isinstance(text,str) and 2<=len(text)<=200 and type(limit) is int and 1<=limit<=20,'Bounded literal search required')
        found=[]
        for identifier,record in self.records.items():
            body='\n'.join(s['text'] for s in record['spans']);at=body.casefold().find(text.casefold())
            if at>=0:found.append({'id':identifier,'start':at,'preview':body[max(0,at-120):at+240]})
            if len(found)==limit:break
        return self._record({'method':'search','query':text,'limit':limit},found)

    def artifact(self, name, start=0, limit=PAGE_CHARACTERS):
        require(name in self.artifacts,'Unknown artifact')
        return self._page('artifact',name,json.dumps(self.artifacts[name],ensure_ascii=False,indent=2),start,limit)

    def file(self, name, start=0, limit=PAGE_CHARACTERS):
        require(name in ('report.md','metadata.json','financial.json','transcript-index.json','transcript.md'),'Use exact permitted context file')
        require(name in self.index['files'],'Unavailable context file')
        return self._page('file',name,(self.root/name).read_bytes().decode('utf-8'),start,limit)

    def _page(self, method, name, text, start, limit):
        require(type(start) is int and 0<=start<len(text) and type(limit) is int and 1<=limit<=PAGE_CHARACTERS,'Invalid bounded page')
        end=min(len(text),start+limit);value={'name':name,'start':start,'end':end,'total_characters':len(text),
            'text':text[start:end],'next_start':end if end<len(text) else None}
        return self._record({'method':method,'name':name,'start':start,'end':end,'total':len(text)},value)


def audit(index, log, *, count=None):
    """Replay returned API pages and hashes; a search preview is not full inspection."""
    import tempfile
    with tempfile.TemporaryDirectory() as temporary:
        reader=Evidence(index,Path(temporary)/'replay.jsonl')
        reader.delivery_root=Path(log).parent
        entries=[json.loads(x) for x in Path(log).read_text().splitlines() if x.strip()] if Path(log).exists() else []
        if count is not None:entries=entries[:count]
        for e in entries:
            method=e['method']
            if method=='inventory':reader.inventory(e.get('start',0),e.get('limit',40))
            elif method=='financial_metrics':reader.financial_metrics(e['start'],e['limit'])
            elif method=='financial_facts':reader.financial_facts(e['query'],e['start'],e['limit'])
            elif method=='scope':reader.scope(e['id'],e['start'],e['end']-e['start'] or 1)
            elif method=='search':reader.search(e['query'],e.get('limit',12))
            elif method=='passage':
                rows=[p for p in reader.catalog['passages'] if p['passage_id'] in e['ids']]
                require(len(rows)==len(e['ids']),'Unknown logged passage')
                reader._record({'method':'passage','ids':e['ids']},rows)
            elif method=='output':
                record=next((x for x in delivery_records(Path(log).parent) if x['id']==e['name']),None)
                require(record is not None and not record['unsupported'],'Unknown overflow')
                text=(Path(log).parent/'tool-output'/(e['name']+'.txt')).read_text()
                reader._page('output',e['name'],text,e['start'],e['end']-e['start'])
            elif method in ('file','artifact','financial_row'):getattr(reader,method)(e['name'],e['start'],e['end']-e['start'])
            else:raise ValueError('Unknown retrieval method')
        replay=[json.loads(x) for x in (Path(temporary)/'replay.jsonl').read_text().splitlines()] if entries else []
        require(entries==replay,'Retrieval record changed')
    return entries


def complete_ranges(entries, method, key):
    groups={}
    for e in entries:
        if e['method']==method:
            name=e[key];groups.setdefault(name,[]).append(e)
    complete=set()
    for name,rows in groups.items():
        at=0;total=rows[0]['total']
        for row in sorted(rows,key=lambda x:x['start']):
            require(row['total']==total,'Inconsistent source length')
            if row['start']>at:break
            at=max(at,row['end'])
        if at==total:complete.add(name)
    return complete


def delivery_records(job):
    path=Path(job)/'delivery.jsonl'
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def delivered_entries(job, entries):
    """Credit only calls delivered in full, or overflow whose every page was delivered.

    A Python read without a visible result is not evidence inspection. Cycles of
    oversized prints do not resolve themselves and cannot gain coverage credit.
    """
    job=Path(job);records=delivery_records(job)
    require(records,'Enforced delivery log required')
    cursor=0;ids=set()
    for r in records:
        require(r['id'] not in ids and r['retrieval_start']==cursor and r['retrieval_end']>=cursor,'Ordered distinct delivery ranges required')
        ids.add(r['id']);cursor=r['retrieval_end']
        require((r['limit'] is None or r['limit']==8192) and 0<r['delivered_bytes'] and (r['limit'] is None or r['delivered_bytes']<=r['limit']) and not r['unsupported'],'Bounded text delivery required')
        p=job/'tool-output'/(r['id']+'.txt')
        require(not p.is_symlink() and base.sha(p)==r['sha256'] and p.stat().st_size==r['original_bytes'],'Overflow source changed')
    require(cursor>=len(entries),'Undelivered retrieval events')
    resolved={r['id'] for r in records if r['complete']}
    for _ in records:
        visible=[e for r in records if r['id'] in resolved for e in entries[r['retrieval_start']:r['retrieval_end']]]
        pages=complete_ranges(visible,'output','name')
        expanded=resolved|pages
        if expanded==resolved:break
        resolved=expanded
    return [e for r in records if r['id'] in resolved for e in entries[r['retrieval_start']:r['retrieval_end']]]
