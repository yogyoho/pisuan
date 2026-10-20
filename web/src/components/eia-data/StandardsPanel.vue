<template>
  <div class="ewp standards-panel">
    <!-- 页头（原型 s11：盾形图标 + 待导出 pill + 双通道导出） -->
    <div class="page-head">
      <div class="ph-icon">
        <ShieldCheck :size="18" />
      </div>
      <div>
        <h2>标准与限值库</h2>
        <div class="ph-sub">
          standards_index 核实闭环 + 限值查找表专家录入（写手引用合法性与取值的权威来源）
        </div>
      </div>
      <div class="ph-actions">
        <span v-if="dbTableCount" class="pill pill-orange"
          ><span class="dot dot-warn"></span>{{ dbTableCount }} 表待导出</span
        >
        <template v-if="userStore.isAdmin">
          <button class="btn btn-sec btn-sm" :disabled="exporting" @click="onExport">
            {{ exporting ? '导出中…' : '导出核实结果' }}
          </button>
          <button
            class="btn btn-pri btn-sm"
            :disabled="exporting || !dbTableCount"
            @click="exportLimits"
          >
            {{ exporting ? '导出中…' : '导出限值行' }}
          </button>
        </template>
      </div>
    </div>

    <!-- 门 1 体检卡（P2-3 只读）：规则规格 + 注册表自检（code 对 allowed_patterns），不伪造违规明细 -->
    <div v-if="gate1" class="gate1-card">
      <div class="gate1-hd">
        <div class="gate1-badge"><ShieldCheck :size="16" /></div>
        <div>
          <h3>门 1 · 标准号体检</h3>
          <div class="hd-sub" :title="gate1.desc">
            gate1_code_checks · 写作前标准引用合法性规则与当前命中
          </div>
        </div>
        <div class="hd-right">
          <span v-if="gate1.registry_check.violations.length" class="pill-warn-tag">
            {{ gate1.registry_check.violations.length }} 项待修正
          </span>
          <span v-else class="pill-ok-tag">全部通过</span>
        </div>
      </div>
      <div class="gate1-metrics">
        <div class="gate1-m">
          <span class="v num">{{ gate1.registry_check.total }}</span>
          <span class="l">在册标准</span>
          <span class="h">standards[].code</span>
        </div>
        <div class="gate1-m">
          <span class="v num">{{ gate1.allowed_patterns.length }}</span>
          <span class="l">引用模式</span>
          <span class="h">allowed_patterns</span>
        </div>
        <div class="gate1-m">
          <span class="v num" :class="gate1.registry_check.violations.length ? 'hot' : 'zero'">
            {{ gate1.registry_check.violations.length }}
          </span>
          <span class="l">命不上模式</span>
          <span class="h">需人工核对登记</span>
        </div>
      </div>
      <div class="gate1-body">
        <div class="gate1-patterns">
          <span class="pl-label">引用模式</span>
          <code v-for="p in gate1.allowed_patterns" :key="p" class="k">{{ p }}</code>
        </div>
        <ol class="gate1-rules">
          <li v-for="(r, i) in gate1.rules" :key="i">{{ r }}</li>
        </ol>
        <template v-if="gate1.registry_check.violations.length">
          <div class="gate1-viol">
            <span class="pl-label">命不上模式的在册编号</span>
            <code v-for="c in gate1.registry_check.violations" :key="c" class="k viol">{{
              c
            }}</code>
          </div>
        </template>
      </div>
    </div>

    <a-spin v-if="loading && !items.length" style="display: block; margin: 48px auto" />
    <template v-else>
      <!-- 标准核实清单（原型 s11：card-hd 内 seg + 搜索，自绘表） -->
      <div class="card">
        <div class="card-hd">
          <h3>标准核实清单</h3>
          <span class="hd-sub"
            >{{ items.length }} 条 · 待核实 {{ todoCount }} · 已核实 {{ doneCount }}</span
          >
          <div class="hd-right">
            <div class="seg">
              <button :class="{ on: filters.state === '' }" @click="filters.state = ''">
                全部 {{ items.length }}
              </button>
              <button :class="{ on: filters.state === 'todo' }" @click="filters.state = 'todo'">
                待核实 {{ todoCount }}
              </button>
              <button :class="{ on: filters.state === 'done' }" @click="filters.state = 'done'">
                已核实 {{ doneCount }}
              </button>
            </div>
            <input
              v-model="filters.q"
              class="inp"
              style="width: 180px"
              placeholder="搜索标准号 / 名称…"
            />
          </div>
        </div>
        <table class="tbl" :style="loading && items.length ? 'opacity: .55' : ''">
          <thead>
            <tr>
              <th style="width: 30px"></th>
              <th style="width: 15%">标准号</th>
              <th style="width: 26%">名称</th>
              <th style="width: 9%">分级</th>
              <th style="width: 8%">语料引用</th>
              <th style="width: 10%">核实状态</th>
              <th style="width: 19%">核实人 / 备注</th>
              <th class="r" style="width: 13%; padding-right: 20px">操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="record in pagedItems" :key="record.code">
              <tr>
                <td>
                  <button
                    class="expander"
                    aria-label="展开关联限值表"
                    @click="toggleTables(record)"
                  >
                    <ChevronRight
                      :size="14"
                      :class="{ open: expandedTableCodes.includes(record.code) }"
                    />
                  </button>
                </td>
                <td class="mono">
                  {{ record.code }}
                  <span
                    v-if="record.review.action && record.needs_verification"
                    class="pill pill-orange pill-sm"
                    style="margin-left: 4px"
                    title="已裁决，导出物化后转「已核实」"
                    >待导出</span
                  >
                </td>
                <td>
                  <div class="title-cell">
                    <span
                      class="title-main"
                      :title="`章节：${record.chapters || '—'} · 语料引用 ${record.cited_count} 份`"
                      >{{ record.title }}</span
                    >
                    <span v-if="record.role" class="title-role" :title="record.role">{{
                      record.role
                    }}</span>
                  </div>
                </td>
                <td>
                  <span
                    class="tier"
                    :class="tierBadge(record.tier)"
                    :title="tierLabel(record.tier)"
                    >{{ tierLabel(record.tier) }}</span
                  >
                </td>
                <td class="num">
                  <button
                    class="btn btn-txt btn-sm"
                    title="点击查看语料引用清单"
                    @click="openCitations(record)"
                  >
                    {{ record.cited_count }} 份
                  </button>
                </td>
                <td>
                  <span v-if="!record.needs_verification" class="pill pill-ok">已核实</span>
                  <span v-else-if="record.review.action" class="pill pill-orange"
                    >已裁决·待导出</span
                  >
                  <span v-else class="pill pill-warn">待核实</span>
                </td>
                <td>
                  <div v-if="record.review.action" class="review-cell">
                    <span class="review-by">{{ record.review.decided_by }}</span>
                    <small
                      v-if="record.review.note"
                      class="review-note"
                      :title="record.review.note"
                      >{{ record.review.note }}</small
                    >
                  </div>
                  <span v-else class="muted">—</span>
                </td>
                <td class="r" style="padding-right: 20px">
                  <button class="btn btn-txt btn-sm" @click="openReview(record)">
                    {{ record.needs_verification || !record.review.action ? '核实' : '查看' }}
                  </button>
                  <button class="btn btn-txt btn-sm" @click="openKbQuery(record)">KB 查询</button>
                </td>
              </tr>
              <tr v-if="expandedTableCodes.includes(record.code)" class="sub-row">
                <td :colspan="STANDARDS_TABLE_COLS">
                  <div v-if="!tablesOf(record.code).length" class="cite-line muted">
                    该标准无关联限值表（code_ref 未挂表）
                  </div>
                  <div v-else class="src-list">
                    <div v-for="[name, t] in tablesOf(record.code)" :key="name" class="cite-line">
                      <FileText :size="13" />
                      <span class="mono">{{ name }}</span>
                      <span class="cite-as" :title="t.note || t.desc">{{ t.desc }}</span>
                      <span class="pill pill-gray s-stage num">{{ (t.rows || []).length }} 行</span>
                      <span
                        class="pill s-stage"
                        :class="t.source === 'db' ? 'pill-orange' : 'pill-gray'"
                        :title="
                          t.source === 'db'
                            ? 'DB 录入为导出真源，导出物化后写手可见'
                            : t.source === 'db_registry'
                              ? '新表已入册，待录入限值行'
                              : '文件锚点态，导出前须先录入核实'
                        "
                        >{{
                          t.source === 'db'
                            ? 'DB · 待导出'
                            : t.source === 'db_registry'
                              ? '已入册'
                              : '文件态'
                        }}</span
                      >
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
        <div v-if="!filteredItems.length" class="empty-state">
          <a-empty :description="emptyDesc">
            <button v-if="isFiltered" class="btn btn-sec btn-sm" @click="clearFilters">
              清除筛选
            </button>
          </a-empty>
        </div>
        <div class="tbl-foot">
          <span
            >共 {{ filteredItems.length }} 条 · 核实 =
            已对照标准原文确认编号/年份/名称；导出物化翻转注册表两标志</span
          >
          <span v-if="pageCount > 1" class="pager">
            <a-select
              :value="pageSize"
              size="small"
              class="size-select"
              popup-class-name="pager-size-dd"
              :options="sizeOptions"
              @change="setPageSize"
            />
            <button class="btn btn-sm" :disabled="page <= 1" @click="page--">上一页</button>
            <span class="num">{{ page }} / {{ pageCount }}</span>
            <button class="btn btn-sm" :disabled="page >= pageCount" @click="page++">下一页</button>
          </span>
        </div>
      </div>

      <!-- 两 tab 容器（原型 2026-10-20：已提取指标核验台 / 缺源候选漏斗） -->
      <div class="tabbar">
        <button
          class="tab"
          :class="{ on: activeTab === 'indicators' }"
          @click="switchTab('indicators')"
        >
          <SquareCheckBig :size="15" />
          已提取指标
        </button>
        <button
          class="tab"
          :class="{ on: activeTab === 'candidates' }"
          @click="switchTab('candidates')"
        >
          <AlertTriangle :size="15" />
          缺源候选
          <span v-if="candidates.length" class="badge num">{{ candidates.length }}</span>
        </button>
      </div>

      <!-- tab1 已提取指标：KB enrich 行按 标准号 → 表单元 分组，表单元级人工核验 -->
      <template v-if="activeTab === 'indicators'">
        <a-spin
          v-if="indicatorsLoading && !kbDocGroups.length"
          style="display: block; margin: 48px auto"
        />
        <template v-else>
          <div class="card">
            <div class="card-hd">
              <h3>已提取指标核验台</h3>
              <span class="hd-sub"
                >KB enrich 产出的权威限值行 · 按 标准号 → 表单元 分组 · 表单元级人工核验</span
              >
              <div class="hd-right">
                <span class="pill pill-gray num">{{ indicatorsSummary }}</span>
                <span class="pill pill-gray">重跑 enrich 后该标准核验态自动失效（重跑即重验）</span>
              </div>
            </div>

            <div
              v-for="doc in kbDocGroups"
              :key="doc.doc_code"
              class="doc-card"
              :class="{ open: expandedDocs.includes(doc.doc_code) }"
            >
              <div class="doc-hd" @click="toggleDoc(doc.doc_code)">
                <span class="expander">
                  <ChevronRight :size="14" :class="{ open: expandedDocs.includes(doc.doc_code) }" />
                </span>
                <span class="doc-ic"><FileText :size="15" /></span>
                <div>
                  <div class="doc-code">
                    {{ doc.doc_code }} <span class="pill pill-main">KB 提取</span>
                  </div>
                  <div class="doc-name">{{ doc.doc_name || '—' }}</div>
                </div>
                <div class="doc-meta">
                  <span class="pill pill-gray num"
                    >{{ doc.totalRows }} 行 · {{ doc.units.length }} 表单元</span
                  >
                  <span v-if="doc.verifiedUnits" class="pill pill-ok"
                    >已核验 {{ doc.verifiedUnits }}</span
                  >
                  <span v-else class="pill pill-warn">待核验 {{ doc.units.length }}</span>
                </div>
              </div>
              <div class="doc-body">
                <template
                  v-for="unit in doc.units"
                  :key="unitKey(doc.doc_code, unit.unit_no)"
                >
                  <div class="unit-row">
                    <span class="u-no">{{ unit.unit_no || '—' }}</span>
                    <span v-if="unit.category" class="pill pill-gray">{{ unit.category }}</span>
                    <span class="u-cnt">{{ unit.rows.length }} 行</span>
                    <div class="u-acts">
                      <template v-if="unit.verified">
                        <span class="pill pill-ok">✓ 已核验</span>
                        <span class="vt"
                          >{{ unit.verified_by || '—' }} · {{ shortDate(unit.verified_at) }}</span
                        >
                        <button
                          v-if="userStore.isAdmin"
                          class="btn btn-txt btn-sm"
                          :disabled="unitBusy(doc.doc_code, unit.unit_no)"
                          @click="onUnverify(doc.doc_code, unit.unit_no)"
                        >
                          撤销
                        </button>
                      </template>
                      <button
                        v-else-if="userStore.isAdmin"
                        class="btn btn-sec btn-sm"
                        :disabled="unitBusy(doc.doc_code, unit.unit_no)"
                        @click="onVerify(doc.doc_code, unit.unit_no)"
                      >
                        {{ unitBusy(doc.doc_code, unit.unit_no) ? '提交中…' : '确认核验' }}
                      </button>
                      <button
                        class="btn btn-txt btn-sm"
                        @click="toggleUnit(doc.doc_code, unit.unit_no)"
                      >
                        行明细
                      </button>
                    </div>
                  </div>
                  <div
                    v-if="expandedUnits.includes(unitKey(doc.doc_code, unit.unit_no))"
                    class="rows-pop"
                  >
                    <table class="tbl unit-tbl">
                      <thead>
                        <tr>
                          <th>因子</th>
                          <th>档位</th>
                          <th>指标</th>
                          <th class="r">限值</th>
                          <th>单位</th>
                          <th>时段</th>
                          <th>备注</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(r, i) in unit.rows" :key="i">
                          <td>{{ r.pollutant }}</td>
                          <td>{{ r.category || '—' }}</td>
                          <td>{{ r.metric || '—' }}</td>
                          <td class="r mono num">{{ r.limit_value }}</td>
                          <td>{{ r.unit || '—' }}</td>
                          <td>{{ r.period || '—' }}</td>
                          <td class="vt">{{ r.condition || '' }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </template>
              </div>
            </div>

            <div v-if="!kbDocGroups.length" class="empty-state">
              <a-empty description="暂无已提取指标 · KB enrich 产出的权威限值行在此呈现" />
            </div>
            <div class="tbl-foot">
              <Info :size="13" />
              <span
                >核验以表单元为单位；行值有误时改用「重跑 enrich」修数据，不做行级编辑（保证与 KB
                分块可溯）。</span
              >
            </div>
          </div>

          <!-- KB 外标准手工录入（专家行 · 降位折叠区块，原型 dashed 卡形态） -->
          <div class="expert-card">
            <div class="card-hd" @click="expertOpen = !expertOpen">
              <span class="expander">
                <ChevronRight :size="14" :class="{ open: expertOpen }" />
              </span>
              <h3>KB 外标准手工录入</h3>
              <span class="hd-sub">专家录入 · 即录即核验 · 与 KB 行同入权威表供写作侧查找</span>
              <div class="hd-right">
                <span class="pill pill-gray num">{{ expertSummary }}</span>
                <button
                  v-if="userStore.isAdmin"
                  class="btn btn-pri btn-sm"
                  @click.stop="openCreateDrawer()"
                >
                  <Plus :size="13" />
                  新建手工录入
                </button>
              </div>
            </div>
            <div v-if="expertOpen" class="expert-body">
              <div class="note-bar expert-note">
                <Info :size="14" />
                <span
                  >适用场景：缺源或无法解析入库的标准（如 GB/T 13201-91）。手工行<b>保存即核验生效</b
                  >并进入 lookup_standard_indicator 查找范围；后续若该标准补源入库，enrich
                  会<b>检测到手工行并拒绝覆盖</b>，需先删除或迁移手工行。</span
                >
              </div>
              <template v-if="expertGroups.length">
                <div v-for="g in expertGroups" :key="g.doc_code" class="exp-item">
                  <span class="e-code">{{ g.doc_code }}</span>
                  <span class="e-name">{{ g.doc_name || '—' }}</span>
                  <span class="pill pill-orange">手工</span>
                  <span class="pill pill-ok">✓ 已核验</span>
                  <span class="u-cnt num"
                    >{{ g.totalRows }} 行 · 保存于 {{ shortDate(g.savedAt) }}</span
                  >
                  <div class="e-acts">
                    <button class="btn btn-txt btn-sm" @click="openEditDrawer(g)">编辑</button>
                    <button class="btn btn-txt btn-sm danger" @click="openDelete(g)">删除</button>
                  </div>
                </div>
              </template>
              <div v-else class="empty-state expert-empty">
                <a-empty description="暂无手工标准 · 点击右上「新建手工录入」建档" />
              </div>
            </div>
          </div>
        </template>
      </template>

      <!-- tab2 缺源候选：写作引用了但权威指标库尚未覆盖的标准 -->
      <template v-else>
        <div class="card">
          <div class="card-hd">
            <h3>缺源候选</h3>
            <span class="hd-sub"
              >环评写作引用了但权威指标库尚未覆盖的标准 · 补源 → 上传解析 → enrich 的漏斗入口</span
            >
            <div class="hd-right">
              <span class="pill pill-gray num">引用清单去重 − 已覆盖 = {{ candidates.length }}</span>
            </div>
          </div>
          <a-spin v-if="candidatesLoading" style="display: block; margin: 48px auto" />
          <div v-else-if="candidates.length" class="cand-grid">
            <div v-for="c in pagedCandidates" :key="c.code" class="cand-card">
              <div class="cand-key">
                <div class="cand-ic"><Link :size="14" /></div>
                <div class="cand-title-wrap">
                  <div class="cand-title" :title="c.code">{{ c.code }}</div>
                  <div class="cand-code mono">被引用 {{ c.ref_count }} 次</div>
                </div>
              </div>
              <div class="cand-meta">
                <span class="pill pill-err">缺源</span>
                <span v-if="(c.sample_sources || []).length" class="cand-samples">
                  <code v-for="s in c.sample_sources" :key="s" class="k">{{ s }}</code>
                </span>
              </div>
              <div class="cand-ft">
                <button
                  v-if="userStore.isAdmin"
                  class="btn btn-sec btn-sm"
                  @click="openCreateDrawer(c.code)"
                >
                  手工录入
                </button>
                <button class="btn btn-pri btn-sm" @click="goSource(c)">去补源</button>
              </div>
            </div>
          </div>
          <a-pagination
            v-if="candidates.length > CAND_PAGE_SIZE"
            v-model:current="candPage"
            class="cand-pager"
            :total="candidates.length"
            :page-size="CAND_PAGE_SIZE"
            :show-size-changer="false"
          />
          <div v-else class="empty-state">
            <a-empty description="暂无缺源候选 · 写作引用的标准均已覆盖" />
          </div>
          <div class="tbl-foot">
            <Info :size="13" />
            <span
              >确有原文的标准优先「去补源」走 KB enrich 管线（行与 KB 分块可溯）；确无来源的才落手工录入。</span
            >
          </div>
        </div>
      </template>

    </template>

    <div class="note-bar">
      <Info :size="14" />
      <span
        >体检命不上模式的编号经核实通道人工登记修正；权威限值行由 KB enrich 与专家手工录入双通道写入
        standard_indicators，写手按 (标准号, 参数) 取值。</span
      >
    </div>

    <!-- 核实对话框 -->
    <a-modal
      v-model:open="dlg.open"
      :title="`核实 · ${dlg.record?.code ?? ''}`"
      :confirm-loading="dlg.submitting"
      ok-text="确认核实无误"
      @ok="onSubmit"
    >
      <div v-if="dlg.record" class="dlg-meta">
        <p class="dlg-title">{{ dlg.record.title }}</p>
        <p class="dlg-line">
          {{ tierLabel(dlg.record.tier) }}
          <template v-if="dlg.record.chapters"> · 章节 {{ dlg.record.chapters }}</template>
          · 语料引用 {{ dlg.record.cited_count }} 份
        </p>
        <div class="redline-box">
          <span class="redline-title">核实语义（红线）</span>
          web_search
          结果不采信，仅当已对照<strong>标准原文</strong>确认编号、年份、名称无误时才可确认。
          导出物化后该条目转「已核实」，写作技能将按注册表引用规范书写；但<strong>限值数值断言仍以限值查找表数据在位为准</strong>——
          档位未录入前达标判定一律输出「需人工对照」。
        </div>
      </div>
      <a-form layout="vertical" class="dlg-form">
        <a-form-item label="备注（仅平台库留档，不进物化文件）">
          <a-textarea
            v-model:value="dlg.form.note"
            :rows="2"
            placeholder="核实依据，如「已对照生态环境部官网现行版本」"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- KB 查询弹层（原型 M4：片段仅作核实线索，非引用来源） -->
    <a-modal
      v-model:open="kbDlg.open"
      :title="`KB 查询 · ${kbDlg.code} ${kbDlg.title}`"
      :width="640"
    >
      <div class="kb-hint">
        <AlertTriangle :size="14" />
        <span
          >web_search 与 KB 片段仅作核实线索，不可直接引用条款号 / 限值——核实以标准原文为准。</span
        >
      </div>
      <div class="frm-row">
        <label>知识库</label>
        <a-select
          v-model:value="kbDlg.kbId"
          :loading="kbLoading"
          :options="kbOptions"
          placeholder="选择知识库"
          show-search
          option-filter-prop="label"
        />
        <div class="frm-help">默认选中名称含「环评」的首个库</div>
      </div>
      <div class="kb-row">
        <a-input
          v-model:value="kbDlg.query"
          placeholder="查询词"
          :disabled="kbDlg.submitting"
          @press-enter="onKbSearch"
        />
        <button class="btn btn-pri btn-sm" :disabled="kbDlg.submitting" @click="onKbSearch">
          <Search :size="14" />
          {{ kbDlg.submitting ? '查询中…' : '查询' }}
        </button>
      </div>
      <div class="kb-res">
        <div v-if="kbDlg.submitting" class="kb-empty">
          <RefreshCw :size="13" class="spin" />
          <span>查询中…</span>
        </div>
        <template v-else-if="kbDlg.result !== null">
          <div v-for="(c, i) in kbChunks" :key="i" class="kb-item">
            <div class="kb-src">
              <FileText :size="12" />
              <span class="kb-src-name">{{
                c.metadata?.source || c.metadata?.file_path || '未知来源'
              }}</span>
              <span v-if="c.score != null" class="score">
                score {{ Number(c.score).toFixed(3) }}
              </span>
            </div>
            <div class="kb-txt">{{ c.content }}</div>
          </div>
          <div v-if="kbTextResult" class="kb-item">
            <div class="kb-txt">{{ kbTextResult }}</div>
          </div>
          <pre v-else-if="kbRawResult" class="kb-raw">{{ kbRawResult }}</pre>
          <div v-else-if="!kbChunks.length" class="kb-empty">未找到相关片段</div>
        </template>
        <div v-else class="kb-empty">点击「查询」获取该库中与标准相关的片段线索</div>
      </div>
      <template #footer>
        <button class="btn btn-sec btn-sm" @click="kbDlg.open = false">关闭</button>
      </template>
    </a-modal>

    <!-- 语料引用抽屉（2026-10-20 交互改版：由行内展开迁出，点「语料引用」列数字触发；0 引用只 toast 不进抽屉） -->
    <a-drawer
      v-model:open="citeDrawer.open"
      :title="`${citeDrawer.code} · 语料引用清单`"
      width="480"
    >
      <div v-if="citeDrawer.title" class="cite-line muted" style="margin-bottom: 8px">
        {{ citeDrawer.title }}
      </div>
      <div v-if="citeLoading[citeDrawer.code]" class="cite-line muted">
        <RefreshCw :size="13" class="spin" />
        <span>引用清单加载中…</span>
      </div>
      <div v-else-if="citationsOf(citeDrawer.code)?.error" class="cite-line warn">
        <AlertTriangle :size="13" />
        <span>引用清单加载失败</span>
        <button class="btn btn-txt btn-sm" @click="retryCitations(citeDrawer.code)">
          点击重试
        </button>
      </div>
      <div v-else-if="!citationsOf(citeDrawer.code)?.reports?.length" class="cite-line warn">
        <AlertTriangle :size="13" />
        <span>语料 0 引用——SKILL 手工登记标准，须人工 KB / 联网核实</span>
      </div>
      <div v-else class="src-list">
        <div v-for="c in citationsOf(citeDrawer.code).reports" :key="c.report_id" class="cite-line">
          <FileText :size="13" />
          <span class="mono">{{ c.report_id }}</span>
          <span class="cite-as" :title="`引用名：${c.cited_as}`">{{ c.cited_as }}</span>
          <span v-if="c.stage" class="pill pill-gray s-stage">{{ c.stage }}</span>
        </div>
      </div>
    </a-drawer>

    <!-- 专家录入抽屉（原型两步：标准信息 → 限值行；新建走 POST，编辑走 PUT 整标准替换） -->
    <a-drawer v-model:open="drawer.open" width="640">
      <template #title>
        <div class="drawer-title">
          <PenLine :size="16" class="drawer-title-ic" />
          <div>
            <h3>手工录入标准限值</h3>
            <div class="drawer-sub">保存即核验生效 · 进入写作侧指标查找范围</div>
          </div>
        </div>
      </template>
      <div class="step-tag"><span class="n">1</span>标准信息</div>
      <div class="frm-grid">
        <div class="frm-row">
          <label>标准号 <span class="req">*</span></label>
          <a-input
            v-model:value="drawer.form.doc_code"
            placeholder="如 GB 18596-2001"
            :disabled="Boolean(drawer.editCode)"
          />
          <div class="frm-help">后续补源入库时以此号与 enrich 对账（冲突守护）</div>
        </div>
        <div class="frm-row">
          <label>标准名称</label>
          <a-input
            v-model:value="drawer.form.doc_name"
            placeholder="如 畜禽养殖业污染物排放标准"
          />
        </div>
      </div>
      <div class="frm-row">
        <label>标准类型</label>
        <select v-model="drawer.form.doc_type" class="inp drawer-type-sel">
          <option value="technical_standard">技术标准（限值表）</option>
          <option value="law_regulation">法规（无限值表，仅建档）</option>
        </select>
      </div>

      <div class="step-tag step-gap">
        <span class="n">2</span>限值行
        <span class="pill pill-gray pill-sm">{{ drawer.rows.length }} 行</span>
      </div>
      <table class="edit-tbl">
        <thead>
          <tr>
            <th>因子 *</th>
            <th>档位</th>
            <th>指标</th>
            <th>限值 *</th>
            <th>单位</th>
            <th>时段</th>
            <th>条件备注</th>
            <th class="col-act"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in drawer.rows" :key="i">
            <td><input v-model="row.pollutant" class="inp" placeholder="因子" /></td>
            <td><input v-model="row.category" class="inp" placeholder="档位" /></td>
            <td><input v-model="row.metric" class="inp" placeholder="指标" /></td>
            <td><input v-model="row.limit_value" class="inp" placeholder="限值" /></td>
            <td><input v-model="row.unit" class="inp" placeholder="单位" /></td>
            <td><input v-model="row.period" class="inp" placeholder="时段" /></td>
            <td><input v-model="row.condition" class="inp" placeholder="条件" /></td>
            <td class="col-act">
              <button class="row-del" aria-label="删除行" @click="drawer.rows.splice(i, 1)">
                <Trash2 :size="13" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <button class="add-row-btn" @click="drawer.rows.push(blankManualRow())">
        <Plus :size="13" />
        添加一行
      </button>
      <div class="note-bar">
        <Info :size="14" />
        <span
          >行值务必对照标准原文录入，保存后即时核验生效；日后可整标准编辑或删除。若该标准号随后补源入库，enrich
          将拒绝覆盖手工行并提示。</span
        >
      </div>
      <template #footer>
        <button class="btn btn-sec btn-sm" @click="drawer.open = false">取消</button>
        <button class="btn btn-pri btn-sm" :disabled="drawer.submitting" @click="onSaveDrawer">
          {{ drawer.submitting ? '保存中…' : `保存并核验（${drawer.rows.length} 行）` }}
        </button>
      </template>
    </a-drawer>

    <!-- 删除手工标准确认（lookup 立即失效 · 不可撤销，文案照原型） -->
    <a-modal
      v-model:open="delDlg.open"
      title="删除手工标准"
      :confirm-loading="delDlg.submitting"
      ok-text="确认删除"
      :ok-button-props="{ danger: true }"
      @ok="onDelete"
    >
      <div class="del-warn">
        <AlertTriangle :size="14" />
        <span
          >将删除 <b>{{ delDlg.group?.doc_code }}</b> 的全部
          {{ delDlg.group?.totalRows }} 条手工限值行。写作侧
          <code class="k">lookup_standard_indicator</code>
          对该标准的查找将立即失效；KB 侧数据不受影响。此操作不可撤销。</span
        >
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  AlertTriangle,
  ChevronRight,
  FileText,
  Info,
  Link,
  PenLine,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  SquareCheckBig,
  Trash2
} from '@lucide/vue'
import { eiaStandardApi } from '@/apis/eia_standard_api'
import { regulationLibraryApi } from '@/apis/regulation_library_api'
import { databaseApi, queryApi } from '@/apis/knowledge_api'
import { useUserStore } from '@/stores/user'

