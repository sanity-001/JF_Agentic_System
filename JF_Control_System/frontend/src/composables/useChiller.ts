import { ref, reactive } from 'vue'
import * as api from '../api/chiller'

export function useChiller() {
  const connected = ref(false)
  const temperature = ref<number | null>(null)
  const flowRate = ref<number | null>(null)
  const running = ref(false)
  const tempSetpoint = ref(20.0)
  const tempHistory = ref<{ time: string; value: number }[]>([])
  const indicators = reactive<Record<string, boolean>>({
    power: false, pump: false, cool: false, run: false,
    level_alarm: false, temp_alarm: false, flow_alarm: false, out: false,
  })

  let pollTimer: ReturnType<typeof setInterval> | null = null

  async function pollStatus() {
    try {
      const s = await api.getStatus()
      if (s && s.connection === 'connected') {
        connected.value = true
        // Temperature may be in centi-degrees (×100) from Modbus
        if (s.temperature !== undefined && s.temperature !== null) {
          temperature.value = Math.abs(s.temperature) > 200 ? s.temperature / 100 : s.temperature
        }
        if (s.flow_rate !== undefined && s.flow_rate !== null) {
          // Flow rate from Modbus is in centi-units (×100), always divide
          flowRate.value = s.flow_rate / 100
        }
        if (s.indicators) Object.assign(indicators, s.indicators)
        running.value = indicators.run
        // Update history
        if (temperature.value !== null) {
          const now = new Date().toLocaleTimeString()
          tempHistory.value.push({ time: now, value: temperature.value })
          if (tempHistory.value.length > 600) tempHistory.value.shift()
        }
      } else {
        connected.value = false
      }
    } catch { /* ignore */ }
  }

  function startPolling() {
    if (pollTimer) return
    pollStatus()
    pollTimer = setInterval(pollStatus, 1000)
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  }

  async function setSP(value: number) {
    await api.setSetpoint(value)
    tempSetpoint.value = value
  }

  // Start polling immediately
  startPolling()

  return {
    connected, temperature, flowRate, running, tempSetpoint, tempHistory, indicators,
    pollStatus, startPolling, stopPolling, setSP,
  }
}
