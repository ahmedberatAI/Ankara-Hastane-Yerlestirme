"""Portable current-source travel CLI: real tiny LPs, immutable IO and identities."""
from copy import deepcopy
import os
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest
from test_run_joint_plan import files
from test_joint_plan_audit import tiny
from scripts import run_joint_plan as base
from scripts import run_joint_travel as r
from backend import joint_travel as travel


def test_complete_tiny_portable_json_without_any_research_files(files):
    root,directory,source=files;before=(directory/'joint-plan.json').read_bytes()
    artifact,proof,audit=r.run(root=root,out='work/travel',seconds=5,profile_seconds=2)
    folder=root/'work/travel'
    assert (directory/'joint-plan.json').read_bytes()==before
    assert set(p.name for p in folder.iterdir())=={'travel-plan.json','travel-proof.json','travel-audit.json'}
    assert artifact['plan']['hospitalCount']==source['plan']['hospitalCount']
    assert artifact['plan']['annualEquivalentCostTRY']==source['plan']['annualEquivalentCostTRY']
    assert r.resource_signature(artifact['plan'])==r.resource_signature(source['plan'])
    assert proof['travelPlanSHA256']==base.sha((folder/'travel-plan.json').read_bytes())
    assert artifact['sourceCostCertificateSHA256']==base.sha(before)
    assert len(artifact['modelCodeSHA256'])==9
    assert proof['executionOrigin']=={'kind':'native_run','sourceReportSHA256':None,'sourceVectorsSHA256':None}
    assert all(p['certificateAccepted'] and p['inequalityDual'] is not None for p in proof['profiles'])
    assert artifact['generation']['jointTravelOptimumProven'] is False
    assert artifact['generation']['extraBudgetTRY']==0
    assert audit['decimalAnnualEquivalentCostTRY']


def test_mixed_unknown_profile_keeps_full_exact_source_json(files,monkeypatch):
    root,directory,source=files;native=travel._solve;calls=[0]
    def mixed(*args):
        calls[0]+=1
        return SimpleNamespace(status=1,x=None) if calls[0]==1 else native(*args)
    monkeypatch.setattr(travel,'_solve',mixed)
    artifact,proof,audit=r.run(root=root,out='work/mixed',seconds=5,profile_seconds=2)
    assert artifact['plan']['profiles'][0]==source['plan']['profiles'][0]
    assert [p['certificateAccepted'] for p in proof['profiles']]==[False,True,True,True]
    fallback=proof['profiles'][0]
    for key in ('inequalityDual','equalityDual','exactLowerBoundNumerator','exactLowerBoundDenominator',
                'lowerBoundMeanMinutes','signedGapMinutes','gapToleranceMinutes'):
        assert fallback[key] is None
    assert fallback['status']=='source_preserved' and fallback['solverReportedOptimal'] is False
    assert not audit['allProfilesAccepted']


def test_preflight_deadline_starts_no_solver_and_preserves_all_source_json(files,monkeypatch):
    root,directory,source=files;now=[0.];read=r.validate_source
    def slow(*args):
        value=read(*args);now[0]=61.;return value
    monkeypatch.setattr(r,'validate_source',slow);monkeypatch.setattr(r,'monotonic',lambda:now[0])
    monkeypatch.setattr(r,'improve_travel',lambda *a,**k:pytest.fail('No LP after preflight deadline'))
    artifact,proof,audit=r.run(root=root,out='work/expired')
    assert artifact['plan']==source['plan']
    assert not artifact['generation']['fixedResourceTravelStagePerformed']
    assert all(p['status']=='source_preserved' for p in proof['profiles'])


@pytest.mark.parametrize('change',['input','seed','cost_code','travel_code','package'])
def test_exit_mutation_blocks_complete_travel_artifact(files,monkeypatch,change):
    root,directory,source=files;real=r.improve_travel
    def changed(*args,**kwargs):
        result=real(*args,**kwargs)
        if change in ('input','seed'):
            name='health-planning.json' if change=='input' else 'joint-plan.json'
            with (directory/name).open('ab') as stream:stream.write(b' ')
        elif change=='cost_code':monkeypatch.setattr(base,'code_hashes',lambda:{})
        elif change=='travel_code':monkeypatch.setattr(r,'code_hashes',lambda:{})
        else:monkeypatch.setattr(base,'check_package',lambda root:'changed')
        return result
    monkeypatch.setattr(r,'improve_travel',changed)
    with pytest.raises(ValueError):r.run(root=root,out='work/reject',seconds=5,profile_seconds=2)
    assert not (root/'work/reject/travel-plan.json').exists()


