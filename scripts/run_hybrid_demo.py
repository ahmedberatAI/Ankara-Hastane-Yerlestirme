"""Reproduce the new MOTIS/hybrid examples and 91-limit diagnostics locally."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.main import Scenario, cached_solve
from backend import motis
from backend.motis_runtime import runtime_identity
from scripts.verify_hybrid import code_identities
from scripts.build_motis_matrices import atomic_bytes


def save(path, value):
    atomic_bytes(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8'))


def bound(result):
    return {**result, 'builtAt': datetime.now(timezone.utc).isoformat(),
        'modelCodeLF_SHA256': code_identities(),
        'dataSHA256': {'dataset': motis.file_sha(ROOT / 'data/processed/dataset.json'),
                       'planning': motis.file_sha(ROOT / 'data/processed/health-planning.json')}}


def summary(result):
    return {key: result[key] for key in ('status', 'scenario', 'hospitalCount', 'reason',
        'restrictedModelStatus', 'restrictedModelReason', 'routingSearchScope',
        'hybridSummary', 'transitEvidence', 'searchScope', 'solver', 'solverReason',
        'infeasibilityScope', 'modelCodeLF_SHA256', 'dataSHA256', 'builtAt') if key in result} | {
        'capacity': {k: result['capacity'][k] for k in ('totalBeds', 'totalDoctors', 'annualEquivalentCostTRY', 'finalPlanCostGap')}
        if result.get('capacity') else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Explicitly publish recorded examples')
    parser.add_argument('--cases', nargs='+', choices=['default', '91'], default=['default', '91'])
    args = parser.parse_args()
    if not args.write:
        parser.error('Use --write to run and publish the explicitly requested experiments')
    initial = motis.manifest()['packageId']
    if set(motis.manifest()['matrices']) != set(motis.PROFILES):
        raise ValueError('All four dated matrices must be prepared before recording release examples')
    output = ROOT / 'data/processed'
    if 'default' in args.cases:
        for mode, threshold, filename in [('hybrid', 30, 'hybrid-result.json'), ('transit', 45, 'motis-transit-result.json')]:
            scenario = Scenario(mode=mode, threshold=threshold, transitEngine='motis', carWeight=70, transitThreshold=45)
            result = bound(cached_solve(scenario.model_dump_json()))
            if result['status'] != 'feasible':
                raise RuntimeError(f'{mode} has no validated default incumbent: {result.get("reason")}')
            if motis.manifest()['packageId'] != initial:
                raise RuntimeError('MOTIS package changed during examples; rerun after preparation completes')
            save(output / filename, result)
            print(json.dumps({'example': filename, 'status': result['status'],
                'hospitalCount': result['hospitalCount'],
                'beds': result['capacity']['totalBeds'], 'doctors': result['capacity']['totalDoctors'],
                'annualCostTRY': result['capacity']['annualEquivalentCostTRY'],
                'meanMinutes': result['metrics']['meanMinutes'], 'hybridSummary': result.get('hybridSummary')}, ensure_ascii=False), flush=True)
    if '91' in args.cases:
        cases = []
        for profile in motis.PROFILES:
            scenario = Scenario(mode='transit', threshold=45, hospitalLimit=91,
                                transitProfile=profile, transitEngine='motis')
            result = bound(cached_solve(scenario.model_dump_json()))
            cases.append(summary(result))
            print(json.dumps({'91': profile, 'status': result['status'], 'hospitalCount': result.get('hospitalCount'), 'reason': result.get('reason')}, ensure_ascii=False), flush=True)
        scenario = Scenario(mode='hybrid', threshold=30, hospitalLimit=91, transitEngine='motis')
        result = bound(cached_solve(scenario.model_dump_json()))
        cases.append(summary(result))
        if motis.manifest()['packageId'] != initial:
            raise RuntimeError('MOTIS package changed during 91 diagnostics')
        save(output / 'motis-91-results.json', {
            'builtAt': datetime.now(timezone.utc).isoformat(), 'packageId': initial,
            'scope': 'Independent dated scenarios on queried MOTIS /plan edges; not a full-candidate or real-city impossibility certificate. Goals are unchanged.',
            'cases': cases})
        print(json.dumps({'91': 'hybrid', 'status': result['status'], 'hospitalCount': result.get('hospitalCount')}, ensure_ascii=False), flush=True)
    print(json.dumps({'runtimeIdentity': runtime_identity(), 'packageId': initial}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
