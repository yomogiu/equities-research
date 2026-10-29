/** Network failure codes only: never record URL, headers, body, messages or stack. */
const ALLOWED = new Set(['ECONNRESET','ECONNREFUSED','ENOTFOUND','EAI_AGAIN','ETIMEDOUT',
  'EHOSTUNREACH','ENETUNREACH','EPIPE','UND_ERR_CONNECT_TIMEOUT','UND_ERR_SOCKET',
  'UND_ERR_HEADERS_TIMEOUT','UND_ERR_BODY_TIMEOUT','CERT_HAS_EXPIRED',
  'UNABLE_TO_VERIFY_LEAF_SIGNATURE','UNABLE_TO_GET_ISSUER_CERT_LOCALLY',
  'DEPTH_ZERO_SELF_SIGNED_CERT','ERR_TLS_CERT_ALTNAME_INVALID']);
export function failureCodes(error) {
  const found = new Set(); const seen = new Set();
  function visit(value, depth) {
    if (!value || typeof value !== 'object' || seen.has(value) || depth > 4) return;
    seen.add(value);
    if (ALLOWED.has(value.code)) found.add(value.code);
    visit(value.cause, depth + 1);
    if (Array.isArray(value.errors)) for (const e of value.errors.slice(0,4)) visit(e, depth+1);
  }
  visit(error,0);
  return {version:'sanitized-network-codes-v1', codes:[...found].sort(),
    execution_certainty:'unknown', retry_authorized:false};
}
// Header receipt does not prove that the response stream or model turn completed.
export function completionStage(last) {
  if (last?.role === 'assistant' && ['error','aborted'].includes(last.stopReason)) return 'model_request';
  return 'output_validation';
}
export function instrumentFetch(fetchImpl, record, lifecycle = () => {}, rejectionRetry = false) {
  let sequence = 0;
  let rejectedRetries = 0;
  const emit = value => { try { lifecycle(value); } catch {} };
  async function rejected(response) {
    if (![429,503].includes(response.status) || !response.headers?.get('content-type')?.includes('application/json')) return false;
    const reader=response.clone().body?.getReader();if(!reader)return false;
    let bytes=0,chunks=[];
    try {
      for(;;){const {done,value}=await reader.read();if(done)break;bytes+=value.length;if(bytes>16384)return false;chunks.push(Buffer.from(value));}
      const body=JSON.parse(Buffer.concat(chunks).toString('utf8'));
      return Object.keys(body).length===1 && body.error &&
        ['server_overloaded','rate_limit_exceeded'].includes(body.error.code) &&
        !('usage' in body.error) && !('output' in body.error) && !('response' in body.error);
    } catch {return false;} finally {void reader.cancel().catch(()=>{});}
  }
  return async function thisFetch(...args) {
    const request_sequence = ++sequence;
    emit({request_sequence, phase:'fetch_started', execution_certainty:'unknown', retry_authorized:false});
    try {
      const response = await fetchImpl.apply(this,args);
      emit({request_sequence, phase:'headers_received',
        ...(Number.isInteger(response.status)?{http_status:response.status}:{}),
        execution_certainty:'unknown', retry_authorized:false});
      if (rejectionRetry && rejectedRetries===0 && await rejected(response)) {
        rejectedRetries++;
        emit({request_sequence,phase:'explicit_provider_rejection',http_status:response.status,
          execution_certainty:'rejected_without_output',retry_authorized:true});
        await new Promise(resolve=>setTimeout(resolve,2000));
        // Retry only this explicit closed rejection, once per role. Network
        // exceptions, SSE errors, partial output and uncertain requests never qualify.
        void response.body?.cancel().catch(()=>{});
        return thisFetch(...args);
      }
      return response;
    } catch (error) {
      const diagnostic = failureCodes(error);
      emit({request_sequence, phase:'fetch_failed', ...diagnostic});
      try { record(diagnostic); } catch {} throw error;
    }
  };
}
