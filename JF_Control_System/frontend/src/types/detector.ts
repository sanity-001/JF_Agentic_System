export interface DetectorStatus {
  connected: boolean
  receiver_running: boolean
  chip_version?: string
  status?: string
  acquiring: boolean
}

export interface Temperatures {
  fpga?: number[]
  adc?: number[]
}

export interface DetectorParams {
  exptime: string
  frames: string
  period: string
  highvoltage: string
  powerchip: string
  timing: string
  fpath: string
  fname: string
  fwrite: string
  readoutspeed: string
  [key: string]: string
}

export interface AcquisitionProgress {
  acquiring: boolean
  percentage: number
}

export interface VisualData {
  baseline: number[][] | null
  result: number[][] | null
  vmin: number
  vmax: number
  shape: [number, number]
  // 4M additions
  is_4m?: boolean
  expand?: boolean
  failed_modules?: string[] | null
}

export interface StatusUpdate {
  type: 'status_update'
  data: {
    status: DetectorStatus
    temperatures: Temperatures
    params: DetectorParams
    progress: AcquisitionProgress
  }
}

export interface HistoryRecord {
  id: number
  timestamp: string
  params_json: string
  fpath?: string
  filename?: string
  frames?: number
  period?: string
  exptime?: string
  duration_ms: number
  status: 'success' | 'failed' | 'aborted'
  error_message?: string
  raw_paths?: string  // JSON-serialized array of raw file paths (4M: 8 files)
}

export type WsMessage =
  | StatusUpdate
  | { type: 'config_loaded'; data: Record<string, string> }
  | { type: 'acquisition_started'; data: { frames: string } }
  | { type: 'acquisition_stopped'; data: Record<string, never> }
  | { type: 'history_updated'; data: HistoryRecord }
  | { type: 'error'; data: { message: string } }
  | { type: 'data_processing'; data: Record<string, never> }
  | { type: 'data_update'; data: VisualData }
  | { type: 'data_warning'; data: { failed_modules: string[]; message: string } }
  | { type: 'pong' }
