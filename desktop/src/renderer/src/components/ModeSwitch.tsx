import type { LauncherMode } from '../lib/launcher'

type ModeSwitchProps = {
  mode: LauncherMode
  onChangeMode: (mode: LauncherMode) => void
}

export function ModeSwitch({ mode, onChangeMode }: ModeSwitchProps) {
  return (
    <div className="mode-switch">
      <button className={`mode-switch__item${mode === 'picker' ? ' mode-switch__item--active' : ''}`} type="button" onClick={() => onChangeMode('picker')}>
        Home
      </button>
      <button className={`mode-switch__item${mode === 'local' ? ' mode-switch__item--active' : ''}`} type="button" onClick={() => onChangeMode('local')}>
        Local
      </button>
      <button className={`mode-switch__item${mode === 'remote' ? ' mode-switch__item--active' : ''}`} type="button" onClick={() => onChangeMode('remote')}>
        Remote
      </button>
    </div>
  )
}
