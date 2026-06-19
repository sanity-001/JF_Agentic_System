<script setup lang="ts">
import { ref, reactive } from 'vue'
import { NCard, NButton, NInput, NInputNumber, NSelect, NSpace, NIcon } from 'naive-ui'
import { BarChartOutline } from '@vicons/ionicons5'

const modes = [
  { label: '1. 单帧查看', value: 1 },
  { label: '2. 多帧平均', value: 2 },
  { label: '3. 单像素拟合', value: 3 },
  { label: '4. 增益图', value: 4 },
  { label: '5. 增益对比', value: 5 },
  { label: '6. 噪声峰图', value: 6 },
  { label: '7. 标准差图', value: 7 },
]

const mode = ref(1)
const filePath = ref('')
const frameIdx = ref(0)
const startFrame = ref(0)
const endFrame = ref(100)
const pixX = ref(256)
const pixY = ref(512)
const useBaseline = ref(false)
const baselinePath = ref('')
const resultImage = ref('')
const resultGainImage = ref('')
const metrics = reactive({ min: 0, max: 0, mean: 0, std: 0 })
const fitResult = reactive({ gain: '', noise_peak: '', signal_peak: '', noise_sigma: '' })
const loading = ref(false)
const error = ref('')

const BASE = '/api/processing'

async function runProcessing() {
  loading.value = true
  error.value = ''
  resultImage.value = ''
  resultGainImage.value = ''

  try {
    let res: any = null
    const file = filePath.value.trim()
    if (!file) { error.value = '请输入数据文件路径'; loading.value = false; return }

    if (mode.value === 1) {
      res = await apiPost('/frame/read', { file_path: file, frame_idx: frameIdx.value })
    } else if (mode.value === 2) {
      const body: any = { file_path: file, start_frame: startFrame.value, end_frame: endFrame.value }
      if (useBaseline.value && baselinePath.value) body.baseline_path = baselinePath.value
      res = await apiPost('/frame/average', body)
    } else if (mode.value === 3) {
      res = await apiPost('/pixel/fit', {
        file_path: file, x: pixX.value, y: pixY.value,
        start_frame: startFrame.value, end_frame: endFrame.value,
      })
    } else if (mode.value === 4) {
      res = await apiPost('/gainmap/compute', {
        file_path: file, start_frame: startFrame.value, end_frame: endFrame.value,
      })
    } else if (mode.value === 6) {
      res = await apiPost('/noisemap/compute', {
        file_path: file, start_frame: startFrame.value, end_frame: endFrame.value,
      })
    } else if (mode.value === 7) {
      const body: any = { file_path: file, start_frame: startFrame.value, end_frame: endFrame.value }
      if (useBaseline.value && baselinePath.value) {
        body.use_baseline = true
        body.baseline_path = baselinePath.value
      }
      res = await apiPost('/stdmap/compute', body)
    }

    if (res) {
      if (res.image_base64) resultImage.value = `data:image/png;base64,${res.image_base64}`
      if (res.gain_base64) resultGainImage.value = `data:image/png;base64,${res.gain_base64}`
      metrics.min = res.min ?? 0
      metrics.max = res.max ?? 0
      metrics.mean = res.mean ?? 0
      metrics.std = res.std ?? 0

      // Mode 3 specific
      if (res.gain_adu_per_kev !== undefined) fitResult.gain = res.gain_adu_per_kev?.toFixed(4) ?? '--'
      if (res.noise_peak !== undefined) fitResult.noise_peak = res.noise_peak?.toFixed(2) ?? '--'
      if (res.signal_peak !== undefined) fitResult.signal_peak = res.signal_peak?.toFixed(2) ?? '--'
      if (res.noise_sigma !== undefined) fitResult.noise_sigma = res.noise_sigma?.toFixed(2) ?? '--'
    }
  } catch (e: any) {
    error.value = e.message || '处理失败'
  } finally {
    loading.value = false
  }
}

async function apiPost(path: string, body: any) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

function exportPNG() {
  if (!resultImage.value) return
  const a = document.createElement('a')
  a.href = resultImage.value
  a.download = `processing_result_${Date.now()}.png`
  a.click()
}

const showFrameRange = () => [2, 3, 4, 6, 7].includes(mode.value)
const showPixelCoords = () => mode.value === 3
const showBaseline = () => [2, 7].includes(mode.value)
const isMode5 = () => mode.value === 5
</script>

