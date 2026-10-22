"""Download the two public sources without replacing existing files."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw'
SOURCES = {
    '2025ADNKS_FavoriTablolar.xlsx': 'https://www.tuik.gov.tr/media/announcements/2025ADNKS_FavoriTablolar.xlsx',
    'turkey-latest.osm.pbf': 'https://download.geofabrik.de/europe/turkey-latest.osm.pbf',
}

def run():
    RAW.mkdir(parents=True, exist_ok=True)
    records = []
    for name, url in SOURCES.items():
        target = RAW / name
        downloaded = not target.exists()
        if downloaded:
            temporary = target.with_suffix(target.suffix + '.part')
            print(f'Downloading {name}', flush=True)
            with requests.get(url, stream=True, timeout=(20, 120), headers={'User-Agent': 'AnkaraHospitalResearch/0.1'}) as response:
                response.raise_for_status()
                expected = response.headers.get('Content-Length')
                with temporary.open('wb') as f:
                    for block in response.iter_content(1024*1024):
                        f.write(block)
                if expected and temporary.stat().st_size != int(expected):
                    raise RuntimeError(f'Incomplete source download: {name}')
            temporary.replace(target)
        with target.open('rb') as f:
            digest = hashlib.file_digest(f, 'sha256').hexdigest()
        records.append({'file': name, 'url': url, 'bytes': target.stat().st_size,
                        'sha256': digest, 'downloadedThisRun': downloaded})
        print(f'{name}: {target.stat().st_size:,} bytes, SHA-256 {digest}', flush=True)
    (RAW / 'download-record.json').write_text(json.dumps({
        'checkedAt': datetime.now(timezone.utc).isoformat(), 'sources': records}, indent=2), encoding='utf-8')

if __name__ == '__main__':
    run()
