<template>
  <n-card size="small" class="status-panel">
    <template #header>
      <span style="display:flex; align-items:center; gap:6px;">
        <n-icon :component="HardwareChipOutline" :size="20" color="#00d4ff" />
        <span style="color: #00d4ff; font-weight: bold;">探测器状态</span>
      </span>
    </template>
    <div class="status-grid">
      <div class="stat-item">
        <div class="stat-label">FPGA 温度</div>
        <div class="stat-value temp">
          <n-tooltip v-if="hasMultiModule(temps.fpga)" trigger="hover" placement="right">
            <template #trigger>
              <span>{{ tempAvg(temps.fpga) }}</span>
            </template>
            <div v-for="(t, i) in temps.fpga" :key="i">d{{ i }}: {{ t.toFixed(1) }}°C</div>
          </n-tooltip>
          <span v-else>{{ tempDisplay(temps.fpga) }}</span>
        </div>
      </div>
      <div class="stat-item">
        <div class="stat-label">ADC 温度</div>
        <div class="stat-value temp">
          <n-tooltip v-if="hasMultiModule(temps.adc)" trigger="hover" placement="right">
            <template #trigger>
              <span>{{ tempAvg(temps.adc) }}</span>
            </template>
            <div v-for="(t, i) in temps.adc" :key="i">d{{ i }}: {{ t.toFixed(1) }}°C</div>
          </n-tooltip>
          <span v-else>{{ tempDisplay(temps.adc) }}</span>
        </div>
      </div>
      <div class="stat-item">
        <div class="stat-label">高压偏置</div>
        <div class="stat-value hv">
          {{ hvDisplay(params.highvoltage) }}
        </div>
      </div>
      <div class="stat-item">
        <div class="stat-label">Power Chip</div>
        <div class="stat-value">
          {{ powerchipDisplay(params.powerchip) }}
        </div>
      </div>
      <div class="stat-item">
        <div class="stat-label">芯片版本</div>
        <div class="stat-value">
          {{ status.chip_version || '-' }}
        </div>
      </div>
      <div class="stat-item">
        <div class="stat-label">采集模式</div>
        <div class="stat-value">
          {{ timingDisplay(params.timing) }}
        </div>
      </div>
    </div>
  </n-card>
</template>

<script setup lang="ts">
import { NCard, NTooltip, NIcon } from 'naive-ui'
import { HardwareChipOutline } from '@vicons/ionicons5'
import type { Temperatures, DetectorStatus, DetectorParams } from '@/types/detector'

defineProps<{
  temps: Temperatures
  params: DetectorParams
  status: DetectorStatus
}>()

function hasMultiModule(arr?: number[]): boolean {
  return (arr?.length ?? 0) > 1
}

function tempAvg(arr?: number[]): string {
  if (!arr || arr.length === 0) return '- °C'
  const avg = arr.reduce((a, b) => a + b, 0) / arr.length
  return `${avg.toFixed(1)}°C (avg)`
}

function tempDisplay(arr?: number[]): string {
  if (!arr || arr.length === 0) return '- °C'
  return arr.map(t => t.toFixed(1) + '°C').join(' / ')
}

function hvDisplay(val: string): string {
  if (!val || val === '0') return '- V'
  return val + ' V'
}

function powerchipDisplay(val: string): string {
  const v = (val ?? '').toString().toLowerCase()
  if (v === '1' || v === 'true' || v === 'on') return 'ON'
  return 'OFF'
}

function timingDisplay(val: string): string {
  const v = (val ?? '').toString().toLowerCase()
  if (v.includes('auto')) return '连续'
  if (v.includes('trigger')) return '触发'
  return val || '-'
}
</script>

<style scoped>
.status-panel {
  background: rgba(255,255,255,0.06);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 14px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.06);
}
.status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.stat-item { background: rgba(255,255,255,0.03); padding: 10px; border-radius: 10px; }
.stat-label { color: #94A3B8; font-size: 12px; font-weight: 500; margin-bottom: 4px; }
.stat-value { color: #F8FAFC; font-size: 15px; font-weight: 600; }
.stat-value.temp { color: #ff9944; }
.stat-value.hv { color: #ff6666; }
</style>
