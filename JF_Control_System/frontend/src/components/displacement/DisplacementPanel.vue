<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { NCard, NButton, NInputNumber, NSelect, NSpace, NModal, NIcon } from 'naive-ui'
import {
  LocateOutline, AlertCircleOutline,
  PlayOutline, StopOutline, ReloadOutline, SettingsOutline
} from '@vicons/ionicons5'
import { useDisplacement } from '../../composables/useDisplacement'
import * as dispApi from '../../api/displacement'

const {
  connected, ports, position, originComplete, scanState,
  driveState, emgSignal, originSignal, limitSignal, softLimit, servoOn, axisNo,
  loadPorts, connect: dispConnect, disconnect: dispDisconnect,
} = useDisplacement()

const absTarget = ref(0)
const relOffset = ref(1000)
const speedTable = ref(0)
const scanDir = ref(1)
const scanStepSize = ref(1000)
const scanSteps = ref(10)
const scanPause = ref(500)
const scanSpeedTable = ref(0)
const showResetModal = ref(false)

// Serial config modal
const showSerialModal = ref(false)
const configPort = ref('/dev/ttyUSB1')
const configBaudrate = ref(115200)
const configAxisNo = ref(1)

const scanProgress = computed(() =>
  scanState.total_steps > 0
    ? Math.round((scanState.current_step / scanState.total_steps) * 100)
    : 0
)

const posDisplay = computed(() => {
  if (!connected.value) return '--'
  return Math.round(position.value ?? 0).toString()
})

async function handleSerialConnect() {
  dispConnect(configPort.value, configBaudrate.value, configAxisNo.value)
  showSerialModal.value = false
}

function handleSerialDisconnect() {
  dispDisconnect()
  showSerialModal.value = false
}

function openSerialModal() {
  configPort.value = configPort.value || (ports.value[0] ?? '')
  configAxisNo.value = axisNo.value
  showSerialModal.value = true
}

async function handleReset() {
  showResetModal.value = false
  await dispApi.systemReset()
}

async function handleEmergencyRelease() {
  await dispApi.emergencyRelease()
}

onMounted(() => { loadPorts() })
</script>

