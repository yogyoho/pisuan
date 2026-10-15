import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

import { splitMathText, mathToLatex } from '../../src/components/eia-data/expr_latex.js'

// 夹具取真实公式库：转换器跑在全部 7 条 expr 上，防「只对样例成立」
const here = path.dirname(fileURLToPath(import.meta.url))
const formulasPath = path.resolve(
  here,
  '../../../backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/formulas.json'
)
const exprs = JSON.parse(readFileSync(formulasPath, 'utf-8')).formulas.map((f) => f.expr)

test('切段无损：数学段/文本段按序拼接回原串', () => {
  for (const expr of exprs) {
    const segs = splitMathText(expr)
    assert.ok(segs.length > 0)
    assert.equal(segs.map((s) => s.text).join(''), expr)
  }
})

test('数学段不含 CJK，文本段至少保留一条中文注释（公式库实况）', () => {
  for (const expr of exprs) {
    const segs = splitMathText(expr)
    for (const seg of segs) {
      if (seg.math) assert.doesNotMatch(seg.text, /[\u4e00-\u9fff]/)
    }
    assert.ok(segs.some((s) => !s.math && /[\u4e00-\u9fff]/.test(s.text)))
  }
})

test('数学段转 LaTeX：伪数学符号全部消解、花括号配平、无下划线裸奔', () => {
  for (const expr of exprs) {
    for (const seg of splitMathText(expr)) {
      if (!seg.math) continue
      const tex = mathToLatex(seg.text)
      assert.doesNotMatch(tex, /[×÷√Σ±²³⁴⁶·−–αβγδσΔπη≈≤≥]/)
      assert.doesNotMatch(tex, /[\u4e00-\u9fff]/)
      let depth = 0
      for (const ch of tex.replaceAll(/\\[{}]/g, '')) {
        if (ch === '{') depth++
        else if (ch === '}') depth--
        assert.ok(depth >= 0, `花括号失衡: ${tex}`)
      }
      assert.equal(depth, 0, `花括号失衡: ${tex}`)
      assert.doesNotMatch(tex, /(^|[^\\])_(?!\{)/, `裸下划线: ${tex}`)
    }
  }
})

test('典型片段转换符合预期', () => {
  assert.match(mathToLatex('A×D·q'), /\\times .*\\cdot /)
  assert.match(mathToLatex('W_max_i'), /\\mathrm\{W\}_\{\\mathrm\{max\}\\_\\mathrm\{i\}\}/)
  assert.match(mathToLatex('10^(Li/10)'), /\^\{\(\\mathrm\{Li\}\/10\)\}/)
  assert.match(mathToLatex('Lw−20·lgr'), /\\lg /)
  assert.match(mathToLatex('Δatm'), /\\Delta \\mathrm\{atm\}/)
  assert.match(mathToLatex('Q·10⁶'), /10\^\{6\}/)
  assert.match(
    mathToLatex('exp(−Heff²/2σz²)'),
    /\\exp \(-\\mathrm\{Heff\}\^\{2\}\/2\\sigma z\^\{2\}\)/
  )
  assert.match(mathToLatex('2.68e-3'), /\\times 10\^\{-3\}/)
  assert.match(mathToLatex('√(1+0.0004x)'), /\\sqrt\{\(1\+0\.0004x\)\}/)
  assert.match(mathToLatex('√S'), /\\sqrt\{S\}/)
  assert.match(
    mathToLatex('Σsupply/Σdemand'),
    /\\sum _\{\\mathrm\{supply\}\}\/\\sum _\{\\mathrm\{demand\}\}/
  )
  assert.match(mathToLatex('Σ_i'), /\\sum _\{\\mathrm\{i\}\}/)
  assert.match(mathToLatex('tanβ_i'), /\\tan \\beta _\{\\mathrm\{i\}\}/)
  // 数据键名（多段下划线）整名直立呈现，禁被函数名前缀拆碎（tanβ…≠tan_beta…）
  assert.match(
    mathToLatex('q_repeat_mining/tan_beta_repeat_mining'),
    /\\mathrm\{q\}_\{\\mathrm\{repeat\}\\_\\mathrm\{mining\}\}\/\\mathrm\{tan\\_beta\\_repeat\\_mining\}/
  )
  assert.equal(mathToLatex('x^0.89'), 'x^{0.89}')
  assert.equal(mathToLatex('(aM+b)'), '(aM+b)')
})
