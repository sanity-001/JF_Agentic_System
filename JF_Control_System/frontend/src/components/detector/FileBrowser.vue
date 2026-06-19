<template>
  <n-modal :show="show" @update:show="$emit('update:show', $event)">
    <n-card title="选择配置文件" style="width:600px" :bordered="false" role="dialog">
      <template #header-extra>
        <n-button size="tiny" @click="$emit('update:show', false)">✕</n-button>
      </template>
      <div class="browser-path">
        <n-input v-model:value="currentPath" size="small" @keyup.enter="browse(currentPath)" />
        <n-button size="small" @click="browse(currentPath)">跳转</n-button>
      </div>
      <n-divider />
      <div class="browser-list">
        <div v-if="parentPath !== null" class="browser-item dir" @click="browse(parentPath)">
          📁 ..
        </div>
        <div v-for="d in dirs" :key="d.path" class="browser-item dir" @click="browse(d.path)">
          📁 {{ d.name }}
        </div>
        <div
          v-for="f in files"
          :key="f.path"
          class="browser-item file"
          :class="{ selected: selectedPath === f.path }"
          @click="selectedPath = f.path"
        >
          {{ f.name.endsWith('.config') ? '⚙' : '📄' }} {{ f.name }}
        </div>
      </div>
      <div v-if="selectedPath" class="browser-selected">
        已选择：{{ selectedPath }}
      </div>
      <template #footer>
        <n-button @click="$emit('update:show', false)">取消</n-button>
        <n-button type="primary" :disabled="!selectedPath" @click="confirm">确定</n-button>
      </template>
    </n-card>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { NModal, NCard, NInput, NButton, NDivider } from 'naive-ui'
import { api } from '@/api/client'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{
  'update:show': [value: boolean]
  select: [path: string]
}>()

const currentPath = ref('/')
const parentPath = ref<string | null>(null)
const dirs = ref<Array<{ name: string; path: string }>>([])
const files = ref<Array<{ name: string; path: string }>>([])
const selectedPath = ref('')

watch(() => props.show, async (val) => {
  if (val) {
    selectedPath.value = ''
    await browse('/')
  }
})

async function browse(path: string) {
  try {
    const result = await api.browse(path)
    currentPath.value = result.current
    parentPath.value = result.parent
    dirs.value = result.dirs
    files.value = result.files
    selectedPath.value = ''
  } catch (e: any) {
    // path error, ignore
  }
}

function confirm() {
  emit('select', selectedPath.value)
  emit('update:show', false)
}
</script>

<style scoped>
.browser-path { display: flex; gap: 8px; }
.browser-list { max-height: 300px; overflow-y: auto; }
.browser-item { padding: 6px 10px; cursor: pointer; border-radius: 4px; font-size: 13px; }
.browser-item:hover { background: #1a3350; }
.browser-item.dir { color: #7eb8da; }
.browser-item.file { color: #c0d0e0; }
.browser-item.selected { background: #152d4a; border: 1px solid #2080f0; color: #fff; }
.browser-selected { margin-top: 10px; padding: 6px 10px; background: #152d4a;
  border-radius: 4px; font-size: 12px; color: #00d4ff; word-break: break-all; }
</style>
