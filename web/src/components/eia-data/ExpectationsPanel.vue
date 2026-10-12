<template>
  <div class="expectations-panel">
    <!-- 取数路径图例：source_hint 词表 + 各路径数据族计数 -->
    <div class="card">
      <div class="toolbar">
        <span class="toolbar-label">取数路径图例</span>
        <span
          v-for="v in vocabulary"
          :key="v.name"
          class="src-chip"
          :class="{ hl: v.count > 0 }"
          :title="v.name"
        >
          {{ v.name }} <b>{{ v.count }}</b>
        </span>
      </div>
    </div>

    <!-- 分章备料：行展开族明细 -->
    <div class="card">
      <div class="card-hd">
        <h3>分章备料</h3>
        <span class="hd-sub">{{ perChapter.length }} 章 · {{ totalFamilies }} 族</span>
      </div>

      <div v-for="ch in perChapter" :key="ch.chapter" class="ch-row">
        <div class="ch-hd" :class="{ open: expanded.has(ch.chapter) }" @click="toggle(ch.chapter)">
          <ChevronRight class="chev" :size="14" />
          <h4>{{ ch.chapter }} · {{ ch.title }}</h4>
          <span class="fam-total">{{ ch.data_families.length }} 族</span>
        </div>
        <div v-if="expanded.has(ch.chapter)" class="ch-bd">
          <div v-for="fam in ch.data_families" :key="fam.family" class="fam-line">
            <span class="fl-name mono">{{ fam.family }}</span>
            <span class="src-chip" :class="{ hl: !!fam.source_hint }">{{
              fam.source_hint || '未指明'
            }}</span>
            <ul class="fl-items">
              <li v-for="(item, i) in fam.items" :key="i">{{ item }}</li>
            </ul>
          </div>
        </div>
      </div>

      <div v-if="!perChapter.length && !loading" class="empty-state">
        <a-empty description="备料清单为空" />
      </div>
    </div>

    <div class="note-bar">
      <Info :size="14" />
      <span>
        备料「对账」发生在写作时（写手按 source_hint
        取数）；本页只呈现基线，不提供编辑——基线调整属工程侧 pipeline。
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { ChevronRight, Info } from '@lucide/vue'
import { eiaDataApi } from '@/apis/eia_data_api'

const loading = ref(false)
const perChapter = ref([])
const vocabulary = ref([])
const expanded = ref(new Set())

const totalFamilies = computed(() =>
  perChapter.value.reduce((acc, ch) => acc + ch.data_families.length, 0)
)

const toggle = (chapter) => {
  const next = new Set(expanded.value)
  if (next.has(chapter)) {
    next.delete(chapter)
  } else {
    next.add(chapter)
  }
  expanded.value = next
}

const fetchData = async () => {
  loading.value = true
  try {
    const out = await eiaDataApi.getDataExpectations()
    perChapter.value = out.per_chapter
    // 词表计数：source_hint 在各数据族上的出现次数（未在 hint 中出现的词也列出，计数 0）
    const counts = {}
    for (const hint of out.source_hint_vocabulary) counts[hint] = 0
    for (const ch of perChapter.value) {
      for (const fam of ch.data_families) {
        if (fam.source_hint && fam.source_hint in counts) counts[fam.source_hint] += 1
      }
    }
    vocabulary.value = Object.entries(counts).map(([name, count]) => ({ name, count }))
    // 默认展开第一章，页面不留白
    if (perChapter.value.length) expanded.value = new Set([perChapter.value[0].chapter])
  } catch (e) {
    message.error(`获取备料清单失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
</script>

<style lang="less" scoped>
.expectations-panel {
  --hairline: var(--gray-200);
}

.mono {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
}

.card {
  background: var(--gray-0);
  border: 1px solid var(--hairline);
  border-radius: 8px;
  margin-bottom: 12px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  flex-wrap: wrap;
}

.toolbar-label {
  font-size: 12px;
  color: var(--gray-500);
}

.card-hd {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--hairline);

  h3 {
    font-size: 14px;
    font-weight: 600;
    margin: 0;
  }

  .hd-sub {
    font-size: 12px;
    color: var(--gray-500);
  }
}

.src-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 22px;
  padding: 0 9px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid var(--hairline);
  background: var(--gray-0);
  color: var(--gray-600);
  white-space: nowrap;

  b {
    font-size: 11px;
    color: var(--main-600);
    font-variant-numeric: tabular-nums;
  }

  &.hl {
    border-color: var(--main-300, var(--main-500));
    background: var(--main-0);
  }
}

.ch-row {
  border-bottom: 1px solid var(--hairline);

  &:last-child {
    border-bottom: none;
  }
}

.ch-hd {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 16px;
  cursor: pointer;

  &:hover {
    background: var(--gray-50);
  }

  .chev {
    color: var(--gray-400);
    transition: transform 0.15s;
  }

  &.open .chev {
    transform: rotate(90deg);
  }

  h4 {
    font-size: 13px;
    font-weight: 600;
    margin: 0;
  }

  .fam-total {
    font-size: 12px;
    color: var(--gray-500);
  }
}

.ch-bd {
  padding: 2px 16px 12px 40px;
}

.fam-line {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 7px 0;

  & + .fam-line {
    border-top: 1px dashed var(--gray-100);
  }

  .fl-name {
    flex: none;
    width: 150px;
    color: var(--gray-800);
  }

  .fl-items {
    margin: 0;
    padding-left: 16px;
    font-size: 12px;
    color: var(--gray-500);
    line-height: 1.7;

    li + li {
      margin-top: 2px;
    }
  }
}

.empty-state {
  padding: 32px 0;
}

.note-bar {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  background: var(--main-0);
  border-radius: 6px;
  padding: 9px 12px;
  font-size: 12px;
  color: var(--gray-600);

  svg {
    margin-top: 2px;
    flex: none;
    color: var(--main-600);
  }
}
</style>