const TIERS = [
  { key: 'framework', label: '框架标准' },
  { key: 'quality_limit', label: '质量标准' },
  { key: 'emission_limit', label: '排放标准' },
  { key: 'method_param', label: '方法与参数' },
  { key: 'pending', label: '档位待定' }
]
const TIER_LABELS = Object.fromEntries(TIERS.map((t) => [t.key, t.label]))

const userStore = useUserStore()
const loading = ref(false)
const exporting = ref(false)
const items = ref([])
const limitTables = ref({})
const gate1 = ref(null)
const filters = reactive({ state: '', q: '' })

const tierLabel = (k) => TIER_LABELS[k] || k
// 分级徽记按真实类别映射展示档位（非虚构 T1/T2 评级）：质量/排放为写手取值主力 → tier-1
const TIER_BADGES = {
  quality_limit: 'tier-1',
  emission_limit: 'tier-1',
  framework: 'tier-2',
  method_param: 'tier-3',
  pending: 'tier-3'
}
const tierBadge = (k) => TIER_BADGES[k] || 'tier-3'

// seg/头标与过滤同源：待核实 = 文件标记且无裁决；已核实 = 其余（含免核实条目）。
// 不用服务端 counts.confirmed——它只数 DB 裁决，与表格过滤口径脱节（会显示 0 却过滤出 21 行）
const todoCount = computed(
  () => items.value.filter((r) => r.needs_verification && !r.review.action).length
)
const doneCount = computed(
  () => items.value.filter((r) => !r.needs_verification || r.review.action).length
)

