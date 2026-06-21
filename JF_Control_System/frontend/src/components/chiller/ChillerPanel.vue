<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { NCard, NButton, NInputNumber, NSpace, NModal, NSelect, NIcon, useMessage } from 'naive-ui'
import {
  ThermometerOutline, SettingsOutline, PlayOutline,
  StopOutline, VolumeMuteOutline
} from '@vicons/ionicons5'
import { useChiller } from '../../composables/useChiller'
import * as chillerApi from '../../api/chiller'
import * as echarts from 'echarts'

const {
  connected: chConnected, temperature, flowRate, tempSetpoint, tempHistory, indicators,
  setSP,
} = useChiller()

const chillerPorts = ref<string[]>([])
const chMessage = useMessage()

async function loadChillerPorts() {
  chillerPorts.value = await chillerApi.listPorts()
}

async function handleMute() {
  try {
    await chillerApi.mute()
    chMessage.success('水冷机已消音')
  } catch (e: any) {
    chMessage.error(`消音失败: ${e.message}`)
  }
}
const chartContainer = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null
let _chartResizeObserver: ResizeObserver | null = null

function resizeChart() {
  chart?.resize()
}

function initChart() {
  if (!chartContainer.value) return
  chart = echarts.init(chartContainer.value)
  chart.setOption({
    grid: { top: 8, right: 8, bottom: 20, left: 40 },
    dataZoom: [{ type: 'slider', show: false, start: 0, end: 100 }],
    xAxis: { type: 'category', data: [], show: true, axisLabel: { fontSize: 10, color: '#64748B', fontFamily: 'Fira Sans' } },
    yAxis: {
      type: 'value', show: true,
      axisLabel: { fontSize: 10, color: '#64748B', fontFamily: 'Fira Code' },
      splitLine: {
        lineStyle: {
          color: 'rgba(255,255,255,0.08)',
          type: 'dashed',
          width: 0.5,
        },
      },
    },
    series: [{
      data: [], type: 'line', smooth: true, showSymbol: false,
      lineStyle: { color: '#00d4ff', width: 1.5 },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(0,212,255,0.3)' },
          { offset: 1, color: 'rgba(0,212,255,0.02)' }
        ])
      },
    }],
  })
}

function updateChart() {
  if (!chart) return
  const xData = tempHistory.value.map(d => d.time)
  const yData = tempHistory.value.map(d => d.value)
  chart.setOption({
    xAxis: { data: xData },
    series: [{ data: yData }],
    dataZoom: [{ start: 0, end: 100 }],
  })
}

watch(() => tempHistory.value.length, () => {
  nextTick(updateChart)
})

onMounted(() => {
  nextTick(() => {
    initChart()
    updateChart()
    if (chartContainer.value) {
      _chartResizeObserver = new ResizeObserver(() => resizeChart())
      _chartResizeObserver.observe(chartContainer.value)
    }
  })
})

onUnmounted(() => {
  if (_chartResizeObserver) {
    _chartResizeObserver.disconnect()
    _chartResizeObserver = null
  }
  chart?.dispose()
})

const tempColor = computed(() => {
  if (!chConnected.value) return '#557799'
  const t = temperature.value ?? 0
  if (t > 40) return '#ff4757'
  if (t > 30) return '#ff9944'
  return '#00e676'
})

const tempDisplay = computed(() => {
  if (!chConnected.value) return '--'
  return temperature.value?.toFixed(1) ?? '--'
})

const indicatorList = [
  { key: 'power', label: '电源' },
  { key: 'pump', label: '泵' },
  { key: 'cool', label: '制冷' },
  { key: 'run', label: '运行' },
  { key: 'out', label: '控制输出' },
  { key: 'temp_alarm', label: '报警' },
  { key: 'flow_alarm', label: '流量报警' },
  { key: 'level_alarm', label: '液位报警' },
]

// Serial config modal
const showConfig = ref(false)
const configPort = ref('/dev/ttyUSB1')
const configBaudrate = ref(4800)
const configSlaveAddr = ref(1)
const configDataBits = ref(8)
const configParity = ref('None')
const configStopBits = ref(2)

const baudrateOptions = [1200, 2400, 4800, 9600, 19200, 38400].map(v => ({ label: String(v), value: v }))
const dataBitsOptions = [7, 8].map(v => ({ label: String(v), value: v }))
const parityOptions = ['None', 'Even', 'Odd'].map(v => ({ label: v, value: v }))
const stopBitsOptions = [1, 2].map(v => ({ label: String(v), value: v }))

async function saveAndReconnect() {
  await chillerApi.connect(configPort.value, configBaudrate.value, configSlaveAddr.value)
  showConfig.value = false
}
</script>

