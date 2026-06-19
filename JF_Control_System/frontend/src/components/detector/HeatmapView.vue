<template>
  <n-card title="采集图像" size="small" class="heatmap-view">
    <template #header-extra>
      <n-space align="center">
        <n-button-group>
          <n-button
            size="tiny"
            :type="viewTab === 'baseline' ? 'primary' : 'default'"
            :disabled="!hasBaseline"
            @click="viewTab = 'baseline'"
          >基线图</n-button>
          <n-button
            size="tiny"
            :type="viewTab === 'result' ? 'primary' : 'default'"
            :disabled="!hasResult"
            @click="viewTab = 'result'"
          >结果图</n-button>
        </n-button-group>
        <n-checkbox
          v-if="props.data?.is_4m"
          size="small"
          :checked="props.data?.expand ?? false"
          @update:checked="onExpandToggle"
        >扩展拼接</n-checkbox>
      </n-space>
    </template>

    <div v-if="props.processing" class="heatmap-processing">
      <n-spin size="large" />
      <span class="processing-text">正在处理中...</span>
    </div>

    <div v-else-if="!currentData" class="heatmap-empty">
      暂无采集数据，请先进行采集
    </div>

    <div v-else class="heatmap-body">
      <div class="heatmap-canvas-wrap" :class="props.data?.is_4m ? 'wrap-4m' : 'wrap-500k'" ref="wrapRef">
        <canvas
          ref="canvasRef"
          :width="canvasW"
          :height="canvasH"
          class="heatmap-canvas"
          :style="canvasStyle"
          @wheel="onWheel"
          @mousedown="onSelStart"
          @mousemove="onSelMove"
          @mouseup="onSelEnd"
          @mouseleave="onSelEnd"
        />
        <div
          v-if="selecting"
          class="sel-rect"
          :style="selStyle"
        />
      </div>

      <div class="heatmap-colorbar">
        <span class="cb-label cb-label-top">{{ vmax.toFixed(0) }}</span>
        <canvas ref="cbarRef" width="20" :height="cbarH" class="cb-gradient" />
        <span class="cb-label cb-label-bot">{{ vmin.toFixed(0) }}</span>
      </div>
    </div>

    <div v-if="currentData" class="heatmap-toolbar">
      <span class="cb-label">范围:</span>
      <n-input-number v-model:value="inputMin" size="small" :style="{ width: '100px' }" placeholder="min" />
      <span>—</span>
      <n-input-number v-model:value="inputMax" size="small" :style="{ width: '100px' }" placeholder="max" />
      <n-button size="tiny" @click="applyRange">确定</n-button>
      <n-button size="tiny" @click="zoomFit" style="margin-left:8px">适应</n-button>
      <n-button size="tiny" @click="saveImage">💾 保存</n-button>
    </div>
  </n-card>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted } from 'vue'
import { NCard, NButton, NButtonGroup, NSpace, NInputNumber, NCheckbox, NSpin } from 'naive-ui'
import type { VisualData } from '@/types/detector'

const props = defineProps<{
  data: VisualData | null
  hasBaseline: boolean
  processing: boolean
}>()

const emit = defineEmits<{
  toggleExpand: [expand: boolean]
}>()

const viewTab = ref<'baseline' | 'result'>('result')
const cmin = ref<number | null>(null)
const cmax = ref<number | null>(null)
const inputMin = ref<number | null>(null)
const inputMax = ref<number | null>(null)
const autoRange = ref<Record<string, { min: number; max: number }>>({})

const canvasW = ref(1024)
const canvasH = ref(512)

const zoom = ref(1)
const offsetX = ref(0)
const offsetY = ref(0)

// 框选
const selecting = ref(false)
const selX = ref(0), selY = ref(0), selW = ref(0), selH = ref(0)
let selStartX = 0, selStartY = 0

const canvasRef = ref<HTMLCanvasElement | null>(null)
const cbarRef = ref<HTMLCanvasElement | null>(null)
const wrapRef = ref<HTMLDivElement | null>(null)
const cbarH = ref(200)

