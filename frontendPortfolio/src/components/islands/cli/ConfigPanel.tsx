import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import type { CliManifest } from "../../../lib/api/schemas";
import { type CliSettings, cycleSetting, settingValue } from "../../../lib/cli/settings";

interface ConfigPanelProps {
  readonly manifest: CliManifest;
  readonly settings: CliSettings;
  readonly onChange: (settings: CliSettings) => void;
  readonly onClose: () => void;
}

export function ConfigPanel({ manifest, settings, onChange, onClose }: ConfigPanelProps) {
  const [selected, setSelected] = useState(0);
  const panelRef = useRef<HTMLDivElement>(null);
  const rows = manifest.settings;

  useEffect(() => {
    panelRef.current?.focus();
  }, []);

  const change = (step: number): void => {
    const setting = rows[selected];
    if (setting !== undefined) {
      onChange(cycleSetting(settings, manifest, setting.key, step));
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>): void => {
    const actions: Readonly<Record<string, () => void>> = {
      ArrowUp: () => setSelected((index) => (index - 1 + rows.length) % rows.length),
      ArrowDown: () => setSelected((index) => (index + 1) % rows.length),
      ArrowLeft: () => change(-1),
      ArrowRight: () => change(1),
      Enter: () => change(1),
      " ": () => change(1),
      Escape: onClose,
    };
    const action = actions[event.key];
    if (action !== undefined) {
      event.preventDefault();
      action();
    }
  };

  return (
    <div
      ref={panelRef}
      role="listbox"
      aria-label="Settings"
      aria-activedescendant={`term-setting-${selected}`}
      tabIndex={0}
      onKeyDown={onKeyDown}
      className="term-box flex-col items-stretch gap-[0.2em] outline-none"
      data-config-panel
    >
      <p className="font-semibold">Settings</p>
      {rows.map((setting, index) => (
        <div
          key={setting.key}
          id={`term-setting-${index}`}
          role="option"
          tabIndex={-1}
          aria-selected={index === selected}
          className="term-setting"
          onMouseDown={(event) => {
            event.preventDefault();
            setSelected(index);
            onChange(cycleSetting(settings, manifest, setting.key, 1));
          }}
        >
          <span aria-hidden="true">{index === selected ? "❯" : " "}</span>
          <span className="truncate">{setting.label}</span>
          <span className="font-semibold">{settingValue(settings, setting.key)}</span>
          <span className="truncate text-faint max-sm:hidden">{setting.summary}</span>
        </div>
      ))}
      <p className="mt-[0.3em] text-faint">
        <span className="hover-only">↑↓ select · ←→ or Enter change · </span>
        <span className="hover-only">Esc done</span>
        <span className="touch-only">
          tap to change ·{" "}
          <button type="button" className="term-link" onClick={onClose}>
            done
          </button>
        </span>
      </p>
    </div>
  );
}
