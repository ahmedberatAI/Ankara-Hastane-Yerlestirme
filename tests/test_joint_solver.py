"""Adverse native return contracts preserve a fully validated source."""
from types import SimpleNamespace
import numpy as np
import pytest
import backend.joint_solver as solver
import backend.joint_heuristic as heuristic
from test_joint_model import fixture,PROFILES


def mock_native(monkeypatch,x,bound=0,accepted=True):
    def fake(c,integer,lb,ub,A,lo,hi,seconds,start,metadata,**kwargs):
        metadata['solverAcceptedFeasibleStart']=accepted
        return SimpleNamespace(x=x,status=1,message='synthetic limit',mip_gap=.5,mip_dual_bound=bound,nodes=0,runtime=.1)
    monkeypatch.setattr(solver,'native_warm_optimize',fake)


@pytest.mark.parametrize('case',['no_incumbent','nan','negative','fractional_resource','closed_flow'])
def test_bad_native_candidate_falls_back_to_source_without_silent_flow_repair(monkeypatch,case):
    p,seed,v,args=fixture(sites_count=3);raw=v.copy()
    if case=='no_incumbent':raw=None
    elif case=='nan':raw[0]=np.nan
    elif case=='negative':raw[-1]=-1e-12
    elif case=='fractional_resource':raw[p.nx]+=.1
    else:
        oi,sj=p.edges[PROFILES[0]];raw[p.offsets[PROFILES[0]]+np.flatnonzero((oi==0)&(sj==2))[0]]=1e-12
    mock_native(monkeypatch,raw);result=solver.solve_cost(p,seed,3)
    back,_=p.read_plan(result);assert np.array_equal(back,v)
    assert result['numericalFallback'] and result['numericFlowCorrectionResidents']==0 and not result['provenOptimal']
    assert result['profileReassignmentPerformed'] is False


def test_dual_above_feasible_cost_is_not_hidden(monkeypatch):
    p,seed,v,args=fixture();mock_native(monkeypatch,v,bound=1e5)
    with pytest.raises(RuntimeError,match='lower bound contradicts'):solver.solve_cost(p,seed,3)


def test_native_start_acceptance_must_be_confirmed(monkeypatch):
    p,seed,v,args=fixture();mock_native(monkeypatch,v,accepted=False)
    with pytest.raises(RuntimeError,match='did not confirm'):solver.solve_cost(p,seed,3)


def test_native_assembly_does_not_start_after_total_deadline(monkeypatch):
    p,seed,v,args=fixture();now=[10.];old=solver.highspy.Highs.passModel
    def slow(highs,*a):
        result=old(highs,*a);now[0]=14.;return result
    monkeypatch.setattr(solver,'monotonic',lambda:now[0])
    monkeypatch.setattr(solver.highspy.Highs,'passModel',slow)
    monkeypatch.setattr(solver.highspy.Highs,'run',lambda *a:pytest.fail('No native solve after deadline'))
    result=solver.solve_cost(p,seed,3)
    back,_=p.read_plan(result)
    assert np.array_equal(back,v) and result['searchSkipped'] and result['nativeRunStarted'] is False
    assert result['costStagePerformed'] is False and result['minimumAnnualCostLowerBoundTRY'] is None
    assert result['profileReassignmentPerformed'] is False


@pytest.mark.parametrize('termination,is_time_limit',[('kInterrupt',False),('kSolveError',False),('kUnknown',False),('kObjectiveTarget',False),('kTimeLimit',True)])
def test_nonoptimal_termination_does_not_automatically_mean_time_limit(monkeypatch,termination,is_time_limit):
    p,seed,v,args=fixture()
    def fake(*a,**k):
        a[9]['solverAcceptedFeasibleStart']=True
        return SimpleNamespace(x=v,status=1,message=termination,nativeModelStatus=termination,
            isTimeLimit=is_time_limit,mip_gap=.5,mip_dual_bound=0,nodes=0,runtime=.1)
    monkeypatch.setattr(solver,'native_warm_optimize',fake)
    result=solver.solve_cost(p,seed,3)
    assert result['timeLimitedFeasible'] is is_time_limit and result['nativeModelStatus']==termination
    assert not result['provenOptimal']


def test_lp_assembly_deadline_and_timeout_incumbent_are_not_accepted(monkeypatch):
    p,seed,v,args=fixture();clock=[10.];original=heuristic.coo_matrix
    def slow(*a,**k):clock[0]=12.;return original(*a,**k)
    monkeypatch.setattr(heuristic,'coo_matrix',slow)
    monkeypatch.setattr(heuristic,'_linprog',lambda *a:pytest.fail('Native LP cannot start after deadline'))
    record,value=heuristic.trial_close(p,v,[0],11.,clock=lambda:clock[0])
    assert value is None and record['status']=='trial_unknown'
    monkeypatch.setattr(heuristic,'coo_matrix',original)
    monkeypatch.setattr(heuristic,'_linprog',lambda *a:SimpleNamespace(status=1,x=np.array([.001,.001])))
    record,value=heuristic.trial_close(p,v,[0],100.,clock=lambda:0)
    assert value is None and record['status']=='trial_unknown'


@pytest.mark.parametrize('kwargs',[{'overall_seconds':301},{'trial_seconds':16},{'max_trials':1001},{'batch_size':17}])
def test_public_heuristic_limits(kwargs):
    p,seed,v,args=fixture()
    with pytest.raises(ValueError):heuristic.batch_close(p,seed,**kwargs)
