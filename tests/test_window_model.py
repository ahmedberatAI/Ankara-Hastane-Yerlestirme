from copy import deepcopy
import numpy as np
import pytest
from test_joint_model import fixture,PROFILES
from backend.joint_model import build_joint_problem
from backend.window_model import build_window_problem


def window(count=12,budget=100,reference=20,swapped=False,sites_count=2):
    p,source,v,args=fixture(sites_count=sites_count);args=list(deepcopy(args))
    args[0]={f'actual-profile-{k}':(np.array([[1,np.inf],[np.inf,1]]) if k%2==0 else np.array([[np.inf,1],[1,np.inf]])) if swapped else np.ones((2,sites_count)) for k in range(count)}
    return build_window_problem(*args,annual_budget=budget,reference_annual_cost=reference),source,args


def test_four_profile_composition_bit_equal_except_new_budget_row():
    old,source,v,args=fixture();new=build_window_problem(*args,annual_budget=100)
    for k in range(4):assert np.array_equal(new.model[k],old.model[k])
    A=new.model[4][:-1]
    for key in ('data','indices','indptr'):assert np.array_equal(getattr(A,key),getattr(old.model[4],key))
    assert np.array_equal(new.model[5][:-1],old.model[5]) and np.array_equal(new.model[6][:-1],old.model[6])
    assert new.cost(v)==old.cost(v)==40 and new.material==10
    new.read_plan(source)


def test_twelve_profiles_block_projection_and_single_material_cost():
    p,source,args=window();nf=p.nf;items=list(args[0].items());r=0;f=nf
    for first in range(0,12,4):
        block=build_joint_problem(dict(items[first:first+4]),*args[1:]);nr=block.model[4].shape[0];flow=len(block.c)-nf
        indices=np.r_[np.arange(nf),np.arange(f,f+flow)]
        assert np.array_equal(p.model[4][r:r+nr][:,indices].toarray(),block.model[4].toarray())
        assert np.array_equal(p.model[5][r:r+nr],block.model[5])
        assert np.array_equal(p.model[6][r:r+nr],block.model[6])
        r+=nr;f+=flow
    assert p.material==10 and p.composition['annualMaterialCount']==1
    assert p.dimensions['profiles']==12 and p.nf==6
    v=p.fixed_resource_vector(source)
    assert p.cost(v)==40 and np.count_nonzero(v[p.nf:])==0
    with pytest.raises(ValueError):p.validate(v)


@pytest.mark.parametrize('count',[0,1,3,5,11])
def test_only_positive_four_profile_blocks(count):
    with pytest.raises(ValueError,match='multiple of four'):window(count)


@pytest.mark.parametrize('budget',[True,0,-1,float('nan'),float('inf')])
def test_invalid_budget_guards(budget):
    with pytest.raises(ValueError):window(budget=budget)


def test_reference_is_only_comparison_and_budget_is_actual_row():
    p,source,args=window(budget=40,reference=1);v=p.fixed_resource_vector(source)
    assert p.cost(v)==40 and p.reference_annual_cost==1
    assert p.model[4][p.budget_row_index]@v<=p.model[6][-1]+1e-12
    low,_,_=window(budget=39)
    with pytest.raises(ValueError):low.fixed_resource_vector(source)


@pytest.mark.parametrize('change',['beds','doctors','radius','material','annual','count'])
def test_old_resource_source_checked_without_claiming_old_flows_valid(change):
    p,source,args=window();source=deepcopy(source)
    if change=='beds':source['selected'][0]['beds']+=1
    elif change=='doctors':source['selected'][0]['doctors']+=1
    elif change=='radius':source['selected'][0]['footprintRadiusMeters']+=1
    elif change=='material':source['annualMaterialCostTRY']*=12
    elif change=='annual':source['annualEquivalentCostTRY']+=1
    else:source['totalDoctors']+=1
    with pytest.raises(ValueError):p.fixed_resource_vector(source)


def test_44_profile_dimensions_and_sparse_global_candidate_identity():
    p,source,args=window(count=44);args[5][0]['candidateIndex']=17;args[5][1]['candidateIndex']=100
    p=build_window_problem(*args,annual_budget=100)
    assert p.ids==[17,100] and len(p.times)==44 and p.dimensions['flowVariables']==44*4
    assert p.composition['blockCount']==11 and len(set(p.offsets.values()))==44


def test_last_block_preserves_geographic_check_and_target_not_relaxed():
    p,source,args=window();args[0][list(args[0])[-1]][0,:]=np.inf
    with pytest.raises(ValueError,match='geographic targets'):build_window_problem(*args,annual_budget=100)