const hasResult = computed(() => props.data?.result !== null && props.data?.result !== undefined)

const currentData = computed(() => {
  if (!props.data) return null
  if (viewTab.value === 'baseline') return props.data.baseline
  return props.data.result
})

const vmin = computed(() => cmin.value ?? autoRange.value[viewTab.value]?.min ?? props.data?.vmin ?? 0)
const vmax = computed(() => cmax.value ?? autoRange.value[viewTab.value]?.max ?? props.data?.vmax ?? 1)

const canvasStyle = computed(() => ({
  transform: `scale(${zoom.value}) translate(${offsetX.value}px, ${offsetY.value}px)`,
  transformOrigin: 'top left',
}))

const selStyle = computed(() => ({
  left: `${selX.value}px`, top: `${selY.value}px`,
  width: `${selW.value}px`, height: `${selH.value}px`,
}))

watch(() => props.data, (newData) => {
  if (newData) {
    // 1. 先确定显示哪个 tab
    if (newData.result) viewTab.value = 'result'
    else if (newData.baseline) viewTab.value = 'baseline'
    // 2. 在 canvas 元素创建之前预设正确尺寸，避免 Vue 渲染后再 resize 导致 canvas 清空
    const arr = newData.result || newData.baseline
    if (arr && arr.length > 0 && arr[0]?.length > 0) {
      canvasW.value = arr[0].length   // cols
      canvasH.value = arr.length      // rows
    }
    cmin.value = null; cmax.value = null
    inputMin.value = null; inputMax.value = null
    zoom.value = 1; offsetX.value = 0; offsetY.value = 0
  }
})

// 同步 inputMin/inputMax 跟随实际范围
watch([vmin, vmax], () => {
  inputMin.value = Math.round(vmin.value)
  inputMax.value = Math.round(vmax.value)
})

watch([currentData, cmin, cmax, vmin, vmax], () => {
  // 用 nextTick 确保 Vue DOM 更新（v-if→v-else）已完成
  // 再用 RAF 确保浏览器已完成布局
  nextTick(() => {
    requestAnimationFrame(() => {
      drawCanvas()
      updateAxes()
      requestAnimationFrame(() => drawColorbar())
    })
  })
})

// 切 tab 时重置 colorbar 为自动范围
watch(viewTab, () => {
  if (autoRange.value[viewTab.value]) {
    cmin.value = null; cmax.value = null
  }
})

// 当前视图数据变化时，缓存该视图的自动 colorbar 范围
watch(currentData, (arr) => {
  if (!arr || cmin.value !== null) return
  let min = Infinity, max = -Infinity
  for (const row of arr) { for (const v of row) { if (v < min) min = v; if (v > max) max = v } }
  if (min !== Infinity) {
    autoRange.value = { ...autoRange.value, [viewTab.value]: { min, max } }
  }
})

onMounted(() => { drawCanvas(); updateAxes(); nextTick(() => drawColorbar()) })

function onExpandToggle(checked: boolean) {
  emit('toggleExpand', checked)
}

// ---- Jet colormap ----
function jetColor(t: number): [number, number, number] {
  t = Math.max(0, Math.min(1, t))
  const stops = [
    { pos: 0.000, r: 0, g: 0, b: 143 }, { pos: 0.125, r: 0, g: 0, b: 255 },
    { pos: 0.250, r: 0, g: 143, b: 255 }, { pos: 0.375, r: 0, g: 255, b: 255 },
    { pos: 0.500, r: 128, g: 255, b: 128 }, { pos: 0.625, r: 255, g: 255, b: 0 },
    { pos: 0.750, r: 255, g: 128, b: 0 }, { pos: 0.875, r: 255, g: 0, b: 0 },
    { pos: 1.000, r: 128, g: 0, b: 0 },
  ]
  let lo = stops[0], hi = stops[stops.length - 1]
  for (let i = 1; i < stops.length; i++) {
    if (t <= stops[i].pos) { hi = stops[i]; lo = stops[i - 1]; break }
  }
  const f = (t - lo.pos) / (hi.pos - lo.pos || 1)
  return [Math.round(lo.r + (hi.r - lo.r) * f), Math.round(lo.g + (hi.g - lo.g) * f), Math.round(lo.b + (hi.b - lo.b) * f)]
}

