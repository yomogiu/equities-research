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
export function instrumentFetch(fetchImpl, record, lifecycle = () => {}) {
  let sequence = 0;
  const emit = value => { try { lifecycle(value); } catch {} };
  return async function(...args) {
    const request_sequence = ++sequence;
    emit({request_sequence, phase:'fetch_started', execution_certainty:'unknown', retry_authorized:false});
    try {
      const response = await fetchImpl.apply(this,args);
      emit({request_sequence, phase:'headers_received', execution_certainty:'unknown', retry_authorized:false});
      return response;
    } catch (error) {
      const diagnostic = failureCodes(error);
      emit({request_sequence, phase:'fetch_failed', ...diagnostic});
      try { record(diagnostic); } catch {} throw error;
    }
  };
}
