<template>
  <div class="ewp expectations-panel">
    <!-- 页头（原型 s4：ClipboardList + data_expectations 基线说明） -->
    <div class="page-head">
      <button class="back-btn" aria-label="返回数据工厂总览" @click="goOverview">
        <ArrowLeft :size="16" />
      </button>
      <div class="ph-icon">
        <ClipboardList :size="18" />
      </div>
      <div>
        <h2>备料清单</h2>
        <div class="ph-sub">
          data_expectations · {{ perChapter.length }} 章应备数据族与取数路径基线（管线生成，只读）
        </div>
      </div>
    </div>

    <!-- 取数路径图例：source_hint 词表 + 各路径数据族计数 -->
    <div class="card" style="margin-bottom: 12px">
      <div class="toolbar">
        <span class="toolbar-label">取数路径图例</span>
        <span
          v-for="v in vocabulary"
          :key="v.name"
          class="src-chip"
          :class="{ hl: v.count > 0 }"
          :title="v.desc"
        >
          {{ v.name }} <b>{{ v.count }}</b>
        </span>
      </div>
    </div>

    <!-- 分章备料：点行展开族明细 -->
    <div class="card">
      <div class="card-hd">
        <h3>分章备料</h3>
        <span class="hd-sub" :title="stageScope"
          >{{ perChapter.length }} 章 · {{ totalFamilies }} 族</span
        >
      </div>

      <div v-for="ch in perChapter" :key="ch.chapter" class="ch-row">
        <div class="ch-hd" :class="{ open: expanded.has(ch.chapter) }" @click="toggle(ch.chapter)">
          <ChevronRight class="chev" :size="14" />
          <h4>{{ ch.chapter }} · {{ ch.title }}</h4>
          <span class="fam-total">{{ ch.data_families.length }} 族</span>
          <span
            class="meter"
            :class="{ low: chStats(ch).pct < 40 }"
            :title="`已具备取数路径 ${chStats(ch).hinted}/${ch.data_families.length}`"
            ><i :style="{ width: chStats(ch).pct + '%' }"></i
          ></span>
          <span class="num ch-ratio">{{ chStats(ch).hinted }}/{{ ch.data_families.length }}</span>
        </div>
        <div v-if="expanded.has(ch.chapter)" class="ch-bd">
          <div v-for="fam in ch.data_families" :key="fam.family" class="fam-line">
            <span class="fl-name" :title="fam.family">{{ fam.family }}</span>
            <!-- source_hint 为「a + b」复合串，拆成多枚路径 chip -->
            <template v-if="fam.source_hint">
              <span
                v-for="h in fam.source_hint.split('+').map((s) => s.trim())"
                :key="h"
                class="src-chip hl"
                >{{ h }}</span
              >
            </template>
            <span v-else class="src-chip">未指明</span>
            <span class="fl-note" :title="fam.items.join('、')">{{ fam.items.join('、') }}</span>
          </div>
        </div>
      </div>

      <div v-if="!perChapter.length && !loading" class="empty-state">
        <a-empty description="备料清单为空" />
      </div>

      <div class="tbl-foot">
        共 {{ perChapter.length }} 章 · 点行展开族明细 · 进度条 = 已具备明确取数路径的族占比
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
import { ArrowLeft, ChevronRight, ClipboardList, Info } from '@lucide/vue'
import { useRouter } from 'vue-router'
import { eiaDataApi } from '@/apis/eia_data_api'

const router = useRouter()
const loading = ref(false)
const perChapter = ref([])
const vocabulary = ref([])
const stageScope = ref('')
const expanded = ref(new Set())

const goOverview = () => router.push('/domain-factory/eia-data')

const totalFamilies = computed(() =>
  perChapter.value.reduce((acc, ch) => acc + ch.data_families.length, 0)
)

// 章 meter 口径：source_hint 非空族数 / 总族数
const chStats = (ch) => {
  const total = ch.data_families.length
  const hinted = ch.data_families.filter((f) => !!f.source_hint).length
  return { hinted, total, pct: total ? Math.round((hinted / total) * 100) : 0 }
}

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
    stageScope.value = out.stage_scope
    // 词表为 {hint: 说明} 对象；计数按 source_hint 复合串（「a + b」）的包含关系统计
    const vocab = Object.entries(out.source_hint_vocabulary ?? {}).map(([name, desc]) => ({
      name,
      desc,
      count: 0
    }))
    for (const ch of perChapter.value) {
      for (const fam of ch.data_families) {
        if (!fam.source_hint) continue
        for (const v of vocab) {
          if (fam.source_hint.includes(v.name)) v.count += 1
        }
      }
    }
    vocabulary.value = vocab
    // 默认展开首个有数据族的章，页面不留白
    const first = perChapter.value.find((ch) => ch.data_families.length)
    if (first) expanded.value = new Set([first.chapter])
  } catch (e) {
    message.error(`获取备料清单失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
</script>

<style lang="less" src="./factory-ui.less"></style>
