"""Optional source audit: pip install pymupdf==1.26.7; no app dependency.

Download only with --download. Assert exact source hashes and Ankara table
rows against the committed transcription; never silently update parameters.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import requests
import fitz

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/health'


def verify(download=False):
    config = json.loads((ROOT/'data/processed/health-planning.json').read_text(encoding='utf-8'))
    RAW.mkdir(parents=True, exist_ok=True)
    for source in [s for s in config['sources'] if s['id']=='siy2024' or 'localFile' in s]:
        name=source.get('localFile','siy2024.pdf')
        path = RAW/name
        if not path.exists() and download:
            response = requests.get(source.get('verifiedCopyUrl', source['url']), timeout=120)
            response.raise_for_status()
            if hashlib.sha256(response.content).hexdigest() != source['sha256']:
                raise ValueError(f'Source version changed: {name}; manually review before updating data')
            path.write_bytes(response.content)
        assert path.exists(), f'{path} missing; run with --download'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source['sha256']
    doc = fitz.open(RAW/'siy2024.pdf')
    expected = {191: 'Ankara 85 24.909', 233: 'Ankara 28.920.274 47.073.855',
                235: 'Ankara 1.063.851 5.409.136 575.665 59,5 5,1',
                290: 'Ankara 12.064 3.448 11.286 26.798'}
    for page, row in expected.items():
        text = re.sub(r'\s+', ' ', doc[page-1].get_text(sort=True))
        assert row in text, f'Ankara source row changed at PDF page {page}'
    # The cost PDF contains fragmented glyphs: its class/hospital mapping was
    # visually reviewed. Hash verification preserves that exact reviewed copy.
    observed, rates = config['observed'], config['rates']
    assert rates['visitsPerResident'] == observed['secondaryTertiaryVisits']/observed['population']
    assert rates['bedDaysPerResident'] == observed['bedDays']/observed['population']
    assert observed['specialists'] + observed['generalPractitioners'] + observed['residents'] == observed['physicians']
    for t in config['templates']:
        assert t['constructionCostTRY'] == t['grossAreaM2'] * t['unitCostTRY']
        assert t['grossAreaM2'] == 4000+160*t['beds']
    au=fitz.open(RAW/'ankara-university-2024.pdf')
    au_text=re.sub(r'\s+',' ',au[161].get_text())
    assert '1.097 921 769 734.451 694.180 40.271' in au_text
    assert '665 836 814 732.837 703.972 28.865' in au_text
    mlp=fitz.open(RAW/'mlp-2024.pdf')
    for page,tokens in [(44,['2.828','444']),(118,['9.994.192','6.417.735','5.113.295','2.245.638','2.533.955']),
                         (119,['3.366.893','184.925','1.007.767'])]:
        text=mlp[page].get_text()
        assert all(token in text for token in tokens)
    assert config['calibration']['contactsPerDoctorObserved']==7000000/3272
    assert config['economics']['annualDoctorCostTRY']==9994192000/3272
    assert config['rates']['contactsPerResident']==rates['visitsPerResident']+rates['admissionsPerResident']
    print('Health sources: 4 PDF identities, Ankara tables, university hospital rows, MLP component values and derived inputs verified.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', action='store_true')
    verify(parser.parse_args().download)
