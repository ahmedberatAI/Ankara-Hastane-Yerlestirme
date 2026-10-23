"""Build separately identified departure-window matrices only below work/.

Default: a hard-60-second, eight-origin/full-candidate pilot for 08:00/08:05.
Full 44-profile execution is explicit; no optimization is performed here.
An accepted manifest is written last, only after all requested profiles pass.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from time import monotonic
import zipfile

import numpy as np
from scipy.sparse import load_npz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.window_routing import (profile_grid, CONSTANTS, route_batch_explicit,
                                    route_events_explicit, compare_minutes)
from scripts.transit_provenance import check_package

INDEPENDENT_ORIGINS = (42, 295, 54, 510, 1239, 638, 963, 228)
DATA_NAMES = ('dataset.json', 'health-planning.json', 'example-transit-result.json',
              'transit-package.json', 'joint-plan.json', 'travel-plan.json',
              'travel-proof.json', 'travel-summary.json', 'ego-network.json.gz',
              'ego-access.npz', 'ego-egress.npz', 'ego-transfers.npz', 'ego-direct.npz',
              'transit-weekday-0800-matrix.npz', 'transit-weekday-1000-matrix.npz',
              'transit-saturday-1000-matrix.npz', 'transit-sunday-1000-matrix.npz')
ARCHIVE = 'docs/experiments/departure-0805-evidence.zip'
SOURCE_FILES = tuple('data/processed/'+name for name in DATA_NAMES)+(ARCHIVE,)
ROUTING_CODE = ('backend/window_routing.py', 'scripts/build_window_matrices.py',
                'backend/timetable.py', 'scripts/transit_provenance.py')
FROZEN_CODE = ('backend/joint_model.py', 'backend/joint_solver.py', 'backend/joint_heuristic.py',
               'scripts/run_joint_plan.py', 'scripts/audit_joint_plan.py', 'scripts/transit_provenance.py',
               'backend/joint_travel.py', 'scripts/run_joint_travel.py', 'scripts/audit_joint_travel.py')
ID_FIELDS = ('format', 'artifactType', 'mode', 'status', 'parentTransitPackageId', 'profiles',
             'initialProfileIds', 'producedProfileIds', 'sourceSHA256', 'routingCodeLF_SHA256',
             'frozenModelCodeLF_SHA256', 'indices', 'constants', 'archived0805')
ARCHIVE_REFERENCE = {
    'archive': ARCHIVE,
    'matrixMember': 'work/referees/profile-shift-full-v07.npz',
    'matrixSHA256': '51b24496428a2d84f614c6809779aea5576512a8867bf7d6b0a519179070faab',
    'reportMember': 'work/referees/profile-shift-full-v07.json',
    'reportSHA256': 'b9f60e61b3bbee0c3aadf670e8f400338fa95dae015bdd590d3d5243096e4eb0',
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')


def sha_bytes(value): return hashlib.sha256(value).hexdigest()


def sha(path, lf=False):
    value = Path(path).read_bytes()
    return sha_bytes(value.replace(b'\r\n', b'\n') if lf else value)


LOADED_CODE = {name: sha(ROOT/name, True) for name in ROUTING_CODE}


def require(condition, message):
    if not condition: raise ValueError(message)


def safe_work_path(path, root=None):
    root = Path(ROOT if root is None else root).resolve(); path = Path(path).absolute()
    base = root/'work'/'window-routing'
    require(path.is_relative_to(base) and path != base, 'Output must be a child of work/window-routing')
    # Parent symlinks/junctions must not redirect even a not-yet-created path.
    require(path.resolve() == path, 'Redirected work path')
    return path


def exclusive_bytes(path, content):
    """Exclusive publication: unique temp inode; never truncate/follow a target."""
    path = Path(path)
    require(not path.exists() and not path.is_symlink(), 'Existing output cannot be replaced')
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        # link is atomic and fails if the target appeared after our existence check.
        os.link(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def exclusive_json(path, value): exclusive_bytes(path, canonical(value)+b'\n')


def identities(root=ROOT):
    return {'sourceSHA256': {name: sha(root/name) for name in SOURCE_FILES},
            'routingCodeLF_SHA256': {name: sha(root/name, True) for name in ROUTING_CODE},
            'frozenModelCodeLF_SHA256': {name: sha(root/name, True) for name in FROZEN_CODE}}


def recheck(expected, root=ROOT):
    require(identities(root) == expected, 'Source/code changed during window routing')
    if root == ROOT:
        require(expected['routingCodeLF_SHA256'] == LOADED_CODE, 'Loaded routing code differs from disk')


def read_archived_0805(root, source_hashes, data):
    with zipfile.ZipFile(root/ARCHIVE) as archive:
        names = archive.namelist()
        payloads = {}
        for kind in ('matrix', 'report'):
            member = ARCHIVE_REFERENCE[kind+'Member']
            require(names.count(member) == 1, 'Missing/duplicate archive member')
            require(archive.getinfo(member).file_size < 32_000_000, 'Oversized archive member')
            payloads[kind] = archive.read(member)
            require(sha_bytes(payloads[kind]) == ARCHIVE_REFERENCE[kind+'SHA256'], 'Archived experiment differs')
    report = json.loads(payloads['report'])
    require(report['sourceSHA256'] == {name: source_hashes['data/processed/'+name] for name in DATA_NAMES},
            'Archived 08:05 experiment has different source data')
    require(report['profiles']['0805'] == {'day':'weekday', 'startSeconds':29100}, 'Archived clock differs')
    with np.load(io.BytesIO(payloads['matrix']), allow_pickle=False) as arrays:
        result = {key: arrays[key].copy() for key in arrays.files}
    require(set(result) == {'originIndices','targetCandidateIndices','minutes0800','minutes0805'}, 'Archive array schema')
    require(np.array_equal(result['originIndices'], np.arange(len(data['demands']))), 'Archive origin order')
    targets = result['targetCandidateIndices']
    require(targets.dtype.kind in 'iu' and len(set(targets.tolist())) == len(targets)
            and np.all((targets >= 0)&(targets < len(data['candidates']))), 'Archive target order')
    require(report['targets'] == [{'index':int(i),'id':data['candidates'][int(i)]['id']} for i in targets], 'Archive target IDs')
    for key in ('minutes0800','minutes0805'):
        require(result[key].shape == (len(data['demands']),len(targets)) and result[key].dtype == np.float32,
                'Archive dimensions/type')
        require(not np.isnan(result[key]).any() and np.all(result[key]>=0), 'Archive values')
    return result


def package_identity(manifest):
    payload = {name: manifest[name] for name in ID_FIELDS}
    payload['matrices'] = [{key: row[key] for key in ('profileId','file','sha256','shape')} for row in manifest['matrices']]
    prefix = 'window-' if manifest['mode'] == 'full' else 'window-pilot-'
    return prefix + sha_bytes(canonical(payload))


def fifo_audit(folder, records, profiles):
    lookup = {x['profileId']:x for x in records}; comparisons = []
    for base in dict.fromkeys(p['baseProfileId'] for p in profiles):
        group = sorted((p for p in profiles if p['baseProfileId']==base and p['id'] in lookup),
                       key=lambda p:p['departureSeconds'])
        for earlier, later in zip(group, group[1:]):
            with np.load(folder/lookup[earlier['id']]['file'],allow_pickle=False) as z: a=z['minutes'].copy()
            with np.load(folder/lookup[later['id']]['file'],allow_pickle=False) as z: b=z['minutes'].copy()
            finite=np.isfinite(a)&np.isfinite(b)
            delta=(later['departureSeconds']-earlier['departureSeconds'])/60
            # Promote before subtraction; do not lose precision in a float32 sum.
            violation=float(np.maximum(a[finite].astype(float)-b[finite].astype(float)-delta,0).max(initial=0))
            require(violation<=2e-5,'FIFO absolute arrival contradiction')
            comparisons.append({'earlierProfileId':earlier['id'],'laterProfileId':later['id'],
                                'commonFinitePairs':int(finite.sum()),'maxEarlyArrivalViolationMinutes':violation})
    return {'comparisons':comparisons,'toleranceMinutes':2e-5}


def worker(job_path):
    job_path=safe_work_path(job_path); folder=job_path.parent
    job=json.loads(job_path.read_text(encoding='utf8')); began=monotonic()
    require(job['profile'] in profile_grid(), 'Unknown profile descriptor')
    require(job['mode'] in ('pilot','full'), 'Unknown routing mode')
    require(type(job['budgetSeconds']) in (int,float) and math.isfinite(job['budgetSeconds'])
            and 0<job['budgetSeconds']<=300,'Invalid routing budget')
    deadline=began+job['budgetSeconds']; recheck(job['bindings'])
    require(check_package()==job['parentTransitPackageId'],'Parent package changed')
    data=json.loads((ROOT/'data/processed/dataset.json').read_text(encoding='utf8'))
    rows=list(INDEPENDENT_ORIGINS) if job['mode']=='pilot' else list(range(len(data['demands'])))
    require(job['originIndices']==rows,'Origin subset differs')
    targets=len(data['candidates'])
    network=json.loads(gzip.decompress((ROOT/'data/processed/ego-network.json.gz').read_bytes()))
    access,egress,transfers,direct=[load_npz(ROOT/'data/processed'/f'ego-{name}.npz') for name in ('access','egress','transfers','direct')]
    access=access[rows];egress=egress[:,:targets].tocsr();direct=direct[rows,:targets].tocsr()
    p=job['profile']
    minutes=route_batch_explicit(network,access,egress,transfers,direct,p['serviceDay'],p['departureSeconds'],deadline=deadline)
    require(minutes.shape==(len(rows),targets) and minutes.dtype==np.float32,'Produced matrix shape/type')
    require(not np.isnan(minutes).any() and np.all(minutes>=0) and np.all(minutes[np.isfinite(minutes)]<=120.00001),'Produced values')
    maximum=0.0
    for origin in INDEPENDENT_ORIGINS:
        local=rows.index(origin)
        expected=route_events_explicit(network,access,egress,transfers,direct,local,p['serviceDay'],p['departureSeconds'],deadline=deadline)
        maximum=max(maximum,compare_minutes(minutes[local],expected))
    baseline=None
    if p['offsetMinutes']==0:
        with np.load(ROOT/'data/processed'/f'transit-{p["baseProfileId"]}-matrix.npz',allow_pickle=False) as z:
            expected=z['minutes'][rows,:targets]
        error=compare_minutes(minutes,expected,exact=True)
        baseline={'kind':'canonical','comparedRows':len(rows),'comparedColumns':targets,'maxMinutesError':error,'bitIdentical':True}
    if p['id']=='weekday-0805':
        archived=read_archived_0805(ROOT,job['bindings']['sourceSHA256'],data)
        cols=archived['targetCandidateIndices']; expected=archived['minutes0805'][rows]
        error=compare_minutes(minutes[:,cols],expected,exact=True)
        baseline={'kind':'archived_0805_subset','comparedRows':len(rows),'comparedColumns':len(cols),'maxMinutesError':error,'bitIdentical':True}
    recheck(job['bindings']);require(check_package()==job['parentTransitPackageId'],'Parent changed at exit')
    require(monotonic()<deadline,'Worker deadline exceeded after validation')
    buffer=io.BytesIO();np.savez_compressed(buffer,minutes=minutes)
    name=p['id']+'.npz';exclusive_bytes(folder/name,buffer.getvalue())
    record={'profileId':p['id'],'file':name,'sha256':sha(folder/name),'shape':list(minutes.shape),
            'audit':{'validated':True,'independentOriginIndices':list(INDEPENDENT_ORIGINS),
                     'independentDestinationsPerOrigin':targets,'independentMaxMinutesError':maximum,
                     'baselineCheck':baseline,'elapsedSeconds':monotonic()-began}}
    require(monotonic()<deadline,'Worker publication deadline exceeded')
    exclusive_json(folder/(p['id']+'.audit.json'),record)
    print(json.dumps({'profile':p['id'],'seconds':record['audit']['elapsedSeconds'],'sha256':record['sha256']}),flush=True)


def build(mode='pilot', run_label=None, profile_seconds=300):
    require(mode in ('pilot','full'),'Unknown mode')
    require(type(profile_seconds) in (int,float) and math.isfinite(profile_seconds) and 0<profile_seconds<=300,'Invalid budget')
    began=monotonic(); now=datetime.now(timezone.utc)
    label=run_label or mode+'-'+now.strftime('%Y%m%dT%H%M%S%fZ')
    require(isinstance(label,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',label)
            and label.upper() not in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]},'Unsafe run label')
    folder=safe_work_path(ROOT/'work/window-routing'/label)
    require(not folder.exists(),'Immutable run folder exists')
    folder.parent.mkdir(parents=True,exist_ok=True); folder.mkdir()
    try:
        package=check_package(); bindings=identities();recheck(bindings)
        data=json.loads((ROOT/'data/processed/dataset.json').read_text(encoding='utf8'))
        require(len(data['demands'])>max(INDEPENDENT_ORIGINS),'Independent origin selection unavailable')
        rows=list(INDEPENDENT_ORIGINS) if mode=='pilot' else list(range(len(data['demands'])))
        indices={'origins':[{'index':i,'id':data['demands'][i]['id']} for i in rows],
                 'candidates':[{'index':i,'id':d['id']} for i,d in enumerate(data['candidates'])]}
        require(len({x['id'] for x in indices['origins']})==len(rows),'Duplicate origin IDs')
        require(len({x['id'] for x in indices['candidates']})==len(data['candidates']),'Duplicate target IDs')
        exclusive_json(folder/'indices.json',indices)
        grid=profile_grid()
        requested=grid if mode=='full' else [p for p in grid if p['id'] in ('weekday-0800','weekday-0805')]
        records=[]
        for p in requested:
            remaining=60-(monotonic()-began) if mode=='pilot' else profile_seconds
            require(remaining>0,'Pilot total deadline exhausted')
            job={'mode':mode,'profile':p,'originIndices':rows,'parentTransitPackageId':package,
                 'bindings':bindings,'budgetSeconds':min(profile_seconds,remaining)}
            job_path=folder/(p['id']+'.job.json');exclusive_json(job_path,job)
            completed=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',str(job_path)],
                                     cwd=ROOT,timeout=min(profile_seconds,remaining))
            require(completed.returncode==0,'Routing subprocess failed; no accepted manifest')
            record=json.loads((folder/(p['id']+'.audit.json')).read_text(encoding='utf8'))
            require(record['profileId']==p['id'] and record['file']==p['id']+'.npz'
                    and record['shape']==[len(rows),len(data['candidates'])]
                    and record['sha256']==sha(folder/record['file']),'Worker output identity')
            records.append(record)
        cross=fifo_audit(folder,records,grid)
        require((folder/'indices.json').read_bytes()==canonical(indices)+b'\n','Indices changed during routing')
        for record in records:
            require(record['sha256']==sha(folder/record['file']),'Matrix changed before manifest')
        recheck(bindings);require(check_package()==package,'Parent changed before final manifest')
        require(mode!='pilot' or monotonic()-began<60,'Pilot total deadline exceeded')
        manifest={'format':1,'artifactType':'departure-window-matrices','mode':mode,
                  'status':'accepted' if mode=='full' else 'pilot_passed','parentTransitPackageId':package,
                  'profiles':grid,'initialProfileIds':[p['id'] for p in grid[:12]],
                  'producedProfileIds':[p['id'] for p in requested],**bindings,
                  'indices':{'file':'indices.json','sha256':sha(folder/'indices.json'),
                             'demandIndexSHA256':sha_bytes(canonical(indices['origins'])),
                             'candidateIndexSHA256':sha_bytes(canonical(indices['candidates']))},
                  'matrices':records,'constants':dict(CONSTANTS),'archived0805':dict(ARCHIVE_REFERENCE),
                  'crossProfileAudit':cross,'builtAt':now.isoformat(),'elapsedSeconds':monotonic()-began,
                  'scope':'Normal-day exact minute grid on the same partial EGO network and estimated offsets. '
                          'Not between-minute, whole-day, calendar-exception or observed real-world reliability. '
                          'Full global candidate order; no capacity or location optimization is performed.'}
        manifest['windowRoutingPackageId']=package_identity(manifest)
        exclusive_json(folder/'manifest.json',manifest)
        print(json.dumps({'folder':str(folder),'manifestSHA256':sha(folder/'manifest.json'),
                          'status':manifest['status'],'package':manifest['windowRoutingPackageId'],
                          'seconds':manifest['elapsedSeconds']}),flush=True)
        return manifest
    except Exception as exc:
        if not (folder/'manifest.json').exists():
            exclusive_json(folder/'failure.json',{'status':'failed_unknown','accepted':False,
                'type':type(exc).__name__,'reason':str(exc),'scope':'Partial files are not an accepted window package.'})
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full',action='store_true');parser.add_argument('--run-label')
    parser.add_argument('--profile-seconds',type=float,default=300)
    parser.add_argument('--worker',type=Path,help=argparse.SUPPRESS)
    options=parser.parse_args()
    if options.worker:
        require(not options.full and options.run_label is None,'Worker arguments cannot change mode')
        worker(options.worker)
    else:build('full' if options.full else 'pilot',options.run_label,options.profile_seconds)
