"""Variable-window shared resources composed from immutable four-profile blocks.

K is a positive multiple of four. Every supplied profile keeps its own flows;
the integer resource prefix and annual material cost appear exactly once.
"""
import math
from time import monotonic
import numpy as np
from scipy.sparse import block_diag,hstack,vstack,coo_matrix
from backend.joint_model import (JointProblem,build_joint_problem,reconstruct_plan,
    validate_vector,positive,finite_nonnegative)

ORIGINAL_ANNUAL_BUDGET_TRY=189556939209.2935
REFERENCE_ANNUAL_COST_TRY=175868263288.70182
BUDGET_TOLERANCE_TRY=.01


class WindowProblem(JointProblem):
    def validate(self,vector):
        residuals,maximum=super().validate(vector)
        annual=self.cost(vector)
        if not math.isfinite(annual) or annual>self.annual_budget+BUDGET_TOLERANCE_TRY:
            raise ValueError('Hard annual budget exceeded after original-vector validation')
        return residuals,maximum

    def fixed_resource_vector(self,plan):
        """Parse resources from an audited older plan; NOT a feasible K-profile seed.

        Empty flows deliberately remain invalid until every new profile is
        independently assigned. No old profile is relabelled or copied.
        """
        raw={'hospitalCount':plan['hospitalCount'],'selected':plan['selected'],
             'profiles':[{'profile':p,'allocations':[]} for p in self.times]}
        vector=reconstruct_plan(raw,self.times,self.sites,self.h,self.s,len(self.c))
        indices=np.r_[self.shared_row_indices,self.budget_row_index]
        c,integer,lb,ub,A,lo,hi=self.model
        validate_vector(vector,integer,lb,ub,A[indices],lo[indices],hi[indices])
        opened,beds,docs=self.resources(vector)
        for key,value in (('hospitalCount',int(opened.sum())),('totalBeds',int(beds.sum())),('totalDoctors',int(docs.sum()))):
            if type(plan.get(key)) is not int or plan[key]!=value:raise ValueError('Source resource totals differ')
        annual=finite_nonnegative(plan['annualEquivalentCostTRY'],'source annual cost')
        if abs(annual-self.cost(vector))>max(.01,annual*1e-12):raise ValueError('Source fixed-resource bill differs')
        if self.cost(vector)>self.annual_budget+BUDGET_TOLERANCE_TRY:raise ValueError('Source resources exceed window budget')
        for key,expected in (('annualMaterialCostTRY',self.material),('annualFixedResourceCostTRY',annual-self.material)):
            if abs(finite_nonnegative(plan[key],key)-expected)>max(.01,annual*1e-12):raise ValueError('Source cost decomposition differs')
        return vector

    def serialize(self,vector,cleanup=None):
        result=super().serialize(vector,cleanup)
        result.update(hardAnnualBudgetTRY=self.annual_budget,hardBudgetConstraint=True,
            referenceAnnualCostTRY=self.reference_annual_cost,
            differenceFromReferenceCostTRY=result['annualEquivalentCostTRY']-self.reference_annual_cost,
            budgetSlackTRY=self.annual_budget-result['annualEquivalentCostTRY'],
            profileCount=len(self.times),profileIds=list(self.times),
            boundScope='supplied_candidate_pool_and_exact_named_profile_set',
            minimumHospitalCountProven=False,annualDemandCountedOnce=True)
        return result


