import { useEffect, useState } from 'react'
import { createTask } from '../../api'
import { composeCreateTaskInput } from './content'

export function TaskCreateModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (taskId: string) => Promise<void> | void
}) {
  const [title, setTitle] = useState('')
  const [source, setSource] = useState('')
  const [supplement, setSupplement] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [])

  async function handleCreate() {
    try {
      setCreating(true)
      setError('')
      const result = await createTask({
        input: composeCreateTaskInput(source, supplement),
        title: title.trim() || undefined,
        repos: [],
      })
      await onCreated(result.task_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建任务失败')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-[rgba(20,20,19,0.2)] backdrop-blur-sm dark:bg-[rgba(20,20,19,0.58)]" onClick={onClose}>
      <div
        className="absolute left-1/2 top-1/2 flex max-h-[calc(100vh-48px)] w-[min(720px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-[28px] border border-[#e8e6dc] bg-[#faf9f5] shadow-[0_24px_64px_rgba(20,20,19,0.18)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_24px_64px_rgba(0,0,0,0.38)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-[#e8e6dc] px-6 py-5 dark:border-[#30302e]">
          <div>
            <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Create Task</div>
            <h3 className="mt-2 text-[30px] leading-[1.08] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">新建任务</h3>
            <p className="mt-3 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">这里只收两类信息：需求原文，以及研发视角下的补充说明。</p>
          </div>
          <button
            className="inline-flex h-9 w-9 items-center justify-center rounded-full text-[#87867f] transition hover:bg-[#f1ece4] hover:text-[#4d4c48] dark:text-[#8f8a82] dark:hover:bg-[#24221f] dark:hover:text-[#f1ede4]"
            onClick={onClose}
            title="关闭"
            type="button"
          >
            <CloseIcon />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5">
          <section className="rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 dark:border-[#30302e] dark:bg-[#232220]">
            <div className="text-[10px] uppercase tracking-[0.45em] text-[#87867f] dark:text-[#b0aea5]">任务标题</div>
            <div className="mt-3 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">建议填一个简短标题，方便后续在任务列表中快速识别。</div>
            <input
              className="mt-4 w-full rounded-[18px] border border-dashed border-[#d8d3c8] bg-[#fffdf9] px-4 py-4 text-sm text-[#141413] outline-none focus:border-[#3898ec] dark:border-[#3a3937] dark:bg-[#151412] dark:text-[#faf9f5] dark:focus:border-[#3898ec]"
              onChange={(event) => setTitle(event.target.value)}
              placeholder="例如：统一商品规则定义口径"
              type="text"
              value={title}
            />
          </section>

          <section className="rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 dark:border-[#30302e] dark:bg-[#232220]">
            <div className="text-[10px] uppercase tracking-[0.45em] text-[#87867f] dark:text-[#b0aea5]">输入内容</div>
            <div className="mt-3 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">填 PRD 内容，或者直接贴飞书文档链接。</div>
            <textarea
              className="mt-4 min-h-[240px] w-full rounded-[18px] border border-dashed border-[#d8d3c8] bg-[#fffdf9] px-4 py-4 text-sm leading-7 text-[#141413] outline-none focus:border-[#3898ec] dark:border-[#3a3937] dark:bg-[#151412] dark:text-[#faf9f5] dark:focus:border-[#3898ec]"
              onChange={(event) => setSource(event.target.value)}
              placeholder={'请输入 PRD 原文，或粘贴飞书文档链接。\n\n例如：\nhttps://bytedance.feishu.cn/docx/...'}
              value={source}
            />
          </section>

          <section className="rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 dark:border-[#30302e] dark:bg-[#232220]">
            <div className="text-[10px] uppercase tracking-[0.45em] text-[#87867f] dark:text-[#b0aea5]">补充说明</div>
            <div className="mt-3 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">研发视角下补充理解、风险、约束，或者贴参考材料。</div>
            <textarea
              className="mt-4 min-h-[180px] w-full rounded-[18px] border border-dashed border-[#d8d3c8] bg-[#fffdf9] px-4 py-4 text-sm leading-7 text-[#141413] outline-none focus:border-[#3898ec] dark:border-[#3a3937] dark:bg-[#151412] dark:text-[#faf9f5] dark:focus:border-[#3898ec]"
              onChange={(event) => setSupplement(event.target.value)}
              placeholder={'例如：\n- 我理解这次主要是统一规则定义。\n- 风险是旧链路字段兼容。\n- 可参考历史需求或知识库文档。'}
              value={supplement}
            />
          </section>
          {error ? <div className="text-sm text-[#b53333]">{error}</div> : null}
        </div>

        <div className="flex flex-wrap gap-2 border-t border-[#e8e6dc] px-6 py-4 dark:border-[#30302e]">
          <button
            className="rounded-[14px] border border-[#c96442] bg-[#c96442] px-5 py-3 text-sm text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757] disabled:cursor-not-allowed disabled:opacity-55"
            disabled={creating || !source.trim()}
            onClick={() => void handleCreate()}
            type="button"
          >
            {creating ? '创建中...' : '创建任务'}
          </button>
          <button
            className="rounded-[14px] border border-[#d1cfc5] bg-[#faf9f5] px-5 py-3 text-sm text-[#4d4c48] transition hover:bg-[#efeae0] dark:border-[#3a3937] dark:bg-[#191816] dark:text-[#f1ede4] dark:hover:bg-[#24221f]"
            onClick={onClose}
            type="button"
          >
            取消
          </button>
        </div>
      </div>
    </div>
  )
}

function CloseIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="14" viewBox="0 0 14 14" width="14">
      <path d="M3.5 3.5l7 7M10.5 3.5l-7 7" stroke="currentColor" strokeLinecap="round" strokeWidth="1.5" />
    </svg>
  )
}
