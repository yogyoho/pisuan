<template>
  <!-- 自绘下拉（原型语汇：触发器即 .inp 配方，菜单选中态同 nav-item.on；bug-438 原生 select 观感不达标） -->
  <div ref="wrap" class="fselect" :class="{ open }">
    <button type="button" class="fs-trigger" @click="open = !open">
      <span class="fs-label">{{ currentLabel }}</span>
      <ChevronDown :size="14" class="fs-caret" />
    </button>
    <div v-if="open" class="fs-menu">
      <button
        v-for="opt in options"
        :key="opt.value"
        type="button"
        class="fs-opt"
        :class="{ on: opt.value === modelValue }"
        @click="pick(opt.value)"
      >
        <span>{{ opt.label }}</span>
        <Check v-if="opt.value === modelValue" :size="14" />
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Check, ChevronDown } from '@lucide/vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  options: { type: Array, required: true } // [{ value, label }]
})
const emit = defineEmits(['update:modelValue', 'change'])

const open = ref(false)
const wrap = ref(null)

const currentLabel = computed(
  () => props.options.find((o) => o.value === props.modelValue)?.label ?? ''
)

const pick = (value) => {
  open.value = false
  if (value === props.modelValue) return
  emit('update:modelValue', value)
  emit('change', value)
}

const onDocClick = (e) => {
  if (open.value && wrap.value && !wrap.value.contains(e.target)) open.value = false
}
const onKey = (e) => {
  if (e.key === 'Escape') open.value = false
}
onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKey)
})
</script>

<style lang="less" scoped>
.fselect {
  position: relative;
}

.fselect.open .fs-trigger,
.fs-trigger:hover {
  border-color: var(--main-500);
}

.fselect.open .fs-trigger {
  box-shadow: 0 0 0 2px var(--main-50);
}

.fs-trigger {
  appearance: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  width: 100%;
  height: 30px;
  padding: 0 8px 0 10px;
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  background: var(--gray-0);
  font-size: 13px;
  color: var(--color-text);
  cursor: pointer;
  transition:
    border-color 0.15s,
    box-shadow 0.15s;
}

.fs-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fs-caret {
  flex: none;
  color: var(--color-text-tertiary);
  transition: transform 0.15s;
}

.fselect.open .fs-caret {
  transform: rotate(180deg);
}

.fs-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  z-index: 30;
  max-height: 264px;
  overflow-y: auto;
  padding: 4px;
  background: var(--gray-0);
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.fs-opt {
  appearance: none;
  background: none;
  border: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  width: 100%;
  padding: 6px 8px;
  border-radius: 5px;
  font-size: 13px;
  text-align: left;
  color: var(--color-text);
  cursor: pointer;

  &:hover {
    background: var(--gray-50);
  }

  &.on {
    background: var(--main-50);
    color: var(--main-600);
    font-weight: 500;
  }
}

/* 暗色：聚焦环/选中底提一档（原型 .proto-dark 同款换档） */
:root.dark .fselect.open .fs-trigger {
  box-shadow: 0 0 0 2px var(--main-100);
}

:root.dark .fs-opt.on {
  background: var(--main-100);
}
</style>
