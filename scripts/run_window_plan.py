"""Bounded joint cost search across all 44 named departure-window matrices.

Always runs the native worker in a subprocess with an outer hard timeout.
Outputs are exclusive, work-only, and the complete certificate is written last.
The immutable historical four-profile plan is never a fallback for new clocks.
"""
import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
from time import monotonic

import numpy as np
import highspy
from pyproj import Transformer
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.window_model import build_window_problem, ORIGINAL_ANNUAL_BUDGET_TRY
from backend.window_solver import solve_window_cost, complete_fixed_resource_seed
from backend.window_seed import run_seed_search
from scripts.run_joint_plan import PLAN_FIELDS, output_directory, write_new, json_bytes, sha
from scripts.audit_joint_plan import validate_joint_plan, SOURCE_FILES, load_json
from scripts.audit_window_plan import (read_window_inputs, unchanged_window_inputs,
                                       validate_window_plan, code_hashes, validate_explicit_candidate_pool)

INPUT_KEYS = ('data', 'health', 'matrices', 'published_reference', 'source_cost_certificate',
              'current_source_hashes', 'package_id', 'manifest', 'manifest_sha256',
              'current_code_hashes', 'baseline_matrices', 'indices_document')
LOADED_CODES = code_hashes()


def formulate(inputs, candidate_indices):
    data = inputs['data']; ids = sorted(candidate_indices)
    if len(ids) != len(set(ids)) or not ids or any(type(j) is not int or not 0 <= j < len(data['candidates']) for j in ids):
        raise ValueError('Invalid candidate pool')
    sites = [dict(data['candidates'][j], candidateIndex=j) for j in ids]
    transform = Transformer.from_crs(4326, 32636, always_xy=True)
    xy = np.array([transform.transform(c['lon'], c['lat']) for c in sites])
    radii = np.array([c['footprintRadiusMeters'] for c in sites])
    conflicts = [(ids[a], ids[b]) for a, b in sorted(cKDTree(xy).query_pairs(2 * radii.max()))
                 if np.linalg.norm(xy[a] - xy[b]) < radii[a] + radii[b]]
    return build_window_problem({p: m[:, ids] for p, m in inputs['matrices'].items()},
        [d['population'] for d in data['demands']], [d['districtId'] for d in data['demands']],
        data['districts'], data['metadata']['provincePopulation'], sites, inputs['health'],
        inputs['source_cost_certificate']['scenario'], conflicts,
        annual_budget=ORIGINAL_ANNUAL_BUDGET_TRY,
        reference_annual_cost=inputs['source_cost_certificate']['plan']['annualEquivalentCostTRY'])


def controls(seconds, seed_seconds, refine_seconds, hard_seconds, adaptive_seconds=0, stage_seconds=300):
    for value, ceiling in ((seconds, 1800), (seed_seconds, 120), (refine_seconds, 120), (hard_seconds, 2400)):
        if type(value) not in (int, float) or not np.isfinite(value) or not 0 < value <= ceiling:
            raise ValueError('Invalid positive bounded time control')
    if seed_seconds >= seconds or hard_seconds < seconds + refine_seconds + 30:
        raise ValueError('Outer deadline must cover search, refinement and auditing')
    if (type(adaptive_seconds) not in (int,float) or not np.isfinite(adaptive_seconds)
        or not 0 <= adaptive_seconds <= 1200 or type(stage_seconds) not in (int,float)
        or not np.isfinite(stage_seconds) or not 0 < stage_seconds <= 300):
        raise ValueError('Invalid adaptive seed time control')
    if adaptive_seconds and adaptive_seconds + seed_seconds + 60 >= seconds:
        raise ValueError('Reserve time for a real full-window search after seed preparation')


