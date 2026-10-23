from copy import deepcopy
from pathlib import Path
import json
import os
import subprocess

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from backend import timetable as frozen
from backend.window_routing import (profile_grid, BASE_PROFILES, OFFSETS, route_batch_explicit,
                                    route_events_explicit, compare_minutes)
from scripts import build_window_matrices as builder


def csr(shape, entries):
    return csr_matrix(([x[2] for x in entries],([x[0] for x in entries],[x[1] for x in entries])),shape=shape,dtype=float)


def pattern(stops, offsets, departures):
    return {'stops':stops,'offsets':offsets,
            'departures':{day:list(departures) for day in ('weekday','saturday','sunday')}}


def fixture():
    net={'stops':[{}]*4,'patterns':[
        pattern([0,1],[0,600],[28920,30000,36120,37200]),
        pattern([2,3],[0,600],[29700,30780,36900,37980])]}
    access=csr((2,4),[(0,0,60),(1,0,120)])
    egress=csr((4,2),[(3,0,60)])
    transfer=csr((4,4),[(1,2,120)])
    direct=csr((2,2),[(0,1,2700),(1,1,7200)])
    return net,access,egress,transfer,direct


def test_exact_profile_order_and_clock_identity():
    profiles=profile_grid()
    assert len(profiles)==len({p['id'] for p in profiles})==44
    assert [p['id'] for p in profiles[:4]]==[p[0] for p in BASE_PROFILES]
    assert [p['offsetMinutes'] for p in profiles[:12]]==[0]*4+[-5]*4+[5]*4
    for k,offset in enumerate(OFFSETS):
        for j,(base,day,start) in enumerate(BASE_PROFILES):
            p=profiles[k*4+j]
            assert p['baseProfileId']==base and p['serviceDay']==day
            assert p['departureSeconds']==start+offset*60 and p['timeZone']=='Europe/Istanbul'


@pytest.mark.parametrize('profile,day,start',BASE_PROFILES)
def test_frozen_four_profiles_bit_equal_without_mutation(profile,day,start):
    args=fixture(); before=deepcopy(frozen.PROFILES)
    expected=frozen.route_batch(*args,profile,batch_size=1)
    actual=route_batch_explicit(*args,day,start,batch_size=1)
    assert np.array_equal(actual,expected) and frozen.PROFILES==before
    for i in range(2):compare_minutes(actual[i],route_events_explicit(*args,i,day,start))


@pytest.mark.parametrize('seed',range(12))
def test_random_small_patterns_agree_with_independent_event_states(seed):
    rng=np.random.default_rng(seed); n=7
    patterns=[]
    for _ in range(8):
        stops=rng.choice(n,4,replace=False).tolist()
        offsets=np.r_[0,np.cumsum(rng.integers(50,500,size=3))].tolist()
        departures=sorted(set((28800+rng.integers(0,3600,size=7)).tolist()))
        patterns.append(pattern(stops,offsets,departures))
    net={'stops':[{}]*n,'patterns':patterns}
    access=csr((3,n),[(i,j,float(rng.integers(0,900))) for i in range(3) for j in range(n) if rng.random()<.3])
    egress=csr((n,5),[(i,j,float(rng.integers(0,900))) for i in range(n) for j in range(5) if rng.random()<.2])
    transfer=csr((n,n),[(i,j,float(rng.integers(0,300))) for i in range(n) for j in range(n) if i!=j and rng.random()<.15])
    direct=csr((3,5),[(i,j,float(rng.integers(0,7201))) for i in range(3) for j in range(5) if rng.random()<.2])
    args=net,access,egress,transfer,direct
    for start in (28800,29100):
        actual=route_batch_explicit(*args,'weekday',start,batch_size=2)
        for origin in range(3):compare_minutes(actual[origin],route_events_explicit(*args,origin,'weekday',start))


def test_later_start_changes_elapsed_not_absolute_arrival_and_board_slack():
    args=fixture()
    early=route_batch_explicit(*args,'weekday',28800)
    later=route_batch_explicit(*args,'weekday',29100)
    common=np.isfinite(early)&np.isfinite(later)
    assert np.all(later[common]+5>=early[common]-2e-5)
    assert later[0,0]>early[0,0] # misses 08:02 service
    assert early[0,1]==later[0,1]==45 # direct walk unchanged