<template>
  <n-card size="small" class="chiller-panel">
    <template #header>
      <div class="panel-header">
        <span style="display:flex; align-items:center; gap:6px;">
          <n-icon :component="ThermometerOutline" :size="20" color="#00d4ff" />
          <span style="color: #00d4ff; font-weight: bold;">水冷机控制</span>
        </span>
      </div>
    </template>

    <template #header-extra>
      <n-space size="small" align="center">
        <n-button size="medium" @click="showConfig = true; loadChillerPorts()">
          <template #icon><n-icon :component="SettingsOutline" :size="14" /></template>
          串口配置
        </n-button>
        <span :style="{ color: chConnected ? tempColor : '#ff4757', fontSize: '12px' }">
          {{ chConnected ? '● ' + tempDisplay + '°C' : '○ 未连接' }}
        </span>
      </n-space>
    </template>

    <div class="chiller-body">
      <!-- Big temperature -->
      <div class="temp-display">
        <span class="temp-value" :style="{ color: tempColor }">{{ tempDisplay }}</span>
        <span class="temp-unit">°C</span>
      </div>

      <!-- Flow rate -->
      <div class="info-row">
        <span class="field-label">流量</span>
        <span class="value">{{ chConnected ? (flowRate ?? '--') + ' L/min' : '--' }}</span>
      </div>

      <!-- Indicator dots -->
      <div class="indicators">
        <span v-for="ind in indicatorList" :key="ind.key"
          class="indicator"
          :class="{ on: ind.key === 'power' ? chConnected : indicators[ind.key], alarm: ind.key.includes('alarm') && indicators[ind.key] }">
          <span class="indicator-dot"></span>
          {{ ind.label }}
        </span>
      </div>

      <!-- Controls -->
      <div class="section">
        <n-space vertical size="small">
          <n-space>
            <span class="field-label">设定温度:</span>
            <n-input-number v-model:value="tempSetpoint" size="small" style="width: 100px;" :step="0.1" />
            <n-button size="small" type="primary" @click="setSP(tempSetpoint)">设置</n-button>
          </n-space>
          <n-space>
            <n-button size="medium" type="primary" @click="chillerApi.start()">
              <template #icon><n-icon :component="PlayOutline" :size="16" /></template>
              启动
            </n-button>
            <n-button size="medium" type="error" @click="chillerApi.stop()">
              <template #icon><n-icon :component="StopOutline" :size="16" /></template>
              停止
            </n-button>
            <n-button size="medium" @click="handleMute">
              <template #icon><n-icon :component="VolumeMuteOutline" :size="14" /></template>
              消音
            </n-button>
          </n-space>
        </n-space>
      </div>

      <!-- Mini trend chart -->
      <div ref="chartContainer" class="mini-chart"></div>
    </div>


    <!-- Serial config modal -->
    <n-modal v-model:show="showConfig" title="串口配置" preset="dialog" positive-text="保存并重连" negative-text="取消" @positive-click="saveAndReconnect">
      <n-space vertical size="small" style="padding: 8px 0;">
        <n-space align="center" justify="space-between">
          <span class="field-label">端口:</span>
          <n-select v-model:value="configPort" :options="chillerPorts.map(p => ({ label: p, value: p }))"
            size="small" style="width: 180px;" placeholder="选择端口" />
        </n-space>
        <n-space align="center" justify="space-between">
          <span class="field-label">波特率:</span>
          <n-select v-model:value="configBaudrate" :options="baudrateOptions" size="small" style="width: 180px;" disabled />
        </n-space>
        <n-space align="center" justify="space-between">
          <span class="field-label">从机地址:</span>
          <n-input-number v-model:value="configSlaveAddr" size="small" :min="1" :max="128" style="width: 180px;" disabled />
        </n-space>
        <n-space align="center" justify="space-between">
          <span class="field-label">数据位:</span>
          <n-select v-model:value="configDataBits" :options="dataBitsOptions" size="small" style="width: 180px;" disabled />
        </n-space>
        <n-space align="center" justify="space-between">
          <span class="field-label">校验位:</span>
          <n-select v-model:value="configParity" :options="parityOptions" size="small" style="width: 180px;" disabled />
        </n-space>
        <n-space align="center" justify="space-between">
          <span class="field-label">停止位:</span>
          <n-select v-model:value="configStopBits" :options="stopBitsOptions" size="small" style="width: 180px;" disabled />
        </n-space>
      </n-space>
    </n-modal>
  </n-card>
</template>

<style scoped>
.chiller-panel {
  background: rgba(255,255,255,0.06);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 14px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.06);
}
.panel-header { display: flex; justify-content: space-between; align-items: center; }
.chiller-body { display: flex; flex-direction: column; gap: 8px; }
.temp-display { text-align: center; padding: 4px 0; }
.temp-value { font-family: 'Fira Code', monospace; font-size: 32px; font-weight: 700; }
.temp-unit { color: #64748B; font-size: 13px; margin-left: 2px; }
.info-row { display: flex; align-items: center; gap: 8px; padding: 2px 0; }
.info-row .field-label { min-width: auto; }
.field-label { color: #94A3B8; font-size: 12px; font-weight: 500; }
.value { color: #F8FAFC; font-size: 13px; }
.indicators { display: flex; flex-wrap: wrap; gap: 5px; }
.indicator {
  font-size: 12px; color: #64748B; padding: 4px 10px;
  background: rgba(255,255,255,0.03); border-radius: 6px;
  display: flex; align-items: center; gap: 5px;
}
.indicator-dot {
  width: 6px; height: 6px; border-radius: 50%; background: #64748B; flex-shrink: 0;
}
.indicator.on { color: #F8FAFC; }
.indicator.on .indicator-dot {
  background: #00e676; box-shadow: 0 0 6px #00e676;
  animation: pulse 2s infinite;
}
.indicator.alarm { color: #ff4757; }
.indicator.alarm .indicator-dot {
  background: #ff4757; box-shadow: 0 0 6px #ff4757;
  animation: pulse 1s infinite;
}
.section { border-top: 1px solid rgba(255,255,255,0.08); padding-top: 8px; }
.mini-chart { width: 100%; min-height: 180px; flex: 1 1 auto; margin: 0 auto; }
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 6px currentColor; }
  50% { box-shadow: 0 0 14px currentColor; }
}
</style>
