"""Extract public TÜİK tables without inventing suppressed observations."""
import csv
import hashlib
import json
from datetime import date
from pathlib import Path
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://www.tuik.gov.tr/media/announcements/2025ADNKS_FavoriTablolar.xlsx"

def extract(path):
    workbook = load_workbook(path, read_only=True, data_only=True)
    neighborhoods = [
        {"id": str(r[4]), "districtId": str(r[2]), "district": r[6], "name": r[8],
         "population": int(r[10]), "year": 2025}
        for r in workbook["MAHALLE NÜFUSU"].values if r[1] == 6
    ]
    districts = [
        {"id": str(r[1]), "name": r[3], "population": int(r[4])}
        for r in workbook["İLÇE NÜFUSU"].values if r[0] == 6
    ]
    province_total = next(int(r[2]) for r in workbook["İL NÜFUSU"].values if r[0] == 6)
    if len({n['id'] for n in neighborhoods}) != len(neighborhoods):
        raise ValueError("Duplicate neighborhood codes")
    if sum(d['population'] for d in districts) != province_total:
        raise ValueError("District and province totals disagree")
    for d in districts:
        d['listedPopulation'] = sum(n['population'] for n in neighborhoods if n['districtId'] == d['id'])
        d['unlistedPopulation'] = d['population'] - d['listedPopulation']
    metadata = {
        "source": SOURCE, "sourceName": "TÜİK ADNKS 2025", "referenceDate": "2025-12-31",
        "retrievedDate": date.fromtimestamp(Path(path).stat().st_mtime).isoformat(),
        "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "provincePopulation": province_total, "listedPopulation": sum(n['population'] for n in neighborhoods),
        "unlistedPopulation": province_total - sum(n['population'] for n in neighborhoods),
        "neighborhoodCount": len(neighborhoods), "districtCount": len(districts),
        "note": "Mahalle tablosu nüfusu 10 ve altında olan mahalleleri ve OSB'leri dışarıda bırakır. Fark, konumu bilinmeyen nüfus olarak korunur."
    }
    return neighborhoods, districts, metadata

if __name__ == '__main__':
    import urllib.request
    raw = ROOT / 'data/raw/2025ADNKS_FavoriTablolar.xlsx'
    raw.parent.mkdir(parents=True, exist_ok=True)
    if not raw.exists():
        urllib.request.urlretrieve(SOURCE, raw)
    neighborhoods, districts, metadata = extract(raw)
    target = ROOT / 'data/processed'
    target.mkdir(parents=True, exist_ok=True)
    (target / 'population.json').write_text(json.dumps({"neighborhoods": neighborhoods, "districts": districts, "metadata": metadata}, ensure_ascii=False, indent=2), encoding='utf-8', newline='\n')
    with (target / 'neighborhood-population-2025.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(neighborhoods[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(neighborhoods)
    print(json.dumps(metadata, ensure_ascii=False))
