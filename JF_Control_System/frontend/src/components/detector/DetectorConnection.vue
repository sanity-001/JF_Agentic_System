<script setup lang="ts">
import { ref, watch } from 'vue'
import { NCard, NButton, NSpace, NModal, NInput, NInputNumber, NIcon, useMessage } from 'naive-ui'
import {
  FolderOpenOutline, PlayOutline, StopOutline,
  CloseCircleOutline, PowerOutline, CheckmarkOutline
} from '@vicons/ionicons5'
import FileBrowser from './FileBrowser.vue'
import type { DetectorStatus } from '@/types/detector'

const props = defineProps<{
  status: DetectorStatus
  hostname: string
}>()

const emit = defineEmits<{
  loadConfig: [path: string]
  disconnect: []
  shutdown: []
  startReceiver: [port: number]
  stopReceiver: []
}>()

const message = useMessage()

// File browser
const showBrowser = ref(false)
const defaultConfigPath = '/home/jfdaq/JF500K/JF500K-shine.config'
const selectedConfigPath = ref(defaultConfigPath)

// 关机/断开后恢复默认路径
watch(() => props.status.connected, (connected) => {
  if (!connected) {
    selectedConfigPath.value = defaultConfigPath
  }
})

function onConfigSelected(path: string) {
  selectedConfigPath.value = path
}

function confirmLoadConfig() {
  if (!selectedConfigPath.value) {
    message.warning('请先选择配置文件')
    return
  }
  emit('loadConfig', selectedConfigPath.value)
  selectedConfigPath.value = ''
}

// Receiver
const receiverPort = ref(1954)

// Shutdown
const showShutdownModal = ref(false)
</script>

<template>
  <n-card size="small" class="detector-connection">
    <template #header>
      <span style="display:flex; align-items:center; gap:6px;">
        <n-icon :component="PowerOutline" :size="20" color="#00d4ff" />
        <span style="color: #00d4ff; font-weight: bold;">探测器连接</span>
      </span>
    </template>

    <template #header-extra>
      <span :style="{ color: status.connected ? '#00e676' : '#ff4757', fontSize: '12px' }">
        {{ status.connected ? '● 已连接' : '○ 未连接' }}
      </span>
    </template>

    <div class="conn-body">
      <!-- Receiver control -->
      <div class="conn-section">
        <div class="section-label">接收器</div>
        <div class="receiver-row">
          <span class="param-label">端口</span>
          <n-input-number v-model:value="receiverPort" size="medium" style="width: 100px;"
            :disabled="status.receiver_running" :min="1" :max="65535" />
          <n-button v-if="!status.receiver_running" size="small" type="primary"
            @click="emit('startReceiver', receiverPort)">
            <template #icon><n-icon :component="PlayOutline" :size="14" /></template>
            启动
          </n-button>
          <n-button v-else size="small" type="error"
            @click="emit('stopReceiver')">
            <template #icon><n-icon :component="StopOutline" :size="14" /></template>
            停止
          </n-button>
        </div>
      </div>

      <!-- Config file selection -->
      <div class="conn-section">
        <div class="section-label">配置文件</div>
        <div class="config-row">
          <n-input v-model:value="selectedConfigPath" size="small"
            :placeholder="defaultConfigPath"
            style="flex:1" />
          <n-button size="small" @click="showBrowser = true">
            <template #icon><n-icon :component="FolderOpenOutline" :size="14" /></template>
            浏览
          </n-button>
          <n-button size="small" type="primary"
            :disabled="!selectedConfigPath || status.connected"
            @click="confirmLoadConfig">
            <template #icon><n-icon :component="CheckmarkOutline" :size="14" /></template>
            加载
          </n-button>
        </div>
        <div v-if="selectedConfigPath && status.connected" class="loaded-info">
          当前配置：{{ selectedConfigPath }}
        </div>
      </div>

      <!-- Disconnect & Shutdown -->
      <div class="conn-section">
        <div class="section-label">系统</div>
        <n-space>
          <n-button size="medium" type="warning" @click="emit('disconnect')"
            :disabled="!status.connected">
            <template #icon><n-icon :component="CloseCircleOutline" :size="16" /></template>
            断开连接
          </n-button>
          <n-button size="medium" type="error" @click="showShutdownModal = true"
            :disabled="!status.connected">
            <template #icon><n-icon :component="PowerOutline" :size="16" /></template>
            关机
          </n-button>
        </n-space>
      </div>
    </div>

    <!-- File Browser Modal -->
    <FileBrowser :show="showBrowser" @update:show="(v: boolean) => showBrowser = v"
      @select="onConfigSelected" />

    <!-- Shutdown Confirm Modal -->
    <n-modal v-model:show="showShutdownModal" title="确认关机" preset="dialog"
      positive-text="确认关机" negative-text="取消"
      @positive-click="emit('shutdown')">
      <div style="padding: 8px 0; color: #c0d0e0;">
        <p>确认执行探测器关机？</p>
        <p style="color: #ff4757; font-size: 12px; margin-top: 8px;">
          关机后需重新上电才能恢复连接。
        </p>
      </div>
    </n-modal>
  </n-card>
</template>

<style scoped>
.detector-connection {
  background: rgba(255,255,255,0.06);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 14px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.06);
}
.conn-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.conn-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 12px;
  background: rgba(255,255,255,0.03);
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.05);
}
.section-label {
  color: #94A3B8;
  font-size: 12px;
  font-weight: 500;
}
.receiver-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.param-label {
  color: #94A3B8;
  font-size: 13px;
}
.config-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.loaded-info {
  color: #00d4ff;
  font-size: 11px;
  margin-top: 4px;
}
</style>
