"""Necessary geographical site-count bound using ALL candidates and all edges.

Capacity, footprint conflicts and cost are deliberately relaxed. A count lower
bound above 91 therefore also rules out 91 in the stricter capacitated model.
The reverse implication is not valid. Dominance is exact for THIS relaxation.
"""
import numpy as np
from scipy.optimize import Bounds
from scipy.sparse import csr_matrix, eye, hstack, vstack
from backend.capacity import optimize
from backend.optimizer import undominated_columns


def geographic_bound(times,populations,demand_districts,districts,province_total,
                     threshold,coverage_target,district_floor,time_limit=20):
    within=np.isfinite(times)&(times<=threshold)
    keep=undominated_columns(within)
    n,m=within.shape[0],len(keep)
    constraints=[hstack([-csr_matrix(within[:,keep],dtype=float),eye(n,format='csr')],format='csr')]
    lower=[-np.inf]*n; upper=[0.]*n
    constraints.append(csr_matrix(np.r_[np.zeros(m),populations/province_total].reshape(1,-1)))
    lower.append(coverage_target); upper.append(np.inf)
    for d in districts:
        weights=np.where(demand_districts==d['id'],populations/d['population'],0.)
        constraints.append(csr_matrix(np.r_[np.zeros(m),weights].reshape(1,-1)))
        lower.append(district_floor); upper.append(np.inf)
    result=optimize(np.r_[np.ones(m),np.zeros(n)],np.r_[np.ones(m),np.zeros(n)],
                    Bounds(np.zeros(m+n),np.ones(m+n)),vstack(constraints,format='csc'),lower,upper,time_limit)
    bound=result.mip_dual_bound
    return {'status':'infeasible' if result.status==2 else ('optimal' if result.status==0 and result.mip_gap<=1e-8 else 'bounded'),
        'minimumCountLowerBound':float(bound) if np.isfinite(bound) else None,
        'feasibleGeographicCount':int(np.rint(result.x[:m]).sum()) if result.x is not None else None,
        'fullCandidateCount':times.shape[1],'undominatedCandidateCount':m,
        'scope':'Tüm adaylar ve süre içindeki tüm bağlantılar; kapasite, maliyet ve yapı-izi çakışması gevşetildi. Sadece gerekli koşul.',
        'thresholdMinutes':threshold,'coverageTargetPercent':coverage_target*100,'districtFloorPercent':district_floor*100}