const isFiltered = computed(() => Boolean(filters.state || filters.q))
const emptyDesc = computed(() => (isFiltered.value ? '当前筛选无匹配标准' : '标准注册表为空'))

const filteredItems = computed(() => {
  let list = items.value
  if (filters.state === 'todo') list = list.filter((r) => r.needs_verification && !r.review.action)
  if (filters.state === 'done') list = list.filter((r) => !r.needs_verification || r.review.action)
  if (filters.q) {
    const q = filters.q.toLowerCase()
    list = list.filter(
      (r) => r.code.toLowerCase().includes(q) || (r.title || '').toLowerCase().includes(q)
    )
  }
  return list
})

const clearFilters = () => {
  filters.state = ''
  filters.q = ''
}

// 前端整包分页（同 LexiconPanel 惯例）：筛选/页大小变更回第 1 页
const page = ref(1)
const PAGE_SIZE_OPTIONS = [10, 20, 50]
const pageSize = ref(10)
const sizeOptions = PAGE_SIZE_OPTIONS.map((n) => ({ value: n, label: `${n} 条/页` }))
const pageCount = computed(() =>
  Math.max(1, Math.ceil(filteredItems.value.length / pageSize.value))
)
const pagedItems = computed(() =>
  filteredItems.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value)
)
const setPageSize = (n) => {
  pageSize.value = n
  page.value = 1
}
watch(filters, () => {
  page.value = 1
})