def check_adaptive_seed(preparation, inputs, problem, report_bytes):
    """Independent full-window primal gate, before the final native warm search."""
    source = inputs['source_cost_certificate']
    last = preparation['stages'][-1]
    prefix = f"stage-{last['stage']:02d}-completion-vectors.npz"
    certificate = dict(format=1,artifactType='window-common-resource-plan',
        transitPackageId=inputs['package_id'],planningVersion=source['planningVersion'],scenario=source['scenario'],
        profileManifestSHA256=inputs['manifest_sha256'],sourceSHA256=inputs['current_source_hashes'],
        modelCodeSHA256=inputs['current_code_hashes'],
        budget=dict(limitTRY=ORIGINAL_ANNUAL_BUDGET_TRY,referenceAnnualCostTRY=source['plan']['annualEquivalentCostTRY'],hardConstraint=True),
        generation=dict(method='Seed preparation only; subset cost search plus complete 44-profile assignments',
            runReportSHA256=sha(report_bytes),vectorSHA256=preparation['artifacts'][prefix],candidateIndices=problem.ids,
            optimizedProfiles=last['optimizedProfileIds'],validatedProfiles=list(inputs['matrices']),
            searchProvenOptimal=False,minimumHospitalCountProven=False,annualDemandCountedOnce=True,
            sameIndividualsAcrossProfilesConstrained=False),
        plan={key:preparation['completeSeedPlan'][key] for key in PLAN_FIELDS})
    return validate_window_plan(certificate,**{key:inputs[key] for key in INPUT_KEYS})