@pytest.mark.parametrize('out',[None,'work','data/processed/new','../escape'])
def test_output_must_be_new_work_directory(files,out):
    root,_,_=files
    with pytest.raises(ValueError):r.run(root=root,out=out)


def test_no_overwrite_existing_work_output(files):
    root,_,_=files;folder=root/'work/existing';folder.mkdir(parents=True)
    (folder/'sentinel').write_text('preserve')
    with pytest.raises(ValueError):r.run(root=root,out=folder)
    assert (folder/'sentinel').read_text()=='preserve'


@pytest.mark.parametrize('nested',[False,True])
def test_work_junction_cannot_redirect_output_to_production(files,nested):
    root,directory,_=files;link=root/'work'
    if nested:link.mkdir();link=link/'redirect'
    try:os.symlink(directory,link,target_is_directory=True)
    except OSError:
        if os.name!='nt':raise
        made=subprocess.run(['cmd','/c','mklink','/J',str(link),str(directory)],capture_output=True,text=True)
        if made.returncode:pytest.skip('No symlink/junction permission')
    with pytest.raises(ValueError):r.run(root=root,out=link/'new')
    assert not (directory/'new').exists()


@pytest.mark.parametrize('kwargs',[{'seconds':61},{'seconds':True},{'seconds':float('nan')},
    {'seconds':0},{'profile_seconds':16},{'profile_seconds':float('inf')}])
def test_controls_reject_invalid_limits_before_solver(files,kwargs):
    root,_,_=files
    with pytest.raises(ValueError):r.run(root=root,out='work/invalid',**kwargs)


@pytest.mark.parametrize('field',['profile','sourceSHA256','generation'])
def test_stale_or_invalid_source_rejected_without_output(files,monkeypatch,field):
    root,directory,source=files;source=deepcopy(source)
    if field=='profile':source['plan']['profiles'][0]['profile']='wrong'
    elif field=='sourceSHA256':source['sourceSHA256']['dataset.json']='0'*64
    else:source['generation']['searchProvenOptimal']=True
    (directory/'joint-plan.json').write_bytes(base.json_bytes(source))
    monkeypatch.setattr(r,'improve_travel',lambda *a,**k:pytest.fail('No solve on invalid source'))
    with pytest.raises(ValueError):r.run(root=root,out='work/invalid')
    assert not (root/'work/invalid').exists()


def test_readonly_preflight_does_not_create_work_or_call_native(files,monkeypatch):
    root,_,source=files
    monkeypatch.setattr(travel,'_solve',lambda *a:pytest.fail('Read-only preflight cannot solve'))
    inputs=r.validate_source(root)
    assert inputs['problem'].ids==[s['candidateIndex'] for s in source['plan']['selected']]
    assert not (root/'work').exists()


@pytest.mark.parametrize('value',[{}, {'kind':'other','sourceReportSHA256':None,'sourceVectorsSHA256':None},
    {'kind':'native_run','sourceReportSHA256':'0'*64,'sourceVectorsSHA256':None},
    {'kind':'reviewed_run_migration','sourceReportSHA256':None,'sourceVectorsSHA256':None},
    {'kind':'reviewed_run_migration','sourceReportSHA256':'bad','sourceVectorsSHA256':'1'*64}])
def test_execution_origin_rejects_false_or_incomplete_provenance(value):
    with pytest.raises(ValueError):r.execution_origin(value)


def test_migration_origin_is_explicit_and_does_not_need_ignored_ancestors():
    value={'kind':'reviewed_run_migration','sourceReportSHA256':'a'*64,'sourceVectorsSHA256':'b'*64}
    assert r.execution_origin(value)==value
