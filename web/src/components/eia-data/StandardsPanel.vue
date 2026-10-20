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
                    该标准无关联限值表（code_ref 未挂表）——限值录入在下方「限值查找表」卡进行
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

      <!-- 限值查找表（原型 s11：表 chips + 单表视图 + 整表替换编辑） -->
      <div class="card">
        <div class="card-hd">
          <h3>限值查找表</h3>
          <span class="hd-sub"
            >{{ tableEntries.length }} 表 · schema 驱动 · 整表替换语义 ·
            档位未录入达标判定输出「需人工对照」</span
          >
        </div>
        <div class="toolbar">
          <button
            v-for="[name, t] in tableEntries"
            :key="name"
            class="stage-chip"
            :class="{ on: activeTable === name }"
            @click="activeTable = name"
          >
            {{ t.desc }} <span class="cnt">{{ (t.rows || []).length }} 行</span>
          </button>
          <span style="flex: 1"></span>
          <span
            v-if="activeMeta"
            class="pill"
            :class="activeMeta.source === 'db' ? 'pill-orange' : 'pill-gray'"
            :title="
              activeMeta.source === 'db'
                ? 'DB 录入为导出真源，导出物化后写手可见'
                : '文件锚点态，导出前请先录入核实'
            "
            >{{ activeMeta.source === 'db' ? 'DB · 待导出' : '文件态' }}</span
          >
          <button
            v-if="userStore.isAdmin"
            class="btn btn-sec btn-sm"
            :disabled="!activeTable"
            @click="openLimitEdit(activeTable, activeMeta)"
          >
            {{ (activeMeta?.rows || []).length ? '编辑限值行' : '添加限值行' }}
          </button>
        </div>
        <table v-if="activeRows.length" class="tbl limit-tbl">
          <thead>
            <tr>
              <th v-for="(spec, k) in activeSchema" :key="k" :class="{ r: spec.type === 'number' }">
                {{ spec.label }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in activeRows" :key="i">
              <td v-for="(spec, k) in activeSchema" :key="k" :class="{ r: spec.type === 'number' }">
                <span :class="spec.type === 'number' ? 'mono num' : ''">{{ row[k] }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="limit-empty">
          <a-empty :description="`「${activeMeta?.desc || ''}」暂无限值行，录入后写手方可取值`" />
        </div>
        <p v-if="activeMeta?.note" class="limit-note" :title="activeMeta.note">
          {{ activeMeta.note }}
        </p>
        <div class="tbl-foot">
          整表替换语义：保存即以 DB 为导出真源全量替换；导出以 (table_key, id) 全序重写 rows
          数组并翻转核验标记；空表拒绝导出
        </div>
      </div>

      <!-- 提取草稿（原型 2026-10-19 Card 1：语料自动提取 · 暂存行逐行核实转正） -->
      <div class="card">
        <div class="card-hd">
          <h3>提取草稿</h3>
          <span class="hd-sub">语料自动提取 · 逐行核实后进入正式表 · 已裁决行不再复生</span>
          <div class="hd-right">
            <span v-if="extractReport" class="report-pill" title="上次提取报告">
              上次：<b>{{ extractReport.files_scanned }}</b> 文件 · 聚合
              <b>{{ extractReport.aggregated }}</b> · 插入 <b>{{ extractReport.inserted }}</b> ·
              跳过 <b>{{ extractReport.skipped }}</b>
            </span>
            <button
              v-if="userStore.isAdmin"
              class="btn btn-sec btn-sm"
              :disabled="extracting"
              @click="onRunExtract"
            >
              <RefreshCw :size="13" :class="{ spin: extracting }" />
              {{ extracting ? '提取中…' : '重新提取' }}
            </button>
          </div>
        </div>
        <div class="toolbar">
          <button
            v-for="g in extractGroups"
            :key="g.key"
            class="stage-chip"
            :class="{ on: activeExtractTable === g.key }"
            @click="activeExtractTable = g.key"
          >
            {{ g.label }} <span class="cnt">{{ g.rows.length }} 行待裁决</span>
          </button>
          <span style="flex: 1"></span>
          <span class="pill pill-gray">仅 pending · 共 {{ extractRows.length }} 行</span>
        </div>
        <table v-if="activeExtractRows.length" class="tbl extract-tbl">
          <thead>
            <tr>
              <th style="width: 30px"></th>
              <th
                v-for="col in extractColumns"
                :key="col.key"
                :class="{ r: col.type === 'number' }"
              >
                {{ col.label }}
              </th>
              <th>置信</th>
              <th>状态</th>
              <th style="width: 150px">操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="r in activeExtractRows" :key="r.id">
              <tr>
                <td>
                  <button
                    class="expander"
                    :aria-label="`展开来源 ${r.sources?.length || 0} 条`"
                    @click="toggleExtractSub(r.id)"
                  >
                    <ChevronRight :size="14" :class="{ open: expandedExtractIds.includes(r.id) }" />
                  </button>
                </td>
                <td
                  v-for="col in extractColumns"
                  :key="col.key"
                  :class="{ r: col.type === 'number' }"
                >
                  <span :class="typeof extractCell(r, col.key) === 'number' ? 'mono num' : ''">{{
                    extractCell(r, col.key)
                  }}</span>
                </td>
                <td>
                  <div class="cell-main">
                    <span class="pill" :class="confPillClass(r.confidence)">
                      {{ r.confidence
                      }}<template v-if="r.confidence === 'multi'"> ·{{ sourceCount(r) }}</template>
                    </span>
                    <div v-if="conflictValues(r).length" class="conf-chips">
                      <code v-for="v in conflictValues(r)" :key="v" class="k">{{ v }}</code>
                    </div>
                  </div>
                </td>
                <td><span class="pill pill-warn">待裁决</span></td>
                <td>
                  <button
                    class="btn btn-txt btn-sm"
                    :disabled="isCandidateRow(r) || r.confidence === 'conflict'"
                    :title="
                      isCandidateRow(r) ? '候选表行须先立表迁移再裁决' : '存在冲突值，须先编辑消解'
                    "
                    @click="openConfirmRow(r)"
                  >
                    确认
                  </button>
                  <button
                    class="btn btn-txt btn-sm"
                    :disabled="isCandidateRow(r)"
                    :title="isCandidateRow(r) ? '候选表行须先立表迁移再裁决' : ''"
                    @click="openEditRow(r)"
                  >
                    编辑
                  </button>
                  <button class="btn btn-txt btn-sm danger" @click="onDiscardRow(r)">丢弃</button>
                </td>
              </tr>
              <tr v-if="expandedExtractIds.includes(r.id)" class="sub-row">
                <td :colspan="extractColumns.length + 4">
                  <div class="src-list">
                    <div v-for="(s, i) in r.sources || []" :key="i" class="src-item">
                      <FileText :size="13" />
                      <span class="mono">{{ s.report_id }}</span>
                      <span v-if="sourceStage(s)" class="pill pill-gray s-stage">{{
                        sourceStage(s)
                      }}</span>
                      <span class="s-anchor">{{ s.anchor }}</span>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
        <div v-else class="empty-state">
          <a-empty
            :description="
              extractRows.length
                ? '当前表暂无待裁决行'
                : '暂无待裁决草稿 · 管理员点击「重新提取」扫描语料'
            "
          />
        </div>
        <div class="tbl-foot">
          确认/编辑转正写入正式表，导出物化后写手可见；丢弃行打 discarded 标记，重跑提取不复生
        </div>
      </div>

      <!-- 新表候选（原型 2026-10-19 Card 2：不在册标准号 → 立表迁移） -->
      <div class="card">
        <div class="card-hd">
          <h3>新表候选</h3>
          <span class="hd-sub">提取发现不在册的表 → 立表后自动迁入正式限值表清单</span>
          <div class="hd-right">
            <span v-if="candidates.length" class="pill pill-gray">
              {{ candidates.length }} 个候选 · {{ candidatePendingCount }} 行 pending
            </span>
          </div>
        </div>
        <div v-if="candidates.length" class="cand-grid">
          <div v-for="c in candidates" :key="c.candidate_key" class="cand-card">
            <div class="cand-key">
              <div class="cand-ic"><AlertTriangle :size="16" /></div>
              <div class="cand-title-wrap">
                <div class="cand-title" :title="candidateCode(c)">{{ candidateCode(c) }}</div>
                <div class="cand-code mono">{{ c.candidate_key }}</div>
              </div>
            </div>
            <div class="cand-meta">
              <span class="pill pill-orange">{{ c.count }} 行待裁决</span>
            </div>
            <div class="fact-list">
              <code v-for="f in candidateFactors(c).shown" :key="f" class="k">{{ f }}</code>
              <code v-if="candidateFactors(c).overflow" class="k"
                >+{{ candidateFactors(c).overflow }}</code
              >
            </div>
            <div class="cand-ft">
              <button class="btn btn-sec btn-sm" @click="onIgnoreCandidate(c)">忽略</button>
              <button v-if="userStore.isAdmin" class="btn btn-pri btn-sm" @click="openRegister(c)">
                立表
              </button>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">
          <a-empty description="暂无新表候选 · 提取发现不在册标准号时在此出现" />
        </div>
        <div class="tbl-foot">
          候选行在未立表前保持 pending；立表（admin）后按 (code, table_key)
          迁入正式表并从候选消失；忽略不可恢复
        </div>
      </div>
    </template>

    <div class="note-bar">
      <Info :size="14" />
      <span
        >体检命不上模式的编号经核实通道人工登记修正；限值行按表 schema
        分型校验（str/number、必填），写手按 (标准号, 参数) 取值。</span
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

    <!-- 限值行编辑对话框（整表替换保存） -->
    <a-modal
      v-model:open="editDlg.open"
      :title="`限值录入 · ${editDlg.tableMeta?.desc ?? ''}`"
      :confirm-loading="editDlg.submitting"
      :width="720"
      ok-text="保存录入"
      @ok="onSaveRows"
    >
      <p class="rows-editor-sub">
        整表替换保存（DB 即导出真源）；数值字段对照标准原文录入纯数字，禁带区间或文字。
      </p>
      <table class="rows-edit-table">
        <thead>
          <tr>
            <th v-for="(spec, k) in editFields" :key="k">{{ spec.label }}</th>
            <th class="op-col">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in editDlg.rows" :key="i">
            <td v-for="(spec, k) in editFields" :key="k">
              <a-input-number
                v-if="spec.type === 'number'"
                v-model:value="row[k]"
                style="width: 100%"
              />
              <a-input v-else v-model:value="row[k]" />
            </td>
            <td class="op-col"><a class="danger" @click="editDlg.rows.splice(i, 1)">删除</a></td>
          </tr>
        </tbody>
      </table>
      <a-button size="small" @click="addBlankRow">＋ 添加一行</a-button>
    </a-modal>

    <!-- 提取行编辑弹层（M1，schema 驱动；保存 = 以编辑后值转正） -->
    <a-modal
      v-model:open="editRowDlg.open"
      :title="`编辑草稿行 · ${extractGroupLabel(editRowDlg.row?.table_key)}${extractFactor(editRowDlg.row) ? ' · ' + extractFactor(editRowDlg.row) : ''}`"
      :confirm-loading="editRowDlg.submitting"
      ok-text="保存并转正"
      @ok="onSubmitEditRow"
    >
      <div class="frm-grid">
        <div v-for="f in editRowFields" :key="f.key" class="frm-row">
          <label>{{ f.label }}</label>
          <a-input-number
            v-if="f.type === 'number'"
            v-model:value="editRowDlg.form[f.key]"
            style="width: 100%"
          />
          <a-input v-else v-model:value="editRowDlg.form[f.key]" />
        </div>
      </div>
      <div class="frm-row">
        <label>裁决备注</label>
        <a-textarea v-model:value="editRowDlg.note" :rows="2" placeholder="仅平台库留档（可选）" />
      </div>
      <div class="frm-help">
        保存并转正 = 以编辑后值写入正式表 {{ editRowDlg.row?.table_key }}，原暂存行转
        edited；冲突行编辑后冲突标记自动消解
      </div>
    </a-modal>

    <!-- 确认转正弹层（M2：红线提示 + 行摘要 + 备注） -->
    <a-modal
      v-model:open="confirmRowDlg.open"
      title="确认转正 · 写入正式表"
      :confirm-loading="confirmRowDlg.submitting"
      ok-text="确认转正"
      @ok="onSubmitConfirmRow"
    >
      <div class="redline-box">
        <span class="redline-title">转正语义（红线）</span>
        该行将写入正式限值表 <strong>{{ confirmRowDlg.row?.table_key }}</strong
        >，导出物化后写手可见；已裁决行重跑提取不再复生。
      </div>
      <div class="sum-box">
        <div v-for="line in confirmRowLines" :key="line.label" class="sum-line">
          <b>{{ line.label }}</b>
          <span :class="typeof line.value === 'number' ? 'mono num' : ''">{{
            line.value === null || line.value === undefined || line.value === '' ? '—' : line.value
          }}</span>
        </div>
        <div class="sum-line">
          <b>来源</b>
          <span class="mono">{{ confirmRowSources || '—' }}</span>
        </div>
      </div>
      <div class="frm-row">
        <label>裁决备注</label>
        <a-textarea
          v-model:value="confirmRowDlg.note"
          :rows="2"
          placeholder="仅平台库留档（可选）"
        />
      </div>
    </a-modal>

    <!-- 候选立表弹层（M3：注册元数据 + 列结构编辑器） -->
    <a-modal
      v-model:open="regDlg.open"
      :title="`立表 · ${regDlg.candidateKey}`"
      :confirm-loading="regDlg.submitting"
      :width="640"
      ok-text="确认立表"
      @ok="onRegisterSubmit"
    >
      <div class="frm-grid">
        <div class="frm-row">
          <label>关联标准编号</label>
          <a-input v-model:value="regDlg.code" />
        </div>
        <div class="frm-row">
          <label>table_key</label>
          <a-input v-model:value="regDlg.tableKey" />
          <div class="frm-help mono">^[a-z0-9_]+$ · 与注册表 / 既有表查重</div>
        </div>
      </div>
      <div class="frm-row">
        <label>描述</label>
        <a-input v-model:value="regDlg.desc" />
      </div>
      <div class="frm-row">
        <label>列结构（按候选行 col_* 键预填，可增删改）</label>
        <table class="schema-tbl">
          <thead>
            <tr>
              <th>列键</th>
              <th>显示名</th>
              <th style="width: 92px">类型</th>
              <th style="width: 52px">必填</th>
              <th style="width: 30px"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(c, i) in regDlg.cols" :key="`${c.key}-${i}`">
              <td>
                <code v-if="!c.custom" class="k">{{ c.key }}</code>
                <a-input v-else v-model:value="c.key" size="small" />
              </td>
              <td><a-input v-model:value="c.label" size="small" /></td>
              <td>
                <select v-model="c.type" class="inp reg-type-sel">
                  <option value="number">number</option>
                  <option value="str">str</option>
                </select>
              </td>
              <td class="reg-req"><input v-model="c.required" type="checkbox" /></td>
              <td class="reg-del">
                <button
                  class="btn btn-txt btn-sm danger"
                  aria-label="删除列"
                  @click="regDlg.cols.splice(i, 1)"
                >
                  ×
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <button class="btn btn-sec btn-sm reg-add-col" @click="addRegCol">＋ 添加列</button>
      </div>
      <div class="frm-help">
        立表后该候选全部 pending 行按新 table_key
        迁入正式表并从候选清单消失；首个因子列沿用行内「因子」键
      </div>
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
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  AlertTriangle,
  ChevronRight,
  FileText,
  Info,
  RefreshCw,
  Search,
  ShieldCheck
} from '@lucide/vue'
import { eiaStandardApi } from '@/apis/eia_standard_api'
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
const schemas = ref({})
const gate1 = ref(null)
const filters = reactive({ state: '', q: '' })
// 限值表单表视图：chips 切换当前表（原型 s11 单表视图）
const activeTable = ref('')

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

// 限值行列头取服务端 schemas（字段顺序与中文标签权威）；schemas 缺席时回退首行键
const rowKeys = (name, t) => {
  const s = schemas.value[name]
  if (s) return Object.keys(s)
  return Object.keys(t.rows?.[0] || {}).filter((k) => k !== 'origin')
}

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

// ── 限值表单表视图 ──────────────────────────────────────

const tableEntries = computed(() =>
  Object.entries(limitTables.value).filter(([, v]) => typeof v === 'object' && v !== null)
)
const activeMeta = computed(() => limitTables.value[activeTable.value] || null)
const activeSchema = computed(() => schemas.value[activeTable.value] || {})
const activeRows = computed(() => {
  const t = activeMeta.value
  if (!t) return []
  // schema 缺席时回退首行键投影（与 rowKeys 同一兜底）
  if (schemas.value[activeTable.value]) return t.rows || []
  const keys = rowKeys(activeTable.value, t)
  return (t.rows || []).map((r) => Object.fromEntries(keys.map((k) => [k, r[k]])))
})

const fetchList = async () => {
  loading.value = true
  try {
    const [data, limits, gate1Data] = await Promise.all([
      eiaStandardApi.listStandards(),
      eiaStandardApi.listLimits(),
      eiaStandardApi.getGate1().catch(() => null) // 体检卡独立降级：不阻塞标准表主链
    ])
    items.value = data.items
    schemas.value = limits.schemas || {}
    limitTables.value = Object.fromEntries(
      Object.entries(limits.limit_tables).filter(([, v]) => typeof v === 'object' && v !== null)
    )
    gate1.value = gate1Data
    // 首次装载缺省选中第一张表；刷新后当前选中表被裁剪则回落
    if (!limitTables.value[activeTable.value]) {
      activeTable.value = tableEntries.value[0]?.[0] ?? ''
    }
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

// ── 限值行编辑对话框（整表替换保存）──────────────────────

const dbTableCount = computed(
  () => Object.values(limitTables.value).filter((t) => t.source === 'db').length
)

const editDlg = reactive({
  open: false,
  submitting: false,
  tableKey: '',
  tableMeta: null,
  rows: []
})
const editFields = computed(() => schemas.value[editDlg.tableKey] || {})

const addBlankRow = () => {
  const blank = {}
  for (const [k, spec] of Object.entries(editFields.value))
    blank[k] = spec.type === 'number' ? null : ''
  editDlg.rows.push(blank)
}

const openLimitEdit = (name, t) => {
  editDlg.tableKey = name
  editDlg.tableMeta = t
  // 按 schema 投影装载：文件锚点行携带的 origin 等溯源字段不进编辑器（服务端校验拒收）
  const fields = schemas.value[name] || {}
  editDlg.rows = (t.rows || []).map((r) =>
    Object.fromEntries(
      Object.entries(fields).map(([k, spec]) => [k, r[k] ?? (spec.type === 'number' ? null : '')])
    )
  )
  if (!editDlg.rows.length) addBlankRow()
  editDlg.open = true
}

const onSaveRows = async () => {
  editDlg.submitting = true
  try {
    const r = await eiaStandardApi.saveLimitRows(editDlg.tableKey, editDlg.rows)
    message.success(
      `「${editDlg.tableMeta?.desc || editDlg.tableKey}」已保存 ${r.saved} 行（导出物化后生效）`
    )
    editDlg.open = false
    await fetchList()
  } catch (e) {
    message.error(e?.message || '限值行保存失败')
  } finally {
    editDlg.submitting = false
  }
}

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

// ── 提取草稿与新表候选（spec 2026-10-19；加载失败静默降级，不阻塞面板主链）──

const CANDIDATE_PREFIX = '__candidate__:'

const extractRows = ref([])
const extractReport = ref(null)
const candidates = ref([])
const activeExtractTable = ref('')
const extracting = ref(false)
const expandedExtractIds = ref([])

const isCandidateRow = (r) => (r?.table_key || '').startsWith(CANDIDATE_PREFIX)
// sources 锚点形如 `{stage}/{切片名}`，阶段 pill 取锚点首段
const sourceStage = (s) => (s?.anchor || '').split('/')[0]
const sourceCount = (r) => new Set((r.sources || []).map((s) => s.report_id)).size
const conflictValues = (r) => (Array.isArray(r?.row?.conflict_values) ? r.row.conflict_values : [])
const extractCell = (r, k) => {
  const v = r?.row?.[k]
  return v === null || v === undefined || v === '' ? '—' : v
}
const confPillClass = (c) =>
  ({ multi: 'pill-ok', single: 'pill-gray', conflict: 'pill-err' })[c] || 'pill-gray'
// 因子摘要：在册表取 pollutant，候选表取首个非空字符串列值
const extractFactor = (r) =>
  r?.row?.pollutant ||
  Object.values(r?.row || {}).find((v) => typeof v === 'string' && v.trim()) ||
  ''

const extractGroupLabel = (tableKey) => {
  if (!tableKey) return ''
  if (tableKey.startsWith(CANDIDATE_PREFIX)) return tableKey.slice(CANDIDATE_PREFIX.length)
  return limitTables.value[tableKey]?.desc || tableKey
}

const extractGroups = computed(() => {
  const map = new Map()
  for (const r of extractRows.value) {
    if (!map.has(r.table_key)) map.set(r.table_key, [])
    map.get(r.table_key).push(r)
  }
  return [...map.entries()].map(([key, rows]) => ({ key, rows, label: extractGroupLabel(key) }))
})

const ensureActiveExtractTable = () => {
  if (!extractRows.value.some((r) => r.table_key === activeExtractTable.value))
    activeExtractTable.value = extractGroups.value[0]?.key ?? ''
}

const activeExtractRows = computed(
  () => extractGroups.value.find((g) => g.key === activeExtractTable.value)?.rows ?? []
)

// 列头 schema 驱动：在册表用 listLimits schemas；候选表按 row col_* 键平铺（全数值列推断为 number）
const extractColumns = computed(() => {
  const key = activeExtractTable.value
  const schema = schemas.value[key]
  if (schema)
    return Object.entries(schema).map(([k, s]) => ({ key: k, label: s.label, type: s.type }))
  const rows = activeExtractRows.value
  const keys = []
  for (const r of rows)
    for (const k of Object.keys(r.row || {}))
      if (k.startsWith('col_') && !keys.includes(k)) keys.push(k)
  return keys.map((k) => {
    const vals = rows
      .map((r) => r.row?.[k])
      .filter((v) => v !== undefined && v !== null && v !== '')
    return {
      key: k,
      label: k.slice(4),
      type: vals.length > 0 && vals.every((v) => typeof v === 'number') ? 'number' : 'str'
    }
  })
})

const loadExtract = async () => {
  try {
    const [rowsData, candData] = await Promise.all([
      eiaStandardApi.listExtractRows({ status: 'pending' }),
      eiaStandardApi.listCandidates()
    ])
    extractRows.value = rowsData.rows || []
    candidates.value = candData.candidates || []
    ensureActiveExtractTable()
  } catch (e) {
    console.warn('[StandardsPanel] 提取草稿/候选加载失败，区块降级为空:', e)
  }
}

const onRunExtract = async () => {
  extracting.value = true
  message.loading({
    content: '正在全库扫描提取限值（约 40 秒+）…',
    key: 'limit-extract',
    duration: 0
  })
  try {
    const r = await eiaStandardApi.runExtract()
    extractReport.value = r
    message.success({ content: `提取完成：插入 ${r.inserted} 行`, key: 'limit-extract' })
    await Promise.all([loadExtract(), fetchList()])
  } catch (e) {
    message.error({ content: e?.message || '提取失败', key: 'limit-extract' })
  } finally {
    extracting.value = false
  }
}

const toggleExtractSub = (id) => {
  expandedExtractIds.value = expandedExtractIds.value.includes(id)
    ? expandedExtractIds.value.filter((x) => x !== id)
    : [...expandedExtractIds.value, id]
}

const removeExtractRow = (id) => {
  extractRows.value = extractRows.value.filter((r) => r.id !== id)
  ensureActiveExtractTable()
}

// 编辑草稿行（M1）：在册表 schema 驱动字段（候选表行不可编辑，入口已禁用）
const editRowDlg = reactive({ open: false, submitting: false, row: null, form: {}, note: '' })

const editRowFields = computed(() => {
  const schema = schemas.value[editRowDlg.row?.table_key] || {}
  return Object.entries(schema).map(([k, s]) => ({ key: k, label: s.label, type: s.type }))
})

const openEditRow = (r) => {
  const schema = schemas.value[r.table_key] || {}
  editRowDlg.row = r
  editRowDlg.form = Object.fromEntries(
    Object.entries(schema).map(([k, s]) => [k, r.row?.[k] ?? (s.type === 'number' ? null : '')])
  )
  editRowDlg.note = ''
  editRowDlg.open = true
}

const submitRowDecision = async (row, payload, successText) => {
  await eiaStandardApi.decideExtractRow(row.id, payload)
  message.success(successText)
  removeExtractRow(row.id)
}

const onSubmitEditRow = async () => {
  editRowDlg.submitting = true
  try {
    await submitRowDecision(
      editRowDlg.row,
      { action: 'edited', row_json: { ...editRowDlg.form }, note: editRowDlg.note || null },
      '已保存并转正（导出物化后写手可见）'
    )
    editRowDlg.open = false
    await fetchList()
  } catch (e) {
    message.error(e?.message || '编辑转正失败')
  } finally {
    editRowDlg.submitting = false
  }
}

// 确认转正（M2）：红线提示 + 行摘要 + 备注
const confirmRowDlg = reactive({ open: false, submitting: false, row: null, note: '' })

const confirmRowLines = computed(() => {
  const r = confirmRowDlg.row
  if (!r) return []
  const schema = schemas.value[r.table_key]
  const entries = schema
    ? Object.entries(schema)
    : Object.keys(r.row || {})
        .filter((k) => k !== 'conflict_values')
        .map((k) => [k, { label: k }])
  return entries.map(([k, s]) => ({ label: s.label || k, value: r.row?.[k] ?? null }))
})

const confirmRowSources = computed(() =>
  [...new Set((confirmRowDlg.row?.sources || []).map((s) => s.report_id))].join(' · ')
)

const openConfirmRow = (r) => {
  confirmRowDlg.row = r
  confirmRowDlg.note = ''
  confirmRowDlg.open = true
}

const onSubmitConfirmRow = async () => {
  confirmRowDlg.submitting = true
  try {
    await submitRowDecision(
      confirmRowDlg.row,
      { action: 'confirm', note: confirmRowDlg.note || null },
      `已转正写入 ${confirmRowDlg.row.table_key}（导出物化后写手可见）`
    )
    confirmRowDlg.open = false
    await fetchList()
  } catch (e) {
    message.error(e?.message || '转正失败')
  } finally {
    confirmRowDlg.submitting = false
  }
}

const onDiscardRow = (r) => {
  Modal.confirm({
    title: '丢弃该草稿行？',
    content: '丢弃行打 discarded 标记，不可恢复；重跑提取不再复生。',
    okText: '丢弃',
    okType: 'danger',
    cancelText: '取消',
    onOk: () =>
      submitRowDecision(r, { action: 'discarded' }, '已丢弃 1 行').catch((e) =>
        message.error(e?.message || '丢弃失败')
      )
  })
}

// 新表候选（Card 2）：因子清单去重前 6 + 忽略 / 立表
const candidatePendingCount = computed(() =>
  candidates.value.reduce((sum, c) => sum + (c.count || 0), 0)
)

const candidateCode = (c) => c.rows?.[0]?.code || c.candidate_key.slice(CANDIDATE_PREFIX.length)

const candidateFactors = (c) => {
  const seen = []
  for (const r of c.rows || []) {
    const v = extractFactor(r)
    if (v && !seen.includes(v)) seen.push(v)
  }
  return { shown: seen.slice(0, 6), overflow: Math.max(seen.length - 6, 0) }
}

const onIgnoreCandidate = (c) => {
  Modal.confirm({
    title: `忽略候选 ${c.candidate_key}？`,
    content: `该候选 ${c.count} 行 pending 将全部转 discarded，不可恢复；重跑提取不再复生。`,
    okText: '忽略',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      try {
        await Promise.all(
          (c.rows || []).map((r) => eiaStandardApi.decideExtractRow(r.id, { action: 'discarded' }))
        )
        message.success(`已忽略：${c.count} 行全部转 discarded`)
        await loadExtract()
      } catch (e) {
        message.error(e?.message || '忽略失败')
        await loadExtract()
      }
    }
  })
}

// 候选立表（M3）：元数据 + 列结构编辑器（列键预填 readonly，新增列可编辑键名）
const regDlg = reactive({
  open: false,
  submitting: false,
  candidateKey: '',
  code: '',
  tableKey: '',
  desc: '',
  cols: []
})

const openRegister = (c) => {
  const rows = c.rows || []
  const keys = []
  for (const r of rows)
    for (const k of Object.keys(r.row || {}))
      if (k.startsWith('col_') && !keys.includes(k)) keys.push(k)
  const code = candidateCode(c)
  regDlg.candidateKey = c.candidate_key
  regDlg.code = code
  regDlg.tableKey = code
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
  regDlg.desc = `${code} · ${keys.map((k) => k.slice(4)).join('/')}`
  regDlg.cols = keys.map((k) => {
    const vals = rows
      .map((r) => r.row?.[k])
      .filter((v) => v !== undefined && v !== null && v !== '')
    return {
      key: k,
      label: k.slice(4),
      type: vals.length > 0 && vals.every((v) => typeof v === 'number') ? 'number' : 'str',
      required: true,
      custom: false
    }
  })
  regDlg.open = true
}

const addRegCol = () => {
  let i = regDlg.cols.length + 1
  while (regDlg.cols.some((c) => c.key === `col_extra_${i}`)) i += 1
  regDlg.cols.push({ key: `col_extra_${i}`, label: '', type: 'str', required: true, custom: true })
}

const onRegisterSubmit = async () => {
  if (!regDlg.code.trim()) {
    message.warning('请填写关联标准编号')
    return
  }
  const tableKey = regDlg.tableKey.trim()
  if (!/^[a-z0-9_]+$/.test(tableKey)) {
    message.warning('table_key 须匹配 ^[a-z0-9_]+$')
    return
  }
  const cols = regDlg.cols.filter((c) => c.key.trim())
  if (!cols.length) {
    message.warning('至少保留一列')
    return
  }
  if (new Set(cols.map((c) => c.key.trim())).size !== cols.length) {
    message.warning('存在重复列键，请修正后再提交')
    return
  }
  regDlg.submitting = true
  try {
    const r = await eiaStandardApi.registerCandidate({
      code: regDlg.code.trim(),
      table_key: tableKey,
      desc: regDlg.desc.trim(),
      columns_schema: Object.fromEntries(
        cols.map((c) => [
          c.key.trim(),
          { label: c.label.trim() || c.key.slice(4), type: c.type, required: c.required }
        ])
      )
    })
    message.success(`已立表并迁移 ${r.migrated} 行`)
    regDlg.open = false
    await Promise.all([loadExtract(), fetchList()])
  } catch (e) {
    message.error(e?.message || '候选立表失败')
  } finally {
    regDlg.submitting = false
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

onMounted(() => {
  fetchList()
  loadExtract()
})
</script>

<style lang="less" scoped>
.standards-panel {
  --hairline: var(--gray-200);
}

/* 清单表列宽固定（标准名/备注为长文本），同 s9/s10 结论；限值表字段短改回自动 */
.standards-panel .tbl {
  table-layout: fixed;

  td {
    overflow-wrap: break-word;
  }
}

.limit-tbl,
.extract-tbl {
  table-layout: auto;
}

.limit-empty {
  padding: 40px 0;
}

.limit-note {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--gray-400);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

/* ── 限值行编辑对话框 ───────────────────────────────── */
.rows-editor-sub {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--gray-500);
}

.rows-edit-table {
  width: 100%;
  margin-bottom: 10px;
  border-collapse: collapse;

  th,
  td {
    padding: 4px 6px;
    border: 1px solid var(--hairline);
  }

  th {
    font-size: 12px;
    font-weight: 600;
    color: var(--gray-600);
    background: var(--gray-50);
    text-align: left;
  }

  td {
    color: var(--gray-800);
  }

  .op-col {
    width: 48px;
    text-align: center;
  }

  a.danger {
    color: var(--second-600);
    font-size: 12px;
  }
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

/* ── 提取草稿（原型 2026-10-19 Card 1）────────────────── */
.report-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 22px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px dashed var(--gray-300);
  color: var(--gray-500);
  white-space: nowrap;

  b {
    color: var(--gray-600);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
}

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

.src-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  background: var(--gray-0);
  font-size: 12px;
  color: var(--gray-600);

  svg {
    flex: none;
    color: var(--gray-500);
  }

  .s-stage {
    flex: none;
  }

  .s-anchor {
    margin-left: auto;
    font-family: ui-monospace, 'Cascadia Code', Consolas, 'Courier New', monospace;
    font-size: 11px;
    color: var(--gray-500);
  }
}

.conf-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;

  code.k {
    background: var(--color-error-50);
    color: var(--color-error-700);
  }
}

.cell-main {
  display: flex;
  flex-direction: column;
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

/* ── 新表候选（原型 2026-10-19 Card 2）────────────────── */
.cand-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
  gap: 10px;
  padding: 14px 16px;
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

.fact-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;

  code.k {
    font-size: 11px;
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

.sum-box {
  margin-bottom: 16px;
  padding: 10px 12px;
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  background: var(--gray-25, var(--gray-50));
  font-size: 13px;

  .sum-line {
    display: flex;
    gap: 8px;
    padding: 2px 0;

    b {
      min-width: 52px;
      flex: none;
      font-weight: 600;
      color: var(--gray-800);
    }

    span {
      color: var(--gray-600);
      word-break: break-all;
    }
  }
}

.schema-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;

  th {
    padding: 4px 6px;
    border-bottom: 1px solid var(--gray-200);
    font-size: 11px;
    font-weight: 500;
    color: var(--gray-500);
    text-align: left;
  }

  td {
    padding: 5px 6px;
    border-bottom: 1px solid var(--gray-100);

    code.k {
      font-size: 11px;
    }
  }

  .reg-type-sel {
    width: 100%;
    height: 26px;
    padding: 0 4px;
    font-size: 12px;
  }

  .reg-req {
    text-align: center;

    input[type='checkbox'] {
      width: 15px;
      height: 15px;
      accent-color: var(--main-600);
    }
  }

  .reg-del {
    text-align: center;
  }
}

.reg-add-col {
  margin-top: 8px;
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
