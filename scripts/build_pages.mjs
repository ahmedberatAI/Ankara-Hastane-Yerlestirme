import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const local = path.join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python')
const python = existsSync(local) ? local : (process.env.PYTHON || 'python')
for (const [command,args] of [[python,['scripts/build_pages.py']], [process.execPath,['node_modules/typescript/bin/tsc','-b']], [process.execPath,['node_modules/vite/bin/vite.js','build','--mode','pages']]]) {
  const r = spawnSync(command,args,{cwd:root,stdio:'inherit',windowsHide:true})
  if(r.error) throw r.error
  if(r.status !== 0) process.exit(r.status || 1)
}
