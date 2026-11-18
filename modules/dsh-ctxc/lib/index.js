// 出处：手机 proot 实测版 local-ctxc（Android + Ollama 1.5B Q4_K_M 实测调参）。
// 模块：压一下胶囊 / 每轮自动会话卡。相关方案见 docs/、scripts/ctxc.py。
import { execFile } from 'node:child_process'
import { readFileSync, writeFileSync, mkdirSync, statSync, readdirSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'

export const name = 'dsh-ctxc'

const HOME = process.env.HOME || '/root'
const DSH_HOME = process.env.DSH_HOME || join(HOME, '.dsh')
const API = process.env.CTXC_API || 'http://127.0.0.1:11436/v1/chat/completions'
const MODEL = process.env.CTXC_MODEL || 'qwen2.5:1.5b-instruct'
const CARD_DIR = process.env.CTXC_CARD_DIR || join(DSH_HOME, 'ctxc-cards')
const LAZ = join(DSH_HOME, 'skills/lazarus/scripts')
const SESS_ROOT = join(DSH_HOME, 'sessions')
const MAX_LOCAL = parseInt(process.env.CTXC_MAX_LOCAL || '2600', 10)
const CHUNK = parseInt(process.env.CTXC_CHUNK || '380', 10)
const MAX_TOKENS = parseInt(process.env.CTXC_MAX_TOKENS || '45', 10)
const COOLDOWN_MS = 120_000
const MAX_LOG_BYTES = 20 * 1024 * 1024

const SYSTEM = '你是上下文压缩器。把输入压缩成中文要点，每点不超过20字；保留数字、名称、结论，去掉客套与重复。只输出要点，不要解释。'
const STATE = join(CARD_DIR, '.state.json')

function loadState() {
  try { return JSON.parse(readFileSync(STATE, 'utf-8')) } catch { return {} }
}
function saveState(s) {
  mkdirSync(dirname(STATE), { recursive: true })
  writeFileSync(STATE, JSON.stringify(s))
}

async function compressLocal(text, signal) {
  const chunks = []
  for (let i = 0; i < text.length; i += CHUNK) chunks.push(text.slice(i, i + CHUNK))
  const outs = []
  for (const c of chunks) {
    if (signal && signal.aborted) throw new Error('aborted')
    const res = await fetch(API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: MODEL,
        messages: [
          { role: 'system', content: SYSTEM },
          { role: 'user', content: c },
        ],
        max_tokens: MAX_TOKENS,
        stream: false,
      }),
      signal,
    })
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const j = await res.json()
    const out = ((j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content) || '').trim()
    if (out) outs.push(out)
  }
  if (!outs.length) throw new Error('empty')
  return outs.join('\n')
}

function clean(s) {
  let t = String(s || '').replace(/\s+/g, ' ').trim()
  for (const bad of ['[Plugin context', 'Spine extract', '这是旧内容摘录']) {
    if (t.startsWith(bad)) return ''
  }
  return t
}

function findLog(sessionId) {
  if (!sessionId) return null
  let dirs = []
  try { dirs = readdirSync(SESS_ROOT) } catch { return null }
  for (const ws of dirs) {
    const p = join(SESS_ROOT, ws, sessionId, 'session.v4.jsonl.zstd')
    if (existsSync(p)) return p
  }
  return null
}

function rollCard(cardPath, header, entry, cap = 5) {
  mkdirSync(dirname(cardPath), { recursive: true })
  let body = ''
  try { body = readFileSync(cardPath, 'utf-8') } catch {}
  const m = body.match(/(^\d+\. .*$\n?)+/m)
  const oldEntries = m ? m[0].split('\n').filter(Boolean).map(x => x.replace(/^\d+\. /, '')) : []
  if (oldEntries.length && oldEntries[oldEntries.length - 1] === entry) return false
  const kept = oldEntries.slice(-(cap - 1))
  const entries = kept.concat([entry])
  const out = header + '\n\n' + entries.map((x, i) => (i + 1) + '. ' + x).join('\n') + '\n'
  writeFileSync(cardPath, out)
  return true
}

