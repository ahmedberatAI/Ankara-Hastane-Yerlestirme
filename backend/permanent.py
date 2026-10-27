"""One permanent shared-resource plan for car and four dated transit profiles.

Only the policy below is public. Five complete demand scenarios share locations,
bed modules and integer physicians; the annual material bill is charged once.
The pure generic row builder preserves the frozen joint formulation. No frozen
module is patched, and native bounds only describe the retained search graph.
"""
import math
from hashlib import sha256
from time import monotonic
import numpy as np
from scipy.sparse import coo_matrix, csc_matrix, vstack
from backend.joint_model import JointProblem, ModelInfeasible, AREA_TOL
from backend.hybrid import _number, _native, _fit, _candidate, _finite, _bound_gap, _modal_result
from backend.joint_travel import one_profile

PROFILES = ('car', 'weekday-0800', 'weekday-1000', 'saturday-1000', 'sunday-1000')
FIXED_POLICY = {'threshold': 30, 'transitThreshold': 60, 'coverageTarget': 95,
    'districtFloor': 80, 'contactsPerDoctor': 2140, 'bedOccupancy': 80,
    'demandMultiplier': 1, 'operatingCostMultiplier': 1, 'costTolerance': 10,
    'trafficFactor': 1, 'hospitalLimit': None, 'carWeight': 70}
WEIGHTS = {'car': .7, **{name: .075 for name in PROFILES[1:]}}


def policy_values(policy):
    """Reject silent policy changes; presentation/provenance metadata may coexist."""
    if not isinstance(policy, dict):
        raise ValueError('Policy must be a mapping')
    values = dict(policy)
    if 'profileIds' in values and values['profileIds'] != list(PROFILES):
        raise ValueError('Permanent policy fixes the five ordered profile identities')
    for name, expected in FIXED_POLICY.items():
        value = values.get(name, expected)
        if expected is None:
            if value is not None: raise ValueError('Permanent policy fixes ' + name)
        elif _number(value, name) != expected:
            raise ValueError('Permanent policy fixes ' + name)
        values[name] = expected
    return values


