"""Evaluate one fixed facility/resource plan against alternative travel matrices.

Annual demand is not added across profiles. Each LP independently tests whether
the SAME buildings, beds and physicians could serve the stated annual demand if
access followed that time profile. This is a scenario stress test, not a patient
arrival simulation and not a re-optimization of hospital locations.
"""
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, vstack
from backend.capacity import annualization


def fixed_plan_costs(selected_sites, planning, scenario):
    """Reconstruct fixed annual costs; materials depend on reassigned demand.

    No original assigned load is reused: buildings, staff and beds stay fixed,
    while materials are priced against each profile's newly served population.
    """
    eco = planning['economics']
    multiplier = scenario.get('operatingCostMultiplier', 1.)
    area = sum(s['grossAreaM2'] for s in selected_sites)
    fixed = area * eco['buildingUnitCostTRY'] * annualization(planning)
    fixed += multiplier * sum(eco['annualFixedSiteCostTRY'] +
        s['doctors'] * eco['annualDoctorCostTRY'] +
        s['beds'] * eco['annualBedSupportCostTRY'] for s in selected_sites)
    variable = (eco['costPerContactTRY'] * planning['rates']['contactsPerResident'] *
                scenario['demandMultiplier'] * multiplier)
    if not np.isfinite([fixed, variable]).all() or fixed < 0 or variable < 0:
        raise ValueError('Invalid annual cost calibration')
    return float(fixed), float(variable)