// ── 限值表关联视图（标准核实清单行内展开用）──────────────

const tableEntries = computed(() =>
  Object.entries(limitTables.value).filter(([, v]) => typeof v === 'object' && v !== null)
)

const fetchList = async () => {
  loading.value = true
  try {
    const [data, limits, gate1Data] = await Promise.all([
      eiaStandardApi.listStandards(),
      eiaStandardApi.listLimits(),
      eiaStandardApi.getGate1().catch(() => null) // 体检卡独立降级：不阻塞标准表主链
    ])
    items.value = data.items
    limitTables.value = Object.fromEntries(
      Object.entries(limits.limit_tables).filter(([, v]) => typeof v === 'object' && v !== null)
    )
    gate1.value = gate1Data
  } catch (e) {
    message.error(e?.message || '标准库加载失败')
  } finally {
    loading.value = false
  }
}

const onExport = async () => {
  exporting.value = true
  message.loading({ content: '正在物化…', key: 'std-export', duration: 0 })
  try {
    const r = await eiaStandardApi.exportReviews()
    message.success({
      content: `已翻转 ${r.materialized} 条裁决 → standards_index.json（落运行栈技能目录，需人工回流 pisuan-custom）`,
      key: 'std-export'
    })
    await fetchList()
  } catch (e) {
    message.error({ content: e?.message || '导出失败', key: 'std-export' })
  } finally {
    exporting.value = false
  }
}

