"""Explicit departure-window routing; frozen production profiles are never mutated.

The vectorized engine preserves timetable.py's arithmetic and FIFO rules. The
separate heap checker is an independent state/event implementation, not a call
back into that engine. Neither function interprets a profile name as a clock.
"""
from bisect import bisect_left
from collections import defaultdict
import heapq
from time import monotonic

import numpy as np
from scipy.sparse import isspmatrix_csr

BASE_PROFILES = (('weekday-0800', 'weekday', 28800),
                 ('weekday-1000', 'weekday', 36000),
                 ('saturday-1000', 'saturday', 36000),
                 ('sunday-1000', 'sunday', 36000))
OFFSETS = (0, -5, 5, -4, -3, -2, -1, 1, 2, 3, 4)
CONSTANTS = {'horizonSeconds': 7200, 'boardingSlackSeconds': 60, 'maxBoardings': 3}


def profile_grid():
    profiles = []
    for offset in OFFSETS:
        for base, day, start in BASE_PROFILES:
            seconds = start + offset * 60
            profiles.append({'id': f'{day}-{seconds//3600:02d}{seconds%3600//60:02d}',
                             'baseProfileId': base, 'offsetMinutes': offset,
                             'serviceDay': day, 'departureSeconds': seconds,
                             'timeZone': 'Europe/Istanbul'})
    return profiles


def validate_clock(day, start):
    if day not in ('weekday', 'saturday', 'sunday'):
        raise ValueError('Explicit normal service day required')
    if type(start) is not int or not 0 <= start < 86400:
        raise ValueError('Integer seconds within the service day required')


def gate(deadline, clock):
    if deadline is not None and clock() >= deadline:
        raise TimeoutError('Departure routing deadline; partial output is not accepted')


def validate_network(network, access, egress, transfers, direct):
    n = len(network['stops'])
    if not n or access.shape[1] != n or egress.shape[0] != n or transfers.shape != (n, n):
        raise ValueError('Stop dimensions differ')
    if direct.shape != (access.shape[0], egress.shape[1]):
        raise ValueError('Origin/target dimensions differ')
    for matrix in (access, egress, transfers, direct):
        if not isspmatrix_csr(matrix) or not matrix.has_canonical_format:
            raise ValueError('Canonical CSR required')
        if np.any(~np.isfinite(matrix.data)) or np.any(matrix.data < 0):
            raise ValueError('Finite nonnegative walking costs required')
    for pattern in network['patterns']:
        stops, offsets = pattern['stops'], np.asarray(pattern['offsets'], dtype=float)
        if len(stops) != len(offsets) or len(stops) < 2:
            raise ValueError('Ordered pattern stops/offsets required')
        if any(type(i) is not int or not 0 <= i < n for i in stops):
            raise ValueError('Invalid stop index')
        if not np.all(np.isfinite(offsets)) or np.any(offsets < 0) or np.any(np.diff(offsets) < 0):
            raise ValueError('Finite monotone offsets required')
        for day in ('weekday', 'saturday', 'sunday'):
            departures = np.asarray(pattern['departures'][day], dtype=float)
            if np.any(~np.isfinite(departures)) or np.any(departures < 0) or np.any(np.diff(departures) <= 0):
                raise ValueError('Sorted distinct finite departures required')


