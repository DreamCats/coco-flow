import type { FormEvent } from 'react'

import type { FormState } from '../lib/launcher'

type AddRemoteModalProps = {
  open: boolean
  form: FormState
  canSubmit: boolean
  onClose: () => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>
  onChange: (updater: (current: FormState) => FormState) => void
}

export function AddRemoteModal({
  open,
  form,
  canSubmit,
  onClose,
  onSubmit,
  onChange,
}: AddRemoteModalProps) {
  if (!open) {
    return null
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <div className="section-head">
          <div>
            <p className="section-label">Add remote</p>
            <h2>New machine</h2>
          </div>
          <button className="button button--ghost" type="button" onClick={onClose}>
            Close
          </button>
        </div>

        <form className="remote-form" onSubmit={(event) => void onSubmit(event)}>
          <label>
            <span>Name</span>
            <input value={form.name} onChange={(event) => onChange((current) => ({ ...current, name: event.target.value }))} />
          </label>
          <label>
            <span>Host</span>
            <input value={form.host} onChange={(event) => onChange((current) => ({ ...current, host: event.target.value }))} />
          </label>
          <label>
            <span>User</span>
            <input
              value={form.user}
              placeholder="Optional"
              onChange={(event) => onChange((current) => ({ ...current, user: event.target.value }))}
            />
          </label>
          <div className="field-row">
            <label>
              <span>Local port</span>
              <input
                inputMode="numeric"
                value={form.localPort}
                onChange={(event) => onChange((current) => ({ ...current, localPort: event.target.value }))}
              />
            </label>
            <label>
              <span>Remote port</span>
              <input
                inputMode="numeric"
                value={form.remotePort}
                onChange={(event) => onChange((current) => ({ ...current, remotePort: event.target.value }))}
              />
            </label>
          </div>
          <button className="button button--primary" type="submit" disabled={!canSubmit}>
            Save Remote
          </button>
        </form>
      </div>
    </div>
  )
}
