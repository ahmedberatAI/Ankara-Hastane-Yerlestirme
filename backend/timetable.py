"""FIFO timetable routing, at most three boardings, one footpath per transfer.

Terminal departures are observed; offsets at intermediate stops are estimates.
The same algorithm serves matrix generation and auditable single-trip traces.
"""
from bisect import bisect_left
from functools import lru_cache
import gzip
import json
from pathlib import Path
import numpy as np
from scipy.sparse import load_npz

DATA=Path(__file__).resolve().parents[1]/'data/processed'
PROFILES={
    'weekday-0800': {'day':'weekday','seconds':8*3600,'label':'Hafta içi · 08.00'},
    'weekday-1000': {'day':'weekday','seconds':10*3600,'label':'Hafta içi · 10.00'},
    'saturday-1000': {'day':'saturday','seconds':10*3600,'label':'Cumartesi · 10.00'},
    'sunday-1000': {'day':'sunday','seconds':10*3600,'label':'Pazar · 10.00'},
}
DEFAULT_PROFILE='weekday-1000'
MAX_SECONDS=7200
BOARD_SLACK=60
MAX_BOARDINGS=3


def route_one(network, access, egress, transfers, direct, origin, profile, destination=None):
    """Earliest arrival with reconstructable legs; CSR absent entries mean INF."""
    p=PROFILES[profile];start=p['seconds'];deadline=start+MAX_SECONDS
    n=len(network['stops']); best=np.full(n,np.inf); traces=[None]*n
    for j,w in zip(access[origin].indices,access[origin].data):
        best[j]=start+w;traces[j]=[{'kind':'access','from':origin,'to':int(j),'seconds':float(w)}]
    arrivals=np.full(egress.shape[1],np.inf); paths=[None]*egress.shape[1]
    for j,w in zip(direct[origin].indices,direct[origin].data):
        arrivals[j]=start+w;paths[j]=[{'kind':'direct','from':origin,'to':int(j),'seconds':float(w)}]
    for _ in range(MAX_BOARDINGS):
        ride=np.full(n,np.inf);ride_paths=[None]*n
        for pattern in network['patterns']:
            departures=pattern['departures'][p['day']]
            if not departures:continue
            trip=np.inf;board_pos=None;prefix=None
            for pos,(stop,offset) in enumerate(zip(pattern['stops'],pattern['offsets'])):
                # Alight BEFORE boarding: a zero-length vehicle ride is not a transfer.
                arrival=trip+offset
                if board_pos is not None and arrival<ride[stop] and arrival<=deadline:
                    ride[stop]=arrival
                    ride_paths[stop]=prefix+[{'kind':'ride','pattern':pattern['id'],
                        'boardPosition':board_pos,'alightPosition':pos,'tripStartSeconds':trip,
                        'departureSeconds':trip+pattern['offsets'][board_pos],'arrivalSeconds':arrival}]
                if np.isfinite(best[stop]):
                    idx=bisect_left(departures,best[stop]+BOARD_SLACK-offset)
                    if idx<len(departures) and departures[idx]<trip:
                        trip=departures[idx];board_pos=pos;prefix=traces[stop]
        # Egress from vehicle arrivals, never via a chain of transfer footpaths.
        for j in np.flatnonzero(np.isfinite(ride)):
            a,b=egress.indptr[j:j+2]; targets=egress.indices[a:b];weights=egress.data[a:b]
            for target,w in zip(targets,weights):
                arrival=ride[j]+w
                if arrival<arrivals[target] and arrival<=deadline:
                    arrivals[target]=arrival
                    paths[target]=ride_paths[j]+[{'kind':'egress','from':int(j),'to':int(target),'seconds':float(w)}]
        next_best=best.copy();next_traces=traces.copy()
        for j in np.flatnonzero(np.isfinite(ride)):
            if ride[j]<next_best[j]:next_best[j]=ride[j];next_traces[j]=ride_paths[j]
            a,b=transfers.indptr[j:j+2]
            for target,w in zip(transfers.indices[a:b],transfers.data[a:b]):
                arrival=ride[j]+w
                if arrival<next_best[target] and arrival<=deadline:
                    next_best[target]=arrival
                    next_traces[target]=ride_paths[j]+[{'kind':'transfer','from':int(j),'to':int(target),'seconds':float(w)}]
        best,traces=next_best,next_traces
    minutes=(arrivals-start)/60
    if destination is None:return minutes,paths
    return float(minutes[destination]),paths[destination]


def route_batch(network, access, egress, transfers, direct, profile, batch_size=96):
    """Vectorized independent origins; no averaging or mixing departure times."""
    p=PROFILES[profile];start=p['seconds'];deadline=start+MAX_SECONDS
    matrix=np.full(direct.shape,np.inf,dtype=np.float32)
    n=len(network['stops'])
    for first in range(0,access.shape[0],batch_size):
        last=min(first+batch_size,access.shape[0]);size=last-first
        best=np.full((size,n),np.inf);dest=np.full((size,egress.shape[1]),np.inf)
        for local,origin in enumerate(range(first,last)):
            row=access[origin];best[local,row.indices]=start+row.data
            row=direct[origin];dest[local,row.indices]=start+row.data
        for _ in range(MAX_BOARDINGS):
            ride=np.full_like(best,np.inf)
            for pattern in network['patterns']:
                departures=np.asarray(pattern['departures'][p['day']],dtype=float)
                if not len(departures):continue
                trip=np.full(size,np.inf)
                for stop,offset in zip(pattern['stops'],pattern['offsets']):
                    np.minimum(ride[:,stop],trip+offset,out=ride[:,stop])
                    idx=np.searchsorted(departures,best[:,stop]+BOARD_SLACK-offset,side='left')
                    valid=idx<len(departures)
                    trip[valid]=np.minimum(trip[valid],departures[idx[valid]])
            ride[ride>deadline]=np.inf
            for j in np.flatnonzero(np.isfinite(ride).any(axis=0)):
                a,b=egress.indptr[j:j+2];target=egress.indices[a:b]
                if len(target):dest[:,target]=np.minimum(dest[:,target],ride[:,j,None]+egress.data[a:b])
            next_best=np.minimum(best,ride)
            for j in np.flatnonzero(np.isfinite(ride).any(axis=0)):
                a,b=transfers.indptr[j:j+2];target=transfers.indices[a:b]
                if len(target):next_best[:,target]=np.minimum(next_best[:,target],ride[:,j,None]+transfers.data[a:b])
            best=next_best
        dest[dest>deadline]=np.inf
        matrix[first:last]=(dest-start)/60
        print(f'{profile}: {last}/{access.shape[0]} origins',flush=True)
    return matrix


@lru_cache(maxsize=1)
def load_network():
    with gzip.open(DATA/'ego-network.json.gz','rt',encoding='utf-8') as f:network=json.load(f)
    return (network,*(load_npz(DATA/f'ego-{name}.npz') for name in ('access','egress','transfers','direct')))


def journey(origin,destination,profile=DEFAULT_PROFILE):
    return route_one(*load_network(),origin,profile,destination)
