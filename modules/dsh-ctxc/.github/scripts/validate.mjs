// 校验 package.json 与 dshGo 清单（CI 用）
import { readFileSync } from 'node:fs'

const pkg = JSON.parse(readFileSync('package.json', 'utf-8'))
const d = pkg.dshGo
if (!d || d.v !== 1) throw new Error('缺少 dshGo.v=1 清单')
if (!pkg.name || !/^[a-z0-9][a-z0-9-]*$/.test(pkg.name)) throw new Error('包名不合法')
if (!pkg.main || !readFileSync(pkg.main, 'utf-8').includes("export const name = '" + pkg.name + "'")) {
  throw new Error('lib 导出名与包名不一致')
}
const ids = []
for (const slot of ['composer.actions', 'message.actions', 'composer.strip', 'panels', 'composer.tools', 'session.actions', 'turn.note']) {
  for (const it of d.contributes?.[slot] || []) {
    if (!it.id) throw new Error(slot + ' 缺 id')
    ids.push(it.id)
  }
}
if (new Set(ids).size !== ids.length) throw new Error('插件内 id 重复')
console.log('清单校验通过:', pkg.name, '|', ids.join(', ') || '(无插槽)')
