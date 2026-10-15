// 伪数学 expr → LaTeX 段落切分与转换（FormulasPanel 黑框公式 KaTeX 排版用）
//
// formulas.json 的 expr 是伪数学串：ASCII 数学式与中文注释（×−·√Σ、全角括号分号、~）混排，
// 不能整串交给 KaTeX。这里切成「数学段 / 文本段」交替序列：
//   文本段（CJK/全角/…/~）由调用方原样输出，享受块内自然换行；
//   数学段经 mathToLatex 消解伪数学符号后交给 KaTeX 内联排版。
// 纯函数模块，供 node --test 直接单测（exprLatex.test.js 夹具为公式库全量 expr）。

// 伪数学符号 → LaTeX。未知符号不在此表 → 原样进入 KaTeX → 抛错 → 调用方回落 token 视图。
const SYM_MAP = {
  '×': '\\times ',
  '·': ' \\cdot ',
  '−': '-',
  '±': '\\pm ',
  '√': '\\sqrt',
  Σ: '\\sum ',
  α: '\\alpha ',
  β: '\\beta ',
  Δ: '\\Delta ',
  σ: '\\sigma ',
  π: '\\pi ',
  '²': '^{2}',
  '⁴': '^{4}',
  '⁶': '^{6}'
}

// 函数名前缀识别（lgr → lg r）。词中含下划线时是数据键名，不走此表（tan_beta… ≠ tan β…）
const FUNCS = ['exp', 'log', 'lg', 'ln', 'cos', 'sin', 'tan', 'max', 'min']

const isTextCh = (ch) => /[\u{4e00}-\u{9fff}\u{3000}-\u{303f}\u{ff00}-\u{ffef}\u{2026}~]/u.test(ch)

// expr → [{ math, text }]，拼接无损
export const splitMathText = (expr) => {
  const segs = []
  let buf = ''
  let bufMath = null
  for (const ch of expr) {
    const math = !isTextCh(ch)
    if (math !== bufMath) {
      if (buf) segs.push({ math: bufMath, text: buf })
      buf = ''
      bufMath = math
    }
    buf += ch
  }
  if (buf) segs.push({ math: bufMath, text: buf })
  return segs
}

// ^ 或 _ 的组：{...} 原样取、(...) 平衡取、其余取连续字母/数字/点（^0.89、_i）
const takeGroup = (s, i) => {
  const c = s[i]
  if (c === '{') {
    const j = s.indexOf('}', i)
    return [s.slice(i, j + 1), j + 1]
  }
  if (c === '(') {
    let depth = 0
    let j = i
    for (; j < s.length; j++) {
      if (s[j] === '(') depth++
      else if (s[j] === ')' && --depth === 0) break
    }
    return [s.slice(i, j + 1), j + 1]
  }
  const m = /^[\w.]+/.exec(s.slice(i))
  return m ? [m[0], i + m[0].length] : ['', i]
}

// 数学段 → LaTeX：
// - 下划线链是数据键名/符号下标：首段单字母按「基符号+下标」转换（W_max_i → \mathrm{W}_{\mathrm{max}\_i}），
//   多字母整名直立（tan_beta_repeat_mining → \mathrm{tan\_beta\_repeat\_mining}），禁被函数名拆碎
// - 2.68e-3 → \times 10^{-3}；10^(Li/10) → 10^{(Li/10)}；√ 取紧随组
export const mathToLatex = (src) => {
  let out = ''
  let i = 0
  while (i < src.length) {
    const ch = src[i]
    if (SYM_MAP[ch]) {
      if (ch === '√') {
        const [raw, next] = takeGroup(src, i + 1)
        out += `\\sqrt{${mathToLatex(raw)}}`
        i = next
        continue
      }
      if (ch === 'Σ') {
        out += '\\sum '
        const m = /^[A-Za-z]\w*/.exec(src.slice(i + 1))
        if (m) {
          out += `_{\\mathrm{${m[0]}}}`
          i += 1 + m[0].length
        } else {
          i++
        }
        continue
      }
      out += SYM_MAP[ch]
      i++
      continue
    }
    if (ch === '_' || ch === '^') {
      // _ 连续链合并进同一下标组（KaTeX 不接受连续下标），段间以 \_ 连接
      if (ch === '_') {
        const parts = []
        let j = i
        while (src[j] === '_') {
          const m = /^[\w.]+/.exec(src.slice(j + 1))
          if (!m) break
          parts.push(m[0])
          j += 1 + m[0].length
        }
        if (parts.length) {
          out += `_{${parts.map((p) => `\\mathrm{${p}}`).join('\\_')}}`
          i = j
          continue
        }
      }
      const [raw, next] = takeGroup(src, i + 1)
      if (raw) {
        out += `^{${mathToLatex(raw)}}`
        i = next
        continue
      }
    }
    if (/[A-Za-z]/.test(ch)) {
      const m = /^[A-Za-z][\w]*(?:_[\w]+)*/.exec(src.slice(i))
      const w = m[0]
      if (w.includes('_')) {
        // 键名链：首段单字母 → 基符号+合并下标；多字母 → 整名直立
        const [head, rest] = w.split(/(?<=^[^_]+)_/)
        if (head.length === 1) {
          const parts = rest.split('_')
          out += `\\mathrm{${head}}_{${parts.map((p) => `\\mathrm{${p}}`).join('\\_')}}`
        } else {
          out += `\\mathrm{${w.replaceAll('_', '\\_')}}`
        }
        i += w.length
        continue
      }
      const fn = FUNCS.find(
        (f) => w.startsWith(f) && (w.length === f.length || w.length - f.length <= 3)
      )
      if (fn) {
        out += `\\${fn} `
        if (w.length === fn.length) {
          i += w.length
          continue
        }
        out += mathToLatex(w.slice(fn.length))
        i += w.length
        continue
      }
      // 多字母符号直立；小写→大写边界视为两因子相邻（aM = a·M），拆开并列
      const factors = w.split(/(?<=[a-z])(?=[A-Z])/)
      out +=
        factors.length > 1
          ? factors.map((p) => (p.length === 1 ? p : `\\mathrm{${p}}`)).join('')
          : w.length === 1
            ? w
            : `\\mathrm{${w}}`
      i += w.length
      continue
    }
    if (/\d/.test(ch)) {
      const m = /^\d+(\.\d+)?/.exec(src.slice(i))
      out += m[0]
      i += m[0].length
      const sci = /^e(\d+|[+-]\d+)/.exec(src.slice(i))
      if (sci) {
        out += `\\times 10^{${sci[1]}}`
        i += sci[0].length
      }
      continue
    }
    out += ch
    i++
  }
  return out
}
