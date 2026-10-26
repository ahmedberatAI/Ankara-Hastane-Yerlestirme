from copy import deepcopy

import pytest

from scripts.probe_free_transit import parameters, summarize, timestamp


def response():
    return dict(direct=[], itineraries=[dict(duration=600,
        startTime='2026-10-27T05:13:00Z', endTime='2026-10-27T05:23:00Z',
        legs=[dict(mode='BUS', startTime='2026-10-27T05:13:00Z',
                   endTime='2026-10-27T05:23:00Z', realTime=False)])])


def test_elapsed_includes_wait_before_provider_journey():
    result = summarize(response(), '2026-10-27T08:05:00+03:00')
    journey = result['journeys'][0]
    assert journey['providerJourneyMinutes'] == 10
    assert journey['elapsedFromRequestedDepartureMinutes'] == 18
    assert journey['initialWaitMinutes'] == 8
    assert result['productionModelInput'] is False


def test_initial_wait_can_fail_45_even_when_provider_duration_passes():
    value = response(); value['itineraries'][0]['startTime'] = '2026-10-27T05:45:00Z'
    value['itineraries'][0]['endTime'] = '2026-10-27T05:55:00Z'
    value['itineraries'][0]['legs'][0].update(startTime='2026-10-27T05:45:00Z', endTime='2026-10-27T05:55:00Z')
    journey = summarize(value, '2026-10-27T05:05:00Z')['journeys'][0]
    assert journey['elapsedFromRequestedDepartureMinutes'] == 50
    assert journey['within45MinuteProviderEstimate'] is False


@pytest.mark.parametrize('status', [401, 429, 500, 503])
def test_provider_error_is_unknown(status):
    result = summarize(None, '2026-10-27T05:05:00Z', status)
    assert result['status'] == 'unknown_provider_error'
    assert result['journeys'] == []


def test_empty_success_is_not_a_service_absence_proof():
    assert summarize(dict(itineraries=[], direct=[]), '2026-10-27T05:05:00Z')['status'] == 'unknown_no_journey_returned'


@pytest.mark.parametrize('change', [
    lambda p: p['itineraries'][0].update(duration=-1),
    lambda p: p['itineraries'][0].update(duration=float('nan')),
    lambda p: p['itineraries'][0].update(duration=6010),
    lambda p: p['itineraries'][0].update(startTime='2026-10-27T04:59:00Z'),
    lambda p: p['itineraries'][0]['legs'][0].update(mode='CAR'),
    lambda p: p['itineraries'][0]['legs'][0].update(endTime='2026-10-27T05:25:00Z'),
    lambda p: p['itineraries'][0]['legs'][0].update(startTime='2026-10-27T05:14:00Z'),
    lambda p: p.pop('direct'),
])
def test_bad_provider_data_rejected(change):
    value = deepcopy(response()); change(value)
    with pytest.raises((ValueError, KeyError)):
        summarize(value, '2026-10-27T05:05:00Z')


def test_explicit_time_and_walk_parameters():
    params = parameters('39.92,32.85', '39.96,32.83', '2026-10-27T08:05:00+03:00')
    assert params['time'] == '2026-10-27T05:05:00+00:00'
    assert params['timetableView'] == 'false'
    assert params['maxPreTransitTime'] == params['maxPostTransitTime'] == params['maxDirectTime'] == 2700
    assert params['directModes'] == 'WALK'
    with pytest.raises(ValueError): timestamp('2026-10-27T08:05:00')
    with pytest.raises(ValueError): parameters('nan,32', '39,32', '2026-10-27T05:05:00Z')


def test_local_service_label_is_historical_and_not_a_production_matrix():
    result = summarize(response(), '2026-10-27T05:05:00Z', local=True)
    assert result['provider'] == 'Local MOTIS'
    assert result['costChannel'] == 'local_no_per_query_api_fee'
    assert result['datasetScenario'] == 'historical_community_GTFS'
    assert result['productionModelInput'] is False
