<script setup lang="ts">
import { ref } from 'vue'
import { NCard, NButton, NSpace, NModal, NInput, NInputNumber, NIcon, useMessage } from 'naive-ui'
import {
  FolderOpenOutline, SaveOutline, PlayOutline, StopOutline,
  CloseCircleOutline, PowerOutline
} from '@vicons/ionicons5'
import { api } from '@/api/client'
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

function onConfigSelected(path: string) {
  emit('loadConfig', path)
}

// Save config
const showSaveModal = ref(false)
const savePath = ref('/')

function openSaveModal() {
  savePath.value = '/'
  showSaveModal.value = true
}

async function handleSaveConfig() {
  try {
    await api.saveConfig(savePath.value)
    message.success('配置已保存')
    showSaveModal.value = false
  } catch (e: any) {
    message.error(`保存失败: ${e.message}`)
  }
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
      <!-- Config file operations -->
      <div class="conn-section">
        <div class="section-label">配置文件</div>
        <n-space>
          <n-button size="medium" @click="showBrowser = true">
            <template #icon><n-icon :component="FolderOpenOutline" :size="16" /></template>
            加载配置
          </n-button>
          <n-button size="medium" @click="openSaveModal">
            <template #icon><n-icon :component="SaveOutline" :size="16" /></template>
            保存配置
          </n-button>
        </n-space>
      </div>

      <!-- Receiver control -->
      <div class="conn-section">
        <div class="section-label">接收器</div>
        <div class="receiver-row">
          <span class="param-label">端口</span>
          <n-input-number v-model:value="receiverPort" size="medium" style="width: 100px;"
            :disabled="status.receiver_running" :min="1" :max="65535" />
        </div>
        <n-button v-if="!status.receiver_running" size="medium" type="primary" block
          @click="emit('startReceiver', receiverPort)">
          <template #icon><n-icon :component="PlayOutline" :size="16" /></template>
          启动接收器
        </n-button>
        <n-button v-else size="medium" type="error" block
          @click="emit('stopReceiver')">
          <template #icon><n-icon :component="StopOutline" :size="16" /></template>
          停止接收器
        </n-button>
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

    <!-- Save Config Modal -->
    <n-modal v-model:show="showSaveModal" title="保存配置文件" preset="dialog"
      positive-text="保存" negative-text="取消" @positive-click="handleSaveConfig">
      <n-space vertical size="small" style="padding: 8px 0;">
        <span class="modal-label">保存路径:</span>
        <n-input v-model:value="savePath" size="small" placeholder="/path/to/config.config" />
      </n-space>
    </n-modal>

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
.modal-label {
  color: #94A3B8;
  font-size: 13px;
}
</style>
