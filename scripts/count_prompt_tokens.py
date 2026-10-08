#!/usr/bin/env python3
"""Local plain-text token diagnostics. No model calls or admission policy changes."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path


def select_encoding(tiktoken, model=None, encoding=None):
    if encoding:
        return tiktoken.get_encoding(encoding), 'explicit_encoding_assumption'
    if not model:
        raise ValueError('Provide --model or --encoding; no silent tokenizer fallback')
    try:
        return tiktoken.encoding_for_model(model), 'tiktoken_model_mapping'
    except KeyError as exc:
        raise ValueError('Model has no tiktoken mapping; choose --encoding explicitly and treat it as an estimate') from exc


def count_file(path, encoder):
    raw = path.read_bytes()
    text = raw.decode('utf-8')  # Preserve CRLF and exact saved prompt bytes.
    tokens = len(encoder.encode_ordinary(text))  # Source text may contain special-token spellings.
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest(),
            'utf8_bytes': len(raw), 'characters': len(text), 'text_tokens': tokens,
            'bytes_per_token': round(len(raw)/tokens, 4) if tokens else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='+', type=Path, help='UTF-8 files or directories containing prompt.txt files')
    parser.add_argument('--model')
    parser.add_argument('--encoding', help='Explicit tokenizer assumption, e.g. o200k_base')
    parser.add_argument('--output', type=Path, help='New diagnostic JSON file; existing files are never overwritten')
    args = parser.parse_args()
    try:
        import tiktoken
        encoder, mapping = select_encoding(tiktoken, args.model, args.encoding)
        files = set()
        for p in args.paths:
            if p.is_dir(): files.update(x.resolve() for x in p.rglob('prompt.txt') if x.is_file())
            elif p.is_file(): files.add(p.resolve())
            else: raise ValueError('Input path does not exist: '+str(p))
        if not files: raise ValueError('No prompt files found')
        rows = [count_file(p, encoder) for p in sorted(files)]
        result = {'version': 1, 'tiktoken_version': importlib.metadata.version('tiktoken'),
                  'requested_model': args.model, 'encoding': encoder.name, 'mapping': mapping,
                  'scope': 'Plain text only; excludes runtime message framing, hidden instructions, reasoning and future output. Model mapping is a library mapping, not server attestation.',
                  'admission_policy_changed': False, 'files': rows,
                  'total_text_tokens': sum(r['text_tokens'] for r in rows)}
        body = json.dumps(result, indent=2, ensure_ascii=False)+'\n'
        if args.output:
            with args.output.open('x', encoding='utf-8') as f: f.write(body)
        else: print(body, end='')
    except ImportError:
        parser.exit(2, 'Install optional dependency: pip install -r requirements-token-counting.txt\n')
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc)+'\n')


if __name__ == '__main__': main()
