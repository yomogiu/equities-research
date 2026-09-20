"""Catalog, evidence packets, and resumable handoffs in a private workspace."""
import argparse
import json

from . import handoffs
from .library import (build_catalog, build_search, catalog, make_packet, materialize,
                      private_root, qualify, read_json, read_span, resolve, resolve_issuer, search, save)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, help='Private data repository root')
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('import')
    p.add_argument('--audit', required=True, help='Private relative path')
    p.add_argument('--languages', help='Private relative path')
    commands.add_parser('index')
    p = commands.add_parser('list')
    p.add_argument('--issuer', help='Stable issuer ID or ticker; ambiguous tickers fail')
    p.add_argument('--kind', help='Candidate document kind, not a qualification')
    p.add_argument('--period-end', help='Candidate YYYY-MM-DD reporting date, not inferred fiscal quarter')
    p.add_argument('--language', help='Screened language label or und')
    p = commands.add_parser('search')
    p.add_argument('query')
    p.add_argument('--issuer')
    p.add_argument('--limit', type=int, default=10)
    p.add_argument('--literal', action='store_true', help='Unicode substring search, including Chinese/Japanese/Korean')
    p = commands.add_parser('read')
    p.add_argument('document_id')
    p.add_argument('--start', type=int, default=0)
    p.add_argument('--end', type=int)
    p = commands.add_parser('qualify')
    p.add_argument('--input', required=True, help='Private relative JSON path; explicit evidence-backed review')
    p = commands.add_parser('packet')
    p.add_argument('--input', required=True, help='Private JSON: issuer_id, period, qualification_ids, missing')
    p = commands.add_parser('materialize')
    p.add_argument('packet_id')
    p.add_argument('--output', required=True, help='New private relative path')
    p = commands.add_parser('plan')
    p.add_argument('packet_id')
    for name in ['status', 'verify']:
        p = commands.add_parser(name)
        p.add_argument('plan_id')
    p = commands.add_parser('claim')
    p.add_argument('plan_id')
    p.add_argument('task_id')
    p.add_argument('--worker', required=True, help='Actual independent agent session ID')
    p.add_argument('--lease-seconds', type=int, default=1800)
    for name in ['complete', 'interrupt']:
        p = commands.add_parser(name)
        p.add_argument('plan_id')
        p.add_argument('task_id')
        p.add_argument('--token', required=True, help='Lease fencing token from claim')
        p.add_argument('--input' if name == 'complete' else '--reason', required=True)
    args = parser.parse_args()
    root = private_root(args.root)
    if args.command == 'import':
        value = build_catalog(root, args.audit, args.languages)
        result = {k: value[k] for k in ['catalog_id', 'input_records', 'deduplicated_records']}
        result.update(issuers=len(value['issuers']), documents=len(value['documents']))
    elif args.command == 'index':
        result = build_search(root)
    elif args.command == 'list':
        cat = catalog(root)
        iid = args.issuer
        if iid:
            iid = resolve_issuer(cat, iid)
        result = [{'document_id': d['document_id'], 'issuer_id': d['issuer_id'],
                   'kind_candidates': d['kind_candidates'], 'period_end_candidates': d['period_end_candidates'],
                   'titles': d['titles'], 'language': d['language'], 'source_qualified': d['source_qualified']}
                  for d in cat['documents'].values()
                  if (not iid or d['issuer_id'] == iid)
                  and (not args.kind or args.kind in d['kind_candidates'])
                  and (not args.period_end or args.period_end in d['period_end_candidates'])
                  and (not args.language or args.language == d['language']['language'])]
    elif args.command == 'search':
        result = search(root, args.query, args.issuer, args.limit, args.literal)
    elif args.command == 'read':
        result = read_span(root, args.document_id, args.start, args.end)
    elif args.command == 'qualify':
        result = qualify(root, read_json(resolve(root, args.input)))
    elif args.command == 'packet':
        data = read_json(resolve(root, args.input))
        value = make_packet(root, data['issuer_id'], data['period'], data['qualification_ids'], data.get('missing'))
        result = {'packet_id': value['packet_id'], 'documents': len(value['documents']), 'translation_required': value['translation_required']}
    elif args.command in {'plan', 'materialize'}:
        value = read_json(resolve(root, f'library/packets/{args.packet_id}.json'))
        if args.command == 'plan':
            result = handoffs.create_plan(root, value)
        else:
            output = resolve(root, args.output)
            if output.exists():
                parser.error('Materialization must use a new private path')
            save(output, materialize(root, value), immutable=True)
            result = {'output': args.output}
    elif args.command == 'status':
        result = read_json(handoffs.plan_path(root, args.plan_id))
    elif args.command == 'claim':
        result = handoffs.claim(root, args.plan_id, args.task_id, args.worker, args.lease_seconds)
    elif args.command == 'complete':
        result = handoffs.complete(root, args.plan_id, args.task_id, args.token, read_json(resolve(root, args.input)))
    elif args.command == 'interrupt':
        result = handoffs.interrupt(root, args.plan_id, args.task_id, args.token, args.reason)
    else:
        result = handoffs.verify_plan(root, args.plan_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
