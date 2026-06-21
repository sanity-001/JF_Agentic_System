<script setup lang="ts">
import { darkTheme, NConfigProvider, NMessageProvider, NTabs, NTabPane, NIcon } from 'naive-ui'
import { ref } from 'vue'
import { HardwareChipOutline, BarChartOutline } from '@vicons/ionicons5'
import ConnectionBar from './components/ConnectionBar.vue'
import ControlView from './components/ControlView.vue'
import ProcessingView from './components/ProcessingView.vue'

const activeTab = ref('control')

const themeOverrides = {
  common: {
    primaryColor: '#00d4ff',
    primaryColorHover: '#33ddff',
    primaryColorPressed: '#00aacc',
    bodyColor: '#020617',
    cardColor: 'transparent',
    inputColor: 'rgba(255,255,255,0.08)',
    borderColor: 'rgba(255,255,255,0.12)',
    fontFamily: "'Fira Sans', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    fontFamilyMono: "'Fira Code', monospace",
  },
}
</script>

<template>
  <n-config-provider :theme="darkTheme" :theme-overrides="themeOverrides">
    <n-message-provider>
      <div class="app-shell">
        <ConnectionBar />
        <div class="tab-bar">
          <n-tabs
            v-model:value="activeTab"
            type="line"
            animated
            size="medium"
          >
            <n-tab-pane name="control">
              <template #tab>
                <span style="display:flex; align-items:center; gap:6px;">
                  <n-icon :component="HardwareChipOutline" :size="18" />
                  <span>实验控制</span>
                </span>
              </template>
            </n-tab-pane>
            <n-tab-pane name="processing">
              <template #tab>
                <span style="display:flex; align-items:center; gap:6px;">
                  <n-icon :component="BarChartOutline" :size="18" />
                  <span>数据分析</span>
                </span>
              </template>
            </n-tab-pane>
          </n-tabs>
        </div>
        <div class="tab-content">
          <KeepAlive>
            <ControlView v-if="activeTab === 'control'" />
            <ProcessingView v-if="activeTab === 'processing'" />
          </KeepAlive>
        </div>
      </div>
    </n-message-provider>
  </n-config-provider>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap');

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  background: linear-gradient(135deg, #020617 0%, #051030 50%, #020617 100%);
  font-family: 'Fira Sans', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  overflow: hidden;
  color: #F8FAFC;
}

.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #020617;
}

.tab-bar {
  background: rgba(2,6,23,0.8);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border-bottom: 1px solid rgba(255,255,255,0.10);
  padding: 0 16px;
  flex-shrink: 0;
}

.tab-content {
  flex: 1;
  overflow: hidden;
  min-height: 0;
}
</style>
