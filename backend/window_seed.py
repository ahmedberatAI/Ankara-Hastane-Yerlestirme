"""Bounded smaller-profile cost searches to prepare a checked 44-profile seed.

The runner supplies checked problems, immutable input bindings and an external
hard timeout. This helper never publishes a final certificate: no partial plan
or native subset bound is promoted to a full-window result.
"""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
from time import monotonic

import numpy as np

from backend import joint_travel
from backend.window_solver import solve_window_cost,complete_fixed_resource_seed

ROOT=Path(__file__).resolve().parents[1]
LOADED_CODE_LF_SHA256=hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest()


def sha(blob):return hashlib.sha256(blob).hexdigest()


def code_hash():return sha(Path(__file__).read_bytes().replace(b'\r\n',b'\n'))


def progress(event,**fields):
    """Observational worker progress; it is never a primal validation claim."""
    print(json.dumps(dict(component='window_seed',event=event,**fields),allow_nan=False),flush=True)


def blob(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()


def identity(value):
    """Bind values AND ordered semantic maps, without lossy array JSON casts."""
    if isinstance(value,np.ndarray):
        return dict(kind='array',shape=list(value.shape),dtype=str(value.dtype),sha256=sha(value.tobytes()))
    if hasattr(value,'format') and hasattr(value,'indptr'):
        return dict(kind='sparse',format=value.format,shape=list(value.shape),
            arrays={key:identity(getattr(value,key)) for key in ('data','indices','indptr')})
    if isinstance(value,dict):return dict(kind='mapping',items=[[identity(k),identity(v)] for k,v in value.items()])
    if isinstance(value,(list,tuple)):return dict(kind=type(value).__name__,items=[identity(v) for v in value])
    if isinstance(value,np.generic):return identity(value.item())
    if value is None or type(value) in (str,int,float,bool):return value
    raise ValueError('Unsupported model identity field: '+type(value).__name__)


def signature(problem):
    """Bind every model field except elapsed construction time.

    In particular the sparse coefficients alone do not identify their meaning:
    edges, offsets, local/global IDs, resource/template columns and derived LP
    coefficients must stay bound too. Unknown future fields fail closed.
    """
    return sha(blob(identity({k:v for k,v in problem.__dict__.items() if k!='buildSeconds'})))


def checked_layout(p):
    """Check each profile's own contiguous layout before mapping by name."""
    for key in ('n','m','nx','nf'):
        value=getattr(p,key)
        if isinstance(value,(bool,np.bool_)) or not isinstance(value,(int,np.integer)) or value<=0:
            raise ValueError('Invalid model layout dimension '+key)
    if p.nf!=p.nx+p.m or p.pop.shape!=(p.n,) or p.dd.shape!=(p.n,):
        raise ValueError('Invalid shared resource/population layout')
    if (len(p.ids)!=p.m or len(set(p.ids))!=p.m or
        any(isinstance(i,(bool,np.bool_)) or not isinstance(i,(int,np.integer)) or i<0 for i in p.ids) or
        [s['candidateIndex'] for s in p.sites]!=p.ids):
        raise ValueError('Candidate IDs/sites layout differs')
    if p.local!={key:i for i,key in enumerate(p.ids)}:raise ValueError('Candidate local ID layout differs')
    if len(p.site_xs)!=p.m or p.xsite.shape!=(p.nx,) or p.xtype.shape!=(p.nx,):
        raise ValueError('Invalid template column layout')
    for values,limit in ((p.xsite,p.m),(p.xtype,len(p.beds))):
        if not np.issubdtype(values.dtype,np.integer) or np.any(values<0) or np.any(values>=limit):
            raise ValueError('Invalid resource column identities')
    if any(not np.array_equal(xs,np.flatnonzero(p.xsite==j)) for j,xs in enumerate(p.site_xs)):
        raise ValueError('Site/template column mapping differs')
    if list(p.edges)!=list(p.times) or list(p.offsets)!=list(p.times):
        raise ValueError('Profile edge/offset identities differ')
    offset=p.nf
    for name,times in p.times.items():
        if times.shape!=(p.n,p.m):raise ValueError('Profile matrix layout differs')
        edge=p.edges[name]
        expected=np.where(np.isfinite(times)&(times<=p.s['threshold']))
        if len(edge)!=2 or any(not np.issubdtype(a.dtype,np.integer) or not np.array_equal(a,b) for a,b in zip(edge,expected)):
            raise ValueError('Profile edge mapping differs from its matrix')
        if isinstance(p.offsets[name],(bool,np.bool_)) or not isinstance(p.offsets[name],(int,np.integer)) or p.offsets[name]!=offset:
            raise ValueError('Profile flow offset is not contiguous')
        offset+=len(edge[0])
    A=p.model[4]
    if any(np.shape(p.model[i])!=(offset,) for i in range(4)) or p.c.shape!=(offset,) or A.shape[1]!=offset:
        raise ValueError('Model variable layout differs from profile edges')
    if not np.array_equal(p.c,p.model[0]) or any(np.shape(p.model[i])!=(A.shape[0],) for i in (5,6)):
        raise ValueError('Model coefficient/row layout differs')


def compatible(full,subset,names):
    if list(subset.times)!=list(names) or subset.ids!=full.ids or subset.nf!=full.nf:
        raise ValueError('Subset identities or shared resource layout differ')
    if subset.h!=full.h or subset.s!=full.s or subset.material!=full.material or subset.annual_budget!=full.annual_budget:
        raise ValueError('Subset changes health, scenario, annual material or budget')
    if subset.districts!=full.districts or subset.total!=full.total or not np.array_equal(subset.pop,full.pop):
        raise ValueError('Subset population denominators differ')
    if not np.array_equal(subset.dd,full.dd):raise ValueError('Subset district identities differ')
    for key in ('sites','local','n','m','nx','nf','target','reference_annual_cost','cost_scale',
                'minimum','da','available','beds','area','xsite','xtype','site_xs','contact',
                'bedrate','occupancy','q','bedcap','module','doc_cost','conflicts'):
        if identity(getattr(subset,key))!=identity(getattr(full,key)):
            raise ValueError('Subset shared resource semantics differ: '+key)
    for i in (0,1,2,3):
        if not np.array_equal(subset.model[i][:subset.nf],full.model[i][:full.nf]):
            raise ValueError('Subset resource coefficients or bounds differ')
    for name in names:
        if not np.array_equal(subset.times[name],full.times[name]):
            raise ValueError('Same-named profile matrix changed')
        if any(not np.array_equal(a,b) for a,b in zip(subset.edges[name],full.edges[name])):
            raise ValueError('Same-named profile edge identities differ')
    checked_layout(full);checked_layout(subset)


def complete_named_window(full,subset,plan,seconds=60,profile_seconds=15,*,clock=monotonic,lp_solve=None):
    """Preserve checked SAME-NAMED flows; solve only remaining actual clocks.

    Failure means this resource attempt has no checked complete assignment.
    Native infeasibility is diagnostic, never a global/candidate-pool proof.
    """
    lp_solve=lp_solve or joint_travel._solve
    if len(full.times)!=44:raise ValueError('Completion requires exactly 44 named profiles')
    if type(seconds) not in (int,float) or not np.isfinite(seconds) or not 0<seconds<=300:
        raise ValueError('Completion time must be in (0,300]')
    if type(profile_seconds) not in (int,float) or not np.isfinite(profile_seconds) or not 0<profile_seconds<=15:
        raise ValueError('Profile LP time must be in (0,15]')
    began=clock();deadline=began+seconds;before=signature(full);subset_before=signature(subset);names=list(subset.times)
    compatible(full,subset,names);old,_=subset.read_plan(plan)
    vector=full.fixed_resource_vector(plan);prefix=vector[:full.nf].copy()
    if not np.array_equal(prefix,old[:subset.nf]):raise ValueError('Resource prefix differs after projection')
    records=[]
    for name in full.times:
        count=len(full.edges[name][0]);offset=full.offsets[name]
        if name in subset.times:
            start=subset.offsets[name];vector[offset:offset+count]=old[start:start+count]
            records.append(dict(profile=name,status='checked_same_named_flow_reused',accepted=True,nativeStatus=None))
            continue
        if clock()>=deadline:
            records.append(dict(profile=name,status='unknown_deadline',accepted=False,nativeStatus=None));continue
        try:
            lp=joint_travel.formulate_profile(full,vector,name)
            remaining=min(profile_seconds,deadline-clock())
            if remaining<=0:
                records.append(dict(profile=name,status='unknown_deadline',accepted=False,nativeStatus=None));continue
            own_deadline=clock()+remaining;solved=lp_solve(lp,remaining)
            if clock()>own_deadline:
                records.append(dict(profile=name,status='unknown_deadline',accepted=False,nativeStatus=solved.status));continue
            if solved.status!=0 or solved.x is None:
                records.append(dict(profile=name,status='no_validated_assignment',accepted=False,nativeStatus=solved.status));continue
            f=np.asarray(solved.x,float)
            if f.shape!=lp['c'].shape or np.any(~np.isfinite(f)) or np.any(f<0) or np.any(f>lp['upper']+1e-8):
                raise ValueError('Invalid finite/nonnegative LP flow')
            if np.max(lp['A']@f-lp['b'],initial=0)>1e-7 or np.max(np.abs(lp['E']@f-lp['d']),initial=0)>1e-7:
                raise ValueError('LP primal residual failed')
            served=np.bincount(lp['edgeOrigin'],weights=f*1000,minlength=full.n)
            if abs(served.sum()-full.target)>.001:raise ValueError('Exact target physical tolerance failed')
            if any(100*served[full.dd==d['id']].sum()/d['population']<full.s['districtFloor']-1e-6 for d in full.districts):
                raise ValueError('District percent tolerance failed')
            vector[offset+lp['kept']]=f
            records.append(dict(profile=name,status='profile_primal_checked',accepted=True,nativeStatus=solved.status))
        except (ValueError,RuntimeError,TimeoutError) as exc:
            records.append(dict(profile=name,status='unknown_numerical_or_solver',accepted=False,nativeStatus=None,reason=str(exc)))
    result=dict(status='no_validated_complete_window_assignment',feasible=None,profiles=records,
        failedProfileIds=[r['profile'] for r in records if not r['accepted']],
        modelInfeasibilityProven=False,resourcesUnchanged=True,annualDemandCountedOnce=True,
        sameNamedFlowsReused=names,oldProfilesRelabelled=False,elapsedSeconds=clock()-began)
    if signature(full)!=before:raise ValueError('Full model changed during completion')
    if signature(subset)!=subset_before:raise ValueError('Subset model changed during completion')
    if not np.array_equal(prefix,vector[:full.nf]):raise ValueError('Completion changed resources')
    if result['failedProfileIds'] or clock()>deadline:return None,result,vector
    try:
        full.validate(vector);complete=full.serialize(vector);final,_=full.read_plan(complete)
        if not np.array_equal(final[:full.nf],prefix):raise ValueError('Serialized resources changed')
    except ValueError as exc:
        result['reason']=str(exc);return None,result,vector
    if clock()>deadline:
        result['reason']='Complete physical audit exceeded deadline';return None,result,vector
    result.update(status='complete_44_seed_primal_checked',feasible=True,annualEquivalentCostTRY=complete['annualEquivalentCostTRY'])
    return complete,result,final


def run_seed_search(full,build_subset,source_plan,*,overall_seconds=900,stage_seconds=300,
                    completion_seconds=60,profile_seconds=15,max_stages=4,clock=monotonic,
                    cost_search=None,warm_complete=None,lp_solve=None,out=None,
                    bindings=None,binding_gate=None):
    """Prepare only a full-window seed, never a final optimization certificate.

    ``build_subset`` must rebuild the same candidate/resource model for exact
    names. The caller must run an independent final auditor before reuse and
    put any real execution under a hard subprocess limit.
    """
    cost_search=cost_search or solve_window_cost;warm_complete=warm_complete or complete_fixed_resource_seed
    if code_hash()!=LOADED_CODE_LF_SHA256:raise ValueError('Loaded seed helper code differs from current file')
    if len(full.times)!=44:raise ValueError('Seed preparation requires exactly 44 named profiles')
    for value,limit in ((overall_seconds,1800),(stage_seconds,300),(completion_seconds,300),(profile_seconds,15)):
        if type(value) not in (int,float) or not np.isfinite(value) or not 0<value<=limit:raise ValueError('Invalid bounded time control')
    if type(max_stages) is not int or not 1<=max_stages<=11:raise ValueError('Invalid stage cap')
    folder=None
    if out is not None:
        folder=Path(out).absolute();work=ROOT/'work'
        if work.resolve()!=work or folder.resolve()!=folder or not folder.is_relative_to(work) or folder.exists():
            raise ValueError('Fresh unredirected work folder required')
        if not isinstance(bindings,dict) or not bindings or not callable(binding_gate):
            raise ValueError('Persisted seed preparation requires caller source bindings and an entry/exit gate')
        folder.mkdir(parents=True)
    names=list(full.times);active=names[:12];last_plan=deepcopy(source_plan);began=clock();deadline=began+overall_seconds
    model_signature=signature(full);stages=[];artifact_hashes={}
    def gate():
        if signature(full)!=model_signature or code_hash()!=LOADED_CODE_LF_SHA256:
            raise ValueError('Model or helper code changed during seed preparation')
        if binding_gate is not None:binding_gate()
    def save(name,payload):
        if folder is not None:
            with (folder/name).open('xb') as stream:stream.write(payload)
            artifact_hashes[name]=sha(payload)
    def finish(seed,reason):
        gate()
        report=dict(format=1,artifactType='window-seed-preparation',
            status='complete_window_seed_prepared' if seed is not None else 'seed_preparation_inconclusive',
            feasible=True if seed is not None else None,reason=reason,
            fullProfileIds=names,candidateIndices=list(map(int,full.ids)),hardAnnualBudgetTRY=full.annual_budget,
            referenceAnnualCostTRY=full.reference_annual_cost,annualDemandCountedOnce=True,
            outerHardTimeoutRequired=True,independentFinalAuditRequired=True,
            globalInfeasibilityProven=False,globalOptimalityProven=False,
            profileSubsetBoundsTransferred=False,modelSignature=model_signature,helperCodeSHA256=LOADED_CODE_LF_SHA256,
            callerSourceBindings=bindings,stages=stages,artifacts=artifact_hashes.copy(),elapsedSeconds=clock()-began,
            controls=dict(overallSeconds=overall_seconds,costStageSeconds=stage_seconds,
                completionSeconds=completion_seconds,profileSeconds=profile_seconds,maxStages=max_stages),
            cooperativeOverallOverrunSeconds=max(0.,clock()-deadline),
            completeSeedPlan=seed,
            scope='Only seed preparation. Partial stage plans/bounds are not 44-profile witnesses. Complete seed must pass the independent full-window auditor before any later full-model warm search.')
        save('seed-preparation.json',blob(report))
        progress('finished',status=report['status'],stageCount=len(stages),elapsedSeconds=report['elapsedSeconds'],reason=reason)
        return report
    gate()
    for index in range(max_stages):
        if clock()>=deadline:return finish(None,'Overall deadline before next stage')
        stage_began=clock();stage_deadline=min(deadline,stage_began+stage_seconds)
        progress('stage_started',stage=index+1,optimizedProfileIds=active,requiredFinalProfileCount=44)
        problem=build_subset(active)
        compatible(full,problem,active);gate();subset_signature=signature(problem)
        remaining=stage_deadline-clock()
        if remaining<=0:return finish(None,'Deadline during subset assembly')
        try:seed,preparation=warm_complete(problem,last_plan,min(30.,remaining),profile_seconds)
        except (ValueError,RuntimeError,TimeoutError) as exc:seed=None;preparation=dict(status='unknown_seed_completion',reason=str(exc))
        gate()
        if signature(problem)!=subset_signature:raise ValueError('Subset model changed during resource seed completion')
        remaining=stage_deadline-clock()
        if remaining<=0:return finish(None,'Deadline before subset cost search')
        progress('subset_cost_started',stage=index+1,profileCount=len(active),completeSubsetWarmStart=seed is not None,maximumSeconds=remaining)
        vectors={};result=cost_search(problem,seed,remaining,capture_vectors=vectors)
        gate()
        if signature(problem)!=subset_signature:raise ValueError('Subset model changed during its cost search')
        stage=dict(stage=index+1,optimizedProfileIds=active.copy(),candidateIndices=list(map(int,problem.ids)),
            dimensions=problem.dimensions,resourceSeedPreparation=preparation,costResult=result,
            costStageElapsedSeconds=clock()-stage_began,cooperativeCostStageOverrunSeconds=max(0.,clock()-stage_deadline),
            boundScope='Only this stage candidate pool and named profile subset; never copied into the final full-window cost bound.')
        stages.append(stage)
        prefix=f'stage-{index+1:02d}'
        archive=io.BytesIO();np.savez_compressed(archive,**vectors)
        save(prefix+'-cost-vectors.npz',archive.getvalue());save(prefix+'-cost.json',blob(stage))
        progress('subset_cost_finished',stage=index+1,status=result.get('status'),feasible=result.get('feasible'),elapsedSeconds=stage['costStageElapsedSeconds'])
        if result.get('feasible') is not True:return finish(None,'Subset cost search produced no validated integer incumbent')
        problem.read_plan(result);last_plan=deepcopy(result)
        if clock()>=deadline:return finish(None,'Overall deadline after subset search')
        complete,diagnostic,partial=complete_named_window(full,problem,result,
            min(completion_seconds,deadline-clock()),profile_seconds,clock=clock,lp_solve=lp_solve)
        gate();stage['fullWindowCompletion']=diagnostic
        progress('full_window_completion_finished',stage=index+1,status=diagnostic['status'],failedProfileIds=diagnostic['failedProfileIds'])
        archive=io.BytesIO();np.savez_compressed(archive,**{
            'complete44Vector' if complete is not None else 'unvalidatedPartial44Vector':partial})
        save(prefix+'-completion-vectors.npz',archive.getvalue());save(prefix+'-completion.json',blob(diagnostic))
        if complete is not None:
            if clock()>deadline:return finish(None,'Overall deadline during complete-seed audit')
            return finish(complete,'Every named profile and original shared-resource condition checked')
        failed=set(diagnostic['failedProfileIds']);blocks={i//4 for i,name in enumerate(names) if name in failed}
        expanded=[name for i,name in enumerate(names) if name in active or i//4 in blocks]
        stage['nextProfileIds']=expanded
        if expanded==active:return finish(None,'No unchecked failing offset block available; no infeasibility claim')
        progress('activate_failed_offset_blocks',stage=index+1,nextProfileIds=expanded)
        active=expanded
    return finish(None,'Bounded stage count exhausted without a complete seed')


if __name__=='__main__':
    raise SystemExit('Use the bounded window-plan runner; this module only prepares a complete seed.')