// ---- Canvas 图像 ----
let _drawPending = false
function drawCanvas() {
  const arr = currentData.value
  const canvas = canvasRef.value
  if (!arr || !canvas) return
  const rows = arr.length, cols = arr[0]?.length || 0
  if (!rows || !cols) return
  canvasW.value = cols; canvasH.value = rows
  // 仅在尺寸变化时才设置，避免不必要的 canvas 位图清空
  if (canvas.width !== cols) canvas.width = cols
  if (canvas.height !== rows) canvas.height = rows
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const imgData = ctx.createImageData(cols, rows)
  const range = vmax.value - vmin.value || 1
  for (let r = 0; r < rows; r++) {
    const row = arr[r]
    const targetRow = rows - 1 - r
    for (let c = 0; c < cols; c++) {
      const t = (row[c] - vmin.value) / range
      const [jr, jg, jb] = jetColor(t)
      const idx = (targetRow * cols + c) * 4
      imgData.data[idx] = jr; imgData.data[idx + 1] = jg
      imgData.data[idx + 2] = jb; imgData.data[idx + 3] = 255
    }
  }
  ctx.putImageData(imgData, 0, 0)

  // 首次绘制后，延迟二次确认绘制（解决 4M 首次基线黑屏问题）
  if (!_drawPending) {
    _drawPending = true
    setTimeout(() => {
      drawCanvas()
      drawColorbar()
      _drawPending = false
    }, 100)
  }
}

function updateAxes() {
  const wrap = wrapRef.value
  if (!wrap) return
  cbarH.value = Math.round(wrap.clientHeight) || 200
}

// ---- Colorbar ----
function drawColorbar() {
  const canvas = cbarRef.value
  if (!canvas) return
  const h = canvas.height
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  for (let y = 0; y < h; y++) {
    const t = 1 - y / (h - 1)
    const [r, g, b] = jetColor(t)
    ctx.fillStyle = `rgb(${r},${g},${b})`
    ctx.fillRect(0, y, canvas.width, 1)
  }
}

// ---- 缩放 / 框选 ----
function onWheel(e: WheelEvent) {
  e.preventDefault()
  zoom.value = Math.max(0.5, Math.min(10, zoom.value * (e.deltaY > 0 ? 0.9 : 1.1)))
}

function getCanvasPos(e: MouseEvent): { x: number; y: number } {
  const wrap = wrapRef.value
  if (!wrap) return { x: 0, y: 0 }
  const rect = wrap.getBoundingClientRect()
  return { x: e.clientX - rect.left, y: e.clientY - rect.top }
}

function onSelStart(e: MouseEvent) {
  const pos = getCanvasPos(e)
  selStartX = pos.x; selStartY = pos.y
  selecting.value = true
  selX.value = pos.x; selY.value = pos.y; selW.value = 0; selH.value = 0
}

function onSelMove(e: MouseEvent) {
  if (!selecting.value) return
  const pos = getCanvasPos(e)
  const x = Math.min(selStartX, pos.x), y = Math.min(selStartY, pos.y)
  const w = Math.abs(pos.x - selStartX), h = Math.abs(pos.y - selStartY)
  selX.value = x; selY.value = y; selW.value = w; selH.value = h
}

