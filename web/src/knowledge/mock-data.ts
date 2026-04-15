import type { KnowledgeDocument, KnowledgeDraftInput, KnowledgeEngine, KnowledgeKind } from './types'

export const knowledgeRepoOptions = ['live_pack', 'live_sdk', 'growth_pack', 'auction_gateway']

export const knowledgeMockDocuments: KnowledgeDocument[] = [
  {
    id: 'flow-auction-explain-card-render',
    kind: 'flow',
    status: 'draft',
    title: '表达层链路',
    desc: '说明竞拍讲解卡在表达层的入口、联动模块、状态变化和常见风险。',
    domainId: 'auction-explain-card',
    domainName: '竞拍讲解卡',
    engines: ['plan', 'refine'],
    repos: ['live_pack', 'live_sdk'],
    paths: ['app/explain_card', 'service/card_render', 'sdk/render'],
    keywords: ['讲解卡', '表达层', 'render', '卡片'],
    priority: 'high',
    confidence: 'medium',
    updatedAt: '2026-04-15 18:20',
    owner: 'Maifeng',
    body: `## Summary

竞拍讲解卡表达层的变更通常从卡片渲染入口发起，再联动讲解数据拼装、实验开关和渲染 SDK。

## Main Flow

1. 表达层收到讲解卡场景请求。
2. 入口模块根据实验和讲解状态选择卡片模板。
3. 拼装层拉取讲解卡字段并产出渲染结构。
4. 渲染 SDK 根据模板和状态生成最终展示结果。

## Risks

- 表达层字段变更容易和实验开关逻辑耦合。
- 渲染降级路径如果没有同步更新，容易出现空卡或字段缺失。

## Code Anchors

- live_pack/app/explain_card
- live_pack/service/card_render
- live_sdk/sdk/render

## Open Questions

- 讲解状态是否由统一字段驱动，还是不同入口各自判断。
- 渲染模板最终由业务仓决定，还是由 SDK 决定。`,
    evidence: {
      inputDescription: '竞拍讲解卡表达层',
      repoMatches: ['live_pack', 'live_sdk'],
      keywordMatches: ['讲解卡', '表达层', 'render', '卡片'],
      pathMatches: ['app/explain_card', 'service/card_render', 'sdk/render'],
      candidateFiles: [
        'app/explain_card/card_handler.go',
        'service/card_render/explain_card_service.go',
        'sdk/render/card_renderer.go',
      ],
      contextHits: ['.livecoding/context/glossary.md 命中 explain_card', '.livecoding/context/patterns.md 命中 card render'],
      retrievalNotes: [
        '表达层相关目录主要集中在 app 和 service，SDK 侧命中渲染模块。',
        '当前草稿优先覆盖 plan 需要的链路和入口信息。',
      ],
      openQuestions: ['是否还有网关层或配置中心参与表达层分流。'],
    },
  },
  {
    id: 'anchor-auction-explain-card-render',
    kind: 'anchor',
    status: 'approved',
    title: '表达层代码映射',
    desc: '收敛竞拍讲解卡表达层最可能命中的 repo、目录和检索词，供 plan 阶段优先搜索。',
    domainId: 'auction-explain-card',
    domainName: '竞拍讲解卡',
    engines: ['plan'],
    repos: ['live_pack', 'live_sdk'],
    paths: ['app/explain_card', 'service/card_render', 'sdk/render'],
    keywords: ['explain_card', 'render_card', '讲解卡', '卡片模板'],
    priority: 'high',
    confidence: 'high',
    updatedAt: '2026-04-15 18:10',
    owner: 'Maifeng',
    body: `## Repos

- live_pack
- live_sdk

## Paths

- app/explain_card
- service/card_render
- sdk/render

## Search Terms

- explain_card
- render_card
- 讲解卡
- 卡片模板

## Adjacent Modules

- experiment/card_scene
- config/card_switch

## Open Questions

- 表达层目录是否还有独立 converter 层需要纳入。`,
    evidence: {
      inputDescription: '竞拍讲解卡表达层代码映射',
      repoMatches: ['live_pack', 'live_sdk'],
      keywordMatches: ['explain_card', 'render_card', '讲解卡'],
      pathMatches: ['app/explain_card', 'service/card_render', 'sdk/render'],
      candidateFiles: [
        'app/explain_card/card_handler.go',
        'service/card_render/card_scene_builder.go',
        'sdk/render/card_renderer.go',
      ],
      contextHits: ['本次草稿未依赖 repo 外知识，仅结合 repo 命中和已有 context。'],
      retrievalNotes: ['代码映射已经人工确认，可直接作为 plan 的优先搜索入口。'],
      openQuestions: ['是否需要补充 experiment 相关目录作为相邻模块。'],
    },
  },
  {
    id: 'rule-auction-explain-card-defaults',
    kind: 'rule',
    status: 'draft',
    title: '默认业务规则',
    desc: '记录竞拍讲解卡表达层的默认展示规则和回退规则，供 refine 补边界条件时参考。',
    domainId: 'auction-explain-card',
    domainName: '竞拍讲解卡',
    engines: ['refine', 'plan'],
    repos: ['live_pack'],
    paths: ['service/card_render', 'config/card_switch'],
    keywords: ['默认规则', '回退', '讲解卡'],
    priority: 'medium',
    confidence: 'medium',
    updatedAt: '2026-04-15 17:58',
    owner: 'Maifeng',
    body: `## Statement

- 讲解卡缺少核心字段时默认走降级模板。
- 表达层开关关闭时不进入讲解卡拼装逻辑。

## Exceptions

- 特殊实验流量可以强制开启新模板。

## Scope

- 只覆盖表达层，不覆盖讲解数据生产链路。

## Open Questions

- 降级模板是否对不同端保持一致。`,
    evidence: {
      inputDescription: '竞拍讲解卡默认业务规则',
      repoMatches: ['live_pack'],
      keywordMatches: ['回退', '默认规则', '开关'],
      pathMatches: ['service/card_render', 'config/card_switch'],
      candidateFiles: ['service/card_render/fallback_rule.go', 'config/card_switch/explain_card_switch.go'],
      contextHits: ['.livecoding/context/business-rules.md 命中讲解卡回退说明'],
      retrievalNotes: ['规则草稿主要用于帮助 refine 补充边界和待确认项。'],
      openQuestions: ['特殊实验是否独立于通用开关。'],
    },
  },
  {
    id: 'domain-auction-shopping-bag',
    kind: 'domain',
    status: 'approved',
    title: '业务方向概览',
    desc: '概览竞拍购物袋的主要目标、关键场景和相关链路。',
    domainId: 'auction-shopping-bag',
    domainName: '竞拍购物袋',
    engines: ['refine', 'plan'],
    repos: ['live_pack', 'auction_gateway'],
    paths: ['app/shopping_bag', 'gateway/bag'],
    keywords: ['购物袋', '竞拍', 'bag'],
    priority: 'medium',
    confidence: 'high',
    updatedAt: '2026-04-14 20:12',
    owner: 'Maifeng',
    body: `## Summary

竞拍购物袋关注商品聚合展示、状态同步和价格相关信息的表达。

## Terms

- 购物袋
- bag
- 竞拍商品聚合

## Rules

- 购物袋状态和竞拍主状态保持一致。

## Related Flows

- 购物袋状态流转链路
- 购物袋表达层链路`,
    evidence: {
      inputDescription: '竞拍购物袋 domain',
      repoMatches: ['live_pack', 'auction_gateway'],
      keywordMatches: ['购物袋', 'bag', '竞拍'],
      pathMatches: ['app/shopping_bag', 'gateway/bag'],
      candidateFiles: ['app/shopping_bag/bag_handler.go', 'gateway/bag/bag_gateway.go'],
      contextHits: ['团队知识库已有 domain 草稿，已人工确认。'],
      retrievalNotes: ['该 domain 已作为 approved 知识默认参与 refine 与 plan。'],
      openQuestions: [],
    },
  },
]

