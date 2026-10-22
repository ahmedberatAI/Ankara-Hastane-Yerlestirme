"""Clip the Geofabrik Turkey snapshot and extract Ankara data reproducibly."""
import gzip
import json
import hashlib
from pathlib import Path
import osmium
from shapely.geometry import shape, mapping, Point

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

class Clip(osmium.SimpleHandler):
    def __init__(self, destination):
        super().__init__()
        self.writer = osmium.SimpleWriter(str(destination))
        self.nodes = set()
        self.ways = set()

    def node(self, n):
        if 30.7 <= n.lon <= 34.5 and 38.4 <= n.lat <= 41.0:
            self.nodes.add(n.id)
            self.writer.add_node(n)

    def way(self, w):
        if all(n.ref in self.nodes for n in w.nodes):
            self.ways.add(w.id)
            self.writer.add_way(w)

    def relation(self, r):
        if any((m.type == "w" and m.ref in self.ways) or
               (m.type == "n" and m.ref in self.nodes) for m in r.members):
            self.writer.add_relation(r)

class Extract(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.factory = osmium.geom.GeoJSONFactory()
        self.nodes = {}
        self.ways = {}
        self.areas = []
        self.routes = []

    def node(self, n):
        if any(k in n.tags for k in ("place", "public_transport", "railway", "highway", "amenity", "healthcare")):
            self.nodes[str(n.id)] = {"id": n.id, "tags": dict(n.tags), "lon": n.lon, "lat": n.lat}

    def way(self, w):
        if any(k in w.tags for k in ("highway", "railway", "amenity", "healthcare")):
            if all(n.location.valid() for n in w.nodes):
                self.ways[str(w.id)] = {"id": w.id, "tags": dict(w.tags), "nodes": [n.ref for n in w.nodes],
                    "geometry": [[n.lon, n.lat] for n in w.nodes]}

    def area(self, a):
        if a.tags.get("boundary") == "administrative" and a.tags.get("admin_level") in ("4", "6", "8", "10"):
            try:
                geometry = json.loads(self.factory.create_multipolygon(a))
                self.areas.append({"type": "Feature", "id": a.orig_id(), "properties": dict(a.tags), "geometry": geometry})
            except (RuntimeError, ValueError):
                pass

    def relation(self, r):
        if r.tags.get("type") == "route" and r.tags.get("route") in ("bus", "subway", "light_rail", "train"):
            self.routes.append({"id": r.id, "tags": dict(r.tags),
                "members": [{"type": m.type, "ref": m.ref, "role": m.role} for m in r.members]})

if __name__ == "__main__":
    source_path = RAW / "turkey-latest.osm.pbf"
    reader = osmium.io.Reader(str(source_path))
    try:
        snapshot_date = reader.header().get('osmosis_replication_timestamp')
    finally:
        reader.close()
    if not snapshot_date:
        raise RuntimeError('OSM source does not declare a replication timestamp')
    clip_path = RAW / "ankara-region.osm.pbf"
    if not clip_path.exists():
        clip = Clip(clip_path)
        clip.apply_file(str(RAW / "turkey-latest.osm.pbf"))
        clip.writer.close()
        print(f"Regional clip: {len(clip.nodes):,} nodes, {len(clip.ways):,} ways", flush=True)
        del clip
    extract = Extract()
    extract.apply_file(str(clip_path), locations=True, idx="flex_mem")
    provinces = [a for a in extract.areas if a['properties'].get('ISO3166-2') == 'TR-06']
    if len(provinces) != 1:
        raise RuntimeError(f"Expected Ankara boundary, found {len(provinces)}")
    ankara = shape(provinces[0]['geometry'])
    boundary = ankara.buffer(0.003)
    areas = [a for a in extract.areas if a == provinces[0] or ankara.covers(shape(a['geometry']).representative_point())]
    nodes = {k: n for k, n in extract.nodes.items() if boundary.covers(Point(n['lon'], n['lat']))}
    # A 5 km collar permits realistic paths just outside the province boundary.
    road_boundary = ankara.buffer(0.06)
    ways = {k: w for k, w in extract.ways.items() if road_boundary.covers(Point(w['geometry'][len(w['geometry'])//2]))}
    routes = [r for r in extract.routes if any(str(m['ref']) in nodes or str(m['ref']) in ways for m in r['members'])]
    with source_path.open('rb') as source_file:
        source_sha = hashlib.file_digest(source_file, 'sha256').hexdigest()
    data = {'province': provinces[0], 'areas': areas, 'nodes': nodes, 'ways': ways, 'routes': routes,
            'sourceMetadata': {'snapshotDate': snapshot_date, 'sha256': source_sha,
                               'url': 'https://download.geofabrik.de/europe/turkey-latest.osm.pbf'}}
    with gzip.open(RAW / "ankara-osm.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    print(f"Ankara: {len(areas)} areas, {len(nodes)} tagged nodes, {len(ways)} ways, {len(routes)} routes", flush=True)
