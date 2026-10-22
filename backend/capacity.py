"""Capacitated, splittable location-allocation with a cost/time epsilon constraint.

Flows are thousands of residents' annual demand, not a count of unique patients.
Two independent resource constraints apply at every site: visits and bed-days.
"""
import numpy as np
import highspy
from types import SimpleNamespace
from time import monotonic
from scipy.optimize import Bounds
from scipy.sparse import coo_matrix, csr_matrix, vstack
from backend.optimizer import weighted_quantile


def optimize(objective, integrality, bounds, A, lower, upper, time_limit, seed=None):
    """Use the native HiGHS API so a checked incumbent survives time limits."""
    A = A.tocsc()
    lp = highspy.HighsLp()
    lp.num_col_, lp.num_row_ = A.shape[1], A.shape[0]
    lp.col_cost_ = objective
    lp.col_lower_, lp.col_upper_ = bounds.lb, bounds.ub
    lp.row_lower_, lp.row_upper_ = lower, upper
    lp.a_matrix_.start_, lp.a_matrix_.index_, lp.a_matrix_.value_ = A.indptr, A.indices, A.data
    if np.any(integrality):
        lp.integrality_ = [highspy.HighsVarType.kInteger if i else highspy.HighsVarType.kContinuous for i in integrality]
    solver = highspy.Highs()
    solver.setOptionValue('output_flag', False)
    solver.setOptionValue('threads', 1)
    solver.setOptionValue('random_seed', 7)
    solver.setOptionValue('time_limit', time_limit)
    solver.setOptionValue('mip_rel_gap', .01)
    solver.passModel(lp)
    if seed is not None:
        supplied = highspy.HighsSolution()
        supplied.col_value = seed
        solver.setSolution(supplied)
    solver.run()
    info, solution, status = solver.getInfo(), solver.getSolution(), solver.getModelStatus()
    valid = info.primal_solution_status == highspy.SolutionStatus.kSolutionStatusFeasible
    return SimpleNamespace(x=np.array(solution.col_value) if valid else None,
        status=0 if status == highspy.HighsModelStatus.kOptimal else (2 if status == highspy.HighsModelStatus.kInfeasible else 1),
        mip_gap=info.mip_gap, mip_dual_bound=info.mip_dual_bound)


def greedy_seed(origin, local_dest, edge_times, populations, demand_districts, districts,
                province_total, coverage_target, district_floor, capacities, costs, h, conflicts):
    """Build an integer incumbent by incremental capacity/cost, then validate it.

    First satisfy district quotas, then the provincial quota. Upgrading an open
    site pays only its incremental cost; spare capacity is used before opening.
    This supplies a start, never an optimality claim or a replacement lower bound.
    """
    k, e = len(costs), len(origin)
    district_index = {d['id']: i for i, d in enumerate(districts)}
    di = np.array([district_index[d] for d in demand_districts])
    remaining = populations / 1000
    quota = np.array([d['population'] * district_floor / 1000 for d in districts])
    allocation = np.zeros(e)
    chosen = np.full(h, -1, dtype=int)
    loads = np.zeros(h)
    edges = [np.flatnonzero(local_dest == j) for j in range(h)]
    edges = [es[np.argsort(edge_times[es], kind='stable')] for es in edges]
    capacity = np.r_[0., capacities]
    cost = np.r_[0., costs]
    for phase in (0, 1):
        for _ in range(h * (k + 1) + 1):
            total_need = max(0., province_total * coverage_target / 1000 - allocation.sum())
            if (phase == 0 and quota.max() < 1e-7) or (phase == 1 and total_need < 1e-7):
                break
            best = None
            for j, es in enumerate(edges):
                if chosen[j] < 0 and any(chosen[v] >= 0 for v in conflicts.get(j, ())):
                    continue
                residents = origin[es]
                if phase == 0:
                    available = float(np.minimum(np.bincount(di[residents], weights=remaining[residents],
                                                              minlength=len(districts)), np.maximum(quota, 0)).sum())
                else:
                    available = min(float(remaining[residents].sum()), total_need)
                if available < 1e-7:
                    continue
                old = chosen[j] + 1
                for typ in range(max(1, old), k + 1):
                    amount = min(available, capacity[typ] - loads[j])
                    if amount < 1e-7:
                        continue
                    extra = cost[typ] - cost[old]
                    score = amount / max(extra, 1e-12)
                    if best is None or score > best[0]:
                        best = (score, j, typ - 1, amount)
            if best is None:
                return None
            _, j, typ, amount = best
            chosen[j] = typ
            for edge in edges[j]:
                i = origin[edge]
                take = min(amount, remaining[i], max(0, quota[di[i]]) if phase == 0 else amount)
                if take > 0:
                    allocation[edge] += take; remaining[i] -= take; loads[j] += take
                    quota[di[i]] -= take; amount -= take
                if amount < 1e-8:
                    break
        else:
            return None
    seed = np.zeros(h * k + e)
    for j, typ in enumerate(chosen):
        if typ >= 0:
            seed[j * k + typ] = 1
    seed[h * k:] = allocation
    return seed


