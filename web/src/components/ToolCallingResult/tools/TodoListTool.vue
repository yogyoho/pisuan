<template>
  <BaseToolCall :tool-call="toolCall" hide-params>
    <template #header>
      <div class="sep-header">
        <span class="note">任务清单</span>
        <span class="separator" v-if="query">|</span>
        <span class="description">{{ query }}</span>
      </div>
    </template>
    <template #result="{ resultContent }">
      <div class="todo-list-result">
        <div class="todo-list">
          <div
            v-for="(todo, index) in todoListData(resultContent)"
            :key="index"
            class="todo-item"
            :class="{ completed: todo.status === 'completed' }"
          >
            <div class="todo-status">
              <CircleCheck v-if="todo.status === 'completed'" :size="16" class="icon completed" />
              <RefreshCw
                v-else-if="todo.status === 'in_progress'"
                :size="16"
                class="icon in-progress"
              />
              <Clock v-else-if="todo.status === 'pending'" :size="16" class="icon pending" />
              <CircleX v-else-if="todo.status === 'cancelled'" :size="16" class="icon cancelled" />
              <CircleHelp v-else :size="16" class="icon unknown" />
            </div>
            <span class="todo-text" :title="formatTodoNameTitle(todo.content)">
              {{ formatTodoName(todo.content) }}
            </span>
          </div>
        </div>
        <div v-if="todoListData(resultContent).length === 0" class="no-results">
          <p>暂无待办事项</p>
        </div>
      </div>
    </template>
  </BaseToolCall>
</template>

<script setup>
import { computed } from 'vue'
import BaseToolCall from '../BaseToolCall.vue'
import { CircleCheck, CircleHelp, CircleX, Clock, RefreshCw } from '@lucide/vue'
import { parseToolCallArgs } from '../toolRegistry'

const props = defineProps({
  toolCall: {
    type: Object,
    required: true
  }
})

const TODO_NAME_MAX_LENGTH = 20

const formatTodoName = (content) => {
  return Array.from(String(content || ''))
    .slice(0, TODO_NAME_MAX_LENGTH)
    .join('')
}

const formatTodoNameTitle = (content) => String(content || '')

const query = computed(() => {
  // 1. Try to get status from result content (Priority)
  const content = props.toolCall.tool_call_result?.content
  if (content) {
    const list = todoListData(content)
    if (list && list.length > 0) {
      // 1. In Progress
      const inProgress = list.find((item) => item.status === 'in_progress')
      if (inProgress) return `进行中: ${formatTodoName(inProgress.content)}`

      // 2. Pending
      const pending = list.find((item) => item.status === 'pending')
      if (pending) return `待处理: ${formatTodoName(pending.content)}`

      // 3. Last item fallback
      const last = list[list.length - 1]
      return `更新: ${formatTodoName(last.content)}`
    }
  }

  // 2. Fallback to args
  const parsedArgs = parseToolCallArgs(props.toolCall)
  if (typeof parsedArgs === 'object') {
    return parsedArgs.content || parsedArgs.action || parsedArgs.todo || ''
  }
  return ''
})

const parseData = (content) => {
  if (typeof content === 'string') {
    try {
      return JSON.parse(content)
    } catch {
      return content
    }
  }
  return content
}

const todoListData = (content) => {
  if (!content) return []
  const data = parseData(content)

  // 1. Try from parsed data
  if (data && typeof data === 'object') {
    if (Array.isArray(data)) return data
    if (data.todos && Array.isArray(data.todos)) return data.todos
  }

  // 2. Try parsing string if it matches specific pattern
  if (typeof content === 'string') {
    let str = content
    if (str.startsWith('Updated todo list to ')) {
      str = str.replace('Updated todo list to ', '')
    }
    const items = []
    const contentRegex = /'content':\s*'((?:[^'\\]|\\.)*)'/
    const statusRegex = /'status':\s*'((?:[^'\\]|\\.)*)'/
    const dictRegex = /\{.*?\}/g
    const dictMatches = str.match(dictRegex)
    if (dictMatches) {
      for (const dictStr of dictMatches) {
        const contentMatch = dictStr.match(contentRegex)
        const statusMatch = dictStr.match(statusRegex)
        if (contentMatch && statusMatch) {
          items.push({
            content: contentMatch[1].replace(/\\'/g, "'").replace(/\\\\/g, '\\'),
            status: statusMatch[1]
          })
        }
      }
    }
    if (items.length > 0) return items
  }
  return []
}
</script>

<style lang="less" scoped>
@keyframes todo-icon-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.todo-list-result {
  background: var(--gray-0);
  padding: 0px;

  .todo-list {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .todo-item {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 4px 0px;
    // background: var(--gray-10);
    border-radius: 6px;
    // border: 1px solid var(--gray-150);

    .todo-status {
      flex-shrink: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-top: 2px;

      .icon {
        &.completed {
          color: var(--color-success-500);
        }
        &.in-progress {
          color: var(--main-color);
          animation: todo-icon-spin 1s linear infinite;
        }
        &.pending {
          color: var(--color-warning-500);
        }
        &.cancelled {
          color: var(--color-error-500);
        }
        &.unknown {
          color: var(--gray-400);
        }
      }
    }

    .todo-text {
      flex: 1;
      font-size: 14px;
      line-height: 1.5;
      color: var(--gray-1000);
      word-break: break-word;

      .todo-item.completed & {
        color: var(--gray-500);
        text-decoration: line-through;
      }
    }
  }

  .no-results {
    text-align: center;
    color: var(--gray-500);
    padding: 10px 0;
    font-size: 13px;
  }
}
</style>
