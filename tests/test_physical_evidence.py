from copy import deepcopy
import math

import pytest
from pyproj import Transformer

from scripts.verify_transit import validate_physical_network


def fixture():
    project=Transformer.from_crs('EPSG:4326','EPSG:32636',always_xy=True)
    stops=[{'id':'1','lon':33.,'lat':39.},{'id':'2','lon':33.01,'lat':39.}]
    points=[project.transform(s['lon'],s['lat']) for s in stops]
    straight=math.dist(*points)
    # Distinct stop coordinates may be snapped to the same road vertex.
    segment={'meters':0.,'endpointDistanceMeters':0.,'coordinates':[[33,39],[33,39]]}
    network={'stops':stops,'segments':{'drive:1:2':segment},'patterns':[
        {'route':'110','mode':'bus','stops':[0,1],'offsets':[0,100.], 'segmentKeys':['drive:1:2']}]}
    official={'routes':[{'id':'110','mode':'bus','distanceKm':1.,'stops':[{'id':'1'},{'id':'2'}]}]}
    quality={'routedRouteCount':1,'excludedRoutes':[],'quarantinedRoutes':[],'quarantinedRouteCount':0,
             'routeGeometryChecks':[{'route':'110','straightStopChainMeters':round(straight),
                 'routedMeters':0.,'publishedMeters':1000.,'status':'passed consistency gates'}]}
    return network,official,quality


def test_independent_physical_check_uses_actual_stop_coordinates_not_builder_hint():
    network,official,quality=fixture()
    validate_physical_network(network,official,quality)
    network['patterns'][0]['offsets']=[0,10.]
    with pytest.raises(AssertionError,match='impossible segment time'):
        validate_physical_network(network,official,quality)


def test_independent_physical_check_enforces_road_length_and_dwell():
    network,official,quality=fixture()
    network['segments']['drive:1:2']['meters']=2500.
    quality['routeGeometryChecks'][0]['routedMeters']=2500.
    network['patterns'][0]['offsets']=[0,100.]
    # 2500m at 90 km/h requires 100s moving plus a separate 10s dwell.
    with pytest.raises(AssertionError,match='impossible segment time'):
        validate_physical_network(network,official,quality)
    network['patterns'][0]['offsets']=[0,110.]
    validate_physical_network(network,official,quality)


def test_independent_geometry_gate_rejects_false_pass_and_usable_quarantined_route():
    network,official,quality=fixture()
    network['segments']['drive:1:2']['meters']=4000.
    network['patterns'][0]['offsets']=[0,500.]
    quality['routeGeometryChecks'][0]['routedMeters']=4000.
    with pytest.raises(AssertionError,match='independent consistency gate'):
        validate_physical_network(network,official,quality)
    check=quality['routeGeometryChecks'][0]
    check['status']='quarantined'
    quality['quarantinedRoutes']=[deepcopy(check)]
    quality['quarantinedRouteCount']=1
    with pytest.raises(AssertionError,match='Quarantined route appears'):
        validate_physical_network(network,official,quality)
    network['patterns']=[]
    quality['routedRouteCount']=0
    quality['excludedRoutes']=[{'route':'110'}]
    validate_physical_network(network,official,quality)
