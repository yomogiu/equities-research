/** Enforced aggregate tool-result boundary, independent of Python print discipline. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
export const LIMIT=8192;
const hash=x=>crypto.createHash('sha256').update(x).digest('hex');
export function installDelivery(agent,job) {
  const previous=agent.afterToolCall;
  const lines=()=>fs.existsSync(path.join(job,'retrieval.jsonl'))?fs.readFileSync(path.join(job,'retrieval.jsonl'),'utf8').split('\n').filter(Boolean).length:0;
  let start=lines();
  agent.afterToolCall=async (event,signal)=>{
    const prior=previous?await previous(event,signal):undefined;
    const result={...event.result,...prior};
    // IPython is a text-only research transport. Unsupported blocks stop acceptance.
    const content=result.content??[];
    const unsupported=content.some(x=>x.type!=='text');
    const text=unsupported?JSON.stringify(content):content.map(x=>x.text).join('\n');
    const id=hash(event.toolCall.id).slice(0,24);
    const root=path.join(job,'tool-output');fs.mkdirSync(root,{recursive:true,mode:0o700});
    fs.writeFileSync(path.join(root,id+'.txt'),text,{flag:'wx',mode:0o600});
    const end=lines();
    let delivered={content:[{type:'text',text}],details:{delivery_id:id},isError:prior?.isError??event.isError};
    const complete=!unsupported && Buffer.byteLength(JSON.stringify(delivered))<=LIMIT;
    if(!complete) delivered={content:[{type:'text',text:JSON.stringify({complete:false,delivery_id:id,sha256:hash(text),total_characters:[...text].length,
      reason:unsupported?'unsupported_content':'output_limit',next_start:0,read:`ctx.output('${id}', start=0, limit=768)`})}],details:{delivery_id:id},isError:unsupported||delivered.isError};
    const record={id,tool_call_id:event.toolCall.id,sha256:hash(text),original_bytes:Buffer.byteLength(text),unsupported,
      complete,retrieval_start:start,retrieval_end:end,delivered_sha256:hash(JSON.stringify(delivered)),delivered_bytes:Buffer.byteLength(JSON.stringify(delivered)),limit:LIMIT};
    fs.appendFileSync(path.join(job,'delivery.jsonl'),JSON.stringify(record)+'\n',{mode:0o600});start=end;
    return delivered;
  };
}
