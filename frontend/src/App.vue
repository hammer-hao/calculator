<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

// When you deploy the backend, change this to your live URL.
const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:5000'

const a = ref('')
const b = ref('')
const op = ref('+')
const loading = ref(false)
const result = ref('')
const error = ref('')
const history = ref([])

const canCalc = computed(() => a.value !== '' && b.value !== '' && op.value)

async function doCalc() {
  error.value = ''
  result.value = ''
  if (!canCalc.value) {
    error.value = 'Please enter both numbers.'
    return
  }
  loading.value = true
  try {
    const { data } = await axios.post(`${API_BASE}/api/calc`, {
      a: a.value, op: op.value, b: b.value
    })
    if (data.ok) {
      result.value = data.result
      await loadHistory()
    } else {
      error.value = data.error || 'Unknown error'
    }
  } catch (e) {
    error.value = e?.response?.data?.error || e.message
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  try {
    const { data } = await axios.get(`${API_BASE}/api/history`)
    if (data.ok) history.value = data.items
  } catch {}
}

onMounted(loadHistory)
</script>

<template>
  <div class="min-h-screen flex items-center justify-center p-6 bg-gray-50">
    <div class="w-full max-w-md bg-white rounded-2xl shadow p-6 space-y-6">
      <h1 class="text-2xl font-semibold">Calculator (Flask API)</h1>

      <div class="space-y-3">
        <div class="grid grid-cols-3 gap-3">
          <input v-model="a" type="text" placeholder="A"
                 class="col-span-1 border rounded px-3 py-2" />
          <select v-model="op" class="col-span-1 border rounded px-3 py-2">
            <option value="+">+</option>
            <option value="-">−</option>
            <option value="*">×</option>
            <option value="/">÷</option>
            <option value="%">%</option>
          </select>
          <input v-model="b" type="text" placeholder="B"
                 class="col-span-1 border rounded px-3 py-2" />
        </div>

        <button @click="doCalc" :disabled="loading || !canCalc"
                class="w-full border rounded px-3 py-2 hover:bg-gray-100 disabled:opacity-50">
          {{ loading ? 'Calculating...' : 'Calculate (backend)' }}
        </button>

        <p v-if="result" class="text-green-700">Result: <strong>{{ result }}</strong></p>
        <p v-if="error" class="text-red-600">Error: {{ error }}</p>
      </div>

      <div>
        <h2 class="font-medium mb-2">History</h2>
        <div v-if="history.length === 0" class="text-sm text-gray-500">No history yet.</div>
        <ul v-else class="space-y-1 text-sm">
          <li v-for="(h, i) in history.slice().reverse()" :key="i">
            {{ h.ts }} — {{ h.a }} {{ h.op }} {{ h.b }} = <strong>{{ h.result }}</strong>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<style>
/* using simple utility-like classes; if you want Tailwind, you can add it, but not required for this test */
</style>
