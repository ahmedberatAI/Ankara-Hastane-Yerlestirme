"""Bounded cost search for a named profile window, with or without an incumbent.

The calling CLI must additionally put its worker under a hard subprocess timeout.
Native limits are cooperative; no incomplete old four-profile plan is a fallback.
"""
from time import monotonic
from types import SimpleNamespace
import math
import highspy
import numpy as np
from backend.joint_model import positive
from backend.joint_solver import native_warm_optimize
from backend import joint_travel


def native_window_optimize(problem,start,seconds,metadata,deadline,presolve='on'):
    c,integer,lb,ub,A,lo,hi=problem.model
    if start is not None:
        metadata['startKind']='validated_complete_window_incumbent'
        return native_warm_optimize(c,integer,lb,ub,A,lo,hi,seconds,start,metadata,presolve=presolve,deadline=deadline)
    metadata.update(startKind='cold_no_feasible_incumbent',completeStartSupplied=False,
        solverAcceptedFeasibleStart=False,initialPrimalBoundConfirmed=False)
    lp=highspy.HighsLp();lp.num_col_,lp.num_row_=A.shape[1],A.shape[0]
    lp.col_cost_,lp.col_lower_,lp.col_upper_=c,lb,ub;lp.row_lower_,lp.row_upper_=lo,hi
    lp.a_matrix_.start_,lp.a_matrix_.index_,lp.a_matrix_.value_=A.indptr,A.indices,A.data
    lp.integrality_=[highspy.HighsVarType.kInteger if v else highspy.HighsVarType.kContinuous for v in integer]
    solver=highspy.Highs();messages=[]
    def record_log(event):
        message=str(event.message)
        messages.append(message)
        # The caller redirects its worker stdout to an immutable run log.
        # Progress is observational; only the returned primal is validated.
        print(message,end='',flush=True)
    solver.cbLogging.subscribe(record_log)
    for name,value in [('output_flag',True),('threads',1),('random_seed',7),('time_limit',seconds),('mip_rel_gap',.002),('presolve',presolve)]:
        if solver.setOptionValue(name,value)!=highspy.HighsStatus.kOk:raise RuntimeError('HiGHS option rejected '+name)
    if solver.passModel(lp)!=highspy.HighsStatus.kOk:raise RuntimeError('HiGHS window model rejected')
    remaining=deadline-monotonic()
    if remaining<=0:raise TimeoutError('Window deadline during assembly; no native solve started')
    if solver.setOptionValue('time_limit',remaining)!=highspy.HighsStatus.kOk:raise RuntimeError('HiGHS time limit rejected')
    metadata.update(nativeSecondsAllocated=remaining,highsVersion=solver.version())
    solver.run();info=solver.getInfo();solution=solver.getSolution();status=solver.getModelStatus()
    metadata['solverLog']=''.join(messages)
    x=np.asarray(solution.col_value,float) if info.primal_solution_status==highspy.SolutionStatus.kSolutionStatusFeasible else None
    return SimpleNamespace(x=x,status=0 if status==highspy.HighsModelStatus.kOptimal else 2 if status==highspy.HighsModelStatus.kInfeasible else 1,
        message=str(status),nativeModelStatus=str(status),isTimeLimit=status==highspy.HighsModelStatus.kTimeLimit,
        mip_gap=info.mip_gap,mip_dual_bound=info.mip_dual_bound,nodes=int(info.mip_node_count),runtime=float(solver.getRunTime()))


