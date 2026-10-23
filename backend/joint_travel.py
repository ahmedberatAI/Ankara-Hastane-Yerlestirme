"""Four independent travel LPs on completely fixed shared resources.

No site/type/physician changes, no resource cleanup, no extra annual cost.
Any unknown or invalid profile keeps its original feasible assignment.
"""
from fractions import Fraction
from copy import deepcopy
import math
from time import monotonic
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix
from backend.joint_model import positive


def exact_box_dual(c,A,b,E,d,upper,y,z):
    """Exact rational lower bound for the represented binary64 LP arrays.

    For min c*x, Ax<=b, Ex=d, 0<=x<=upper, y<=0 and arbitrary z:
    b*y+d*z+sum(min(0,c-A.T*y-E.T*z)*upper) is a lower bound.
    Float multipliers need not be dual-feasible: sign clipping and the finite-box
    residual term repair them. Fraction arithmetic introduces no proof rounding.
    This certifies the represented LP, not unrounded clinical source ratios.
    """
    c=np.asarray(c,float);b=np.asarray(b,float);d=np.asarray(d,float);upper=np.asarray(upper,float)
    y=np.asarray(y,float);z=np.asarray(z,float);A=A.tocsc();E=E.tocsc()
    if c.ndim!=1 or upper.shape!=c.shape or y.shape!=b.shape or z.shape!=d.shape or A.shape!=(len(b),len(c)) or E.shape!=(len(d),len(c)):
        raise ValueError('Dual certificate shape mismatch')
    if any(np.any(~np.isfinite(v)) for v in (c,b,d,upper,y,z,A.data,E.data)) or np.any(upper<0):
        raise ValueError('Finite coefficient/dual/bounds required')
    correction=float(np.maximum(y,0).max(initial=0));y=np.minimum(y,0)
    F=lambda x:Fraction.from_float(float(x))
    fy=[F(v) for v in y];fz=[F(v) for v in z]
    bound=sum((F(v)*q for v,q in zip(b,fy)),Fraction())+sum((F(v)*q for v,q in zip(d,fz)),Fraction())
    for j in range(len(c)):
        reduced=F(c[j])
        for matrix,multiplier in ((A,fy),(E,fz)):
            for k in range(matrix.indptr[j],matrix.indptr[j+1]):
                reduced-=F(matrix.data[k])*multiplier[matrix.indices[k]]
        if reduced<0:bound+=reduced*F(upper[j])
    try:value=float(bound)
    except OverflowError:raise ValueError('Nonfinite certificate value') from None
    if not math.isfinite(value):raise ValueError('Nonfinite certificate value')
    if Fraction.from_float(value)>bound:
        with np.errstate(over='ignore'):value=float(np.nextafter(value,-np.inf))
    if not math.isfinite(value):raise ValueError('Nonfinite certificate value after downward rounding')
    return {'lowerBoundMinutes':value,'exactNumerator':str(bound.numerator),'exactDenominator':str(bound.denominator),
        'positiveInequalityMultiplierClipping':correction,'certifiedForRepresentedFixedResourceLP':True,
        'method':'Exact rational finite-box Lagrangian on stored binary64 coefficient arrays; not a full location/resource optimum.'}


def formulate_profile(problem,source_vector,profile):
    p=problem;opened,beds,docs=p.resources(source_vector)
    oi,sj=p.edges[profile];kept=np.flatnonzero(opened[sj]);a,b=oi[kept],sj[kept];ne=len(kept)
    if not ne or p.target<=0:raise ValueError('Positive feasible travel target and reachable open sites required')
    district_index={d['id']:k for k,d in enumerate(p.districts)}
    di=np.array([district_index[x] for x in p.dd[a]])
    rows=np.r_[a,p.n+b,p.n+p.m+b,p.n+2*p.m+di]
    cols=np.tile(np.arange(ne),4);values=np.r_[np.ones(3*ne),-np.ones(ne)]
    bub=np.r_[p.pop/1000,beds*365*p.occupancy/p.bedrate/1000,docs*p.q,
        [-d['population']*p.s['districtFloor']/100/1000 for d in p.districts]]
    A=coo_matrix((values,(rows,cols)),shape=(len(bub),ne)).tocsc()
    E=coo_matrix((np.ones(ne),(np.zeros(ne,dtype=int),np.arange(ne))),shape=(1,ne)).tocsc()
    d=np.array([p.target/1000]);upper=p.pop[a]/1000;c=p.times[profile][a,b]/(p.target/1000)
    return {'c':c,'A':A,'b':bub,'E':E,'d':d,'upper':upper,'kept':kept,
        'edgeOrigin':a,'edgeSite':b}


def _solve(lp,seconds):
    return linprog(lp['c'],A_ub=lp['A'],b_ub=lp['b'],A_eq=lp['E'],b_eq=lp['d'],
        bounds=np.column_stack([np.zeros(len(lp['c'])),lp['upper']]),method='highs',options={'time_limit':seconds})