def test_no_fourth_boarding_or_chained_transfer_walk():
    t=36000
    net={'stops':[{}]*6,'patterns':[pattern([i,i+1],[0,120],[t+120+i*240]) for i in range(4)]}
    args=(net,csr((1,6),[(0,0,10)]),csr((6,2),[(4,0,10),(5,1,10)]),
          csr((6,6),[(1,2,10),(2,5,10)]),csr((1,2),[]))
    actual=route_batch_explicit(*args,'weekday',t)
    assert np.isfinite(actual[0,0]) and np.isinf(actual[0,1])
    compare_minutes(actual[0],route_events_explicit(*args,0,'weekday',t))
    # Removing the one-transfer shortcut requires four boardings, which is forbidden.
    args=(*args[:3],csr((6,6),[]),args[4])
    assert np.isinf(route_batch_explicit(*args,'weekday',t)).all()
    assert np.isinf(route_events_explicit(*args,0,'weekday',t)).all()


@pytest.mark.parametrize('day,start',[('holiday',28800),('weekday',True),('weekday',28800.),
                                     ('weekday',-1),('weekday',86400),('weekday',float('nan'))])
def test_bad_explicit_clock_rejected(day,start):
    with pytest.raises(ValueError):route_batch_explicit(*fixture(),day,start)


@pytest.mark.parametrize('operation',[route_batch_explicit,route_events_explicit])
def test_deadline_prevents_accepting_partial_result(operation):
    args=fixture()
    extra=(0,'weekday',28800) if operation is route_events_explicit else ('weekday',28800)
    with pytest.raises(TimeoutError):operation(*args,*extra,deadline=1,clock=lambda:1)


@pytest.mark.parametrize('value',[-1,float('nan'),float('inf')])
def test_bad_walk_cost_rejected(value):
    args=list(fixture());args[1]=args[1].copy();args[1].data[0]=value
    with pytest.raises(ValueError):route_batch_explicit(*args,'weekday',28800)


def test_nonfinite_or_decreasing_offsets_rejected():
    args=list(fixture());args[0]=deepcopy(args[0]);args[0]['patterns'][0]['offsets']=[600,0]
    with pytest.raises(ValueError):route_batch_explicit(*args,'weekday',28800)


def test_existing_hardlink_and_symlink_targets_are_never_truncated(tmp_path):
    source=tmp_path/'source';source.write_bytes(b'original');dest=tmp_path/'target'
    os.link(source,dest)
    with pytest.raises(ValueError):builder.exclusive_bytes(dest,b'replacement')
    assert source.read_bytes()==dest.read_bytes()==b'original'


def test_fixed_temp_hardlink_does_not_affect_unique_atomic_publish(tmp_path):
    source=tmp_path/'source';source.write_bytes(b'original')
    os.link(source,tmp_path/'out.json.tmp')
    builder.exclusive_bytes(tmp_path/'out.json',b'new')
    assert source.read_bytes()==b'original' and (tmp_path/'out.json').read_bytes()==b'new'


def test_target_appearing_during_publish_is_preserved(tmp_path,monkeypatch):
    source=tmp_path/'source';source.write_bytes(b'original');dest=tmp_path/'out'
    original=os.link
    def racing_link(a,b):
        original(source,b)
        return original(a,b)
    monkeypatch.setattr(builder.os,'link',racing_link)
    with pytest.raises(FileExistsError):builder.exclusive_bytes(dest,b'bad')
    assert source.read_bytes()==dest.read_bytes()==b'original'
    assert not list(tmp_path.glob('.*.tmp'))


def test_path_escape_rejected(tmp_path):
    with pytest.raises(ValueError):builder.safe_work_path(tmp_path/'data/processed/output',tmp_path)
    with pytest.raises(ValueError):builder.safe_work_path(tmp_path/'work/window-routing',tmp_path)
    assert builder.safe_work_path(tmp_path/'work/window-routing/new/manifest.json',tmp_path)==tmp_path/'work/window-routing/new/manifest.json'


