"""Two complete demand scenarios sharing sites, integer beds and physicians.

Annual materials count once. Modal weights affect travel priorities only.
The public solver is bounded and reports its candidate/edge search restriction.
The frozen four-profile implementation is not changed.
"""
import math
from time import monotonic
from types import SimpleNamespace
import numpy as np
from scipy.sparse import coo_matrix, csc_matrix, vstack
from backend.joint_model import JointProblem, ModelInfeasible, AREA_TOL, validate_vector
from backend.optimizer import weighted_quantile

MODES = ('car', 'transit')


def _number(value, name, *, minimum=0., maximum=math.inf):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
        raise ValueError('Invalid ' + name)
    value = float(value)
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError('Invalid ' + name)
    return value


def build_hybrid_problem(car_times, transit_times, populations, demand_districts,
                         districts, province_total, planning, scenario, candidates,
                         conflicts=(), *, neighbors=12):
    """Pure two-mode formulation. None retains every legal allocation edge.

    Nearest neighbors are selected independently for each origin, mode and
    footprint-radius class. No coverage or demand is weighted by modal weights.
    All candidate identities remain global in serialized output.
    """
    car_limit = _number(scenario.get('threshold', 30), 'car threshold', minimum=1e-12)
    conflicts = tuple(tuple(pair) for pair in conflicts)
    transit_limit = _number(scenario.get('transitThreshold', 45), 'transit threshold', minimum=1e-12)
    car_weight = _number(scenario.get('carWeight', 70), 'car weight', maximum=100) / 100
    if neighbors is not None and (isinstance(neighbors, bool) or not isinstance(neighbors, int) or neighbors < 1):
        raise ValueError('Neighbors must be a positive integer or None')
    # Validate identities/denominators/clinical parameters in the pure builder,
    # before any restricted infeasibility can be mistaken for a city finding.
    matrices = {}
    for name, raw, limit in zip(MODES, (car_times, transit_times), (car_limit, transit_limit)):
        t = np.asarray(raw, dtype=float)
        if t.shape != (len(populations), len(candidates)) or np.any(np.isnan(t)) or np.any(t < 0):
            raise ValueError('Invalid ' + name + ' matrix')
        matrices[name] = np.where(t <= limit, t, np.inf)
    internal = dict(scenario, threshold=max(car_limit, transit_limit))
    # Full-geometry necessary conditions use original province/district
    # denominators, including residents lacking an origin coordinate.
    pop = np.asarray(populations, dtype=float)
    dd = np.asarray(demand_districts)
    if pop.ndim != 1 or dd.shape != pop.shape or np.any(~np.isfinite(pop)) or np.any(pop < 0):
        raise ValueError('Invalid population')
    total = _number(province_total, 'province population', minimum=1e-12)
    coverage = _number(internal['coverageTarget'], 'coverage', maximum=100)
    floor = _number(internal['districtFloor'], 'district floor', maximum=100)
    ids = [d['id'] for d in districts]
    denoms = [_number(d['population'], 'district population', minimum=1e-12) for d in districts]
    if (len(set(ids)) != len(ids) or not set(dd).issubset(ids)
            or not math.isclose(sum(denoms), total, rel_tol=1e-10, abs_tol=1e-6)
            or pop.sum() > total + 1e-6
            or any(pop[dd == d['id']].sum() > d['population'] + 1e-6 for d in districts)):
        raise ValueError('Invalid district identities or population denominators')
    if coverage < floor or total * coverage / 100 > pop.sum() + 1e-6:
        raise ModelInfeasible('Full two-mode model: located population or district floors conflict with exact province target')
    full_edges = {name: int(np.isfinite(t).sum()) for name, t in matrices.items()}
    for name, t in matrices.items():
        accessible = np.isfinite(t).any(axis=1)
        if (pop[accessible].sum() < total * coverage / 100 - 1e-6
                or any(pop[accessible & (dd == d['id'])].sum() < d['population'] * floor / 100 - 1e-6 for d in districts)):
            raise ModelInfeasible('All supplied candidates fail necessary geographic targets in ' + name)
    radii = np.array([_number(c['footprintRadiusMeters'], 'plot radius', minimum=1e-12) for c in candidates])
    if neighbors is not None:
        for name, t in matrices.items():
            retained = np.zeros(t.shape, dtype=bool)
            for radius in np.unique(radii):
                columns = np.flatnonzero(radii == radius)
                for i in range(len(pop)):
                    legal = columns[np.isfinite(t[i, columns])]
                    chosen = legal[np.argsort(t[i, legal], kind='stable')[:neighbors]]
                    retained[i, chosen] = True
            matrices[name] = np.where(retained, t, np.inf)
    used = np.logical_or.reduce([np.isfinite(t).any(axis=0) for t in matrices.values()])
    # Removing sites with no retained edge is itself part of the declared
    # restriction. It does not hide an all-candidate infeasibility claim.
    if coverage == 0:
        used[:] = True
    selected = np.flatnonzero(used)
    sites = [candidates[j] for j in selected]
    retained_ids = {s['candidateIndex'] for s in sites}
    original_ids = [s['candidateIndex'] for s in candidates]
    if len(set(original_ids)) != len(original_ids) or any(isinstance(i, bool) or not isinstance(i, (int, np.integer)) or i < 0 for i in original_ids):
        raise ValueError('Invalid candidate identities')
    for pair in conflicts:
        if len(pair) != 2 or pair[0] == pair[1] or any(i not in original_ids for i in pair):
            raise ValueError('Invalid plot conflict')
    reduced_conflicts = tuple(pair for pair in conflicts if all(i in retained_ids for i in pair))
    problem = _build_two_profile_problem({name: t[:, selected] for name, t in matrices.items()},
        populations, demand_districts, districts, total, sites, planning, internal, reduced_conflicts)
    kept = {name: len(problem.edges[name][0]) for name in MODES}
    restricted = any(kept[name] != full_edges[name] for name in MODES)
    problem.modal_weights = {'car': car_weight, 'transit': 1 - car_weight}
    problem.modal_thresholds = {'car': car_limit, 'transit': transit_limit}
    problem.search_scope = {
        'kind': 'restricted_allocation_edges' if restricted else 'all_supplied_allocation_edges',
        'neighborsPerOriginModeFootprintClass': neighbors,
        'allCandidateCount': len(candidates), 'retainedCandidateCount': len(sites),
        'allLegalEdgesByMode': full_edges, 'retainedEdgesByMode': kept,
        'candidateIndices': list(map(int, problem.ids)), 'restricted': restricted,
        'boundScope': 'supplied_candidate_pool_and_retained_modal_edges',
        'description': 'Nearest allocation edges per origin, mode and plot-radius class. A restricted search failure is not an infeasibility certificate for all candidates or Ankara.'}
    return problem