<template>
  <n-card size="small" class="disp-panel">
    <template #header>
      <div class="panel-header">
        <span style="display:flex; align-items:center; gap:6px;">
          <n-icon :component="LocateOutline" :size="20" color="#00d4ff" />
          <span style="color: #00d4ff; font-weight: bold;">位移台控制</span>
        </span>
      </div>
    </template>

    <template #header-extra>
      <n-space size="small" align="center">
        <n-button size="medium" @click="openSerialModal">
          <template #icon><n-icon :component="SettingsOutline" :size="14" /></template>
          串口配置
        </n-button>
        <span :style="{ color: connected ? '#00e676' : '#ff4757', fontSize: '12px' }">
          {{ connected ? '● 已连接' : '○ 未连接' }}
        </span>
      </n-space>
    </template>

    <div class="disp-body">
      <!-- Status Grid 2x4 -->
      <div class="section">
        <div class="field-label">状态</div>
        <div class="status-grid">
          <div class="stat-item">
            <span class="stat-label">位置</span>
            <span class="stat-value temp">{{ connected ? posDisplay : '--' }} pulse</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">伺服上电</span>
            <span :class="['stat-value', connected && servoOn ? 'success' : '']">
              {{ connected ? (servoOn ? '已上电' : '未上电') : '--' }}
            </span>
          </div>
          <div class="stat-item">
            <span class="stat-label">驱动状态</span>
            <span :class="['stat-value', connected && driveState === '运行中' ? 'success' : '']">
              {{ connected ? (driveState || '--') : '--' }}
            </span>
          </div>
          <div class="stat-item">
            <span class="stat-label">原点完成</span>
            <span :class="['stat-value', connected && originComplete ? 'success' : '']">
              {{ connected ? (originComplete ? '完成' : '未完成') : '--' }}
            </span>
          </div>
          <div class="stat-item">
            <span class="stat-label">急停信号</span>
            <span :class="['stat-value', connected && emgSignal ? 'alarm' : connected ? 'success' : '']">
              {{ connected ? (emgSignal ? '触发' : '正常') : '--' }}
            </span>
          </div>
          <div class="stat-item">
            <span class="stat-label">原点信号</span>
            <span :class="['stat-value', connected && originSignal ? 'alarm' : '']">
              {{ connected ? (originSignal ? 'ON' : 'OFF') : '--' }}
            </span>
          </div>
          <div class="stat-item">
            <span class="stat-label">限位信号</span>
            <span :class="['stat-value', connected && limitSignal ? 'alarm' : connected ? 'success' : '']">
              {{ connected ? (limitSignal ? '触发' : '正常') : '--' }}
            </span>
          </div>
          <div class="stat-item">
            <span class="stat-label">软限位</span>
            <span :class="['stat-value', connected && softLimit ? 'alarm' : connected ? 'success' : '']">
              {{ connected ? (softLimit ? '超限' : '正常') : '--' }}
            </span>
          </div>
        </div>
      </div>

      <!-- Movement Control -->
      <div class="section">
        <div class="field-label">移动控制</div>
        <n-space vertical size="large">
          <n-space align="center">
            <span class="param-label">速度表</span>
            <n-input-number v-model:value="speedTable" size="small" style="width: 110px;" :min="0" :max="4" />
            <n-button size="medium" type="error" @click="dispApi.stop(axisNo)">
              <template #icon><n-icon :component="StopOutline" :size="16" /></template>
              停止
            </n-button>
          </n-space>
          <n-space align="center">
            <span class="param-label">目标位置</span>
            <n-input-number v-model:value="absTarget" size="small" style="width: 110px;" placeholder="目标位置" />
            <n-button size="medium" type="primary" @click="dispApi.moveAbsolute(axisNo, absTarget, speedTable)">绝对移动</n-button>
          </n-space>
          <n-space align="center">
            <span class="param-label">偏移量</span>
            <n-input-number v-model:value="relOffset" size="small" style="width: 110px;" placeholder="偏移量" />
            <n-button size="medium" type="primary" @click="dispApi.moveRelative(axisNo, -Math.abs(relOffset), speedTable)">
              <template #icon><n-icon :component="PlayOutline" :size="14" style="transform: scaleX(-1)" /></template>
              负向移动
            </n-button>
            <n-button size="medium" type="primary" @click="dispApi.moveRelative(axisNo, Math.abs(relOffset), speedTable)">
              <template #icon><n-icon :component="PlayOutline" :size="14" /></template>
              正向移动
            </n-button>
          </n-space>
        </n-space>
      </div>

      <!-- Scan Mode -->
      <div class="section">
        <div class="field-label">扫描模式</div>
        <n-space vertical size="large">
          <n-space align="center">
            <span class="param-label">方向</span>
            <n-button size="medium" :type="scanDir === 0 ? 'primary' : 'default'" @click="scanDir = 0">
              <template #icon><n-icon :component="PlayOutline" :size="14" /></template>
              正向
            </n-button>
            <n-button size="medium" :type="scanDir === 1 ? 'primary' : 'default'" @click="scanDir = 1">
              <template #icon><n-icon :component="PlayOutline" :size="14" style="transform: scaleX(-1)" /></template>
              负向
            </n-button>
          </n-space>
          <n-space align="center">
            <span class="param-label">速度表</span>
            <n-input-number v-model:value="scanSpeedTable" size="small" style="width: 85px;" :min="0" :max="9" />
            <span class="param-label" style="margin-left:8px;">步长</span>
            <n-input-number v-model:value="scanStepSize" size="small" style="width: 110px;" :step="0.1" :min="0.001" />
            <span class="param-label" style="margin-left:8px;">步数</span>
            <n-input-number v-model:value="scanSteps" size="small" style="width: 85px;" :min="1" :step="1" />
            <span class="param-label" style="margin-left:8px;">步间暂停</span>
            <n-input-number v-model:value="scanPause" size="small" style="width: 110px;" :min="0" :step="10" />
            <span style="color:#557799; font-size:10px;">ms</span>
          </n-space>
          <n-space>
            <n-button size="medium" type="primary" @click="dispApi.startScan(axisNo, scanDir, scanStepSize, scanSteps, scanSpeedTable, scanPause)"
              :disabled="scanState.running">
              <template #icon><n-icon :component="PlayOutline" :size="14" /></template>
              开始扫描
            </n-button>
            <n-button size="medium" type="error" @click="dispApi.stopScan()"
              :disabled="!scanState.running">
              <template #icon><n-icon :component="StopOutline" :size="14" /></template>
              停止
            </n-button>
          </n-space>
          <div style="margin-top: 4px;">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: scanProgress + '%' }"></div>
            </div>
            <span class="stat-label">{{ scanState.running ? scanState.current_step + ' / ' + scanState.total_steps : '就绪' }}</span>
          </div>
        </n-space>
      </div>

      <!-- Functions (last) -->
      <div class="section">
        <div class="field-label">功能</div>
        <n-space>
          <n-button size="medium" type="primary" @click="dispApi.originReturn(axisNo)">
            <template #icon><n-icon :component="ReloadOutline" :size="16" /></template>
            原点回归
          </n-button>
          <n-button size="medium" type="error" @click="showResetModal = true">
            <template #icon><n-icon :component="ReloadOutline" :size="16" style="transform: scaleX(-1)" /></template>
            系统复位
          </n-button>
          <n-button size="medium" type="warning" @click="handleEmergencyRelease">
            <template #icon><n-icon :component="AlertCircleOutline" :size="16" /></template>
            急停释放
          </n-button>
        </n-space>
      </div>
    </div>

    <!-- Serial Config Modal -->
    <n-modal v-model:show="showSerialModal" title="串口配置" preset="dialog" positive-text="连接" negative-text="取消"
      @positive-click="handleSerialConnect">
      <n-space vertical size="small" style="padding: 8px 0;">
        <n-space align="center" justify="space-between">
          <span class="modal-label">端口:</span>
          <n-select v-model:value="configPort" :options="ports.map(p => ({ label: p, value: p }))"
            size="small" style="width: 200px;" placeholder="选择端口" />
        </n-space>
        <n-space align="center" justify="space-between">
          <span class="modal-label">波特率:</span>
          <n-input-number v-model:value="configBaudrate" size="small" style="width: 200px;" disabled />
        </n-space>
        <n-space align="center" justify="space-between">
          <span class="modal-label">轴号:</span>
          <n-input-number v-model:value="configAxisNo" size="small" :min="1" :max="32" style="width: 200px;" />
        </n-space>
        <n-space v-if="connected" justify="center" style="margin-top: 8px;">
          <n-button size="medium" type="error" @click="handleSerialDisconnect">断开</n-button>
        </n-space>
      </n-space>
    </n-modal>

    <!-- System Reset Modal -->
    <n-modal :show="showResetModal" @update:show="(v: boolean) => showResetModal = v">
      <n-card style="width: 320px;" title="系统复位" :bordered="false" size="huge" role="dialog" aria-modal="true">
        <p style="color: #c0d0e0; margin-bottom: 16px;">确认执行系统复位？</p>
        <n-space justify="end">
          <n-button size="medium" @click="showResetModal = false">取消</n-button>
          <n-button size="medium" type="error" @click="handleReset">确认复位</n-button>
        </n-space>
      </n-card>
    </n-modal>
  </n-card>
