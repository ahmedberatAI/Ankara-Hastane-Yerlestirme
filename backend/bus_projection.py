"""Project distant bus stops onto existing directed road edges.

Coordinates are projected meters. Only stops farther than the existing vertex
snap limit are considered. Splitting an edge preserves its original direction,
cost and topology; this module does not create pedestrian or car connections.
"""
from collections import defaultdict
import numpy as np
from scipy.sparse import csr_matrix
from scipy.spatial import cKDTree


PROJECTION_POLICY = {
    'maximumSnapMeters': 300.,
    'ambiguityMeters': .5,
    'scope': 'Bus stops beyond the existing outgoing-vertex snap limit only. '
             'Project onto existing bus edges; preserve direction and cost. '
             'Equally close distinct edges are withheld, never joined. '
             'This does not establish a real boarding entrance or pedestrian access.',
}


def attach_far_bus_stops(graph, xy, points, maximum_snap=300., ambiguity_meters=.5):
    """Return graph, coordinates, attachments and explicit unresolved records.

    Existing node indices and coordinates remain unchanged. New nodes lie on
    one original edge identity; projected coordinates shared by separate edges
    never merge. The two directions of one edge may carry different costs.
    """
    xy = np.asarray(xy, dtype=float)
    if graph.shape != (len(xy), len(xy)) or xy.shape != (len(xy), 2):
        raise ValueError('Bus graph and projected coordinates must have matching dimensions')
    if not np.isfinite(xy).all() or not np.isfinite(graph.data).all() or np.any(graph.data <= 0):
        raise ValueError('Bus graph requires finite coordinates and positive finite edge costs')
    if maximum_snap <= 0 or ambiguity_meters < 0:
        raise ValueError('Invalid bus projection thresholds')
    if not points:
        return graph.copy(), xy.copy(), {}, {}
    source = graph.tocsr(copy=True)
    source.sum_duplicates()
    coo = source.tocoo()
    row, col, cost = coo.row, coo.col, coo.data
    nonself = row != col
    pairs = np.unique(np.sort(np.column_stack([row[nonself], col[nonself]]), axis=1), axis=0)
    a, b = xy[pairs[:, 0]], xy[pairs[:, 1]]
    vector = b - a
    length2 = np.einsum('ij,ij->i', vector, vector)
    keep = length2 > 1e-12
    pairs, a, vector, length2 = pairs[keep], a[keep], vector[keep], length2[keep]
    outgoing = np.flatnonzero(np.diff(source.indptr) > 0)
    if not len(outgoing):
        return source, xy.copy(), {}, {code: {'reason': 'empty_bus_graph'} for code in points}
    tree = cKDTree(xy[outgoing])
    splits = defaultdict(list)
    additions, attached, excluded = [], {}, {}
    for code in sorted(points):
        point = np.asarray(points[code], dtype=float)
        if point.shape != (2,) or not np.isfinite(point).all():
            raise ValueError(f'Invalid projected bus-stop coordinate: {code}')
        node_distance, node_index = tree.query(point)
        original = {'originalNodeSnapMeters': float(node_distance)}
        if node_distance <= maximum_snap:
            attached[code] = {**original, 'node': int(outgoing[node_index]),
                              'snapMeters': float(node_distance), 'changed': False}
            continue
        if not len(pairs):
            excluded[code] = {**original, 'reason': 'no_nonzero_bus_edge'}
            continue
        fraction = np.clip(np.einsum('ij,ij->i', point - a, vector) / length2, 0, 1)
        projected = a + fraction[:, None] * vector
        distance = np.linalg.norm(projected - point, axis=1)
        best = int(distance.argmin())
        nearest = {**original, 'nearestEdgeMeters': float(distance[best])}
        if distance[best] > maximum_snap:
            excluded[code] = {**nearest, 'reason': 'no_bus_edge_within_existing_snap_limit'}
            continue
        tied = np.flatnonzero(distance <= distance[best] + ambiguity_meters)
        if len(tied) > 1:
            excluded[code] = {**nearest, 'reason': 'ambiguous_distinct_bus_edges',
                              'candidateEdges': pairs[tied].tolist()}
            continue
        pair = tuple(int(v) for v in pairs[best])
        f = float(fraction[best])
        if f <= 1e-12:
            node = pair[0]
        elif f >= 1 - 1e-12:
            node = pair[1]
        else:
            existing = [node for value, node in splits[pair] if abs(value - f) < 1e-12]
            if existing:
                node = existing[0]
            else:
                node = len(xy) + len(additions)
                additions.append(projected[best])
                splits[pair].append((f, node))
        attached[code] = {**original, 'node': node, 'edge': list(pair), 'fraction': f,
                          'snapMeters': float(distance[best]), 'changed': True}
    if not splits:
        return source, xy.copy(), attached, excluded
    retained = np.ones(len(row), dtype=bool)
    extra_row, extra_col, extra_cost = [], [], []
    for pair, split_points in splits.items():
        ordered = [(0., pair[0]), *sorted(split_points), (1., pair[1])]
        for u, v in (pair, pair[::-1]):
            matching = (row == u) & (col == v)
            if not matching.any():
                continue
            weight = float(cost[matching][0])
            retained[matching] = False
            chain = ordered if u == pair[0] else ordered[::-1]
            for (f, start), (g, end) in zip(chain[:-1], chain[1:]):
                extra_row.append(start)
                extra_col.append(end)
                extra_cost.append(weight * abs(g - f))
    new_xy = np.vstack([xy, np.asarray(additions)])
    result = csr_matrix((np.r_[cost[retained], extra_cost],
                         (np.r_[row[retained], extra_row], np.r_[col[retained], extra_col])),
                        shape=(len(new_xy), len(new_xy)))
    return result, new_xy, attached, excluded
