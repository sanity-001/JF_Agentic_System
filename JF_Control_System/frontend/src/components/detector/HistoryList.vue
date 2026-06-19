<template>
  <n-card size="small" class="history-list">
    <template #header>
      <span style="display:flex; align-items:center; gap:6px;">
        <n-icon :component="ListOutline" :size="20" color="#00d4ff" />
        <span style="color: #00d4ff; font-weight: bold;">采集历史</span>
      </span>
    </template>
    <n-data-table
      :columns="columns"
      :data="records"
      :bordered="false"
      size="small"
      virtual-scroll
      max-height="300"
    />
  </n-card>
</template>

<script setup lang="ts">
import { h } from 'vue'
import { NCard, NDataTable, NTag, NTooltip, NIcon } from 'naive-ui'
import { ListOutline } from '@vicons/ionicons5'
import type { DataTableColumns } from 'naive-ui'
import type { HistoryRecord } from '@/types/detector'

defineProps<{ records: HistoryRecord[] }>()

const statusColor: Record<string, any> = {
  success: { type: 'success' },
  failed: { type: 'error' },
  aborted: { type: 'warning' },
}

function parseRawPaths(rawPathsStr?: string): string[] {
  if (!rawPathsStr) return []
  try {
    return JSON.parse(rawPathsStr)
  } catch {
    return []
  }
}

function formatFilename(record: HistoryRecord): string {
  const paths = parseRawPaths(record.raw_paths)
  if (paths.length <= 1) return record.filename || '-'
  const first = paths[0].split('/').pop() || ''
  const last = paths[paths.length - 1].split('/').pop() || ''
  const m = first.match(/^(.+)_d(\d+)_(.+)$/)
  const lm = last.match(/_d(\d+)_/)
  if (m && lm) {
    return `${m[1]}_d[${m[2]}-${lm[1]}]_${m[3]}`
  }
  return record.filename || '-'
}

function filenameTooltip(record: HistoryRecord): string {
  const paths = parseRawPaths(record.raw_paths)
  if (paths.length <= 1) return ''
  return paths.map(p => p.split('/').pop()).join('\n')
}

const columns: DataTableColumns<HistoryRecord> = [
  { title: '#', key: 'id', width: 40 },
  { title: '时间', key: 'timestamp', width: 140 },
  { title: '帧数', key: 'frames', width: 60 },
  { title: '文件名', key: 'filename', width: 170, ellipsis: { tooltip: true },
    render(row) {
      const paths = parseRawPaths(row.raw_paths)
      if (paths.length <= 1) return row.filename || '-'
      return h(NTooltip, { trigger: 'hover' }, {
        trigger: () => h('span', { style: { cursor: 'pointer' } }, formatFilename(row)),
        default: () => h('div', { style: { whiteSpace: 'pre-line', fontSize: '12px' } },
          filenameTooltip(row)),
      })
    }
  },
  { title: '状态', key: 'status', width: 55,
    render(row) {
      return h(NTag, { size: 'tiny', ...(statusColor[row.status] || {}) },
        () => row.status === 'success' ? '成功' :
              row.status === 'failed' ? '失败' : '中止')
    }
  },
  { title: '路径', key: 'fpath', ellipsis: { tooltip: true } },
]
</script>

<style scoped>
.history-list {
  background: rgba(255,255,255,0.06);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 14px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.06);
}
</style>