def build_permanent_problem(profile_times, populations, demand_districts, districts,
        province_total, planning, policy, candidates, conflicts=(), *, car_neighbors=12):
    """All known PT edges; optionally nearest car edges per plot-radius class.

    Routing matrices can themselves be shortlisted. Neither this builder nor a
    native infeasibility report certifies unqueried MOTIS pairs or the real city.
    """
    scenario = policy_values(policy)
    if not isinstance(profile_times, dict) or tuple(profile_times) != PROFILES:
        raise ValueError('Exactly five canonical ordered profiles are required')
    if car_neighbors is not None and (isinstance(car_neighbors, bool) or not isinstance(car_neighbors, int) or car_neighbors < 1):
        raise ValueError('Car neighbors must be a positive integer or None')
    matrices = {}
    thresholds = {name: scenario['threshold'] if name == 'car' else scenario['transitThreshold'] for name in PROFILES}
    for name, raw in profile_times.items():
        t = np.asarray(raw, dtype=float)
        if t.shape != (len(populations), len(candidates)) or np.any(np.isnan(t)) or np.any(t < 0):
            raise ValueError('Invalid ' + name + ' matrix')
        matrices[name] = np.where(t <= thresholds[name], t, np.inf)
    all_edges = {name: int(np.isfinite(t).sum()) for name, t in matrices.items()}
    # All profile necessary conditions are checked before optional edge pruning.
    pop = np.asarray(populations, float); dd = np.asarray(demand_districts)
    total = _number(province_total, 'province population', minimum=1e-12)
    if pop.ndim != 1 or dd.shape != pop.shape or np.any(~np.isfinite(pop)) or np.any(pop < 0):
        raise ValueError('Invalid population')
    ids = [d['id'] for d in districts]
    denoms = [_number(d['population'], 'district population', minimum=1e-12) for d in districts]
    if (len(set(ids)) != len(ids) or not set(dd).issubset(ids)
            or not math.isclose(sum(denoms), total, rel_tol=1e-10, abs_tol=1e-6)
            or pop.sum() > total + 1e-6
            or any(pop[dd == d['id']].sum() > d['population'] + 1e-6 for d in districts)):
        raise ValueError('Invalid district identities or population denominators')
    for name, t in matrices.items():
        reachable = np.isfinite(t).any(axis=1)
        if (pop[reachable].sum() < total * .95 - 1e-6 or any(
                pop[reachable & (dd == d['id'])].sum() < d['population'] * .8 - 1e-6 for d in districts)):
            raise ModelInfeasible('Known supplied edges fail necessary geographic targets in ' + name)
    radii = np.array([_number(c['footprintRadiusMeters'], 'plot radius', minimum=1e-12) for c in candidates])
    if car_neighbors is not None:
        t = matrices['car']; retained = np.zeros(t.shape, bool)
        for radius in np.unique(radii):
            columns = np.flatnonzero(radii == radius)
            for i in range(len(pop)):
                legal = columns[np.isfinite(t[i, columns])]
                chosen = legal[np.argsort(t[i, legal], kind='stable')[:car_neighbors]]
                retained[i, chosen] = True
        matrices['car'] = np.where(retained, t, np.inf)
    internal = dict(scenario, threshold=max(thresholds.values()))
    p = _build_profiles(matrices, populations, demand_districts, districts, total,
                        candidates, planning, internal, tuple(tuple(x) for x in conflicts))
    p.modal_weights = dict(WEIGHTS); p.modal_thresholds = thresholds; p.policy = scenario
    kept = {name: len(p.edges[name][0]) for name in PROFILES}
    restricted = kept != all_edges
    p.search_scope = {'kind': 'restricted_car_edges_all_supplied_transit_edges' if restricted else 'all_supplied_allocation_edges',
        'carNeighborsPerOriginFootprintClass': car_neighbors,
        'allCandidateCount': len(candidates), 'retainedCandidateCount': len(candidates),
        'candidateIndices': list(map(int, p.ids)), 'restricted': restricted,
        'allLegalEdgesByProfile': all_edges, 'retainedEdgesByProfile': kept,
        'boundScope': 'supplied_candidate_pool_and_retained_five_profile_edges',
        'allKnownTransitEdgesRetained': True, 'unqueriedTransitPairsAreNotCertifiedUnreachable': True,
        'description': 'Five full-demand profiles; all supplied legal transit edges and the stated car-edge subset. Upstream MOTIS query shortlists remain a separate limitation. No real-city or minimum-hospital-count optimality certificate.'}
    return p