def route_batch_explicit(network, access, egress, transfers, direct, service_day,
                         departure_seconds, batch_size=96, deadline=None, clock=monotonic):
    validate_clock(service_day, departure_seconds)
    if type(batch_size) is not int or batch_size <= 0:
        raise ValueError('Positive integer batch size required')
    validate_network(network, access, egress, transfers, direct)
    start = departure_seconds; end = start + CONSTANTS['horizonSeconds']
    matrix = np.full(direct.shape, np.inf, dtype=np.float32)
    n = len(network['stops'])
    for first in range(0, access.shape[0], batch_size):
        gate(deadline, clock)
        last = min(first + batch_size, access.shape[0]); size = last - first
        best = np.full((size, n), np.inf); dest = np.full((size, egress.shape[1]), np.inf)
        for local, origin in enumerate(range(first, last)):
            row = access[origin]; best[local, row.indices] = start + row.data
            row = direct[origin]; dest[local, row.indices] = start + row.data
        for _ in range(CONSTANTS['maxBoardings']):
            gate(deadline, clock)
            ride = np.full_like(best, np.inf)
            for pattern in network['patterns']:
                departures = np.asarray(pattern['departures'][service_day], dtype=float)
                if not len(departures): continue
                trip = np.full(size, np.inf)
                for stop, offset in zip(pattern['stops'], pattern['offsets']):
                    np.minimum(ride[:, stop], trip + offset, out=ride[:, stop])
                    idx = np.searchsorted(departures, best[:, stop] + CONSTANTS['boardingSlackSeconds'] - offset, side='left')
                    valid = idx < len(departures)
                    trip[valid] = np.minimum(trip[valid], departures[idx[valid]])
            ride[ride > end] = np.inf
            for j in np.flatnonzero(np.isfinite(ride).any(axis=0)):
                a, b = egress.indptr[j:j+2]; target = egress.indices[a:b]
                if len(target): dest[:, target] = np.minimum(dest[:, target], ride[:, j, None] + egress.data[a:b])
            next_best = np.minimum(best, ride)
            for j in np.flatnonzero(np.isfinite(ride).any(axis=0)):
                a, b = transfers.indptr[j:j+2]; target = transfers.indices[a:b]
                if len(target): next_best[:, target] = np.minimum(next_best[:, target], ride[:, j, None] + transfers.data[a:b])
            best = next_best
        dest[dest > end] = np.inf
        matrix[first:last] = (dest-start)/60
        gate(deadline, clock)
    return matrix


def route_events_explicit(network, access, egress, transfers, direct, origin,
                          service_day, departure_seconds, deadline=None, clock=monotonic):
    """Independent ready/alighted-state event queue, with no chained footpaths."""
    validate_clock(service_day, departure_seconds)
    if type(origin) is not int or not 0 <= origin < access.shape[0]:
        raise ValueError('Origin index out of range')
    validate_network(network, access, egress, transfers, direct)
    occurrences = defaultdict(list)
    for pi, pattern in enumerate(network['patterns']):
        for position, stop in enumerate(pattern['stops']): occurrences[stop].append((pi, position))
    start = departure_seconds; end = start + 7200
    best = np.full((4, 2, len(network['stops'])), np.inf)
    dest = np.full(egress.shape[1], np.inf); heap = []

    def push(boardings, phase, stop, at):
        if at < best[boardings, phase, stop] and at <= end:
            best[boardings, phase, stop] = at
            heapq.heappush(heap, (at, boardings, phase, int(stop)))

    row = access[origin]
    for stop, seconds in zip(row.indices, row.data): push(0, 0, stop, start + seconds)
    row = direct[origin]; dest[row.indices] = start + row.data
    count = 0
    while heap:
        count += 1
        if count % 256 == 1: gate(deadline, clock)
        at, boardings, phase, stop = heapq.heappop(heap)
        if at != best[boardings, phase, stop]: continue
        if phase == 1:
            row = egress[stop]; dest[row.indices] = np.minimum(dest[row.indices], at + row.data)
            if boardings < 3:
                push(boardings, 0, stop, at)
                row = transfers[stop]
                for other, seconds in zip(row.indices, row.data): push(boardings, 0, other, at + seconds)
        elif boardings < 3:
            for pi, position in occurrences[stop]:
                pattern = network['patterns'][pi]; departures = pattern['departures'][service_day]
                k = bisect_left(departures, at + 60 - pattern['offsets'][position])
                if k == len(departures): continue
                trip = departures[k]
                for other, offset in zip(pattern['stops'][position+1:], pattern['offsets'][position+1:]):
                    push(boardings+1, 1, other, trip+offset)
    gate(deadline, clock)
    dest[dest > end] = np.inf
    return (dest-start)/60


def compare_minutes(actual, expected, exact=False):
    if actual.shape != expected.shape or np.any(np.isnan(actual)) or np.any(actual < 0):
        raise ValueError('Invalid matrix shape/values')
    finite = np.isfinite(actual)
    if not np.array_equal(finite, np.isfinite(expected)):
        raise ValueError('Finite/unreachable sets differ')
    difference = float(np.max(np.abs(actual[finite]-expected[finite]), initial=0))
    if (exact and not np.array_equal(actual, expected)) or difference > 2e-5:
        raise ValueError('Routing matrices differ')
    return difference
