"""Negative controls for provenance, cached observation times and displayed claims."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.timetable import PROFILES
from scripts.fetch_ego import fetch_source, snapshot_metadata
from scripts.verify_release import (
    BENCHMARK_KEYS, TRANSIT_REPORT_KEYS, summarize, verify_benchmark,
    verify_certificate, verify_report_records, verify_result_package,
)


class Session:
    def __init__(self, content=b'official response'):
        self.content = content
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        return SimpleNamespace(content=self.content, raise_for_status=lambda: None)


def test_cache_hit_preserves_observation_and_snapshot_identity(tmp_path, monkeypatch):
    monkeypatch.setattr('scripts.fetch_ego.time.sleep', lambda _: None)
    session = Session()
    _, first = fetch_source(session, tmp_path, '110.html', {'hat_no': '110'})
    _, cached = fetch_source(session, tmp_path, '110.html', {'hat_no': '110'})
    assert session.calls == 1
    assert cached['observedAt'] == first['observedAt']
    assert first['downloadedThisRun'] and not cached['downloadedThisRun']
    assert snapshot_metadata([first])['sourceSnapshotId'] == snapshot_metadata([cached])['sourceSnapshotId']
    assert snapshot_metadata([cached])['retrievedAt'] == first['observedAt']


def test_unknown_cache_time_is_not_fabricated_from_mtime(tmp_path):
    (tmp_path / '110.html').write_bytes(b'legacy bytes')
    session = Session()
    _, record = fetch_source(session, tmp_path, '110.html', {'hat_no': '110'})
    assert session.calls == 0 and record['observedAt'] is None
    metadata = snapshot_metadata([record])
    assert metadata['retrievedAt'] is None
    assert metadata['observationPeriod']['unknownSourceCount'] == 1
    assert metadata['processedAt']


def test_changed_cache_cannot_inherit_old_observation(tmp_path, monkeypatch):
    monkeypatch.setattr('scripts.fetch_ego.time.sleep', lambda _: None)
    _, first = fetch_source(Session(), tmp_path, '110.html', {'hat_no': '110'})
    (tmp_path / '110.html').write_bytes(b'different bytes')
    _, modified = fetch_source(Session(), tmp_path, '110.html', {'hat_no': '110'})
    assert modified['observedAt'] is None
    assert snapshot_metadata([first])['sourceSnapshotId'] != snapshot_metadata([modified])['sourceSnapshotId']


def certificate(count=3, status='optimal'):
    return {'status': status, 'minimumCountLowerBound': float(count),
            'feasibleGeographicCount': count, 'fullCandidateCount': 100,
            'undominatedCandidateCount': 60, 'scope': 'full-edge geographical relaxation',
            'thresholdMinutes': 45, 'coverageTargetPercent': 95., 'districtFloorPercent': 80.}


def test_certificate_rejects_false_saved_number_even_when_both_exceed_91():
    # The previous release audit checked only fresh_bound > 91, accepting 999.
    with pytest.raises(AssertionError, match='optimalLowerBound'):
        verify_certificate(certificate(999), certificate(171))


def test_certificate_accepts_solver_rounding_and_rejects_changed_scope():
    saved, fresh = certificate(), certificate()
    fresh['minimumCountLowerBound'] -= 1e-8
    verify_certificate(saved, fresh)
    fresh['thresholdMinutes'] = 60
    with pytest.raises(AssertionError, match='thresholdMinutes'):
        verify_certificate(saved, fresh)


def test_weaker_time_limited_solve_does_not_recertify_stronger_old_bound():
    saved, fresh = certificate(3, 'bounded'), certificate(2, 'bounded')
    saved['feasibleGeographicCount'] = fresh['feasibleGeographicCount'] = 5
    with pytest.raises(AssertionError, match='too weak'):
        verify_certificate(saved, fresh)
    fresh['minimumCountLowerBound'] = 4
    verify_certificate(saved, fresh)  # a stronger new bound validates the old conservative one


def records():
    package_id = 'ego-test-package'
    results = [{'scenario': {'mode': 'transit', 'hospitalLimit': 91, 'transitProfile': profile},
                'status': 'infeasible', 'geographicCertificate': certificate(171),
                'metadata': {'transitPackageId': package_id},
                'transitEvidence': {'packageId': package_id, 'profile': details}}
               for profile, details in PROFILES.items()]
    report = {'transitPackageId': package_id,
              'profiles': [summarize(r, TRANSIT_REPORT_KEYS) for r in results],
              'legacy': certificate(291), 'walkingCorrectionOnly': certificate(169),
              'withoutDistrictFloor': certificate(35)}
    quality = {'officialRouteCount': 665, 'routedRouteCount': 427}
    benchmark = {'transitPackageId': package_id, 'sensitivity': None,
                 'cases': [summarize(r, BENCHMARK_KEYS) for r in results],
                 'transitAudit': {'legacyLowerBound': 291., 'walkingCorrectionLowerBound': 169.,
                                  'withoutDistrictFloorLowerBound': 35., 'officialRoutes': 665, 'modeledRoutes': 427}}
    return deepcopy((results, report, benchmark, quality, package_id))


def test_saved_result_requires_current_package_and_exact_profile():
    results, _, _, _, package_id = records()
    result = results[0]
    verify_result_package(result, package_id)
    result['transitEvidence']['packageId'] = 'old-package'
    with pytest.raises(AssertionError, match='different transit package'):
        verify_result_package(result, package_id)
    result['transitEvidence']['packageId'] = package_id
    result['transitEvidence']['profile'] = PROFILES['sunday-1000']
    with pytest.raises(AssertionError, match='profile'):
        verify_result_package(result, package_id)


def test_report_rejects_stale_package_duplicate_profile_and_changed_number():
    results, report, _, _, package_id = records()
    verify_report_records(report, results, package_id)
    wrong = deepcopy(report)
    wrong['transitPackageId'] = 'old-package'
    with pytest.raises(AssertionError, match='different transit package'):
        verify_report_records(wrong, results, package_id)
    wrong = deepcopy(report)
    wrong['profiles'][1] = deepcopy(wrong['profiles'][0])
    with pytest.raises(AssertionError):
        verify_report_records(wrong, results, package_id)
    wrong = deepcopy(report)
    wrong['profiles'][0]['geographicCertificate']['minimumCountLowerBound'] = 999
    with pytest.raises(AssertionError, match='minimumCountLowerBound'):
        verify_report_records(wrong, results, package_id)


def test_benchmark_cannot_display_different_certificate_or_ablation_number():
    results, report, benchmark, quality, package_id = records()
    verify_benchmark(benchmark, results, report, package_id, quality, None)
    wrong = deepcopy(benchmark)
    wrong['cases'][0]['geographicCertificate']['minimumCountLowerBound'] = 999
    with pytest.raises(AssertionError, match='minimumCountLowerBound'):
        verify_benchmark(wrong, results, report, package_id, quality, None)
    wrong = deepcopy(benchmark)
    wrong['transitAudit']['walkingCorrectionLowerBound'] = 17
    with pytest.raises(AssertionError, match='walkingCorrectionLowerBound'):
        verify_benchmark(wrong, results, report, package_id, quality, None)
