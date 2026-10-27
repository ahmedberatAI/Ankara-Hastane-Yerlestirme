/** Static-only preview with the same project subpath as GitHub Pages. */
import http from 'node:http'
import path from 'node:path'
import { readFile, stat } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../dist-pages')
const html=await readFile(path.join(root,'index.html'),'utf8')
const base=html.match(/src="([^\"]*\/)assets\/[^\"]+\.js"/)?.[1]
if(!base || !/^\/(?:[A-Za-z0-9_-]+\/)?$/.test(base)) throw Error('Derlenmiş Pages proje yolu bulunamadı')
const types = { '.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8', '.css':'text/css; charset=utf-8', '.json':'application/json; charset=utf-8', '.png':'image/png', '.svg':'image/svg+xml' }
http.createServer(async (req,res) => {
  if(!['GET','HEAD'].includes(req.method)) { res.writeHead(405); return res.end() }
  try {
    const url = new URL(req.url,'http://127.0.0.1:4173')
    if(url.pathname === '/') {res.writeHead(302,{Location:base});return res.end()}
    if(!url.pathname.startsWith(base)) {res.writeHead(404);return res.end()}
    const name=decodeURIComponent(url.pathname.slice(base.length)) || 'index.html'
    const target=path.resolve(root,name)
    if(!target.startsWith(root+path.sep) || !(await stat(target)).isFile()) {res.writeHead(404);return res.end()}
    const data=await readFile(target)
    res.writeHead(200,{'Content-Type':types[path.extname(target)] || 'application/octet-stream','Cache-Control':'no-cache'})
    res.end(req.method==='HEAD' ? undefined : data)
  } catch {res.writeHead(404);res.end()}
}).listen(4173,'127.0.0.1',()=>console.log(`Statik Pages önizlemesi: http://127.0.0.1:4173${base} (API veya Python sunucusu kullanmaz)`))
