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
  connect:         (hostname?: string, configPath?: string) =>
    request<any>(`/connect`, { method: 'POST', body: JSON.stringify({ hostname, config_path: configPath }) }),
  disconnect:      () =>
    request<any>(`/disconnect`, { method: 'POST' }),
  shutdown:        () =>
    request<any>(`/shutdown`, { method: 'POST' }),
  receiverStart:   (port: number = 1954) =>
    request<any>(`/receiver/start`, { method: 'POST', body: JSON.stringify({ port }) }),
  receiverStop:    () =>
    request<any>(`/receiver/stop`, { method: 'POST' }),
  browse:          (path: string) =>
    request<any>(`/detector/browse?path=${encodeURIComponent(path)}`),

  getStatus:       ()       => request<any>(`/status`),
  getTemperatures: ()       => request<any>(`/temperatures`),
  getParams:       ()       => request<any>(`/params`),
  setParam:        (name: string, value: string) =>
    request<any>(`/params`, { method: 'PUT', body: JSON.stringify({ name, value }) }),

  loadConfig:      (path: string) =>
    request<any>(`/detector/load_config`, { method: 'POST', body: JSON.stringify({ path }) }),
  saveConfig:      (path: string) =>
    request<any>(`/config/save`, { method: 'POST', body: JSON.stringify({ path }) }),

  acquireStart:    (mode: string = 'signal') =>
    request<any>(`/acquire/start`, { method: 'POST', body: JSON.stringify({ mode }) }),
  acquireStop:     () =>
    request<any>(`/acquire/stop`, { method: 'POST' }),
  clearBaseline:   () =>
    request<any>(`/baseline/clear`, { method: 'POST' }),

  visualExpand:    (expand: boolean) =>
    request<any>(`/visual/expand`, { method: 'POST', body: JSON.stringify({ expand }) }),

  getHistory:      (limit = 20, offset = 0) =>
    request<any[]>(`/detector/history?limit=${limit}&offset=${offset}`),
  getHistoryRecord: (id: number) =>
    request<any>(`/detector/history/${id}`),
}