</template>

<style scoped>
.disp-panel {
  background: rgba(255,255,255,0.06);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 14px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.06);
}
.panel-header { display: flex; justify-content: space-between; align-items: center; }
.disp-body { display: flex; flex-direction: column; gap: 8px; }
.section { border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 8px; }
.section:last-child { border-bottom: none; padding-bottom: 0; }
.field-label { color: #94A3B8; font-size: 12px; font-weight: 500; margin-bottom: 6px; }
.status-grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 6px; }
.stat-item { background: rgba(255,255,255,0.03); padding: 6px 8px; border-radius: 10px; text-align: center; }
.stat-label { color: #64748B; font-size: 12px; font-weight: 400; display: block; }
.stat-value { color: #F8FAFC; font-size: 15px; font-weight: 600; }
.stat-value.temp { color: #ff9944; }
.stat-value.success { color: #00e676; }
.stat-value.alarm { color: #ff4757; }
.param-label { color: #94A3B8; font-size: 12px; font-weight: 500; min-width: 40px; }
.modal-label { color: #94A3B8; font-size: 13px; }
.progress-bar { height: 4px; background: rgba(255,255,255,0.08); border-radius: 2px; overflow: hidden; margin-bottom: 2px; }
.progress-fill { height: 100%; background: linear-gradient(135deg, #00d4ff, #2080f0); transition: width 0.3s; }
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 6px currentColor; }
  50% { box-shadow: 0 0 14px currentColor; }
}
</style>