def _build_two_profile_problem(profile_times,populations,demand_districts,districts,province_total,
                        candidates,planning,scenario,conflicts=()):
    """Build all supplied candidate/profile edges without invoking a solver."""
    started=monotonic()
    def positive(v, name, zero=False):
        if isinstance(v, (bool, np.bool_)) or not np.isfinite(v) or (v < 0 if zero else v <= 0):
            raise ValueError('Invalid ' + name)
        return float(v)
    total = positive(province_total, 'province population')
    pop = np.asarray(populations, dtype=float); dd = np.asarray(demand_districts)
    if pop.ndim != 1 or not len(pop) or pop.shape != dd.shape or np.any(~np.isfinite(pop)) or np.any(pop < 0) or pop.sum() > total + 1e-6:
        raise ValueError('Invalid located population or denominator')
    if not districts or not candidates or not isinstance(profile_times, dict) or len(profile_times)!=2:
        raise ValueError('Candidates, districts and named profiles required')
    if any(not isinstance(p, str) or not p for p in profile_times):
        raise ValueError('Invalid profile names')
    district_ids = [d['id'] for d in districts]
    denoms = np.array([positive(d['population'], 'district population') for d in districts])
    if len(set(district_ids)) != len(districts) or not set(dd).issubset(district_ids) or not np.isclose(denoms.sum(), total, rtol=1e-10, atol=1e-6):
        raise ValueError('District identity/denominators invalid')
    if any(pop[dd == d['id']].sum() > d['population'] + 1e-6 for d in districts):
        raise ValueError('District located population exceeds denominator')
    ids = [s['candidateIndex'] for s in candidates]
    if any(isinstance(i, bool) or not isinstance(i, (int, np.integer)) or i < 0 for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Invalid candidate identities')
    id_to_local = {value: i for i, value in enumerate(ids)}
    local_conflicts = set()
    for pair in conflicts:
        if len(pair) != 2 or pair[0] not in id_to_local or pair[1] not in id_to_local or pair[0] == pair[1]:
            raise ValueError('Invalid plot conflict')
        local_conflicts.add(tuple(sorted((id_to_local[pair[0]], id_to_local[pair[1]]))))
    threshold = positive(scenario['threshold'], 'threshold')
    coverage = positive(scenario['coverageTarget'], 'coverage', zero=True)
    district_floor = positive(scenario['districtFloor'], 'district floor', zero=True)
    occupancy = positive(scenario['bedOccupancy'], 'occupancy') / 100
    if max(coverage, district_floor) > 100 or occupancy > 1:
        raise ValueError('Percent outside range')
    demand = positive(scenario['demandMultiplier'], 'demand multiplier')
    throughput = positive(scenario['contactsPerDoctor'], 'physician throughput')
    operating = positive(scenario.get('operatingCostMultiplier', 1), 'operating multiplier')
    tolerance = positive(scenario.get('costTolerance', 10), 'cost tolerance', zero=True) / 100
    hospital_limit = scenario.get('hospitalLimit')
    if hospital_limit is not None and (isinstance(hospital_limit, bool) or int(hospital_limit) != hospital_limit or hospital_limit < 0):
        raise ValueError('Invalid hospital limit')
    design, rates, eco = planning['design'], planning['rates'], planning['economics']
    min_docs = positive(design['minimumDoctorsPerSite'], 'minimum physicians')
    if int(min_docs) != min_docs: raise ValueError('Minimum physicians must be integer')
    doctor_area = positive(design['areaPerDoctorM2'], 'physician area')
    floors = positive(design['maxFloors'], 'floor limit')
    radii = np.array([positive(s['footprintRadiusMeters'], 'plot radius') for s in candidates])
    available = np.pi * radii ** 2 * floors
    contact = positive(rates['contactsPerResident'], 'contact rate') * demand
    bedrate = positive(rates['bedDaysPerResident'], 'bed-day rate') * demand
    templates = planning['templates']
    if not templates or len({x['id'] for x in templates}) != len(templates): raise ValueError('Invalid templates')
    beds = np.array([positive(x['beds'], 'beds') for x in templates])
    area = np.array([positive(x['grossAreaM2'], 'template area') for x in templates])
    if np.any(beds != np.rint(beds)): raise ValueError('Beds must be integer')
    for key in ('buildingUnitCostTRY', 'annualFixedSiteCostTRY', 'annualDoctorCostTRY', 'annualBedSupportCostTRY', 'costPerContactTRY', 'realDiscountRate'):
        positive(eco[key], key, zero=True)
    years = positive(eco['horizonYears'], 'cost horizon'); r = eco['realDiscountRate']
    annuity = r / (1 - (1 + r) ** -years) if r else 1 / years
    n, m = len(pop), len(candidates); target = total * coverage / 100
    def failure(status, reason):
        raise ModelInfeasible(reason)
    profile_edges = {}; matrices = {}
    for name, raw in profile_times.items():
        t = np.asarray(raw, dtype=float)
        if t.shape != (n, m) or np.any(np.isnan(t)) or np.any(t < 0): raise ValueError('Invalid matrix')
        matrices[name] = t; oi, sj = np.where(np.isfinite(t) & (t <= threshold)); profile_edges[name] = (oi, sj)
    if target > pop.sum() + 1e-6 or target < denoms.sum() * district_floor / 100 - 1e-6:
        return failure('infeasible', 'Exact target conflicts with located population or district floors within this model.')
    for name, t in matrices.items():
        accessible = (np.isfinite(t) & (t <= threshold)).any(axis=1)
        if pop[accessible].sum() < target - 1e-6 or any(pop[accessible & (dd == d['id'])].sum() < d['population'] * district_floor / 100 - 1e-6 for d in districts):
            return failure('infeasible', 'All supplied candidates fail geographic targets in ' + name)
    eligible = area[None, :] + min_docs * doctor_area <= available[:, None] + AREA_TOL
    xsite, xtype = np.where(eligible); nx = len(xsite); nf = nx + m
    if not nx: return failure('infeasible', 'No supplied plot fits minimum resources.')
    site_xs = [np.flatnonzero(xsite == j) for j in range(m)]
    max_docs = np.maximum(0, np.floor(np.nextafter((available + AREA_TOL - area.min()) / doctor_area, np.inf)))
    max_docs = np.minimum(max_docs, max(min_docs, math.ceil(target * contact / throughput)))
    max_docs[~eligible.any(axis=1)] = 0
    offsets = {}; nv = nf
    for name, (oi, _) in profile_edges.items(): offsets[name] = nv; nv += len(oi)
    module_cost = area * eco['buildingUnitCostTRY'] * annuity + operating * (eco['annualFixedSiteCostTRY'] + beds * eco['annualBedSupportCostTRY'])
    doc_cost = doctor_area * eco['buildingUnitCostTRY'] * annuity + operating * eco['annualDoctorCostTRY']
    material = target * contact * eco['costPerContactTRY'] * operating
    cost_scale = max(1., float(module_cost.max()), doc_cost)
    c = np.r_[module_cost[xtype], np.full(m, doc_cost), np.zeros(nv - nf)] / cost_scale
    integer = np.r_[np.ones(nf), np.zeros(nv - nf)]
    lb = np.zeros(nv); ub = np.r_[np.ones(nx), max_docs, np.concatenate([pop[oi] / 1000 for oi, _ in profile_edges.values()])]
    rows, cols, values, lo, hi = [], [], [], [], []
    def row(indices, vals, lower=-np.inf, upper=np.inf):
        rows.extend([len(lo)] * len(indices)); cols.extend(indices); values.extend(vals); lo.append(lower); hi.append(upper)
    for j, xs in enumerate(site_xs):
        ts = xtype[xs]; dj = nx + j
        row(xs, np.ones(len(xs)), upper=1.)
        row(np.r_[xs, dj], np.r_[np.full(len(xs), min_docs), -1.], upper=0.)
        # When closed, positive physician area forces staff to zero.
        row(np.r_[xs, dj], np.r_[(area[ts] - available[j]) / doctor_area, 1.], upper=0.)
    for a, b in sorted(local_conflicts):
        xs = np.r_[site_xs[a], site_xs[b]]; row(xs, np.ones(len(xs)), upper=1.)
    if hospital_limit is not None: row(np.arange(nx), np.ones(nx), upper=hospital_limit)
    def groups(indices, count):
        order = np.argsort(indices, kind='stable'); sizes = np.bincount(indices, minlength=count)
        return np.split(order, np.cumsum(sizes)[:-1])
    for name, (oi, sj) in profile_edges.items():
        fs = offsets[name] + np.arange(len(oi))
        for i, es in enumerate(groups(oi, n)): row(fs[es], np.ones(len(es)), upper=pop[i] / 1000)
        for j, es in enumerate(groups(sj, m)):
            xs = site_xs[j]
            row(np.r_[xs, fs[es]], np.r_[-beds[xtype[xs]] * 365 * occupancy / bedrate / 1000, np.ones(len(es))], upper=0.)
            row(np.r_[nx + j, fs[es]], np.r_[-throughput / contact / 1000, np.ones(len(es))], upper=0.)
        row(fs, np.ones(len(fs)), lower=target / 1000, upper=target / 1000)
        for d in districts:
            es = np.flatnonzero(dd[oi] == d['id']); row(fs[es], np.ones(len(es)), lower=d['population'] * district_floor / 100 / 1000)
    A = coo_matrix((values, (rows, cols)), shape=(len(lo), nv)).tocsc(); lo, hi = np.asarray(lo), np.asarray(hi)
    if np.any(~np.isfinite(c)) or np.any(~np.isfinite(A.data)) or np.any(~np.isfinite(lb)) or np.any(~np.isfinite(ub)):
        raise ValueError('Nonfinite derived formulation coefficients/bounds')
    return JointProblem(times=matrices,pop=pop,dd=dd,districts=districts,total=total,
        sites=candidates,h=planning,s=scenario,n=n,m=m,target=target,ids=ids,local=id_to_local,
        conflicts=tuple(conflicts),model=(c,integer,lb,ub,A,lo,hi),c=c,minimum=int(min_docs),
        da=doctor_area,available=available,beds=beds,area=area,xsite=xsite,xtype=xtype,
        nx=nx,nf=nf,site_xs=site_xs,contact=contact,bedrate=bedrate,occupancy=occupancy,
        q=throughput/contact/1000,bedcap=beds*365*occupancy/bedrate/1000,module=module_cost,
        doc_cost=doc_cost,cost_scale=cost_scale,material=material,edges=profile_edges,offsets=offsets,
        buildSeconds=monotonic()-started,dimensions={'binaryTemplates':nx,'integerPhysicians':m,
            'flowVariables':nv-nf,'variables':nv,'constraints':A.shape[0],'nonzeros':A.nnz,'conflicts':len(local_conflicts)})


def _native(model, seconds, start=None, *, deadline=None):
    """One bounded native search, optionally with a complete checked incumbent."""
    import highspy
    from backend.joint_solver import native_warm_optimize
    deadline = monotonic() + seconds if deadline is None else deadline
    metadata = {}
    if start is not None:
        solved = native_warm_optimize(*model, seconds, start, metadata, deadline=deadline)
        # A feasible local fallback remains valid even if the native solver does
        # not confirm using its start. Never claim that unconfirmed acceptance.
        solved.warm = metadata
        return solved
    c, integer, lb, ub, A, lo, hi = model
    lp = highspy.HighsLp()
    lp.num_col_, lp.num_row_ = A.shape[1], A.shape[0]
    lp.col_cost_, lp.col_lower_, lp.col_upper_ = c, lb, ub
    lp.row_lower_, lp.row_upper_ = lo, hi
    lp.a_matrix_.start_, lp.a_matrix_.index_, lp.a_matrix_.value_ = A.indptr, A.indices, A.data
    lp.integrality_ = [highspy.HighsVarType.kInteger if x else highspy.HighsVarType.kContinuous for x in integer]
    solver = highspy.Highs()
    for name, value in [('output_flag', False), ('threads', 1), ('random_seed', 7), ('mip_rel_gap', .002)]:
        if solver.setOptionValue(name, value) != highspy.HighsStatus.kOk:
            raise RuntimeError('HiGHS rejected option ' + name)
    if solver.passModel(lp) != highspy.HighsStatus.kOk:
        raise RuntimeError('HiGHS rejected hybrid model')
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError('Deadline exhausted before native solve')
    solver.setOptionValue('time_limit', remaining)
    solver.run()
    info, status, solution = solver.getInfo(), solver.getModelStatus(), solver.getSolution()
    return SimpleNamespace(
        x=np.asarray(solution.col_value) if info.primal_solution_status == highspy.SolutionStatus.kSolutionStatusFeasible else None,
        status=0 if status == highspy.HighsModelStatus.kOptimal else 2 if status == highspy.HighsModelStatus.kInfeasible else 1,
        message=str(status), nativeModelStatus=str(status), isTimeLimit=status == highspy.HighsModelStatus.kTimeLimit,
        mip_dual_bound=info.mip_dual_bound, mip_gap=info.mip_gap, nodes=int(info.mip_node_count),
        runtime=float(solver.getRunTime()), warm={'completeStartSupplied': False, 'solverAcceptedFeasibleStart': False})


def _fit(p, j, load):
    """Cheapest integer resource pair for a proposed maximum modal load."""
    need = max(p.minimum, math.ceil(math.nextafter(load * p.contact / p.s['contactsPerDoctor'], -math.inf)))
    if need > p.model[3][p.nx + j]:
        return None
    options = []
    for x in p.site_xs[j]:
        t = p.xtype[x]
        if p.area[t] + need * p.da <= p.available[j] + AREA_TOL and p.bedcap[t] * 1000 >= load - 1e-9:
            options.append((float(p.module[t] + p.doc_cost * need), int(x), need))
    return min(options) if options else None


def _greedy_seed(p, deadline):
    """Bounded shared-resource opening heuristic, independently validated.

    Per-mode quota allocation remains separate. This seed is not a minimum-cost
    or hospital-count result, and failure says nothing about feasibility.
    """
    v = np.zeros(len(p.c))
    if p.target == 0:
        p.validate(v)
        return v
    district_index = {d['id']: i for i, d in enumerate(p.districts)}
    di = np.array([district_index[d] for d in p.dd])
    rem = {mode: p.pop.copy() for mode in MODES}
    quota = {mode: np.array([d['population'] * p.s['districtFloor'] / 100 for d in p.districts]) for mode in MODES}
    need = {mode: p.target for mode in MODES}
    loads = {mode: np.zeros(p.m) for mode in MODES}
    groups = {}
    for mode in MODES:
        oi, sj = p.edges[mode]
        order = np.argsort(sj, kind='stable')
        groups[mode] = np.split(order, np.cumsum(np.bincount(sj, minlength=p.m))[:-1])
        for j, es in enumerate(groups[mode]):
            groups[mode][j] = es[np.argsort(p.times[mode][oi[es], j], kind='stable')]
    blocked = [set() for _ in range(p.m)]
    for a, b in p.conflicts:
        ja, jb = p.local[a], p.local[b]
        blocked[ja].add(jb); blocked[jb].add(ja)
    opened = set()
    ceiling = np.zeros(p.m)
    for j, xs in enumerate(p.site_xs):
        for x in xs:
            t = p.xtype[x]
            docs = min(p.model[3][p.nx + j], math.floor(math.nextafter((p.available[j] + AREA_TOL - p.area[t]) / p.da, math.inf)))
            if docs >= p.minimum:
                ceiling[j] = max(ceiling[j], min(p.bedcap[t], docs * p.q) * 1000)

    def preview(mode, j, room, floor_phase):
        es = groups[mode][j]; oi = p.edges[mode][0][es]
        if not len(es) or room <= 0 or need[mode] <= 0:
            return es[:0], np.zeros(0)
        amount = rem[mode][oi].copy()
        if floor_phase:
            for d in np.unique(di[oi]):
                slots = np.flatnonzero(di[oi] == d)
                earlier = np.r_[0., np.cumsum(amount[slots])[:-1]]
                amount[slots] = np.minimum(amount[slots], np.maximum(0., quota[mode][d] - earlier))
        earlier = np.r_[0., np.cumsum(amount)[:-1]]
        amount = np.minimum(amount, np.maximum(0., min(room, need[mode]) - earlier))
        return es, amount

    def proposal(j, floor_phase):
        if ceiling[j] <= 0 or blocked[j] & opened:
            return None
        limit = p.s.get('hospitalLimit')
        if j not in opened and limit is not None and len(opened) >= limit:
            return None
        proposed = {mode: preview(mode, j, ceiling[j] - loads[mode][j], floor_phase) for mode in MODES}
        gain = {mode: float(proposed[mode][1].sum()) for mode in MODES}
        if sum(gain.values()) <= 1e-9:
            return None
        option = _fit(p, j, max(loads[mode][j] + gain[mode] for mode in MODES))
        if option is None:
            return None
        old_cost = float(p.module[p.xtype[p.site_xs[j]]] @ v[p.site_xs[j]] + p.doc_cost * v[p.nx+j])
        score = sum(gain.values()) / max(option[0] - old_cost, 1e-9)
        return ((score, sum(gain.values()), -int(p.ids[j])), option, proposed)

    for floor_phase in (True, False):
        # Rank once per quota phase, then recompute each proposed allocation at
        # its turn. Avoid an O(m squared) full rescan after every opening; this
        # bounded seed heuristic claims no greedy optimum.
        ranked = []
        for j in range(p.m):
            if monotonic() >= deadline:
                return None
            item = proposal(j, floor_phase)
            if item is not None:
                ranked.append((item[0], j))
        ranked.sort(reverse=True)
        for _, j in ranked:
            if monotonic() >= deadline:
                return None
            if all((quota[mode].sum() if floor_phase else need[mode]) <= 1e-8 for mode in MODES):
                break
            item = proposal(j, floor_phase)
            if item is None:
                continue
            _, (_, x, docs), proposed = item
            v[p.site_xs[j]] = 0; v[x] = 1; v[p.nx+j] = docs; opened.add(j)
            for mode, (es, amount) in proposed.items():
                oi = p.edges[mode][0][es]
                v[p.offsets[mode] + es] += amount / 1000
                rem[mode][oi] -= amount
                quota[mode] = np.maximum(0., quota[mode] - np.bincount(di[oi], weights=amount, minlength=len(p.districts)))
                loads[mode][j] += amount.sum(); need[mode] -= amount.sum()
        if any((quota[mode].sum() if floor_phase else need[mode]) > 1e-8 for mode in MODES):
            return None
    try:
        p.validate(v)
        return v
    except ValueError:
        return None


def _travel_objective(p):
    c = np.zeros(len(p.c))
    if p.target:
        for mode, (oi, sj) in p.edges.items():
            c[p.offsets[mode]:p.offsets[mode] + len(oi)] = p.modal_weights[mode] * p.times[mode][oi, sj] * 1000 / p.target
    return c


def _candidate(p, raw, source=None, *, objective=None, budget=None):
    """No flow clipping: invalid numerical incumbents preserve a checked source."""
    reason = None
    if raw is None:
        reason = 'No native incumbent returned'
    else:
        try:
            raw = np.asarray(raw, dtype=float)
            if raw.shape != p.c.shape or np.any(~np.isfinite(raw)) or np.any(raw[p.nf:] < 0):
                raise ValueError('Invalid finite/nonnegative native flow')
            if np.max(np.abs(raw[:p.nf] - np.rint(raw[:p.nf])), initial=0) > 1e-5:
                raise ValueError('Native resource integrality residual too large')
            v = raw.copy(); v[:p.nf] = np.rint(v[:p.nf])
            p.validate(v)
            if budget is not None and p.cost(v) > budget + max(.01, abs(budget) * 1e-12):
                raise ValueError('Native incumbent exceeds travel-stage annual budget')
            if source is not None and objective is not None and objective @ v > objective @ source + 1e-8:
                raise ValueError('Native incumbent worsens the validated source objective')
            return v, None
        except ValueError as exc:
            reason = str(exc)
    return (source.copy() if source is not None else None), reason


def _finite(value):
    return float(value) if value is not None and np.isfinite(value) else None


def _bound_gap(value, lower, tolerance):
    if lower is None:
        return None
    if lower > value + tolerance:
        raise RuntimeError('Native lower bound exceeds independently validated incumbent')
    return max(0., value - lower) / abs(value) if value else (0. if abs(lower) <= tolerance else None)


def _modal_result(p, v, mode):
    oi, sj = p.edges[mode]
    flow = v[p.offsets[mode]:p.offsets[mode] + len(oi)] * 1000
    minutes = p.times[mode][oi, sj]
    served = np.bincount(oi, weights=flow, minlength=p.n)

    def metrics(mask, total):
        w = flow[mask]; covered = float(w.sum()); unserved = max(0., total - covered)
        return {'coveredPopulation': covered, 'coveragePercent': 100 * covered / total,
            'reachablePopulation': covered, 'unreachableOrUnlocatedPopulation': unserved,
            'meanPopulationDenominator': covered,
            'meanMinutes': float(w @ minutes[mask] / covered) if covered else None,
            'p90Minutes': weighted_quantile(np.r_[minutes[mask], np.inf], np.r_[w, unserved], .9)}
    assignments = []
    order = np.argsort(oi, kind='stable')
    grouped = np.split(order, np.cumsum(np.bincount(oi, minlength=p.n))[:-1])
    for i, es in enumerate(grouped):
        es = es[flow[es] > 0]; es = es[np.argsort(-flow[es], kind='stable')]
        parts = [{'candidateIndex': int(p.ids[sj[a]]), 'population': float(flow[a]),
                  'fraction': float(flow[a] / p.pop[i]) if p.pop[i] else 0., 'minutes': float(minutes[a])} for a in es]
        primary = parts[0] if parts else None
        assignments.append({'candidateIndex': primary['candidateIndex'] if primary else None,
            'minutes': primary['minutes'] if primary else None,
            'servedFraction': float(served[i] / p.pop[i]) if p.pop[i] else 0.,
            'covered': bool(served[i] >= p.pop[i] - 1e-4), 'allocations': parts})
    return {'metrics': metrics(np.ones(len(oi), dtype=bool), p.total),
        'districts': [{**d, **metrics(p.dd[oi] == d['id'], d['population'])} for d in p.districts],
        'assignments': assignments}


def _api_result(p, v, reference, budget, first, second, cleanup, fallbacks, began):
    # Inherited serialization also validates the exact global candidate IDs and
    # all positive modal allocations on a JSON/vector round trip.
    plan = p.serialize(v, cleanup)
    modal = {mode: _modal_result(p, v, mode) for mode in MODES}
    ref_modal = {mode: _modal_result(p, reference, mode) for mode in MODES}
    travel = _travel_objective(p)
    weighted = float(travel @ v) if p.target else None
    reference_mean = float(travel @ reference) if p.target else None
    annual = p.cost(v); reference_cost = p.cost(reference)
    cost_lower = _finite(first.mip_dual_bound * p.cost_scale + p.material) if first is not None else None
    cost_tol = max(.01, abs(annual) * 1e-9)
    cost_gap = _bound_gap(reference_cost, cost_lower, cost_tol)
    final_gap = _bound_gap(annual, cost_lower, cost_tol)
    travel_lower = _finite(second.mip_dual_bound) if second is not None else None
    travel_gap = _bound_gap(weighted or 0., travel_lower, 1e-7)
    eco, rates = p.h['economics'], p.h['rates']
    r, years = eco['realDiscountRate'], eco['horizonYears']
    annuity = r / (1 - (1 + r) ** -years) if r else 1 / years
    operating = p.s.get('operatingCostMultiplier', 1)
    demand = p.s['demandMultiplier']
    visit_rate = rates.get('visitsPerResident', rates['contactsPerResident']) * demand
    admission_rate = rates.get('admissionsPerResident', 0.) * demand
    loads = {}
    for mode, (_, sj) in p.edges.items():
        f = v[p.offsets[mode]:p.offsets[mode] + len(sj)] * 1000
        loads[mode] = np.bincount(sj, weights=f, minlength=p.m)
    sites = []
    for selected in plan['selected']:
        j = p.local[selected['candidateIndex']]
        t = next(t for t in p.h['templates'] if t['id'] == selected['templateId'])
        assigned = max(loads[mode][j] for mode in MODES)
        # The car allocation is a deterministic accounting partition of ONE
        # annual material bill. Sum of per-site modal maxima would double count.
        material_load = loads['car'][j]
        capex = selected['grossAreaM2'] * eco['buildingUnitCostTRY']
        breakdown = {'fixedSiteTRY': operating * eco['annualFixedSiteCostTRY'],
            'physiciansTRY': operating * selected['doctors'] * eco['annualDoctorCostTRY'],
            'bedSupportTRY': operating * selected['beds'] * eco['annualBedSupportCostTRY'],
            'materialsTRY': operating * material_load * p.contact * eco['costPerContactTRY']}
        contact_capacity = selected['doctors'] * p.s['contactsPerDoctor']
        bed_capacity = selected['beds'] * 365 * p.occupancy
        sites.append({**selected, 'templateLabel': t.get('label', t['id']), 'constructionCostTRY': capex,
            'annualOperatingCostTRY': sum(breakdown.values()),
            'annualEquivalentCostTRY': capex * annuity + sum(breakdown.values()), 'operatingBreakdown': breakdown,
            'assignedPopulation': float(assigned), 'assignedPopulationByMode': {mode: float(loads[mode][j]) for mode in MODES},
            'resourceLoadBasis': 'maximum_of_two_alternative_full_demand_scenarios_not_sum',
            'materialAccountingPopulation': float(material_load), 'materialAccountingBasis': 'car_allocation_partition_of_one_annual_bill',
            'annualVisits': assigned * visit_rate, 'annualContacts': assigned * p.contact,
            'annualAdmissions': assigned * admission_rate, 'annualBedDays': assigned * p.bedrate,
            'contactCapacity': contact_capacity, 'bedDayCapacity': bed_capacity,
            'doctorUtilizationPercent': assigned * p.contact / contact_capacity * 100,
            'bedUtilizationPercent': assigned * p.bedrate / bed_capacity * 100,
            'physicalOccupancyPercent': assigned * p.bedrate / (selected['beds'] * 365) * 100,
            'areaUtilizationPercent': selected['grossAreaM2'] / p.available[j] * 100})
    capex = sum(s['constructionCostTRY'] for s in sites)
    opex = sum(s['annualOperatingCostTRY'] for s in sites)
    if abs(capex * annuity + opex - annual) > max(.01, annual * 1e-12):
        raise RuntimeError('Hybrid single annual bill reconstruction mismatch')
    if annual > budget + max(.01, abs(budget) * 1e-12):
        raise RuntimeError('Hybrid final annual cost exceeds travel-stage budget')
    ref_plan = p.serialize(reference)
    reference_stage = {'hospitalCount': ref_plan['hospitalCount'], 'beds': ref_plan['totalBeds'],
        'doctors': ref_plan['totalDoctors'], 'coveragePercent': p.s['coverageTarget'],
        'annualEquivalentCostTRY': reference_cost, 'meanMinutes': reference_mean,
        'weightedMeanMinutes': reference_mean,
        'modalMeanMinutes': {mode: ref_modal[mode]['metrics']['meanMinutes'] for mode in MODES},
        'gap': cost_gap, 'lowerBoundTRY': cost_lower, 'boundScope': p.search_scope['boundScope'],
        'method': 'Validated cost-stage incumbent after resource-only cleanup; not assumed to be the global minimum.'}
    summary = {'carWeight': 100 * p.modal_weights['car'], 'transitWeight': 100 * p.modal_weights['transit'],
        'weightedMeanMinutes': weighted, 'thresholds': p.modal_thresholds,
        'annualDemandCountedOnce': True, 'twoFullDemandScenarios': True,
        'sameIndividualsAcrossModesConstrained': False,
        'semantics': 'Weights express travel priority only, not observed patient or ambulance shares. Each mode independently serves the full target using shared beds and physicians; annual materials are charged once. No ambulance speed gain is assumed.'}
    return {'status': 'feasible', 'selectedIndices': [s['candidateIndex'] for s in sites],
        'hospitalCount': len(sites), 'metrics': modal['car']['metrics'], 'districts': modal['car']['districts'],
        'assignments': modal['car']['assignments'], 'capacitySites': sites, 'modalResults': modal,
        'hybridSummary': summary, 'hybrid': summary,
        'gap': cost_gap, 'lowerBound': cost_lower, 'secondaryOptimal': bool(second is not None and second.status == 0 and travel_gap is not None and travel_gap <= 1e-8),
        'provenOptimal': False, 'incumbentValidated': True,
        'capacity': {'totalBeds': plan['totalBeds'], 'totalDoctors': plan['totalDoctors'],
            'constructionCostTRY': capex, 'annualOperatingCostTRY': opex, 'annualEquivalentCostTRY': annual,
            'annualMaterialCostTRY': p.material, 'annualDemandCountedOnce': True,
            'lifecyclePresentCostTRY': annual / annuity, 'priceBase': eco.get('priceBase'),
            'horizonYears': years, 'realDiscountRate': r,
            'referenceCostTRY': reference_cost, 'budgetLimitTRY': budget, 'referenceStage': reference_stage,
            'resourceCleanup': cleanup, 'solutionSource': 'hybrid_shared_resource_two_stage_search',
            'numericalFallback': fallbacks or None, 'finalPlanCostGap': final_gap,
            'costBoundNumericalToleranceTRY': cost_tol, 'optimalityScope': p.search_scope['kind'],
            'referenceMeanMinutes': reference_mean,
            'travelImprovementPercent': 100 * (reference_mean - weighted) / reference_mean if reference_mean else 0.,
            'annualVisitsDemand': p.total * visit_rate, 'annualVisitsServed': p.target * visit_rate,
            'annualContactsDemand': p.total * p.contact, 'annualContactsServed': p.target * p.contact,
            'annualAdmissionsDemand': p.total * admission_rate, 'annualBedDaysDemand': p.total * p.bedrate,
            'annualBedDaysServed': p.target * p.bedrate,
            'doctorUtilizationPercent': p.target * p.contact / (plan['totalDoctors'] * p.s['contactsPerDoctor']) * 100 if plan['totalDoctors'] else 0.,
            'bedUtilizationPercent': p.target * p.bedrate / (plan['totalBeds'] * 365 * p.occupancy) * 100 if plan['totalBeds'] else 0.,
            'costStageGap': cost_gap,
            'costStageProvenOptimal': bool(first is not None and first.status == 0 and cost_gap is not None and cost_gap <= 1e-8),
            'travelStageGap': travel_gap, 'travelStageSolverGap': _finite(second.mip_gap) if second is not None else None,
            'travelStageLowerBoundMeanMinutes': travel_lower,
            'travelStageImproved': bool(reference_mean is not None and weighted < reference_mean - 1e-7),
            'planningVersion': p.h.get('version')},
        'searchScope': p.search_scope,
        'solver': {'costNativeStatus': first.message if first is not None else None,
            'travelNativeStatus': second.message if second is not None else None,
            'costStagePerformed': first is not None, 'travelStagePerformed': second is not None,
            'costTimeLimit': bool(first is not None and first.isTimeLimit),
            'travelTimeLimit': bool(second is not None and second.isTimeLimit),
            'costWarmStartAccepted': bool(first is not None and first.warm.get('solverAcceptedFeasibleStart')),
            'travelWarmStartAccepted': bool(second is not None and second.warm.get('solverAcceptedFeasibleStart')),
            'elapsedSeconds': monotonic() - began, 'dimensions': p.dimensions,
            'boundInterpretation': 'Native solver bounds only; limited to the stated candidate/edge scope. Cost and weighted-travel bounds describe different objectives. No minimum hospital-count or real-city optimality certificate.'}}


def solve_hybrid(car_times, transit_times, populations, demand_districts, districts,
                 province_total, planning, scenario, candidates, conflicts=(), time_limit=35):
    """Cost first, then weighted modal mean under a reference-cost allowance.

    The total cooperative allowance includes formulation and seed preparation.
    Missing incumbents remain inconclusive. A full-geometry necessary-condition
    failure is distinct from native infeasibility in a restricted search graph.
    """
    seconds = _number(time_limit, 'time limit', minimum=1e-6, maximum=300)
    began = monotonic(); deadline = began + seconds
    try:
        p = build_hybrid_problem(car_times, transit_times, populations, demand_districts, districts,
            province_total, planning, scenario, candidates, conflicts,
            neighbors=scenario.get('hybridNeighbors', 12))
    except ModelInfeasible as exc:
        return {'status': 'infeasible', 'reason': str(exc), 'selectedIndices': [],
            'hospitalCount': None, 'incumbentValidated': False, 'provenOptimal': False,
            'searchScope': {'kind': 'necessary_conditions_for_supplied_candidates',
                'description': 'Elementary geometry/population/plot check within these supplied matrices and candidates; not a real-Ankara impossibility certificate.'}}
    seed = _greedy_seed(p, min(deadline, monotonic() + min(6., seconds * .2)))
    first = second = None; fallbacks = []
    reference = seed
    remaining = deadline - monotonic()
    if remaining > 0:
        cost_deadline = min(deadline, monotonic() + remaining * .65)
        try:
            first = _native(p.model, cost_deadline - monotonic(), seed, deadline=cost_deadline)
            reference, reason = _candidate(p, first.x, seed, objective=p.c)
            if reason:
                fallbacks.append({'stage': 'cost', 'reason': reason, 'validatedSourcePreserved': seed is not None})
        except TimeoutError as exc:
            fallbacks.append({'stage': 'cost', 'reason': str(exc), 'validatedSourcePreserved': seed is not None})
    if reference is None:
        native_infeasible = first is not None and first.status == 2
        full_scope = not p.search_scope['restricted']
        return {'status': 'infeasible' if native_infeasible and full_scope else 'inconclusive',
            'reason': 'Native solver reports infeasible for the supplied complete model' if native_infeasible and full_scope else 'No independently validated common-resource incumbent within the bounded search',
            'nativeModelStatus': first.message if first is not None else None,
            'nativeReportedInfeasible': native_infeasible, 'independentlyProvenInfeasible': False,
            'selectedIndices': [], 'hospitalCount': None, 'incumbentValidated': False,
            'provenOptimal': False, 'searchScope': p.search_scope, 'elapsedSeconds': monotonic() - began}
    reference, reference_cleanup = p.clean(reference)
    budget = p.cost(reference) * (1 + _number(scenario.get('costTolerance', 10), 'cost tolerance') / 100)
    travel = _travel_objective(p)
    final = reference.copy()
    remaining = deadline - monotonic()
    if remaining > 0 and p.target > 0:
        c, integer, lb, ub, A, lo, hi = p.model
        A = vstack([A, csc_matrix(c.reshape(1, -1))], format='csc')
        model = (travel, integer, lb, ub, A, np.r_[lo, -np.inf], np.r_[hi, (budget - p.material) / p.cost_scale])
        try:
            second = _native(model, remaining, reference, deadline=deadline)
            final, reason = _candidate(p, second.x, reference, objective=travel, budget=budget)
            if reason:
                fallbacks.append({'stage': 'travel', 'reason': reason, 'validatedSourcePreserved': True})
        except TimeoutError as exc:
            fallbacks.append({'stage': 'travel', 'reason': str(exc), 'validatedSourcePreserved': True})
    final, cleanup = p.clean(final)
    cleanup['referenceStageCleanup'] = reference_cleanup
    return _api_result(p, final, reference, budget, first, second, cleanup, fallbacks, began)
