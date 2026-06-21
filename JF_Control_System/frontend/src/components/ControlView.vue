<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMessage, NIcon } from 'naive-ui'
import { ChevronBack, ChevronForward } from '@vicons/ionicons5'
import StatusPanel from './detector/StatusPanel.vue'
import DetectorConnection from './detector/DetectorConnection.vue'
import ParamSettings from './detector/ParamSettings.vue'
import AcquisitionControl from './detector/AcquisitionControl.vue'
import HeatmapView from './detector/HeatmapView.vue'
import HistoryList from './detector/HistoryList.vue'
import DisplacementPanel from './displacement/DisplacementPanel.vue'
import ChillerPanel from './chiller/ChillerPanel.vue'
import { useDetector } from '../composables/useDetector'

const message = useMessage()
const historyOpen = ref(false)

const {
  status, temperatures, params, progress, history, error,
  acqMode, visualData, hasBaseline, visualProcessing,
  hostname,
  setParam,
  startAcquisition, startLocalProgress, stopAcquisition,
  fetchHistory, toggleExpand,
  loadConfigFile, shutdownDetector, disconnectDetector,
  startReceiver, stopReceiver,
} = useDetector()

async function onUpdateParams(changes: Record<string, string>) {
  const entries = Object.entries(changes)
  for (let i = 0; i < entries.length; i++) {
    const [name, value] = entries[i]
    try {
      await setParam(name, value)
    } catch (e: any) {
      message.error(`参数 ${name} 设置失败: ${e.message}`)
      return
    }
  }
  message.success('参数已更新')
}

function onStartAcq(mode: 'baseline' | 'signal') {
  if (mode === 'signal' && !hasBaseline.value) {
    message.warning('请先进行基线采集')
    return
  }
  progress.value.acquiring = true
  startLocalProgress()
  startAcquisition(mode).catch((e: any) => {
    progress.value.acquiring = false
    message.error(`采集启动失败: ${e.message}`)
  })
}

function onStopAcq() {
  stopAcquisition().catch((e: any) =>
    message.error(`采集停止失败: ${e.message}`)
  )
}

async function onLoadConfig(path: string) {
  try {
    await loadConfigFile(path)
    message.success('配置文件加载成功')
  } catch (e: any) {
    message.error(`配置文件加载失败: ${e.message}`)
  }
}

async function onDisconnect() {
  try {
    await disconnectDetector()
    message.success('已断开连接')
  } catch (e: any) {
    message.error(`断开失败: ${e.message}`)
  }
}

async function onShutdown() {
  try {
    await shutdownDetector()
    message.success('探测器已关机')
  } catch (e: any) {
    message.error(`关机失败: ${e.message}`)
  }
}

async function onStartReceiver(port: number) {
  try {
    await startReceiver(port)
    message.success('接收器已启动')
  } catch (e: any) {
    message.error(`接收器启动失败: ${e.message}`)
  }
}

async function onStopReceiver() {
  try {
    await stopReceiver()
    message.success('接收器已停止')
  } catch (e: any) {
    message.error(`接收器停止失败: ${e.message}`)
  }
}

onMounted(() => {
  fetchHistory().catch(() => {})
})
</script>

<template>
  <div class="control-view">
    <!-- Left: Displacement + Chiller stacked 50/50 -->
    <div class="left-panels">
      <div class="left-half">
        <ChillerPanel />
      </div>
      <div class="left-half">
        <DisplacementPanel />
      </div>
    </div>

    <!-- Center: StatusPanel + Detector workspace -->
    <div class="main-area">
      <div class="detector-top-row">
        <StatusPanel
          :temps="temperatures"
          :params="params"
          :status="status"
        />
        <DetectorConnection
          :status="status"
          :hostname="hostname"
          @load-config="onLoadConfig"
          @disconnect="onDisconnect"
          @shutdown="onShutdown"
          @start-receiver="onStartReceiver"
          @stop-receiver="onStopReceiver"
        />
      </div>
      <div class="center-top">
        <ParamSettings
          :params="params"
          :disabled="progress.acquiring"
          @update-params="onUpdateParams"
        />
        <AcquisitionControl
          :progress="progress"
          :params="params"
          :status="status"
          :error="error"
          :acq-mode="acqMode"
          :has-baseline="hasBaseline"
          @start="onStartAcq"
          @stop="onStopAcq"
        />
      </div>
      <div class="center-bottom">
        <HeatmapView
          :data="visualData"
          :has-baseline="hasBaseline"
          :processing="visualProcessing"
          @toggle-expand="(expand: boolean) => toggleExpand(expand)"
        />
      </div>
    </div>

    <!-- Right sidebar: History, collapsible -->
    <div class="history-sidebar" :class="{ collapsed: !historyOpen }">
      <div class="history-toggle" @click="historyOpen = !historyOpen">
        <n-icon :component="historyOpen ? ChevronForward : ChevronBack" :size="16" />
      </div>
      <div v-show="historyOpen" class="history-content">
        <HistoryList :records="history" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.control-view {
  display: flex;
  gap: 0;
  padding: 8px;
  height: 100%;
  min-height: 0;
  position: relative;
}

/* ── Left column: 4 ── */
.left-panels {
  flex: 4;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 260px;
  padding-right: 10px;
}

.left-half {
  min-height: 0;
  overflow-y: auto;
}

/* ── Center column: 6 ── */
.main-area {
  flex: 6;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  min-height: 0;
  padding: 0 5px;
}

.detector-top-row {
  flex-shrink: 0;
  display: flex;
  gap: 10px;
}

.detector-top-row > * {
  flex: 1;
  min-width: 0;
}

.center-top {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.center-bottom {
  flex: 1 1 0%;
  min-height: 0;
  overflow: hidden;
}

/* ── Right sidebar: History overlay ── */
.history-sidebar {
  position: absolute;
  right: 0;
  top: 8px;
  bottom: 8px;
  z-index: 20;
  transform: translateX(calc(100% - 28px));
  transition: transform 0.3s ease;
  display: flex;
  flex-direction: row;
}

.history-sidebar:not(.collapsed) {
  transform: translateX(0);
}

.history-toggle {
  width: 24px;
  height: 48px;
  margin-top: auto;
  margin-bottom: auto;
  flex-shrink: 0;
  background: rgba(255,255,255,0.06);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 8px 0 0 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #94A3B8;
  user-select: none;
  transition: color 0.2s, background 0.2s;
}

.history-toggle:hover {
  color: #00d4ff;
  background: rgba(255,255,255,0.10);
}

.history-content {
  width: 800px;
  height: 100%;
  overflow: hidden;
  flex-shrink: 0;
  background: rgba(2,6,23,0.95);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 0;
}

@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
</style>
