import { ChevronDown } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

export type ModelOption = {
  readonly id: string;
  readonly name?: string;
};

type Props = {
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly options: readonly ModelOption[];
  readonly disabled?: boolean;
  readonly placeholder?: string;
  readonly id?: string;
  readonly name?: string;
  readonly 'aria-label'?: string;
  readonly className?: string;
  /** Extra option shown at top of dropdown (e.g. inherit / empty). */
  readonly emptyOptionLabel?: string;
};

/**
 * Editable model field + chevron dropdown (cc-switch style).
 * Typing edits the value directly; picking from the list fills the input.
 */
export function ModelInputCombobox({
  value,
  onChange,
  options,
  disabled = false,
  placeholder,
  id,
  name,
  'aria-label': ariaLabel,
  className,
  emptyOptionLabel,
}: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();
  const canOpen = !disabled && (options.length > 0 || Boolean(emptyOptionLabel));

  useEffect(() => {
    if (!open) return;
    function onDocPointer(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onDocPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  return (
    <div ref={rootRef} className={cn('relative mt-1.5', className)}>
      <div
        className={cn(
          'flex overflow-hidden rounded-lg border border-slate-300 bg-white',
          disabled && 'bg-slate-50',
        )}
      >
        <input
          id={id}
          name={name}
          type="text"
          value={value}
          disabled={disabled}
          placeholder={placeholder}
          aria-label={ariaLabel}
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={open ? listId : undefined}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => {
            if (canOpen) setOpen(true);
          }}
          className="min-w-0 flex-1 border-0 bg-transparent px-3 py-2 font-mono text-sm text-slate-900 outline-none focus-visible:ring-0 disabled:cursor-not-allowed disabled:text-slate-500"
        />
        <button
          type="button"
          disabled={!canOpen}
          aria-label="Toggle model list"
          aria-expanded={open}
          aria-controls={open ? listId : undefined}
          onClick={() => setOpen((prev) => !prev)}
          className="grid w-9 shrink-0 place-items-center border-l border-slate-200 text-slate-500 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronDown
            className={cn('size-4 transition-transform', open && 'rotate-180')}
            aria-hidden="true"
          />
        </button>
      </div>

      {open && canOpen ? (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-slate-200 bg-white py-1 shadow-lg"
        >
          {emptyOptionLabel ? (
            <li role="option">
              <button
                type="button"
                className={cn(
                  'flex w-full px-3 py-1.5 text-left text-sm text-slate-600 hover:bg-slate-50',
                  value === '' && 'bg-blue-50 text-blue-700',
                )}
                onClick={() => {
                  onChange('');
                  setOpen(false);
                }}
              >
                {emptyOptionLabel}
              </button>
            </li>
          ) : null}
          {options.map((opt) => {
            const selected = value === opt.id;
            return (
              <li key={opt.id} role="option" aria-selected={selected}>
                <button
                  type="button"
                  className={cn(
                    'flex w-full flex-col px-3 py-1.5 text-left hover:bg-slate-50',
                    selected && 'bg-blue-50',
                  )}
                  onClick={() => {
                    onChange(opt.id);
                    setOpen(false);
                  }}
                >
                  <span className="font-mono text-sm text-slate-900">{opt.id}</span>
                  {opt.name && opt.name !== opt.id ? (
                    <span className="text-xs text-slate-500">{opt.name}</span>
                  ) : null}
                </button>
              </li>
            );
          })}
          {options.length === 0 && !emptyOptionLabel ? (
            <li className="px-3 py-2 text-xs text-slate-500">—</li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}
