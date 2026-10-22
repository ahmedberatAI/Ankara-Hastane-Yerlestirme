import json
import pytest
from scripts.transit_provenance import MODEL_FILES, ARTIFACT_FILES, EVIDENCE_FILES, write_package, check_package


def package(tmp_path):
    for name in MODEL_FILES:
        path = tmp_path/name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'line1\nline2\n')
    for name in EVIDENCE_FILES:
        path = tmp_path/name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'evidence:'+name.encode())
    out = tmp_path/'data/processed'; out.mkdir(parents=True)
    for name in ARTIFACT_FILES:
        (out/name).write_bytes(b'fixture:'+name.encode())
    data = {'demands': [{'id': 'a'}, {'id': 'b'}], 'candidates': [{'id': 'x'}],
            'hospitals': [], 'districts': [], 'metadata': {'provincePopulation': 10}}
    (out/'dataset.json').write_text(json.dumps(data), encoding='utf-8')
    return write_package(tmp_path)


def test_transit_identity_rejects_stale_matrix_and_swapped_rows(tmp_path):
    p = package(tmp_path)
    assert check_package(tmp_path) == p['transitPackageId']
    matrix = tmp_path/'data/processed/transit-weekday-1000-matrix.npz'
    original = matrix.read_bytes(); matrix.write_bytes(b'other-snapshot')
    with pytest.raises(AssertionError, match='package mismatch'):
        check_package(tmp_path)
    matrix.write_bytes(original)
    archive=tmp_path/EVIDENCE_FILES[0]
    original=archive.read_bytes();archive.write_bytes(b'changed historical evidence')
    with pytest.raises(AssertionError,match='package mismatch'):
        check_package(tmp_path)
    archive.write_bytes(original)
    datafile = tmp_path/'data/processed/dataset.json'
    data = json.loads(datafile.read_text(encoding='utf-8'))
    data['demands'].reverse(); datafile.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(AssertionError, match='index mismatch'):
        check_package(tmp_path)


def test_transit_identity_is_time_and_code_line_ending_independent(tmp_path):
    before = package(tmp_path)
    code = tmp_path/MODEL_FILES[0]
    code.write_bytes(code.read_bytes().replace(b'\n', b'\r\n'))
    assert check_package(tmp_path) == before['transitPackageId']
    after = write_package(tmp_path)
    assert before['transitPackageId'] == after['transitPackageId']
    code.write_bytes(b'changed model')
    with pytest.raises(AssertionError, match='package mismatch'):
        check_package(tmp_path)