def solve_window_cost(problem,seed=None,time_limit=300,presolve='on',capture_vectors=None):
    seconds=positive(time_limit,'window solver seconds')
    if seconds>1800 or presolve not in ('on','off'):raise ValueError('Window cost search limit is 1800 seconds; invalid presolve')
    began=monotonic();deadline=began+seconds;metadata={};source_residuals=None
    start=None if seed is None else problem.read_plan(seed)[0]
    if start is not None:source_residuals=problem.validate(start)[0]
    base=dict(hardAnnualBudgetTRY=problem.annual_budget,hardBudgetConstraint=True,
        referenceAnnualCostTRY=problem.reference_annual_cost,profileCount=len(problem.times),profileIds=list(problem.times),
        boundScope='supplied_candidate_pool_and_exact_named_profile_set',boundCandidateIndices=list(map(int,problem.ids)),
        annualDemandCountedOnce=True,newJointAnnualBudgetTRY=None,minimumHospitalCountProven=False,
        outerHardTimeoutRequired=True,sourceOriginalResiduals=source_residuals)
    def no_incumbent(reason,solved=None):
        return dict(base,status='inconclusive_without_validated_incumbent',feasible=None,incumbentValidated=False,
            provenOptimal=False,reason=reason,selected=None,profiles=None,annualEquivalentCostTRY=None,
            minimumAnnualCostLowerBoundTRY=None,costGap=None,
            nativeReportedInfeasible=bool(solved is not None and solved.status==2),
            nativeModelStatus=getattr(solved,'nativeModelStatus',None),
            timeLimitReached=bool(getattr(solved,'isTimeLimit',False)),
            modelInfeasibilityIndependentlyCertified=False,warmStart=metadata,elapsedSeconds=monotonic()-began)
    try:
        if monotonic()>=deadline:raise TimeoutError('Window deadline before native preparation')
        solved=native_window_optimize(problem,start,max(1e-9,deadline-monotonic()),metadata,deadline,presolve)
    except TimeoutError as exc:
        if start is None:return no_incumbent(str(exc))
        result=problem.serialize(start);result.update(base,feasible=True,searchSkipped=str(exc),nativeRunStarted=False,
            costStagePerformed=False,provenOptimal=False,minimumAnnualCostLowerBoundTRY=None,costGap=None,
            solverStatus=None,nativeModelStatus=None,solverReportedGap=None,nativeReportedInfeasible=False,
            timeLimitedFeasible=False,profileReassignmentPerformed=False,
            nativeBoundIndependentlyCertified=False,modelInfeasibilityIndependentlyCertified=False,
            sourceAnnualEquivalentCostTRY=problem.cost(start),annualImprovementTRY=0.,dimensions=problem.dimensions,
            numericalFallback='Validated complete window source retained',warmStart=metadata,elapsedSeconds=monotonic()-began)
        if capture_vectors is not None:capture_vectors.update(suppliedOriginalVector=start.copy(),finalOriginalVector=start.copy())
        return result
    if start is not None and solved.status==2:
        raise RuntimeError('Native infeasibility contradicts validated complete window warm start')
    if start is not None and metadata.get('solverAcceptedFeasibleStart') is not True:
        raise RuntimeError('Native solver did not confirm complete window warm start')
    vector=None;fallback=None;raw=None;cleanup=None;rounded=False
    if solved.x is not None:
        try:
            raw=np.asarray(solved.x,float)
            if raw.shape!=problem.c.shape or np.any(~np.isfinite(raw)) or np.any(raw[problem.nf:]<0):
                raise ValueError('Returned window vector has invalid finite/nonnegative entries')
            if np.max(np.abs(raw[:problem.nf]-np.rint(raw[:problem.nf])),initial=0)>1e-5:
                raise ValueError('Returned window integrality violation')
            vector=raw.copy();vector[:problem.nf]=np.rint(vector[:problem.nf]);rounded=bool(np.any(vector[:problem.nf]!=raw[:problem.nf]))
            problem.validate(vector);vector,cleanup=problem.clean(vector)
            if start is not None and problem.cost(vector)>problem.cost(start)+max(.01,abs(problem.cost(start))*1e-12):
                raise ValueError('Returned window solution worsens validated source')
            problem.serialize(vector)
        except ValueError as exc:vector=None;fallback=str(exc)
    else:fallback='No returned feasible window incumbent'
    if vector is None:
        if start is None:return no_incumbent(fallback,solved)
        vector=start.copy();cleanup={'applied':False,'allocationsPreserved':True,'annualCostReductionTRY':0.,
            'numericalFallbackToValidatedSource':True,'numericFlowCorrectionResidents':0.}
    if solved.status==2:
        raise RuntimeError('Native infeasibility contradicts validated returned window incumbent')
    result=problem.serialize(vector,cleanup);annual=result['annualEquivalentCostTRY']
    raw_bound=getattr(solved,'mip_dual_bound',np.nan)
    bound=float(raw_bound*problem.cost_scale+problem.material) if np.isfinite(raw_bound) else None
    tolerance=max(.01,abs(annual)*1e-9)
    if bound is not None and bound>annual+tolerance:raise RuntimeError('Window cost bound contradicts validated feasible incumbent')
    gap=max(0.,(annual-bound)/annual) if bound is not None and annual else 0. if annual==bound==0 else None
    result.update(base,feasible=True,costStagePerformed=True,minimumAnnualCostLowerBoundTRY=bound,costGap=gap,
        costNumericalToleranceTRY=tolerance,nativeBoundIndependentlyCertified=False,
        provenOptimal=bool(solved.status==0 and gap is not None and gap<=1e-8 and fallback is None),
        solverStatus=solved.status,nativeModelStatus=solved.nativeModelStatus,solverMessage=solved.message,
        nativeReportedInfeasible=solved.status==2,solverSeconds=solved.runtime,mipNodes=solved.nodes,
        solverReportedGap=float(solved.mip_gap) if np.isfinite(solved.mip_gap) else None,
        timeLimitedFeasible=bool(solved.isTimeLimit),nativeRunStarted=True,numericalFallback=fallback,
        integerRoundingApplied=rounded,sourceAnnualEquivalentCostTRY=None if start is None else problem.cost(start),
        annualImprovementTRY=None if start is None else problem.cost(start)-annual,
        profileReassignmentPerformed=True if start is None else not np.array_equal(vector[problem.nf:],start[problem.nf:]),
        warmStart=metadata,dimensions=problem.dimensions,elapsedSeconds=monotonic()-began)
    if capture_vectors is not None:
        capture_vectors['finalOriginalVector']=vector.copy()
        if start is not None:capture_vectors['suppliedOriginalVector']=start.copy()
        if raw is not None:capture_vectors['returnedRawVector']=raw.copy()
    return result


