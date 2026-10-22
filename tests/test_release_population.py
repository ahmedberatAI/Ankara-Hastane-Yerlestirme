"""Tampered saved-plan rows must not bypass district service constraints."""
from copy import deepcopy
import pytest
import scripts.verify_release as release


def records():
    data = {'demands': [{'id': 'x'}, {'id': 'y'}],
            'districts': [{'id': 'a', 'population': 100}, {'id': 'b', 'population': 200}],
            'candidates': [{}, {}]}
    plan = {'assignments': [{'demandId': 'x'}, {'demandId': 'y'}],
            'districts': deepcopy(data['districts']), 'hospitalCount': 2,
            'selectedIndices': [0, 1], 'selected': [{'candidateIndex': 0}, {'candidateIndex': 1}]}
    return data, plan


def test_complete_identity_allows_different_district_display_order():
    data, plan = records()
    plan['districts'].reverse()
    release.verify_population_identity(plan, data)


@pytest.mark.parametrize('mutation', ['missing_district', 'duplicate_district', 'unknown_district',
    'denominator', 'missing_demand', 'duplicate_demand', 'missing_site', 'duplicate_site',
    'duplicate_index', 'negative_index'])
def test_plan_audit_rejects_identity_tampering_before_metric_checks(monkeypatch, mutation):
    data, plan = records()
    if mutation == 'missing_district': plan['districts'].pop()
    elif mutation == 'duplicate_district': plan['districts'][1] = deepcopy(plan['districts'][0])
    elif mutation == 'unknown_district': plan['districts'][1]['id'] = 'other'
    elif mutation == 'denominator': plan['districts'][1]['population'] = 1
    elif mutation == 'missing_demand': plan['assignments'].pop()
    elif mutation == 'duplicate_demand': plan['assignments'][1]['demandId'] = 'x'
    elif mutation == 'missing_site': plan['selected'].pop()
    elif mutation == 'duplicate_site': plan['selected'][1]['candidateIndex'] = 0
    elif mutation == 'duplicate_index': plan['selectedIndices'][1] = 0
    elif mutation == 'negative_index': plan['selectedIndices'][1] = -1
    monkeypatch.setattr(release, 'dataset', lambda: data)
    # Other physical fields are deliberately absent: reject at the source gate.
    with pytest.raises(AssertionError):
        release.audit(plan)
