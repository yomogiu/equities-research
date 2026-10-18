/** Worker-local connection selection. No request retry or TLS bypass. */
import dns from 'node:dns';
import net from 'node:net';
export function configureWorkerConnections(dnsApi=dns,netApi=net) {
  dnsApi.setDefaultResultOrder('ipv4first');
  netApi.setDefaultAutoSelectFamily(true);
  netApi.setDefaultAutoSelectFamilyAttemptTimeout(1000);
  return {version:'ipv4-first-worker-connect-v1',dns_order:'ipv4first',
    auto_select_family:true,family_attempt_timeout_ms:1000,
    tls_verification:true,request_retries:0};
}
