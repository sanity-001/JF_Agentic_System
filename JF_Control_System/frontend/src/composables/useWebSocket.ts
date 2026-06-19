import { ref, reactive } from 'vue'

export interface WsDisplacement {
  connected: boolean
  position: number
  drive_state: string
  scan_running: boolean
  scan_current: number
  scan_total: number
}

export interface WsChiller {
  connected: boolean
  temperature: number | null
  flow_rate: number | null
  indicators: Record<string, boolean>
}

export interface WsDetector {
  connected: boolean
  fpga_temp: number | null
  adc_temp: number | null
  hv: number | null
  acquiring: boolean
  frames_done: number
}

export function useWebSocket() {
  const wsConnected = ref(false)
  const displacement = reactive<WsDisplacement>({
    connected: false, position: 0, drive_state: '',
    scan_running: false, scan_current: 0, scan_total: 0,
  })
  const chiller = reactive<WsChiller>({
    connected: false, temperature: null, flow_rate: null, indicators: {},
  })
  const detector = reactive<WsDetector>({
    connected: false, fpga_temp: null, adc_temp: null,
    hv: null, acquiring: false, frames_done: 0,
  })

  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let reconnectDelay = 1000
  let handlers: Array<(data: any) => void> = []

  function onMessage(handler: (data: any) => void) {
    handlers.push(handler)
    return () => {
      handlers = handlers.filter(h => h !== handler)
    }
  }

  function connect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return
    }
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${proto}//${location.host}/ws`)

    ws.onopen = () => {
      wsConnected.value = true
      reconnectDelay = 1000
    }

    ws.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data)
        // Update unified status
        if (d.displacement) Object.assign(displacement, d.displacement)
        if (d.chiller) Object.assign(chiller, d.chiller)
        if (d.detector) Object.assign(detector, d.detector)
        // Forward raw data to registered handlers (backward compat with useDetector)
        for (const h of handlers) h(d)
      } catch { /* ignore parse errors */ }
    }

    ws.onclose = () => {
      wsConnected.value = false
      scheduleReconnect()
    }

    ws.onerror = () => {
      ws?.close()
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = setTimeout(() => {
      reconnectDelay = Math.min(reconnectDelay * 2, 30000)
      connect()
    }, reconnectDelay)
  }

  function disconnect() {
    if (reconnectTimer) clearTimeout(reconnectTimer)
    ws?.close()
  }

  connect()

  return { wsConnected, displacement, chiller, detector, connect, disconnect, onMessage }
}
