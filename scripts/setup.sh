#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s .agents/skills/translate-documents/scripts -p 'test_*.py' -v
python3 -m research.cli --help
python3 -m research.collect --help
python3 -m research.workspace --help
