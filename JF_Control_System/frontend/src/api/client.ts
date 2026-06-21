const BASE = '/api'

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  // ── Detector connection ──
  connect:         (hostname: string, configParams?: Record<string, string>) =>
    request<any>(`/detector/connect`, {
      method: 'POST',
      body: JSON.stringify({ hostname, config_params: configParams || {} }),
    }),
  loadConfig:      (path: string) =>
    request<any>(`/detector/load_config`, {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),
  disconnect:      () =>
    request<any>(`/detector/disconnect`, { method: 'POST' }),
  shutdown:        () =>
    request<any>(`/detector/shutdown`, { method: 'POST' }),

  // ── Receiver ──
  receiverStart:   (port: number = 1954) =>
    request<any>(`/detector/receiver/start`, {
      method: 'POST',
      body: JSON.stringify({ port }),
    }),
  receiverStop:    () =>
    request<any>(`/detector/receiver/stop`, { method: 'POST' }),

  // ── File browse ──
  browse:          (path: string) =>
    request<any>(`/detector/browse?path=${encodeURIComponent(path)}`),

  // ── Status & params ──
  getStatus:       ()       => request<any>(`/detector/status`),
  getTemperatures: ()       => request<any>(`/detector/temperatures`),
  getParams:       ()       => request<any>(`/detector/params`),
  setParam:        (key: string, value: string) =>
    request<any>(`/detector/params`, {
      method: 'POST',
      body: JSON.stringify({ key, value }),
    }),

  // ── Acquisition ──
  setMode:         (mode: string) =>
    request<any>(`/detector/mode`, {
      method: 'POST',
      body: JSON.stringify({ mode }),
    }),
  acquireStart:    () =>
    request<any>(`/detector/acquire/start`, { method: 'POST' }),
  acquireStop:     () =>
    request<any>(`/detector/acquire/stop`, { method: 'POST' }),

  // ── History ──
  getHistory:      (limit = 20, offset = 0) =>
    request<any[]>(`/detector/history?limit=${limit}&offset=${offset}`),

  // ── Config file save ──
  saveConfig:      (path: string) =>
    request<any>(`/detector/save_config`, {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),
}
