// 泛化 prompt 覆盖测算（实体轮转口径）单测——与后端 _load_entity_schema_variables 同构。
// useEntitySchemas 引用了 @/apis，走 vite ssrLoadModule 解析别名。
import assert from 'node:assert/strict'
import test from 'node:test'
import { createServer } from 'vite'

const ent = (key, name, category, props) => ({
  entity_id: `id-${key}`,
  entity_key: key,
  name_cn: name,
  category,
  properties: props.map(([k, n, required]) => ({ key: k, name_cn: n, required: Boolean(required) }))
})

const CATS = ['project_basic', 'env_quality']

test('breadth-first: 每实体先拿 1 条，再进入第二轮；required 优先', async () => {
  // ssr 链上有 store 顶层引用 localStorage，先给存根
  const previousStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: { getItem: () => null, setItem() {}, removeItem() {} }
  })
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { computePromptCoverage, PROMPT_PROPERTY_LIMIT } = await server.ssrLoadModule(
      '/src/composables/useEntitySchemas.js'
    )
    const entities = [
      ent('a', '实体A', 'project_basic', [
        ['a_opt', '普通属性'],
        ['a_req', '必填属性', true],
        ['a2', '属性二'],
        ['a3', '属性三']
      ]),
      ent('b', '实体B', 'project_basic', [
        ['b1', '属性一'],
        ['b2', '属性二']
      ]),
      ent('c', '实体C', 'env_quality', [['c1', '属性一']])
    ]
    const cov = computePromptCoverage(entities, 4, CATS)
    // a 排序后 [a_req, a_opt, a2, a3]：第 1 轮各实体取第 1 条，第 2 轮 a 取 a_opt
    assert.deepEqual([...cov.coveredRefs].sort(), ['a.a_req', 'a.a_opt', 'b.b1', 'c.c1'].sort())
    assert.equal(cov.covered, 4)
    assert.equal(cov.byEntity['id-a'], 2)
    assert.equal(cov.byEntity['id-b'], 1)
    assert.equal(cov.byEntity['id-c'], 1)

    // limit 小于实体数：每实体至多 1 条，覆盖 limit 个实体
    const many = Array.from({ length: 100 }, (_, i) => ent(`e${i}`, `实体${i}`, 'project_basic', [['p1', '属性']]))
    const cov2 = computePromptCoverage(many, PROMPT_PROPERTY_LIMIT, CATS)
    assert.equal(cov2.covered, PROMPT_PROPERTY_LIMIT)
    assert.equal(Object.values(cov2.byEntity).filter((n) => n > 0).length, PROMPT_PROPERTY_LIMIT)

    // 字典外分类排最后；无属性实体不占预算
    const mixed = [
      ent('z', '字典外实体', 'unknown_cat', [['z1', '属性']]),
      ent('a', '字典内实体', 'project_basic', [['a1', '属性']]),
      ent('e', '空实体', 'project_basic', [])
    ]
    const cov3 = computePromptCoverage(mixed, 1, CATS)
    assert.deepEqual([...cov3.coveredRefs], ['a.a1'])
    assert.equal(cov3.eligible, 2)
  } finally {
    await server.close()
    if (previousStorage) {
      Object.defineProperty(globalThis, 'localStorage', previousStorage)
    } else {
      delete globalThis.localStorage
    }
  }
})