export function generateKnowledgeDrafts(input: KnowledgeDraftInput): KnowledgeDocument[] {
  const description = input.description.trim()
  const repos = input.repos.length > 0 ? input.repos : ['live_pack']
  const domainName = inferDomainName(description)
  const domainId = slugifyDomain(domainName)
  const timestamp = formatNow()
  const keywords = inferKeywords(description)
  const paths = inferPaths(description)
  const files = inferCandidateFiles(paths)
  const contextHits = description.includes('讲解卡')
    ? ['.livecoding/context/glossary.md 命中 explain_card', '.livecoding/context/patterns.md 命中 render']
    : ['当前未命中明确的 repo context，仅保留 repo 扫描证据。']

  return input.kinds.map((kind, index) => buildDraftDocument({
    kind,
    description,
    domainId,
    domainName,
    repos,
    paths,
    keywords,
    files,
    contextHits,
    notes: input.notes.trim(),
    timestamp,
    sequence: index,
  }))
}

function buildDraftDocument({
  kind,
  description,
  domainId,
  domainName,
  repos,
  paths,
  keywords,
  files,
  contextHits,
  notes,
  timestamp,
  sequence,
}: {
  kind: KnowledgeKind
  description: string
  domainId: string
  domainName: string
  repos: string[]
  paths: string[]
  keywords: string[]
  files: string[]
  contextHits: string[]
  notes: string
  timestamp: string
  sequence: number
}): KnowledgeDocument {
  const id = `${kind}-${domainId}-${Date.now()}-${sequence}`
  return {
    id,
    kind,
    status: 'draft',
    title: buildDraftTitle(kind, description),
    desc: buildDraftDescription(kind, description),
    domainId,
    domainName,
    engines: inferEngines(kind),
    repos,
    paths,
    keywords,
    priority: kind === 'flow' || kind === 'anchor' ? 'high' : 'medium',
    confidence: 'medium',
    updatedAt: timestamp,
    owner: 'Maifeng',
    body: buildDraftBody(kind, description, repos, paths, keywords, notes),
    evidence: {
      inputDescription: description,
      repoMatches: repos,
      keywordMatches: keywords,
      pathMatches: paths,
      candidateFiles: files,
      contextHits,
      retrievalNotes: [
        '本次为 mock 生成草稿，优先保留了可用于 plan / refine 的高信号字段。',
        '建议先确认证据页里的 repo 命中和路径，再决定是否发布。',
        ...(notes ? [`补充材料：${notes}`] : []),
      ],
      openQuestions: buildDraftOpenQuestions(kind, description),
    },
  }
}

