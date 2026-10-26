from copy import deepcopy
import pytest
from backend.main import Scenario
from scripts.verify_release import verify_saved_scenario


def legacy():
    expected = Scenario(mode='transit', threshold=45).model_dump()
    record = {key: value for key, value in expected.items() if key not in ('transitEngine', 'carWeight', 'transitThreshold')}
    return record, expected


def test_historical_scenario_keeps_all_original_parameters_with_explicit_ego_defaults():
    verify_saved_scenario(*legacy())
    expected = Scenario(mode='hybrid', transitEngine='motis').model_dump()
    verify_saved_scenario(deepcopy(expected), expected)


@pytest.mark.parametrize('key', ['threshold', 'coverageTarget', 'districtFloor', 'transitProfile'])
def test_missing_original_parameters_are_not_hidden_by_defaults(key):
    record, expected = legacy()
    del record[key]
    with pytest.raises(AssertionError, match='Missing original'):
        verify_saved_scenario(record, expected)


def test_new_provider_or_unknown_field_cannot_be_relabelled_as_legacy():
    record, expected = legacy()
    record['transitEngine'] = 'motis'
    with pytest.raises(AssertionError):
        verify_saved_scenario(record, expected)
    record, expected = legacy()
    record['unrecognized'] = True
    with pytest.raises(AssertionError):
        verify_saved_scenario(record, expected)


def test_hybrid_records_require_the_new_explicit_preferences():
    expected = Scenario(mode='hybrid', transitEngine='motis').model_dump()
    record = deepcopy(expected)
    del record['carWeight']
    with pytest.raises(AssertionError, match='explicit contract'):
        verify_saved_scenario(record, expected)


@pytest.mark.parametrize('key', ['trafficFactor', 'demandMultiplier', 'operatingCostMultiplier'])
def test_boolean_is_not_a_numeric_model_parameter(key):
    record, expected = legacy()
    record[key] = True
    with pytest.raises(AssertionError):
        verify_saved_scenario(record, expected)


def test_tiny_numeric_change_is_not_hidden_by_comparison_tolerance():
    record, expected = legacy()
    record['coverageTarget'] += 1e-10
    with pytest.raises(AssertionError):
        verify_saved_scenario(record, expected)