// ── 核实对话框 ──────────────────────────────────────────

const dlg = reactive({ open: false, submitting: false, record: null, form: { note: '' } })

const openReview = (record) => {
  dlg.record = record
  dlg.form.note = record.review?.note || ''
  dlg.open = true
}

const onSubmit = async () => {
  dlg.submitting = true
  try {
    await eiaStandardApi.setReview(dlg.record.code, {
      action: 'confirm',
      note: dlg.form.note || null
    })
    message.success(`「${dlg.record.code}」核实裁决已保存（导出物化后生效）`)
    dlg.open = false
    await fetchList()
  } catch (e) {
    message.error(e?.message || '核实保存失败')
  } finally {
    dlg.submitting = false
  }
}

// ── 页头 dbTableCount pill（DB 录入表 → 待导出计数）──────

const dbTableCount = computed(
  () => Object.values(limitTables.value).filter((t) => t.source === 'db').length
)

const exportLimits = async () => {
  exporting.value = true
  message.loading({ content: '正在物化限值行…', key: 'limits-export', duration: 0 })
  try {
    const r = await eiaStandardApi.exportLimits()
    message.success({
      content: `已物化 ${r.materialized} 张限值表 ${r.rows} 行 → standards_index.json（落运行栈技能目录，需人工回流 pisuan-custom）`,
      key: 'limits-export'
    })
    await fetchList()
  } catch (e) {
    message.error({ content: e?.message || '限值行导出失败', key: 'limits-export' })
  } finally {
    exporting.value = false
  }
}

// ── 标准核实辅助（T8：关联限值表行内展开 + 引用清单抽屉 + KB 查询弹层）─────────
const expandedTableCodes = ref([])
// 标准 → 关联限值表：limit_tables 条目的 code_ref 与注册表 code 精确相等（文件态/DB 入册两通道均露出）
const tablesOf = (code) => tableEntries.value.filter(([, t]) => t.code_ref === code)
const toggleTables = (record) => {
  const code = record.code
  expandedTableCodes.value = expandedTableCodes.value.includes(code)
    ? expandedTableCodes.value.filter((x) => x !== code)
    : [...expandedTableCodes.value, code]
}

const citationCache = ref({}) // code → listCitations 响应（拉一次后缓存；失败缓存 error 哨兵，由「点击重试」清除后重拉）
const citeLoading = ref({})
// 标准核实表列数（表头：展开/标准号/名称/分级/语料引用/核实状态/核实人/操作）——加列时与 thead 同步
const STANDARDS_TABLE_COLS = 8

const citationsOf = (code) => citationCache.value[code]

const loadCitations = async (code) => {
  if (code in citationCache.value || citeLoading.value[code]) return
  citeLoading.value = { ...citeLoading.value, [code]: true }
  try {
    const r = await eiaStandardApi.listCitations(code)
    citationCache.value = { ...citationCache.value, [code]: r }
  } catch (e) {
    message.error(e?.message || `引用清单加载失败：${code}`)
    // 失败只缓存哨兵不缓存「空清单」——接口故障不得伪装成「语料 0 引用」业务事实
    citationCache.value = { ...citationCache.value, [code]: { error: true } }
  } finally {
    citeLoading.value = { ...citeLoading.value, [code]: false }
  }
}

const retryCitations = (code) => {
  delete citationCache.value[code]
  loadCitations(code)
}

// 引用抽屉：0 引用是业务信号（SKILL 手工登记）只警示不进抽屉；>0 打开抽屉懒加载清单
const citeDrawer = reactive({ open: false, code: '', title: '' })
const openCitations = (record) => {
  if (!record.cited_count) {
    message.warning('语料 0 引用——SKILL 手工登记标准，须人工 KB / 联网核实')
    return
  }
  citeDrawer.code = record.code
  citeDrawer.title = record.title
  citeDrawer.open = true
  loadCitations(record.code)
}

const kbDlg = reactive({
  open: false,
  submitting: false,
  code: '',
  title: '',
  kbId: '',
  query: '',
  result: null,
  seq: 0 // 请求序号令牌：关闭/换标准重开弹层后，旧查询的迟到回包一律丢弃
})
const databases = ref([])
const kbLoading = ref(false)

const kbOptions = computed(() =>
  databases.value.map((d) => ({ label: `${d.name}（${d.kb_id}）`, value: d.kb_id }))
)
const kbChunks = computed(() => (Array.isArray(kbDlg.result) ? kbDlg.result : []))
const kbTextResult = computed(() => (typeof kbDlg.result === 'string' ? kbDlg.result : ''))
const kbRawResult = computed(() =>
  kbDlg.result !== null && !Array.isArray(kbDlg.result) && typeof kbDlg.result !== 'string'
    ? JSON.stringify(kbDlg.result, null, 2)
    : ''
)

const loadDatabases = async () => {
  if (kbLoading.value) return
  kbLoading.value = true
  try {
    const r = await databaseApi.getDatabases()
    databases.value = r.databases || []
  } catch (e) {
    message.error(e?.message || '知识库列表加载失败')
  } finally {
    kbLoading.value = false
  }
}

const openKbQuery = async (record) => {
  kbDlg.seq += 1 // 作废可能在飞的旧查询回包
  kbDlg.code = record.code
  kbDlg.title = record.title
  kbDlg.query = `${record.title} ${record.code}`
  kbDlg.result = null
  kbDlg.submitting = false // 重开时清掉旧查询遗留的「查询中…」
  kbDlg.open = true
  await loadDatabases()
  // 默认选名称含「环评」的首个库；用户手动选过则尊重其选择
  if (!kbDlg.kbId) {
    const preferred = databases.value.find((d) => (d.name || '').includes('环评'))
    kbDlg.kbId = preferred?.kb_id || databases.value[0]?.kb_id || ''
  }
}

const onKbSearch = async () => {
  if (!kbDlg.kbId) {
    message.warning('请先选择知识库')
    return
  }
  if (!kbDlg.query.trim()) {
    message.warning('请输入查询词')
    return
  }
  const seq = ++kbDlg.seq
  kbDlg.submitting = true
  kbDlg.result = null
  try {
    const r = await queryApi.queryTest(kbDlg.kbId, kbDlg.query.trim(), {})
    if (seq !== kbDlg.seq) return
    kbDlg.result = r
  } catch (e) {
    if (seq !== kbDlg.seq) return
    message.error(e?.message || 'KB 查询失败')
  } finally {
    // 仅最新请求有权复位 submitting，否则会盖掉重开弹层后的新状态
    if (seq === kbDlg.seq) kbDlg.submitting = false
  }
}

// ── 两 tab（原型 2026-10-20）：已提取指标核验台 / 缺源候选 ──────────────

const router = useRouter()
const activeTab = ref('indicators')
const indicators = ref([])
const indicatorsLoading = ref(false)
const expandedDocs = ref([])
const expandedUnits = ref([])
const verifyBusyKey = ref('')
const expertOpen = ref(false)
const candidates = ref([])
const candidatesLoading = ref(false)
const CAND_PAGE_SIZE = 9
const candPage = ref(1)
const pagedCandidates = computed(() =>
  candidates.value.slice((candPage.value - 1) * CAND_PAGE_SIZE, candPage.value * CAND_PAGE_SIZE)
)
const candidatesLoaded = ref(false)

