"""Bounded public HTTPS retrieval with persistent conditional caching. No model calls."""
import hashlib
import ipaddress
import json
import socket
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, parse_qsl
from urllib.request import HTTPRedirectHandler, Request, build_opener

# Public-site compatibility syntax, retaining the actual automated client identity.
# Regulator clients must continue supplying their required contact User-Agent.
PUBLIC_USER_AGENT = 'Mozilla/5.0 (compatible; equities-research/0.1; +https://github.com/yomogiu/equities-research)'


class FetchError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    temp.chmod(0o600)
    temp.replace(path)


def check_url(url, hosts, resolve=True):
    try:
        u = urlsplit(url)
        port = u.port
    except ValueError as exc:
        raise FetchError('unapproved_url') from exc
    if any(k.lower() in ('token', 'key', 'api_key', 'signature', 'x-amz-signature') for k, _ in parse_qsl(u.query)):
        raise FetchError('credential_url')
    if (u.scheme != 'https' or not u.hostname or u.username or u.password
            or port not in (None, 443) or u.hostname.lower() not in hosts):
        raise FetchError('unapproved_url')
    if resolve:
        try:
            addresses = socket.getaddrinfo(u.hostname, 443, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise FetchError('dns_error') from exc
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise FetchError('non_public_address')
    return u


class Redirects(HTTPRedirectHandler):
    def __init__(self, hosts):
        super().__init__()
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl, self.hosts)
        # Do not forward conditional validators to a different URL.
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new:
            new.remove_header('If-none-match')
            new.remove_header('If-modified-since')
        return new


class Client:
    def __init__(self, root, hosts, user_agent, max_requests=160,
                 max_bytes=64 * 1024 * 1024, max_document_bytes=16 * 1024 * 1024,
                 interval=.25, transport=None, sleep=time.sleep):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.hosts = {h.lower() for h in hosts}
        self.user_agent = user_agent
        self.max_requests, self.max_bytes = max_requests, max_bytes
        self.max_document_bytes, self.interval = max_document_bytes, interval
        self.transport, self.sleep = transport, sleep
        self.requests = self.bytes = self.cache_hits = 0
        self.last_request = 0
        self.path = self.root / 'http-cache.json'
        self.cache = json.loads(self.path.read_text()) if self.path.exists() else {}

    def object(self, data, suffix='bin'):
        sha = hashlib.sha256(data).hexdigest()
        relative = f'objects/{sha}.{suffix}'
        path = self.root / relative
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(0o600)
        return relative

    def _cached(self, entry):
        if not entry:
            return None
        p = self.root / entry['body_path']
        if not p.exists():
            return None
        data = p.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise FetchError('cache_integrity_error')
        return data

    def _request(self, url, headers):
        if self.transport:
            return self.transport(url, headers)
        req = Request(url, headers=headers)
        try:
            with build_opener(Redirects(self.hosts)).open(req, timeout=25) as response:
                body = response.read(self.max_document_bytes + 1)
                return response.status, dict(response.headers.items()), body, response.url
        except HTTPError as exc:
            return exc.code, dict(exc.headers.items()), b'', url
        except (URLError, TimeoutError, OSError) as exc:
            raise FetchError('network_error') from exc

    def get(self, url, fresh_seconds=900):
        check_url(url, self.hosts, resolve=self.transport is None)
        entry = self.cache.get(url)
        cached = self._cached(entry)
        now = time.time()
        if cached is not None and now - entry.get('checked_at', 0) < fresh_seconds:
            self.cache_hits += 1
            return cached, entry
        headers = {'User-Agent': self.user_agent, 'Accept-Encoding': 'identity',
                   'Accept': 'application/json,text/html,application/pdf,text/plain,application/xml,*/*'}
        if cached is not None:
            if entry.get('etag'):
                headers['If-None-Match'] = entry['etag']
            if entry.get('last_modified'):
                headers['If-Modified-Since'] = entry['last_modified']
        for attempt in range(2):
            if self.requests >= self.max_requests or self.bytes >= self.max_bytes:
                raise FetchError('run_budget_exhausted')
            self.sleep(max(0, self.interval - (time.monotonic() - self.last_request)))
            self.requests += 1
            self.last_request = time.monotonic()
            status, result_headers, body, final_url = self._request(url, headers)
            check_url(final_url, self.hosts, resolve=self.transport is None)
            h = {k.lower(): v for k, v in result_headers.items()}
            if status == 304 and cached is not None:
                entry['checked_at'] = now
                save_json(self.path, self.cache)
                self.cache_hits += 1
                return cached, entry
            if status in (429, 500, 502, 503, 504) and attempt == 0:
                retry = h.get('retry-after', '2')
                if not retry.isdigit() or int(retry) > 10:
                    raise FetchError('retry_later')
                self.sleep(max(2, int(retry)))
                continue
            if status != 200:
                raise FetchError('access_blocked' if status in (401, 403) else f'http_{status}')
            if len(body) > self.max_document_bytes or self.bytes + len(body) > self.max_bytes:
                raise FetchError('size_limit')
            self.bytes += len(body)
            # Detect common soft-block responses; never retry with disguised identities.
            first = body[:5000].lower()
            if any(x in first for x in (b'undeclared automated tool', b'your request originates',
                                       b'<title>access denied', b'<title>just a moment')):
                raise FetchError('access_blocked')
            entry = {'body_path': self.object(body), 'sha256': hashlib.sha256(body).hexdigest(),
                     'content_type': h.get('content-type', ''), 'etag': h.get('etag'),
                     'last_modified': h.get('last-modified'), 'final_url': final_url,
                     'checked_at': now}
            self.cache[url] = entry
            save_json(self.path, self.cache)
            return body, entry
        raise FetchError('retry_later')
