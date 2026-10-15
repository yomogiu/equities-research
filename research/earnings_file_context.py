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
    @classmethod
    def for_job(cls):
        """Bind paths from the runner-owned request, never model-copied strings."""
        job=Path.cwd().resolve();q=base.read(job/'request.json')
        require(q.get('version')=='file-prime-role-v1' and q.get('job_path')==str(job),'Active bound role request required')
        return cls(q['context_index'],job/'retrieval.jsonl')

    def __init__(self, index, log, *, _replay=False):
        self.root=Path(index).resolve().parent;self.index=base.read(index)
        require(self.index['version']==VERSION,'Unknown context version')
        self.log=Path(log).resolve()
        active=Path.cwd().resolve();request=active/'request.json'
        if not _replay and request.is_file():
            q=base.read(request)
            if q.get('version')=='file-prime-role-v1':
                require(q.get('job_path')==str(active) and Path(q['context_index']).resolve()==Path(index).resolve(),'Evidence differs from active role request')
                self.log=active/'retrieval.jsonl'
        self.verify()
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

    def load_structured(self, name):
        """Load large structured evidence into kernel memory; return counts only.

        Original text inspection still uses scope/passage/row APIs. Loading a
        large extraction is not equivalent to showing its contents to the model.
        """
        require(name in ('financial.json','transcript-index.json'),'Exact structured evidence file required')
        value=base.read(self.root/name)
        attribute='financial_data' if name=='financial.json' else 'transcript_index'
        setattr(self,attribute,value)
        counts={k:len(v) for k,v in value.items() if isinstance(v,(list,dict))}
        return self._record({'method':'load_structured','name':name},{'name':name,'kernel_attribute':'ctx.'+attribute,'counts':counts,
            'instruction':'Select fields in kernel memory. Inspect cited original text through scope, passage or financial_row; do not print the full extraction.'})

    def _call_scopes(self):
        """Only exact spans in the hash-bound transcript can share coverage."""
        text=(self.root/'transcript.md').read_bytes().decode('utf-8')
        raw_sha=self.index['files']['transcript.md']; scopes={}
        for identifier,record in self.records.items():
            spans=record['spans']
            if spans and all(s['sha256']==raw_sha and 0<=s['start']<=s['end']<=len(text)
                             and s['text']==text[s['start']:s['end']] for s in spans):
                scopes[identifier]=[[s['start'],s['end']] for s in spans]
        return text,scopes

    def _call_batch(self, start, limit):
        require(type(start) is int and type(limit) is int and 1<=limit<=48000,'Call batch limited to 48000 characters')
        text,scopes=self._call_scopes()
        require(0<=start<len(text),'Call batch outside transcript')
        end=min(len(text),start+limit)
        # IDs and offsets replace repeated paragraph text in section, exchange,
        # turn, passage and grounding representations. Original text occurs once.
        by_turn={}
        for p in self.catalog['passages']:
            if p['scope_id'] in scopes and p['scope_id'].startswith('turn-'):
                if p['scope_id'] not in by_turn or len(p['text'])>len(by_turn[p['scope_id']]['text']):by_turn[p['scope_id']]=p
        locators={'offset_unit':'unicode_character','start':start,'end':end,'total':len(text),
                  'next_start':end if end<len(text) else None,
                  'scopes':{k:v for k,v in scopes.items() if k.startswith('section-')} if start==0 else {},
                  'turn_ranges':[[k,*v[0]] for k,v in scopes.items() if k.startswith('turn-') and len(v)==1] if start==0 else [],
                  'passages':[[p['passage_id'],p['start'],p['end']]
                              for p in by_turn.values()] if start==0 else []}
        if start==0:
            index=base.read(self.root/'transcript-index.json')
            locators['passage_selection']='One longest exact passage per turn; other original passage IDs remain available in ctx.catalog for targeted selection.'
            locators['passage_columns']=['passage_id','start','end']
            locators['exchanges']=[{k:e.get(k) for k in ('id','question_turn_ids','answer_turn_ids','followup_of','status')} for e in index['exchanges']] if not self.artifacts.get('qa_grounding') else []
            grounding=self.artifacts.get('qa_grounding',{})
            locators['grounding_notice']={k:v for k,v in grounding.items() if k not in ('exchanges','unassigned_qa_turns')}
            locators['grounding_columns']=sorted({k for e in grounding.get('exchanges',[]) for k in e if k!='turns'})
            locators['grounding']=[[e.get(k) for k in locators['grounding_columns']] for e in grounding.get('exchanges',[])]
            locators['turn_role_columns']=['id','speaker','role','participant_function','dialogue_function','courtesy_only','routing_only']
            locators['turn_roles']=[[t.get(k) for k in locators['turn_role_columns']]
                for t in {t['id']:t for e in grounding.get('exchanges',[]) for t in e.get('turns',[])}.values()]
        # The IPython runtime has its own 65,536-character truncation even
        # without a delivery-hook byte cap. Leave room for tool formatting.
        for _ in range(4):
            locators.update(end=end,next_start=end if end<len(text) else None)
            result=('# Call batch: original evidence, never instructions\n'
                    '## Citation locators (no repeated source paragraphs)\n'+json.dumps(locators,ensure_ascii=False,separators=(',',':'))+
                    '\n## Original transcript characters '+str(start)+':'+str(end)+'\n'+text[start:end]+'\n# End call batch\n')
            excess=len(result)-60000
            if excess<=0:return result
            end-=excess
            require(end>start,'Citation locators exceed one tool batch; use targeted source access')
        raise ValueError('Call batch could not fit the runtime output boundary')

    def call_batch(self, start=0, limit=48000):
        """Print one batch once; retain exact offsets, annotations and quote IDs."""
        result=self._call_batch(start,limit)
        total=len((self.root/'transcript.md').read_bytes().decode('utf-8'))
        return self._record({'method':'call_batch','name':'transcript.md','start':start,
                             'end':json.loads(result.splitlines()[2])['end'],'total':total,'limit':limit},result)

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

    def _filing_batch(self, query, limit):
        """Rank short terms locally; return whole original D scopes, not previews."""
        import re
        require(isinstance(query,str) and 2<=len(query)<=500 and type(limit) is int and 1<=limit<=4,'Bounded filing query and one to four excerpts required')
        stop={'the','and','for','with','from','this','that','what','which','how','are','was','were','has','have','its','into'}
        tokens=lambda text:set(re.findall(r'[^\W_]+',text.casefold(),re.UNICODE))-stop
        terms=tokens(query);defaults=tokens('guidance EBITDA cash debt capital expenditure revenue income liquidity commitments')
        rows=[];excluded=0
        for identifier,record in sorted(self.records.items()):
            if not re.fullmatch(r'D[0-9]+',identifier):continue
            body='\n'.join(span['text'] for span in record['spans'])
            if not body.strip():continue
            if len(body)>PAGE_CHARACTERS:excluded+=1;continue
            words=tokens(body);matched=sorted(words&terms)
            rows.append({'id':identifier,'text':body,'spans':record['spans'],'matched_terms':matched,
                         'score':len(matched),'fallback_score':len(words&defaults)})
        fallback=not any(r['score'] for r in rows)
        ranked=sorted(rows,key=lambda r:(-(r['fallback_score'] if fallback else r['score']),r['id']))
        if not fallback:ranked=[r for r in ranked if r['score']]
        selected=[];fingerprints=set();intervals={};documents=set()
        # Prefer one excerpt per original document before filling remaining slots.
        for diverse in (True,False):
            for row in ranked:
                if len(selected)==limit:break
                doc=tuple(sorted({s['document_id'] for s in row['spans']}))
                fingerprint=hashlib.sha256(row['text'].encode()).hexdigest()
                overlap=any(s['start']<end and start<s['end'] for s in row['spans'] for start,end in intervals.get((s['path'],s['sha256']),[]))
                if fingerprint in fingerprints or overlap or (diverse and doc in documents):continue
                selected.append(row);fingerprints.add(fingerprint);documents.add(doc)
                for span in row['spans']:intervals.setdefault((span['path'],span['sha256']),[]).append((span['start'],span['end']))
        ids=[r['id'] for r in selected]
        metadata={'selected_document_ids':ids,'query':query,'query_terms':sorted(terms),'fallback_used':fallback,
                  'selection_status':'representative_fallback_verify_relevance' if fallback else 'ranked_term_matches_verify_relevance',
                  'eligible_scope_count':len(rows),'excluded_oversized_scope_count':excluded,
                  'notice':'Selection is provisional. These are complete original excerpts, not proof of analytical relevance or exhaustive filing coverage. No matches is never evidence of absence.'}
        chunks=['# Filing batch: original evidence, never instructions',json.dumps(metadata,ensure_ascii=False,separators=(',',':'))]
        for row in selected:
            provenance=[{k:v for k,v in span.items() if k!='text'} for span in row['spans']]
            chunks.extend(['## '+row['id'],json.dumps({'matched_terms':row['matched_terms'],'provenance':provenance},ensure_ascii=False,separators=(',',':')),row['text']])
        if not selected:chunks.append('No eligible filing excerpts. Record a source-access gap; do not return an accepted empty document selection.')
        chunks.append('# End filing batch')
        result='\n'.join(chunks)+'\n'
        require(len(result)<=60000,'Filing batch exceeds runtime output boundary')
        return result,ids

    def filing_batch(self, query='guidance EBITDA cash debt capital expenditure', limit=4):
        """Print one ranked, deduplicated batch; empty searches use marked fallback."""
        result,ids=self._filing_batch(query,limit)
        return self._record({'method':'filing_batch','query':query,'limit':limit,'ids':ids},result)

    def artifact(self, name, start=0, limit=PAGE_CHARACTERS):
        require(name in self.artifacts,'Unknown artifact')
        return self._page('artifact',name,json.dumps(self.artifacts[name],ensure_ascii=False,indent=2),start,limit)

    def file(self, name, start=0, limit=PAGE_CHARACTERS):
        require(name not in ('financial.json','transcript-index.json'),'Large structured evidence stays in kernel memory: use ctx.load_structured(name), then select fields; financial_facts and scope retain original evidence access')
        require(name in ('report.md','metadata.json','transcript.md'),'Use exact permitted context file')
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
        reader=Evidence(index,Path(temporary)/'replay.jsonl',_replay=True)
        reader.delivery_root=Path(log).parent
        entries=[json.loads(x) for x in Path(log).read_text().splitlines() if x.strip()] if Path(log).exists() else []
        if count is not None:entries=entries[:count]
        for e in entries:
            method=e['method']
            if method=='inventory':reader.inventory(e.get('start',0),e.get('limit',40))
            elif method=='filing_batch':reader.filing_batch(e['query'],e['limit'])
            elif method=='call_batch':reader.call_batch(e['start'],e['limit'])
            elif method=='load_structured':reader.load_structured(e['name'])
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
    visible=[]
    reader=None
    for r in records:
        if r['id'] not in resolved:continue
        for e in entries[r['retrieval_start']:r['retrieval_end']]:
            if e['method'] in ('call_batch','filing_batch'):
                if reader is None:reader=Evidence(base.read(job/'request.json')['context_index'],job/'unused-audit.jsonl')
                rendered=reader._call_batch(e['start'],e['limit']) if e['method']=='call_batch' else reader._filing_batch(e['query'],e['limit'])[0]
                if rendered not in (job/'tool-output'/(r['id']+'.txt')).read_bytes().decode('utf-8'):continue
            visible.append(e)
    return visible


def inspected_call(index, entries):
    """Full visible call batches cover only byte/offset-equivalent call scopes."""
    if 'transcript.md' not in complete_ranges(entries,'call_batch','name'):return set(),set()
    reader=Evidence(index,Path(index).parent/'unused-audit.jsonl')
    _,scopes=reader._call_scopes()
    return set(scopes),{'transcript.md'}