function inferEngines(kind: KnowledgeKind): KnowledgeEngine[] {
  if (kind === 'anchor') {
    return ['plan']
  }
  if (kind === 'flow') {
    return ['plan', 'refine']
  }
  return ['refine', 'plan']
}

function inferDomainName(description: string): string {
  const trimmed = description.trim()
  const normalized = trimmed
    .replace(/表达层/g, '')
    .replace(/代码映射/g, '')
    .replace(/默认业务规则/g, '')
    .replace(/业务规则/g, '')
    .replace(/链路/g, '')
    .trim()
  return normalized || trimmed || '未命名领域'
}

function slugifyDomain(name: string): string {
  if (name.includes('讲解卡')) {
    return 'auction-explain-card'
  }
  if (name.includes('购物袋')) {
    return 'auction-shopping-bag'
  }
  return `knowledge-${Date.now()}`
}

function buildDraftTitle(kind: KnowledgeKind, description: string): string {
  switch (kind) {
    case 'flow':
      return description.includes('链路') ? description : `${description}链路`
    case 'anchor':
      return description.includes('代码映射') ? description : `${description}代码映射`
    case 'rule':
      return description.includes('规则') ? description : `${description}业务规则`
    case 'domain':
      return description.includes('概览') ? description : `${inferDomainName(description)}业务方向概览`
  }
}

function buildDraftDescription(kind: KnowledgeKind, description: string): string {
  switch (kind) {
    case 'flow':
      return `归纳 ${description} 的主链路、关键依赖和风险，供 plan 与 refine 渐进加载。`
    case 'anchor':
      return `为 ${description} 收敛 repo、路径和检索词，供 plan 阶段优先搜索。`
    case 'rule':
      return `整理 ${description} 的默认规则、例外和待确认问题，供 refine 补边界时参考。`
    case 'domain':
      return `概览 ${inferDomainName(description)} 的关键场景、相关链路和默认约束。`
  }
}

