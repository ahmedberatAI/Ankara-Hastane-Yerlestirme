from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from test_joint_model import independently_enumerated_cost
from test_window_model import window
import backend.window_solver as solver


@pytest.mark.parametrize('swapped',[False,True])
def test_cold_cost_matches_independent_integer_enumeration_for_twelve_profiles(swapped):
    p,source,args=window(swapped=swapped,budget=30)
    result=solver.solve_window_cost(p,time_limit=3)
    assert result['feasible'] and result['incumbentValidated']
    assert result['annualEquivalentCostTRY']==pytest.approx(independently_enumerated_cost(args[0]))
    assert result['hardBudgetConstraint'] and result['warmStart']['startKind']=='cold_no_feasible_incumbent'
    assert not result['warmStart']['completeStartSupplied']
    assert result['annualMaterialCostTRY']==10 and result['profileCount']==12
    p.read_plan(result)


def test_feasible_cost_can_exceed_reference_but_not_actual_budget():
    p,source,args=window(budget=25,reference=1)
    result=solver.solve_window_cost(p,time_limit=3)
    assert result['annualEquivalentCostTRY']==25 and result['differenceFromReferenceCostTRY']==24
    assert result['budgetSlackTRY']==0


def test_no_feasible_budget_result_is_unknown_without_independent_infeasibility_proof():
    p,source,args=window(budget=24)
    result=solver.solve_window_cost(p,time_limit=3)
    assert result['feasible'] is None and result['selected'] is None
    assert result['nativeReportedInfeasible'] and not result['modelInfeasibilityIndependentlyCertified']
    assert result['minimumAnnualCostLowerBoundTRY'] is None and result['costGap'] is None


def test_old_four_flow_seed_is_not_warm_start_for_twelve(monkeypatch):
    p,source,args=window()
    monkeypatch.setattr(solver,'native_window_optimize',lambda *a:pytest.fail('Old profile seed rejected before native'))
    with pytest.raises(ValueError,match='profile identities'):solver.solve_window_cost(p,source,3)


def test_fixed_resources_reassigned_in_all_profiles_then_valid_native_warm_start():
    p,source,args=window(swapped=True)
    seed,diagnostic=solver.complete_fixed_resource_seed(p,source,time_limit=5,profile_seconds=1)
    assert diagnostic['status']=='complete_window_seed_validated' and not diagnostic['oldAssignmentsReused']
    assert seed['hospitalCount']==source['hospitalCount'] and seed['totalDoctors']==source['totalDoctors']
    assert seed['annualEquivalentCostTRY']==40 and seed['annualMaterialCostTRY']==10
    assert len(seed['profiles'])==12
    result=solver.solve_window_cost(p,seed,time_limit=3)
    assert result['warmStart']['solverAcceptedFeasibleStart']
    assert result['annualEquivalentCostTRY']==26


@pytest.mark.parametrize('status',[1,2,4])
def test_incomplete_resource_seed_never_returns_old_flow_fallback(monkeypatch,status):
    p,source,args=window()
    monkeypatch.setattr(solver.joint_travel,'_solve',lambda *a:SimpleNamespace(status=status,x=None))
    seed,diagnostic=solver.complete_fixed_resource_seed(p,source,5,1)
    assert seed is None and diagnostic['feasible'] is None and not diagnostic['globalInfeasibilityProven']


def fake_native(monkeypatch,x,*,bound=0,status=1,accept=True):
    def call(problem,start,seconds,metadata,deadline,presolve):
        metadata['solverAcceptedFeasibleStart']=accept
        return SimpleNamespace(x=x,status=status,mip_dual_bound=bound,mip_gap=.5,runtime=.1,nodes=0,
            nativeModelStatus='kTimeLimit' if status==1 else 'kUnknown',message='synthetic',isTimeLimit=status==1)
    monkeypatch.setattr(solver,'native_window_optimize',call)


@pytest.mark.parametrize('kind',['none','negative','nan','integer'])
def test_bad_cold_return_has_no_invalid_source_fallback(monkeypatch,kind):
    p,source,args=window();seed,_=solver.complete_fixed_resource_seed(p,source,5,1);v=p.read_plan(seed)[0]
    if kind=='none':v=None
    elif kind=='negative':v[-1]=-1e-13
    elif kind=='nan':v[0]=np.nan
    else:v[p.nx]+=.1
    fake_native(monkeypatch,v)
    result=solver.solve_window_cost(p,None,3)
    assert result['feasible'] is None and result['selected'] is None and not result['provenOptimal']


def test_valid_complete_seed_is_only_permitted_fallback(monkeypatch):
    p,source,args=window();seed,_=solver.complete_fixed_resource_seed(p,source,5,1);v=p.read_plan(seed)[0]
    fake_native(monkeypatch,None);result=solver.solve_window_cost(p,seed,3)
    back,_=p.read_plan(result)
    assert np.array_equal(back,v) and result['numericalFallback'] and not result['profileReassignmentPerformed']