def worker(args):
    started = monotonic(); requested = Path(args.out).absolute(); folder = requested.resolve(strict=True)
    work = ROOT/'work'
    if work.resolve() != work or folder != requested or folder == work or not folder.is_relative_to(work) or not folder.is_dir():
        raise ValueError('Worker output must be an unredirected directory inside repository work/')
    inputs = read_window_inputs(args.manifest)
    if inputs['current_code_hashes'] != LOADED_CODES or code_hashes() != LOADED_CODES:
        raise ValueError('Code changed after import')
    seed_path = Path(args.resource_seed).resolve(strict=True)
    seed_bytes = seed_path.read_bytes(); source = load_json(seed_bytes)
    validate_joint_plan(source, inputs['data'], inputs['health'], inputs['baseline_matrices'],
        inputs['published_reference'], {k: inputs['current_source_hashes'][k] for k in SOURCE_FILES}, inputs['package_id'])
    seed_indices = sorted(s['candidateIndex'] for s in source['plan']['selected'])
    pool_bytes = None; pool_path = None
    if args.pool == 'explicit':
        if not args.pool_file: raise ValueError('Explicit pool requires --pool-file')
        pool_path = Path(args.pool_file).resolve(strict=True); pool_bytes = pool_path.read_bytes()
        pool_document = load_json(pool_bytes)
        validate_explicit_candidate_pool(pool_document, inputs, seed_indices)
        pool = pool_document['candidateIndices']
    else:
        if getattr(args, 'pool_file', None): raise ValueError('--pool-file requires --pool explicit')
        pool = list(range(len(inputs['data']['candidates']))) if args.pool == 'all' else seed_indices
    search_started = monotonic(); deadline = search_started + args.seconds
    problem = formulate(inputs, pool)
    remaining = deadline - monotonic()
    if remaining <= 0: raise TimeoutError('Window deadline exhausted during model formulation; no seed LP started')
    seed, seed_report = complete_fixed_resource_seed(problem, source['plan'],
        min(args.seed_seconds, remaining), 15)
    adaptive_payloads = {}; adaptive_hash = None
    adaptive_seconds = getattr(args,'adaptive_seed_seconds',0)
    if seed is None and adaptive_seconds:
        remaining = deadline - monotonic() - 60
        if remaining <= 0: raise TimeoutError('No time reserved for adaptive seed and full-window native search')
        bindings = dict(sourceSHA256=inputs['current_source_hashes'],modelCodeSHA256=LOADED_CODES,
            profileManifestSHA256=inputs['manifest_sha256'],resourceSeedSHA256=sha(seed_bytes),
            candidatePoolSHA256=sha(pool_bytes) if pool_bytes is not None else None)
        def gate():
            unchanged_window_inputs(inputs)
            if code_hashes()!=LOADED_CODES or seed_path.read_bytes()!=seed_bytes:
                raise ValueError('Adaptive preparation source/code changed')
            if pool_path is not None and pool_path.read_bytes()!=pool_bytes:
                raise ValueError('Adaptive preparation candidate pool changed')
        def subset(names):
            return formulate(dict(inputs,matrices={name:inputs['matrices'][name] for name in names}),pool)
        preparation = run_seed_search(problem,subset,source['plan'],
            overall_seconds=min(adaptive_seconds,remaining),stage_seconds=getattr(args,'seed_stage_seconds',300),
            completion_seconds=60,profile_seconds=15,max_stages=4,out=folder/'seed-preparation',
            bindings=bindings,binding_gate=gate)
        prep_path = folder/'seed-preparation'/'seed-preparation.json'; prep_bytes = prep_path.read_bytes()
        if load_json(prep_bytes)!=preparation: raise ValueError('Saved adaptive preparation differs')
        adaptive_hash = sha(prep_bytes); adaptive_payloads['seed-preparation.json']=prep_bytes
        for name,wanted in preparation['artifacts'].items():
            if Path(name).name!=name: raise ValueError('Invalid adaptive artifact path')
            content=(prep_path.parent/name).read_bytes()
            if sha(content)!=wanted: raise ValueError('Adaptive stage artifact differs')
            adaptive_payloads[name]=content
        if preparation.get('feasible') is True:
            check_adaptive_seed(preparation,inputs,problem,prep_bytes)
            seed=preparation['completeSeedPlan']
            print('Adaptive seed independently passed all 44 profiles and strict annual budget',flush=True)
    remaining = deadline - monotonic()
    if remaining <= 0: raise TimeoutError('Window search deadline exhausted before cost search')
    print('Window model ready:', problem.dimensions, 'seed:', seed_report['status'], flush=True)
    vectors = {}
    if adaptive_hash is not None and seed is None:
        result=dict(status='inconclusive_without_validated_incumbent',feasible=None,
            reason='Adaptive preparation did not yield a complete checked seed; final 44-profile native search skipped',
            selected=None,profiles=None,annualEquivalentCostTRY=None,minimumAnnualCostLowerBoundTRY=None,costGap=None,
            nativeRunStarted=False,nativeReportedInfeasible=False,modelInfeasibilityIndependentlyCertified=False,
            minimumHospitalCountProven=False,provenOptimal=False,warmStart={})
    else:
        result = solve_window_cost(problem, seed, remaining, capture_vectors=vectors)
        if adaptive_hash is not None and result.get('nativeRunStarted') is not True:
            raise ValueError('Prepared seed cannot be relabelled as a performed 44-profile native optimization')
    result.pop('secondTravelStageImplemented', None)
    result['costStageProfileReassignmentPerformed'] = result.pop('profileReassignmentPerformed', None)
    search_elapsed = monotonic() - search_started
    native_log = result.get('warmStart', {}).pop('solverLog', '')
    result['travelRefinement'] = {'status': 'not_run_without_validated_cost_plan'}
    if result.get('feasible') is True:
        cost_plan = {key: result[key] for key in PLAN_FIELDS}
        cost_vector, _ = problem.read_plan(cost_plan)
        vectors['costStageOriginalVector'] = cost_vector
        if 'finalOriginalVector' in vectors:
            vectors['costStageNativeValidatedVector'] = vectors['finalOriginalVector'].copy()
        vectors['finalOriginalVector'] = cost_vector.copy()
        try:
            refined, travel = complete_fixed_resource_seed(problem, cost_plan, args.refine_seconds, 15)
        except (ValueError, RuntimeError, TimeoutError) as exc:
            refined, travel = None, dict(status='refinement_rejected', reason=str(exc))
        result['travelRefinement'] = travel
        if refined is not None:
            try:
                previous = {p['profile']: p['meanMinutes'] for p in cost_plan['profiles']}
                if any(p['meanMinutes'] > previous[p['profile']] + 1e-7 for p in refined['profiles']):
                    raise ValueError('Fixed-resource travel refinement worsened a profile')
                final_vector, _ = problem.read_plan(refined)
                if not np.array_equal(final_vector[:problem.nf], cost_vector[:problem.nf]):
                    raise ValueError('Travel refinement changed resource decisions')
            except ValueError as exc:
                refined = None
                travel.update(status='refinement_rejected', reason=str(exc))
            else:
                result.update({key: refined[key] for key in PLAN_FIELDS})
                vectors['finalOriginalVector'] = final_vector
                travel.update(sourceMeanMinutes=previous, globalTravelOptimumProven=False,
                              resourcesUnchanged=True, independentlyCertifiedOptimality=False)
        travel['costStageAssignmentsRetained'] = refined is None
        result['travelRefinementPerformed'] = refined is not None
        result['travelRefinementChangedAssignments'] = not np.array_equal(
            vectors['finalOriginalVector'][problem.nf:], cost_vector[problem.nf:])
        vector, residuals = problem.read_plan(result)
        if not np.array_equal(vector, vectors['finalOriginalVector']):
            raise ValueError('Final JSON does not reconstruct exact vector')
    else: residuals = None
    archive = io.BytesIO(); np.savez_compressed(archive, **vectors); vector_bytes = archive.getvalue()
    log_bytes = native_log.encode('utf8')
    profiles = list(inputs['matrices'])
    report = dict(format=1, artifactType='departure-window-cost-run', builtAt=datetime.now(timezone.utc).isoformat(),
        transitPackageId=inputs['package_id'], profileManifestSHA256=inputs['manifest_sha256'],
        sourceSHA256=inputs['current_source_hashes'], modelCodeSHA256=LOADED_CODES,
        resourceSeedSHA256=sha(seed_bytes), seedResourceAudit='frozen_four_profile_independent_auditor',
        resourceSeed=seed_report, candidatePool=args.pool, candidateIndices=problem.ids,
        adaptiveSeedPreparationSHA256=adaptive_hash,
        candidatePoolSHA256=sha(pool_bytes) if pool_bytes is not None else None,
        fullCandidateCount=len(inputs['data']['candidates']),
        optimizedProfiles=[] if adaptive_hash is not None and seed is None else profiles,
        validatedProfiles=profiles if result.get('feasible') is True else [],
        boundScope='Only this candidate pool and these 44 named matrices; no global or minimum-count proof',
        controls=dict(searchSeconds=args.seconds, seedCompletionWithinSearchSeconds=args.seed_seconds,
            adaptiveSeedWithinSearchSeconds=adaptive_seconds,seedStageSeconds=getattr(args,'seed_stage_seconds',300),
            finalTravelRefinementSeconds=args.refine_seconds, outerHardSeconds=args.hard_seconds),
        searchElapsedSeconds=search_elapsed, cooperativeSearchOverrunSeconds=max(0.,search_elapsed-args.seconds),
        result=result, finalResiduals=residuals, dimensions=problem.dimensions,
        vectorSHA256=sha(vector_bytes), solverLogSHA256=sha(log_bytes),
        versions=dict(python=platform.python_version(), numpy=np.__version__, highs=highspy.Highs().version()),
        scope='Sampled minute grid only. Same resources and annual demand counted once; clinical, service and full public cost calibration remain open.')
    report_bytes = json_bytes(report)
    certificate = None; audit = None
    if result.get('feasible') is True:
        certificate = dict(format=1, artifactType='window-common-resource-plan',
            transitPackageId=inputs['package_id'], planningVersion=source['planningVersion'], scenario=source['scenario'],
            profileManifestSHA256=inputs['manifest_sha256'], sourceSHA256=inputs['current_source_hashes'], modelCodeSHA256=LOADED_CODES,
            budget=dict(limitTRY=ORIGINAL_ANNUAL_BUDGET_TRY,
                referenceAnnualCostTRY=inputs['source_cost_certificate']['plan']['annualEquivalentCostTRY'], hardConstraint=True),
            generation=dict(method='Bounded common-resource location/template/physician cost MIP plus optional fixed-resource travel assignment',
                runReportSHA256=sha(report_bytes), vectorSHA256=sha(vector_bytes), candidateIndices=problem.ids,
                optimizedProfiles=profiles, validatedProfiles=profiles, searchProvenOptimal=False, minimumHospitalCountProven=False,
                annualDemandCountedOnce=True, sameIndividualsAcrossProfilesConstrained=False),
            plan={key: result[key] for key in PLAN_FIELDS})
        audit = validate_window_plan(certificate, **{key: inputs[key] for key in INPUT_KEYS})
    unchanged_window_inputs(inputs)
    if seed_path.read_bytes() != seed_bytes or code_hashes() != LOADED_CODES:
        raise ValueError('Resource seed or loaded code changed during search')
    if pool_path is not None and pool_path.read_bytes() != pool_bytes:
        raise ValueError('Explicit candidate pool changed during search')
    for name,content in adaptive_payloads.items():
        if (folder/'seed-preparation'/name).read_bytes()!=content:
            raise ValueError('Adaptive seed artifact changed during final search')
    if pool_bytes is not None: write_new(folder/'candidate-pool.json',pool_bytes)
    write_new(folder/'resource-seed.json', seed_bytes)
    write_new(folder/'vectors.npz', vector_bytes); write_new(folder/'solver.log', log_bytes)
    write_new(folder/'run-result.json', report_bytes)
    if certificate is not None:
        write_new(folder/'audit.json', json_bytes(audit))
        write_new(folder/'window-plan.json', json_bytes(certificate))
    print('Completed', 'audited feasible plan' if certificate else 'without validated incumbent',
          'elapsed', monotonic()-started, flush=True)


