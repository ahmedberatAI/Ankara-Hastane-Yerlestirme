"""Record exact source/derived file identities; never invent unavailable hashes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'data/processed'
RAW = ROOT/'data/raw'

def record(path):
    with path.open('rb') as f:
        sha = hashlib.file_digest(f, 'sha256').hexdigest()
    return {'file':path.relative_to(ROOT).as_posix(), 'bytes':path.stat().st_size, 'sha256':sha}

def run():
    data = json.loads((OUT/'dataset.json').read_text(encoding='utf-8'))
    source_names = ['2025ADNKS_FavoriTablolar.xlsx','turkey-latest.osm.pbf','ankara-osm.json.gz','health/siy2024.pdf','health/costs2026.pdf']
    output = {'createdAt':datetime.now(timezone.utc).isoformat(),
              'populationReferenceDate':data['metadata']['referenceDate'], 'osmSnapshotDate':data['metadata']['osmDate'],
              'sources':[record(RAW/name) for name in source_names if (RAW/name).exists()],
              'files':[record(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != 'manifest.json']}
    (OUT/'manifest.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8', newline='\n')
    print(f'Manifest: {len(output["sources"])} source identities, {len(output["files"])} output identities.')

if __name__ == '__main__':run()
