import type { LauncherMode } from '../lib/launcher'

type ModePickerProps = {
  onSelectMode: (mode: Exclude<LauncherMode, 'picker'>) => void
}

export function ModePicker({ onSelectMode }: ModePickerProps) {
  return (
    <section className="mode-picker">
      <button className="panel mode-card" type="button" onClick={() => onSelectMode('local')}>
        <p className="section-label">Local</p>
        <h2>Use on this Mac</h2>
        <p className="mode-card__copy">启动本机 `coco-flow`，直接打开本地 Web UI。</p>
      </button>
      <button className="panel mode-card" type="button" onClick={() => onSelectMode('remote')}>
        <p className="section-label">Remote</p>
        <h2>Connect to remote machine</h2>
        <p className="mode-card__copy">连接开发机，建立隧道后在本地打开 Web UI。</p>
      </button>
    </section>
  )
}