function onSelEnd() {
  if (!selecting.value) return
  selecting.value = false
  if (selW.value < 5 || selH.value < 5) return

  const canvas = canvasRef.value
  const wrap = wrapRef.value
  if (!canvas || !wrap) return

  // 选区在 wrap 中的坐标 → 映射到数据索引
  const crect = canvas.getBoundingClientRect()
  const wrect = wrap.getBoundingClientRect()
  const ox = crect.left - wrect.left, oy = crect.top - wrect.top
  const cw = crect.width, ch = crect.height

  const col1 = Math.max(0, Math.floor((selX.value - ox) / cw * canvasW.value))
  const row1 = Math.max(0, Math.floor((selY.value - oy) / ch * canvasH.value))
  const col2 = Math.min(canvasW.value - 1, Math.ceil((selX.value + selW.value - ox) / cw * canvasW.value))
  const row2 = Math.min(canvasH.value - 1, Math.ceil((selY.value + selH.value - oy) / ch * canvasH.value))

  // 更新 colorbar 范围为选中区域的数据 min/max
  const arr = currentData.value
  if (arr) {
    let min = Infinity, max = -Infinity
    for (let r = row1; r <= row2; r++) {
      const row = arr[r]
      if (!row) continue
      for (let c = col1; c <= col2; c++) {
        const v = row[c] ?? 0
        if (v < min) min = v; if (v > max) max = v
      }
    }
    if (min !== Infinity) { cmin.value = min; cmax.value = max }
  }

  // 缩放并居中到框选区域
  const scx = selX.value + selW.value / 2
  const scy = selY.value + selH.value / 2
  const scale = Math.min(wrap.clientWidth / selW.value, wrap.clientHeight / selH.value)
  const oldZoom = zoom.value
  zoom.value = Math.max(0.5, Math.min(10, oldZoom * scale))
  offsetX.value = wrap.clientWidth / (2 * zoom.value) - scx / oldZoom + offsetX.value
  offsetY.value = wrap.clientHeight / (2 * zoom.value) - scy / oldZoom + offsetY.value
}

function applyRange() {
  cmin.value = inputMin.value
  cmax.value = inputMax.value
}

function zoomFit() { zoom.value = 1; offsetX.value = 0; offsetY.value = 0; cmin.value = null; cmax.value = null }
function saveImage() { const c = canvasRef.value; if (!c) return; const a = document.createElement('a'); a.download = `heatmap_${viewTab.value}.png`; a.href = c.toDataURL('image/png'); a.click() }
</script>

<style scoped>
.heatmap-view { background: rgba(255,255,255,0.06); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); border: 1px solid rgba(255,255,255,0.12); border-radius: 14px; box-shadow: 0 8px 32px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.06); display: flex; flex-direction: column; max-height: 100%; overflow: auto; }
.heatmap-processing { color: #94A3B8; text-align: center; padding: 40px; flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; }
.processing-text { font-size: 14px; color: #94A3B8; }
.heatmap-empty { color: #64748B; text-align: center; padding: 40px; flex: 1; display: flex; align-items: center; justify-content: center; }
.heatmap-body { display: flex; justify-content: center; align-items: stretch; gap: 8px; margin: 8px 0; }
.heatmap-canvas-wrap {
  display: flex; align-items: center; justify-content: center;
  overflow: hidden; flex: none;
  background: #0a1520; border-radius: 4px; position: relative;
}
.heatmap-canvas-wrap.wrap-500k { width: 300px; height: 500px; }
.heatmap-canvas-wrap.wrap-4m { width: 500px; height: 500px; }
.sel-rect {
  position: absolute; border: 1px dashed #00d4ff;
  background: rgba(0, 212, 255, 0.1); pointer-events: none;
}
.heatmap-canvas { max-width: 100%; max-height: 100%; object-fit: contain; image-rendering: pixelated; }
.heatmap-colorbar { display: flex; flex-direction: column; align-items: center; gap: 2px; flex-shrink: 0; }
.cb-gradient { width: 18px; border-radius: 2px; }
.cb-label { color: #94A3B8; font-size: 10px; }
.cb-label-top { margin-bottom: 2px; }
.cb-label-bot { margin-top: 2px; }
.heatmap-toolbar { display: flex; align-items: center; gap: 6px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.10); justify-content: center; }
</style>
