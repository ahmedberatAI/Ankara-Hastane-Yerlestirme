"""Real tiny CLI runs and source/output/claim boundary regressions."""
from copy import deepcopy
from pathlib import Path
import json
import os
import subprocess
import numpy as np
import pytest
from scripts import run_joint_plan as r
from test_joint_plan_audit import tiny


@pytest.fixture
def files(tmp_path, monkeypatch, tiny):
    cert, data, health, matrices, published, hashes = tiny
    directory = tmp_path / 'data/processed'; directory.mkdir(parents=True)
    values = {'dataset.json': data, 'health-planning.json': health,
              'example-transit-result.json': published, 'transit-package.json': {'transitPackageId': 'p'}}
    for name, value in values.items(): (directory / name).write_bytes(r.json_bytes(value))
    for p, m in matrices.items(): np.savez_compressed(directory / f'transit-{p}-matrix.npz', minutes=m)
    cert['sourceSHA256'] = {name: r.sha((directory / name).read_bytes()) for name in r.SOURCE_FILES}
    (directory / 'joint-plan.json').write_bytes(r.json_bytes(cert))
    monkeypatch.setattr(r, 'check_package', lambda root: 'p')
    return tmp_path, directory, cert


@pytest.mark.parametrize('strategy,pool', [('close', 'selected'), ('cost', 'selected'), ('cost', 'all')])
def test_complete_tiny_source_to_independent_certificate(files, strategy, pool):
    root, directory, source = files; before = (directory / 'joint-plan.json').read_bytes()
    report, certificate, audit = r.run(root=root, out='work/result', strategy=strategy, pool=pool, seconds=5)
    folder = root / 'work/result'
    assert (directory / 'joint-plan.json').read_bytes() == before
    assert audit['withinOriginalTransitBudget'] and audit['hospitalCount'] == 1
    assert all(p['coveragePercent'] == pytest.approx(95) for p in audit['profiles'])
    assert report['budgetIsConstraint'] is False and report['newBudgetProduced'] is False
    assert all(certificate['generation'][f] is False for f in ('searchProvenOptimal', 'minimumHospitalCountProven', 'travelTimeOptimized'))
    assert certificate['generation']['researchReportSHA256'] == r.sha((folder / 'run-result.json').read_bytes())
    assert certificate['generation']['researchVectorSHA256'] == r.sha((folder / 'vectors.npz').read_bytes())
    assert report['candidateIndices'] == ([0] if pool == 'selected' else [0, 1, 2])
    if strategy == 'cost':
        assert report['result']['warmStart']['solverAcceptedFeasibleStart']
        assert report['result']['boundCandidateIndices'] == report['candidateIndices']
        assert report['result']['boundScope'] == 'supplied_candidate_pool_all_profile_edges'
        assert report['solverLogSHA256'] == r.sha((folder / 'solver.log').read_bytes())
    with np.load(folder / 'vectors.npz') as archive:
        assert np.all(np.isfinite(archive['finalOriginalVector']))
    # Continuation consumes a complete certificate; no ignored research needed.
    _, next_cert, _ = r.run(root=root, seed=folder / 'joint-plan.json', out='work/next', strategy='close', seconds=5)
    assert next_cert['plan']['annualEquivalentCostTRY'] <= certificate['plan']['annualEquivalentCostTRY']


@pytest.mark.parametrize('out', [None, 'data/processed/new', 'work', '../escape'])
def test_new_work_directory_required(files, out):
    root, _, _ = files
    with pytest.raises(ValueError): r.run(root=root, out=out)


def test_no_overwrite_existing_directory(files):
    root, _, _ = files; folder = root / 'work/existing'; folder.mkdir(parents=True)
    (folder / 'sentinel').write_text('preserve')
    with pytest.raises(ValueError): r.run(root=root, out=folder)
    assert (folder / 'sentinel').read_text() == 'preserve'


