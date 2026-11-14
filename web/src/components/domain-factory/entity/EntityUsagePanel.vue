<script setup>
import { computed } from 'vue'
import { CircleAlert, Info } from '@lucide/vue'

const props = defineProps({
  usage: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' }
})

const SOURCE_LABELS = [
  ['templates', '段落模板'],
  ['pending_tasks', '待审核任务'],
  ['report_pps', '报告参数'],
  ['facts', '区域事实']
]

const totals = computed(() => props.usage?.totals || {})
const unusedProperties = computed(() => props.usage?.unused_properties || [])
const danglingRefs = computed(() => props.usage?.dangling_refs || [])
const pendingTaskRefs = computed(() => props.usage?.pending_task_refs || [])
const templateRefs = computed(() => (props.usage?.template_refs || []).slice(0, 8))

const hasDetails = computed(() => pendingTaskRefs.value.length > 0 || templateRefs.value.length > 0)
</script>

<template>
  <a-card title="使用情况" class="editor-section usage-panel">
    <a-spin :spinning="loading">
      <a-alert v-if="error" type="warning" show-icon :message="error" />
      <template v-else-if="usage">
        <div class="usage-stats">
          <div v-for="[key, label] in SOURCE_LABELS" :key="key" class="usage-stat">
            <span class="num" :class="{ zero: !totals[key] }">{{ totals[key] || 0 }}</span>
            <span class="label">{{ label }}</span>
          </div>
        </div>

        <div class="usage-note">
          <Info :size="13" />
          <span>
            删除实体或删除属性前先看这里：被引用的属性删掉后，存量模板与待审核任务里的 entity_ref
            会变成悬空字符串，抽取与写作会静默降质。
          </span>
        </div>

        <div v-if="unusedProperties.length" class="usage-warn">
          <CircleAlert :size="13" />
          <span
            >未使用属性 {{ unusedProperties.length }} 个：{{ unusedProperties.join('、') }}</span
          >
        </div>

        <div v-if="danglingRefs.length" class="usage-warn danger">
          <CircleAlert :size="13" />
          <span>悬空引用 {{ danglingRefs.length }} 条：{{ danglingRefs.join('、') }}</span>
        </div>

        <a-collapse v-if="hasDetails" ghost size="small" class="usage-details">
          <a-collapse-panel key="refs" header="最近引用明细">
            <div v-for="task in pendingTaskRefs" :key="`task-${task.id}`" class="ref-line">
              <span class="ref-title">待审核任务 · {{ task.file_name || task.id }}</span>
              <span class="ref-body">{{ task.refs.join('、') }}</span>
            </div>
            <div v-for="item in templateRefs" :key="`tpl-${item.id}`" class="ref-line">
              <span class="ref-title">
                模板 · {{ item.chapter || '未命名章节' }}（{{ item.source_count }} 份来源）
              </span>
              <span class="ref-body">{{ item.refs.join('、') }}</span>
            </div>
          </a-collapse-panel>
        </a-collapse>
      </template>
      <a-empty v-else description="暂无使用情况" />
    </a-spin>
  </a-card>
</template>

<style scoped lang="less">
.usage-panel {
  .usage-stats {
    display: flex;
    gap: 24px;
    margin-bottom: 12px;

    .usage-stat {
      display: flex;
      flex-direction: column;
      gap: 2px;

      .num {
        font-size: 22px;
        font-weight: 600;
        line-height: 1.2;
        color: var(--gray-800);

        &.zero {
          color: var(--gray-400);
        }
      }

      .label {
        font-size: 12px;
        color: var(--gray-500);
      }
    }
  }

  .usage-note,
  .usage-warn {
    display: flex;
    align-items: flex-start;
    gap: 6px;
    margin-bottom: 8px;
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 12px;
    line-height: 1.7;
  }

  .usage-note {
    background: var(--gray-50);
    color: var(--gray-600);
  }

  .usage-warn {
    background: var(--color-warning-50);
    color: var(--gray-700);

    &.danger {
      background: var(--color-error-50);
    }
  }

  .usage-details {
    margin-top: 4px;

    .ref-line {
      display: flex;
      flex-direction: column;
      gap: 2px;
      padding: 4px 0;
      font-size: 12px;

      & + .ref-line {
        border-top: 1px dashed var(--gray-150);
      }

      .ref-title {
        color: var(--gray-700);
      }

      .ref-body {
        color: var(--gray-500);
        word-break: break-all;
      }
    }
  }
}
</style>