def _build_profiles(profile_times,populations,demand_districts,districts,province_total,
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
    if not districts or not candidates or not isinstance(profile_times, dict) or not len(profile_times):
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


def _greedy_seed(p, deadline):
    """Bounded shared-resource opening heuristic, independently validated.

    Per-profile quota allocation remains separate. This seed is not a minimum-cost
    or hospital-count result, and failure says nothing about feasibility.
    """
    v = np.zeros(len(p.c))
    if p.target == 0:
        p.validate(v)
        return v
    district_index = {d['id']: i for i, d in enumerate(p.districts)}
    di = np.array([district_index[d] for d in p.dd])
    rem = {mode: p.pop.copy() for mode in p.times}
    quota = {mode: np.array([d['population'] * p.s['districtFloor'] / 100 for d in p.districts]) for mode in p.times}
    need = {mode: p.target for mode in p.times}
    loads = {mode: np.zeros(p.m) for mode in p.times}
    groups = {}
    for mode in p.times:
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
        proposed = {mode: preview(mode, j, ceiling[j] - loads[mode][j], floor_phase) for mode in p.times}
        gain = {mode: float(proposed[mode][1].sum()) for mode in p.times}
        if sum(gain.values()) <= 1e-9:
            return None
        option = _fit(p, j, max(loads[mode][j] + gain[mode] for mode in p.times))
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
            if all((quota[mode].sum() if floor_phase else need[mode]) <= 1e-8 for mode in p.times):
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
        if any((quota[mode].sum() if floor_phase else need[mode]) > 1e-8 for mode in p.times):
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


def _fixed_travel(p, source, deadline, *, per_profile_seconds=3.):
    """Five separable assignment LPs on one validated fixed resource design.

    Incomplete or numerical LPs keep their own complete source assignment.
    Bounds belong to these fixed resources, never to the location MILP.
    """
    p.validate(source)
    current = source.copy(); records = []
    for profile in p.times:
        record, updated = one_profile(p, current, profile,
            min(deadline, monotonic() + per_profile_seconds), clock=monotonic)
        # Defense in depth around the reused generic LP helper.
        p.validate(updated)
        if not np.array_equal(updated[:p.nf], source[:p.nf]):
            raise RuntimeError('Fixed-resource LP changed a location, bed type or physician count')
        if _travel_objective(p) @ updated > _travel_objective(p) @ current + 1e-10:
            raise RuntimeError('Fixed-resource LP worsened weighted travel')
        if record['sourceFallback'] and not np.array_equal(updated, current):
            raise RuntimeError('Unknown fixed-resource LP changed its validated source')
        current = updated; records.append(record)
    return current, {'profiles': records, 'allProfilesAccepted': all(r['accepted'] for r in records),
        'resourcePrefixSHA256': sha256(source[:p.nf].tobytes()).hexdigest(),
        'sourceAnnualCostTRY': p.cost(source), 'finalAnnualCostTRY': p.cost(current),
        'resourcesUnchanged': True, 'annualCostUnchanged': True,
        'additionalBudgetTRY': 0., 'wholeJointTravelOptimumProven': False,
        'scope': 'Five independent allocation LPs on these exact shared resources and retained edges; native location/travel bounds are separate.'}


def _api_result(p, v, reference, budget, first, second, cleanup, fallbacks, began, lp_stages):
    # Inherited serialization also validates the exact global candidate IDs and
    # all positive modal allocations on a JSON/vector round trip.
    plan = p.serialize(v, cleanup)
    plan.pop('secondTravelStageImplemented', None)
    plan['profileReassignmentPerformed'] = not np.array_equal(v[p.nf:], reference[p.nf:])
    modal = {mode: _modal_result(p, v, mode) for mode in p.times}
    ref_modal = {mode: _modal_result(p, reference, mode) for mode in p.times}
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
        assigned = max(loads[mode][j] for mode in p.times)
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
            'assignedPopulation': float(assigned), 'assignedPopulationByProfile': {mode: float(loads[mode][j]) for mode in p.times},
            'resourceLoadBasis': 'maximum_of_five_alternative_full_demand_scenarios_not_sum',
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
        raise RuntimeError('Permanent single annual bill reconstruction mismatch')
    if annual > budget + max(.01, abs(budget) * 1e-12):
        raise RuntimeError('Permanent final annual cost exceeds travel-stage budget')
    ref_plan = p.serialize(reference)
    reference_stage = {'hospitalCount': ref_plan['hospitalCount'], 'beds': ref_plan['totalBeds'],
        'doctors': ref_plan['totalDoctors'], 'coveragePercent': p.s['coverageTarget'],
        'annualEquivalentCostTRY': reference_cost, 'meanMinutes': reference_mean,
        'weightedMeanMinutes': reference_mean,
        'modalMeanMinutes': {mode: ref_modal[mode]['metrics']['meanMinutes'] for mode in p.times},
        'gap': cost_gap, 'lowerBoundTRY': cost_lower, 'boundScope': p.search_scope['boundScope'],
        'method': 'Validated cost-stage incumbent after resource-only cleanup; not assumed to be the global minimum.'}
    summary = {'carWeight': 100 * p.modal_weights['car'], 'transitWeight': 100 * sum(p.modal_weights[name] for name in PROFILES[1:]),
        'weightedMeanMinutes': weighted, 'thresholds': p.modal_thresholds,
        'annualDemandCountedOnce': True, 'fullDemandScenarioCount': 5,
        'sameIndividualsAcrossModesConstrained': False,
        'semantics': 'Weights express travel priority only, not observed patient or ambulance shares. Each mode independently serves the full target using shared beds and physicians; annual materials are charged once. No ambulance speed gain is assumed.'}
    critical = min(PROFILES[1:], key=lambda name: (-modal[name]['metrics']['meanMinutes'], name))
    summary.update(profileWeights=dict(p.modal_weights), criticalTransitProfile=critical,
        criticalTransitSelection='maximum_of_four_population_weighted_profile_means',
        criticalTransitTieBreak='ascending_profile_id', profileCount=5, transitProfileCount=4,
        meanTransitMinutes=sum(modal[name]['metrics']['meanMinutes'] for name in PROFILES[1:]) / 4,
        worstTransitMeanMinutes=modal[critical]['metrics']['meanMinutes'],
        minimumProvinceCoveragePercent=min(x['metrics']['coveragePercent'] for x in modal.values()),
        minimumDistrictCoveragePercent=min(d['coveragePercent'] for x in modal.values() for d in x['districts']),
        allFiveHardTargetsValidated=True, sameIndividualsAcrossProfilesConstrained=False)
    return {'status': 'feasible', 'selectedIndices': [s['candidateIndex'] for s in sites],
        'hospitalCount': len(sites), 'metrics': modal['car']['metrics'], 'districts': modal['car']['districts'],
        'assignments': modal['car']['assignments'], 'capacitySites': sites, 'modalResults': {'car': modal['car'], 'transit': modal[critical]},
        'permanentSummary': summary, 'criticalTransitProfile': critical, 'profiles': modal,
        'commonPlan': {key: plan[key] for key in ('selected', 'profiles', 'hospitalCount',
            'totalBeds', 'totalDoctors', 'annualEquivalentCostTRY', 'annualMaterialCostTRY',
            'annualFixedResourceCostTRY')},
        'policy': dict(p.policy), 'fixedResourceTravelStages': lp_stages,
        'gap': cost_gap, 'lowerBound': cost_lower, 'secondaryOptimal': False,
        'provenOptimal': False, 'incumbentValidated': True,
        'capacity': {'totalBeds': plan['totalBeds'], 'totalDoctors': plan['totalDoctors'],
            'constructionCostTRY': capex, 'annualOperatingCostTRY': opex, 'annualEquivalentCostTRY': annual,
            'annualMaterialCostTRY': p.material, 'annualDemandCountedOnce': True,
            'lifecyclePresentCostTRY': annual / annuity, 'priceBase': eco.get('priceBase'),
            'horizonYears': years, 'realDiscountRate': r,
            'referenceCostTRY': reference_cost, 'budgetLimitTRY': budget, 'referenceStage': reference_stage,
            'resourceCleanup': cleanup, 'solutionSource': 'permanent_five_profile_cost_then_weighted_travel',
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
            'costStageProvenOptimal': False,
            'costStageNativeReportedOptimal': bool(first is not None and first.status == 0),
            'travelStageGap': travel_gap, 'travelStageNativeReportedOptimal': bool(second is not None and second.status == 0), 'travelStageSolverGap': _finite(second.mip_gap) if second is not None else None,
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


def solve_permanent(profile_times, populations, demand_districts, districts,
        province_total, planning, policy, candidates, conflicts=(), time_limit=180):
    """Bounded fixed-policy search, never an automatic UI-view recomputation.

    The cooperative total includes building, seeding and LP validation. A caller
    needing a hard wall-clock cap must additionally isolate this operation in a
    process. No feasible label is returned without five complete checked flows.
    """
    seconds = _number(time_limit, 'time limit', minimum=1e-6, maximum=180)
    began = monotonic(); deadline = began + seconds
    # Search controls are implementation choices, not user policy controls.
    try:
        p = build_permanent_problem(profile_times, populations, demand_districts, districts,
            province_total, planning, policy, candidates, conflicts)
    except ModelInfeasible as exc:
        return {'status': 'inconclusive', 'reason': str(exc), 'selectedIndices': [],
            'hospitalCount': None, 'incumbentValidated': False, 'provenOptimal': False,
            'representedSupportNecessaryFailure': True, 'nativeReportedInfeasible': False,
            'independentlyProvenRealCityInfeasible': False,
            'searchScope': {'kind': 'necessary_conditions_for_supplied_edges',
                'description': 'The supplied edge/plot model fails a necessary condition. Unqueried MOTIS pairs are unknown; this is not a real-city impossibility certificate.'}}
    seed_deadline = min(deadline, monotonic() + min(18., seconds * .15))
    seed = _greedy_seed(p, seed_deadline)
    first = second = None; fallbacks = []; lp_stages = []
    if seed is not None:
        p.validate(seed)
        # Better allocations can reduce redundant resources before the cost
        # MIP, while already furnishing a valid five-profile native start.
        limit = min(deadline, monotonic() + min(12., seconds * .08))
        seed, record = _fixed_travel(p, seed, limit)
        record['stage'] = 'seed_fixed_resources'; lp_stages.append(record)
        seed, _ = p.clean(seed)
    reference = seed
    remaining = deadline - monotonic()
    if remaining > 0:
        cost_deadline = min(deadline, monotonic() + remaining * .65)
        try:
            first = _native(p.model, cost_deadline - monotonic(), seed, deadline=cost_deadline)
            if first.status == 2 and seed is not None:
                raise RuntimeError('Native cost infeasibility contradicts a validated five-profile start')
            reference, reason = _candidate(p, first.x, seed, objective=p.c)
            if reason:
                fallbacks.append({'stage': 'cost', 'reason': reason, 'validatedSourcePreserved': seed is not None})
        except TimeoutError as exc:
            fallbacks.append({'stage': 'cost', 'reason': str(exc), 'validatedSourcePreserved': seed is not None})
    if reference is None:
        return {'status': 'inconclusive', 'reason': 'No validated five-profile common-resource plan within this bounded search',
            'selectedIndices': [], 'hospitalCount': None, 'incumbentValidated': False, 'provenOptimal': False,
            'nativeReportedInfeasible': bool(first is not None and first.status == 2),
            'nativeModelStatus': first.message if first is not None else None,
            'independentlyProvenRealCityInfeasible': False,
            'searchScope': p.search_scope, 'elapsedSeconds': monotonic() - began}
    reference, reference_cleanup = p.clean(reference)
    budget = p.cost(reference) * (1 + p.policy['costTolerance'] / 100)
    travel = _travel_objective(p); final = reference.copy()
    # Preserve a budget-free travel improvement even when the location MIP
    # later spends its whole allowance at the root node without an incumbent.
    remaining = deadline - monotonic()
    if remaining > 0:
        final, record = _fixed_travel(p, final, min(deadline, monotonic() + min(12., remaining * .25)))
        record['stage'] = 'reference_fixed_resources'; lp_stages.append(record)
    remaining = deadline - monotonic()
    reserve = min(12., max(0., remaining * .2))
    if remaining - reserve > 0:
        native_deadline = deadline - reserve
        c, integer, lb, ub, A, lo, hi = p.model
        A = vstack([A, csc_matrix(c.reshape(1, -1))], format='csc')
        model = (travel, integer, lb, ub, A, np.r_[lo, -np.inf], np.r_[hi, (budget - p.material) / p.cost_scale])
        try:
            second = _native(model, native_deadline - monotonic(), final, deadline=native_deadline)
            if second.status == 2:
                raise RuntimeError('Native weighted-travel infeasibility contradicts a validated budget-feasible start')
            final, reason = _candidate(p, second.x, final, objective=travel, budget=budget)
            if reason:
                fallbacks.append({'stage': 'weighted_travel', 'reason': reason, 'validatedSourcePreserved': True})
        except TimeoutError as exc:
            fallbacks.append({'stage': 'weighted_travel', 'reason': str(exc), 'validatedSourcePreserved': True})
    if monotonic() < deadline:
        final, record = _fixed_travel(p, final, deadline)
        record['stage'] = 'final_fixed_resources'; lp_stages.append(record)
    final, cleanup = p.clean(final)
    cleanup['referenceStageCleanup'] = reference_cleanup
    p.validate(final)
    return _api_result(p, final, reference, budget, first, second, cleanup, fallbacks, began, lp_stages)

