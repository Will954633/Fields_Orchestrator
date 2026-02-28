#!/usr/bin/env python3
"""
generate_schema_snapshot.py
Samples all Azure Cosmos DB (MongoDB API) collections and writes a
comprehensive SCHEMA_SNAPSHOT.md that Claude Code reads at session start.
Run daily via cron.
"""

import os
import sys
from datetime import datetime, timezone
from collections import defaultdict
from pymongo import MongoClient

CONN = os.environ.get('COSMOS_CONNECTION_STRING')
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'SCHEMA_SNAPSHOT.md')
SAMPLE_SIZE = 5

TARGET_DBS = [
    'Gold_Coast_Currently_For_Sale',
    'Gold_Coast_Recently_Sold',
    'Gold_Coast',
    'Target_Market_Sold_Last_12_Months',
    'property_data',
    'system_monitor',
]

def infer_type(value):
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'bool'
    if isinstance(value, int):
        return 'int'
    if isinstance(value, float):
        return 'float'
    if isinstance(value, list):
        if value:
            return f'array[{infer_type(value[0])}]'
        return 'array[]'
    if isinstance(value, dict):
        return 'object'
    return type(value).__name__

def get_schema(collection, sample_size=SAMPLE_SIZE):
    docs = list(collection.find({}, {'_id': 0}).limit(sample_size))
    if not docs:
        return {}, {}, {}
    field_types = defaultdict(set)
    for doc in docs:
        for key, val in doc.items():
            field_types[key].add(infer_type(val))
    nested = {}
    for doc in docs:
        for key, val in doc.items():
            if isinstance(val, dict) and key not in nested:
                nested[key] = list(val.keys())[:10]
    return dict(field_types), nested, docs[0]

def format_example(doc, max_fields=8):
    lines = []
    for i, (k, v) in enumerate(doc.items()):
        if i >= max_fields:
            lines.append(f'  ... (+{len(doc) - max_fields} more fields)')
            break
        if isinstance(v, str) and len(v) > 80:
            v = v[:80] + '...'
        if isinstance(v, list) and len(v) > 3:
            v = v[:3] + [f'...({len(v)} total)']
        lines.append(f'  {k}: {repr(v)}')
    return '\n'.join(lines)

def main():
    if not CONN:
        print("ERROR: COSMOS_CONNECTION_STRING not set", file=sys.stderr)
        sys.exit(1)
    client = MongoClient(CONN, serverSelectionTimeoutMS=10000)
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    lines = [
        '# Database Schema Snapshot',
        '',
        f'**Generated:** {now}  ',
        f'**Source:** Azure Cosmos DB (MongoDB API)  ',
        '**Script:** `generate_schema_snapshot.py` (runs daily via cron)',
        '',
        '> Claude: Read this file before writing ANY MongoDB query. Use exact field names',
        '> shown here. If a field is not listed, sample the collection first.',
        '',
        '---',
        '',
    ]
    for db_name in TARGET_DBS:
        db = client[db_name]
        try:
            all_cols = db.list_collection_names()
        except Exception as e:
            lines.append(f'## {db_name}\n\n_Error listing collections: {e}_\n\n---\n')
            continue
        if not all_cols:
            continue
        lines.append(f'## Database: `{db_name}`\n')
        suburb_keywords = ['burleigh','robina','varsity','coolangatta','carrara','merrimac','mudgeeraba','reedy','worongary','palm_beach','miami','mermaid']
        utility_cols = [c for c in all_cols if not any(s in c for s in suburb_keywords)]
        suburb_cols = [c for c in all_cols if c not in utility_cols]
        for col_name in sorted(utility_cols) + sorted(suburb_cols):
            col = db[col_name]
            try:
                count = col.estimated_document_count()
            except:
                count = '?'
            lines.append(f'### `{col_name}` ({count} documents)\n')
            if count == 0 or count == '?':
                lines.append('_Empty collection._\n')
                continue
            try:
                field_types, nested, example_doc = get_schema(col)
            except Exception as e:
                lines.append(f'_Error sampling: {e}_\n')
                continue
            if not field_types:
                lines.append('_No documents sampled._\n')
                continue
            lines.append('**Fields:**\n')
            lines.append('| Field | Type(s) |')
            lines.append('|-------|---------|')
            for field, types in sorted(field_types.items()):
                type_str = ' / '.join(sorted(types))
                sub = ''
                if field in nested:
                    sub = f' → `{", ".join(nested[field])}`'
                lines.append(f'| `{field}` | {type_str}{sub} |')
            lines.append('')
            lines.append('<details><summary>Example document</summary>\n')
            lines.append('```')
            lines.append(format_example(example_doc))
            lines.append('```')
            lines.append('</details>\n')
        lines.append('---\n')
    with open(OUTPUT, 'w') as f:
        f.write('\n'.join(lines))
    print(f"Schema snapshot written to {OUTPUT}")
    print(f"Total databases documented: {len(TARGET_DBS)}")

if __name__ == '__main__':
    main()
