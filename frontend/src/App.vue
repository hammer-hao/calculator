<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:5000'

// --- state ---
const expr = ref('')              // main line (current input/result)
const prevLine = ref('')          // aux line (previous evaluated expression with '=')
const result = ref('')            // last evaluation result (string)
const error = ref('')
const loading = ref(false)
const history = ref([])
const localExprHistory = ref([])
let localCursor = -1
let lastWasEval = false           // true right after a successful evaluation

// --- display ---
const displayPrev = computed(() => prevLine.value)                 // aux box
const displayMain = computed(() => expr.value || '0')              // main box
const canSubmit  = computed(() => !!expr.value.trim())

// --- helpers for multi-op editing ---
const OPS = "+-*/%"

function isOp(ch) { return OPS.includes(ch) }

function lastNonSpaceChar(s = expr.value) {
  for (let i = s.length - 1; i >= 0; i--) {
    const ch = s[i]
    if (ch !== ' ') return ch
  }
  return null
}

function isUnaryMinusPosition() {
  const ch = lastNonSpaceChar()
  return ch === null || ch === '(' || isOp(ch)
}

function unmatchedLeftParens(s = expr.value) {
  let bal = 0
  for (const ch of s) {
    if (ch === '(') bal++
    else if (ch === ')') bal = Math.max(0, bal - 1)
  }
  return bal
}

function pushLocalHistory(e) {
  if (!e) return
  if (localExprHistory.value[localExprHistory.value.length - 1] !== e) {
    localExprHistory.value.push(e)
  }
  localCursor = -1
}

// --- editing primitives (respecting Windows-like post-eval behavior) ---
function beginNewIfLastWasEval() {
  // If the last action was "=", and the user starts entering a number, decimal, or '(',
  // we start a NEW expression (replace expr). For operators we continue from current expr.
  if (lastWasEval) {
    expr.value = ''  // start fresh
    lastWasEval = false
  }
}

function appendOp(op) {
  // If last was eval, and user hits an operator, continue from the result (expr already holds it)
  if (op === '-' && isUnaryMinusPosition()) { expr.value += '-'; lastWasEval = false; return }
  const trimmedEnd = expr.value.replace(/\s+$/, '')
  const last = lastNonSpaceChar(trimmedEnd)
  if (last && isOp(last)) {
    expr.value = trimmedEnd.slice(0, trimmedEnd.length - 1) + op + ' '
  } else {
    if (trimmedEnd && last !== '(') expr.value = trimmedEnd + ' '
    else expr.value = trimmedEnd
    expr.value += op + ' '
  }
  lastWasEval = false
}

function appendDigitOrDot(ch) {
  beginNewIfLastWasEval()
  const last = lastNonSpaceChar()
  if (last === ')') expr.value += ' '
  expr.value += ch
}

function appendLPar() {
  beginNewIfLastWasEval()
  const last = lastNonSpaceChar()
  if (last && last !== '(' && !isOp(last)) expr.value += ' * '  // implicit multiply
  expr.value += '('
}

function appendRPar() {
  if (unmatchedLeftParens() === 0) return
  const last = lastNonSpaceChar()
  if (last === null || last === '(' || isOp(last)) return
  expr.value += ')'
}

// --- keypad / key handling ---
function press(key) {
  error.value = ''

  if (key === 'C' || key === 'Escape') {
    expr.value = ''
    prevLine.value = ''
    result.value = ''
    lastWasEval = false
    return
  }
  if (key === '←' || key === 'Backspace') {
    if (lastWasEval) { // backspace after eval should start fresh
      expr.value = ''
      lastWasEval = false
    } else {
      expr.value = expr.value.slice(0, -1)
    }
    return
  }
  if (key === '=' || key === 'Enter') { doCalc(); return }
  if (key === '(') { appendLPar(); return }
  if (key === ')') { appendRPar(); return }

  if (isOp(key)) { appendOp(key); return }

  // digits / dot
  if ((key >= '0' && key <= '9') || key === '.') {
    appendDigitOrDot(key)
    return
  }
}

// --- server I/O ---
async function loadServerHistory() {
  try {
    const { data } = await axios.get(`${API_BASE}/api/history`)
    if (data.ok) history.value = data.items
  } catch {}
}

async function doCalc() {
  error.value = ''
  let e = expr.value.trim()
  if (!e) { error.value = 'Enter an expression'; return }

  const missing = unmatchedLeftParens(e)
  if (missing > 0) e += ')'.repeat(missing)

  loading.value = true
  try {
    const { data } = await axios.post(`${API_BASE}/api/eval`, { expr: e }, {
      headers: { 'Content-Type': 'application/json' }
    })
    if (data.ok) {
      // 1) Push evaluated expression to aux line (with '=')
      prevLine.value = e + ' ='
      // 2) Show ONLY the result in the main line (becomes the new starting value)
      result.value = data.result
      expr.value = data.result
      lastWasEval = true

      pushLocalHistory(e)
      await loadServerHistory()
    } else {
      error.value = data.error || 'Unknown error'
    }
  } catch (ex) {
    error.value = ex?.response?.data?.error || ex.message
  } finally {
    loading.value = false
  }
}

