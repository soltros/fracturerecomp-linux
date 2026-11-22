#!/usr/bin/env python3
"""Validate the shipped profile against the vendored official SDK schema."""
import json
from pathlib import Path
import sys
import jsonschema

root = Path(__file__).resolve().parents[1]
schema = json.loads((root / '.github/recomplauncher/recomplauncher.schema.json').read_text())
profile = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else root / 'recomplauncher.json').read_text())
validator = jsonschema.validators.validator_for(schema)
validator.check_schema(schema)
validator(schema).validate(profile)
assert profile['repo'] == 'soltros/fracturerecomp-linux'
assert profile['prepare']['done'] and profile['prepare']['keeps_copy']
assert not profile.get('game', {}).get('dumps'), 'Only add independently verified whole-disc dump metadata'
print('RecompLauncher profile: schema and preparation checks passed')