<template>
  <div class="processing-view">
    <!-- Left control panel -->
    <div class="proc-left">
      <n-card size="small" class="proc-card">
        <div style="color: #00d4ff; font-weight: bold; margin-bottom: 12px; display:flex; align-items:center; gap:6px;">
          <n-icon :component="BarChartOutline" :size="20" />
          <span>数据分析</span>
        </div>

        <n-space vertical size="small">
          <!-- File path -->
          <div>
            <div class="field-label">数据文件路径</div>
            <n-input v-model:value="filePath" size="small" placeholder="D:/path/to/file.raw" />
          </div>

          <!-- Mode selector -->
          <div>
            <div class="field-label">处理模式</div>
            <n-select v-model:value="mode" :options="modes" size="small" />
          </div>

          <!-- Mode 1: Single frame -->
          <div v-if="mode === 1">
            <div class="field-label">帧序号</div>
            <n-input-number v-model:value="frameIdx" size="small" :min="0" style="width: 100%;" />
          </div>

          <!-- Frame range (modes 2,4,6,7) -->
          <div v-if="showFrameRange()">
            <div class="field-label">帧范围</div>
            <n-space>
              <n-input-number v-model:value="startFrame" size="small" :min="0" style="width: 90px;" />
              <span style="color: #557799; line-height: 28px;">—</span>
              <n-input-number v-model:value="endFrame" size="small" :min="0" style="width: 90px;" />
            </n-space>
          </div>

          <!-- Pixel coordinates (mode 3) -->
          <div v-if="showPixelCoords()">
            <div class="field-label">像素坐标 (col, row)</div>
            <n-space>
              <n-input-number v-model:value="pixX" size="small" :min="0" :max="1023" style="width: 80px;" />
              <n-input-number v-model:value="pixY" size="small" :min="0" :max="511" style="width: 80px;" />
            </n-space>
          </div>

          <!-- Baseline (modes 2,7) -->
          <div v-if="showBaseline()">
            <div style="margin-bottom: 4px;">
              <label style="color: #7eb8da; font-size: 11px; cursor: pointer;">
                <input type="checkbox" v-model="useBaseline" style="margin-right: 4px;" />
                使用基线文件
              </label>
            </div>
            <n-input v-if="useBaseline" v-model:value="baselinePath" size="small" placeholder="基线文件路径" />
          </div>

          <!-- Mode 5: not implemented yet -->
          <div v-if="isMode5()" style="color: #ff9944; font-size: 12px; padding: 8px 0;">
            ⚠ 增益对比功能正在开发中
          </div>

          <!-- Run button -->
          <n-button type="primary" size="medium" :loading="loading" block @click="runProcessing"
            :disabled="isMode5()">
            {{ loading ? '处理中...' : '▶ 开始处理' }}
          </n-button>

          <!-- Error -->
          <div v-if="error" class="error-msg">{{ error }}</div>
        </n-space>
      </n-card>
    </div>

    <!-- Right result area -->
    <div class="proc-right">
      <div class="result-area" v-if="resultImage || loading">
        <!-- Fit result for mode 3 -->
        <div v-if="mode === 3 && fitResult.gain" class="fit-results">
          <div class="metric-item">
            <span class="metric-label">增益</span>
            <span class="metric-value">{{ fitResult.gain }} ADU/keV</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">噪声峰</span>
            <span class="metric-value">{{ fitResult.noise_peak }} ADU</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">信号峰</span>
            <span class="metric-value">{{ fitResult.signal_peak }} ADU</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">噪声σ</span>
            <span class="metric-value">{{ fitResult.noise_sigma }} ADU</span>
          </div>
        </div>

        <!-- General metrics -->
        <div class="metrics-row" v-if="metrics.max > 0 || metrics.min !== 0">
          <div class="metric-item">
            <span class="metric-label">最小值</span>
            <span class="metric-value">{{ metrics.min.toFixed(2) }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">最大值</span>
            <span class="metric-value">{{ metrics.max.toFixed(2) }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">均值</span>
            <span class="metric-value">{{ metrics.mean.toFixed(2) }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">标准差</span>
            <span class="metric-value">{{ metrics.std.toFixed(2) }}</span>
          </div>
        </div>

        <!-- Images -->
        <div class="images-row">
          <div v-if="resultImage" class="image-container">
            <img :src="resultImage" class="result-img" />
          </div>
          <div v-if="resultGainImage" class="image-container">
            <img :src="resultGainImage" class="result-img" />
          </div>
        </div>

        <!-- Export -->
        <n-button v-if="resultImage" size="small" style="margin-top: 8px;" @click="exportPNG">
          💾 导出 PNG
        </n-button>
      </div>

      <div v-else class="empty-state">
        <span style="color: #557799; font-size: 16px;">选择文件和处理模式，点击开始处理</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.processing-view {
  display: flex;
  gap: 12px;
  padding: 8px;
  height: 100%;
  min-height: 0;
}

.proc-left {
  width: 280px;
  flex-shrink: 0;
  overflow-y: auto;
}

.proc-card {
  background: rgba(255,255,255,0.06);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 14px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.06);
}

.fit-results {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.proc-right {
  flex: 1;
  overflow-y: auto;
  min-width: 0;
}

.field-label {
  color: #94A3B8;
  font-size: 12px;
  font-weight: 500;
  margin-bottom: 4px;
}

.error-msg {
  color: #ff6666;
  font-size: 12px;
  padding: 6px;
  background: rgba(255, 71, 87, 0.1);
  border-radius: 4px;
  border: 1px solid rgba(255, 71, 87, 0.3);
  word-break: break-all;
}

.metrics-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.metric-item {
  background: rgba(255,255,255,0.06);
  border-radius: 4px;
  padding: 8px 12px;
  text-align: center;
  flex: 1;
}

.metric-label {
  display: block;
  color: #64748B;
  font-size: 10px;
}

.metric-value {
  display: block;
  color: #F8FAFC;
  font-size: 14px;
  font-weight: 600;
}

.images-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.image-container {
  background: #0a1520;
  border-radius: 4px;
  overflow: hidden;
  flex-shrink: 0;
}

.result-img {
  display: block;
  image-rendering: pixelated;
  max-width: 600px;
  max-height: 500px;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #64748B;
}
</style>