function buildDraftBody(
  kind: KnowledgeKind,
  description: string,
  repos: string[],
  paths: string[],
  keywords: string[],
  notes: string,
): string {
  const repoLines = repos.map((repo) => `- ${repo}`).join('\n')
  const pathLines = paths.map((path) => `- ${path}`).join('\n')
  const keywordLines = keywords.map((keyword) => `- ${keyword}`).join('\n')
  const noteLine = notes ? `\n## Notes\n\n- ${notes}\n` : ''

  switch (kind) {
    case 'flow':
      return `## Summary

${description} 当前作为知识草稿，重点帮助 plan 先理解链路，再定位代码。

## Main Flow

1. 根据场景入口识别表达层或业务入口。
2. 收敛关键服务与状态判断。
3. 明确需要联动的 repo 和模块。

## Dependencies

${repoLines}

## Risks

- 关键状态来源可能仍需人工确认。
- 相邻模块边界可能需要在 repo 调研后继续收敛。

## Code Anchors

${pathLines}

## Open Questions

- 当前链路是否还有上游网关或配置依赖。${noteLine}`
    case 'anchor':
      return `## Repos

${repoLines}

## Paths

${pathLines}

## Search Terms

${keywordLines}

## Adjacent Modules

- experiment
- config

## Open Questions

- 哪些目录是主入口，哪些只是相邻依赖。${noteLine}`
    case 'rule':
      return `## Statement

- ${description} 存在默认规则，但当前仍是待确认草稿。

## Exceptions

- 特殊实验或灰度逻辑可能覆盖默认规则。

## Scope

- 当前只覆盖与 ${description} 直接相关的主链路。

## Open Questions

- 哪些例外规则已经在线上固化。${noteLine}`
    case 'domain':
      return `## Summary

${inferDomainName(description)} 当前作为领域级知识入口，用来把相关 flow / rule / anchor 聚合到同一个 domain。

## Terms

${keywordLines}

## Rules

- 领域级规则仍待补齐。

## Related Flows

- ${description}${noteLine}`
  }
}

function buildDraftOpenQuestions(kind: KnowledgeKind, description: string): string[] {
  if (kind === 'anchor') {
    return ['哪些路径是主搜索入口，哪些路径只是邻接模块。']
  }
  if (kind === 'rule') {
    return ['默认规则和实验覆盖规则之间的优先级是否已经明确。']
  }
  if (kind === 'domain') {
    return ['是否需要补一个领域级 glossary 文件。']
  }
  return [`${description} 是否还有额外的上下游依赖没有被纳入当前链路。`]
}

function inferKeywords(description: string): string[] {
  const keywords: string[] = []
  if (description.includes('讲解卡')) {
    keywords.push('讲解卡', 'explain_card')
  }
  if (description.includes('购物袋')) {
    keywords.push('购物袋', 'shopping_bag')
  }
  if (description.includes('表达层')) {
    keywords.push('表达层', 'render', '卡片')
  }
  if (keywords.length === 0) {
    keywords.push('feature', 'flow')
  }
  return Array.from(new Set(keywords))
}

function inferPaths(description: string): string[] {
  if (description.includes('讲解卡')) {
    return description.includes('表达层')
      ? ['app/explain_card', 'service/card_render', 'sdk/render']
      : ['app/explain_card', 'service/explain_card']
  }
  if (description.includes('购物袋')) {
    return ['app/shopping_bag', 'service/shopping_bag', 'gateway/bag']
  }
  return ['app/feature', 'service/feature']
}

function inferCandidateFiles(paths: string[]): string[] {
  return paths.map((path) => `${path}/${path.split('/').slice(-1)[0]}_handler.go`)
}

function formatNow(): string {
  const now = new Date()
  const year = now.getFullYear()
  const month = `${now.getMonth() + 1}`.padStart(2, '0')
  const day = `${now.getDate()}`.padStart(2, '0')
  const hours = `${now.getHours()}`.padStart(2, '0')
  const minutes = `${now.getMinutes()}`.padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}`
}
