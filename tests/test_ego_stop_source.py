import pytest
import json
import os
from scripts import fetch_ego_stops as source
from scripts.fetch_ego_stops import parse_stop


def test_current_public_stop_coordinates_use_lat_lon_and_validate_identity():
    body = b"{'Err':'','Msg':'','Row':1,'Tbl':[{'adi':'41893','yeri':'Sirkeli','px':'40.143848','py':'32.847659'}]}"
    result = parse_stop(body, '41893')
    assert result['lat'] == 40.143848 and result['lon'] == 32.847659
    with pytest.raises(ValueError, match='ID mismatch'):
        parse_stop(body, '41821')
    with pytest.raises(ValueError, match='coordinate'):
        parse_stop(body.replace(b'40.143848', b'32.847659'), '41893')
    assert parse_stop(b"{'Err':'','Row':0,'Tbl':[]}", '41893') is None


def test_public_stop_payload_cannot_execute_python():
    with pytest.raises((ValueError, SyntaxError)):
        parse_stop(b"__import__('os').getcwd()", '41893')


def test_legacy_turkish_encoding_preserves_address():
    text = "{'Err':'','Row':1,'Tbl':[{'adi':'14123','yeri':'Şereflikoçhisar','px':'39.0','py':'33.5'}]}"
    assert parse_stop(text.encode('cp1254'), '14123')['address'] == 'Şereflikoçhisar'


@pytest.mark.parametrize('prior_quality_exists', [True, False])
def test_empty_cache_retry_and_original_observation_survives_file_copy_time(tmp_path, monkeypatch, prior_quality_exists):
    out, raw, work = (tmp_path/name for name in ('out', 'raw', 'work'))
    for path in (out, raw, work): path.mkdir()
    monkeypatch.setattr(source, 'OUT', out); monkeypatch.setattr(source, 'RAW', raw); monkeypatch.setattr(source, 'WORK', work)
    monkeypatch.setattr(source.time, 'sleep', lambda _: None)
    (out/'ego-official.json').write_text(json.dumps({'routes': [{'stops': [{'id': '41893'}]}]}))
    if prior_quality_exists:
        (out/'ego-quality.json').write_text('{}')
    cached = raw/'41893.txt'; cached.write_bytes(b'')
    body = b"{'Err':'','Row':1,'Tbl':[{'adi':'41893','yeri':'Sirkeli','px':'40.143848','py':'32.847659'}]}"
    calls = []
    class Response:
        status_code = 200
        content = body
        headers = {'Content-Type': 'text/html'}
        def raise_for_status(self): pass
    class Session:
        headers = {}
        def get(self, *a, **kw): return Response()
        def post(self, *a, **kw): calls.append(kw['data']); return Response()
    monkeypatch.setattr(source.requests, 'Session', Session)
    source.run()
    report = json.loads((out/'ego-stop-coordinates.json').read_text(encoding='utf-8'))
    assert report['emptyUnavailable'] == ['41893'] and report['notFound'] == [] and not calls
    assert report['rawSources'][0]['observedAt'] is None
    source.run(retry_unavailable=True)
    first = json.loads((out/'ego-stop-coordinates.json').read_text(encoding='utf-8'))
    observed = first['stops']['41893']['observedAt']; assert observed and len(calls) == 1
    os.utime(cached, (2000000000, 2000000000))
    source.run()
    second = json.loads((out/'ego-stop-coordinates.json').read_text(encoding='utf-8'))
    assert second['stops']['41893']['observedAt'] == observed
    assert second['snapshotId'] == first['snapshotId'] and len(calls) == 1
    cached.write_bytes(b'broken object')
    source.run()
    assert len(calls) == 2 and cached.read_bytes() == body
    sidecar = raw/'41893.source.json'
    provenance = json.loads(sidecar.read_text(encoding='utf-8'))
    provenance['url'] = 'https://different.example/source'
    sidecar.write_text(json.dumps(provenance), encoding='utf-8')
    source.run()
    wrong_source = json.loads((out/'ego-stop-coordinates.json').read_text(encoding='utf-8'))
    assert wrong_source['stops']['41893']['observedAt'] is None and len(calls) == 2
