"""Two immutable exact-source proofs, preserving the original report packet."""
from pathlib import Path
from . import library,earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-two-link-source-currentness-v1'
def checked(root,first,last,stamp,*,as_of=None):
 from . import earnings_source_revalidation as s
 a=b.read(first);z=b.read(last)
 c.require(a['version']==z['version']==s.VERSION and a['new_packet_id']==z['old_packet_id'],'Exact adjacent ordinary source proofs required')
 receipt=b.read(library.resolve(root,a['source_receipt']));c.require(stamp==receipt['checked_at'],'Historical first observation must be exact recorded receipt time')
 old=s.verify(root,first,as_of=stamp);mid=s.verify(root,last,as_of=as_of)
 c.require(old['issuer_id']==mid['issuer_id'] and old['period']==mid['period'],'Source chain scope changed')
 return old
def prepare(root,first,last,output):
 root=Path(root).resolve();first=Path(first).resolve();last=Path(last).resolve();a=b.read(first);z=b.read(last);stamp=b.read(library.resolve(root,a['source_receipt']))['checked_at'];checked(root,first,last,stamp)
 v={'version':VERSION,'old_packet_id':a['old_packet_id'],'new_packet_id':z['new_packet_id'],'first':str(first.relative_to(root)),'first_sha256':b.sha(first),'last':str(last.relative_to(root)),'last_sha256':b.sha(last),'first_as_of':stamp};c.require(not Path(output).exists(),'New immutable chain required');c.write(output,v);return v
def verify(root,path,*,as_of=None):
 root=Path(root).resolve();v=b.read(path);c.require(set(v)=={'version','old_packet_id','new_packet_id','first','first_sha256','last','last_sha256','first_as_of'} and v['version']==VERSION,'Exact source chain fields required');first=library.resolve(root,v['first']);last=library.resolve(root,v['last']);c.require(b.sha(first)==v['first_sha256'] and b.sha(last)==v['last_sha256'],'Source proof chain changed');a=b.read(first);z=b.read(last);c.require(v['old_packet_id']==a['old_packet_id'] and v['new_packet_id']==z['new_packet_id'],'Chain endpoints changed');return checked(root,first,last,v['first_as_of'],as_of=as_of)
def bindings(root,path):
 from . import earnings_source_revalidation as s
 root=Path(root).resolve();path=Path(path).resolve();verify(root,path);v=b.read(path);return {str(path.relative_to(root)):b.sha(path),**s.input_bindings(root,library.resolve(root,v['first']),as_of=v['first_as_of']),**s.input_bindings(root,library.resolve(root,v['last']))}
