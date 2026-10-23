"""Bounded monotone closure on an explicit already-built joint problem.

Four fixed-resource LPs per trial; unknown never means globally infeasible.
No solver invocation is hidden in problem construction.
"""
from collections import deque
from time import monotonic
import math
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix
from backend.joint_model import JointProblem,positive

def _linprog(c,Aub,bub,Aeq,beq,bounds,seconds):
    return linprog(c,A_ub=Aub,b_ub=bub,A_eq=Aeq,b_eq=beq,bounds=bounds,method='highs',options={'time_limit':seconds})


def fixed_profile_lp(ctx,current,profile,closed,seconds,*,deadline=None,clock=monotonic):
    """Exact-target LP on all retained selected-site threshold edges.

    Status 1, even with an apparent incumbent, is deliberately not accepted.
    Feasibility is subsequently checked in the complete original formulation.
    """
    seconds=positive(seconds,'LP seconds');call_deadline=clock()+seconds
    if deadline is not None:
        if not math.isfinite(deadline):raise ValueError('Finite absolute LP deadline required')
        call_deadline=min(call_deadline,deadline)
    opened,beds,docs=ctx.resources(current)
    available=opened.copy()
    for j in closed:available[j]=False
    oi,sj=ctx.edges[profile];kept=np.flatnonzero(available[sj]);a,b=oi[kept],sj[kept];ne=len(kept)
    if clock()>=call_deadline:return {'status':'trial_unknown','reason':'LP budget exhausted before formulation','flow':None}
    if ctx.target==0 and ctx.s['districtFloor']==0:
        # Exactly zero annual target/floors has the all-zero assignment even
        # when the last open site is removed. This is not a tiny-flow cutoff.
        return {'status':'profile_feasible','flow':np.zeros(len(oi)),'maximumRowViolation':0.,'edges':ne,'nativeLPRequired':False}
    if not ne:return {'status':'trial_infeasible_fixed_resources','reason':'No retained reachable edges','flow':None}
    district_index={d['id']:k for k,d in enumerate(ctx.districts)};di=np.array([district_index[x] for x in ctx.dd[a]])
    cols=np.tile(np.arange(ne),4)
    rows=np.r_[a,ctx.n+b,ctx.n+ctx.m+b,ctx.n+2*ctx.m+di]
    values=np.r_[np.ones(3*ne),-np.ones(ne)]
    ub=np.r_[ctx.pop/1000,beds*365*ctx.occupancy/ctx.bedrate/1000,docs*ctx.q,
        [-d['population']*ctx.s['districtFloor']/100/1000 for d in ctx.districts]]
    Aub=coo_matrix((values,(rows,cols)),shape=(len(ub),ne)).tocsc()
    Aeq=coo_matrix((np.ones(ne),(np.zeros(ne,dtype=int),np.arange(ne))),shape=(1,ne)).tocsc()
    upper=ctx.pop[a]/1000;bounds=np.column_stack([np.zeros(ne),upper])
    objective=np.zeros(ne);equality_target=np.array([ctx.target/1000])
    # Sparse construction is inside the same wall budget. Recompute immediately
    # before the native call rather than reusing a stale pre-construction limit.
    remaining=call_deadline-clock()
    if remaining<=0:return {'status':'trial_unknown','reason':'LP budget exhausted during formulation; native call not started','flow':None}
    solved=_linprog(objective,Aub,ub,Aeq,equality_target,bounds,remaining)
    if clock()>call_deadline:return {'status':'trial_unknown','reason':'Native LP completed after cooperative deadline; incumbent rejected','flow':None}
    if solved.status==2:return {'status':'trial_infeasible_fixed_resources','reason':'Fixed selected resources/profile LP infeasible; no global claim','flow':None}
    if solved.status!=0 or solved.x is None:return {'status':'trial_unknown','reason':'LP limit/nonoptimal status; any partial incumbent rejected','flow':None}
    f=np.asarray(solved.x,dtype=float)
    if f.shape!=(ne,) or np.any(~np.isfinite(f)) or np.any(f<0) or np.any(f>upper+1e-8):
        return {'status':'trial_unknown','reason':'LP vector finite/nonnegative/bounds audit failed','flow':None}
    violation=float(max(np.maximum(Aub@f-ub,0).max(initial=0),abs(float(f.sum())-ctx.target/1000)))
    if violation>1e-7:return {'status':'trial_unknown','reason':'LP constraints audit failed','flow':None,'maximumRowViolation':violation}
    full=np.zeros(len(oi));full[kept]=f
    return {'status':'profile_feasible','flow':full,'maximumRowViolation':violation,'edges':ne}


