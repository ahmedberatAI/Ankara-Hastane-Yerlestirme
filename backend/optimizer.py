"""Partial set cover with district coverage floors, solved by HiGHS MILP."""
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import csr_matrix, eye, hstack, vstack

def undominated_columns(within):
    """For equal opening costs, a subset column cannot improve minimum count.

    Retain the full pool for subsequent coverage/time objectives. Python integer
    bit sets make the exact subset checks inexpensive without approximate radii.
    """
    keys = [int.from_bytes(row.tobytes(), 'little') for row in np.packbits(within.T, axis=1)]
    kept = []
    for j in sorted(range(len(keys)), key=lambda j: (-keys[j].bit_count(), j)):
        if keys[j] and not any(keys[j] & keys[k] == keys[j] for k in kept):
            kept.append(j)
    return np.array(sorted(kept), dtype=int)

def weighted_quantile(values, weights, quantile):
    order = np.argsort(values)
    values, weights = np.asarray(values)[order], np.asarray(weights)[order]
    if not len(values) or weights.sum() <= 0:
        return None
    value = values[min(np.searchsorted(np.cumsum(weights), weights.sum() * quantile), len(values)-1)]
    return float(value) if np.isfinite(value) else None

def metrics(times, populations, province_total, threshold):
    finite = np.isfinite(times)
    covered = finite & (times <= threshold + 1e-7)
    served = int(populations[covered].sum())
    reachable = int(populations[finite].sum())
    # Unknown locations and unreachable demand remain in the provincial denominator.
    unknown = max(0, province_total - int(populations.sum()))
    q_values = np.append(times, np.inf)
    q_weights = np.append(populations, unknown)
    return {'coveredPopulation': served, 'coveragePercent': 100 * served / province_total,
            'reachablePopulation': reachable, 'unreachableOrUnlocatedPopulation': province_total-reachable,
            'meanMinutes': float(np.average(times[finite], weights=populations[finite])) if reachable else None,
            'p90Minutes': weighted_quantile(q_values, q_weights, .9),
            'meanPopulationDenominator': reachable}

