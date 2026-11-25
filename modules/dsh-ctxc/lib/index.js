import { execFile } from 'node:child_process'
import { readFileSync, writeFileSync, mkdirSync, statSync, readdirSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'

export const name = 'local-ctxc'

const API = 'http://127.0.0.1:11436/v1/chat/completions'
const MODEL = 'qwen2.5:1.5b-instruct'
const MAX_LOCAL = 2600
const CHUNK = 380
const MAX_TOKENS = 45
const LAZ = join(process.env.HOME || '/root', '.dsh/skills/lazarus/scripts')
const SESS_ROOT = join(process.env.HOME || '/root', '.dsh/sessions')
const CARD_DIR = '/root/workspace/记忆档案/连续性/会话卡'
const MAIN_CARD = '/root/workspace/记忆档案/连续性/本线主卡.md'
const STATE = join(CARD_DIR, '.state.json')
const COOLDOWN_MS = 120_000
const MAX_LOG_BYTES = 20 * 1024 * 1024

const SYSTEM = '你是上下文压缩器。把输入压缩成中文要点，每点不超过20字；保留数字、名称、结论，去掉客套与重复。只输出要点，不要解释。'

function loadState() {
  try { return JSON.parse(readFileSync(STATE, 'utf-8')) } catch { return {} }
}
function saveState(s) {
  mkdirSync(dirname(STATE), { recursive: true })
  writeFileSync(STATE, JSON.stringify(s))
}

async function compressChunk(c, signal, prev) {
  const sys = prev ? SYSTEM + '\n上段要点（供衔接，不要重复）：' + prev : SYSTEM
  const res = await fetch(API, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: MODEL,
      messages: [
        { role: 'system', content: sys },
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
  return out
}

async function compressLocal(text, signal) {
  const chunks = []
  for (let i = 0; i < text.length; i += CHUNK) chunks.push(text.slice(i, i + CHUNK))
  const outs = []
  // 2 路并发，上一批的末条要点作为下一批的衔接上下文
  let prev = ''
  for (let i = 0; i < chunks.length; i += 2) {
    if (signal && signal.aborted) throw new Error('aborted')
    const batch = chunks.slice(i, i + 2)
    const results = await Promise.all(batch.map((c) => compressChunk(c, signal, prev).catch(() => '')))
    for (const r of results) { if (r) outs.push(r) }
    prev = outs[outs.length - 1] || prev
  }
  if (!outs.length) throw new Error('empty')
  return outs.join('\n')
}

// 质量自检：抽取原文关键数字/英文专名，检查压缩结果是否保留
function qualityCheck(src, out) {
  // 只查信息量大的 token：英文/工具专名（≥5 字符）+ 百分比。日期与普通数字压缩本就会丢，不误报。
  const names = [...new Set((src.match(/[A-Za-z][A-Za-z0-9_.-]{4,}/g) || []))].slice(0, 6)
  const pct = [...new Set((src.match(/\d+(?:\.\d+)?%/g) || []))].slice(0, 4)
  const tokens = names.concat(pct)
  if (!tokens.length) return { ok: true, missing: [] }
  const missing = tokens.filter((t) => !out.includes(t))
  return { ok: missing.length <= Math.ceil(tokens.length / 2), missing }
}

// 失败回退：原文摘录 + 明确标记未压缩
function fallbackExcerpt(text) {
  const flat = String(text || '').replace(/\s+/g, ' ').trim()
  return flat.slice(0, 600) + (flat.length > 600 ? '…' : '')
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
  for (const ws of readdirSync(SESS_ROOT)) {
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
    const header = '# 会话卡 · ' + key + '\n\n> 每轮对话后自动滚动（local-ctxc）。'
    rollCard(join(CARD_DIR, key + '.md'), header, entry)
    state[key] = { size: st.size, mtime: st.mtimeMs, at: Date.now() }
    saveState(state)
  } catch { /* 静默：压缩失败不影响对话 */ } finally {
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
          ? '\n\n（原文共 ' + text.length + ' 字，输入框放不下，已截断至 ' + body.length + ' 字；全文压缩用 ctxc.py）'
          : ''
        return { insert: '帮我压缩下面这段，输出三点要点，每点不超过20字：\n\n' + body + note }
      }

      return {
        pending: { label: '本地压缩中', timeoutMs: 60_000 },
        result: async (signal) => {
          try {
            const out = await compressLocal(text, signal)
            const head = out.length > 1800 ? out.slice(0, 1800) + '…' : out
            const q = qualityCheck(text, out)
            const warn = q.ok ? '' : '\n\n⚠ 可能丢要点：' + q.missing.join('、')
            return { insert: '压缩要点：\n' + head + warn }
          } catch (e) {
            if (signal && signal.aborted) return { toast: '压缩超时，可再点一次' }
            // 回退：不空手而归，给原文摘录并标明未压缩
            return { insert: '【本地压缩失败，以下为原文摘录（未压缩）】\n' + fallbackExcerpt(text) }
          }
        },
      }
    })

    ctx.dshGo.turnNote('auto-compress', (scope) => {
      // 每轮结束后后台压缩这轮对话，滚进会话卡；不阻塞回合。
      autoCompress(scope.sessionId)
    })
  })
}