def complete_fixed_resource_seed(problem,source_plan,time_limit=120,profile_seconds=15):
    """Try all K assignments on old resources; failure never rejects other designs."""
    seconds=positive(time_limit,'seed completion seconds');each=positive(profile_seconds,'seed profile seconds')
    if seconds>300 or each>15:raise ValueError('Seed completion max 300 total / 15 per profile seconds')
    began=monotonic();deadline=began+seconds
    vector=problem.fixed_resource_vector(source_plan);prefix=vector[:problem.nf].copy();records=[]
    def unknown(reason):
        return None,dict(status='fixed_resource_seed_unavailable',feasible=None,reason=reason,
            profiles=records,globalInfeasibilityProven=False,oldAssignmentsReused=False,elapsedSeconds=monotonic()-began)
    for name,(oi,sj) in problem.edges.items():
        if monotonic()>=deadline:return unknown('Seed completion deadline; no complete incumbent')
        try:lp=joint_travel.formulate_profile(problem,vector,name)
        except ValueError as exc:return unknown(str(exc))
        remaining=min(each,deadline-monotonic())
        if remaining<=0:return unknown('Deadline during profile formulation; no native LP started')
        profile_deadline=monotonic()+remaining
        try:solved=joint_travel._solve(lp,remaining)
        except (ValueError,RuntimeError) as exc:return unknown('Assignment LP error: '+str(exc))
        records.append(dict(profile=name,nativeStatus=solved.status))
        if monotonic()>profile_deadline or solved.status!=0 or solved.x is None:return unknown('Profile lacked a validated optimal native assignment within time')
        f=np.asarray(solved.x,float)
        if f.shape!=lp['c'].shape or np.any(~np.isfinite(f)) or np.any(f<0) or np.any(f>lp['upper']+1e-8):
            return unknown('Profile finite/nonnegative/upper-bound check failed')
        vector[problem.offsets[name]+lp['kept']]=f
    try:
        problem.validate(vector)
        if not np.array_equal(vector[:problem.nf],prefix):raise ValueError('Seed completion changed resources')
        plan=problem.serialize(vector)
    except ValueError as exc:return unknown(str(exc))
    if monotonic()>deadline:return unknown('Seed validation exceeded deadline')
    return plan,dict(status='complete_window_seed_validated',feasible=True,profiles=records,
        oldAssignmentsReused=False,resourcesUnchanged=True,annualDemandCountedOnce=True,
        annualEquivalentCostTRY=plan['annualEquivalentCostTRY'],elapsedSeconds=monotonic()-began)
