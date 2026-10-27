"""Build a complete offline data bundle; never route or solve during publishing."""
import json
from pathlib import Path
import shutil
import sys
from html import escape
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.publication import canonical, require, sha, snapshot, validated_cache


def prepare():
    plan, plan_sha = snapshot()
    captured, routes = validated_cache(plan,plan_sha)
    owned = ROOT / 'work/pages-public'
    require(owned.resolve().is_relative_to(ROOT.resolve()), 'Publication directory outside workspace')
    marker = owned / '.generated-by-build-pages'
    if owned.exists():
        require(owned.resolve() == owned.absolute() and not owned.is_symlink() and
            marker.is_file() and marker.read_text() == 'ankara-pages-v1', 'Refusing to clear an unowned publication directory')
    else:
        owned.mkdir(parents=True); marker.write_text('ankara-pages-v1')
    site = owned / 'site'
    require(site.resolve().parent == owned.resolve() and not site.is_symlink(), 'Publication directory outside owned workspace')
    if site.exists(): shutil.rmtree(site)
    public = site / 'publication'; public.mkdir(parents=True)
    files = {}
    def write(kind,blob):
        checksum = sha(blob)
        filename = kind + '.' + checksum + '.json'
        path = public / filename; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(blob)
        return {'file':filename,'sha256':checksum,'bytes':len(blob)}
    def read(name): return (ROOT / name).read_bytes()
    dataset = json.loads(read('data/processed/dataset.json'))
    dataset['healthPlanning'] = json.loads(read('data/processed/health-planning.json'))
    dataset['sources'] = json.loads(read('docs/sources.json'))
    files['/api/data'] = write('data',canonical(dataset))
    files['/api/planning-policy'] = write('policy',read('data/planning-policy.json'))
    files['/api/permanent-plan'] = write('plan',read('data/processed/permanent-plan.json'))
    for layer in ('province','districts','roads'):
        files['/api/layers/' + layer] = write('layers/' + layer,read('data/processed/' + layer + '.geojson'))
    route_files = {key:write('routes/' + key.replace('/','-'),blob) for key,(blob,_) in routes.items()}
    require(snapshot()[1] == plan_sha, 'Plan changed while building publication')
    manifest = {'format':1,'delivery':'precomputed','planId':plan['planId'],'sourcePlanSHA256':plan_sha,
        'transitPackageId':plan['identity']['transitPackageId'],'capturedAt':captured['completedAt'],
        'builtAt':datetime.now(timezone.utc).isoformat(),'counts':captured['counts'], 'files':files,'routes':route_files}
    manifest['publicationId'] = 'pages-' + sha(canonical(manifest))
    (public / 'manifest.json').write_bytes(canonical(manifest))
    policy = plan['policy']
    targets = ''.join('<article><h2>'+escape(str(t['value']))+' '+escape(t['unit'])+'</h2><p>'+escape(t['rationale'])+'</p><p class="muted">'+escape(t['applicability'])+'</p></article>' for t in policy['targets'])
    sources = ''.join('<article><a rel="noreferrer" href="'+escape(s['url'],quote=True)+'">'+escape(s['title'])+'</a><p>'+escape(s.get('locator',''))+'</p><p class="muted">'+escape(s.get('role',''))+'</p></article>' for s in policy['sources'])
    document='''<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sabit hedeflerin dayanağı · ERİŞİM</title><style>body{margin:0;background:#f3f5ef;color:#294834;font:16px/1.8 system-ui,sans-serif}main{max-width:800px;margin:36px auto;padding:32px;background:#fff;border:1px solid #e1e7d9;border-radius:18px}h1{line-height:1.3;letter-spacing:-1px;font-weight:550}h2{font-size:22px;font-weight:550}a{color:#315e3d;text-underline-offset:4px}article{padding:18px 0;border-bottom:1px solid #e4eadc}.muted{color:#66765d;font-size:14px}@media(max-width:600px){main{margin:14px;padding:22px}}</style><main><a href="./">← Haritaya dön</a><h1>Planlama hedeflerinin gerekçesi</h1><p>Araba için 30, toplu taşıma için 60 dakika; il genelinde %95 ve her ilçede en az %80 talep kapsamı, bu projenin sabit politikasıdır. Literatürden yararlanılarak seçilmiştir; evrensel, yasal veya klinik standart değildir. İlçe tabanı ayrıca korunan proje eşitlik tercihidir.</p>'''+targets+'<h2>Birincil kaynaklar</h2>'+sources+'<p>Tarihsel ulaşım verisi ve beş kayıtlı kesit kullanılır. Bunlar bütün gün hizmet veya gerçek klinik kapasite garantisi oluşturmaz. Konumsuz nüfus paydada tutulur; seçilen hastane sayısının asgari ihtiyaç olduğu kanıtlanmaz.</p></main></html>'
    (site / 'method.html').write_text(document,encoding='utf8',newline='\n')
    (site / '.nojekyll').write_bytes(b'')
    size = sum(p.stat().st_size for p in site.rglob('*') if p.is_file())
    require(size < 900 * 1024 ** 2, 'Publication exceeds the Pages size budget')
    print(json.dumps({'publicationId':manifest['publicationId'],'routes':manifest['counts'],
        'megabytes':round(size/1024**2,2),'publicDir':str(site)},ensure_ascii=False))
    return site


if __name__ == '__main__': prepare()
