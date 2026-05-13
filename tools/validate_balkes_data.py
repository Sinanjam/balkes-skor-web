#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, json
from pathlib import Path

def load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-dir', default='docs/data')
    ap.add_argument('--reports-dir', default='reports/season-sync')
    args = ap.parse_args()
    data_dir = Path(args.data_dir)
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    errors, warnings = [], []
    def must_json(path: Path):
        try:
            return load(path)
        except Exception as exc:
            errors.append(f'JSON parse error: {path}: {exc}')
            return None
    manifest = must_json(data_dir/'manifest.json')
    if not manifest:
        raise SystemExit('manifest.json cannot be parsed')
    for rel in ['data_report.json','players_index.json','opponents_index.json','search_index.json']:
        if not (data_dir/rel).exists(): errors.append(f'Missing root file: {rel}')
        else: must_json(data_dir/rel)
    detail_ids, total_manifest = set(), 0
    for season in manifest.get('availableSeasons', []) or []:
        sid = season.get('id')
        if not sid:
            errors.append('availableSeasons item without id'); continue
        total_manifest += int(season.get('matchCount') or (season.get('summary') or {}).get('matches') or 0)
        sdir = data_dir/'seasons'/sid
        for rel in ['season.json','matches_index.json','standings_by_week.json']:
            path=sdir/rel
            if not path.exists(): errors.append(f'Missing {sid}/{rel}')
            else: must_json(path)
        idx_path=sdir/'matches_index.json'
        idx=must_json(idx_path) if idx_path.exists() else []
        if not isinstance(idx, list):
            errors.append(f'{idx_path} is not a list'); idx=[]
        for m in idx:
            mid=str(m.get('id',''))
            if not mid: errors.append(f'{idx_path}: match without id'); continue
            if mid in detail_ids: errors.append(f'Duplicate match id: {mid}')
            detail_ids.add(mid)
            detail_url=m.get('detailUrl') or f'seasons/{sid}/matches/{mid}.json'
            detail_path=data_dir/detail_url
            if not detail_path.exists(): errors.append(f'Missing detail file: {detail_url}'); continue
            detail=must_json(detail_path)
            if detail and str(detail.get('id')) != mid: errors.append(f'Detail id mismatch: {detail_url}')
    report=must_json(data_dir/'data_report.json') if (data_dir/'data_report.json').exists() else {}
    if isinstance(report, dict) and report.get('totalAppMatches') is not None:
        if int(report.get('totalAppMatches')) != total_manifest:
            errors.append(f'data_report.totalAppMatches={report.get("totalAppMatches")} but manifest total={total_manifest}')
    md=["# Balkes data validation", "", f"- Manifest seasons: `{len(manifest.get('availableSeasons', []) or [])}`", f"- Manifest total matches: `{total_manifest}`", f"- Detail IDs: `{len(detail_ids)}`", f"- Errors: `{len(errors)}`", f"- Warnings: `{len(warnings)}`", ""]
    if errors:
        md.append('## Errors'); md += [f'- {e}' for e in errors]
    if warnings:
        md.append(''); md.append('## Warnings'); md += [f'- {w}' for w in warnings[:100]]
    (reports_dir/'VALIDATION.md').write_text('\n'.join(md)+'\n', encoding='utf-8')
    if errors:
        print('\n'.join(errors)); raise SystemExit(1)
    print('Validation OK')
if __name__ == '__main__': main()
