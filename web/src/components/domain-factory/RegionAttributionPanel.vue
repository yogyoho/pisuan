<script setup>
import { ref, watch } from 'vue'
import { Rows3 } from '@lucide/vue'
import AttributionTaskTable from './AttributionTaskTable.vue'
import RegionalFactsTable from './RegionalFactsTable.vue'
import KBAttributionTable from './KBAttributionTable.vue'
import RegionBoard from './RegionBoard.vue'

// [pisuan-custom] W4 归属管理容器：四子页（任务归属/KB绑定/区域事实/模板隔离）。
// v-show 保持子页状态，看板下钻经 ref 调子页 applyRegionFilter 带 region 跳转。
const activeSub = ref('tasks')
const taskTableRef = ref(null)
const kbTableRef = ref(null)
const factsTableRef = ref(null)
const boardRef = ref(null)

const jumpToTasks = ({ regionKey }) => {
  activeSub.value = 'tasks'
  taskTableRef.value?.applyRegionFilter(regionKey)
}
const jumpToFacts = ({ regionKey }) => {
  activeSub.value = 'facts'
  factsTableRef.value?.applyRegionFilter(regionKey)
}

// 子页切换时刷新目标子页（改判级联后防止 facts/board 显示陈旧数据）
watch(activeSub, (sub) => {
  if (sub === 'facts') factsTableRef.value?.refresh()
  else if (sub === 'bindings') kbTableRef.value?.refresh()
  else if (sub === 'board') boardRef.value?.refresh()
})
</script>

<template>
  <div class="ewp attribution-panel">
    <!-- 页头（EIA page-head 配方）：四子页 seg 分段器收编进 ph-actions（SectionsPanel 同款） -->
    <div class="page-head">
      <div class="ph-icon">
        <Rows3 :size="18" />
      </div>
      <div>
        <h2>归属管理</h2>
        <div class="ph-sub">任务归属 · KB 绑定诊断 · 区域事实 · 模板隔离看板</div>
      </div>
      <div class="ph-actions">
        <div class="seg">
          <button :class="{ on: activeSub === 'tasks' }" @click="activeSub = 'tasks'">任务归属</button>
          <button :class="{ on: activeSub === 'bindings' }" @click="activeSub = 'bindings'">KB绑定</button>
          <button :class="{ on: activeSub === 'facts' }" @click="activeSub = 'facts'">区域事实</button>
          <button :class="{ on: activeSub === 'board' }" @click="activeSub = 'board'">模板隔离</button>
        </div>
      </div>
    </div>
    <AttributionTaskTable v-show="activeSub === 'tasks'" ref="taskTableRef" />
    <KBAttributionTable v-show="activeSub === 'bindings'" ref="kbTableRef" />
    <RegionalFactsTable v-show="activeSub === 'facts'" ref="factsTableRef" />
    <RegionBoard
      v-show="activeSub === 'board'"
      ref="boardRef"
      @jump-to-tasks="jumpToTasks"
      @jump-to-facts="jumpToFacts"
    />
  </div>
</template>

<style lang="less" scoped>
/* 公共配方（page-head/seg/card）在 factory-core/factory-ui.less，本页无额外形状 */
</style>

<style lang="less" src="../factory-core/factory-ui.less"></style>
