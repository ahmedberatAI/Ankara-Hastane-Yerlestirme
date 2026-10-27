"""Explicit offline build; map-view changes never invoke optimization."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.permanent_service import build_plan
from backend.permanent_evidence import PLAN_FILE
from scripts.build_motis_matrices import atomic_bytes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--seconds', type=float, default=180)
    args = parser.parse_args()
    if not args.write:
        parser.error('Use --write to prepare and publish the fixed-policy plan')
    result = build_plan(time_limit=args.seconds)
    if result['status'] != 'feasible':
        diagnostic = ROOT / 'work/permanent-plan-inconclusive.json'
        atomic_bytes(diagnostic, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8'))
        raise SystemExit('No validated permanent plan; diagnostic saved, no plan published')
    atomic_bytes(PLAN_FILE, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8'))
    print(json.dumps({'planId': result['planId'], 'hospitalCount': result['hospitalCount'],
        'beds': result['capacity']['totalBeds'], 'doctors': result['capacity']['totalDoctors'],
        'annualCostTRY': result['capacity']['annualEquivalentCostTRY'],
        'criticalTransitProfile': result['criticalTransitProfile'],
        'summary': result['permanentSummary'], 'audit': result['auditSummary']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
