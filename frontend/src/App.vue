Here’s an updated, self-contained file that always shows History: it stays to the **right** on wide screens and moves **below** the calculator on narrow screens. I also removed the “Show History” button and any related state.

```vue
<script setup>
import { ref, computed, watchEffect, nextTick, onMounted, onBeforeUnmount } from 'vue'
import axios from 'axios'

/* Config */
const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:5000'

/* Per-user client id */
function getClientId() {
  const KEY = 'calc-client-id'
  let id = localStorage.getItem(KEY)
  if (!id) {
    id = (crypto.randomUUID && crypto.randomUUID()) || Math.random().toString(36).slice(2) + Date.now()
    localStorage.setItem(KEY, id)
  }
  return id
}
const CLIENT_ID = getClientId()

/* Axios */
const api = axios.create({ baseURL: API_BASE })
api.defaults.headers.common['X-Client-Id'] = CLIENT_ID
api.defaults.headers.post['Content-Type'] = 'application/json'

/* State */
const expr = ref('')
const prevLine = ref('')
const prevLineText = computed(() => (prevLine.value ? prevLine.value : '\xa0')) // NBSP when empty
const loading = ref(false)
const history = ref([])
const localExprHistory = ref([])
let localCursor = -1
let lastWasEval = false

/* UI */
const activeTab = ref('history')
const displayMain = computed(() => expr.value || '0')

/* Autoshrink */
const mainLineEl = ref(null)
const defaultFontSize = 48
const minFontSize = 16
const fontSize = ref(defaultFontSize)
let measureEl = null
let ro = null

const historyView = computed(() => history.value.slice().reverse())

function prettyResult(val) {
  if (val == null) return ''
  const num = Number(val)
  if (!Number.isFinite(num)) {
    const s = String(val)
    return s.length > 14 ? s.slice(0, 14) + '…' : s
  }
  const s = num.toString()
  if (s.length <= 14) return s
  // 12 significant digits, trim trailing zeros before 'e'
  return num.toExponential(5).replace(/(\.\d*?[1-9])0+(e)/, '$1$2').replace(/\.0+e/, 'e')
}

function adjustFontSize() {
  const el = mainLineEl.value
  if (!el) return
  const avail = el.clientWidth
  if (avail <= 0) return

  if (!measureEl) {
    measureEl = document.createElement('span')
    Object.assign(measureEl.style, {
      position: 'absolute',
      visibility: 'hidden',
      whiteSpace: 'nowrap',
      left: '-99999px',
      top: '0'
    })
    document.body.appendChild(measureEl)
  }

  const cs = getComputedStyle(el)
  Object.assign(measureEl.style, {
    fontFamily: cs.fontFamily,
    fontWeight: cs.fontWeight,
    letterSpacing: cs.letterSpacing,
    wordSpacing: cs.wordSpacing,
    textTransform: cs.textTransform
  })

  const text = (expr.value && expr.value.trim()) ? expr.value : '0'
  measureEl.style.fontSize = defaultFontSize + 'px'
  measureEl.textContent = text
  // force layout
  // eslint-disable-next-line no-unused-expressions
  measureEl.offsetWidth

  const wDefault = measureEl.offsetWidth || 1
  let ideal = defaultFontSize * (avail / wDefault)
  ideal = Math.max(minFontSize, Math.min(defaultFontSize, ideal))
  const rounded = Math.round(ideal * 4) / 4
  fontSize.value = rounded

  // If we’re at min and still overflowing, push scroll to end
  measureEl.style.fontSize = rounded + 'px'
  // eslint-disable-next-line no-unused-expressions
  measureEl.offsetWidth
  if (measureEl.offsetWidth > avail && rounded <= minFontSize) {
    el.scrollLeft = el.scrollWidth
  }
}
watchEffect(() => { expr.value; nextTick(adjustFontSize) })
function onResize() { requestAnimationFrame(adjustFontSize) }

/* Toasts */
const MAX_CHARS = 30
const showToast = ref(false)
const toastMsg = ref('')
const toastKind = ref('info')  // 'info' | 'warn' | 'error'
let toastTimer
function notify(msg, kind = 'info', duration = null) {
  toastKind.value = kind
  toastMsg.value = msg
  showToast.value = true
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (showToast.value = false),
    duration ?? (kind === 'error' ? 2600 : 1500)
  )
}
const notifyError = (msg) => notify(msg, 'error')
function exprCountNonSpace() { return expr.value.replace(/\s+/g, '').length }
function guardAppend(delta) {
  if (exprCountNonSpace() + delta > MAX_CHARS) { notify(`Max ${MAX_CHARS} characters`, 'warn'); return false }
  return true
}

/* Expression helpers */
const OPS = "+-*/%"
function isOp(ch) { return OPS.includes(ch) }
function lastNonSpaceChar(s = expr.value) {
  for (let i = s.length - 1; i >= 0; i--) { const ch = s[i]; if (ch !== ' ') return ch }
  return null
}
function isUnaryMinusPosition() { const ch = lastNonSpaceChar(); return ch === null || ch === '(' || isOp(ch) }
function unmatchedLeftParens(s = expr.value) {
  let bal = 0
  for (const ch of s) { if (ch === '(') bal++; else if (ch === ')') bal = Math.max(0, bal - 1) }
  return bal
}
function pushLocalHistory(e) {
  if (!e) return
  if (localExprHistory.value[localExprHistory.value.length - 1] !== e) localExprHistory.value.push(e)
  localCursor = -1
}

/* Editing (Windows-like) */
function beginNewIfLastWasEval() { if (lastWasEval) { expr.value = ''; lastWasEval = false } }
function appendOp(op) {
  if (op === '-' && isUnaryMinusPosition()) {
    if (!guardAppend(1)) return
    expr.value += '-'; lastWasEval = false; return
  }
  const trimmedEnd = expr.value.replace(/\s+$/, '')
  const last = lastNonSpaceChar(trimmedEnd)
  if (last && isOp(last)) { expr.value = trimmedEnd.slice(0, -1) + op + ' '; return }
  if (!guardAppend(1)) return
  expr.value = (trimmedEnd && last !== '(') ? trimmedEnd + ' ' : trimmedEnd
  expr.value += op + ' '
  lastWasEval = false
}
function appendDigitOrDot(ch) {
  beginNewIfLastWasEval()
  if (!guardAppend(1)) return
  if (lastNonSpaceChar() === ')') expr.value += ' '
  expr.value += ch
}
function appendLPar() {
  beginNewIfLastWasEval()
  const last = lastNonSpaceChar()
  const needsMul = last && last !== '(' && !isOp(last)
  const delta = 1 + (needsMul ? 1 : 0)
  if (!guardAppend(delta)) return
  if (needsMul) expr.value += ' * '
  expr.value += '('
}
function appendRPar() {
  if (unmatchedLeftParens() === 0) return
  const last = lastNonSpaceChar()
  if (last === null || last === '(' || isOp(last)) return
  if (!guardAppend(1)) return
  expr.value += ')'
}

/* Keypad / keyboard (scoped to app root) */
const rootEl = ref(null)
function press(key) {
  if (key === 'C' || key === 'Escape') { expr.value = ''; prevLine.value = ''; lastWasEval = false; return }
  if (key === '←' || key === 'Backspace') {
    if (lastWasEval){ expr.value=''; lastWasEval=false } else { expr.value = expr.value.slice(0,-1) }
    return
  }
  if (key === '=' || key === 'Enter') { doCalc(); return }
  if (key === '(') { appendLPar(); return }
  if (key === ')') { appendRPar(); return }
  if (isOp(key)) { appendOp(key); return }
  if ((key >= '0' && key <= '9') || key === '.') { appendDigitOrDot(key); return }
}
function handleKeydown(ev) {
  if (ev.metaKey || ev.ctrlKey || ev.altKey) return
  const target = ev.target
  const isTextField = target && (
    target.tagName === 'INPUT' ||
    target.tagName === 'TEXTAREA' ||
    target.isContentEditable
  )
  if (!rootEl.value || !rootEl.value.contains(target) || isTextField) return

  const key = (ev.code === 'NumpadEnter') ? 'Enter' : ev.key
  if (key === 'ArrowUp') {
    if (!localExprHistory.value.length) return
    if (localCursor === -1) localCursor = localExprHistory.value.length - 1
    else if (localCursor > 0) localCursor--
    expr.value = localExprHistory.value[localCursor]
    lastWasEval = false; ev.preventDefault(); return
  }
  if (key === 'ArrowDown') {
    if (!localExprHistory.value.length) return
    if (localCursor !== -1 && localCursor < localExprHistory.value.length - 1) { localCursor++; expr.value = localExprHistory.value[localCursor] }
    else { localCursor = -1; expr.value = '' }
    lastWasEval = false; ev.preventDefault(); return
  }
  const acceptable = '0123456789.+-*/%()'
  if (acceptable.includes(key) || key === 'Enter' || key === 'Backspace' || key === 'Escape') {
    press(key === 'Backspace' ? 'Backspace' : key)
    ev.preventDefault()
  }
}

/* History */
function fmtHistoryExpr(h) {
  const expr = h.op === '=' ? `${h.a} =` : `${h.a} ${h.op} ${h.b} =`
  const MAX = 10
  const plain = expr.replace(/\s+/g, ' ').trim()

  // robust slicing (handles emojis/surrogates)
  const first7 = Array.from(plain).slice(0, MAX).join('')
  return plain.length > MAX ? first7 + '…' : plain
}
async function loadServerHistory() {
  try {
    const { data } = await api.get('/api/history')
    if (data.ok) history.value = data.items
  } catch {}
}
function restoreFromHistory(h) {
  if (h.op === '=') { prevLine.value = (h.a ? h.a + ' =' : ''); expr.value = h.result || ''; lastWasEval = true }
  else { prevLine.value = ''; expr.value = `${h.a} ${h.op} ${h.b}`.trim(); lastWasEval = false }
}

/* Evaluate */
async function doCalc() {
  let e = expr.value.trim()
  if (!e) { notifyError('Enter an expression'); return }
  const missing = unmatchedLeftParens(e); if (missing > 0) e += ')'.repeat(missing)
  loading.value = true
  try {
    const { data } = await api.post('/api/eval', { expr: e })
    if (data.ok) {
      prevLine.value = e + ' ='
      expr.value = data.result
      lastWasEval = true
      pushLocalHistory(e)
      await loadServerHistory()
    } else {
      notifyError(data.error || 'Unknown error')
    }
  } catch (ex) {
    notifyError(ex?.response?.data?.error || ex.message)
  } finally {
    loading.value = false
  }
}

const historyPanelEl = ref(null)
let scrollHideTimer

function handleHistoryScroll() {
  const el = historyPanelEl.value
  if (!el) return
  el.classList.add('is-scrolling')
  clearTimeout(scrollHideTimer)
  scrollHideTimer = setTimeout(() => el.classList.remove('is-scrolling'), 700)
}

/* Mount / Unmount */
onMounted(() => {
  historyPanelEl.value?.addEventListener('scroll', handleHistoryScroll, { passive: true })
  document.documentElement.setAttribute('data-theme', 'dark')
  loadServerHistory()
  nextTick(adjustFontSize)

  // Scoped keyboard handling
  rootEl.value?.addEventListener('keydown', handleKeydown, { passive: false })
  rootEl.value?.focus()

  // Resize handling
  window.addEventListener('resize', onResize)
  ro = new ResizeObserver(() => requestAnimationFrame(adjustFontSize))
  if (mainLineEl.value) ro.observe(mainLineEl.value)
})
onBeforeUnmount(() => {
  historyPanelEl.value?.removeEventListener('scroll', handleHistoryScroll)
  rootEl.value?.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('resize', onResize)
  ro?.disconnect(); ro = null
  clearTimeout(toastTimer)
  if (measureEl?.parentNode) measureEl.parentNode.removeChild(measureEl)
})
</script>

<template>
  <main class="container" ref="rootEl" tabindex="0">
    <!-- Header -->
    <header class="app-header">
      <h1>Calculator</h1>
    </header>

    <div class="app-shell">
      <!-- LEFT: Calculator -->
      <article class="calc-root">
        <section class="display">
          <div class="prev-line">{{ prevLineText }}</div>
          <div class="main-line" ref="mainLineEl" :style="{ fontSize: fontSize + 'px' }">
            {{ displayMain }}
          </div>
          <div v-if="loading" class="spinner" role="status" aria-live="polite" aria-label="Calculating">
            <span class="sr-only">Calculating</span>
          </div>
        </section>

        <section class="grid keypad" aria-label="Calculator keypad">
          <button type="button" class="focus-ring" @click="press('(')">(</button>
          <button type="button" class="focus-ring" @click="press(')')">)</button>
          <button type="button" class="muted focus-ring" @click="press('C')">C</button>
          <button type="button" class="muted focus-ring" @click="press('Backspace')">←</button>

          <button type="button" class="focus-ring" @click="press('7')">7</button>
          <button type="button" class="focus-ring" @click="press('8')">8</button>
          <button type="button" class="focus-ring" @click="press('9')">9</button>
          <button type="button" class="op focus-ring" @click="press('/')">÷</button>

          <button type="button" class="focus-ring" @click="press('4')">4</button>
          <button type="button" class="focus-ring" @click="press('5')">5</button>
          <button type="button" class="focus-ring" @click="press('6')">6</button>
          <button type="button" class="op focus-ring" @click="press('*')">×</button>

          <button type="button" class="focus-ring" @click="press('1')">1</button>
          <button type="button" class="focus-ring" @click="press('2')">2</button>
          <button type="button" class="focus-ring" @click="press('3')">3</button>
          <button type="button" class="op focus-ring" @click="press('-')">−</button>

          <button type="button" class="focus-ring" @click="press('0')">0</button>
          <button type="button" class="focus-ring" @click="press('.')">.</button>
          <button type="button" class="op focus-ring" @click="press('%')">%</button>
          <button type="button" class="op focus-ring" @click="press('+')">+</button>

          <button type="button" class="equals focus-ring" @click="press('Enter')">=</button>
        </section>
      </article>

      <!-- RIGHT or BELOW: Sidebar (always visible) -->
      <aside class="sidebar" aria-label="Sidebar">
        <nav class="side-tabs">
          <button class="side-tab focus-ring" :class="{ active: activeTab==='history' }" @click="activeTab='history'">
            History
          </button>
        </nav>

        <section v-show="activeTab==='history'" class="tab-panel" ref="historyPanelEl">
          <div v-if="!history.length" class="secondary">No history yet.</div>
          <ul v-else class="history-list">
            <li v-for="(h, i) in history.slice().reverse()" :key="i">
              <button
                type="button"
                class="history-item focus-ring"
                @click="restoreFromHistory(h)"
                :title="`${fmtHistoryExpr(h)} ${h.result}`"
              >
                <span class="expr">{{ fmtHistoryExpr(h) }}</span>
                <span class="res">{{ prettyResult(h.result) }}</span>
              </button>
            </li>
          </ul>
        </section>
      </aside>
    </div>

    <!-- Toast -->
    <div
      class="toast"
      :class="[{ show: showToast }, toastKind]"
      :role="toastKind === 'error' ? 'alert' : 'status'"
      aria-live="polite"
    >
      {{ toastMsg }}
    </div>
  </main>
</template>

<style>
:root{
  /* Size/layout */
  --calc-fixed-w: 400px;
  --calc-fixed-h: 580px;
  --app-vpad: clamp(8px, 2dvh, 16px);
  --calc-max-h: calc(100dvh - (var(--app-vpad) * 2));
  --key-size: 56px;
  --gap: 0.45rem;
  --display-pad: 0.75rem;
  --display-height: 4.6rem;
  --display-prev-height: 1.2rem;
  --sidebar-min: 260px;
  --sidebar-max: 320px;
  --hist-item-h: 56px;

  /* Dark + cyan theme */
  --bg: #0b1220;
  --fg: #e6faff;
  --muted: #9fb3c8;
  --border: rgba(148,163,184,.18);
  --card: #0f172a;
  --card-elev: 0 1px 2px rgba(2,12,27,.55);
  --primary: #06b6d4;
  --primary-2: #22d3ee;
  --ring: rgba(34,211,238,.28);
  --key-bg: #0b1a2b;
  --key-hover: #0e2238;
  --op-bg: #0c1f33;
  --op-fg: #a5f3fc;
  --equals-grad: linear-gradient(135deg, #06b6d4, #22d3ee);
  --link: #67e8f9;
  --spinner-track: rgba(148,163,184,.22);
  --spinner-accent: var(--primary);
  --toast-bg: rgba(2,12,27,.92);
  --toast-error: rgba(220,38,38,.9);
  --toast-warn: rgba(234,179,8,.92);
}

/* Global */
html, body { background: var(--bg); color: var(--fg); }

/* Header */
.app-header{
  max-width: calc(var(--calc-fixed-w) + 1rem + var(--sidebar-max));
  margin: var(--app-vpad) auto .5rem;
  padding: 0 .5rem;
  display:flex;
  justify-content:center;
  align-items:center;
}
.app-header h1{ margin: 0; text-align: center; }

/* Shell: 2 columns on wide; stack on narrow */
.app-shell{
  display:grid;
  grid-template-columns: minmax(0, var(--calc-fixed-w)) minmax(var(--sidebar-min), var(--sidebar-max));
  gap:1rem;
  justify-content:center;
  align-items:start;
}
@media (max-width: 860px){
  .app-shell{ grid-template-columns: 1fr; }
  .calc-root{ transform: scale(0.92); transform-origin: top center; }
  .sidebar{ max-width: none; margin-top: .5rem; }
}
@media (max-width: 420px){
  .calc-root{ transform: scale(0.85); }
}

/* Calculator panel */
.calc-root{
  width: var(--calc-fixed-w);
  height: min(var(--calc-fixed-h), var(--calc-max-h));
  margin: 0 auto var(--app-vpad);
  background: var(--card);
  border-radius: .75rem;
  box-shadow: var(--card-elev);
  border: 1px solid var(--border);
  padding: 1rem;
  display:flex;
  flex-direction:column;
}

/* Display */
.display{
  border-radius:.6rem;
  padding: var(--display-pad);
  background: var(--card);
  box-shadow: var(--card-elev);
  border: 1px solid var(--border);
  position: relative;
}
.prev-line{
  height: var(--display-prev-height);
  display:flex; align-items:flex-end; justify-content:flex-end;
  white-space:nowrap; overflow-x:auto; overflow-y:hidden; scrollbar-width:none;
  color: var(--muted);
}
.prev-line::-webkit-scrollbar{ display:none; }
.main-line{
  font-weight:600;
  height: var(--display-height);
  display:flex; align-items:flex-end; justify-content:flex-end;
  white-space:nowrap; overflow-x:auto; overflow-y:hidden; scrollbar-width:none;
}
.main-line::-webkit-scrollbar{ display:none; }

/* Spinner */
.sr-only { position: absolute !important; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); border:0; }
.spinner {
  position: absolute; top:.5rem; right:.5rem;
  width:22px; height:22px; border-radius:50%;
  border:3px solid var(--spinner-track); border-top-color: var(--spinner-accent);
  animation: spin 0.8s linear infinite; filter: drop-shadow(0 1px 2px rgba(0,0,0,.15));
}
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce){ .spinner { animation: none; } }

/* Keypad (auto-fit vertically: 6 rows including = row) */
.keypad{
  margin-top: var(--gap);
  display:grid;
  grid-template-columns: repeat(4, 1fr);
  grid-template-rows: repeat(6, 1fr);
  gap: var(--gap);
  flex: 1 1 auto;
  align-content: stretch;
  min-height: 0;
}
.keypad button{
  height: 100%;
  min-height: 0;
  font-size: 1rem; color: var(--fg);
  background: var(--key-bg); border:1px solid var(--border);
  transition: background .15s ease, transform .02s ease;
}
.keypad button:hover{ background: var(--key-hover); }
.keypad button:active{ transform: translateY(1px); }
.keypad .op{ background: var(--op-bg); color: var(--op-fg); font-weight:600; }
.keypad .muted{ opacity:.9; }
.keypad .equals{
  grid-column: span 4; font-weight:700;
  background: var(--equals-grad); color:#001317; border:none;
}

/* Sidebar (always visible) */
.sidebar{
  width:100%;
  max-width: var(--sidebar-max);
  min-width: 0;
  align-self:start;
  background: var(--card); color: var(--fg);
  border-radius:.75rem; box-shadow: var(--card-elev); border:1px solid var(--border);
  padding:.75rem;
  overflow-x: hidden; /* never scroll sideways */
}
.side-tabs{ display:grid; grid-auto-flow:column; grid-auto-columns:1fr; margin-bottom:.5rem; gap:.25rem; }
.side-tab{
  display:inline-flex; justify-content:center; align-items:center; cursor:pointer;
  background:transparent; color: var(--fg);
  border:1px solid var(--border); border-radius:.5rem; padding:.45rem .6rem; font-size:.95rem; line-height:1;
}
.side-tab.active{
  border-color: var(--primary);
  background: rgba(34,211,238,.08);
  box-shadow: 0 0 0 2px var(--ring) inset;
}

/* History */
.tab-panel{ max-height:60vh; overflow:auto; scrollbar-gutter: stable;}

/* Firefox: keep width constant; hide by making it transparent */
.tab-panel { scrollbar-width: thin; scrollbar-color: transparent transparent; }
.tab-panel:hover,
.tab-panel.is-scrolling { scrollbar-color: rgba(34,211,238,.55) transparent; }

/* WebKit (Chrome/Edge/Safari): keep width constant; hide via transparency */
.tab-panel::-webkit-scrollbar { width: 10px; height: 10px; } /* constant */
.tab-panel::-webkit-scrollbar-track { background: transparent; }
.tab-panel::-webkit-scrollbar-thumb {
  background-color: transparent;         /* invisible by default */
  border-radius: 999px;
  border: 2px solid transparent;         /* inset look when visible */
  background-clip: padding-box;
}
.tab-panel:hover::-webkit-scrollbar-thumb,
.tab-panel.is-scrolling::-webkit-scrollbar-thumb {
  background-color: rgba(34,211,238,.38);
}
.tab-panel::-webkit-scrollbar-thumb:active {
  background-color: var(--primary);
}

.history-list{ list-style:none; padding:0; margin:0; display:grid; }
.history-item{
  display:grid;
  grid-template-columns: minmax(0, 1fr) minmax(8ch, 14ch); /* expr | result */
  align-items:center;
  column-gap: .75rem;
  width:100%;
  min-height: var(--hist-item-h);
  max-height: var(--hist-item-h);
  padding:.5rem .6rem; border:1px solid var(--border);
  margin: 0rem;
  border-radius:.6rem; background: var(--card); color: var(--fg);
  line-height:1.1
}
.history-item:hover{ background: #0d1a2a; }
.history-item .expr{
  font-size:.95rem;
  min-width: 0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
  justify-self: start; text-align:left;
}
.history-item .res{
  font-weight:700;
  min-width: 0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
  justify-self: end; text-align:right; font-variant-numeric: tabular-nums;
}

/* Toasts */
.toast{
  position:fixed; left:50%; bottom:1rem; transform: translateX(-50%) translateY(8px);
  background: var(--toast-bg); color:#fff; padding:.5rem .75rem; border-radius:.5rem;
  font-size:.9rem; line-height:1.2; box-shadow: 0 2px 10px rgba(0,0,0,.25);
  pointer-events:none; opacity:0; transition: opacity .18s ease, transform .18s ease; z-index:1000;
}
.toast.show{ opacity:1; transform: translateX(-50%) translateY(0); }
.toast.error{ background: var(--toast-error); }
.toast.warn { background: var(--toast-warn); color: #111827; }

/* Focus ring (consolidated) */
.focus-ring:focus-visible{ outline: none; box-shadow: 0 0 0 3px var(--ring); }

/* Small utilities */
.ghost{ background:transparent; border:1px solid var(--border); padding:.35rem .6rem; border-radius:.6rem; font-size:.9rem; }
</style>
```
