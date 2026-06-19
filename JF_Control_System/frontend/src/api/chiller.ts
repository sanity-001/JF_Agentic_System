const BASE = '/api/chiller'

export async function listPorts(): Promise<string[]> {
  const res = await fetch(`${BASE}/ports`)
  const data = await res.json()
  return data.ports || []
}

export async function getStatus() {
  const res = await fetch(`${BASE}/status`)
  return res.json()
}

export async function getParams() {
  const res = await fetch(`${BASE}/params`)
  return res.json()
}

export async function connect(port: string, baudrate: number, slaveAddress: number = 1) {
  const res = await fetch(`${BASE}/connect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ port, baudrate, slave_address: slaveAddress }),
  })
  return res.json()
}

export async function getConfig() {
  const res = await fetch('/api/config')
  const data = await res.json()
  return data.chiller || {}
}

export async function disconnect() {
  const res = await fetch(`${BASE}/disconnect`, { method: 'POST' })
  return res.json()
}

export async function setSetpoint(value: number) {
  const res = await fetch(`${BASE}/setpoint`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value }),
  })
  return res.json()
}

export async function start() {
  const res = await fetch(`${BASE}/start`, { method: 'POST' })
  return res.json()
}

export async function stop() {
  const res = await fetch(`${BASE}/stop`, { method: 'POST' })
  return res.json()
}

export async function autotune() {
  const res = await fetch(`${BASE}/autotune`, { method: 'POST' })
  return res.json()
}

export async function mute() {
  const res = await fetch(`${BASE}/mute`, { method: 'POST' })
  return res.json()
}

export async function setPID(p: number, i: number, d: number) {
  const res = await fetch(`${BASE}/pid`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ p, i, d }),
  })
  return res.json()
}
