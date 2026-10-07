<script setup>
import { ref } from 'vue'
import AttributionTaskTable from './AttributionTaskTable.vue'
import RegionalFactsTable from './RegionalFactsTable.vue'
import RegionBoard from './RegionBoard.vue'

// [pisuan-custom] W4 归属管理容器：三子页（任务归属/区域事实/模板聚合）。
// v-show 保持子页状态，看板下钻经 ref 调子页 applyRegionFilter 带 region 跳转。
const activeSub = ref('tasks')
const taskTableRef = ref(null)
const factsTableRef = ref(null)

const jumpToTasks = ({ regionKey }) => {
  activeSub.value = 'tasks'
  taskTableRef.value?.applyRegionFilter(regionKey)
}
const jumpToFacts = ({ regionKey }) => {
  activeSub.value = 'facts'
  factsTableRef.value?.applyRegionFilter(regionKey)
}
</script>

<template>
  <div class="attribution-panel">
    <a-tabs v-model:activeKey="activeSub" size="small">
      <a-tab-pane key="tasks" tab="任务归属" />
      <a-tab-pane key="facts" tab="区域事实" />
      <a-tab-pane key="board" tab="模板聚合" />
    </a-tabs>
    <AttributionTaskTable v-show="activeSub === 'tasks'" ref="taskTableRef" />
    <RegionalFactsTable v-show="activeSub === 'facts'" ref="factsTableRef" />
    <RegionBoard
      v-show="activeSub === 'board'"
      @jump-to-tasks="jumpToTasks"
      @jump-to-facts="jumpToFacts"
    />
  </div>
</template>

<style lang="less" scoped>
.attribution-panel {
  padding-top: 4px;
}
</style>
