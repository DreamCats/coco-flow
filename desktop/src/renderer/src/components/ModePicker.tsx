import type { LauncherMode } from '../lib/launcher'

type ModePickerProps = {
  onSelectMode: (mode: Exclude<LauncherMode, 'picker'>) => void
}

export function ModePicker({ onSelectMode }: ModePickerProps) {
  return (
    <section className="mode-picker">
      <div className="panel home-shell">
        <div className="home-shell__intro">
          <p className="section-label">Choose mode</p>
          <h2>How do you want to use coco-flow?</h2>
        </div>

        <button className="mode-option" type="button" onClick={() => onSelectMode('local')}>
          <span className="mode-option__title">Use on this Mac</span>
          <span className="mode-option__copy">启动本机 `coco-flow`，直接打开本地 Web UI。</span>
        </button>

        <button className="mode-option" type="button" onClick={() => onSelectMode('remote')}>
          <span className="mode-option__title">Connect to remote machine</span>
          <span className="mode-option__copy">连接开发机，建立隧道后在本地打开 Web UI。</span>
        </button>
      </div>
    </section>
  )
}
