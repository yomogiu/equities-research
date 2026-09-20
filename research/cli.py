"""Validate Codex role artifacts and render reports without invoking a model."""
import argparse
import json
from pathlib import Path

from .contracts import (packet_id, require, validate_calendar, validate_commentary,
                        validate_extraction, validate_packet, validate_review, watchlist)

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    def invalid(value):
        raise ValueError('Non-standard JSON constant: '+value)
    return json.loads(Path(path).read_text(), parse_constant=invalid)


def private_output(path):
    path = Path(path).resolve()
    require(path != ROOT and ROOT not in path.parents, 'Research output must be outside the public checkout')
    require(not path.exists(), 'Preserve prior report; choose a new version path')
    return path


def render(packet, extraction, commentary, review):
    validate_extraction(extraction, packet)
    validate_commentary(commentary, packet)
    validate_review(review, packet)
    status = 'reviewed' if review['verdict'] == 'pass' else 'needs_attention'
    return '\n\n'.join([
        '# Earnings evidence report\n\nStatus: '+status,
        'Packet: `'+packet_id(packet)+'`',
        '## Quotes and data\n\n'+extraction['report_markdown'],
        '## Framework commentary\n\n'+commentary['report_markdown'],
        '## Independent review\n\n'+review['report_markdown'],
        '## Sources\n\n'+'\n'.join(f"- [{d['title']}]({d['source_url']}) — {d['kind']}; {d['completeness']}; `{d['document_id']}`" for d in packet['documents']),
        '## Document availability\n\n'+'\n'.join(f'- {k}: {v}' for k,v in sorted(packet['availability'].items())),
        'Limited public event update. Private research-library and portfolio context may be unavailable; '
        'this is not a completed position review or an approved portfolio action.'])+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('watchlist','calendar','packet','extraction','commentary','review'):
        command=sub.add_parser(name)
        command.add_argument('--input',required=True,type=Path)
        if name=='calendar':
            command.add_argument('--watchlist',required=True,type=Path)
        if name in ('extraction','commentary','review'):
            command.add_argument('--packet',required=True,type=Path)
        if name=='packet':
            command.add_argument('--previous',type=Path)
            command.add_argument('--output',required=True,type=Path,
                                 help='New private path for normalized packet with document IDs')
    report=sub.add_parser('report')
    for name in ('packet','extraction','commentary','review','output'):
        report.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args()
    if a.command=='report':
        output=private_output(a.output)
        packet=validate_packet(read(a.packet))
        text=render(packet,read(a.extraction),read(a.commentary),read(a.review))
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('x') as f:
            f.write(text)
        output.chmod(0o600)
    else:
        value=read(a.input)
        if a.command=='watchlist':
            watchlist(value)
        elif a.command=='calendar':
            validate_calendar(value,read(a.watchlist))
        elif a.command=='packet':
            output=private_output(a.output)
            previous=validate_packet(read(a.previous)) if a.previous else None
            value=validate_packet(value,previous)
            output.parent.mkdir(parents=True,exist_ok=True)
            with output.open('x') as f:
                json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)
                f.write('\n')
            output.chmod(0o600)
        else:
            packet=validate_packet(read(a.packet))
            {'extraction':validate_extraction,'commentary':validate_commentary,
             'review':validate_review}[a.command](value,packet)
    print(json.dumps({'status':'valid','artifact_type':a.command}))


if __name__=='__main__':
    main()
