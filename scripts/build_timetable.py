"""Official EGO departures + stop order; explicitly estimated intermediate times.

Coordinates: current OSM stop references first; historical community GTFS only
for otherwise missing bus coordinates. Its calendars/times are NEVER imported.
Vehicle segments follow OSM streets/rails, with no straight-line ride fallback.
"""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix, load_npz, save_npz
from scipy.sparse.csgraph import dijkstra, connected_components
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.geo import normalize, project, permissions, speed
from backend.timetable import PROFILES, DEFAULT_PROFILE, route_batch

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'data/processed';RAW=ROOT/'data/raw';WORK=ROOT/'work/ego-build'


def write_json(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8',newline='\n')


def station_name(name):
    n=normalize(name)
    if n.startswith('DEVLET') and 'ANKARAGUCU' in n:return 'DEVLETANKARAGUCU'
    for part in ('METROISTASYONU','ISTASYONU','METRO','ANKARAY','ISTASYON','1','2'):
        n=n.replace(part,'')
    aliases={'15TEMMUZKIZILAYMILLIIRADE':'KIZILAY','ANADOLUANITKABIR':'ANADOLU','BELEDIYE':'KECIORENBELEDIYESI',
        'GARYHT':'GAR','DEVLETMH90ANKARAGUCU':'DEVLETMAHALLESI','OSBTOREKENT':'OSBTOREKENT',
        'GOP':'GOKCEK','TARIMBAKANLIGIDANISTAY':'TARIMBAKANLIGIDANISTAY'}
    return aliases.get(n,n)


def resolve_note(note,stops):
    """Only unambiguous whole-route or explicit stop-code start/end patterns.

    Never turn a named opposite-terminal departure or detour into a full trip.
    Unknown notes are recorded, excluded, and exposed as missing service.
    """
    n=normalize(re.sub(r'^\d{2}:\d{2}\s*','',note).strip())
    if not n or n in ('GECESERVISI','RING'):
        return 0,len(stops)-1
    refs=re.findall(r'(?<!\d)\d{5}(?!\d)',note)
    ids=[s['id'] for s in stops]
    # Permit only start/end instructions, not an additional unmodelled detour.
    if refs and all(x in ids for x in refs) and not any(x in n for x in ('GIDER','GIRER','GITMEZ','UGRAR','UZAT')):
        if len(refs)==1 and ('BASLA' in n or 'DENHAREKET' in n):return ids.index(refs[0]),len(stops)-1
        if len(refs)==1 and ('BITER' in n or 'SON' in n):return 0,ids.index(refs[0])
        if len(refs)==2 and 'BASLA' in n and 'BITER' in n:
            a,b=ids.index(refs[0]),ids.index(refs[1])
            if a<b:return a,b
    # Exact named rail stations in early morning start instructions.
    if 'BASLA' in n and not refs:
        prefix=re.split('ISTASYON|ISTAYON',n)[0].replace('METRO','')
        hits=[i for i,s in enumerate(stops) if station_name(s['name'])==station_name(prefix)]
        if len(hits)==1:return hits[0],len(stops)-1
    for suffix in ('NDANHAREKETSAATI','NDENHAREKETSAATI','DANHAREKETSAATI','DENHAREKETSAATI',
                   'NDANBASLAR','NDENBASLAR','DANBASLAR','DENBASLAR'):
        if n.endswith(suffix):
            name=n[:-len(suffix)]
            hits=[i for i,s in enumerate(stops) if station_name(s['name'])==station_name(name)]
            if len(hits)==1:return hits[0],len(stops)-1
    return None


def coordinate_registry(official,osm):
    refs=defaultdict(list);stations=[]
    for node in osm['nodes'].values():
        tags=node['tags']
        if tags.get('highway')=='bus_stop' or tags.get('public_transport') in ('platform','stop_position'):
            for ref in re.split(r'[;,]',tags.get('ref','')):
                if ref:refs[ref.strip()].append(node)
        if tags.get('railway') in ('station','halt','stop') or tags.get('station') in ('subway','light_rail'):
            if tags.get('name'):stations.append(node)
    with zipfile.ZipFile(RAW/'ego/community-ankara.zip') as z:
        community={s['stop_id']:s for s in csv.DictReader(io.TextIOWrapper(z.open('stops.txt'),encoding='utf-8-sig'))}
    wanted={s['id']:s for r in official['routes'] for s in r['stops']};result={};missing=[];conflicts=[]
    for code,s in wanted.items():
        options=refs.get(code,[]);source='OSM stop ref';node=None
        if options:
            node=next((x for x in options if x['tags'].get('highway')=='bus_stop'),options[0])
        elif not code.isdigit():
            name=station_name(s['name']);matches=[x for x in stations if station_name(x['tags']['name'])==name]
            if not matches:
                matches=[x for x in stations if min(len(name),len(station_name(x['tags']['name'])))>=5 and
                         (name in station_name(x['tags']['name']) or station_name(x['tags']['name']) in name)]
            if matches:
                hint=community.get(code)
                if hint:
                    xy=project([[float(hint['stop_lon']),float(hint['stop_lat'])]])[0]
                    node=min(matches,key=lambda x:np.linalg.norm(project([[x['lon'],x['lat']]])[0]-xy))
                else:node=matches[0]
                source='OSM station name / official stop identity'
        elif code in community:
            c=community[code];node={'lon':float(c['stop_lon']),'lat':float(c['stop_lat'])};source='Historical community GTFS coordinate; official stop ID'
        if node:
            result[code]={**s,'lon':node['lon'],'lat':node['lat'],'coordinateSource':source}
            if code in community and source.startswith('OSM'):
                c=community[code];dist=float(np.linalg.norm(np.diff(project([[node['lon'],node['lat']],[float(c['stop_lon']),float(c['stop_lat'])]]),axis=0)))
                if dist>300:conflicts.append({'stopId':code,'differenceMeters':round(dist),'chosen':'OSM'})
        else:missing.append(s)
    return result,missing,conflicts


def rail_graph(osm, family):
    nodes={};coords=[];edges={}
    allowed={'rail-A':{'A'},'rail-M123':{'M1','M2','M3'},'rail-M4':{'M4'}}[family]
    ways={str(m['ref']) for r in osm['routes'] if r['tags'].get('route') in ('subway','light_rail') and r['tags'].get('ref') in allowed for m in r['members'] if m['type']=='w'}
    for w in osm['ways'].values():
        if str(w['id']) not in ways or w['tags'].get('railway') not in ('subway','light_rail','rail'):continue
        ids=[]
        for key,ll in zip(w['nodes'],w['geometry']):
            if key not in nodes:nodes[key]=len(coords);coords.append(ll)
            ids.append(nodes[key])
        if len(ids)<2:continue
        lengths=np.linalg.norm(np.diff(project(w['geometry']),axis=0),axis=1)
        for a,b,length in zip(ids[:-1],ids[1:],lengths):
            if a!=b:edges[a,b]=edges[b,a]=max(.01,float(length))
    row,col=np.asarray(list(edges)).T
    return csr_matrix((list(edges.values()),(row,col)),shape=(len(coords),len(coords))),np.array(coords)


def vehicle_mode(route):
    if route['mode']=='bus':return 'drive'
    return 'rail-A' if route['id'].startswith('A') else ('rail-M4' if route['id'].startswith('M4') else 'rail-M123')


def bus_graph(osm):
    nodes={};coords=[];edges={}
    for w in osm['ways'].values():
        t=w['tags']
        if 'highway' not in t or t['highway'] in ('proposed','construction') or len(w['nodes'])<2:continue
        allowed=permissions(t)[0]
        access=t.get('bus',t.get('psv'))
        if access in ('yes','designated','permissive') or t['highway']=='busway':allowed=True
        if access in ('no','private'):allowed=False
        if not allowed:continue
        ids=[]
        for ref,ll in zip(w['nodes'],w['geometry']):
            if ref not in nodes:nodes[ref]=len(coords);coords.append(ll)
            ids.append(nodes[ref])
        one=t.get('oneway:bus',t.get('oneway:psv',t.get('oneway','yes' if t.get('junction')=='roundabout' or t['highway']=='motorway' else 'no')))
        lengths=np.linalg.norm(np.diff(project(w['geometry']),axis=0),axis=1)
        for a,b,length in zip(ids[:-1],ids[1:],lengths):
            if a==b or length<=0:continue
            seconds=float(length/(speed(t)/3.6))
            if one not in ('-1','reverse'):edges[a,b]=min(edges.get((a,b),np.inf),seconds)
            if one not in ('yes','1','true'):edges[b,a]=min(edges.get((b,a),np.inf),seconds)
    row,col=np.asarray(list(edges)).T
    return csr_matrix((list(edges.values()),(row,col)),shape=(len(coords),len(coords))),np.array(coords)


def reconstruct(pred,start,end):
    path=[int(end)]
    for _ in range(len(pred)):
        if path[-1]==start:return path[::-1]
        p=int(pred[path[-1]])
        if p<0:return []
        path.append(p)
    return []


def build():
    WORK.mkdir(parents=True,exist_ok=True)
    official=json.loads((OUT/'ego-official.json').read_text(encoding='utf-8'))
    assert not official['errors']
    with gzip.open(RAW/'ankara-osm.json.gz','rt',encoding='utf-8') as f:osm=json.load(f)
    data=json.loads((OUT/'dataset.json').read_text(encoding='utf-8'));coords=np.load(OUT/'graph-coordinates.npy');xy=project(coords)
    walk=load_npz(OUT/'walk-graph.npz');drive,drive_coords=bus_graph(osm)
    rails={family:rail_graph(osm,family) for family in ('rail-A','rail-M123','rail-M4')}
    registry,missing,conflicts=coordinate_registry(official,osm)
    write_json(WORK/'missing-stops.json',missing)
    for mode,g,c in [('walk',walk,coords),('drive',drive,drive_coords),*((key,*val) for key,val in rails.items())]:
        valid=np.flatnonzero(np.diff(g.indptr)>0)
        if mode.startswith('rail'):
            _,labels=connected_components(g,directed=False)
            sizes=np.bincount(labels[valid]);valid=valid[labels[valid]==sizes.argmax()]
        tree=cKDTree(project(c[valid]))
        for s in registry.values():
            dist,k=tree.query(project([[s['lon'],s['lat']]])[0])
            s[mode+'Node']=int(valid[k]);s[mode+'SnapMeters']=float(dist)
        if mode=='drive':drive_valid,drive_tree=valid,tree
    print('Coordinates',len(registry),'missing',len(missing),Counter(s['coordinateSource'] for s in registry.values()),flush=True)
    # A cache is keyed by the actual source hash, so refreshed inputs cannot reuse stale geometry.
    digest=hashlib.sha256(b'bus-psv-geometry-v2')
    for path in (OUT/'ego-official.json',RAW/'ankara-osm.json.gz',RAW/'ego/community-ankara.zip',OUT/'graph-coordinates.npy'):
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    fingerprint=digest.hexdigest()
    cachepath=WORK/('segments-'+fingerprint[:16]+'.json.gz')
    if cachepath.exists():
        with gzip.open(cachepath,'rt',encoding='utf-8') as f:segments=json.load(f)
    else:segments={}
    pairs=defaultdict(set)
    for r in official['routes']:
        known=[s['id'] for s in r['stops'] if s['id'] in registry]
        mode=vehicle_mode(r)
        for a,b in zip(known[:-1],known[1:]):
            if f'{mode}:{a}:{b}' not in segments:pairs[mode,a].add(b)
    for i,((mode,a),targets) in enumerate(pairs.items()):
        g,c=(drive,drive_coords) if mode=='drive' else rails[mode];s=registry[a]
        maxsnap=300 if mode=='drive' else 600
        if s[mode+'SnapMeters']>maxsnap:continue
        lengths=np.linalg.norm(project([[registry[b]['lon'],registry[b]['lat']] for b in targets])-project([[s['lon'],s['lat']]])[0],axis=1)
        limit=max(300,float(lengths.max())/5) if mode=='drive' else max(3000,float(lengths.max())*4)
        distance,pred=dijkstra(g,indices=s[mode+'Node'],return_predecessors=True,limit=limit)
        if any(not np.isfinite(distance[registry[b][mode+'Node']]) and registry[b][mode+'SnapMeters']<=maxsnap for b in targets):
            distance,pred=dijkstra(g,indices=s[mode+'Node'],return_predecessors=True,limit=7200 if mode=='drive' else 100000)
        for b in targets:
            t=registry[b];value=distance[t[mode+'Node']]
            if t[mode+'SnapMeters']>maxsnap:continue
            path=reconstruct(pred,s[mode+'Node'],t[mode+'Node']) if np.isfinite(value) else []
            geometry=c[path] if path else np.empty((0,2))
            length=float(np.linalg.norm(np.diff(project(geometry),axis=0),axis=1).sum()) if path else np.inf
            euclid=float(np.linalg.norm(project([[s['lon'],s['lat']],[t['lon'],t['lat']]])[1]-project([[s['lon'],s['lat']]])[0]))
            if (not path or length>max(4000,euclid*8)) and mode=='drive':
                # A point-to-nearest-vertex snap can pick the opposite carriageway.
                # Retry nearby road vertices, still traversing directed OSM edges.
                def alternatives(stop):
                    ds,ks=drive_tree.query(project([[stop['lon'],stop['lat']]])[0],k=24)
                    keep=ds<=min(200,ds[0]+100)
                    return drive_valid[ks[keep]],ds[keep]
                starts,_=alternatives(s);ends,end_dist=alternatives(t)
                alt,pr,sources=dijkstra(g,indices=starts,min_only=True,return_predecessors=True,limit=1800)
                k=int(np.argmin(alt[ends]+end_dist/8));end=int(ends[k]);start=int(sources[end])
                if not np.isfinite(alt[end]) or start<0:continue
                newpath=reconstruct(pr,start,end)
                if not newpath:continue
                geometry=c[newpath];value=alt[end]
                length=float(np.linalg.norm(np.diff(project(geometry),axis=0),axis=1).sum())
                if length>max(4000,euclid*8):continue
            if not np.isfinite(value):continue
            # Co-located stop IDs are a zero-distance vertex, with dwell in offsets.
            # No straight line between different locations is invented.
            if len(geometry)==1:geometry=np.repeat(geometry,2,axis=0)
            segments[f'{mode}:{a}:{b}']={'secondsWeight':float(value if mode=='drive' else value/11.11),
                                       'meters':length,'coordinates':geometry.round(6).tolist(),'coLocated':length<.1}
        if i%200==0:print('Vehicle geometry',i,'/',len(pairs),flush=True)
        if i%1000==0:
            with gzip.open(cachepath,'wt',encoding='utf-8') as f:json.dump(segments,f,ensure_ascii=False,separators=(',',':'))
    with gzip.open(cachepath,'wt',encoding='utf-8') as f:json.dump(segments,f,ensure_ascii=False,separators=(',',':'))
    stops=list(registry.values());index={s['id']:i for i,s in enumerate(stops)}
    patterns=[];excluded=[];notes=[];accepted=[];duration_flags=[]
    for r in official['routes']:
        known=[(i,s) for i,s in enumerate(r['stops']) if s['id'] in registry]
        if len(known)<2 or known[0][0]!=0 or known[-1][0]!=len(r['stops'])-1:
            excluded.append({'route':r['id'],'reason':'Missing terminal coordinates'});continue
        mode=vehicle_mode(r);keys=[];bad=False
        for (_,a),(_,b) in zip(known[:-1],known[1:]):
            key=f"{mode}:{a['id']}:{b['id']}"
            if key not in segments:bad=True;break
            keys.append(key)
        if bad or not r['durationMinutes'] or r['durationMinutes']<=0:
            excluded.append({'route':r['id'],'reason':'Missing road/rail segment or duration'});continue
        weights=np.array([segments[k]['secondsWeight']+25 for k in keys])
        total=r['durationMinutes']*60
        # Never compress a path below a physically plausible 90 km/h bus / 80 km/h rail.
        minimum=sum(segments[k]['meters']/(25 if mode=='drive' else 22.222)+10 for k in keys)
        if total<minimum:
            duration_flags.append({'route':r['id'],'publishedMinutes':total/60,'usedMinutes':minimum/60})
            total=minimum
        offsets=np.r_[0,np.cumsum(weights)/sum(weights)*total]
        mapped={old:new for new,(old,_) in enumerate(known)};groups=defaultdict(lambda:{d:[] for d in ('weekday','saturday','sunday')})
        for day,entries in r['departures'].items():
            for entry in entries:
                span=resolve_note(entry['note'],r['stops'])
                if span is None or span[0] not in mapped or span[1] not in mapped:
                    notes.append({'route':r['id'],'day':day,**entry});continue
                a,b=map(mapped.get,span)
                if a>=b:continue
                groups[a,b][day].append(entry['seconds'])
        for (a,b),deps in groups.items():
            if not any(deps.values()):continue
            patterns.append({'id':len(patterns),'route':r['id'],'name':r['name'],'mode':r['mode'],
                'stops':[index[s['id']] for _,s in known[a:b+1]],'offsets':(offsets[a:b+1]-offsets[a]).tolist(),
                'departures':{d:sorted(set(v)) for d,v in deps.items()},'segmentKeys':keys[a:b],
                'sourceUrl':r['url'],'intermediateTimes':'estimated; road/rail weights scaled to published route duration'})
        if groups:accepted.append(r['id'])
        else:excluded.append({'route':r['id'],'reason':'No published departures' if not any(r['departures'].values()) else 'Only unresolved special-service notes'})
    network={'version':'ego-scheduled-v1','stops':stops,'patterns':patterns,'segments':segments}
    with gzip.open(OUT/'ego-network.json.gz','wt',encoding='utf-8') as f:json.dump(network,f,ensure_ascii=False,separators=(',',':'))
    report={'officialRouteCount':len(official['routes']),'officialStopCount':len({s['id'] for r in official['routes'] for s in r['stops']}),
            'routedRouteCount':len(accepted),'patternCount':len(patterns),'coordinateStopCount':len(stops),
            'coordinateSources':dict(Counter(s['coordinateSource'] for s in stops)),
            'missingCoordinates':missing,'coordinateDisagreements':conflicts,'excludedRoutes':excluded,
            'excludedDepartures':notes,'durationAdjustments':duration_flags,
            'usedDepartures':{d:sum(len(p['departures'][d]) for p in patterns) for d in ('weekday','saturday','sunday')},
            'officialDepartures':{d:sum(len(r['departures'][d]) for r in official['routes']) for d in ('weekday','saturday','sunday')},
            'coordinateWarning':'Historical community coordinates are supplementary, not an official current stop-location export.',
            'supplementaryCoordinates':{'url':'https://dl.dropboxusercontent.com/scl/fi/d7u3d00gd85w2qbzedze6/ankara.zip?rlkey=4x8oz2sby5vvqgf1iuaeit70l',
                'sha256':hashlib.sha256((RAW/'ego/community-ankara.zip').read_bytes()).hexdigest()},
            'coLocatedSegmentCount':sum(v.get('coLocated',False) for v in segments.values()),
            'walkingAccessibleStops':sum(s['walkSnapMeters']<=200 for s in stops),
            'excludedNotePolicy':'Unresolved detours, named starting points and opposite-direction notes are not silently treated as full-route trips.'}
    write_json(OUT/'ego-quality.json',report)
    print('Patterns',len(patterns),'accepted routes',len(accepted),'excluded',len(excluded),'unresolved departures',len(notes),flush=True)
    n=len(data['demands']);destinations=data['candidates']+data['hospitals'];m=len(destinations)
    origins=np.array([d['node'] for d in data['demands']]);destnodes=np.array([d['node'] for d in destinations]);stopnodes=np.array([s['walkNode'] for s in stops])
    originsecs=np.array([d['snapMeters']/1.25 for d in data['demands']]);destsecs=np.array([d['accessMeters']/1.25 for d in destinations]);stopsecs=np.array([s['walkSnapMeters']/1.25 for s in stops])
    rows={k:[] for k in ('access','egress','transfers','direct')};cols={k:[] for k in rows};vals={k:[] for k in rows}
    def add(kind,a,b,w):rows[kind].append(int(a));cols[kind].append(int(b));vals[kind].append(float(max(.001,w)))
    walking_key=hashlib.sha256(json.dumps({'walkGraphSha256':hashlib.sha256((OUT/'walk-graph.npz').read_bytes()).hexdigest(),
        'stops':[(s['id'],s['walkNode'],s['walkSnapMeters']) for s in stops],
        'demands':data['demands'],'destinations':destinations},sort_keys=True).encode()).hexdigest()
    marker=WORK/('walking-'+walking_key+'.ok')
    reuse=marker.exists() and all((OUT/f'ego-{k}.npz').exists() for k in rows)
    for j,s in enumerate([] if reuse else stops):
        if s['walkSnapMeters']>200:continue
        distances=dijkstra(walk,indices=s['walkNode'],limit=900)
        cost=distances[origins]+originsecs+stopsecs[j]
        for i in np.flatnonzero(cost<=900):add('access',i,j,cost[i])
        cost=distances[destnodes]+destsecs+stopsecs[j]
        for i in np.flatnonzero(cost<=900):add('egress',j,i,cost[i])
        cost=distances[stopnodes]+stopsecs+stopsecs[j]
        for k in np.flatnonzero((cost<=300)&(stopsecs<=160)):
            if k!=j:add('transfers',j,k,cost[k])
        if j%500==0:print('Walking connections',j,'/',len(stops),flush=True)
    for i,d in enumerate([] if reuse else data['demands']):
        distances=dijkstra(walk,indices=d['node'],limit=7200)
        cost=distances[destnodes]+originsecs[i]+destsecs
        for j in np.flatnonzero(cost<=7200):add('direct',i,j,cost[j])
        if i%200==0:print('Direct walking',i,'/',n,flush=True)
    shapes={'access':(n,len(stops)),'egress':(len(stops),m),'transfers':(len(stops),len(stops)),'direct':(n,m)}
    for kind in rows:
        if not reuse:
            g=csr_matrix((vals[kind],(rows[kind],cols[kind])),shape=shapes[kind]);save_npz(OUT/f'ego-{kind}.npz',g)
    marker.write_text('Built from matching source and destination identities.\n',encoding='utf-8')
    from shapely.geometry import LineString
    features=[]
    for code in accepted:
        pp=[p for p in patterns if p['route']==code];p=pp[0]
        keys=list(dict.fromkeys(k for v in pp for k in v['segmentKeys']))
        features.append({'type':'Feature','properties':{'ref':p['route'],'name':p['name'],'mode':p['mode'],'geometrySource':'OSM modeled between official stops'},
                         'geometry':{'type':'MultiLineString','coordinates':[list(LineString(segments[k]['coordinates']).simplify(.0001).coords) for k in keys]}})
    write_json(OUT/'transit-lines.geojson',{'type':'FeatureCollection','features':features})
    data['metadata'].update({'transitStatus':'official_departures_estimated_stop_times','transitRoutes':len(accepted),'transitStops':len(stops),
        'transitModel':'Resmi EGO kalkış saatleri ve durak sırası; ara durak süreleri tahmini; eksik sefer/konumlar kalite raporunda.',
        'transitAssumptions':{'scheduleAvailable':True,'intermediateStopTimesObserved':False,'maxAccessWalkMinutes':15,'maxTransferWalkMinutes':5,
            'maxDirectWalkMinutes':120,'boardingSlackSeconds':60,'maxTransfers':2,'serviceWindow':'Seçilen normal gün türü ve hareket saati; tatil istisnaları yok.'},
        'transitProfiles':PROFILES,'transitDataQuality':{k:report[k] for k in ('officialRouteCount','officialStopCount','routedRouteCount','coordinateStopCount','usedDepartures','officialDepartures','coordinateSources')},
        'transitVersion':network['version']})
    write_json(OUT/'dataset.json',data)


def matrices():
    with gzip.open(OUT/'ego-network.json.gz','rt',encoding='utf-8') as f:network=json.load(f)
    graphs=[load_npz(OUT/f'ego-{k}.npz') for k in ('access','egress','transfers','direct')]
    for profile in PROFILES:
        path=OUT/f'transit-{profile}-matrix.npz'
        matrix=route_batch(network,*graphs,profile)
        np.savez_compressed(path,minutes=matrix)
        if profile==DEFAULT_PROFILE:np.savez_compressed(OUT/'transit-matrix.npz',minutes=matrix)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--matrices-only',action='store_true');parser.add_argument('--network-only',action='store_true');args=parser.parse_args()
    if not args.matrices_only:build()
    if not args.network_only:matrices()