// --- global keyboard + history nav ---
function handleKeydown(ev) {
  if (ev.metaKey || ev.ctrlKey || ev.altKey) return
  const key = (ev.code === 'NumpadEnter') ? 'Enter' : ev.key

  // Up/Down -> local expression history (the expressions before '=')
  if (key === 'ArrowUp') {
    if (localExprHistory.value.length === 0) return
    if (localCursor === -1) localCursor = localExprHistory.value.length - 1
    else if (localCursor > 0) localCursor--
    expr.value = localExprHistory.value[localCursor]
    lastWasEval = false
    ev.preventDefault()
    return
  }
  if (key === 'ArrowDown') {
    if (localExprHistory.value.length === 0) return
    if (localCursor !== -1 && localCursor < localExprHistory.value.length - 1) {
      localCursor++
      expr.value = localExprHistory.value[localCursor]
    } else {
      localCursor = -1
      expr.value = ''
    }
    lastWasEval = false
    ev.preventDefault()
    return
  }

  const acceptable = '0123456789.+-*/%()'
  if (acceptable.includes(key) || key === 'Enter' || key === 'Backspace' || key === 'Escape') {
    press(key === 'Backspace' ? 'Backspace' : key)
    ev.preventDefault()
  }
}

// restore from server history (supports both /calc and /eval formats)
function restoreFromHistory(h) {
  if (h.op === '=') {
    prevLine.value = (h.a ? h.a + ' =' : '')
    expr.value = h.result || ''
    result.value = h.result || ''
    lastWasEval = true
  } else {
    prevLine.value = ''
    expr.value = `${h.a} ${h.op} ${h.b}`.trim()
    lastWasEval = false
  }
  error.value = ''
}

onMounted(() => {
  loadServerHistory()
  document.addEventListener('keydown', handleKeydown, { passive: false })
})
onBeforeUnmount(() => document.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <main class="container">
    <article class="calc-root">
      <header class="calc-header">
        <h1>Calculator</h1>
        <p class="secondary">Windows-like main/aux display • Backend eval</p>
      </header>

      <!-- Aux (previous) and Main display -->
      <section class="display">
        <div class="prev-line" v-if="displayPrev">{{ displayPrev }}</div>
        <div class="main-line">{{ displayMain }}</div>
        <div class="sub-line" v-if="loading">Calculating…</div>
      </section>

      <!-- Actions -->
      <div class="actions-row">
        <button :disabled="loading || !canSubmit" @click="doCalc">=</button>
        <button class="muted" @click="press('C')">Clear</button>
      </div>

      <p v-if="error" class="error">{{ error }}</p>

      <!-- Keypad -->
      <section class="grid keypad" aria-label="Calculator keypad">
        <button type="button" @click="press('(')">(</button>
        <button type="button" @click="press(')')">)</button>
        <button type="button" class="muted" @click="press('C')">C</button>
        <button type="button" class="muted" @click="press('Backspace')">←</button>

        <button type="button" @click="press('7')">7</button>
        <button type="button" @click="press('8')">8</button>
        <button type="button" @click="press('9')">9</button>
        <button type="button" class="op" @click="press('/')">÷</button>

        <button type="button" @click="press('4')">4</button>
        <button type="button" @click="press('5')">5</button>
        <button type="button" @click="press('6')">6</button>
        <button type="button" class="op" @click="press('*')">×</button>

        <button type="button" @click="press('1')">1</button>
        <button type="button" @click="press('2')">2</button>
        <button type="button" @click="press('3')">3</button>
        <button type="button" class="op" @click="press('-')">−</button>

        <button type="button" @click="press('0')">0</button>
        <button type="button" @click="press('.')">.</button>
        <button type="button" class="op" @click="press('%')">%</button>
        <button type="button" class="op" @click="press('+')">+</button>

        <button type="button" class="equals" @click="press('Enter')">=</button>
      </section>

      <!-- Full history (click to restore) -->
      <details class="history">
        <summary>History</summary>
        <ul v-if="history.length">
          <li v-for="(h, i) in history.slice().reverse()" :key="i">
            <button type="button" class="linklike" @click="restoreFromHistory(h)">
              <template v-if="h.op === '='">
                {{ h.a }} = <strong>{{ h.result }}</strong>
              </template>
              <template v-else>
                {{ h.a }} {{ h.op }} {{ h.b }} = <strong>{{ h.result }}</strong>
              </template>
            </button>
            <small class="secondary"> · {{ new Date(h.ts).toLocaleString() }}</small>
          </li>
        </ul>
        <p v-else class="secondary">No history yet.</p>
      </details>
    </article>
  </main>
</template>

<style>
/* Looks great with Pico.css linked in index.html */
.calc-root { max-width: 420px; margin: 3rem auto; }
.calc-header h1 { margin-bottom: .25rem; }

.display {
  background: var(--card-background-color, #f6f7f9);
  border-radius: .75rem;
  padding: 1rem 1rem .75rem;
  box-shadow: var(--card-box-shadow, 0 1px 2px rgba(0,0,0,.05));
}
.prev-line {
  font-size: .95rem;
  color: var(--muted-color, #6b7280);
  text-align: right;
  white-space: nowrap;
  overflow-x: auto;
}
.main-line {
  font-size: 2rem;
  font-weight: 600;
  line-height: 1.2;
  text-align: right;
  white-space: nowrap;
  overflow-x: auto;
}
.sub-line {
  font-size: .9rem;
  color: var(--muted-color, #6b7280);
  text-align: right;
  margin-top: .25rem;
}

.actions-row {
  margin-top: .75rem;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: .5rem;
}

.keypad {
  margin-top: .75rem;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: .5rem;
}
.keypad button { height: 3rem; font-size: 1.05rem; }
.keypad .op { font-weight: 600; }
.keypad .muted { opacity: .85; }
.keypad .equals { grid-column: span 4; font-weight: 700; }

.history { margin-top: 1rem; }
.error { color: var(--del-color, #b42318); margin-top: .5rem; }

.linklike {
  background: none; border: none; padding: 0;
  font: inherit; color: var(--primary, #0ea5e9); cursor: pointer;
}
</style>
