"""Bound source-refresh checkouts to selected issuers and referenced source files."""
import json
from pathlib import Path

def paths(root,issuer_ids):
 root=Path(root).resolve();selected=set(issuer_ids)
 if not 1<=len(selected)<=3:raise ValueError('One to three issuers required')
 def read(p):return json.loads((root/p).read_text())
 config=read('config.json');catalog=read('library/catalog.json');latest=read('published/latest.json')['issuers']
 if not selected<=set(latest):raise ValueError('Selected issuer has no packet')
 files={'config.json','workflow.json','library/catalog.json','library/review-queue.json','collection/document-index.json','published/latest.json','published/review-queue.json','published/receipt.json','pipeline/source-coverage.json'}
 files.update(str(p.relative_to(root)) for p in (root/'scripts').glob('*.py'))
 seen=set()
 def collect(value):
  if isinstance(value,dict):
   for v in value.values():collect(v)
  elif isinstance(value,list):
   for v in value:collect(v)
  elif isinstance(value,str) and not value.startswith(('http:','https:')):
   for prefix in ('','collection/'):
    try:
     candidate=(root/(prefix+value)).resolve()
     if not candidate.is_relative_to(root) or not candidate.is_file():continue
    except OSError:continue
    rel=str(candidate.relative_to(root));files.add(rel)
    if candidate.suffix=='.json' and rel not in seen:
     seen.add(rel)
     try:collect(json.loads(candidate.read_text()))
     except (UnicodeError,json.JSONDecodeError):pass
 for iid in selected:
  packet=read('library/packets/'+latest[iid]['packet_id']+'.json');collect(packet)
  files.add('library/packets/'+latest[iid]['packet_id']+'.json')
  if packet.get('catalog_id'):files.add('library/snapshots/'+packet['catalog_id']+'.json')
  for d in packet['documents']:
   if d.get('qualification_id'):collect('library/qualifications/'+d['qualification_id']+'.json')
 for d in catalog['documents'].values():
  if d['issuer_id'] in selected:collect(d)
 audit=config['earnings_pipeline']['audit'];files.add(audit)
 for row in read(audit)['results']:
  if row['issuer_id'] in selected:collect(row)
 if config['earnings_pipeline'].get('languages'):files.add(config['earnings_pipeline']['languages'])
 # Catalog rebuild reads every collector manifest before filtering owner, but
 # source bodies outside the selected issuer are deliberately excluded.
 for entry in read('collection/document-index.json').values():files.add('collection/'+entry['manifest_path'])
 for pattern in ('sources/**/http-cache.json','library/qualifications/*.json'):
  files.update(str(p.relative_to(root)) for p in root.glob(pattern))
 return sorted(p for p in files if (root/p).is_file())