def improve_travel_seed(first, travel_obj, bounds, A, lower, upper, objective,
                        nx, k, origin, dest, local_dest, edge_times, budget, capacities, time_limit):
    """Reallocate fixed sites, then try affordable capacity additions as MIP starts.

    Every proposed addition is accepted only after an LP verifies all constraints
    and actual travel improves. The final MILP can change any site/size again.
    """
    started = monotonic()
    best = first.copy()
    fixed = Bounds(np.r_[np.rint(best[:nx]), bounds.lb[nx:]], np.r_[np.rint(best[:nx]), bounds.ub[nx:]])
    allocation = optimize(travel_obj, np.zeros(len(best)), fixed, A, lower, upper, min(5, time_limit))
    if allocation.x is not None and travel_obj @ allocation.x < travel_obj @ best:
        best = allocation.x
    edges = [np.flatnonzero(local_dest == j) for j in range(nx // k)]
    tried = set()
    while monotonic() - started < time_limit:
        resident = np.bincount(origin, weights=best[nx:])
        total_time = np.bincount(origin, weights=best[nx:] * edge_times, minlength=len(resident))
        mean = np.divide(total_time, resident, out=np.zeros_like(total_time), where=resident > 1e-9)
        current_cost = objective @ best
        x = np.rint(best[:nx]).reshape(-1, k)
        choices = []
        for j, es in enumerate(edges):
            old = int(np.argmax(x[j])) if x[j].sum() > .5 else -1
            gains = np.maximum(mean[origin[es]] - edge_times[es], 0)
            order = np.argsort(-gains)
            for typ in range(old + 1, k):
                if (j, typ) in tried:
                    continue
                extra = objective[j*k+typ] - (objective[j*k+old] if old >= 0 else 0)
                if extra > budget - current_cost + 1e-8:
                    continue
                remaining_capacity = capacities[typ] - (capacities[old] if old >= 0 else 0)
                benefit = 0.
                for a in order:
                    take = min(remaining_capacity, resident[origin[es[a]]])
                    benefit += take * gains[a]
                    remaining_capacity -= take
                    if remaining_capacity < 1e-9:
                        break
                if benefit > 1e-8:
                    choices.append((benefit / extra, j, typ))
        if not choices:
            break
        _, j, typ = max(choices)
        tried.add((j, typ))
        proposed = best[:nx].copy()
        proposed[j*k:(j+1)*k] = 0; proposed[j*k+typ] = 1
        fixed = Bounds(np.r_[proposed, bounds.lb[nx:]], np.r_[proposed, bounds.ub[nx:]])
        candidate = optimize(travel_obj, np.zeros(len(best)), fixed, A, lower, upper, min(3, time_limit))
        if candidate.x is not None and travel_obj @ candidate.x < travel_obj @ best - 1e-7:
            best = candidate.x
    return best


def solve_capacity(times, populations, demand_districts, districts, province_total,
                   planning, threshold=30, coverage_target=.95, district_floor=.8,
                   demand_multiplier=1., bed_occupancy=.8, visits_per_doctor=4000,
                   cost_tolerance=.1, time_limit=35, neighbors=16, conflicts=()):
    populations = np.asarray(populations, dtype=float)
    n, m = times.shape
    within = np.isfinite(times) & (times <= threshold)
    possible = within.any(axis=1)
    upper = float(populations[possible].sum() / province_total)
    ceilings = [{'id': d['id'], 'name': d['name'], 'maximumPercent':
                 100 * float(populations[(demand_districts == d['id']) & possible].sum()) / d['population']}
                for d in districts]
    limiting = [d for d in ceilings if d['maximumPercent'] + 1e-7 < 100 * district_floor]
    if upper + 1e-9 < coverage_target or limiting or not n or not m:
        return {'status': 'infeasible', 'reason': 'Yol ağı ve süre sınırı erişim hedefini karşılamıyor.',
                'maximumCoveragePercent': upper * 100, 'limitingDistricts': limiting}

    # No set-cover dominance pruning: a geographically dominated site still
    # supplies additional capacity and can be essential in a dense neighborhood.
    origin, dest = [], []
    for i in range(n):
        choices = np.flatnonzero(within[i])
        choices = choices[np.argsort(times[i, choices], kind='stable')[:neighbors]]
        origin.extend([i] * len(choices))
        dest.extend(choices.tolist())
    origin, dest = np.array(origin, dtype=int), np.array(dest, dtype=int)
    sites = np.unique(dest)
    site_lookup = {int(j): k for k, j in enumerate(sites)}
    local_dest = np.array([site_lookup[int(j)] for j in dest])
    templates = planning['templates']
    k, h, e = len(templates), len(sites), len(origin)
    nx, nv = h * k, h * k + e
    visits_rate = planning['rates']['visitsPerResident'] * demand_multiplier
    bed_rate = planning['rates']['bedDaysPerResident'] * demand_multiplier
    admission_rate = planning['rates']['admissionsPerResident'] * demand_multiplier
    visit_cap = np.array([t['doctors'] * visits_per_doctor for t in templates])
    bed_cap = np.array([t['beds'] * 365 * bed_occupancy for t in templates])
    cost = np.array([t['constructionCostTRY'] / 1e9 for t in templates])
    rows, cols, vals, lower, upper_bounds = [], [], [], [], []

    def row(indices, values, lo=-np.inf, hi=np.inf):
        r = len(lower)
        rows.extend([r] * len(indices)); cols.extend(indices); vals.extend(values)
        lower.append(lo); upper_bounds.append(hi)

    flow = nx + np.arange(e)
    for i in range(n):
        edges = np.flatnonzero(origin == i)
        row(flow[edges], np.ones(len(edges)), hi=populations[i] / 1000)
    for j in range(h):
        x = j * k + np.arange(k)
        edges = np.flatnonzero(local_dest == j)
        row(x, np.ones(k), hi=1)
        # Normalize both resource rows in thousands of resident-equivalents.
        row(np.r_[x, flow[edges]], np.r_[-visit_cap / visits_rate / 1000, np.ones(len(edges))], hi=0)
        row(np.r_[x, flow[edges]], np.r_[-bed_cap / bed_rate / 1000, np.ones(len(edges))], hi=0)
    local_conflicts = {}
    for a, b in conflicts:
        if a in site_lookup and b in site_lookup:
            a, b = site_lookup[a], site_lookup[b]
            row(np.r_[a*k + np.arange(k), b*k + np.arange(k)], np.ones(2*k), hi=1)
            local_conflicts.setdefault(a, set()).add(b)
            local_conflicts.setdefault(b, set()).add(a)
    row(flow, np.ones(e), lo=province_total * coverage_target / 1000)
    for d in districts:
        edges = np.flatnonzero(demand_districts[origin] == d['id'])
        row(flow[edges], np.ones(len(edges)), lo=d['population'] * district_floor / 1000)
    A = coo_matrix((vals, (rows, cols)), shape=(len(lower), nv)).tocsc()
    objective = np.r_[np.tile(cost, h), np.zeros(e)]
    integrality = np.r_[np.ones(nx), np.zeros(e)]
    bounds = Bounds(np.zeros(nv), np.r_[np.ones(nx), populations[origin] / 1000])
    relaxation = optimize(objective, np.zeros(nv), bounds, A, lower, upper_bounds, min(15, time_limit))
    seed = None
    if relaxation.x is not None:
        seed = relaxation.x.copy()
        seed[:nx] = 0
        relaxed_loads = np.bincount(local_dest, weights=seed[nx:], minlength=h)
        for j, load in enumerate(relaxed_loads):
            if load > 1e-9:
                fitting = np.flatnonzero((visit_cap / visits_rate / 1000 >= load - 1e-7) &
                                        (bed_cap / bed_rate / 1000 >= load - 1e-7))
                if not len(fitting):
                    seed = None
                    break
                seed[j * k + fitting[np.argmin(cost[fitting])]] = 1
    greedy = greedy_seed(origin, local_dest, times[origin, dest], populations, demand_districts, districts,
                         province_total, coverage_target, district_floor,
                         np.minimum(visit_cap / visits_rate, bed_cap / bed_rate) / 1000, cost, h, local_conflicts)
    if seed is not None:
        activity = A @ seed
        if np.any(activity < np.asarray(lower) - 1e-7) or np.any(activity > np.asarray(upper_bounds) + 1e-7):
            seed = None
    if greedy is not None:
        activity = A @ greedy
        if np.all(activity >= np.asarray(lower) - 1e-7) and np.all(activity <= np.asarray(upper_bounds) + 1e-7):
            if seed is None or objective @ greedy < objective @ seed:
                seed = greedy
    first = optimize(objective, integrality, bounds, A, lower, upper_bounds, time_limit, seed)
    if first.x is None:
        return {'status': 'timeout' if first.status == 1 else 'infeasible',
                'reason': 'Kapasiteli model süre sınırında geçerli çözüm bulamadı.' if first.status == 1 else
                          'Seçili kapasite, aday ve süre sınırları birlikte hedefi karşılayamıyor.',
                'maximumCoveragePercent': upper * 100, 'limitingDistricts': limiting,
                'searchScope': {'nearestCandidatesPerOrigin': neighbors, 'candidateCount': h}}
    reference_cost = float(objective @ first.x)
    reference_served = float(first.x[nx:].sum())
    first_minutes = float(first.x[nx:] @ times[origin, dest] / reference_served)
    budget = reference_cost * (1 + cost_tolerance)
    # Hold exactly the same served demand: minimizing mean time must not reward
    # dropping patients. The budget is relative to the incumbent, NOT a claimed optimum.
    extra = csr_matrix(np.vstack([objective, np.r_[np.zeros(nx), np.ones(e)]]))
    travel_obj = np.r_[np.zeros(nx), times[origin, dest] / province_total * 1000]
    travel_A = vstack([A, extra], format='csc')
    travel_lower = np.r_[lower, -np.inf, reference_served]
    travel_upper = np.r_[upper_bounds, budget + 1e-8, reference_served]
    travel_seed = improve_travel_seed(first.x, travel_obj, bounds, travel_A, travel_lower, travel_upper,
                                      objective, nx, k, origin, dest, local_dest, times[origin, dest], budget,
                                      np.minimum(visit_cap / visits_rate, bed_cap / bed_rate) / 1000,
                                      min(12, time_limit))
    second = optimize(travel_obj, integrality, bounds, travel_A, travel_lower, travel_upper, time_limit, travel_seed)
    solution = first.x
    used_second = second.x is not None and travel_obj @ second.x <= travel_obj @ first.x + 1e-8
    if used_second:
        solution = second.x
    # Recheck raw, unrounded resource, flow, coverage and cost constraints.
    activity = A @ solution
    if np.any(activity < np.asarray(lower) - 1e-5) or np.any(activity > np.asarray(upper_bounds) + 1e-5):
        raise RuntimeError('Capacity solution violates independently recomputed constraints')
    if np.max(np.abs(solution[:nx] - np.round(solution[:nx]))) > 1e-5:
        raise RuntimeError('Nonintegral facility choice')
    x = np.rint(solution[:nx]).reshape(h, k)
    allocation = np.maximum(solution[nx:], 0) * 1000
    selected = [(int(sites[j]), int(np.argmax(x[j]))) for j in range(h) if x[j].sum() > .5]
    loads = np.bincount(dest, weights=allocation, minlength=m)
    capacity_sites = []
    for j, ti in selected:
        t = templates[ti]
        assigned = float(loads[j])
        capacity_sites.append({'candidateIndex': j, 'templateId': t['id'], 'templateLabel': t['label'],
            'beds': t['beds'], 'doctors': t['doctors'], 'grossAreaM2': t['grossAreaM2'],
            'constructionCostTRY': t['constructionCostTRY'], 'assignedPopulation': assigned,
            'annualVisits': assigned * visits_rate, 'annualAdmissions': assigned * admission_rate,
            'annualBedDays': assigned * bed_rate, 'visitCapacity': float(visit_cap[ti]),
            'bedDayCapacity': float(bed_cap[ti]),
            'doctorUtilizationPercent': assigned * visits_rate / visit_cap[ti] * 100,
            'bedUtilizationPercent': assigned * bed_rate / bed_cap[ti] * 100,
            'physicalOccupancyPercent': assigned * bed_rate / (t['beds'] * 365) * 100})
    served = np.bincount(origin, weights=allocation, minlength=n)

    def summary(mask, total):
        weights = allocation[mask]
        covered = float(weights.sum())
        unserved = max(0., total - covered)
        return {'coveredPopulation': covered, 'coveragePercent': covered / total * 100,
                'reachablePopulation': covered, 'unreachableOrUnlocatedPopulation': unserved,
                'meanPopulationDenominator': covered,
                'meanMinutes': float(np.average(times[origin[mask], dest[mask]], weights=weights)) if covered else None,
                'p90Minutes': weighted_quantile(np.r_[times[origin[mask], dest[mask]], np.inf],
                                                np.r_[weights, unserved], .9)}

    actual = summary(np.ones(e, dtype=bool), province_total)
    district_metrics = [{**d, **summary(demand_districts[origin] == d['id'], d['population'])} for d in districts]
    assignments = []
    for i in range(n):
        edges = np.flatnonzero((origin == i) & (allocation > 1e-7))
        edges = edges[np.argsort(-allocation[edges])]
        parts = [{'candidateIndex': int(dest[a]), 'population': float(allocation[a]),
                  'fraction': float(allocation[a] / populations[i]), 'minutes': float(times[i, dest[a]])} for a in edges]
        primary = parts[0] if parts else None
        assignments.append({'candidateIndex': primary['candidateIndex'] if primary else None,
            'minutes': primary['minutes'] if primary else None, 'servedFraction': float(served[i] / populations[i]),
            'covered': bool(served[i] >= populations[i] - 1e-4), 'allocations': parts})
    total_beds = sum(c['beds'] for c in capacity_sites)
    total_doctors = sum(c['doctors'] for c in capacity_sites)
    final_cost = sum(c['constructionCostTRY'] for c in capacity_sites)
    if final_cost > budget * 1e9 + 100:
        raise RuntimeError('Capacity solution exceeds construction budget')
    return {'status': 'optimal' if first.status == 0 and first.mip_gap <= 1e-8 and cost_tolerance == 0 else 'feasible',
        'selectedIndices': [j for j, _ in selected], 'hospitalCount': len(selected),
        'gap': float(first.mip_gap), 'lowerBound': float(first.mip_dual_bound) * 1e9,
        'secondaryOptimal': bool(used_second and second.status == 0 and second.mip_gap <= 1e-8),
        'metrics': actual, 'districts': district_metrics, 'assignments': assignments, 'capacitySites': capacity_sites,
        'capacity': {'totalBeds': total_beds, 'totalDoctors': total_doctors, 'constructionCostTRY': final_cost,
            'referenceCostTRY': reference_cost * 1e9, 'budgetLimitTRY': budget * 1e9,
            'referenceMeanMinutes': first_minutes, 'travelImprovementPercent':
                100 * (first_minutes - actual['meanMinutes']) / first_minutes if first_minutes else 0,
            'annualVisitsDemand': province_total * visits_rate, 'annualVisitsServed': actual['coveredPopulation'] * visits_rate,
            'annualAdmissionsDemand': province_total * admission_rate, 'annualBedDaysDemand': province_total * bed_rate,
            'annualBedDaysServed': actual['coveredPopulation'] * bed_rate,
            'doctorUtilizationPercent': actual['coveredPopulation'] * visits_rate / (total_doctors * visits_per_doctor) * 100,
            'bedUtilizationPercent': actual['coveredPopulation'] * bed_rate / (total_beds * 365 * bed_occupancy) * 100,
            'costStageGap': float(first.mip_gap), 'costStageProvenOptimal': first.status == 0 and first.mip_gap <= 1e-8,
            'travelStageGap': float(second.mip_gap) if used_second and second.mip_gap is not None else None,
            'travelStageImproved': bool(used_second), 'planningVersion': planning['version']},
        'searchScope': {'nearestCandidatesPerOrigin': neighbors, 'candidateCount': h, 'allocationEdges': e}}
