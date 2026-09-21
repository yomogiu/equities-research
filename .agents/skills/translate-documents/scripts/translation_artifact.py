"""Prepare and validate traceable translations. Standard library; no model calls."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    def reject(value):
        raise ValueError('Non-finite JSON value: ' + value)
    return json.loads(Path(path).read_text(encoding='utf-8'), parse_constant=reject)


def source(path):
    path = Path(path)
    raw = path.read_bytes()
    if path.suffix == '.gz':
        raw = gzip.decompress(raw)
    text = raw.decode('utf-8')
    require(bool(text.strip()), 'Source text is empty')
    require('\x00' not in text, 'Source must be extracted UTF-8 text, not a binary file')
    return text, hashlib.sha256(raw).hexdigest()


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    with path.open('x', encoding='utf-8', newline='') as stream:
        stream.write(body)


def interval(value, length):
    a, b = value['start'], value['end']
    require(type(a) is int and type(b) is int and 0 <= a < b <= length,
            'Offsets must be integers with 0 <= start < end <= source length')
    return a, b


def prepare(text, sha, source_language, target_language, max_chars=6000, ranges=None, document_id=None):
    require(source_language.strip() and target_language.strip(), 'Both languages are required')
    require(type(max_chars) is int and max_chars > 0, 'Chunk size must be a positive integer')
    selected = sorted(interval(r, len(text)) for r in ranges) if ranges is not None else [(0, len(text))]
    require(bool(selected), 'At least one selected interval is required')
    segments, omitted, cursor = [], [], 0
    for a, b in selected:
        require(a >= cursor, 'Selected intervals overlap')
        if a > cursor:
            omitted.append({'start': cursor, 'end': a})
        pos = a
        while pos < b:
            end = min(pos + max_chars, b)
            if end < b:
                boundary = text.rfind('\n', pos + max_chars // 2, end)
                if boundary >= pos:
                    end = boundary + 1
            segments.append({'start': pos, 'end': end, 'original_text': text[pos:end],
                             'translated_text': '', 'label': 'translation'})
            pos = end
        cursor = b
    if cursor < len(text):
        omitted.append({'start': cursor, 'end': len(text)})
    return {'schema_version': 1, 'document_id': document_id or sha, 'source_sha256': sha,
            'source_language': source_language, 'target_language': target_language,
            'scope': 'selected' if omitted else 'full', 'translator_version': '',
            'glossary': [], 'notes': [], 'segments': segments, 'untranslated_ranges': omitted}


def validate(value, text, sha):
    require(value['schema_version'] == 1, 'Unsupported schema version')
    require(value['source_sha256'] == sha, 'Source hash mismatch; extraction may have changed')
    for key in ['document_id', 'source_language', 'target_language', 'translator_version']:
        require(isinstance(value[key], str) and value[key].strip(), key + ' is required')
    require(value['scope'] in {'full', 'selected'}, 'Scope must be full or selected')
    require(isinstance(value['segments'], list) and value['segments'], 'Translation segments required')
    require(isinstance(value['untranslated_ranges'], list), 'Untranslated ranges must be a list')
    intervals, translated, previous = [], 0, -1
    for seg in value['segments']:
        a, b = interval(seg, len(text))
        require(a >= previous, 'Translation segments must be ordered and nonoverlapping')
        previous = b
        require(seg['original_text'] == text[a:b], 'Original text differs from exact source span')
        require(seg['label'] == 'translation', 'Rendering must be labeled translation')
        require(isinstance(seg['translated_text'], str) and seg['translated_text'].strip(),
                'Empty translation; draft is incomplete')
        intervals.append((a, b))
        translated += b - a
    previous = -1
    for row in value['untranslated_ranges']:
        a, b = interval(row, len(text))
        require(a >= previous, 'Untranslated ranges must be ordered and nonoverlapping')
        previous = b
        intervals.append((a, b))
    cursor = 0
    for a, b in sorted(intervals):
        require(a == cursor, 'Coverage has a gap or overlap')
        cursor = b
    require(cursor == len(text), 'Coverage does not account for the full source')
    require(value['scope'] != 'full' or translated == len(text), 'Full scope contains untranslated text')
    body = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return {'structurally_valid': True, 'semantic_review': 'separate review required',
            'source_sha256': sha, 'translation_sha256': hashlib.sha256(body).hexdigest(),
            'source_characters': len(text), 'translated_source_characters': translated,
            'untranslated_source_characters': len(text) - translated,
            'coverage_percent': round(100 * translated / len(text), 4), 'scope': value['scope']}


def export_workspace(value):
    require(value['target_language'] == 'en', 'Current earnings workspace requires target language en')
    result = {key: value[key] for key in ['document_id', 'source_sha256', 'source_language',
                                        'target_language', 'translator_version', 'untranslated_ranges']}
    result['segments'] = [{**{k: seg[k] for k in ['start', 'end', 'original_text', 'label']},
                           'english_text': seg['translated_text']} for seg in value['segments']]
    for key in ['notes', 'glossary']:
        if key in value:
            result[key] = value[key]
    return result


def render(value, receipt):
    lines = ['# Document translation', '',
             f"Language: {value['source_language']} → {value['target_language']}", '',
             f"Coverage: {receipt['scope']}; {receipt['coverage_percent']}% of extracted source characters.", '',
             f"Source SHA-256: `{receipt['source_sha256']}`", '',
             f"Translation SHA-256: `{receipt['translation_sha256']}`", '',
             'Machine-assisted translation. Structural checks passed; consult the separate semantic review.', '']
    for seg in value['segments']:
        lines.extend([f"## Translation — source characters {seg['start']}–{seg['end']}", '', seg['translated_text'], ''])
    for key in ['glossary', 'notes', 'untranslated_ranges']:
        if value.get(key):
            lines.extend(['## ' + key.replace('_', ' ').capitalize(), '', '```json',
                          json.dumps(value[key], ensure_ascii=False, indent=2), '```', ''])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ['prepare', 'validate', 'render', 'export-workspace']:
        sub = commands.add_parser(command)
        sub.add_argument('--source', required=True)
        if command == 'prepare':
            sub.add_argument('--source-language', required=True)
            sub.add_argument('--target-language', required=True)
            sub.add_argument('--document-id')
            sub.add_argument('--max-chars', type=int, default=6000)
            sub.add_argument('--ranges', help='JSON intervals; omission selects all extracted text')
        else:
            sub.add_argument('--input', required=True)
        if command != 'validate':
            sub.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        text, sha = source(args.source)
        if args.command == 'prepare':
            value = prepare(text, sha, args.source_language, args.target_language, args.max_chars,
                            read_json(args.ranges) if args.ranges else None, args.document_id)
            write_new(args.output, value)
            print(json.dumps({'status': 'draft_requires_translation', 'segments': len(value['segments']),
                              'scope': value['scope'], 'source_sha256': sha}))
        else:
            value = read_json(args.input)
            receipt = validate(value, text, sha)
            if args.command == 'render':
                write_new(args.output, render(value, receipt))
            elif args.command == 'export-workspace':
                write_new(args.output, export_workspace(value))
            print(json.dumps(receipt))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(2, f'{error}\n')


if __name__ == '__main__':
    main()