const unitKey = (docCode, unitNo) => `${docCode}|${unitNo}`
// 核验请求按单元粒度上锁：仅对应单元的按钮进入提交态
const unitBusy = (docCode, unitNo) => verifyBusyKey.value === unitKey(docCode, unitNo)
// 核验时间仅展示月-日（原型口径）；ISO 串或 null
const shortDate = (iso) => (iso ? String(iso).slice(5, 10) : '—')

const toggleDoc = (code) => {
  expandedDocs.value = expandedDocs.value.includes(code)
    ? expandedDocs.value.filter((x) => x !== code)
    : [...expandedDocs.value, code]
}

const toggleUnit = (docCode, unitNo) => {
  const key = unitKey(docCode, unitNo)
  expandedUnits.value = expandedUnits.value.includes(key)
    ? expandedUnits.value.filter((x) => x !== key)
    : [...expandedUnits.value, key]
}

// 客户端分组 doc_code → unit_no；source='expert' 不进 KB 分组（归 tab1 底部手工区块）
const groupIndicators = (kind) => {
  const docMap = new Map()
  for (const r of indicators.value) {
    const isExpert = r.source === 'expert'
    if ((kind === 'expert') !== isExpert) continue
    if (!docMap.has(r.doc_code)) {
      docMap.set(r.doc_code, { doc_code: r.doc_code, doc_name: r.doc_name || '', units: new Map() })
    }
    const doc = docMap.get(r.doc_code)
    if (!doc.doc_name && r.doc_name) doc.doc_name = r.doc_name
    const uNo = r.unit_no ?? '' // 分组保留原始 unit_no（可能为空），「—」仅作展示 fallback
    if (!doc.units.has(uNo)) {
      doc.units.set(uNo, { unit_no: uNo, rows: [], category: '', verified: false, verified_by: '', verified_at: '' })
    }
    doc.units.get(uNo).rows.push(r)
  }
  return [...docMap.values()].map((doc) => {
    const units = [...doc.units.values()].map((u) => {
      // 表单元级核验态：所有行 verified_at 非空即视为已核验；档位 pill 仅当全单元同一 category
      u.verified = u.rows.every((r) => Boolean(r.verified_at))
      const cats = [...new Set(u.rows.map((r) => (r.category || '').trim()).filter(Boolean))]
      u.category = cats.length === 1 ? cats[0] : ''
      if (u.verified) {
        u.verified_by = u.rows[0]?.verified_by || ''
        u.verified_at = u.rows[0]?.verified_at || ''
      }
      return u
    })
    return {
      doc_code: doc.doc_code,
      doc_name: doc.doc_name,
      units,
      totalRows: units.reduce((sum, u) => sum + u.rows.length, 0),
      verifiedUnits: units.filter((u) => u.verified).length
    }
  })
}

const kbDocGroups = computed(() => groupIndicators('kb'))

const expertGroups = computed(() =>
  groupIndicators('expert').map((g) => ({
    ...g,
    // 手工行 born-verified：保存时间取该标准最早 verified_at
    savedAt:
      g.units
        .flatMap((u) => u.rows)
        .map((r) => r.verified_at)
        .filter(Boolean)
        .sort()[0] || ''
  }))
)

const indicatorsSummary = computed(() => {
  const docs = kbDocGroups.value
  const unitCount = docs.reduce((sum, d) => sum + d.units.length, 0)
  const verifiedCount = docs.reduce((sum, d) => sum + d.verifiedUnits, 0)
  return `${docs.length} 标准 · ${unitCount} 表单元 · ${verifiedCount} 已核验`
})

const expertSummary = computed(() => {
  const groups = expertGroups.value
  const rowCount = groups.reduce((sum, g) => sum + g.totalRows, 0)
  return `${groups.length} 标准 · ${rowCount} 行`
})

const loadIndicators = async (silent = false) => {
  if (!silent) indicatorsLoading.value = true
  try {
    const data = await regulationLibraryApi.getIndicators()
    indicators.value = data.items || []
  } catch (e) {
    // 非管理员访问 admin 端点属预期：静默降级为空台；管理员遇到真实故障才提示
    if (userStore.isAdmin) message.error(e?.message || '已提取指标加载失败')
    else console.warn('[StandardsPanel] 指标加载跳过（非管理员）：', e?.message)
  } finally {
    if (!silent) indicatorsLoading.value = false
  }
}

// 核验/撤销后静默重拉（无整页 spinner），服务端始终是核验态唯一事实
const setUnitVerify = async (docCode, unitNo, verify) => {
  verifyBusyKey.value = unitKey(docCode, unitNo)
  try {
    const data = verify
      ? await regulationLibraryApi.verifyUnit(docCode, unitNo)
      : await regulationLibraryApi.unverifyUnit(docCode, unitNo)
    if ((data?.updated ?? 0) === 0) {
      // updated=0：该单元无可核验行，服务端未变更，不置核验态
      message.warning('该单元无可核验行')
      return
    }
    message.success(`${verify ? '已核验' : '已撤销核验'} ${docCode} · ${unitNo || '—'}`)
    await loadIndicators(true)
  } catch (e) {
    message.error(e?.message || (verify ? '核验失败' : '撤销失败'))
  } finally {
    verifyBusyKey.value = ''
  }
}

const onVerify = (docCode, unitNo) => setUnitVerify(docCode, unitNo, true)
const onUnverify = (docCode, unitNo) => setUnitVerify(docCode, unitNo, false)

// tab2 缺源候选：进 tab 拉一次（引用清单去重 − 已覆盖，admin）
const loadCandidates = async () => {
  if (candidatesLoaded.value) return
  candidatesLoading.value = true
  try {
    candidates.value = await eiaStandardApi.listSourceCandidates()
    candidatesLoaded.value = true
    candPage.value = 1
  } catch (e) {
    if (userStore.isAdmin) message.error(e?.message || '缺源候选加载失败')
    else console.warn('[StandardsPanel] 缺源候选加载跳过（非管理员）：', e?.message)
  } finally {
    candidatesLoading.value = false
  }
}

const switchTab = (tab) => {
  activeTab.value = tab
  if (tab === 'candidates') loadCandidates()
}

// 「去补源」：无标准库专设路由，跳知识库列表页（tab=knowledge）并由 toast 指路
const goSource = (c) => {
  message.info(`请在知识库「标准规范库」补源上传「${c.code}」，解析后 enrich 自动提取指标`)
  router.push({ path: '/extensions', query: { tab: 'knowledge' } })
}

// ── 专家录入抽屉（新建 POST / 编辑 PUT 整标准替换；手工行保存即核验）────────

const MANUAL_ROW_FIELDS = [
  'pollutant',
  'category',
  'metric',
  'limit_value',
  'unit',
  'period',
  'condition'
]
const blankManualRow = () => Object.fromEntries(MANUAL_ROW_FIELDS.map((k) => [k, '']))

const drawer = reactive({
  open: false,
  submitting: false,
  editCode: '', // 非空 = 编辑态（PUT 以 path 上的 doc_code 定位）
  form: { doc_code: '', doc_name: '', doc_type: 'technical_standard' },
  rows: []
})

const openCreateDrawer = (prefillCode = '') => {
  drawer.editCode = ''
  drawer.form = { doc_code: prefillCode, doc_name: '', doc_type: 'technical_standard' }
  drawer.rows = [blankManualRow()]
  drawer.open = true
}

const openEditDrawer = (group) => {
  drawer.editCode = group.doc_code
  drawer.form = {
    doc_code: group.doc_code,
    doc_name: group.doc_name,
    doc_type: 'technical_standard' // doc_type 仅创建时传后端，不回显持久化
  }
  drawer.rows = group.units
    .flatMap((u) => u.rows)
    .map((r) => Object.fromEntries(MANUAL_ROW_FIELDS.map((k) => [k, r[k] ?? ''])))
  if (!drawer.rows.length) drawer.rows = [blankManualRow()]
  drawer.open = true
}

