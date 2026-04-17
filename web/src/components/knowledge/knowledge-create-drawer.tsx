import { useEffect, useState, type ReactNode } from 'react'

type KnowledgeCreateDrawerProps = {
  creating: boolean
  open: boolean
  onClose: () => void
  onSubmit: (payload: { title: string; content: string }) => void
}

const contentPlaceholder = `---
kind: flow
status: draft
engines: []
---

## Summary

补充这份知识的背景、结论和范围。

## Main Flow

1. ...

## Notes

- ...
`

export function KnowledgeCreateDrawer({ creating, open, onClose, onSubmit }: KnowledgeCreateDrawerProps) {
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')

  useEffect(() => {
    if (!open) {
      return
    }
    setTitle('')
    setContent('')
  }, [open])

  if (!open) {
    return null
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(20,20,19,0.42)] p-4 backdrop-blur-sm">
      <div className="max-h-[min(860px,calc(100vh-32px))] w-full max-w-[820px] overflow-y-auto rounded-[24px] border border-[#e8e6dc] bg-[#faf9f5] p-5 shadow-[0_24px_80px_rgba(20,20,19,0.18)] dark:border-[#30302e] dark:bg-[#1d1c1a]">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Knowledge File</div>
            <h3 className="mt-2 text-[30px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">新建知识文档</h3>
            <div className="mt-2 text-sm text-[#87867f] dark:text-[#b0aea5]">直接维护文档内容。正文开头如果带 YAML frontmatter 也会按文件保存。</div>
          </div>
          <button
            className="inline-flex h-10 w-10 items-center justify-center rounded-[12px] border border-[#e8e6dc] text-[#5e5d59] transition hover:text-[#141413] dark:border-[#30302e] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]"
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </div>

        <div className="mt-5 space-y-4">
          <FormBlock label="标题">
            <input
              className={fieldClassName}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="例如：竞拍讲解卡表达层参考"
              type="text"
              value={title}
            />
          </FormBlock>

          <FormBlock label="Markdown 内容">
            <textarea
              className={`${fieldClassName} min-h-[420px] resize-y font-mono text-xs leading-6`}
              onChange={(event) => setContent(event.target.value)}
              placeholder={contentPlaceholder}
              value={content}
            />
            <div className="mt-3 text-xs text-[#87867f] dark:text-[#b0aea5]">不写 YAML 也可以；系统会补默认 frontmatter。需要参与后续引擎时，可以在这里手动维护 `status`、`engines`、`kind` 等字段。</div>
          </FormBlock>

          <div className="flex flex-wrap items-center justify-end gap-3 pt-2">
            <button
              className="rounded-[12px] border border-[#e8e6dc] px-4 py-2 text-sm text-[#5e5d59] transition hover:text-[#141413] dark:border-[#30302e] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]"
              onClick={onClose}
              type="button"
            >
              取消
            </button>
            <button
              className="rounded-[12px] border border-[#c96442] bg-[#c96442] px-4 py-2 text-sm font-semibold text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!title.trim() || creating}
              onClick={() => onSubmit({ title, content })}
              type="button"
            >
              {creating ? '保存中...' : '创建文档'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function FormBlock({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.86)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
      <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">{label}</div>
      {children}
    </section>
  )
}

const fieldClassName =
  'w-full rounded-[12px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-2 text-sm text-[#141413] outline-none transition placeholder:text-[#87867f] focus:border-[#3898ec] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#faf9f5] dark:placeholder:text-[#87867f] dark:focus:border-[#3898ec]'