def test_parent_symlink_rejected(tmp_path):
    outside=tmp_path/'outside';outside.mkdir();base=tmp_path/'work/window-routing';base.mkdir(parents=True)
    try:(base/'link').symlink_to(outside,target_is_directory=True)
    except OSError:pytest.skip('Windows symbolic-link privilege unavailable')
    with pytest.raises(ValueError):builder.safe_work_path(base/'link/manifest.json',tmp_path)


def identity_manifest():
    result={name:{} for name in builder.ID_FIELDS}
    result.update(format=1,artifactType='departure-window-matrices',mode='full',status='accepted',
                  profiles=profile_grid(),initialProfileIds=[p['id'] for p in profile_grid()[:12]],
                  matrices=[{'profileId':'weekday-0800','file':'weekday-0800.npz','sha256':'a'*64,'shape':[1413,4701],'audit':{}}])
    return result


def test_package_identity_binds_profile_source_matrix_and_index_but_not_runtime():
    a=identity_manifest();initial=builder.package_identity(a)
    a['builtAt']='later';a['matrices'][0]['audit']['elapsedSeconds']=100
    assert builder.package_identity(a)==initial
    for change in ('profile','matrix','indices','source'):
        b=deepcopy(a)
        if change=='profile':b['profiles'][0]['departureSeconds']+=1
        elif change=='matrix':b['matrices'][0]['sha256']='b'*64
        elif change=='indices':b['indices']={'sha256':'b'*64}
        else:b['sourceSHA256']={'data/processed/dataset.json':'b'*64}
        assert builder.package_identity(b)!=initial


def test_failed_worker_cannot_publish_accepted_manifest(tmp_path,monkeypatch):
    (tmp_path/'data/processed').mkdir(parents=True)
    data={'demands':[{'id':str(i)} for i in range(1413)],'candidates':[{'id':'h'}]}
    (tmp_path/'data/processed/dataset.json').write_text(json.dumps(data))
    monkeypatch.setattr(builder,'ROOT',tmp_path)
    monkeypatch.setattr(builder,'check_package',lambda:'test')
    monkeypatch.setattr(builder,'identities',lambda:{})
    monkeypatch.setattr(builder,'recheck',lambda bindings:None)
    monkeypatch.setattr(builder.subprocess,'run',lambda *args,**kwargs:subprocess.CompletedProcess(args,1))
    with pytest.raises(ValueError):builder.build('pilot','failed-worker')
    folder=tmp_path/'work/window-routing/failed-worker'
    assert not (folder/'manifest.json').exists()
    assert json.loads((folder/'failure.json').read_text())['status']=='failed_unknown'


def test_timeout_cannot_publish_accepted_manifest(tmp_path,monkeypatch):
    (tmp_path/'data/processed').mkdir(parents=True)
    data={'demands':[{'id':str(i)} for i in range(1413)],'candidates':[{'id':'h'}]}
    (tmp_path/'data/processed/dataset.json').write_text(json.dumps(data))
    monkeypatch.setattr(builder,'ROOT',tmp_path)
    monkeypatch.setattr(builder,'check_package',lambda:'test')
    monkeypatch.setattr(builder,'identities',lambda:{})
    monkeypatch.setattr(builder,'recheck',lambda bindings:None)
    def timeout(*args,**kwargs):raise subprocess.TimeoutExpired('worker',60)
    monkeypatch.setattr(builder.subprocess,'run',timeout)
    with pytest.raises(subprocess.TimeoutExpired):builder.build('pilot','timeout')
    assert not (tmp_path/'work/window-routing/timeout/manifest.json').exists()


def test_fifo_check_uses_absolute_arrival_and_rejects_beyond_tolerance(tmp_path):
    profiles=[p for p in profile_grid() if p['id'] in ('weekday-0800','weekday-0805')]
    rows=[]
    for name,minutes in [('weekday-0800',30),('weekday-0805',25)]:
        np.savez(tmp_path/(name+'.npz'),minutes=np.array([[minutes]],np.float32))
        rows.append({'profileId':name,'file':name+'.npz'})
    assert builder.fifo_audit(tmp_path,rows,profiles)['comparisons'][0]['maxEarlyArrivalViolationMinutes']==0
    np.savez(tmp_path/'weekday-0805.npz',minutes=np.array([[24.99]],np.float32))
    with pytest.raises(ValueError):builder.fifo_audit(tmp_path,rows,profiles)
