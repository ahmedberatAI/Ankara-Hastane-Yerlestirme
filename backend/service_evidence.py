"""Exact, reviewed event interpretations; never a general terminal-name parser.

Each interpretation is bound to source bytes, ordered stop identities and one
published calendar/time/note. Timing remains an explicit estimate, including
the dated 2025 plan used for four 615 outbound trips. A changed source disables
its interpretations until reviewed again. No missing trip or return is added.
"""
import hashlib
import json
import math


CALENDARS = ('weekday', 'saturday', 'sunday')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def event_key(route_id, calendar, seconds, note):
    return route_id, calendar, seconds, note


def reviewed_events(evidence, official):
    """Return active exact-event rules and explicit invalidation records.

    Malformed configuration raises; changed source data fails closed per rule.
    Historical-plan validity is not silently promoted by a recent HTTP fetch.
    """
    if evidence.get('format') != 'reviewed-ego-events-v1':
        raise ValueError('Unsupported reviewed-event format')
    routes = {r['id']: r for r in official['routes']}
    raw = {s['file']: s['sha256'] for s in official['rawSources']}
    sources = evidence['sources']
    active, withheld, ids, keys = {}, [], set(), set()
    for rule in evidence['events']:
        rid, day = rule['routeId'], rule['calendar']
        seconds, note = rule['departureSeconds'], rule['exactNote']
        key = event_key(rid, day, seconds, note)
        if rule['id'] in ids or key in keys:
            raise ValueError('Duplicate reviewed event')
        ids.add(rule['id']); keys.add(key)
        budget = rule['durationBudgetSeconds']
        if (day not in CALENDARS or isinstance(seconds, bool) or not isinstance(seconds, int)
                or not 0 <= seconds < 30 * 3600 or not isinstance(note, str)
                or isinstance(budget, bool) or not isinstance(budget, (int, float))
                or not math.isfinite(budget) or budget <= 0):
            raise ValueError('Invalid reviewed event clock/calendar/duration')
        if (rule.get('currentArrivalTimeConfirmed') is not False
                or rule.get('isMeasuredTravelTime') is not False
                or not rule.get('timingConfidence') or not rule.get('assumption')):
            raise ValueError('Reviewed estimate must retain its timing limitations')
        binding = {'routeId': rid, 'calendar': day, 'departureSeconds': seconds, 'exactNote': note}
        if digest(binding) != rule['recordSha256']:
            raise ValueError('Reviewed event identity checksum mismatch')
        for source_id in rule['evidenceSourceIds']:
            source = sources[source_id]
            if not source.get('url') or len(source.get('sha256', '')) != 64:
                raise ValueError('Evidence source lacks URL/content identity')
        route = routes.get(rid)
        reason = None
        if route is None:
            reason = 'reviewed_route_missing'
        elif any(raw.get(f'{code}.html') != expected
                 for code, expected in rule['dependentRouteRawHashes'].items()):
            reason = 'reviewed_source_bytes_changed'
        elif digest([s['id'] for s in route['stops']]) != rule['stopSequenceSha256']:
            reason = 'reviewed_stop_sequence_changed'
        elif not any(e['seconds'] == seconds and e['note'] == note for e in route['departures'][day]):
            reason = 'reviewed_calendar_event_changed'
        if reason:
            withheld.append({'id': rule['id'], 'route': rid, 'reason': reason})
            continue
        a, b = rule['span']['indicesZeroBasedInclusive']
        if (isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, int)
                or not isinstance(b, int) or not 0 <= a < b < len(route['stops'])):
            raise ValueError('Reviewed span must follow the published forward order')
        stop_ids = [s['id'] for s in route['stops']]
        if digest(stop_ids[a:b + 1]) != rule['span']['stopIdsSha256']:
            raise ValueError('Reviewed span checksum mismatch')
        for name, pos in [('start', a), ('end', b)]:
            endpoint = rule['span'][name]
            if (stop_ids[pos] != endpoint['stopId'] or endpoint['sequenceOneBased'] != pos + 1
                    or stop_ids[:pos + 1].count(stop_ids[pos]) != endpoint['occurrenceOrdinalOfSameStopId']):
                raise ValueError('Reviewed endpoint identity/occurrence mismatch')
        duration = rule['durationEvidence']
        duration_source=sources[duration['sourceId']]
        if duration['sourceId'] not in rule['evidenceSourceIds'] or rid not in duration_source['routeIds']:
            raise ValueError('Duration source does not belong to the reviewed route/event')
        if duration['type'] == 'published_route_duration_field':
            if (duration_source['kind']!='timetable' or a != 0 or b != len(stop_ids) - 1
                    or route['durationMinutes'] * 60 != budget):
                raise ValueError('Whole-direction duration cannot be sliced or changed')
        elif duration['type'] == 'dated_planned_departure_to_closing_interval':
            cells = duration['plannedCells']
            direction=lambda value: ''.join(c for c in value.upper() if c.isalnum())
            def clock(value):
                hour, minute = map(int, value.split(':'))
                if not 0 <= hour < 30 or not 0 <= minute < 60:
                    raise ValueError('Invalid published plan clock')
                return hour * 3600 + minute * 60
            if (duration_source['kind']!='dated_notice' or day != duration['announcedCalendar'] or day != 'weekday'
                    or len(cells)!=5 or duration['sourceTableIndexZeroBased']!=0
                    or str(duration['plannedRowNumber'])!=cells[0]
                    or duration['directionLabel']!=cells[3] or duration['changeLabel']!=cells[4]
                    or direction(cells[3])!=direction(note)
                    or digest(cells) != duration['plannedRowSha256']
                    or clock(cells[1]) != seconds or clock(cells[2]) - seconds != budget
                    or duration['departureClock']!=cells[1] or duration['closingClock']!=cells[2]
                    or not duration.get('publicationDate') or not duration.get('announcedEffectiveFrom')):
                raise ValueError('Dated plan budget/calendar binding mismatch')
        else:
            raise ValueError('Unsupported reviewed duration evidence')
        active[key] = rule
    return active, withheld