function extractLastPair(talk) {
  const lines = talk.split('\n')
  const turns = []
  let cur = null
  for (const line of lines) {
    if (line.startsWith('**他**') || line.startsWith('**我**')) {
      if (cur) turns.push(cur)
      const who = line.startsWith('**他**') ? 'ta' : 'me'
      cur = [who, line.includes('：') ? line.split('：').slice(1).join('：').trim() : '']
    } else if (cur && line.trim() && !line.startsWith('### ')) {
      cur[1] += '\n' + line
    }
  }
  if (cur) turns.push(cur)
  for (let i = turns.length - 1; i >= 0; i--) {
    if (turns[i][0] === 'ta') {
      const ta = clean(turns[i][1])
      if (!ta) continue
      let me = ''
      for (let j = i + 1; j < Math.min(i + 6, turns.length); j++) {
        if (turns[j][0] === 'me') {
          const m = clean(turns[j][1])
          if (m && m !== '（无正文）' && !m.startsWith('（无正文）')) { me = m; break }
        }
      }
      if (me) return [ta, me]
    }
  }
  return null
}

function talkFile(sessionId) {
  const short = String(sessionId).slice(0, 13)
  return new Promise((resolve) => {
    execFile('node', [join(LAZ, 'rescue.mjs'), 'talk', short, '/tmp/ctxc-talk-' + short + '.md'], { cwd: LAZ, timeout: 240_000, maxBuffer: 4 * 1024 * 1024 }, (err) => {
      if (err) return resolve(null)
      try { resolve(readFileSync('/tmp/ctxc-talk-' + short + '.md', 'utf-8')) } catch { resolve(null) }
    })
  })
}

let busy = false
async function autoCompress(sessionId) {
  if (busy) return
  busy = true
  try {
    const log = findLog(sessionId)
    if (!log) return
    const st = statSync(log)
    if (st.size > MAX_LOG_BYTES) return
    const key = String(sessionId).slice(0, 13)
    const state = loadState()
    const prev = state[key] || {}
    if (prev.size === st.size && prev.mtime === st.mtimeMs && Date.now() - (prev.at || 0) < COOLDOWN_MS) return
    const talk = await talkFile(sessionId)
    if (!talk) return
    const pair = extractLastPair(talk)
    if (!pair) return
    const [ta, me] = pair
    const taS = ta.slice(0, 100) + (ta.length > 100 ? '…' : '')
    const meS = me.slice(0, 80) + (me.length > 80 ? '…' : '')
    const day = new Date().toISOString().slice(0, 10)
    const entry = day + ' | ta：「' + taS + '」→ 我：「' + meS + '」'
    rollCard(join(CARD_DIR, key + '.md'), '# 会话卡 · ' + key + '\n\n> 每轮对话后自动滚动（dsh-ctxc）。', entry)
    state[key] = { size: st.size, mtime: st.mtimeMs, at: Date.now() }
    saveState(state)
  } catch { /* 静默 */ } finally {
    busy = false
  }
}

export function apply(ctx) {
  ctx.inject(['dshGo'], (ctx) => {
    ctx.dshGo.on('compress', (scope) => {
      const text = (scope.clipboard || '').trim()
      if (!text) return { toast: '剪贴板里没有文字' }

      if (text.length > MAX_LOCAL) {
        const body = text.slice(0, 1900)
        const note = text.length > body.length
          ? '\n\n（原文共 ' + text.length + ' 字，输入框放不下，已截断至 ' + body.length + ' 字；全文压缩请用 ctxc.py 或分次压缩）'
          : ''
        return { insert: '帮我压缩下面这段，输出三点要点，每点不超过20字：\n\n' + body + note }
      }

      return {
        pending: { label: '本地压缩中', timeoutMs: 60_000 },
        result: async (signal) => {
          try {
            const out = await compressLocal(text, signal)
            const head = out.length > 1800 ? out.slice(0, 1800) + '…' : out
            return { insert: '压缩要点：\n' + head }
          } catch (e) {
            if (signal && signal.aborted) return { toast: '压缩超时，可再点一次' }
            return { toast: '本地模型不可用，检查 Ollama 服务' }
          }
        },
      }
    })

    ctx.dshGo.turnNote('auto-compress', (scope) => {
      autoCompress(scope.sessionId)
    })
  })
}
