"""Publish one complete audited window run, without solving or overwriting.

The certificate proves its stated feasibility. Native bounds in the saved run
remain solver reports for the declared candidate pool, not independent proofs.
"""
import argparse
import io
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_window_plan import (read_window_inputs, unchanged_window_inputs,
                                      audit_saved_window_plan, load_json)
from scripts.run_window_plan import formulate
from scripts.run_joint_plan import PLAN_FIELDS, sha, write_new, json_bytes
from scripts.manifest import run as update_manifest


def validated_bundle(run_folder, manifest_path):
    folder = Path(run_folder).resolve(strict=True)
    payloads = {name: (folder/name).read_bytes() for name in
        ('window-plan.json','run-result.json','vectors.npz','solver.log','resource-seed.json','process-status.json')}
    cert = load_json(payloads['window-plan.json']); report = load_json(payloads['run-result.json'])
    if report['candidatePool'] == 'explicit':
        payloads['candidate-pool.json'] = (folder/'candidate-pool.json').read_bytes()
        if sha(payloads['candidate-pool.json']) != report['candidatePoolSHA256']:
            raise ValueError('Expanded candidate pool identity mismatch')
    if report.get('adaptiveSeedPreparationSHA256') is not None:
        seed_folder=folder/'seed-preparation'
        if seed_folder.resolve()!=seed_folder or not seed_folder.is_dir():
            raise ValueError('Adaptive seed folder must not be redirected')
        seed_bytes=(seed_folder/'seed-preparation.json').read_bytes()
        if sha(seed_bytes)!=report['adaptiveSeedPreparationSHA256']:
            raise ValueError('Adaptive seed preparation identity mismatch')
        payloads['seed-preparation/seed-preparation.json']=seed_bytes
        for name,wanted in load_json(seed_bytes)['artifacts'].items():
            if Path(name).name!=name or (seed_folder/name).resolve().parent!=seed_folder:
                raise ValueError('Adaptive seed artifact escaped its folder')
            content=(seed_folder/name).read_bytes()
            if sha(content)!=wanted: raise ValueError('Adaptive seed stage identity mismatch')
            payloads['seed-preparation/'+name]=content
    process = load_json(payloads['process-status.json']); generation = cert['generation']
    if (process['status'] != 'completed' or type(process['returnCode']) is not int
        or process['returnCode'] != 0 or process['certificateFilePresent'] is not True):
        raise ValueError('Only a completed audited worker run can be published')
    if (sha(payloads['run-result.json']) != generation['runReportSHA256']
        or sha(payloads['vectors.npz']) != generation['vectorSHA256']):
        raise ValueError('Run report/vector identity mismatch')
    if sha(payloads['vectors.npz']) != report['vectorSHA256'] or sha(payloads['solver.log']) != report['solverLogSHA256']:
        raise ValueError('Run report does not bind its vector and native log')
    if sha(payloads['resource-seed.json']) != report['resourceSeedSHA256']:
        raise ValueError('Historical seed identity mismatch')
    for key in ('sourceSHA256','modelCodeSHA256','profileManifestSHA256','transitPackageId'):
        if report[key] != cert[key]: raise ValueError('Run/certificate identity differs: '+key)
    for key in ('candidateIndices','optimizedProfiles','validatedProfiles'):
        if report[key] != generation[key]: raise ValueError('Run search scope differs: '+key)
    if report['result'].get('feasible') is not True or {k:report['result'][k] for k in PLAN_FIELDS} != cert['plan']:
        raise ValueError('Final result differs from certified plan')
    inputs = read_window_inputs(manifest_path)
    problem = formulate(inputs, generation['candidateIndices']); final, _ = problem.read_plan(cert['plan'])
    with np.load(io.BytesIO(payloads['vectors.npz']),allow_pickle=False) as vectors:
        if 'finalOriginalVector' not in vectors or not np.array_equal(vectors['finalOriginalVector'],final):
            raise ValueError('Saved original vector differs from full reconstructed certificate')
    summary = audit_saved_window_plan(folder/'window-plan.json',manifest_path)
    unchanged_window_inputs(inputs)
    if any((folder/name).read_bytes()!=blob for name,blob in payloads.items()):
        raise ValueError('Run bundle changed while auditing')
    return payloads, summary, inputs


def publish(run_folder, manifest_path):
    payloads, summary, inputs = validated_bundle(run_folder,manifest_path)
    processed = ROOT/'data/processed'; routing = processed/'departure-window'; plan = processed/'departure-window-plan'
    summary_path = processed/'window-plan-summary.json'
    if processed.resolve()!=processed or any(p.exists() or p.is_symlink() for p in (routing,plan,summary_path)):
        raise ValueError('Publication paths must be new, unredirected processed paths')
    matrix_folder = Path(manifest_path).resolve(strict=True).parent
    names = ['manifest.json','indices.json',*[r['file'] for r in inputs['manifest']['matrices']]]
    # Read a complete snapshot before reserving destinations. The input exit
    # check below prevents producing an accepted release from changing inputs.
    route_payloads = {name:(matrix_folder/name).read_bytes() for name in names}
    routing.mkdir(); plan.mkdir()
    for name,blob in route_payloads.items(): write_new(routing/name,blob)
    for name,blob in payloads.items():
        target=plan/name;target.parent.mkdir(parents=True,exist_ok=True)
        write_new(target,blob)
    published = audit_saved_window_plan(plan/'window-plan.json',routing/'manifest.json')
    if published!=summary: raise ValueError('Published audit differs from source audit')
    unchanged_window_inputs(inputs)
    write_new(summary_path,json_bytes(published))
    update_manifest()
    print('Published',published['hospitalCount'],'sites;',published['profileCount'],'profiles;',
          published['annualEquivalentCostTRY'],'TRY annual equivalent')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True);parser.add_argument('--manifest',required=True)
    options=parser.parse_args();publish(options.run,options.manifest)