def build_window_problem(profile_times,populations,demand_districts,districts,province_total,
                         candidates,planning,scenario,conflicts=(),*,
                         annual_budget=ORIGINAL_ANNUAL_BUDGET_TRY,
                         reference_annual_cost=REFERENCE_ANNUAL_COST_TRY):
    began=monotonic()
    budget=positive(annual_budget,'hard annual budget')
    reference=finite_nonnegative(reference_annual_cost,'reference annual cost')
    if not isinstance(profile_times,dict) or not profile_times or len(profile_times)%4:
        raise ValueError('Window profile count must be a positive multiple of four')
    if any(not isinstance(name,str) or not name for name in profile_times):raise ValueError('Named actual profiles required')
    items=list(profile_times.items());blocks=[]
    for first in range(0,len(items),4):
        blocks.append(build_joint_problem(dict(items[first:first+4]),populations,demand_districts,districts,
            province_total,candidates,planning,scenario,conflicts))
    first=blocks[0];nf=first.nf
    for block in blocks[1:]:
        if block.ids!=first.ids or block.nf!=nf or block.cost_scale!=first.cost_scale or block.material!=first.material:
            raise ValueError('Four-profile block shared identity or one annual bill differs')
        for key in ('xsite','xtype','area','available','beds','module'):
            if not np.array_equal(getattr(block,key),getattr(first,key)):raise ValueError('Shared resource layout differs')
        for k in range(4):
            if not np.array_equal(block.model[k][:nf],first.model[k][:nf]):raise ValueError('Shared resource cost/bounds/integrality differ')
    matrices=[p.model[4] for p in blocks]
    # Identical plot/minimum-staff/conflict rows remain repeated. This preserves
    # the frozen coefficients exactly and is mathematically redundant.
    A=hstack([vstack([a[:,:nf] for a in matrices],format='csc'),
        block_diag([a[:,nf:] for a in matrices],format='csc')],format='csc')
    flow_count=sum(len(p.c)-nf for p in blocks);nv=nf+flow_count
    c=np.r_[first.c[:nf],np.zeros(flow_count)]
    integer=np.r_[first.model[1][:nf],np.zeros(flow_count)]
    lb=np.r_[first.model[2][:nf],np.concatenate([p.model[2][nf:] for p in blocks])]
    ub=np.r_[first.model[3][:nf],np.concatenate([p.model[3][nf:] for p in blocks])]
    lo=np.concatenate([p.model[5] for p in blocks]);hi=np.concatenate([p.model[6] for p in blocks])
    budget_index=len(lo)
    budget_row=coo_matrix((c[:nf],(np.zeros(nf,dtype=int),np.arange(nf))),shape=(1,nv)).tocsc()
    A=vstack([A,budget_row],format='csc');lo=np.r_[lo,-np.inf];hi=np.r_[hi,(budget-first.material)/first.cost_scale]
    times={};edges={};offsets={};offset=nf;shared_indices=[];row_offset=0
    block_profile_rows=first.n+2*first.m+1+len(first.districts)
    common_rows=first.model[4].shape[0]-4*block_profile_rows
    if common_rows<3*first.m:raise ValueError('Unexpected frozen row layout')
    # Check the common row prefix rather than relying on row counts alone.
    shared=first.model[4][:common_rows,:nf]
    for block in blocks:
        actual=block.model[4][:common_rows,:nf]
        if actual.shape!=shared.shape or any(not np.array_equal(getattr(actual,k),getattr(shared,k)) for k in ('data','indices','indptr')):
            raise ValueError('Frozen shared rows differ')
        if block.model[4].shape[0]!=common_rows+4*block_profile_rows:raise ValueError('Unexpected block row layout')
        shared_indices.extend(range(row_offset,row_offset+common_rows));row_offset+=block.model[4].shape[0]
        for name,raw in block.times.items():
            times[name]=raw;edges[name]=block.edges[name];offsets[name]=offset;offset+=len(edges[name][0])
    assert offset==nv
    fields=dict(first.__dict__)
    fields.update(times=times,edges=edges,offsets=offsets,c=c,model=(c,integer,lb,ub,A,lo,hi),
        annual_budget=budget,reference_annual_cost=reference,budget_row_index=budget_index,
        shared_row_indices=np.asarray(shared_indices,dtype=int),buildSeconds=monotonic()-began,
        composition={'blockCount':len(blocks),'profilesPerFrozenBlock':4,'sharedResourcePrefixColumns':nf,
            'sharedRowsPerBlock':common_rows,'sharedRowsDuplicated':len(blocks)>1,'annualMaterialCount':1},
        dimensions={'binaryTemplates':first.nx,'integerPhysicians':first.m,'flowVariables':flow_count,
            'variables':nv,'constraints':A.shape[0],'nonzeros':A.nnz,'conflicts':len(first.conflicts),'profiles':len(times)})
    return WindowProblem(**fields)
