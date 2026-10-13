<template>
  <div class="stats-canvas">
    <DatasetStatsPanel />
  </div>
</template>

<script setup>
import DatasetStatsPanel from '@/components/eia-data/DatasetStatsPanel.vue'
</script>

<style lang="less" scoped>
/* .stats-panel 自身无内边距（P1 时曾依赖本视图外框）；chrome 画布只管宽，内边距在此补齐（同 .ewp 20/24/40） */
.stats-canvas {
  padding: 20px 24px 40px;
}
</style>