def run(args):
    controls(args.seconds,args.seed_seconds,args.refine_seconds,args.hard_seconds,
        getattr(args,'adaptive_seed_seconds',0),getattr(args,'seed_stage_seconds',300))
    folder = output_directory(ROOT,args.out); folder.mkdir(parents=True,exist_ok=False)
    command = [sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--worker',
        '--manifest',str(Path(args.manifest).resolve(strict=True)), '--resource-seed',str(Path(args.resource_seed).resolve(strict=True)),
        '--out',str(folder),'--pool',args.pool,'--seconds',str(args.seconds),
        '--seed-seconds',str(args.seed_seconds),'--refine-seconds',str(args.refine_seconds),'--hard-seconds',str(args.hard_seconds)]
    if getattr(args,'pool_file',None): command.extend(['--pool-file',str(Path(args.pool_file).resolve(strict=True))])
    command.extend(['--adaptive-seed-seconds',str(getattr(args,'adaptive_seed_seconds',0)),
                    '--seed-stage-seconds',str(getattr(args,'seed_stage_seconds',300))])
    began=monotonic()
    with (folder/'worker.log').open('xb') as log:
        try:
            result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=args.hard_seconds,check=False)
            status=dict(status='completed' if result.returncode==0 else 'worker_failed',returnCode=result.returncode)
        except subprocess.TimeoutExpired:
            status=dict(status='hard_timeout',returnCode=None)
    status.update(elapsedSeconds=monotonic()-began,hardTimeoutSeconds=args.hard_seconds,
        certificateFilePresent=(folder/'window-plan.json').is_file())
    write_new(folder/'process-status.json',json_bytes(status));print(json.dumps(status),flush=True)
    if status['status']!='completed':raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True);parser.add_argument('--resource-seed',required=True)
    parser.add_argument('--out',required=True);parser.add_argument('--pool',choices=('seed','all','explicit'),default='seed')
    parser.add_argument('--pool-file',help='Explicit source-bound expanded candidate-pool JSON')
    parser.add_argument('--seconds',type=float,default=300);parser.add_argument('--seed-seconds',type=float,default=90)
    parser.add_argument('--refine-seconds',type=float,default=120);parser.add_argument('--hard-seconds',type=float,default=600)
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--adaptive-seed-seconds',type=float,default=0,help='Optional smaller-profile seed search within total search time')
    parser.add_argument('--seed-stage-seconds',type=float,default=300)
    arguments=parser.parse_args();controls(arguments.seconds,arguments.seed_seconds,arguments.refine_seconds,arguments.hard_seconds,
        arguments.adaptive_seed_seconds,arguments.seed_stage_seconds)
    worker(arguments) if arguments.worker else run(arguments)
