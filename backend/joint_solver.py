"""Native cost search on an explicit shared-plan problem and complete warm start."""
import math
import re
from types import SimpleNamespace
from time import monotonic
import highspy
import numpy as np
from backend.joint_model import JointProblem,positive,validate_vector

def acceptance_from_log(log, supplied_objective):
    explicit=re.findall(r'MIP start solution is feasible, objective value is\s+([-+0-9.eE]+)',log)
    before=log.split('Presolving model')[0].split('Presolve is switched off')[0]
    assessed='Assessing feasibility of MIP' in before and all(
        re.search(pattern,before) for pattern in (
            r'Col\s+infeasibilities\s+0\s+',r'Integer\s+infeasibilities\s+0\s+',r'Row\s+infeasibilities\s+0\s+'))
    explicit_value=float(explicit[0]) if explicit else None
    # Log objective has limited printed precision. This comparison checks the
    # reported start is our supplied feasible point, not a repaired other point.
    explicit_matches=explicit_value is not None and math.isclose(explicit_value,supplied_objective,rel_tol=1e-5,abs_tol=1e-8)
    if explicit and not explicit_matches:
        return {'solverAcceptedFeasibleStart':False,'initialPrimalBoundConfirmed':False,
            'acceptanceEvidenceKind':'solver_start_objective_mismatch',
            'solverReportedStartScaledObjective':explicit_value,
            'acceptanceScope':'Solver start objective differs from the supplied vector; acceptance is not certified.'}
    return {'solverAcceptedFeasibleStart':bool(explicit_matches or assessed),
        'initialPrimalBoundConfirmed':bool(explicit_matches),
        'acceptanceEvidenceKind':'explicit_feasible_mip_start' if explicit_matches else 'solver_feasibility_assessment_before_presolve' if assessed else 'unconfirmed',
        'solverReportedStartScaledObjective':explicit_value,
        'acceptanceScope':'A feasible start was assessed; presolve may solve before using an initial search bound.' if not explicit_matches and assessed else 'Explicit initial feasible MIP start recorded.' if explicit_matches else 'No solver acceptance claim.'}


def native_warm_optimize(c,integer,lb,ub,A,lo,hi,seconds,start,metadata,*,presolve='on',deadline=None):
    deadline=monotonic()+seconds if deadline is None else deadline
    metadata['independentVectorResiduals']=validate_vector(start,integer,lb,ub,A,lo,hi)
    metadata['suppliedScaledObjective']=float(c@start)
    lp=highspy.HighsLp();lp.num_col_,lp.num_row_=A.shape[1],A.shape[0]
    lp.col_cost_,lp.col_lower_,lp.col_upper_=c,lb,ub;lp.row_lower_,lp.row_upper_=lo,hi
    lp.a_matrix_.start_,lp.a_matrix_.index_,lp.a_matrix_.value_=A.indptr,A.indices,A.data
    lp.integrality_=[highspy.HighsVarType.kInteger if value else highspy.HighsVarType.kContinuous for value in integer]
    solver=highspy.Highs();messages=[]
    # Callback logging suppresses printing itself while preserving the solver's
    # own start-assessment text. log_to_console=False would suppress callbacks.
    solver.cbLogging.subscribe(lambda event:messages.append(event.message))
    for name,value in [('output_flag',True),('threads',1),('random_seed',7),('time_limit',seconds),('mip_rel_gap',.002),('presolve',presolve)]:
        if solver.setOptionValue(name,value)!=highspy.HighsStatus.kOk:raise RuntimeError('HiGHS option rejected '+name)
    if solver.passModel(lp)!=highspy.HighsStatus.kOk:raise RuntimeError('HiGHS model rejected')
    solution=highspy.HighsSolution();solution.col_value=start;solution.value_valid=True
    status=solver.setSolution(solution)
    metadata.update(apiSetSolutionStatus=str(status),highsVersion=solver.version(),completeStartSupplied=True)
    if status!=highspy.HighsStatus.kOk:raise RuntimeError('HiGHS rejected complete start')
    # Native assembly and setSolution use the same total allowance. Recheck
    # immediately before run: never start a solve with a stale remaining limit.
    remaining=deadline-monotonic()
    if remaining<=0:raise TimeoutError('Cost deadline exhausted during model/start preparation; no native solve started')
    if solver.setOptionValue('time_limit',remaining)!=highspy.HighsStatus.kOk:raise RuntimeError('HiGHS remaining time limit rejected')
    metadata['nativeSecondsAllocated']=remaining
    solver.run();info=solver.getInfo();solution=solver.getSolution();status=solver.getModelStatus()
    log=''.join(messages);metadata.update(acceptance_from_log(log,float(c@start)));metadata['solverLog']=log
    x=np.array(solution.col_value) if info.primal_solution_status==highspy.SolutionStatus.kSolutionStatusFeasible else None
    # No feasible result silently turns into an infeasibility claim if a complete
    # original-model feasible point was supplied and independently checked.
    if status==highspy.HighsModelStatus.kInfeasible:
        raise RuntimeError('Solver infeasibility contradicts independently validated supplied incumbent')
    if x is not None:
        if float(c@x)>float(c@start)+max(1e-8,abs(float(c@start))*1e-8):
            raise RuntimeError('Returned incumbent is worse than the supplied feasible start')
    return SimpleNamespace(x=x,status=0 if status==highspy.HighsModelStatus.kOptimal else 1,
        message=str(status),mip_gap=info.mip_gap,mip_dual_bound=info.mip_dual_bound,
        nativeModelStatus=str(status),isTimeLimit=status==highspy.HighsModelStatus.kTimeLimit,
        nodes=int(info.mip_node_count),runtime=float(solver.getRunTime()))


