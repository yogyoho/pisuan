<script setup>
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Plus } from '@lucide/vue'

// 规则数组由父级实体草稿持有：本组件只做增删改，不重新赋值整个数组
const rules = defineModel('rules', { type: Array, default: () => [] })

const props = defineProps({
  // 已有实体的 entity_key 列表，用于提示规则目标是否存在
  entityKeys: { type: Array, default: () => [] }
})

const ruleModalVisible = ref(false)
const editingRuleIndex = ref(-1)
const editingRule = ref(emptyRule())

function emptyRule() {
  return {
    rule_id: '',
    rule_name: '',
    condition_json: '{}',
    actions_json: '[]',
    description: ''
  }
}

const handleAddRule = () => {
  editingRuleIndex.value = -1
  editingRule.value = emptyRule()
  ruleModalVisible.value = true
}

const handleEditRule = (index) => {
  editingRuleIndex.value = index
  const rule = rules.value[index]
  editingRule.value = {
    rule_id: rule.rule_id || '',
    rule_name: rule.rule_name || '',
    condition_json: JSON.stringify(rule.condition || {}, null, 2),
    actions_json: JSON.stringify(rule.actions || [], null, 2),
    description: rule.description || ''
  }
  ruleModalVisible.value = true
}

const handleDeleteRule = (index) => {
  rules.value.splice(index, 1)
}

const handleSaveRule = () => {
  try {
    let condition, actions
    try {
      condition = JSON.parse(editingRule.value.condition_json)
      actions = JSON.parse(editingRule.value.actions_json)
    } catch {
      message.error('JSON格式错误')
      return
    }
    if (!editingRule.value.rule_name) {
      message.error('请填写规则名称')
      return
    }
    if (
      !condition ||
      typeof condition !== 'object' ||
      Array.isArray(condition) ||
      !Object.keys(condition).length
    ) {
      message.error('条件必须是非空对象，如 {"location_relation": "错动线内"}')
      return
    }
    if (!Array.isArray(actions) || actions.length === 0) {
      message.error('动作必须是非空数组')
      return
    }
    for (const action of actions) {
      if (action?.type !== 'create_edge') {
        message.error('动作目前只支持 type=create_edge')
        return
      }
      if (!action.relation || !action.target) {
        message.error('create_edge 需要 relation（关系名）与 target（目标 entity_key）')
        return
      }
      if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(action.relation)) {
        message.error('relation 必须是英文标识（字母开头，可含下划线），如 CONFLICT_WITH')
        return
      }
    }
    const unknownTargets = actions
      .map((action) => action.target)
      .filter((target) => !props.entityKeys.includes(target))
    if (unknownTargets.length) {
      message.warning(`目标实体不存在，将按规则创建占位节点：${unknownTargets.join(', ')}`)
    }
    if (!editingRule.value.rule_id) editingRule.value.rule_id = `rule_${Date.now()}`
    const data = {
      rule_id: editingRule.value.rule_id,
      rule_name: editingRule.value.rule_name,
      condition,
      actions,
      description: editingRule.value.description || ''
    }
    if (editingRuleIndex.value >= 0) {
      rules.value[editingRuleIndex.value] = data
    } else {
      rules.value.push(data)
    }
    ruleModalVisible.value = false
    message.success('规则保存成功')
  } catch (e) {
    console.error('保存规则失败', e)
    message.error('保存规则失败')
  }
}
</script>

<template>
  <a-card title="图谱关系推理规则" class="editor-section">
    <div class="rule-hint">
      规则在文档入库阶段求值：<code>condition</code> 的键是本实体的属性 key，按段落 slot
      值逐项比对； 全部命中后，按 <code>actions</code> 生成
      <code>（段落模板）-[关系]-&gt;（目标实体）</code> 图谱边，<code>target</code> 填目标
      entity_key。
    </div>
    <div v-for="(rule, index) in rules" :key="index" class="rule-item">
      <div class="rule-header">
        <strong>{{ rule.rule_name || `规则 ${index + 1}` }}</strong>
        <a-space>
          <a-button type="link" size="small" @click="handleEditRule(index)">编辑</a-button>
          <a-popconfirm title="删除此规则？" @confirm="handleDeleteRule(index)">
            <a-button type="link" size="small" danger>删除</a-button>
          </a-popconfirm>
        </a-space>
      </div>
      <div class="rule-content">
        <div class="rule-condition">
          <strong>条件：</strong>
          <code>{{ JSON.stringify(rule.condition, null, 2) }}</code>
        </div>
        <div class="rule-actions">
          <strong>动作：</strong>
          <code>{{ JSON.stringify(rule.actions, null, 2) }}</code>
        </div>
      </div>
    </div>
    <a-button type="dashed" block style="margin-top: 16px" @click="handleAddRule">
      <template #icon><Plus :size="14" /></template>
      添加规则
    </a-button>

    <a-modal
      v-model:open="ruleModalVisible"
      title="关系推理规则"
      width="800px"
      @ok="handleSaveRule"
    >
      <a-form :model="editingRule" layout="vertical">
        <a-form-item label="规则名称" required>
          <a-input
            v-model:value="editingRule.rule_name"
            placeholder="例如：错动线内不搬迁冲突检测"
          />
        </a-form-item>
        <a-form-item label="条件表达式 (JSON)" required>
          <a-textarea
            v-model:value="editingRule.condition_json"
            :rows="4"
            placeholder='{"location_relation": "错动线内", "protection_status": "留守"}'
          />
        </a-form-item>
        <a-form-item label="动作列表 (JSON)" required>
          <a-textarea
            v-model:value="editingRule.actions_json"
            :rows="6"
            placeholder='[{"type": "create_edge", "relation": "CONFLICT_WITH", "target": "Project_Entity"}]'
          />
        </a-form-item>
        <a-form-item label="规则描述">
          <a-textarea v-model:value="editingRule.description" :rows="2" placeholder="规则描述" />
        </a-form-item>
      </a-form>
    </a-modal>
  </a-card>
</template>

<style scoped lang="less">
.rule-hint {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 6px;
  background: var(--color-info-50);
  color: var(--gray-700);
  font-size: 12px;
  line-height: 1.7;
  code {
    padding: 1px 4px;
    border-radius: 3px;
    background: var(--gray-100);
  }
}

.rule-item {
  padding: 12px;
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  margin-bottom: 12px;
  .rule-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }
  .rule-content {
    font-size: 12px;
    .rule-condition,
    .rule-actions {
      margin-bottom: 8px;
      code {
        display: block;
        padding: 8px;
        background: var(--gray-100);
        border-radius: 4px;
        margin-top: 4px;
        font-family: 'Courier New', monospace;
      }
    }
  }
}
</style>