def trial_close(ctx,current,closed_ids,deadline,clock=monotonic):
    opened,_,_=ctx.resources(current)
    if not closed_ids or any(isinstance(j,bool) or not isinstance(j,(int,np.integer)) for j in closed_ids) or len(set(closed_ids))!=len(closed_ids) or any(j not in ctx.local or not opened[ctx.local[j]] for j in closed_ids):
        raise ValueError('Closure must name distinct currently open candidate IDs')
    closed=[ctx.local[j] for j in closed_ids];trial=current.copy();profiles=[]
    for j in closed:trial[ctx.site_xs[j]]=0;trial[ctx.nx+j]=0
    for p,(oi,sj) in ctx.edges.items():
        remaining=deadline-clock()
        if remaining<=0:return {'status':'trial_unknown','reason':'Trial/overall budget exhausted before next LP','profiles':profiles},None
        started=clock();r=fixed_profile_lp(ctx,current,p,closed,remaining,deadline=deadline,clock=clock)
        profiles.append({'profile':p,'status':r['status'],'elapsedSeconds':clock()-started,
            'maximumRowViolation':r.get('maximumRowViolation')})
        if clock()>deadline:return {'status':'trial_unknown','reason':'LP completed after cooperative time budget; incumbent rejected','profiles':profiles},None
        if r['status']!='profile_feasible':return {'status':r['status'],'reason':r['reason'],'profiles':profiles},None
        trial[ctx.offsets[p]:ctx.offsets[p]+len(oi)]=r['flow']
    try:
        ctx.validate(trial);cleaned,cleanup=ctx.clean(trial);plan=ctx.serialize(cleaned,cleanup)
    except ValueError as exc:return {'status':'trial_unknown','reason':'Complete original-model audit failed: '+str(exc),'profiles':profiles},None
    if clock()>deadline:return {'status':'trial_unknown','reason':'Post-LP audit completed after cooperative time budget; incumbent rejected','profiles':profiles},None
    improvement=ctx.cost(current)-ctx.cost(cleaned);money_tolerance=max(.01,abs(ctx.cost(current))*1e-12)
    if improvement<=money_tolerance:return {'status':'trial_no_cost_improvement','reason':'No verified strict annual cost decrease','profiles':profiles},None
    if any(s['candidateIndex'] in closed_ids for s in plan['selected']):raise RuntimeError('Closed site survived original-model audit')
    return {'status':'accepted','profiles':profiles,'closedCandidateIndices':list(closed_ids),
        'annualCostReductionTRY':improvement,'resourceCleanup':cleanup,'allOriginalConstraintsVerified':True},cleaned


def batch_close(problem,initial,overall_seconds=300,trial_seconds=15,max_trials=1000,batch_size=16,clock=monotonic):
    overall_seconds=positive(overall_seconds,'overall seconds');trial_seconds=positive(trial_seconds,'trial seconds')
    if overall_seconds>300 or trial_seconds>15:raise ValueError('Heuristic wall/trial limits exceeded')
    for value in (max_trials,batch_size):
        if isinstance(value,bool) or not isinstance(value,int) or value<=0:raise ValueError('Positive integer trial/batch limits required')
    if max_trials>1000 or batch_size>16:raise ValueError('Heuristic trial/batch count limits exceeded')
    began=clock();deadline=began+overall_seconds
    ctx=problem
    current,source_residuals=ctx.read_plan(initial);initial_cost=ctx.cost(current);source_flows=current[ctx.nf:].copy()
    _,maximum=ctx.validate(current)
    opened,_,docs=ctx.resources(current)
    fixed={j:float(ctx.module[int(ctx.xtype[np.flatnonzero((ctx.xsite==j)&(current[:ctx.nx]>.5))[0]])]+docs[j]*ctx.doc_cost) for j in np.flatnonzero(opened)}
    ordered=sorted(np.flatnonzero(opened),key=lambda j:(maximum[j],-fixed[j],ctx.ids[j]))
    groups=deque([[ctx.ids[j] for j in ordered[k:k+batch_size]] for k in range(0,len(ordered),batch_size)])
    trials=[];accepted=0
    while groups and len(trials)<max_trials and clock()<deadline:
        open_now,_,_=ctx.resources(current);group=[j for j in groups.popleft() if open_now[ctx.local[j]]]
        if not group:continue
        start=clock();record,candidate=trial_close(ctx,current,group,min(deadline,start+trial_seconds),clock)
        record.update(proposedClosedCandidateIndices=group,elapsedSeconds=clock()-start)
        trials.append(record)
        if candidate is not None:current=candidate;accepted+=1
        elif record['status'] in ('trial_infeasible_fixed_resources','trial_no_cost_improvement') and len(group)>1:
            half=len(group)//2;groups.appendleft(group[half:]);groups.appendleft(group[:half])
        # Unknown/time-limited groups are not recursively retried under a tight
        # budget and never become an infeasibility certificate.
    final=ctx.serialize(current)
    final['profileReassignmentPerformed']=not np.array_equal(current[ctx.nf:],source_flows)
    final.update(heuristic={'name':'deterministic_batch_close_four_fixed_resource_LPs','sourceHospitalCount':initial['hospitalCount'],
        'sourceAnnualEquivalentCostTRY':initial_cost,'annualCostReductionTRY':initial_cost-final['annualEquivalentCostTRY'],
        'acceptedTrials':accepted,'trials':trials,'configuredOverallSeconds':overall_seconds,'configuredTrialSeconds':trial_seconds,
        'maximumTrials':max_trials,'initialBatchSize':batch_size,'elapsedSeconds':clock()-began,
        'stoppedForBudget':clock()>=deadline,'remainingGroups':len(groups),'sourceOriginalResiduals':source_residuals,
        'timeBudgetScope':'Remaining wall budget passed to each LP; no new LP after deadline. Native cooperative overruns are recorded and rejected, not hidden.',
        'failedTrialScope':'Only the tested remaining locations and fixed resources; unknown is not infeasible; no global certificate.',
        'globalBoundProduced':False,'newCostStageBudgetProduced':False})
    return final