@pytest.mark.parametrize('nested',[False,True])
def test_work_root_or_nested_directory_cannot_redirect_to_production(files,nested):
    root,directory,_=files
    link=root/'work'
    if nested:link.mkdir();link=link/'redirect'
    try:os.symlink(directory,link,target_is_directory=True)
    except OSError:
        if os.name!='nt':raise
        made=subprocess.run(['cmd','/c','mklink','/J',str(link),str(directory)],capture_output=True,text=True)
        if made.returncode:pytest.skip('Neither directory symlink nor junction creation is available')
    with pytest.raises(ValueError):r.output_directory(root,link/'new-run')
    assert not (directory/'new-run').exists()


@pytest.mark.parametrize('change', ['source', 'seed', 'code', 'package'])
def test_exit_identity_change_blocks_final_certificate(files, monkeypatch, change):
    root, directory, _ = files
    def changed(problem, seed, *args):
        result = problem.serialize(problem.read_plan(seed)[0])
        if change == 'source':
            with (directory / 'health-planning.json').open('ab') as stream: stream.write(b' ')
        elif change == 'seed':
            with (directory / 'joint-plan.json').open('ab') as stream: stream.write(b' ')
        elif change == 'code': monkeypatch.setattr(r, 'code_hashes', lambda: {})
        else: monkeypatch.setattr(r, 'check_package', lambda root: 'changed')
        return result
    monkeypatch.setattr(r, 'batch_close', changed)
    with pytest.raises(ValueError, match='changed'): r.run(root=root, out='work/changed')
    assert not (root / 'work/changed/joint-plan.json').exists()


def test_stale_source_rejected_before_solver_or_output(files, monkeypatch):
    root, directory, cert = files
    cert['sourceSHA256']['dataset.json'] = '0' * 64
    (directory / 'joint-plan.json').write_bytes(r.json_bytes(cert))
    monkeypatch.setattr(r, 'batch_close', lambda *a: pytest.fail('Must not solve stale source'))
    with pytest.raises(ValueError, match='Stale source'): r.run(root=root, out='work/stale')
    assert not (root / 'work/stale').exists()


def test_total_deadline_includes_preflight_and_build(files, monkeypatch):
    root, _, _ = files; now = [0.]; real = r.formulate
    def slow(*args):
        p = real(*args); now[0] = 301.; return p
    monkeypatch.setattr(r, 'monotonic', lambda: now[0])
    monkeypatch.setattr(r, 'formulate', slow)
    monkeypatch.setattr(r, 'solve_cost', lambda *a, **k: pytest.fail('Native work after deadline'))
    report, certificate, audit = r.run(root=root, out='work/expired', strategy='cost', seconds=300)
    assert report['result']['searchSkipped'] and not report['result']['costStagePerformed']
    assert report['result']['profileReassignmentPerformed'] is False
    assert 'no native search started' in certificate['generation']['method']
    assert certificate['plan']['hospitalCount'] == 1 and audit['witnessFound']


def test_independent_postgate_prevents_invalid_output(files, monkeypatch):
    root, _, _ = files; real = r.validate_joint_plan; calls = [0]
    def reject_second(*args):
        calls[0] += 1
        if calls[0] == 2: raise ValueError('Independent final resource mismatch')
        return real(*args)
    monkeypatch.setattr(r, 'validate_joint_plan', reject_second)
    with pytest.raises(ValueError, match='Independent final'): r.run(root=root, out='work/rejected')
    assert not (root / 'work/rejected/joint-plan.json').exists()


@pytest.mark.parametrize('kwargs', [{'seconds':301}, {'seconds':float('nan')}, {'trial_seconds':16},
    {'max_trials':1001}, {'max_trials':True}, {'batch_size':17}, {'pool':'unknown'}, {'strategy':'unknown'}])
def test_cli_control_caps(files, kwargs):
    root, _, _ = files
    with pytest.raises(ValueError): r.run(root=root, out='work/invalid', **kwargs)