const onSaveDrawer = async () => {
  const code = drawer.form.doc_code.trim()
  if (!code) {
    message.warning('请填写标准号')
    return
  }
  if (!drawer.rows.length) {
    message.warning('请至少录入一行限值')
    return
  }
  if (drawer.rows.length > 500) {
    message.warning('限值行不能超过 500 行')
    return
  }
  const hasBlankRequired = drawer.rows.some(
    (r) => !String(r.pollutant || '').trim() || !String(r.limit_value || '').trim()
  )
  if (hasBlankRequired) {
    message.warning('存在缺少「因子」或「限值」的行，请补全或删除该行')
    return
  }
  const payload = {
    doc_code: code,
    doc_name: drawer.form.doc_name.trim(),
    doc_type: drawer.form.doc_type,
    rows: drawer.rows.map((r) => ({
      pollutant: String(r.pollutant).trim(),
      category: String(r.category || '').trim(),
      metric: String(r.metric || '').trim(),
      limit_value: String(r.limit_value).trim(),
      unit: String(r.unit || '').trim(),
      period: String(r.period || '').trim(),
      condition: String(r.condition || '').trim()
    }))
  }
  drawer.submitting = true
  try {
    if (drawer.editCode) await regulationLibraryApi.updateManualStandard(drawer.editCode, payload)
    else await regulationLibraryApi.createManualStandard(payload)
    message.success(`「${code}」已保存并核验生效（${payload.rows.length} 行）`)
    drawer.open = false
    expertOpen.value = true
    candidatesLoaded.value = false // 手工标准增删后缺源候选缓存失效，下次进 tab2 重拉
    await loadIndicators(true)
  } catch (e) {
    // 409（编号已存在 / 非 expert 行）、400（校验失败）detail 由 api 层透出
    message.error(e?.message || '手工标准保存失败')
  } finally {
    drawer.submitting = false
  }
}

// ── 删除手工标准（确认弹窗：lookup 立即失效、不可撤销）──────────────────

const delDlg = reactive({ open: false, submitting: false, group: null })

const openDelete = (group) => {
  delDlg.group = group
  delDlg.open = true
}

const onDelete = async () => {
  delDlg.submitting = true
  try {
    await regulationLibraryApi.deleteManualStandard(delDlg.group.doc_code)
    message.success(`已删除 ${delDlg.group.doc_code}（${delDlg.group.totalRows} 行）`)
    delDlg.open = false
    candidatesLoaded.value = false // 手工标准增删后缺源候选缓存失效，下次进 tab2 重拉
    await loadIndicators(true)
  } catch (e) {
    message.error(e?.message || '删除失败')
  } finally {
    delDlg.submitting = false
  }
}

onMounted(() => {
  fetchList()
  loadIndicators()
})
</script>

<style lang="less" scoped>
.standards-panel {
  --hairline: var(--gray-200);
}

/* 清单表列宽固定（标准名/备注为长文本），同 s9/s10 结论；单元行明细表字段短改回自动 */
.standards-panel .tbl {
  table-layout: fixed;

  td {
    overflow-wrap: break-word;
  }
}

.unit-tbl {
  table-layout: auto;
}

.title-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;

  .title-main {
    color: var(--gray-800);
  }

  .title-role {
    font-size: 11px;
    line-height: 1.5;
    color: var(--gray-400);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    white-space: normal;
    word-break: break-all;
  }
}

.muted {
  color: var(--gray-400);
}

.review-cell {
  display: flex;
  flex-direction: column;

  .review-by {
    font-size: 13px;
    font-weight: 600;
    color: var(--main-600);
  }

  .review-note {
    font-size: 11px;
    color: var(--gray-400);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

/* ── 空态 ───────────────────────────────────────────── */
.empty-state {
  padding: 48px 0;
  text-align: center;
}

/* ── 核实对话框 ─────────────────────────────────────── */
.dlg-meta {
  margin-bottom: 12px;
}

.dlg-title {
  margin: 0 0 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--gray-800);
}

.dlg-line {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--gray-600);
}

.redline-box {
  padding: 10px 12px;
  border: 1px solid var(--second-600);
  border-radius: 6px;
  background: var(--main-0);
  font-size: 12px;
  line-height: 1.7;
  color: var(--gray-600);

  .redline-title {
    display: block;
    margin-bottom: 4px;
    font-weight: 600;
    color: var(--second-600);
  }

  strong {
    color: var(--gray-800);
  }
}

.dlg-form {
  margin-top: 4px;
}

/* ── 门 1 体检卡 ── */
.gate1-card {
  border: 1px solid var(--hairline);
  border-radius: 8px;
  background: var(--gray-0);
  margin-bottom: 12px;
  overflow: hidden;
}

.gate1-hd {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;

  h3 {
    font-size: 14px;
    font-weight: 600;
    margin: 0;
  }

  .hd-sub {
    font-size: 12px;
    color: var(--gray-500);
  }

  .hd-right {
    margin-left: auto;
  }
}

.gate1-badge {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: var(--main-0);
  color: var(--main-600);
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
}

.pill-warn-tag,
.pill-ok-tag {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 999px;
}

.pill-warn-tag {
  background: var(--second-50, var(--gray-100));
  color: var(--second-600);
}

.pill-ok-tag {
  background: var(--main-0);
  color: var(--main-600);
}

.gate1-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border-top: 1px solid var(--hairline);
}

.gate1-m {
  padding: 11px 16px;
  display: flex;
  align-items: baseline;
  gap: 8px;

  & + & {
    border-left: 1px solid var(--hairline);
  }

  .v {
    font-size: 20px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;

    &.zero {
      color: var(--main-600);
    }

    &.hot {
      color: var(--second-600);
    }
  }

  .l {
    font-size: 12px;
    color: var(--gray-600);
  }

  .h {
    margin-left: auto;
    font-size: 11px;
    color: var(--gray-500);
  }
}

.gate1-body {
  border-top: 1px solid var(--hairline);
  padding: 10px 16px 12px;
}

.pl-label {
  display: inline-block;
  font-size: 12px;
  color: var(--gray-500);
  margin-right: 8px;
}

.gate1-patterns,
.gate1-viol {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

/* mono 栈对齐原型 var(--mono)（用户裁定，2026-10-13） */
code.k {
  font-family: ui-monospace, 'Cascadia Code', Consolas, 'Courier New', monospace;
  font-size: 12px;
  background: var(--gray-100);
  border-radius: 4px;
  padding: 1px 6px;
  color: var(--gray-700);

  &.viol {
    color: var(--second-600);
    background: var(--second-50, var(--gray-100));
  }
}

.gate1-rules {
  margin: 8px 0 0;
  padding-left: 30px;
  font-size: 12px;
  color: var(--gray-600);
  line-height: 1.9;

  li + li {
    margin-top: 2px;
  }
}

.gate1-viol {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--hairline);
}

/* ── 提取弹层表单（专家录入抽屉沿用）───────────────────── */

.expander {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  border-radius: 5px;
  background: none;
  color: var(--gray-500);
  cursor: pointer;

  &:hover {
    background: var(--gray-100);
    color: var(--gray-800);
  }

  svg {
    transition: transform 0.15s;

    &.open {
      transform: rotate(90deg);
    }
  }
}

.sub-row > td {
  padding: 10px 12px 12px 42px;
  background: var(--gray-25, var(--gray-50));
  border-bottom: 1px solid var(--gray-100);
}

.src-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.btn-txt.danger {
  color: var(--second-600);

  &:hover {
    background: var(--second-50, var(--gray-100));
  }
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* ── 缺源候选（tab2 复用原候选卡形态）──────────────────── */
.cand-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
  gap: 10px;
  padding: 14px 16px;
}

.cand-pager {
  display: flex;
  justify-content: center;
  padding: 4px 16px 16px;
}

.cand-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  background: var(--gray-0);
  transition: border-color 0.15s;

  &:hover {
    border-color: var(--main-300);
  }
}

.cand-key {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;

  .cand-ic {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    flex: none;
    border-radius: 6px;
    background: var(--second-50, var(--gray-100));
    color: var(--second-600);
  }
}

.cand-title-wrap {
  min-width: 0;
}

