<template>
  <n-card size="small" class="param-settings">
    <template #header>
      <span style="display:flex; align-items:center; gap:6px;">
        <n-icon :component="SettingsOutline" :size="20" color="#00d4ff" />
        <span style="color: #00d4ff; font-weight: bold;">采集参数</span>
      </span>
    </template>
    <div class="param-grid">
      <div v-for="field in editableFields" :key="field.key" class="param-row">
        <span class="param-label">{{ field.label }}</span>
        <n-input
          v-model:value="editing[field.key]"
          size="small"
          :disabled="disabled"
          :style="{ width: field.wide ? '280px' : field.browse ? '100px' : field.unit ? '110px' : '140px' }"
        />
        <n-button
          v-if="field.browse"
          size="medium"
          :disabled="disabled"
          @click="openBrowser"
        >
          <template #icon><n-icon><FolderOutline /></n-icon></template>
        </n-button>
        <span v-if="field.unit" class="param-unit">{{ field.unit }}</span>
      </div>
    </div>
    <div class="param-actions">
      <n-button type="primary" size="medium" @click="onConfirm" :disabled="disabled || !dirty">确定</n-button>
      <n-button size="medium" @click="onReset" :disabled="disabled || !dirty">重置</n-button>
    </div>

    <!-- 目录浏览弹窗 -->
    <n-modal :show="showBrowser" @update:show="showBrowser = $event">
      <n-card title="选择存储目录" style="width:600px" :bordered="false" role="dialog">
        <template #header-extra>
          <n-button size="tiny" @click="showBrowser = false">✕</n-button>
        </template>
        <div class="browser-path">
          <n-input v-model:value="browsePath" size="small" @keyup.enter="doBrowse(browsePath)" />
          <n-button size="small" @click="doBrowse(browsePath)">跳转</n-button>
        </div>
        <n-divider />
        <div class="browser-list">
          <div v-if="browseParent !== null" class="browser-item dir" @click="doBrowse(browseParent!)">
            📁 ..
          </div>
          <div v-for="d in browseDirs" :key="d.path" class="browser-item dir" @click="doBrowse(d.path)">
            📁 {{ d.name }}
          </div>
        </div>
        <div class="browser-selected">
          当前目录：{{ browsePath }}
        </div>
        <template #footer>
          <n-button @click="showBrowser = false">取消</n-button>
          <n-button type="primary" @click="selectDir">确定</n-button>
        </template>
      </n-card>
    </n-modal>
  </n-card>
</template>

<script setup lang="ts">
import { reactive, ref, watch, nextTick, onUnmounted } from 'vue'
import { NCard, NInput, NButton, NModal, NIcon, NDivider } from 'naive-ui'
import { SettingsOutline, FolderOutline } from '@vicons/ionicons5'
import { api } from '@/api/client'
import type { DetectorParams } from '@/types/detector'

const props = defineProps<{
  params: DetectorParams
  disabled: boolean
}>()

const emit = defineEmits<{
  updateParams: [changes: Record<string, string>]
}>()

const editableFields = [
  { key: 'exptime', label: '曝光时间', unit: 'μs' },
  { key: 'period', label: '帧周期', unit: 'ms' },
  { key: 'frames', label: '采集帧数' },
  { key: 'highvoltage', label: '偏置电压', unit: 'V' },
  { key: 'powerchip', label: 'Power Chip' },
  { key: 'timing', label: '时序模式' },
  { key: 'fwrite', label: '写入文件' },
  { key: 'fname', label: '文件名' },
  { key: 'fpath', label: '存储路径', browse: true, wide: true },
  { key: 'readoutspeed', label: '读出速度' },
]

const editing = reactive<Record<string, string>>({})
const dirty = ref(false)
const confirming = ref(false)
let _syncing = false
let _confirmTimer: ReturnType<typeof setTimeout> | null = null

// 目录浏览
const showBrowser = ref(false)
const browsePath = ref('/')
const browseParent = ref<string | null>(null)
const browseDirs = ref<Array<{ name: string; path: string }>>([])

function openBrowser() {
  showBrowser.value = true
  doBrowse(editing['fpath'] || '/')
}

async function doBrowse(path: string) {
  try {
    const result = await api.browse(path)
    browsePath.value = result.current
    browseParent.value = result.parent
    browseDirs.value = result.dirs
  } catch {
    // path error, ignore
  }
}

function selectDir() {
  editing['fpath'] = browsePath.value
  dirty.value = true
  showBrowser.value = false
}

onUnmounted(() => {
  if (_confirmTimer) clearTimeout(_confirmTimer)
})

watch(() => props.params, (newParams) => {
  if (dirty.value) return
  if (confirming.value) {
    const synced = editableFields.every(f =>
      (newParams[f.key] ?? '') === (editing[f.key] ?? '')
    )
    if (!synced) return
    confirming.value = false
    if (_confirmTimer) { clearTimeout(_confirmTimer); _confirmTimer = null }
  }
  _syncing = true
  for (const field of editableFields) {
    editing[field.key] = newParams[field.key] ?? ''
  }
  nextTick(() => { _syncing = false })
}, { immediate: true, deep: true })

watch(editing, () => {
  if (!_syncing) dirty.value = true
}, { deep: true })

function onConfirm() {
  const changes: Record<string, string> = {}
  for (const field of editableFields) {
    const newVal = editing[field.key] ?? ''
    const oldVal = props.params[field.key] ?? ''
    if (newVal !== oldVal) {
      changes[field.key] = newVal
    }
  }
  if (Object.keys(changes).length > 0) {
    emit('updateParams', changes)
    confirming.value = true
    if (_confirmTimer) clearTimeout(_confirmTimer)
    _confirmTimer = setTimeout(() => { confirming.value = false }, 3000)
  }
  dirty.value = false
}

function onReset() {
  confirming.value = false
  if (_confirmTimer) { clearTimeout(_confirmTimer); _confirmTimer = null }
  _syncing = true
  for (const field of editableFields) {
    editing[field.key] = props.params[field.key] ?? ''
  }
  dirty.value = false
  nextTick(() => { _syncing = false })
}
</script>

<style scoped>
.param-settings {
  background: rgba(255,255,255,0.06);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 14px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.06);
}
.param-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.param-row { display: flex; align-items: center; gap: 8px; }
.param-label { color: #94A3B8; font-size: 12px; font-weight: 500; min-width: 60px; text-align: right; }
.param-unit { color: #64748B; font-size: 11px; min-width: 28px; }
.param-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }

.browser-path { display: flex; gap: 8px; }
.browser-list { max-height: 300px; overflow-y: auto; }
.browser-item { padding: 6px 10px; cursor: pointer; border-radius: 4px; font-size: 13px; }
.browser-item:hover { background: rgba(255,255,255,0.06); }
.browser-item.dir { color: #94A3B8; }
.browser-selected { margin-top: 10px; padding: 6px 10px; background: rgba(255,255,255,0.04);
  border-radius: 4px; font-size: 12px; color: #00d4ff; word-break: break-all; }
</style>
