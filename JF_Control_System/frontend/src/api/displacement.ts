const BASE = '/api/displacement'

export async function listPorts(): Promise<string[]> {
  const res = await fetch(`${BASE}/ports`)
  const data = await res.json()
  return data.ports || []
}

export async function connect(port: string, baudrate: number) {
  const res = await fetch(`${BASE}/connect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ port, baudrate }),
  })
  return res.json()
}

export async function disconnect() {
  const res = await fetch(`${BASE}/disconnect`, { method: 'POST' })
  return res.json()
}

export async function getStatus(axis: number = 1) {
  const res = await fetch(`${BASE}/status/${axis}`)
  return res.json()
}

export async function moveAbsolute(axis: number, position: number, speedTable: number = 0) {
  const res = await fetch(`${BASE}/move/absolute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ axis, position, speed_table: speedTable }),
  })
  return res.json()
}

export async function moveRelative(axis: number, offset: number, speedTable: number = 0) {
  const res = await fetch(`${BASE}/move/relative`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ axis, offset, speed_table: speedTable }),
  })
  return res.json()
}

export async function stop(axis: number = 1) {
  const res = await fetch(`${BASE}/stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ axis, mode: 0 }),
  })
  return res.json()
}

export async function originReturn(axis: number = 1) {
  const res = await fetch(`${BASE}/origin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ axis }),
  })
  return res.json()
}

export async function startScan(axis: number, direction: number, stepSize: number,
  steps: number, speedTable: number, pauseMs: number) {
  const res = await fetch(`${BASE}/scan/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ axis, direction, step_size: stepSize, steps,
      speed_table: speedTable, pause_ms: pauseMs }),
  })
  return res.json()
}

export async function stopScan() {
  const res = await fetch(`${BASE}/scan/stop`, { method: 'POST' })
  return res.json()
}

export async function getScanState() {
  const res = await fetch(`${BASE}/scan/state`)
  return res.json()
}

export async function systemReset() {
  const res = await fetch(`${BASE}/reset`, { method: 'POST' })
  return res.json()
}

export async function emergencyRelease() {
  const res = await fetch(`${BASE}/emergency/release`, { method: 'POST' })
  return res.json()
}
