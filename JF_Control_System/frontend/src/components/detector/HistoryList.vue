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
      max-height="400"
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

function formatFilename(rawPathsStr?: string): string {
  const paths: string[] = rawPathsStr ? (() => { try { return JSON.parse(rawPathsStr) } catch { return [] } })() : []
  if (paths.length === 0) return '-'
  return paths.join(', ')
}

const columns: DataTableColumns<HistoryRecord> = [
  { title: '#', key: 'id', width: 40 },
  { title: '时间', key: 'timestamp', width: 150 },
  { title: '帧数', key: 'frames', width: 60 },
  { title: '文件名', key: 'raw_paths', ellipsis: { tooltip: true },
    render(row) { return formatFilename(row.raw_paths) }
  },
  { title: '状态', key: 'status', width: 55,
    render(row) {
      return h(NTag, { size: 'tiny', ...(statusColor[row.status] || {}) },
        () => row.status === 'success' ? '成功' :
              row.status === 'failed' ? '失败' : '中止')
    }
  },
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
