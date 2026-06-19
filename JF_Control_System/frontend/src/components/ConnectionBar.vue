<script setup lang="ts">
import { useWebSocket } from '../composables/useWebSocket'

const { wsConnected } = useWebSocket()
</script>

<template>
  <div class="connection-bar">
    <div class="brand">
      <span class="brand-dot" :style="{ background: wsConnected ? '#00d4ff' : '#557799' }"></span>
      <span class="brand-text">JUNGFRAU Control System</span>
    </div>
  </div>
</template>

<style scoped>
.connection-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 20px;
  background: rgba(2,6,23,0.8);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border-bottom: 1px solid rgba(255,255,255,0.10);
  flex-shrink: 0;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  box-shadow: 0 0 8px #00d4ff;
  transition: background 0.3s;
}
.brand-text {
  color: #F8FAFC;
  font-weight: 600;
  font-size: 15px;
}
</style>
