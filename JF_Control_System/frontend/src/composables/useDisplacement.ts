import { ref, reactive } from 'vue'
import * as api from '../api/displacement'

export function useDisplacement() {
  const connected = ref(false)
  const ports = ref<string[]>([])
  const position = ref(0)
  const rawStatus = ref<string[]>([])
  const servo = ref('')
  const originComplete = ref(false)
  const scanState = reactive({ running: false, current_step: 0, total_steps: 0 })

  // New parsed status fields
  const axisNo = ref(1)
  const driveState = ref('')
  const emgSignal = ref(false)
  const originSignal = ref(false)
  const limitSignal = ref(false)
  const softLimit = ref(false)
  const servoReady = ref(false)
  const servoOn = ref(false)

  let pollTimer: ReturnType<typeof setInterval> | null = null
  let portRefreshTimer: ReturnType<typeof setInterval> | null = null

  async function loadPorts() {
    ports.value = await api.listPorts()
  }

  async function connect(port: string, baudrate: number, axis: number = 1) {
    axisNo.value = axis
    const r = await api.connect(port, baudrate)
    if (r.success) {
      connected.value = true
      startPolling(axis)
      // Start auto-refreshing ports
      if (!portRefreshTimer) {
        portRefreshTimer = setInterval(() => loadPorts(), 3000)
      }
    }
    return r
  }

  async function disconnect() {
    stopPolling()
    // Stop port auto-refresh
    if (portRefreshTimer) {
      clearInterval(portRefreshTimer)
      portRefreshTimer = null
    }
    await api.disconnect()
    connected.value = false
    position.value = 0
    driveState.value = ''
    emgSignal.value = false
    originSignal.value = false
    limitSignal.value = false
    softLimit.value = false
    servoReady.value = false
    servoOn.value = false
  }

  async function pollStatus(axis: number = 1) {
    try {
      const s = await api.getStatus(axis)
      if (s && s.connected) {
        connected.value = true
        position.value = s.position || 0
        rawStatus.value = s.status || []
        servo.value = s.servo || ''
        originComplete.value = s.origin_complete || false
        if (s.scan) {
          scanState.running = s.scan.running
          scanState.current_step = s.scan.current_step
          scanState.total_steps = s.scan.total_steps
        }

        // Parse status dict from backend (read_status returns dict)
        const st = s.status
        if (st && typeof st === 'object' && !Array.isArray(st)) {
          driveState.value = st.drive_state_text || ''
          emgSignal.value = st.emg === '1' || st.emg_text === 'ON'
          // org_norg: 2 or 3 means ORG ON
          const onVal = parseInt(st.org_norg, 10)
          originSignal.value = onVal === 2 || onVal === 3
          // cw_ccw: 1 or 2 or 3 means at least one limit ON
          const cwVal = parseInt(st.cw_ccw, 10)
          limitSignal.value = cwVal === 1 || cwVal === 2 || cwVal === 3
          // soft_limit: 1 or 2 means soft limit tripped
          const slVal = parseInt(st.soft_limit, 10)
          softLimit.value = slVal === 1 || slVal === 2
        } else if (Array.isArray(st) && st.length > 0) {
          // Fallback: array of strings like ['停止中', 'EMG:OFF', ...]
          driveState.value = st[0] || ''
          emgSignal.value = st.some((item: string) => item.includes('EMG:ON'))
          originSignal.value = st.some((item: string) => item.includes('ORG:ON'))
          limitSignal.value = st.some((item: string) =>
            item.includes('LIMIT:ON') || item.includes('CW') || item.includes('CCW')
          )
          softLimit.value = st.some((item: string) => item.includes('SOFT'))
        }

        // Parse servo dict from backend (read_servo_status returns dict)
        const sv = s.servo
        if (sv && typeof sv === 'object' && !Array.isArray(sv)) {
          servoReady.value = sv.servo_ready === '1'
          servoOn.value = sv.servo_on === '1'
        } else if (typeof sv === 'string') {
          // Fallback: concatenated string
          servoReady.value = sv.includes('Ready:1') || sv.includes('Ready: ON')
          servoOn.value = sv.includes('ON:1') || sv.includes('ON: ON')
        }
      }
    } catch { /* ignore poll errors */ }
  }

  function startPolling(axis: number = 1) {
    if (pollTimer) return
    pollStatus(axis)
    pollTimer = setInterval(() => pollStatus(axis), 500)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  return {
    connected, ports, position, rawStatus, servo, originComplete, scanState,
    driveState, emgSignal, originSignal, limitSignal, softLimit, servoReady, servoOn, axisNo,
    loadPorts, connect, disconnect, pollStatus, startPolling, stopPolling,
  }
}
