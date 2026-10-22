"""Experimental capacity repair at mandatory, FIXED hospital locations.

Bed modules and integer physician counts are shared by all profiles. Flows are
profile-specific; annual demand/materials are counted once, never summed across
profiles. This does not optimize locations, hospital count or travel time.
"""
import math
import numpy as np
from scipy.optimize import Bounds
from scipy.sparse import coo_matrix
from backend.capacity import annualization, optimize


SCOPE = ('Fixed mandatory sites; shared bed modules and integer physicians; '
         'all threshold-feasible edges and separate flows in every profile. '
         'Partial clinical/cost calibration; not a location/count optimum, '
         'clinical staffing standard or continuous-time service guarantee.')
BOUND_SCOPE = 'shared_resources_at_fixed_mandatory_sites_all_allocation_edges'
# Square metres, used only for floating-point eligibility/bounds and the final
# physical check. The MILP area row itself retains the nominal physical limit.
AREA_NUMERICAL_TOLERANCE_M2 = .001


def repair_shared_capacity(profile_times, populations, demand_districts, districts,
                           province_total, selected_sites, planning, scenario,
                           original_annual_budget=None, time_limit=60):
    """Minimize annual resource cost, then compare with the ORIGINAL budget.

    Every profile serves exactly coverageTarget * province_total residents'
    annual demand. Thus the variable material bill is identical and included
    exactly once. The budget is a post-solve comparison, not a relaxed target.
    No saved data or application state is changed by this function.
    """
    def number(value, name, minimum=0., maximum=np.inf, positive=False):
        if isinstance(value, (bool, np.bool_)):
            raise ValueError(f'{name} must be numeric')
        try:
            value = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'{name} must be numeric') from exc
        if not np.isfinite(value) or value < minimum or value > maximum or (positive and value <= 0):
            raise ValueError(f'Invalid {name}')
        return value

    total = number(province_total, 'province total', positive=True)
    time_limit = number(time_limit, 'time limit', positive=True)
    if not isinstance(profile_times, dict) or not profile_times:
        raise ValueError('At least one named profile is required')
    if any(not isinstance(key, str) or not key for key in profile_times):
        raise ValueError('Profile names must be nonempty strings')
    pop = np.asarray(populations, dtype=float)
    dd = np.asarray(demand_districts)
    if pop.ndim != 1 or dd.shape != pop.shape or not len(pop):
        raise ValueError('Demand vectors must be nonempty and match')
    if np.any(~np.isfinite(pop)) or np.any(pop < 0) or pop.sum() > total + 1e-6:
        raise ValueError('Invalid population or province denominator')
    if not selected_sites or not districts:
        raise ValueError('Fixed sites and districts must be nonempty')
    district_ids = [d['id'] for d in districts]
    if len(set(district_ids)) != len(district_ids) or not set(dd).issubset(district_ids):
        raise ValueError('District identities must be unique and cover demand')
    district_pop = np.array([number(d['population'], 'district population', positive=True) for d in districts])
    if not np.isclose(district_pop.sum(), total, atol=1e-6, rtol=1e-10):
        raise ValueError('District denominators must sum to province population')
    for d, denom in zip(districts, district_pop):
        if pop[dd == d['id']].sum() > denom + 1e-6:
            raise ValueError('Located district population exceeds its denominator')
    site_ids = [s['candidateIndex'] for s in selected_sites]
    if any(isinstance(i, (bool, np.bool_)) or not isinstance(i, (int, np.integer)) or i < 0 for i in site_ids):
        raise ValueError('Candidate indices must be nonnegative integers')
    if len(set(site_ids)) != len(site_ids):
        raise ValueError('Fixed sites must be unique')
    threshold = number(scenario['threshold'], 'threshold', positive=True)
    target_fraction = number(scenario['coverageTarget'], 'coverage target', maximum=100) / 100
    floor = number(scenario['districtFloor'], 'district floor', maximum=100) / 100
    occupancy = number(scenario['bedOccupancy'], 'bed occupancy', maximum=100, positive=True) / 100
    demand_multiplier = number(scenario['demandMultiplier'], 'demand multiplier', positive=True)
    throughput = number(scenario['contactsPerDoctor'], 'contacts per physician', positive=True)
    operating = number(scenario.get('operatingCostMultiplier', 1), 'operating multiplier', positive=True)
    if original_annual_budget is not None:
        original_annual_budget = number(original_annual_budget, 'original annual budget')
    rates, design, eco = planning['rates'], planning['design'], planning['economics']
    contact_rate = number(rates['contactsPerResident'], 'contact rate', positive=True) * demand_multiplier
    bed_rate = number(rates['bedDaysPerResident'], 'bed-day rate', positive=True) * demand_multiplier
    doctor_area = number(design['areaPerDoctorM2'], 'physician area', positive=True)
    floors = number(design['maxFloors'], 'maximum floors', positive=True)
    minimum_docs = number(design['minimumDoctorsPerSite'], 'minimum physicians', positive=True)
    if minimum_docs != round(minimum_docs):
        raise ValueError('Minimum physicians must be an integer')
    number(eco['realDiscountRate'], 'discount rate')
    number(eco['horizonYears'], 'horizon', positive=True)
    for field in ('buildingUnitCostTRY', 'annualFixedSiteCostTRY', 'annualDoctorCostTRY',
                  'annualBedSupportCostTRY', 'costPerContactTRY'):
        number(eco[field], field)
    templates = planning['templates']
    if not templates or len({t['id'] for t in templates}) != len(templates):
        raise ValueError('Bed templates must be nonempty and unique')
    beds = np.array([number(t['beds'], 'template beds', positive=True) for t in templates])
    if np.any(beds != np.rint(beds)):
        raise ValueError('Template bed counts must be integers')
    area = np.array([number(t['grossAreaM2'], 'template area', positive=True) for t in templates])
    radii = np.array([number(s['footprintRadiusMeters'], 'footprint radius', positive=True) for s in selected_sites])
    available = math.pi * radii ** 2 * floors
    n, m, k = len(pop), len(selected_sites), len(templates)
    target = total * target_fraction
    base = {'scope': SCOPE, 'hospitalCount': m, 'allSitesMandatoryOpen': True,
            'allSelectedSiteEdges': True, 'profileNames': list(profile_times),
            'servedPopulationPerProfile': target, 'coverageTargetPercent': target_fraction * 100,
            'districtFloorPercent': floor * 100, 'thresholdMinutes': threshold,
            'planningVersion': planning.get('version'), 'timeLimitSeconds': time_limit,
            'originalAnnualBudgetTRY': original_annual_budget,
            'budgetIsOptimizationConstraint': False,
            'annualDemandCountedOnce': True,
            'boundScope': BOUND_SCOPE}

    def failure(status, reason, **extra):
        return {**base, 'status': status, 'reason': reason, 'selected': [], 'profiles': [],
                'provenOptimal': False, 'incumbentValidated': False, 'timeLimitedFeasible': False,
                'budgetStatus': 'targets_infeasible' if status == 'infeasible' else 'inconclusive',
                'meetsOriginalBudget': False if status == 'infeasible' else None, **extra}

    matrices, profile_edges = {}, {}
    for name, raw in profile_times.items():
        t = np.asarray(raw, dtype=float)
        if t.shape != (n, m) or np.any(np.isnan(t)) or np.any(t < 0):
            raise ValueError('Profile matrix shape or travel values invalid')
        matrices[name] = t
        origin, dest = np.where(np.isfinite(t) & (t <= threshold))
        profile_edges[name] = (origin, dest)
    if target > pop.sum() + 1e-6 or target < district_pop.sum() * floor - 1e-6:
        return failure('infeasible', 'Exact provincial service total conflicts with available population or district floors.')
    eligible = area[None, :] + minimum_docs * doctor_area <= available[:, None] + AREA_NUMERICAL_TOLERANCE_M2
    if not np.all(eligible.any(axis=1)):
        return failure('infeasible', 'A mandatory site cannot fit any bed module and minimum physician staff.')
    for name, t in matrices.items():
        reachable = (np.isfinite(t) & (t <= threshold)).any(axis=1)
        if pop[reachable].sum() < target - 1e-6 or any(
                pop[reachable & (dd == d['id'])].sum() < denom * floor - 1e-6
                for d, denom in zip(districts, district_pop)):
            return failure('infeasible', f'Fixed-site geographic ceiling fails in profile {name}.')

    nx, nf = m * k, m * k + m
    offsets, nv = {}, nf
    for name, (origin, dest) in profile_edges.items():
        offsets[name] = nv
        nv += len(origin)
    max_docs = np.floor(np.nextafter(
        (available + AREA_NUMERICAL_TOLERANCE_M2 - area.min()) / doctor_area, np.inf))
    # No profile serves more than target; extra staff beyond all that workload
    # cannot improve feasibility or nonnegative costs at a mandatory site.
    max_docs = np.minimum(max_docs, max(minimum_docs, math.ceil(target * contact_rate / throughput)))
    crf = annualization(planning)
    module_cost = area * eco['buildingUnitCostTRY'] * crf + operating * (
        eco['annualFixedSiteCostTRY'] + beds * eco['annualBedSupportCostTRY'])
    physician_cost = doctor_area * eco['buildingUnitCostTRY'] * crf + operating * eco['annualDoctorCostTRY']
    material_cost = target * contact_rate * eco['costPerContactTRY'] * operating
    cost_scale = max(1., float(module_cost.max()), float(physician_cost))
    objective = np.r_[np.tile(module_cost, m), np.full(m, physician_cost), np.zeros(nv - nf)] / cost_scale
    integrality = np.r_[np.ones(nf), np.zeros(nv - nf)]
    lower_bounds = np.r_[np.zeros(nx), np.full(m, minimum_docs), np.zeros(nv - nf)]
    upper_bounds = np.r_[eligible.ravel().astype(float), max_docs,
                         np.concatenate([pop[o] / 1000 for o, _ in profile_edges.values()])]
    rows, cols, vals, lower, upper = [], [], [], [], []

    def row(indices, values, lo=-np.inf, hi=np.inf):
        rows.extend([len(lower)] * len(indices)); cols.extend(indices); vals.extend(values)
        lower.append(lo); upper.append(hi)

    for j in range(m):
        xs = j * k + np.arange(k)
        row(xs, np.ones(k), 1., 1.)
        # Divide by doctor area for moderate coefficients, retaining physical fit.
        row(np.r_[xs, nx + j], np.r_[area / doctor_area, 1.], hi=available[j] / doctor_area)
    for name, (origin, dest) in profile_edges.items():
        fs = offsets[name] + np.arange(len(origin))
        for i in range(n):
            es = np.flatnonzero(origin == i)
            row(fs[es], np.ones(len(es)), hi=pop[i] / 1000)
        for j in range(m):
            es = np.flatnonzero(dest == j)
            row(np.r_[j * k + np.arange(k), fs[es]],
                np.r_[-beds * 365 * occupancy / bed_rate / 1000, np.ones(len(es))], hi=0.)
            row(np.r_[nx + j, fs[es]],
                np.r_[-throughput / contact_rate / 1000, np.ones(len(es))], hi=0.)
        row(fs, np.ones(len(fs)), target / 1000, target / 1000)
        for d, denom in zip(districts, district_pop):
            es = np.flatnonzero(dd[origin] == d['id'])
            row(fs[es], np.ones(len(es)), lo=denom * floor / 1000)
    A = coo_matrix((vals, (rows, cols)), shape=(len(lower), nv)).tocsc()
    lower, upper = np.asarray(lower), np.asarray(upper)
    bounds = Bounds(lower_bounds, upper_bounds)
    result = optimize(objective, integrality, bounds, A, lower, upper, time_limit)
    raw_bound = result.mip_dual_bound
    bound = float(raw_bound * cost_scale + material_cost) if np.isfinite(raw_bound) else None
    base.update(allocationEdgesByProfile={name: len(es[0]) for name, es in profile_edges.items()},
                solverStatus=int(result.status), solverReportedGap=float(result.mip_gap) if np.isfinite(result.mip_gap) else None,
                minimumAnnualCostLowerBoundTRY=bound)
    if result.status == 2:
        return failure('infeasible', 'The shared-resource MILP proved these fixed sites cannot meet all targets.')
    if result.x is None:
        return failure('inconclusive', 'Solver returned no validated feasible incumbent; no infeasibility claim.')
    raw = np.asarray(result.x)
    if raw.shape != (nv,) or np.any(~np.isfinite(raw)):
        return failure('inconclusive', 'Solver incumbent contains invalid numeric values.')
    if np.max(np.abs(raw[:nf] - np.rint(raw[:nf]))) > 1e-5 or np.min(raw[nf:], initial=0) < -1e-9:
        return failure('inconclusive', 'Solver incumbent violates integer/nonnegative-flow tolerances.')
    accepted = raw.copy()
    accepted[:nf] = np.rint(accepted[:nf])
    accepted[nf:] = np.maximum(accepted[nf:], 0)
    activity = A @ accepted
    if (np.any(accepted < lower_bounds - 1e-8) or np.any(accepted > upper_bounds + 1e-8)
            or np.any(activity < lower - 1e-7) or np.any(activity > upper + 1e-7)):
        return failure('inconclusive', 'Rounded incumbent failed independent model constraint validation.')
    chosen = np.argmax(accepted[:nx].reshape(m, k), axis=1)
    docs = accepted[nx:nf].astype(int)
    selected = []
    for j, typ in enumerate(chosen):
        gross = float(area[typ] + docs[j] * doctor_area)
        if gross > available[j] + AREA_NUMERICAL_TOLERANCE_M2:
            return failure('inconclusive', 'Physical area verification failed.')
        selected.append({'candidateIndex': int(site_ids[j]), 'id': selected_sites[j].get('id'),
                         'templateId': templates[typ]['id'], 'beds': int(beds[typ]),
                         'doctors': int(docs[j]), 'grossAreaM2': gross,
                         'footprintRadiusMeters': float(radii[j])})
    cost = float(objective @ accepted * cost_scale + material_cost)
    cost_tolerance = max(.01, abs(cost) * 1e-9)
    if bound is not None and bound > cost + cost_tolerance:
        raise RuntimeError('Shared-model cost lower bound exceeds validated feasible cost')
    gap = max(0., (cost - bound) / cost) if bound is not None and cost > 0 else (0. if bound == cost == 0 else None)
    profiles = []
    for name, (origin, dest) in profile_edges.items():
        flow = accepted[offsets[name]:offsets[name] + len(origin)] * 1000
        served = np.bincount(origin, weights=flow, minlength=n)
        loads = np.bincount(dest, weights=flow, minlength=m)
        if (np.any(served > pop + .001) or abs(served.sum() - target) > .001
                or np.any(loads * contact_rate > docs * throughput + .1)
                or np.any(loads * bed_rate > beds[chosen] * 365 * occupancy + .1)):
            return failure('inconclusive', 'Physical-unit flow/resource verification failed.')
        district_summary = [{'id': d['id'], 'coveragePercent': float(served[dd == d['id']].sum() / denom * 100)}
                            for d, denom in zip(districts, district_pop)]
        if any(d['coveragePercent'] < floor * 100 - 1e-6 for d in district_summary):
            return failure('inconclusive', 'Physical-unit district verification failed.')
        profiles.append({'profile': name, 'coveredPopulation': float(served.sum()),
                         'coveragePercent': float(served.sum() / total * 100),
                         'meanMinutes': float(flow @ matrices[name][origin, dest] / target) if target else None,
                         'districts': district_summary, 'siteLoads': loads.tolist(),
                         'allocations': [{'demandIndex': int(i), 'candidateIndex': int(site_ids[j]),
                                          'population': float(v), 'minutes': float(matrices[name][i, j])}
                                         for i, j, v in zip(origin, dest, flow) if v > 0]})
    met_budget = None if original_annual_budget is None else cost <= original_annual_budget + cost_tolerance
    if original_annual_budget is None:
        budget_status = 'not_requested'
    elif met_budget:
        budget_status = 'feasible_within_original_budget'
    elif bound is not None and bound > original_annual_budget + cost_tolerance:
        budget_status = 'proven_over_original_budget_for_fixed_sites'
    else:
        budget_status = 'incumbent_over_budget_unresolved'
    return {**base, 'status': 'feasible', 'selected': selected, 'profiles': profiles,
            'totalBeds': sum(s['beds'] for s in selected), 'totalDoctors': int(docs.sum()),
            'annualEquivalentCostTRY': cost, 'annualMaterialCostTRY': material_cost,
            'annualFixedResourceCostTRY': cost - material_cost,
            'costGap': gap, 'provenOptimal': gap is not None and gap <= 1e-8,
            'timeLimitedFeasible': result.status == 1,
            'budgetStatus': budget_status, 'meetsOriginalBudget': met_budget,
            'costNumericalToleranceTRY': cost_tolerance,
            'numericFlowCorrectionResidents': float(np.abs(raw[nf:] - accepted[nf:]).sum() * 1000),
            'incumbentValidated': True}