.cand-title {
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cand-code {
  font-size: 12px;
  color: var(--gray-500);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cand-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12px;
  color: var(--gray-500);
}

/* 引用别名样本（后端 sample_sources，≤3 条） */
.cand-samples {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-width: 0;

  code.k {
    font-size: 11px;
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.cand-ft {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 9px;
  border-top: 1px dashed var(--gray-200);
  margin-top: auto;
}

/* ── 提取弹层表单（M1 编辑 / M2 转正 / M3 立表）───────── */
.frm-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 12px;
}

.frm-row {
  margin-bottom: 14px;

  label {
    display: block;
    margin-bottom: 5px;
    font-size: 12px;
    font-weight: 500;
    color: var(--gray-600);
  }
}

.frm-help {
  margin-top: 4px;
  font-size: 12px;
  color: var(--gray-500);
}

/* ── 两 tab 容器（原型 2026-10-20）────────────────────── */
.tabbar {
  display: flex;
  gap: 4px;
  padding: 0 8px;
  border-bottom: 1px solid var(--hairline);
  margin-bottom: 12px;

  .tab {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 9px 14px 8px;
    font-size: 14px;
    color: var(--color-text-secondary);
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    cursor: pointer;
    font-family: inherit;

    &:hover {
      color: var(--main-600);
    }

    &.on {
      color: var(--main-600);
      font-weight: 600;
      border-bottom-color: var(--main-600);
    }

    .badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      height: 17px;
      min-width: 17px;
      padding: 0 5px;
      border-radius: 999px;
      font-size: 11px;
      background: var(--gray-100);
      color: var(--gray-600);
      font-variant-numeric: tabular-nums;
    }

    &.on .badge {
      background: var(--main-50);
      color: var(--main-600);
    }
  }
}

/* ── tab1 核验台：标准折叠卡 → 表单元行 ────────────────── */
.doc-card {
  border-bottom: 1px solid var(--gray-100);

  &:last-of-type {
    border-bottom: none;
  }
}

.doc-hd {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 16px;
  cursor: pointer;
  user-select: none;

  &:hover {
    background: var(--gray-50);
  }

  .doc-ic {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    flex: none;
    border-radius: 7px;
    background: var(--main-50);
    color: var(--main-600);
  }

  .doc-code {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 600;
  }

  .doc-name {
    font-size: 12px;
    color: var(--color-text-tertiary);
  }

  .doc-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-left: auto;
    flex: none;
  }
}

.doc-body {
  display: none;
  border-top: 1px solid var(--gray-100);
}

.doc-card.open .doc-body {
  display: block;
}

.unit-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px 8px 26px;
  border-bottom: 1px solid var(--gray-100);
  font-size: 13px;

  &:hover {
    background: var(--gray-50);
  }

  .u-no {
    min-width: 72px;
    flex: none;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--color-text-secondary);
  }

  .u-cnt {
    flex: none;
    font-size: 12px;
    color: var(--color-text-tertiary);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .u-acts {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-left: auto;
    flex: none;
  }
}

.vt {
  font-size: 11px;
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

/* 行明细展开：浅底衬块 + 横向滚动兜底（GB 8978 单元 276 行宽值） */
.rows-pop {
  padding: 10px 16px 12px 26px;
  background: var(--gray-25, var(--gray-50));
  border-bottom: 1px solid var(--gray-100);
  overflow-x: auto;

  .tbl td {
    background: var(--gray-0);
  }
}

/* ── KB 外标准手工录入（tab1 底部折叠区块，dashed 卡形态）── */
.expert-card {
  margin-top: 12px;
  border: 1px dashed var(--main-300);
  border-radius: 8px;
  overflow: hidden;

  .card-hd {
    cursor: pointer;
    user-select: none;
    background: var(--main-10, var(--main-50));

    &:hover {
      background: var(--main-30, var(--main-50));
    }
  }
}

.expert-note {
  margin: 12px 16px 0;
}

.expert-empty {
  padding: 24px 0;
}

.exp-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 16px;
  border-bottom: 1px solid var(--gray-100);
  font-size: 13px;

  &:hover {
    background: var(--gray-50);
  }

  .e-code {
    flex: none;
    font-family: var(--font-mono);
    font-size: 12px;
    font-weight: 600;
  }

  .e-name {
    min-width: 0;
    font-size: 12px;
    color: var(--color-text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .u-cnt {
    margin-left: auto;
    flex: none;
    font-size: 12px;
    color: var(--color-text-tertiary);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .e-acts {
    display: flex;
    gap: 4px;
    flex: none;
  }
}

/* ── 专家录入抽屉（两步表单 + 限值行编辑）──────────────── */
.drawer-title {
  display: flex;
  align-items: center;
  gap: 10px;

  .drawer-title-ic {
    flex: none;
    color: var(--main-600);
  }

  h3 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    line-height: 1.3;
  }

  .drawer-sub {
    font-size: 12px;
    color: var(--color-text-tertiary);
  }
}

.step-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--main-600);

  .n {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    border-radius: 999px;
    background: var(--main-50);
    color: var(--main-600);
    font-size: 11px;
  }
}

.step-gap {
  margin-top: 20px;
}

.req {
  color: var(--color-error-500);
}

.drawer-type-sel {
  width: 100%;
}

.edit-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;

  th {
    padding: 4px 6px;
    border-bottom: 1px solid var(--hairline);
    font-size: 11px;
    font-weight: 500;
    color: var(--color-text-tertiary);
    text-align: left;
    white-space: nowrap;
  }

  td {
    padding: 4px 6px;
    border-bottom: 1px solid var(--gray-100);
  }

  .inp {
    width: 100%;
    min-width: 0;
    height: 26px;
    padding: 0 7px;
    font-size: 12px;
  }

  .col-act {
    width: 26px;
  }

  .row-del {
    display: inline-flex;
    padding: 4px;
    border: none;
    border-radius: 4px;
    background: none;
    color: var(--color-text-tertiary);
    cursor: pointer;

    &:hover {
      background: var(--color-error-50);
      color: var(--color-error-700);
    }
  }
}

.add-row-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  height: 30px;
  margin-top: 8px;
  border: 1px dashed var(--gray-300);
  border-radius: 6px;
  background: none;
  color: var(--color-text-tertiary);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;

  &:hover {
    border-color: var(--main-400);
    color: var(--main-600);
    background: var(--main-10, var(--main-50));
  }
}

/* 删除确认警示框（文案照原型：lookup 立即失效、不可撤销） */
.del-warn {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 9px 12px;
  border: 1px solid color-mix(in srgb, var(--color-error-500) 30%, transparent);
  border-radius: 6px;
  background: var(--color-error-50);
  font-size: 12px;
  color: var(--color-error-700);

  svg {
    flex: none;
    margin-top: 2px;
  }
}

/* ── 标准核实辅助（T8：引用清单展开 + KB 查询弹层）───────── */
.cite-line {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  font-size: 12px;
  color: var(--gray-600);

  svg {
    flex: none;
    color: var(--gray-500);
  }

  &.warn {
    color: var(--second-700);
  }

  .cite-as {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .s-stage {
    flex: none;
  }
}

.kb-hint {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 14px;
  padding: 9px 12px;
  border: 1px solid var(--second-200);
  border-radius: 6px;
  background: var(--second-50);
  font-size: 12px;
  color: var(--second-700);

  svg {
    flex: none;
    margin-top: 2px;
  }
}

.kb-row {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;

  > :first-child {
    flex: 1;
  }

  .btn {
    display: inline-flex;
    flex: none;
    align-items: center;
    gap: 6px;
  }
}

.kb-res {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
}

.kb-item {
  padding: 9px 12px;
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  font-size: 12px;

  .kb-src {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
    color: var(--gray-500);

    .kb-src-name {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .score {
      flex: none;
      margin-left: auto;
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--main-600);
    }
  }

  .kb-txt {
    display: -webkit-box;
    -webkit-line-clamp: 4;
    -webkit-box-orient: vertical;
    overflow: hidden;
    color: var(--gray-600);
    line-height: 1.7;
  }
}

.kb-empty {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border: 1px dashed var(--gray-200);
  border-radius: 6px;
  font-size: 12px;
  color: var(--gray-500);
}

.kb-raw {
  max-height: 260px;
  margin: 0;
  padding: 10px 12px;
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  overflow: auto;
  font-size: 11px;
  color: var(--gray-600);
}

.pager {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

/* 统计文案居左、页大小下拉与翻页控件居右（共享 .tbl-foot 无 justify，本页覆写） */
.standards-panel .tbl-foot {
  justify-content: space-between;
}

/* 页大小下拉：约束 min-width 防 flex 拉伸；antd selection-item 显式 14px，须 :deep 二段覆盖 */
.size-select {
  min-width: 88px;
  font-size: 12px;

  :deep(.ant-select-selection-item) {
    font-size: 12px;
  }
}

/* 下拉面板 teleport 到 body，scoped 触不到——popupClassName + :global 下探（同 LexiconPanel） */
:global(.pager-size-dd .ant-select-item) {
  font-size: 12px;
}
</style>

<style lang="less" src="./factory-ui.less"></style>