def evaluate_fixed_plan(times, populations, demand_districts, districts,
                        province_total, selected_sites, planning, scenario,
                        time_limit=30, annual_budget=None):
    """Maximize assigned resident-equivalents with fixed beds and physicians.

    ``times`` contains every demand row and exactly the selected-site columns,
    in ``selected_sites`` order. No nearest-neighbor pruning is performed.
    Physician and bed-day capacities remain two separate constraint families.
    When supplied, annual_budget also limits the reconstructed annual cost;
    the source plan's reference budget is not recalculated for another profile.
    """
    times = np.asarray(times, dtype=float)
    populations = np.asarray(populations, dtype=float)
    demand_districts = np.asarray(demand_districts)
    n, m = times.shape
    if n != len(populations) or n != len(demand_districts) or m != len(selected_sites):
        raise ValueError('Fixed-plan matrix and index sizes differ')
    if province_total <= 0 or np.any(~np.isfinite(populations)) or np.any(populations < 0):
        raise ValueError('Invalid population denominator')
    if np.any(np.isnan(times)) or np.any(times < 0):
        raise ValueError('Travel times must be non-negative or positive infinity')
    district_ids = {d['id'] for d in districts}
    if len(district_ids) != len(districts) or not set(demand_districts).issubset(district_ids):
        raise ValueError('District identities do not match the demand index')
    if any(d['population'] <= 0 for d in districts):
        raise ValueError('District denominators must be positive')
    rates = planning['rates']
    contacts = rates['contactsPerResident'] * scenario['demandMultiplier']
    bed_days = rates['bedDaysPerResident'] * scenario['demandMultiplier']
    if contacts <= 0 or bed_days <= 0:
        raise ValueError('Demand resource rates must be positive')
    beds = np.array([s['beds'] for s in selected_sites], dtype=float)
    doctors = np.array([s['doctors'] for s in selected_sites], dtype=float)
    if np.any(~np.isfinite(beds)) or np.any(~np.isfinite(doctors)) or np.any(beds < 0) or np.any(doctors < 0):
        raise ValueError('Invalid fixed resources')
    if np.any(beds != np.rint(beds)) or np.any(doctors != np.rint(doctors)):
        raise ValueError('Fixed resources must be integer counts')
    doctor_capacity = doctors * scenario['contactsPerDoctor']
    bed_capacity = beds * 365 * scenario['bedOccupancy'] / 100
    within = np.isfinite(times) & (times <= scenario['threshold'])
    origin, dest = np.where(within)
    e = len(origin)
    base = {
        'thresholdMinutes': scenario['threshold'],
        'coverageTargetPercent': scenario['coverageTarget'],
        'districtFloorPercent': scenario['districtFloor'],
        'fixedHospitalCount': m, 'fixedBeds': int(beds.sum()),
        'fixedDoctors': int(doctors.sum()), 'allocationEdges': e,
        'allSelectedSiteEdges': True,
        'scope': 'Fixed sites, beds and physicians; each time profile is evaluated independently. Annual demand is not summed across profiles.',
    }
    fixed_cost = variable_cost = None
    base['annualBudget'] = {'enforced': annual_budget is not None,
        'limitTRY': annual_budget, 'fixedCostTRY': None, 'variableCostPerResidentTRY': None,
        'scope': 'Equivalent annual cost in the original price base; the partial cost calibration is unchanged.'}
    if annual_budget is not None:
        if not np.isfinite(annual_budget) or annual_budget < 0:
            raise ValueError('Annual budget must be finite and non-negative')
        fixed_cost, variable_cost = fixed_plan_costs(selected_sites, planning, scenario)
        base['annualBudget'].update(fixedCostTRY=fixed_cost, variableCostPerResidentTRY=variable_cost)
        if fixed_cost > annual_budget + .01:
            return {**base, 'status': 'fixed_cost_exceeds_budget', 'targetsMet': False,
                'maximumCoveragePercent': None, 'districtTargetsFeasible': None,
                'reason': 'The fixed buildings, beds and physicians alone exceed the original annual budget.'}
    possible = within.any(axis=1)
    base['geographicDistrictCeilings'] = [
        {'id': d['id'], 'name': d.get('name', d['id']),
         'maximumPercent': float(populations[(demand_districts == d['id']) & possible].sum() / d['population'] * 100)}
        for d in districts
    ]
    # Flows use thousands of resident-equivalents. Resource rows are scaled to
    # their respective resident-equivalent capacity, but remain separate rows.
    edge = np.arange(e)
    A = coo_matrix((np.ones(e * 3),
                   (np.r_[origin, n + dest, n + m + dest], np.tile(edge, 3))),
                  shape=(n + 2 * m, e)).tocsr()
    b = np.r_[populations / 1000, doctor_capacity / contacts / 1000,
              bed_capacity / bed_days / 1000]
    if annual_budget is not None and variable_cost > 0:
        # Scale to thousands of residents like other rows, avoiding TRY-scale
        # coefficients. This limits materials after every profile reallocation.
        A = vstack([A, coo_matrix((np.ones(e), (np.zeros(e, dtype=int), edge)),
                                  shape=(1, e))], format='csr')
        b = np.r_[b, max(0., annual_budget - fixed_cost) / variable_cost / 1000]
    di = {d['id']: i for i, d in enumerate(districts)}
    edge_district = np.array([di[d] for d in demand_districts[origin]], dtype=int)
    district_A = coo_matrix((-np.ones(e), (edge_district, edge)),
                           shape=(len(districts), e)).tocsr()
    district_quota = np.array([d['population'] * scenario['districtFloor'] / 100 / 1000 for d in districts])
    full_A = vstack([A, district_A], format='csr')
    full_b = np.r_[b, -district_quota]

    def solve(include_floors):
        if not e:
            # scipy.linprog does not accept a zero-column LP.
            return None
        return linprog(-np.ones(e), A_ub=full_A if include_floors else A,
                       b_ub=full_b if include_floors else b, bounds=(0, None),
                       method='highs', options={'time_limit': time_limit})

    def summarize(solution):
        flow = np.maximum(solution, 0) * 1000
        served = np.bincount(origin, weights=flow, minlength=n)
        load = np.bincount(dest, weights=flow, minlength=m)
        if np.any(served > populations + .001):
            raise RuntimeError('Fixed-plan LP duplicates population')
        if np.any(load * contacts > doctor_capacity + .1) or np.any(load * bed_days > bed_capacity + .1):
            raise RuntimeError('Fixed-plan LP exceeds a resource')
        total = float(served.sum())
        annual_cost = fixed_cost + total * variable_cost if annual_budget is not None else None
        if annual_cost is not None and annual_cost > annual_budget + max(.01, variable_cost * .001):
            raise RuntimeError('Fixed-plan LP exceeds the original annual budget')
        return {
            'maximumCoveredPopulation': total,
            'maximumCoveragePercent': total / province_total * 100,
            'populationShortfall': max(0., province_total * scenario['coverageTarget'] / 100 - total),
            'districts': [
                {'id': d['id'], 'name': d.get('name', d['id']),
                 'coveredPopulation': float(served[demand_districts == d['id']].sum()),
                 'coveragePercent': float(served[demand_districts == d['id']].sum() / d['population'] * 100)}
                for d in districts
            ],
            'annualContactsServed': total * contacts,
            'annualBedDaysServed': total * bed_days,
            'annualEquivalentCostTRY': annual_cost,
        }

    result = solve(True)
    no_edge_floor_failure = not e and np.any(district_quota > 0)
    if no_edge_floor_failure or (result is not None and result.status == 2):
        # The maximum below intentionally drops district floors. It must never
        # be presented as a feasible plan satisfying those floors.
        diagnostic = solve(False)
        unconstrained = summarize(np.zeros(e)) if not e else (summarize(diagnostic.x) if diagnostic.success else None)
        return {**base, 'status': 'district_targets_infeasible', 'targetsMet': False,
                'maximumCoveragePercent': None, 'districtTargetsFeasible': False,
                'withoutDistrictTargets': unconstrained,
                'reason': 'Fixed sites/resources and any enforced annual budget cannot simultaneously meet the district floors. The optional diagnostic removes only those floors.'}
    if result is not None and not result.success:
        return {**base, 'status': 'inconclusive', 'targetsMet': None,
                'districtTargetsFeasible': None, 'maximumCoveragePercent': None,
                'solverStatus': int(result.status), 'reason': result.message}
    summary = summarize(np.zeros(e) if result is None else result.x)
    if any(d['coveragePercent'] < scenario['districtFloor'] - 1e-6 for d in summary['districts']):
        raise RuntimeError('Fixed-plan LP violates a district floor')
    met = summary['maximumCoveragePercent'] >= scenario['coverageTarget'] - 1e-6
    return {**base, **summary, 'status': 'targets_met' if met else 'province_target_not_met',
            'targetsMet': met, 'districtTargetsFeasible': True}
