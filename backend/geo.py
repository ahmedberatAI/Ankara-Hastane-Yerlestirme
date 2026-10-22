"""Geographic helpers shared by data preparation and validation."""
import re
import unicodedata
import numpy as np
from pyproj import Transformer

PROJECT = Transformer.from_crs(4326, 32636, always_xy=True)
UNPROJECT = Transformer.from_crs(32636, 4326, always_xy=True)

def normalize(value):
    value = value.replace('ı', 'i').replace('İ', 'I')
    value = ''.join(c for c in unicodedata.normalize('NFD', value) if not unicodedata.combining(c)).upper()
    value = re.sub(r'\b(MAHALLESI|MAHALLE|MAH|KOYU)\b', '', value)
    return re.sub(r'[^A-Z0-9]', '', value)

def project(coords):
    a = np.asarray(coords)
    x, y = PROJECT.transform(a[:, 0], a[:, 1])
    return np.column_stack((x, y))

def lonlat(xy):
    a = np.asarray(xy)
    x, y = UNPROJECT.transform(a[:, 0], a[:, 1])
    return np.column_stack((x, y))

SPEEDS = {'motorway': 95, 'trunk': 75, 'primary': 55, 'secondary': 45,
          'tertiary': 35, 'unclassified': 30, 'residential': 25, 'living_street': 15, 'service': 15}

def permissions(tags):
    highway = tags.get('highway', '')
    base = highway.replace('_link', '')
    access = tags.get('access')
    drive = base in SPEEDS
    drive_access = tags.get('motorcar', tags.get('motor_vehicle', tags.get('vehicle', access)))
    drive = drive and drive_access not in ('no', 'private', 'agricultural', 'forestry')
    foot_access = tags.get('foot', access)
    walk = highway not in ('motorway', 'motorway_link', 'trunk', 'trunk_link', 'construction', 'proposed')
    if foot_access in ('yes', 'designated', 'permissive'):
        walk = True
    if foot_access in ('no', 'private'):
        walk = False
    return drive, walk

def speed(tags):
    base = tags.get('highway', '').replace('_link', '')
    value = SPEEDS.get(base, 20)
    sign = re.match(r'^(\d+(?:\.\d+)?)$', tags.get('maxspeed', ''))
    if sign:
        value = min(value, float(sign.group(1)) * .75)
    if tags.get('highway', '').endswith('_link'):
        value = min(value, 35)
    return max(5, value)

def road_half_width(tags):
    try:
        return max(2, float(tags.get('width', '').replace(' m', '')) / 2)
    except ValueError:
        return {'motorway': 13, 'trunk': 12, 'primary': 10, 'secondary': 8, 'tertiary': 6}.get(tags.get('highway', '').replace('_link', ''), 4)