def one_profile(problem,current,profile,deadline,clock=monotonic,capture=None):
    began=clock();p=problem;oi,_=p.edges[profile];offset=p.offsets[profile]
    source_mean=float(current[offset:offset+len(oi)]@p.times[profile][p.edges[profile]]/(p.target/1000))
    base={'profile':profile,'sourceMeanMinutes':source_mean,'accepted':False,'sourceFallback':True,
          'lowerBoundMinutes':None,'gapMinutes':None,'solverReportedOptimal':False,
          'boundScope':'Only this profile with these unchanged open locations, bed types and physician integers; no location/resource/travel-stage global bound.'}
    def fallback(reason,status=None):
        return dict(base,status='source_preserved',reason=reason,nativeStatus=status,elapsedSeconds=clock()-began),current
    if clock()>=deadline:return fallback('Deadline exhausted before formulation')
    lp=formulate_profile(p,current,profile)
    remaining=deadline-clock()
    if remaining<=0:return fallback('Deadline exhausted during formulation; no native LP started')
    try:solved=_solve(lp,remaining)
    except (ValueError,RuntimeError) as exc:
        return fallback('Native LP error; source retained: '+str(exc))
    if clock()>deadline:return fallback('Native LP exceeded cooperative deadline; candidate not accepted',solved.status)
    if solved.status!=0 or solved.x is None:
        return fallback('Native LP not optimal; no infeasibility claim against the validated source',solved.status)
    f=np.asarray(solved.x,float)
    if f.shape!=lp['c'].shape or np.any(~np.isfinite(f)) or np.any(f<0) or np.any(f>lp['upper']+1e-8):
        return fallback('Returned finite/nonnegative/bound validation failed',solved.status)
    candidate=current.copy();candidate[offset:offset+len(oi)]=0
    candidate[offset+lp['kept']]=f
    try:
        residuals,_=p.validate(candidate)
        if not np.array_equal(candidate[:p.nf],current[:p.nf]):raise ValueError('Fixed resources changed')
        certificate=exact_box_dual(lp['c'],lp['A'],lp['b'],lp['E'],lp['d'],lp['upper'],
            solved.ineqlin.marginals,solved.eqlin.marginals)
        mean=float(lp['c']@f)
        # No worsening is accepted, including a tiny positive difference.
        if mean>source_mean:raise ValueError('Travel mean worsened; retain original profile')
        if certificate['lowerBoundMinutes']>mean+1e-7:raise ValueError('Lower bound contradicts checked primal mean')
        if abs(p.cost(candidate)-p.cost(current))>1e-6:raise ValueError('Fixed-resource annual bill changed')
        p.serialize(candidate) # Complete original-model JSON/vector roundtrip.
    except (ValueError,AttributeError,TypeError) as exc:return fallback(str(exc),solved.status)
    if clock()>deadline:return fallback('Post-LP physical/dual audit exceeded deadline; candidate not accepted',solved.status)
    if capture is not None:
        capture[profile]={'lp':lp,'inequalityDual':np.asarray(solved.ineqlin.marginals,float),
            'equalityDual':np.asarray(solved.eqlin.marginals,float),'primal':f.copy()}
    return dict(base,status='travel_profile_accepted',accepted=True,sourceFallback=False,nativeStatus=solved.status,
        solverReportedOptimal=True,meanMinutes=mean,reductionMinutes=source_mean-mean,
        lowerBoundMinutes=certificate['lowerBoundMinutes'],gapMinutes=max(0.,mean-certificate['lowerBoundMinutes']),
        primalMinusLowerBoundMinutes=mean-certificate['lowerBoundMinutes'],primalDualToleranceMinutes=1e-7,
        certificate=certificate,physicalResiduals=residuals,nativeMessage=solved.message,elapsedSeconds=clock()-began),candidate


def improve_travel(problem,source,overall_seconds=60,profile_seconds=15,clock=monotonic,capture=None):
    if positive(overall_seconds,'overall seconds')>60 or positive(profile_seconds,'profile seconds')>15:
        raise ValueError('Fixed-resource travel limits are at most 60 overall / 15 per profile seconds')
    if problem.target<=0:raise ValueError('Positive travel target required')
    began=clock();deadline=began+overall_seconds
    current,residuals=problem.read_plan(source);original=current.copy();records=[]
    for profile in problem.times:
        record,current=one_profile(problem,current,profile,min(deadline,clock()+profile_seconds),clock,capture)
        records.append(record)
    result=problem.serialize(current)
    # A fallback means the complete original JSON assignment, not a silently
    # rounded reconstruction through thousands-of-residents solver units.
    for k,record in enumerate(records):
        if record['sourceFallback']:result['profiles'][k]=deepcopy(source['profiles'][k])
    problem.read_plan(result)
    result.pop('secondTravelStageImplemented',None)
    if not np.array_equal(current[:problem.nf],original[:problem.nf]):raise RuntimeError('Resources changed in fixed travel stage')
    if result['annualEquivalentCostTRY']!=problem.cost(original):raise RuntimeError('Annual fixed-resource bill changed')
    result.update(profileReassignmentPerformed=not np.array_equal(current[problem.nf:],original[problem.nf:]),
        fixedResourceTravel={'profiles':records,'allProfilesAccepted':all(r['accepted'] for r in records),
            'resourcesUnchanged':True,'resourceCleanupPerformed':False,'annualCostUnchanged':True,
            'additionalBudgetTRY':0.,'wholeJointTravelOptimumProven':False,'noCommonIndividualIdentityCoupling':True,
            'sourceOriginalResiduals':residuals,'elapsedSeconds':clock()-began,
            'configuredOverallSeconds':overall_seconds,'configuredProfileSeconds':profile_seconds,
            'scope':'Four separate minimum-mean assignment LPs on unchanged shared resources; no annual frequency weights or global site/resource optimum. Unknown/numerical profiles preserve their complete original flows.'})
    if capture is not None:capture['sourceVector']=original;capture['finalVector']=current
    return result
