import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import net from 'node:net'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const python = path.join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python')
if (!existsSync(python) || !existsSync(path.join(root, 'dist/index.html'))) {
  console.error('Önce README kurulum adımlarını ve npm run build komutunu tamamlayın.')
  process.exit(1)
}
// Reuse an already running local motor; only stop a motor started by this run.
const motisRoot = path.join(root, 'work/free-routing-research-2026-10-26')
const motisExe = path.join(motisRoot, 'motis-2.10.2/motis.exe')
const motisData = path.join(motisRoot, 'local-motis')
const portOpen = await new Promise(resolve => {
  const socket = net.createConnection({ host: '127.0.0.1', port: 8088 })
  socket.setTimeout(1500)
  socket.once('connect', () => { socket.destroy(); resolve(true) })
  socket.once('error', () => { socket.destroy(); resolve(false) })
  socket.once('timeout', () => { socket.destroy(); resolve(false) })
})
let motor
if (!portOpen && process.platform === 'win32' && existsSync(motisExe) && existsSync(path.join(motisData, 'config.yml')) && existsSync(path.join(motisData, 'data'))) {
  motor = spawn(motisExe, ['server', '--data', 'data', '--log-level', 'error'], { cwd: motisData, stdio: 'inherit', windowsHide: true })
  motor.on('error', error => console.error(`MOTIS başlatılamadı: ${error.message}`))
  motor.on('exit', code => console.log(`Yerel MOTIS kapandı (${code}). Araba ve kayıtlı matris hesabı kullanılabilir; canlı MOTIS rotası için motoru yeniden başlatın.`))
} else if (!portOpen) {
  console.log('MOTIS motoru çalışmıyor. Yerel kurulum için docs/motis-hybrid.md belgesine bakın; ücretli sağlayıcıya geçilmez.')
}
console.log('ERİŞİM: http://127.0.0.1:8000')
const child = spawn(python, ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8000'], { cwd: root, stdio: 'inherit' })
child.on('error', error => { console.error(error.message); process.exitCode = 1 })
child.on('exit', code => { motor?.kill(); process.exitCode = code ?? 0 })
process.on('SIGINT', () => { child.kill('SIGINT'); motor?.kill() })
process.on('SIGTERM', () => { child.kill('SIGTERM'); motor?.kill() })