def test_warm_pre_native_timeout_retains_complete_feasible_plan_without_bound(monkeypatch):
    p,source,args=window();seed,_=solver.complete_fixed_resource_seed(p,source,5,1);v=p.read_plan(seed)[0]
    def timeout(*args,**kwargs):raise TimeoutError('Synthetic model preparation deadline')
    monkeypatch.setattr(solver,'native_window_optimize',timeout);vectors={}
    result=solver.solve_window_cost(p,seed,3,capture_vectors=vectors)
    assert result['feasible'] is True and result['incumbentValidated'] is True
    assert not result['costStagePerformed'] and not result['nativeRunStarted'] and not result['provenOptimal']
    assert result['minimumAnnualCostLowerBoundTRY'] is None and result['costGap'] is None
    assert result['nativeModelStatus'] is None and result['solverStatus'] is None
    assert not result['timeLimitedFeasible'] and not result['nativeReportedInfeasible']
    assert result['annualImprovementTRY']==0 and not result['profileReassignmentPerformed']
    assert np.array_equal(p.read_plan(result)[0],v)
    assert np.array_equal(vectors['suppliedOriginalVector'],v)
    assert np.array_equal(vectors['finalOriginalVector'],v)


def test_cold_pre_native_timeout_has_no_feasible_fallback(monkeypatch):
    p,source,args=window()
    def timeout(*args,**kwargs):raise TimeoutError('Synthetic model preparation deadline')
    monkeypatch.setattr(solver,'native_window_optimize',timeout)
    result=solver.solve_window_cost(p,None,3)
    assert result['feasible'] is None and not result['incumbentValidated']
    assert result['selected'] is None and result['minimumAnnualCostLowerBoundTRY'] is None


@pytest.mark.parametrize('returned_primal',[False,True])
def test_native_infeasible_with_validated_warm_plan_is_explicit_contradiction(monkeypatch,returned_primal):
    p,source,args=window();seed,_=solver.complete_fixed_resource_seed(p,source,5,1);v=p.read_plan(seed)[0]
    fake_native(monkeypatch,v if returned_primal else None,status=2,bound=0)
    with pytest.raises(RuntimeError,match='infeasibility contradicts validated complete window warm start'):
        solver.solve_window_cost(p,seed,3)


def test_native_infeasible_with_valid_cold_return_is_explicit_contradiction(monkeypatch):
    p,source,args=window();seed,_=solver.complete_fixed_resource_seed(p,source,5,1);v=p.read_plan(seed)[0]
    fake_native(monkeypatch,v,status=2,bound=0)
    with pytest.raises(RuntimeError,match='infeasibility contradicts validated returned window incumbent'):
        solver.solve_window_cost(p,None,3)


def test_false_bound_above_real_cost_is_rejected(monkeypatch):
    p,source,args=window();seed,_=solver.complete_fixed_resource_seed(p,source,5,1);v=p.read_plan(seed)[0]
    fake_native(monkeypatch,v,bound=1e5)
    with pytest.raises(RuntimeError,match='bound contradicts'):solver.solve_window_cost(p,seed,3)


def test_cold_assembly_deadline_starts_no_native(monkeypatch):
    p,source,args=window();clock=[10.];original=solver.highspy.Highs.passModel
    def slow(h,*a):
        result=original(h,*a);clock[0]=14.;return result
    monkeypatch.setattr(solver,'monotonic',lambda:clock[0]);monkeypatch.setattr(solver.highspy.Highs,'passModel',slow)
    monkeypatch.setattr(solver.highspy.Highs,'run',lambda *a:pytest.fail('Native must not start after deadline'))
    result=solver.solve_window_cost(p,time_limit=3)
    assert result['feasible'] is None and result['nativeModelStatus'] is None


def test_seed_assembly_deadline_starts_no_profile_lp(monkeypatch):
    p,source,args=window();clock=[10.];original=solver.joint_travel.formulate_profile
    def slow(*a):
        value=original(*a);clock[0]=14.;return value
    monkeypatch.setattr(solver,'monotonic',lambda:clock[0]);monkeypatch.setattr(solver.joint_travel,'formulate_profile',slow)
    monkeypatch.setattr(solver.joint_travel,'_solve',lambda *a:pytest.fail('No late profile LP'))
    seed,diagnostic=solver.complete_fixed_resource_seed(p,source,3,1)
    assert seed is None and diagnostic['feasible'] is None


@pytest.mark.parametrize('seconds',[True,0,1800.00001,1801,float('nan')])
def test_time_limit_controls(seconds):
    p,source,args=window()
    with pytest.raises(ValueError):solver.solve_window_cost(p,time_limit=seconds)


@pytest.mark.parametrize('seconds',[301,1800])
def test_explicit_long_cost_limit_is_forwarded_without_running_native(monkeypatch,seconds):
    p,source,args=window();limits=[]
    # This is a forwarding test, not a real-clock accuracy test. A fixed clock
    # avoids sub-picosecond subtraction roundoff at the 1800-second boundary.
    monkeypatch.setattr(solver,'monotonic',lambda:10.)
    def no_native(problem,start,allocated,metadata,deadline,presolve):
        limits.append(allocated)
        return SimpleNamespace(x=None,status=1,nativeModelStatus='kTimeLimit',isTimeLimit=True)
    monkeypatch.setattr(solver,'native_window_optimize',no_native)
    result=solver.solve_window_cost(p,time_limit=seconds)
    assert result['feasible'] is None and result['timeLimitReached'] is True
    assert len(limits)==1 and seconds-1<=limits[0]<=seconds


def test_seed_completion_limit_remains_300_seconds():
    p,source,args=window()
    with pytest.raises(ValueError,match='max 300'):
        solver.complete_fixed_resource_seed(p,source,time_limit=301)


def test_cold_native_log_stream_matches_saved_log(capsys):
    p,source,args=window();metadata={}
    solved=solver.native_window_optimize(p,None,3,metadata,solver.monotonic()+3)
    assert solved.x is not None
    output=capsys.readouterr().out
    assert metadata['solverLog'] and metadata['solverLog'] in output
    assert 'Solving report' in metadata['solverLog']
