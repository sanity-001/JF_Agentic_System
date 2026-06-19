<template>
  <n-card size="small" class="acq-control">
    <template #header>
      <span style="display:flex; align-items:center; gap:6px;">
        <n-icon :component="PlayOutline" :size="20" color="#00d4ff" />
        <span style="color: #00d4ff; font-weight: bold;">采集控制</span>
      </span>
    </template>
    <div class="mode-toggle" v-if="!progress.acquiring">
      <n-radio-group v-model:value="localMode" name="acq-mode">
        <n-radio-button value="baseline">基线采集</n-radio-button>
        <n-radio-button value="signal">上光采集</n-radio-button>
      </n-radio-group>
    </div>
    <div class="acq-actions">
      <n-button
        type="primary"
        size="large"
        :disabled="!canStart"
        :loading="progress.acquiring"
        @click="$emit('start', localMode)"
      >
        <template #icon><n-icon :component="PlayOutline" /></template>
        开始采集
      </n-button>
      <n-button
        type="error"
        size="large"
        :disabled="!progress.acquiring"
        @click="$emit('stop')"
      >
        <template #icon><n-icon :component="StopOutline" /></template>
        停止
      </n-button>
      <n-tag v-if="error" type="error">{{ error }}</n-tag>
    </div>
    <n-progress
      v-if="progress.acquiring"
      type="line"
      :percentage="progress.percentage"
      :indicator-placement="'inside'"
      color="#00d4ff"
      rail-color="#152d4a"
      processing
      style="margin-top: 16px"
    />
    <div class="acq-info" v-if="progress.acquiring">
      <n-tag type="info" round>采集中...</n-tag>
      <span>帧数: {{ params.frames }}</span>
      <span>{{ progress.percentage }}%</span>
    </div>
    <div v-else class="acq-info idle">
      <n-tag round>就绪</n-tag>
    </div>
  </n-card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NCard, NButton, NIcon, NProgress, NTag, NRadioGroup, NRadioButton } from 'naive-ui'
import { PlayOutline, StopOutline } from '@vicons/ionicons5'
import type { AcquisitionProgress, DetectorParams, DetectorStatus } from '@/types/detector'

const props = defineProps<{
  progress: AcquisitionProgress
  params: DetectorParams
  status: DetectorStatus
  error: string | null
  acqMode: 'baseline' | 'signal'
  hasBaseline: boolean
}>()

defineEmits<{ start: [mode: 'baseline' | 'signal']; stop: [] }>()

const localMode = ref<'baseline' | 'signal'>(props.acqMode)
watch(() => props.acqMode, (v) => { localMode.value = v })

const canStart = computed(() =>
  props.status.connected && !props.progress.acquiring
)
</script>

<style scoped>
.acq-control {
  background: rgba(255,255,255,0.06);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 14px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.06);
}
.mode-toggle { margin-bottom: 16px; }
.acq-actions { display: flex; gap: 16px; align-items: center; }
.acq-info { display: flex; gap: 16px; margin-top: 14px; color: #94A3B8; font-size: 13px; }
.acq-info.idle { color: #64748B; }
</style>
