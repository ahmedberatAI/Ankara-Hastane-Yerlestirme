import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
const base='/Ankara-Hastane-Yerlestirme/', planId='permanent-'+'a'.repeat(64)
async function bundle(entry,mode='pages') {
  const built=await build({entryPoints:[entry],bundle:true,platform:'node',format:'cjs',write:false,external:['react'],
    define:{'import.meta.env.MODE':JSON.stringify(mode),'import.meta.env.BASE_URL':JSON.stringify(base)}})
  const m={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),m,m.exports)
  return m.exports
}
const client=await bundle('src/dataClient.ts'), ui=await bundle('src/Permanent.tsx')
const bytes=value=>Buffer.from(JSON.stringify(value)), digest=b=>createHash('sha256').update(b).digest('hex')
const entry=(file,b)=>({file,sha256:digest(b),bytes:b.length})
function fixture() {
  const p=bytes({planId}), d=bytes({message:'Kayıtlı veri'})
  const request={planId,view:'car',demandId:'D',candidateId:'C'}
  const record={format:1,request,sourcePlanSHA256:digest(p),response:{planId,routeMode:'car',minutes:12}}
  const route=bytes(record)
  const manifest={format:1,delivery:'precomputed',publicationId:'pages-'+'b'.repeat(64),planId,sourcePlanSHA256:digest(p),
    files:{'/api/data':entry('data.json',d),'/api/permanent-plan':entry('plan.json',p)},routes:{'car/D/C':entry('routes/car-D-C.json',route)}}
  return {manifest,request,record,files:{'data.json':d,'plan.json':p,'routes/car-D-C.json':route}}
}
let calls=[]
function install(f) {
  client.resetPublicationCache();calls=[]
  globalThis.fetch=async(url,init={})=>{
    calls.push({url,method:init.method || 'GET'})
    assert.ok(url.startsWith(base+'publication/'),'No request may reach a backend or another host')
    const file=url.slice((base+'publication/').length)
    const body=file==='manifest.json'?bytes(f.manifest):f.files[file]
    return new Response(body ?? '',{status:body?200:404})
  }
}
const options=f=>({method:'POST',body:JSON.stringify(f.request)})
let count=0
async function test(name,fn) {try{await fn();count++}catch(e){throw new Error(name,{cause:e})}}
await test('same UI endpoints map to subpath files with no API',async()=>{
  const f=fixture();install(f)
  assert.deepEqual(await client.readJson('/api/data'),{message:'Kayıtlı veri'})
  assert.deepEqual(await client.readJson('/api/permanent-plan'),{planId})
  assert.ok(calls.every(c=>c.method==='GET'))
})
await test('route POST becomes verified static GET',async()=>{
  const f=fixture();install(f)
  assert.deepEqual(await client.readJson('/api/permanent-route',options(f)),f.record.response)
  assert.ok(calls.every(c=>c.method==='GET'))
})
await test('manifest cannot name another plan while serving valid plan bytes',async()=>{
  const f=fixture();f.manifest.planId='permanent-'+'c'.repeat(64);install(f)
  await assert.rejects(client.readJson('/api/permanent-plan'))
})
for(const name of ['missing-route','old-plan','extra-field','unsafe-id','provider-field']) await test(name,async()=>{
  const f=fixture()
  if(name==='missing-route')f.manifest.routes={}
  if(name==='old-plan')f.request.planId='permanent-'+'c'.repeat(64)
  if(name==='extra-field')f.request.threshold=120
  if(name==='unsafe-id')f.request.demandId='../D'
  if(name==='provider-field')f.request.transitEngine='ego'
  install(f);await assert.rejects(client.readJson('/api/permanent-route',options(f)))
  assert.equal(calls.length,1)
})
for(const name of ['../secret.json','/api/data.json','https://evil.example/data.json','%2e%2e/data.json']) await test('unsafe path '+name,async()=>{
  const f=fixture();f.manifest.files['/api/data'].file=name;install(f)
  await assert.rejects(client.readJson('/api/data'));assert.equal(calls.length,1)
})
for(const name of ['checksum','size','unknown-endpoint','bad-version','mixed-plan']) await test(name,async()=>{
  const f=fixture()
  if(name==='checksum')f.manifest.files['/api/data'].sha256='0'.repeat(64)
  if(name==='size')f.manifest.files['/api/data'].bytes++
  if(name==='bad-version')f.manifest.format=true
  if(name==='mixed-plan')f.manifest.sourcePlanSHA256='0'.repeat(64)
  install(f);await assert.rejects(client.readJson(name==='unknown-endpoint'?'/api/solve':'/api/data'))
})
for(const name of ['plan','endpoint','record-source','format-bool']) await test('foreign record '+name,async()=>{
  const f=fixture()
  if(name==='plan')f.record.response.planId='permanent-'+'c'.repeat(64)
  if(name==='endpoint')f.record.request={...f.request,candidateId:'other'}
  if(name==='record-source')f.record.sourcePlanSHA256='0'.repeat(64)
  if(name==='format-bool')f.record.format=true
  f.files['routes/car-D-C.json']=bytes(f.record)
  f.manifest.routes['car/D/C']=entry('routes/car-D-C.json',f.files['routes/car-D-C.json'])
  install(f);await assert.rejects(client.readJson('/api/permanent-route',options(f)))
})
await test('every captured route passes the actual display contract',async()=>{
  const plan=JSON.parse(readFileSync('data/processed/permanent-plan.json','utf8'))
  const manifest=JSON.parse(readFileSync('data/precomputed-routes/manifest.json','utf8'))
  const expected=Object.fromEntries(['car','transit'].flatMap(view=>plan.profiles[view==='car'?'car':plan.criticalTransitProfile].assignments.flatMap(a=>a.allocations.map(x=>[`${view}/${a.demandId}/${x.candidateId}`,{view,demandId:a.demandId,candidateId:x.candidateId}]))))
  assert.deepEqual(Object.keys(manifest.routes).sort(),Object.keys(expected).sort())
  for(const [key,e] of Object.entries(manifest.routes)) {
    const b=readFileSync('data/precomputed-routes/'+e.file);assert.equal(digest(b),e.sha256)
    const r=JSON.parse(b.toString('utf8')), q=expected[key]
    assert.equal(ui.permanentRouteProblem(r.response,plan,q.view,q.demandId,q.candidateId),null,key)
  }
})
await test('algorithm explanation names decisions, both stages and proof limits',async()=>{
  const Method=(await bundle('src/OptimizationMethod.tsx')).default
  const policy=JSON.parse(readFileSync('data/planning-policy.json','utf8'))
  const plan=JSON.parse(readFileSync('data/processed/permanent-plan.json','utf8'))
  const html=renderToStaticMarkup(React.createElement(Method,{policy,plan}))
  for(const phrase of ['karma tamsayılı doğrusal programlama','HiGHS','sezgisel','yatak','hekim','bütçe','kesme kısıtları','asgari hastane ihtiyacı değildir','süre sınırlı'])assert.ok(html.includes(phrase),phrase)
  assert.equal((html.match(/<li>/g)||[]).length,4)
})
console.log(`${count} publication client and algorithm checks passed; all captured routes validated`)
