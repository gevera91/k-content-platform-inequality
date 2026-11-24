#!/usr/bin/env python3
"""Verify the frozen release's SHA-256 file manifest (standard library only)."""
import argparse
import csv
import hashlib
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=ROOT/'publication/SHA256SUMS.csv')
    args=parser.parse_args()
    failed=[]; count=0
    with args.manifest.open(encoding='utf-8',newline='') as handle:
        for row in csv.DictReader(handle):
            relative=Path(row['path'])
            path=(ROOT/relative).resolve()
            if relative.is_absolute() or not path.is_relative_to(ROOT):
                failed.append(f'Unsafe manifest entry: {relative}');continue
            count+=1
            if not path.is_file():
                failed.append(f'Missing: {relative}');continue
            if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
                failed.append(f'Changed: {relative}')
    if failed:
        print('\n'.join(failed));sys.exit(1)
    print(f'PASS: {count} released files match the SHA-256 manifest.')

if __name__=='__main__':main()

