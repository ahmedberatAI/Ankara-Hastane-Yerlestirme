import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gzip
import json
import hashlib
from datetime import date
import numpy as np
from shapely.geometry import Point, LineString, shape
from shapely.ops import transform
from shapely.strtree import STRtree
from backend.geo import project, road_half_width, PROJECT

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/processed'
def run():
    data=json.loads((OUT/'dataset.json').read_text(encoding='utf-8'))
    with gzip.open(ROOT/'data/raw/ankara-osm.json.gz','rt',encoding='utf-8') as f:
        raw=json.load(f)
    geometries=[]; widths=[]; rail=[]
    for w in raw['ways'].values():
        t=w['tags']
        if len(w['geometry'])<2: continue
        if 'highway' in t and t.get('highway') not in ('construction','proposed'):
            geometries.append(LineString(project(w['geometry'])));widths.append(road_half_width(t))
        if t.get('railway') in ('rail','light_rail','subway','tram') and t.get('tunnel') not in ('yes','building_passage') and t.get('layer','0') not in ('-1','-2','-3'):
            rail.append(LineString(project(w['geometry'])))
    tree=STRtree(geometries);rail_tree=STRtree(rail)
    province=transform(PROJECT.transform,shape(raw['province']['geometry']))
    invalid=[];rail_conflicts=[]
    for c in data['candidates']:
        p=Point(project([[c['lon'],c['lat']]])[0]);r=c['footprintRadiusMeters']
        if not province.covers(p.buffer(r)) or any(p.distance(geometries[i])+1e-6<r+widths[i] for i in tree.query(p.buffer(r+max(widths)))):
            invalid.append(c['id'])
        if any(p.distance(rail[i])<r+5 for i in rail_tree.query(p.buffer(r+5))):rail_conflicts.append(c['id'])
    dimensions={}
    for mode in ('car','transit'):
        a=np.load(OUT/f'{mode}-matrix.npz')['minutes']
        assert a.shape==(len(data['demands']),len(data['candidates'])+len(data['hospitals']))
        assert not np.isnan(a).any() and np.all(a>=0)
        dimensions[mode]=list(a.shape)
    assert sum(d['population'] for d in data['districts'])==data['metadata']['provincePopulation']
    report={'date':date.today().isoformat(),'roadFootprintViolations':invalid,'surfaceRailConflicts':rail_conflicts,'matrixDimensions':dimensions,
        'matchedPopulation':sum(d['population'] for d in data['demands']),'missingPopulation':data['metadata']['unlocatedPopulation'],
        'candidateCount':len(data['candidates']),'scope':'Geographic access prototype, not a capacity or clinical model',
        'sourceSha256':data['metadata']['sha256']}
    (OUT/'quality-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8', newline='\n')
    print(json.dumps(report,ensure_ascii=False))
    assert not invalid, 'Some candidate footprints intersect a mapped road'
    assert not rail_conflicts, 'Some candidate footprints intersect a mapped surface railway'
    return rail_conflicts

if __name__=='__main__':run()
