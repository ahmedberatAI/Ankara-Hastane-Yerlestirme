"""Official EGO departures + stop order; explicitly estimated intermediate times.

Coordinates: current official EGO stop queries first, then OSM stop references;
historical community GTFS only for otherwise missing bus coordinates, subject to
source-consistency gates. Its calendars/times are NEVER imported.
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
from backend.geo import normalize, project, permissions, speed, PROJECT
from backend.timetable import PROFILES, DEFAULT_PROFILE, route_batch

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'data/processed';RAW=ROOT/'data/raw';WORK=ROOT/'work/ego-build'
GEOMETRY_ENGINE='bus-psv-geometry-v3-quality-gates'
GEOMETRY_POLICY={
    'coordinateDistrictToleranceMeters':3000,
    'straightStopChainMaxPublishedDistanceRatio':1.5,
    'routedPathMaxPublishedDistanceRatio':2.0,
    'distanceToleranceMeters':2000,
    'scope':'Conservative source-consistency gates, not measured route accuracy. '
            'A conflict does not establish which source is wrong; unresolved data is quarantined, not relocated.',
}


def write_json(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8',newline='\n')


def validate_coordinate_districts(registry,district_geojson):
    """Do not use a supplementary coordinate far outside its official address.

    Administrative addresses can be stale. Current OSM coordinates therefore
    remain warnings; an unverified historical fallback is withheld on conflict.
    This does not replace either source with an inferred location.
    """
    from shapely.geometry import shape, Point
    from shapely.ops import transform
    polygons={normalize(f['properties']['name']):transform(PROJECT.transform,shape(f['geometry']))
              for f in district_geojson['features']}
    retained=dict(registry);conflicts=[];missing=[];matched=0
    for code,stop in registry.items():
        address=normalize(stop.get('address','')).removesuffix('ANKARA')
        names=[name for name in polygons if address.endswith(name)]
        if len(names)!=1:continue
        matched+=1;name=names[0]
        x,y=PROJECT.transform(stop['lon'],stop['lat'])
        outside=float(polygons[name].distance(Point(x,y)))
        if outside<=GEOMETRY_POLICY['coordinateDistrictToleranceMeters']:continue
        quarantine=stop['coordinateSource'].startswith('Historical community')
        record={'stopId':code,'name':stop['name'],'address':stop.get('address',''),
                'declaredDistrict':name,'outsideDistrictMeters':round(outside),
                'coordinateSource':stop['coordinateSource'],'coordinates':[stop['lon'],stop['lat']],
                'action':'quarantined supplementary coordinate' if quarantine else 'retained current-source coordinate; address conflict needs review'}
        conflicts.append(record)
        if quarantine:
            retained.pop(code)
            missing.append({'id':code,'name':stop['name'],'address':stop.get('address',''),
                            'reason':'Historical coordinate conflicts with official district address; no replacement inferred'})
    return retained,missing,{'matchedStopCount':matched,'quarantinedCoordinateCount':len(missing),'conflicts':conflicts}


def route_geometry_check(route,known,registry,keys,segments):
    """Quarantine grossly inconsistent geometry before calibrating its times.

    The straight stop chain is a distance lower bound, not a substitute route.
    Wide, declared tolerances allow rounding and source-definition differences;
    passing these gates must never be described as route-location validation.
    """
    points=project([[registry[s['id']]['lon'],registry[s['id']]['lat']] for _,s in known])
    straight=float(np.linalg.norm(np.diff(points,axis=0),axis=1).sum())
    routed=float(sum(segments[k]['meters'] for k in keys))
    published=float(route.get('distanceKm') or 0)*1000
    reasons=[]
    if published>0:
        for value,ratio,label in ((straight,GEOMETRY_POLICY['straightStopChainMaxPublishedDistanceRatio'],'stop coordinate chain'),
                                  (routed,GEOMETRY_POLICY['routedPathMaxPublishedDistanceRatio'],'modeled road/rail path')):
            if value>max(published*ratio,published+GEOMETRY_POLICY['distanceToleranceMeters']):
                reasons.append(label+' exceeds published-distance consistency gate')
    return {'route':route['id'],'publishedMeters':published or None,'straightStopChainMeters':round(straight),
            'routedMeters':round(routed),'straightToPublishedRatio':straight/published if published else None,
            'routedToPublishedRatio':routed/published if published else None,
            'status':'quarantined' if reasons else ('passed consistency gates' if published else 'published distance unavailable'),
            'reasons':reasons}


def allocate_segment_times(segment_meters,segment_weights,published_seconds,mode):
    """Preserve a physical minimum on EVERY segment, then allocate spare time.

    Scaling one total previously produced individual 149 km/h bus segments.
    Terminal duration is preserved when feasible; any increase is auditable.
    """
    meters=np.asarray(segment_meters,dtype=float);weights=np.asarray(segment_weights,dtype=float)
    if (meters.ndim!=1 or weights.shape!=meters.shape or not len(meters) or
        not np.isfinite(meters).all() or not np.isfinite(weights).all() or
        np.any(meters<0) or np.any(weights<=0) or not np.isfinite(published_seconds) or published_seconds<=0):
        raise ValueError('Finite nonnegative segment lengths and positive weights/duration required')
    maximum_mps=(90 if mode=='drive' else 80)/3.6
    minimum=meters/maximum_mps+10
    total=max(float(published_seconds),float(minimum.sum()))
    durations=minimum+(total-minimum.sum())*weights/weights.sum()
    return np.r_[0,np.cumsum(durations)],float(minimum.sum())


def timing_segment_meters(segment):
    # Two distinct stop coordinates can snap to the same road vertex. The
    # Euclidean distance is only a physical lower bound, never a ride geometry.
    return max(segment['meters'],segment.get('endpointDistanceMeters',segment['meters']))


def nearby_bus_vertices(tree,valid,stop):
    if not len(valid):return np.array([],dtype=int),np.array([],dtype=float)
    ds,ks=tree.query(PROJECT.transform(stop['lon'],stop['lat']),k=min(24,len(valid)))
    ds=np.atleast_1d(ds);ks=np.atleast_1d(ks)
    keep=np.isfinite(ds)&(ds<=min(200,ds[0]+100))
    return valid[ks[keep]],ds[keep]


def walking_cache_valid(metadata_path,input_key,paths):
    """A key marker alone cannot detect A->B->A with shared output filenames."""
    try:
        metadata=json.loads(metadata_path.read_text(encoding='utf-8'))
        if metadata['inputKey']!=input_key:return False
        return all(metadata['sha256'][name]==hashlib.sha256(path.read_bytes()).hexdigest()
                   for name,path in paths.items())
    except (OSError,ValueError,KeyError,TypeError):
        return False


def record_walking_cache(metadata_path,input_key,paths):
    metadata={'inputKey':input_key,'sha256':{name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in paths.items()}}
    temporary=metadata_path.with_suffix('.tmp')
    write_json(temporary,metadata)
    temporary.replace(metadata_path)


def station_name(name):
    n=normalize(name)
    if n.startswith('DEVLET') and 'ANKARAGUCU' in n:return 'DEVLETANKARAGUCU'
    for part in ('METROISTASYONU','ISTASYONU','METRO','ANKARAY','ISTASYON','1','2'):
        n=n.replace(part,'')
    aliases={'15TEMMUZKIZILAYMILLIIRADE':'KIZILAY','ANADOLUANITKABIR':'ANADOLU','BELEDIYE':'KECIORENBELEDIYESI',
        'GARYHT':'GAR','DEVLETMH90ANKARAGUCU':'DEVLETMAHALLESI','OSBTOREKENT':'OSBTOREKENT',
        'GOP':'GOKCEK','TARIMBAKANLIGIDANISTAY':'TARIMBAKANLIGIDANISTAY'}
    return aliases.get(n,n)


def resolve_note_details(note,stops,departure_seconds=None):
    """Match conservative stop-span patterns and reject known unresolved clauses.

    A column clock and a different clock inside the note have uncertain roles.
    Neither silently overrides the other. Such service is unknown, not absent.
    This is not a general Turkish grammar or a date-specific service calendar;
    stop-name text around explicit IDs still requires source-level review.
    """
    clocks=[]
    for match in re.finditer(r'(?<!\d)(\d{1,2}):(\d{2})(?!\d)',note):
        hour,minute=int(match[1]),int(match[2])
        clocks.append(hour*3600+minute*60 if hour<=29 and minute<60 else None)
    def result(span=None,reason=None):
        return {'span':span,'reason':reason,'columnSeconds':departure_seconds,'noteClockSeconds':clocks}
    if not stops:return result(reason='missing_stop_sequence')
    if None in clocks:return result(reason='invalid_note_clock')
    if len(clocks)>1:return result(reason='multiple_note_clocks_require_separate_service_semantics')
    body=note.strip()
    if clocks:
        if departure_seconds is None:return result(reason='note_clock_requires_column_clock_context')
        if clocks[0]!=departure_seconds:return result(reason='note_clock_conflicts_with_column_clock')
        match=re.match(r'^(?:U[ÇC]\s*)?\d{1,2}:\d{2}\s*',body,re.IGNORECASE)
        if not match:return result(reason='embedded_clock_role_unresolved')
        body=body[match.end():]
    n=normalize(body)
    if not n or n in ('GECESERVISI','RING'):return result((0,len(stops)-1))
    # Keep word boundaries here: OKUL, PAZAR and MAYIS alone can belong to
    # actual stop names (school, market or 19 Mayis Cd.), not calendar rules.
    words=' '.join(normalize(token) for token in re.findall(r'\w+',body))
    if (re.search(r'\b(?:SADECE|YALNIZ|YALNIZCA|HARIC\w*|DISINDA|KOSULUYLA|HALINDE|'
                  r'GUNU|GUNLERI|GUNLERINDE|GUNUNDEN|GUNUNE|TARIH\w*|ITIBAREN|'
                  r'BAYRAM\w*|TATIL\w*)\b',words) or
        re.search(r'\b(?:HAFTA ICI|HAFTA SONU|EGITIM OGRETIM|OKULLAR AC\w*|OKULLAR KAPA\w*)\b',words) or
        re.search(r'(?<!\d)(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}[./-]\d{1,2}[./-]\d{1,2})(?!\d)',body)):
        return result(reason='conditional_or_dated_service_calendar_unresolved')
    # These modify direction, service availability, destination or route. A
    # stop number elsewhere in the sentence does not make that meaning known.
    if any(word in n for word in ('DONUS','SERVISDISI','DBOS','GIDER','GIRER','GITMEZ','UGRAR','UZAT','GELIR','YAPMAZ')):
        return result(reason='unresolved_return_deadhead_or_route_variant')
    if 'BSLR' in n:return result(reason='abbreviated_start_instruction_unresolved')
    refs=re.findall(r'(?<!\d)\d{5}(?!\d)',body)
    ids=[s['id'] for s in stops]
    if refs and any(ids.count(ref)!=1 for ref in refs):return result(reason='unknown_or_repeated_stop_reference')
    if len(refs)>2:return result(reason='multiple_stop_instructions_unresolved')
    # Permit a harmless UÇ service label only at the outside of the instruction.
    if n.startswith('UC'):n=n[2:]
    if n.endswith('UC'):n=n[:-2]
    if len(refs)==2:
        if n.count('BASLAR')==1 and n.count('BITER')==1 and n.endswith('BITER'):
            start_clause,end_clause=n.split('BASLAR')
            if refs[0] in start_clause and refs[1] in end_clause and refs[1] not in start_clause:
                a,b=ids.index(refs[0]),ids.index(refs[1])
                if a<b:return result((a,b))
        return result(reason='combined_start_end_instructions_not_fully_resolved')
    if len(refs)==1:
        ref=refs[0]
        # A mixed named endpoint such as "... BAŞLAR ULUS SON" cannot be
        # interpreted as service through the final listed return stop.
        if 'BASLA' in n:
            if n.count('BASLA')==1 and n.endswith(('BASLAR','BASLAYACAK')) and 'BITER' not in n:
                return result((ids.index(ref),len(stops)-1))
            return result(reason='start_instruction_has_unresolved_remaining_clause')
        if n.endswith(('DENHAREKETSAATI','DANHAREKETSAATI')) and 'BITER' not in n and 'SON' not in n:
            return result((ids.index(ref),len(stops)-1))
        if n.endswith(('BITER','SON')) and not any(word in n for word in ('HAREKET','KALK')):
            if clocks:return result(reason='note_clock_at_end_only_instruction_unresolved')
            return result((0,ids.index(ref)))
        return result(reason='stop_reference_role_unresolved')
    # Exact named starts, including the two spellings used by the rail source.
    suffixes=('ISTASYONUNDANBASLAYACAK','ISTAYONUNDANBASLAYACAK',
              'NDANHAREKETSAATI','NDENHAREKETSAATI','DANHAREKETSAATI','DENHAREKETSAATI',
              'NDANBASLAR','NDENBASLAR','DANBASLAR','DENBASLAR')
    for suffix in suffixes:
        if n.endswith(suffix):
            name=n[:-len(suffix)]
            hits=[i for i,s in enumerate(stops) if station_name(s['name'])==station_name(name)]
            if len(hits)==1:return result((hits[0],len(stops)-1))
    return result(reason='named_start_or_other_instruction_unresolved')


def resolve_note(note,stops,departure_seconds=None):
    """Compatibility wrapper for callers that only need a supported stop span."""
    return resolve_note_details(note,stops,departure_seconds)['span']


def coordinate_registry(official,osm,official_coordinates=None):
    if official_coordinates is not None and (official_coordinates.get('format')!=1 or
                                            not isinstance(official_coordinates.get('stops'),dict)):
        raise ValueError('Unsupported official stop-coordinate snapshot')
    primary=(official_coordinates or {}).get('stops',{})
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
        if code in primary:
            entry=primary[code]
            if entry.get('id')!=code or not (-180<=float(entry['lon'])<=180 and -90<=float(entry['lat'])<=90):
                raise ValueError(f'Invalid official stop-coordinate identity or values: {code}')
            node={'lon':float(entry['lon']),'lat':float(entry['lat'])};source='EGO Başkentkart public stop query'
            if options:
                osm_node=next((x for x in options if x['tags'].get('highway')=='bus_stop'),options[0])
                distance=float(np.linalg.norm(np.diff(project([[node['lon'],node['lat']],[osm_node['lon'],osm_node['lat']]]),axis=0)))
                if distance>300:conflicts.append({'stopId':code,'differenceMeters':round(distance),'chosen':'EGO Başkentkart','comparedSource':'OSM'})
        elif options:
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
            if code in primary:
                result[code].update({'coordinateObservedAt':primary[code].get('observedAt'),
                    'coordinateRawSha256':primary[code].get('rawSha256'),'coordinateSourceUrl':primary[code].get('sourceUrl')})
            if code in community and (source.startswith('OSM') or code in primary):
                c=community[code];dist=float(np.linalg.norm(np.diff(project([[node['lon'],node['lat']],[float(c['stop_lon']),float(c['stop_lat'])]]),axis=0)))
                if dist>300:conflicts.append({'stopId':code,'differenceMeters':round(dist),
                    'chosen':'EGO Başkentkart' if code in primary else 'OSM','comparedSource':'Historical community GTFS'})
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
    official_coords_path=OUT/'ego-stop-coordinates.json'
    official_coords=json.loads(official_coords_path.read_text(encoding='utf-8')) if official_coords_path.exists() else None
    registry,missing,conflicts=coordinate_registry(official,osm,official_coords)
    districts=json.loads((OUT/'districts.geojson').read_text(encoding='utf-8'))
    registry,withheld,address_quality=validate_coordinate_districts(registry,districts)
    missing.extend(withheld)
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
    digest=hashlib.sha256(GEOMETRY_ENGINE.encode())
    for code_path in (Path(__file__),ROOT/'backend/geo.py'):
        digest.update(hashlib.sha256(code_path.read_bytes()).digest())
    for path in (OUT/'ego-official.json',RAW/'ankara-osm.json.gz',RAW/'ego/community-ankara.zip',OUT/'graph-coordinates.npy',OUT/'districts.geojson'):
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    if official_coords_path.exists():digest.update(hashlib.sha256(official_coords_path.read_bytes()).digest())
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
                starts,_=nearby_bus_vertices(drive_tree,drive_valid,s)
                ends,end_dist=nearby_bus_vertices(drive_tree,drive_valid,t)
                if not len(starts) or not len(ends):continue
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
                                       'meters':length,'endpointDistanceMeters':euclid,
                                       'coordinates':geometry.round(6).tolist(),'coLocated':length<.1}
        if i%200==0:print('Vehicle geometry',i,'/',len(pairs),flush=True)
        if i%1000==0:
            with gzip.open(cachepath,'wt',encoding='utf-8') as f:json.dump(segments,f,ensure_ascii=False,separators=(',',':'))
    with gzip.open(cachepath,'wt',encoding='utf-8') as f:json.dump(segments,f,ensure_ascii=False,separators=(',',':'))
    stops=list(registry.values());index={s['id']:i for i,s in enumerate(stops)}
    patterns=[];excluded=[];notes=[];accepted=[];duration_flags=[];geometry_checks=[];quarantined=[]
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
        check=route_geometry_check(r,known,registry,keys,segments)
        geometry_checks.append(check)
        if check['status']=='quarantined':
            quarantined.append(check)
            excluded.append({'route':r['id'],'reason':'Quarantined: route geometry conflicts with published distance'});continue
        offsets,minimum=allocate_segment_times([timing_segment_meters(segments[k]) for k in keys],
            [segments[k]['secondsWeight']+25 for k in keys],r['durationMinutes']*60,mode)
        if offsets[-1]>r['durationMinutes']*60+1e-6:
            duration_flags.append({'route':r['id'],'publishedMinutes':r['durationMinutes'],'usedMinutes':float(offsets[-1]/60),
                                   'minimumMinutes':minimum/60,'reason':'Sum of per-segment speed/dwell minima exceeds published duration'})
        mapped={old:new for new,(old,_) in enumerate(known)};groups=defaultdict(lambda:{d:[] for d in ('weekday','saturday','sunday')})
        for day,entries in r['departures'].items():
            for entry in entries:
                resolution=resolve_note_details(entry['note'],r['stops'],entry['seconds'])
                span=resolution['span']
                if span is None or span[0] not in mapped or span[1] not in mapped:
                    notes.append({'route':r['id'],'day':day,**entry,
                        'resolutionReason':resolution['reason'] or 'resolved_endpoint_coordinate_unavailable',
                        'columnSeconds':entry['seconds'],'noteClockSeconds':resolution['noteClockSeconds']});continue
                a,b=map(mapped.get,span)
                if a>=b:continue
                groups[a,b][day].append(entry['seconds'])
        for (a,b),deps in groups.items():
            if not any(deps.values()):continue
            patterns.append({'id':len(patterns),'route':r['id'],'name':r['name'],'mode':r['mode'],
                'stops':[index[s['id']] for _,s in known[a:b+1]],'offsets':(offsets[a:b+1]-offsets[a]).tolist(),
                'departures':{d:sorted(set(v)) for d,v in deps.items()},'segmentKeys':keys[a:b],
                'sourceUrl':r['url'],'intermediateTimes':'estimated; per-segment speed/dwell minima plus weighted residual of published route duration'})
        if groups:accepted.append(r['id'])
        else:excluded.append({'route':r['id'],'reason':'No published departures' if not any(r['departures'].values()) else 'Only unresolved special-service notes'})
    network={'version':'ego-scheduled-v2-quality-gates','stops':stops,'patterns':patterns,'segments':segments}
    with gzip.open(OUT/'ego-network.json.gz','wt',encoding='utf-8') as f:json.dump(network,f,ensure_ascii=False,separators=(',',':'))
    report={'officialRouteCount':len(official['routes']),'officialStopCount':len({s['id'] for r in official['routes'] for s in r['stops']}),
            'routedRouteCount':len(accepted),'patternCount':len(patterns),'coordinateStopCount':len(stops),
            'coordinateSources':dict(Counter(s['coordinateSource'] for s in stops)),
            'missingCoordinates':missing,'coordinateDisagreements':conflicts,'excludedRoutes':excluded,
            'coordinateAddressAudit':address_quality,'geometryQualityPolicy':GEOMETRY_POLICY,
            'routeGeometryChecks':geometry_checks,'quarantinedRoutes':quarantined,'quarantinedRouteCount':len(quarantined),
            'quarantinedCoordinateCount':address_quality['quarantinedCoordinateCount'],
            'coordinateAddressConflictCount':len(address_quality['conflicts']),
            'officialCoordinateSnapshot':({'snapshotId':official_coords.get('snapshotId'),
                'requestedCount':official_coords.get('requestedCount'),'availableCount':len(official_coords['stops']),
                'usedCount':sum(s['coordinateSource']=='EGO Başkentkart public stop query' for s in stops),
                'notFoundCount':len(official_coords.get('notFound',[])),'errorCount':len(official_coords.get('errors',[])),
                'sha256':hashlib.sha256(official_coords_path.read_bytes()).hexdigest()}
                if official_coords is not None else None),
            'segmentTimingPolicy':{'busMaximumKmh':90,'railMaximumKmh':80,'minimumSecondsPerSegmentDwell':10,
                'minimumDistanceBasis':'Maximum of modeled road/rail length and stop-to-stop straight distance; no straight-line ride geometry is added.',
                'allocation':'Per-segment minimum plus nonnegative residual, weighted by estimated road/rail travel time plus 25 seconds.'},
            'excludedDepartures':notes,'durationAdjustments':duration_flags,
            'excludedDepartureReasons':dict(Counter(note['resolutionReason'] for note in notes)),
            'usedDepartures':{d:sum(len(p['departures'][d]) for p in patterns) for d in ('weekday','saturday','sunday')},
            'officialDepartures':{d:sum(len(r['departures'][d]) for r in official['routes']) for d in ('weekday','saturday','sunday')},
            'coordinateWarning':'Historical community coordinates are supplementary, not an official current stop-location export.',
            'supplementaryCoordinates':{'url':'https://dl.dropboxusercontent.com/scl/fi/d7u3d00gd85w2qbzedze6/ankara.zip?rlkey=4x8oz2sby5vvqgf1iuaeit70l',
                'sha256':hashlib.sha256((RAW/'ego/community-ankara.zip').read_bytes()).hexdigest()},
            'coLocatedSegmentCount':sum(v.get('coLocated',False) for v in segments.values()),
            'walkingAccessibleStops':sum(s['walkSnapMeters']<=200 for s in stops),
            'excludedNotePolicy':'Conservative stop-span pattern matching, not a full language parser or dated service calendar. '
                'Conflicting or multiple clocks, clocked end-only instructions, conditional/date rules, return/deadhead clauses '
                'and unresolved named endpoints are retained as unknown service, not invented full-route trips. '
                'Stop-name text around explicit IDs remains subject to source-level review.'}
    write_json(OUT/'ego-quality.json',report)
    print('Patterns',len(patterns),'accepted routes',len(accepted),'excluded',len(excluded),'unresolved departures',len(notes),flush=True)
    n=len(data['demands']);destinations=data['candidates']+data['hospitals'];m=len(destinations)
    origins=np.array([d['node'] for d in data['demands']]);destnodes=np.array([d['node'] for d in destinations]);stopnodes=np.array([s['walkNode'] for s in stops])
    originsecs=np.array([d['snapMeters']/1.25 for d in data['demands']]);destsecs=np.array([d['accessMeters']/1.25 for d in destinations]);stopsecs=np.array([s['walkSnapMeters']/1.25 for s in stops])
    rows={k:[] for k in ('access','egress','transfers','direct')};cols={k:[] for k in rows};vals={k:[] for k in rows}
    def add(kind,a,b,w):rows[kind].append(int(a));cols[kind].append(int(b));vals[kind].append(float(max(.001,w)))
    walking_key=hashlib.sha256(json.dumps({'walkGraphSha256':hashlib.sha256((OUT/'walk-graph.npz').read_bytes()).hexdigest(),
        'builderSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'stops':[(s['id'],s['walkNode'],s['walkSnapMeters']) for s in stops],
        'demands':data['demands'],'destinations':destinations},sort_keys=True).encode()).hexdigest()
    cache_metadata=WORK/'walking-cache.json'
    cache_paths={k:OUT/f'ego-{k}.npz' for k in rows}
    reuse=walking_cache_valid(cache_metadata,walking_key,cache_paths)
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
    record_walking_cache(cache_metadata,walking_key,cache_paths)
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
        'transitProfiles':PROFILES,'transitDataQuality':{k:report[k] for k in ('officialRouteCount','officialStopCount','routedRouteCount','coordinateStopCount',
            'usedDepartures','officialDepartures','coordinateSources','quarantinedCoordinateCount','coordinateAddressConflictCount','quarantinedRouteCount')},
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
    from scripts.transit_provenance import write_package
    write_package()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--matrices-only',action='store_true');parser.add_argument('--network-only',action='store_true');args=parser.parse_args()
    if not args.matrices_only:build()
    if not args.network_only:matrices()