def solve_cost(problem,seed,time_limit=300,presolve='on',capture_vectors=None):
    """Improve a validated seed in the supplied pool; no new budget is created.

    The bound covers only the supplied candidates, even when the final plan also
    validates in a larger pool. A numerical fallback preserves the source plan.
    """
    seconds=positive(time_limit,'solver seconds')
    if seconds>300:raise ValueError('Cost search is limited to 300 seconds')
    if presolve not in ('on','off'):raise ValueError('Invalid presolve mode')
    began=monotonic();start,source_residuals=problem.read_plan(seed)
    c,integer,lb,ub,A,lo,hi=problem.model;metadata={}
    try:
        solved=native_warm_optimize(c,integer,lb,ub,A,lo,hi,seconds,start,metadata,presolve=presolve,deadline=began+seconds)
    except TimeoutError as exc:
        result=problem.serialize(start)
        result.update(searchSkipped=str(exc),nativeRunStarted=False,newJointAnnualBudgetTRY=None,
            previousBudgetIsConstraint=False,sourceOriginalResiduals=source_residuals,
            elapsedSeconds=monotonic()-began)
        if capture_vectors is not None:capture_vectors.update(suppliedOriginalVector=start.copy(),finalOriginalVector=start.copy())
        return result
    if metadata.get('solverAcceptedFeasibleStart') is not True:
        raise RuntimeError('Native solver did not confirm feasibility of the supplied start')
    source_cost=problem.cost(start);v=start.copy();fallback=None;raw=None;rounded=False
    if solved.x is None:fallback='No returned feasible incumbent; validated source preserved'
    else:
        raw=np.asarray(solved.x,dtype=float)
        try:
            if raw.shape!=start.shape or np.any(~np.isfinite(raw)) or np.any(raw[problem.nf:]<0):
                raise ValueError('Invalid finite/nonnegative returned vector')
            if np.max(np.abs(raw[:problem.nf]-np.rint(raw[:problem.nf])),initial=0)>1e-5:
                raise ValueError('Returned resource integrality residual too large')
            candidate=raw.copy();candidate[:problem.nf]=np.rint(candidate[:problem.nf])
            rounded=bool(np.any(candidate[:problem.nf]!=raw[:problem.nf]))
            problem.validate(candidate)
            candidate,cleanup=problem.clean(candidate)
            if problem.cost(candidate)>source_cost+max(.01,abs(source_cost)*1e-12):
                raise ValueError('Returned/rounded resources worsen validated source')
            v=candidate
        except ValueError as exc:fallback=str(exc)
    if fallback is not None:cleanup={'applied':False,'allocationsPreserved':True,'annualCostReductionTRY':0.,'numericFlowCorrectionResidents':0.,'numericalFallbackToValidatedSource':True}
    result=problem.serialize(v,cleanup);annual=result['annualEquivalentCostTRY'];tolerance=max(.01,abs(annual)*1e-9)
    raw_bound=solved.mip_dual_bound
    bound=float(raw_bound*problem.cost_scale+problem.material) if np.isfinite(raw_bound) else None
    if bound is not None and bound>annual+tolerance:raise RuntimeError('Native lower bound contradicts validated feasible plan')
    gap=max(0.,(annual-bound)/annual) if annual and bound is not None else 0. if annual==bound==0 else None
    result.update(costStagePerformed=True,minimumAnnualCostLowerBoundTRY=bound,costGap=gap,
        profileReassignmentPerformed=not np.array_equal(v[problem.nf:],start[problem.nf:]),
        boundScope='supplied_candidate_pool_all_profile_edges',boundCandidateIndices=list(map(int,problem.ids)),
        provenOptimal=bool(solved.status==0 and gap is not None and gap<=1e-8 and fallback is None),
        solverStatus=solved.status,solverMessage=solved.message,solverSeconds=solved.runtime,
        solverReportedGap=float(solved.mip_gap) if np.isfinite(solved.mip_gap) else None,mipNodes=solved.nodes,
        timeLimitedFeasible=bool(getattr(solved,'isTimeLimit',False)),
        nativeModelStatus=getattr(solved,'nativeModelStatus',solved.message),
        costNumericalToleranceTRY=tolerance,newJointAnnualBudgetTRY=None,
        previousBudgetIsConstraint=False,secondTravelStageImplemented=False,sourceAnnualEquivalentCostTRY=source_cost,
        annualImprovementTRY=source_cost-annual,numericalFallback=fallback,integerRoundingApplied=rounded,
        numericFlowCorrectionResidents=0.,warmStart=metadata,sourceOriginalResiduals=source_residuals,
        dimensions=problem.dimensions,elapsedSeconds=monotonic()-began)
    if capture_vectors is not None:
        capture_vectors.update(suppliedOriginalVector=start.copy(),finalOriginalVector=v.copy())
        if raw is not None:capture_vectors['returnedRawVector']=raw.copy()
    return result