def solve_cover(times, populations, demand_districts, districts, province_total,
                threshold=30, coverage_target=.95, district_floor=.8, time_limit=20):
    n, m = times.shape
    if not n or not m:
        return {'status': 'infeasible', 'reason': 'Hesaplanabilir talep veya hastane adayı bulunmuyor.'}
    within = (times <= threshold) & np.isfinite(times)
    possible = within.any(axis=1)
    ceilings = []
    for d in districts:
        mask = demand_districts == d['id']
        max_pop = int(populations[mask & possible].sum())
        ceilings.append({'id': d['id'], 'name': d['name'], 'maximumPercent': max_pop / d['population'] * 100})
    upper = int(populations[possible].sum()) / province_total
    impossible = [d for d in ceilings if d['maximumPercent'] + 1e-7 < district_floor * 100]
    if upper + 1e-9 < coverage_target or impossible:
        return {'status': 'infeasible', 'reason': 'Bu veri ve süre eşiğiyle erişim hedefi sağlanamıyor. Süreyi artırın veya hedefi azaltın.',
                'maximumCoveragePercent': upper * 100, 'limitingDistricts': impossible}
    # y_i <= sum_j a_ij*x_j, x_j and y_i binary. Cost units are equal.
    constraints = [hstack((-csr_matrix(within, dtype=float), eye(n, format='csr')), format='csr')]
    lower = [-np.inf] * n
    upper_bounds = [0.] * n
    weights = populations / province_total
    constraints.append(csr_matrix(np.r_[np.zeros(m), weights].reshape(1, -1)))
    lower.append(coverage_target)
    upper_bounds.append(np.inf)
    for d in districts:
        ds = np.where(demand_districts == d['id'], populations / d['population'], 0.)
        constraints.append(csr_matrix(np.r_[np.zeros(m), ds].reshape(1, -1)))
        lower.append(district_floor)
        upper_bounds.append(np.inf)
    A = vstack(constraints, format='csr')
    objective = np.r_[np.ones(m), np.zeros(n)]
    options = {'time_limit': time_limit, 'mip_rel_gap': 0.0}
    keep = undominated_columns(within)
    primary_columns = np.r_[keep, m + np.arange(n)]
    # Given binary x, continuous 0 <= y <= 1 has the same coverage feasibility:
    # it is zero for uncovered demand and may be one for every covered demand.
    first = milp(objective[primary_columns], integrality=np.r_[np.ones(len(keep)), np.zeros(n)], bounds=Bounds(0, 1),
                 constraints=LinearConstraint(A[:, primary_columns], lower, upper_bounds), options=options)
    if first.x is None:
        return {'status': 'timeout' if first.status == 1 else 'infeasible',
                'reason': 'Süre sınırında geçerli çözüm bulunamadı.' if first.status == 1 else 'Hedefler için geçerli çözüm yok.'}
    selected = keep[np.flatnonzero(first.x[:len(keep)] > .5)]
    count = len(selected)
    # Lexicographic secondary objective: maximize additional population served
    # without increasing the primary number of hospitals.
    fixed_count = csr_matrix(np.r_[np.ones(m), np.zeros(n)].reshape(1, -1))
    second = milp(np.r_[np.zeros(m), -weights], integrality=np.r_[np.ones(m), np.zeros(n)], bounds=Bounds(0, 1),
                  constraints=LinearConstraint(vstack([A, fixed_count], format='csr'),
                                               np.r_[lower, count], np.r_[upper_bounds, count]),
                  options={'time_limit': min(10, time_limit), 'mip_rel_gap': .0005})
    if second.x is not None:
        selected = np.flatnonzero(second.x[:m] > .5)
    # Tertiary local p-median improvement. Preserve count, achieved coverage and
    # every district floor. This is NOT a claim of globally optimal travel time.
    finite_cost = np.nan_to_num(times, posinf=1440.)
    preserved_coverage = populations[(times[:, selected].min(axis=1) <= threshold)].sum()
    current_score = float(populations @ finite_cost[:, selected].min(axis=1))
    improvements = 0
    for _ in range(2):
        best = None
        for remove in selected:
            remaining = selected[selected != remove]
            baseline = times[:, remaining].min(axis=1) if len(remaining) else np.full(n, np.inf)
            options_time = np.minimum(baseline[:, None], times)
            options_covered = options_time <= threshold
            eligible = populations @ options_covered >= preserved_coverage - 1e-5
            for d in districts:
                mask = demand_districts == d['id']
                eligible &= populations[mask] @ options_covered[mask] >= d['population'] * district_floor - 1e-5
            eligible[selected] = False
            scores = populations @ np.nan_to_num(options_time, posinf=1440.)
            scores[~eligible] = np.inf
            candidate = int(scores.argmin())
            if scores[candidate] < current_score - 1 and (best is None or scores[candidate] < best[0]):
                best = (scores[candidate], remove, candidate)
        if best is None:
            break
        current_score, remove, candidate = best
        selected = np.sort(np.r_[selected[selected != remove], candidate])
        improvements += 1
    nearest = times[:, selected].min(axis=1)
    actual = metrics(nearest, populations, province_total, threshold)
    district_metrics = []
    for d in districts:
        mask = demand_districts == d['id']
        district_metrics.append({**d, **metrics(nearest[mask], populations[mask], d['population'], threshold)})
    if actual['coveragePercent'] + 1e-5 < coverage_target * 100 or any(d['coveragePercent'] + 1e-5 < district_floor*100 for d in district_metrics):
        raise RuntimeError('Solver returned a solution violating the independently recomputed coverage constraints')
    assignment = selected[np.argmin(times[:, selected], axis=1)]
    return {'status': 'optimal' if first.status == 0 else 'feasible', 'selectedIndices': selected.tolist(),
            'hospitalCount': len(selected), 'costUnits': len(selected),
            'lowerBound': float(first.mip_dual_bound) if first.mip_dual_bound is not None else None,
            'gap': float(first.mip_gap) if first.mip_gap is not None else None,
            'secondaryOptimal': second.status == 0, 'metrics': actual, 'districts': district_metrics,
            'primaryCandidateCount': len(keep),
            'travelRefinement': {'method': 'coverage-preserving one-swap', 'iterations': improvements, 'globallyOptimal': False},
            'assignments': [{'candidateIndex': int(c), 'minutes': float(t) if np.isfinite(t) else None,
                             'covered': bool(t <= threshold)} for c, t in zip(assignment, nearest)]}
