import { ref, reactive } from 'vue'
import { useWebSocket } from './useWebSocket'
import { api } from '@/api/client'
import type {
  DetectorStatus, Temperatures, DetectorParams,
  AcquisitionProgress, HistoryRecord, VisualData
} from '@/types/detector'

function parseDuration(val: string, name?: string): number {
  val = val.trim()
  if (val.endsWith('us')) return parseFloat(val) * 1e-6
  if (val.endsWith('ms')) return parseFloat(val) * 1e-3
  if (val.endsWith('ns')) return parseFloat(val) * 1e-9
  if (val.endsWith('s'))  return parseFloat(val)
  // 无后缀时根据参数名推断单位（_normalize_param 已将值转成纯数字）
  if (name === 'exptime') return parseFloat(val) * 1e-6
  if (name === 'period')  return parseFloat(val) * 1e-3
  return 0.001
}

export function useDetector() {
  const { connect: wsConnect, disconnect: wsDisconnect, onMessage } = useWebSocket()

  const hostname = ref('')
  const status = reactive<DetectorStatus>({ connected: false, receiver_running: false, acquiring: false })
  const temperatures = ref<Temperatures>({})
  const params = ref<DetectorParams>({
    exptime: '', frames: '', period: '', highvoltage: '0',
    powerchip: '0', timing: '', fpath: '', fname: '', fwrite: '1',
    readoutspeed: ''
  })
  const progress = ref<AcquisitionProgress>({ acquiring: false, percentage: 0 })
  const history = ref<HistoryRecord[]>([])
  const error = ref<string | null>(null)
  const acqMode = ref<'baseline' | 'signal'>('signal')
  const visualData = ref<VisualData | null>(null)
  const hasBaseline = ref(false)
  const visualProcessing = ref(false)

  // 本地进度计时器
  let _progressTimer: ReturnType<typeof setInterval> | null = null
  let _progressStart = 0
  let _progressExpected = 10

  function _startLocalProgress() {
    const frames = parseInt(params.value.frames) || 0
    const period = parseDuration(params.value.period || '1ms', 'period')
    _progressExpected = frames * period || 10
    _progressStart = Date.now()
    if (_progressTimer) clearInterval(_progressTimer)
    _progressTimer = setInterval(() => {
      const elapsed = (Date.now() - _progressStart) / 1000
      const pct = Math.min(Math.floor(elapsed / _progressExpected * 100), 99)
      progress.value = { acquiring: true, percentage: pct }
    }, 100)
  }

  function _stopLocalProgress() {
    if (_progressTimer) {
      clearInterval(_progressTimer)
      _progressTimer = null
    }
    progress.value = { acquiring: false, percentage: 100 }
  }

  // 定时轮询参数和温度（弥补 WebSocket 不推送这些字段的问题）
  let _pollTimer: ReturnType<typeof setInterval> | null = null

  function _startPolling() {
    if (_pollTimer) return
    _pollTimer = setInterval(async () => {
      if (!status.connected) return
      try {
        // 状态（含 chip_version、receiver_running）
        const s = await api.getStatus()
        if (s) Object.assign(status, s)
        // 参数
        const p = await api.getParams()
        if (p && Object.keys(p).length > 0) {
          Object.assign(params.value, p)
        }
        // 温度
        const t = await api.getTemperatures()
        if (t) {
          temperatures.value = t
        }
      } catch { /* polling is best-effort */ }
    }, 2000)
  }

  function _stopPolling() {
    if (_pollTimer) {
      clearInterval(_pollTimer)
      _pollTimer = null
    }
  }

  // 监听 WebSocket 的新格式消息: {displacement, chiller, detector, timestamp}
  onMessage(async (msg) => {
    // 新后端格式：{displacement, chiller, detector, timestamp}
    if (msg.detector) {
      const det = msg.detector
      // 更新探测器状态（合并而非覆盖，保留 chip_version 等 WebSocket 不推送的字段）
      status.connected = det.connected ?? status.connected
      status.acquiring = det.acquiring ?? status.acquiring
      // 温湿度从消息中提取
      if (det.fpga_temp != null) {
        temperatures.value = { ...temperatures.value, fpga: [det.fpga_temp] }
      }
      if (det.adc_temp != null) {
        temperatures.value = { ...temperatures.value, adc: [det.adc_temp] }
      }
      // 采集完成 → 停止进度条 + 获取图像 + 刷新历史
      if (!det.acquiring && progress.value.acquiring) {
        _stopLocalProgress()
        try {
          const vd = await api.processVisual()
          if (vd) {
            visualData.value = vd as VisualData
            hasBaseline.value = vd.baseline !== null
          }
        } catch { /* best-effort */ }
        // 刷新历史记录
        fetchHistory().catch(() => {})
      }
      error.value = null
      return
    }

    // 兼容旧格式（保留原有 type-based 协议处理）
    if (msg.type === 'status_update') {
      const p = msg.data.progress
      if (p && !p.acquiring && progress.value.acquiring) {
        _stopLocalProgress()
      }
      Object.assign(status, msg.data.status)
      temperatures.value = msg.data.temperatures
      if (msg.data.params && Object.keys(msg.data.params).length > 0) {
        params.value = msg.data.params as DetectorParams
      }
      error.value = null
    } else if (msg.type === 'error') {
      error.value = msg.data.message
    } else if (msg.type === 'history_updated') {
      history.value.unshift(msg.data as HistoryRecord)
      if (history.value.length > 100) history.value.pop()
    } else if (msg.type === 'data_processing') {
      visualProcessing.value = true
    } else if (msg.type === 'data_update') {
      visualData.value = msg.data as VisualData
      hasBaseline.value = msg.data.baseline !== null
      visualProcessing.value = false
    } else if (msg.type === 'data_warning') {
      error.value = msg.data.message
    }
  })

  async function loadConfigFile(configPath: string) {
    await api.loadConfig(configPath)
    status.connected = true
    _startPolling()
    // 加载配置后单独获取参数和温度
    try {
      const p = await api.getParams()
      if (p && Object.keys(p).length > 0) {
        Object.assign(params.value, p)
      }
    } catch { /* best-effort */ }
    try {
      const t = await api.getTemperatures()
      if (t) temperatures.value = t
    } catch { /* best-effort */ }
    wsConnect()
    await fetchHistory()
  }

  async function disconnectDetector() {
    _stopPolling()
    wsDisconnect()
    await api.disconnect()
    status.connected = false
  }

  async function shutdownDetector() {
    _stopPolling()
    await api.shutdown()
    wsDisconnect()
    // 清空所有状态
    Object.assign(status, { connected: false, receiver_running: false, acquiring: false, chip_version: undefined, status: undefined })
    params.value = { exptime: '', frames: '', period: '', highvoltage: '0', powerchip: '0', timing: '', fpath: '', fname: '', fwrite: '1', readoutspeed: '' }
    temperatures.value = {}
    visualData.value = null
    hasBaseline.value = false
    acqMode.value = 'signal'
  }

  async function startReceiver(port: number = 1954) {
    await api.receiverStart(port)
    status.receiver_running = true
  }

  async function stopReceiver() {
    await api.receiverStop()
    status.receiver_running = false
  }

  async function setParam(name: string, value: string) {
    await api.setParam(name, value)
  }

  async function startAcquisition(mode: 'baseline' | 'signal' = 'signal') {
    acqMode.value = mode
    await api.setMode(mode)
    await api.acquireStart()
  }

  function startLocalProgress() {
    _startLocalProgress()
  }

  async function stopAcquisition() {
    await api.acquireStop()
    _stopLocalProgress()
  }

  async function clearBaseline() {
    visualData.value = null
    hasBaseline.value = false
  }

  async function toggleExpand(_expand: boolean) {
    // expand toggle — backend endpoint pending
  }

  async function fetchHistory(limit = 20, offset = 0) {
    history.value = await api.getHistory(limit, offset)
  }

  return {
    hostname, status, temperatures, params, progress, history, error,
    acqMode, visualData, hasBaseline, visualProcessing,
    loadConfigFile, disconnectDetector, shutdownDetector,
    startReceiver, stopReceiver,
    setParam,
    startAcquisition, startLocalProgress, stopAcquisition,
    clearBaseline,
    toggleExpand,
    fetchHistory,
  }
}
