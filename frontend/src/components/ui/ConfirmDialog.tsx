import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";

/**
 * Modular confirmation modal.
 *
 * Mount <ConfirmDialogProvider> once at the layout level. Any descendant
 * component can then call:
 *
 *     const confirm = useConfirm();
 *     const ok = await confirm({
 *       title: "Mark T&C as signed manually?",
 *       body:  "Make sure all parties have signed before continuing.",
 *       confirmLabel: "Yes, mark as signed",
 *       tone: "warning",
 *     });
 *     if (!ok) return;
 *     // proceed with the destructive / consequential action
 *
 * `tone` drives the styling:
 *   - info     → cream/navy (default for low-stakes confirmations)
 *   - warning  → amber border + amber primary button
 *   - danger   → rose border + rose primary button
 *
 * Returning a promise lets callers `await` the user's decision inline, so
 * the call site reads naturally and no callback nesting is needed.
 */

export type ConfirmTone = "info" | "warning" | "danger";

export type ConfirmOptions = {
  title: string;
  body: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: ConfirmTone;
};

type Resolver = (ok: boolean) => void;

type ConfirmContextValue = (opts: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmContextValue | null>(null);

export function useConfirm(): ConfirmContextValue {
  const ctx = useContext(ConfirmContext);
  if (!ctx) {
    throw new Error("useConfirm() called outside <ConfirmDialogProvider>");
  }
  return ctx;
}

export function ConfirmDialogProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ConfirmOptions | null>(null);
  // Refs (not state) so the promise resolver isn't snapshotted into a render
  // that may have already unmounted by the time the user clicks.
  const resolverRef = useRef<Resolver | null>(null);
  const cancelBtnRef = useRef<HTMLButtonElement | null>(null);

  const confirm = useCallback<ConfirmContextValue>((opts) => {
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
      setState(opts);
    });
  }, []);

  const finish = useCallback((ok: boolean) => {
    const r = resolverRef.current;
    resolverRef.current = null;
    setState(null);
    if (r) r(ok);
  }, []);

  // Focus the cancel button when the dialog opens so Enter doesn't accidentally
  // confirm a destructive action. Esc closes; Enter on the dialog confirms
  // ONLY if focus is on the primary button.
  useEffect(() => {
    if (state && cancelBtnRef.current) cancelBtnRef.current.focus();
  }, [state]);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {state && (
        <Dialog
          opts={state}
          onConfirm={() => finish(true)}
          onCancel={() => finish(false)}
          cancelBtnRef={cancelBtnRef}
        />
      )}
    </ConfirmContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Dialog body — separated so the provider stays tiny and the styling lives
// in one place.
// ---------------------------------------------------------------------------
const TONE_STYLES: Record<ConfirmTone, { border: string; header: string; kicker: string; confirmBtn: string }> = {
  info: {
    border: "border-cream-300",
    header: "bg-cream-100 border-cream-300 text-ink",
    kicker: "text-navy-700",
    confirmBtn: "bg-navy-600 hover:bg-navy-700 text-white",
  },
  warning: {
    border: "border-amber-300",
    header: "bg-amber-50 border-amber-200 text-amber-900",
    kicker: "text-amber-700",
    confirmBtn: "bg-amber-600 hover:bg-amber-700 text-white",
  },
  danger: {
    border: "border-rose-300",
    header: "bg-rose-50 border-rose-200 text-rose-900",
    kicker: "text-rose-700",
    confirmBtn: "bg-rose-600 hover:bg-rose-700 text-white",
  },
};

function Dialog({ opts, onConfirm, onCancel, cancelBtnRef }: {
  opts: ConfirmOptions;
  onConfirm: () => void;
  onCancel: () => void;
  cancelBtnRef: React.RefObject<HTMLButtonElement>;
}) {
  const tone = opts.tone ?? "info";
  const styles = TONE_STYLES[tone];

  // Backdrop click + Escape both cancel. Enter is intentionally NOT a
  // shortcut — for warning/danger we want a deliberate click.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return (
    <div
      className="fixed inset-0 z-50 bg-ink/40 backdrop-blur-[1px] flex items-center justify-center p-4"
      onClick={onCancel}
      role="presentation">
      <div
        className={`bg-white rounded-md shadow-paper border-2 ${styles.border} max-w-md w-full overflow-hidden`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title">
        <header className={`px-5 py-3 border-b ${styles.header}`}>
          <div className={`kicker ${styles.kicker}`}>
            {tone === "danger" ? "Destructive action" : tone === "warning" ? "Heads up" : "Confirm"}
          </div>
          <h3 id="confirm-dialog-title" className="font-serif text-base font-semibold mt-0.5">
            {opts.title}
          </h3>
        </header>
        <div className="px-5 py-4 text-sm text-ink-soft">{opts.body}</div>
        <footer className="px-5 py-3 bg-cream-50 border-t border-cream-300 flex justify-end gap-2">
          <button
            ref={cancelBtnRef}
            type="button"
            className="btn-secondary text-sm"
            onClick={onCancel}>
            {opts.cancelLabel ?? "Cancel"}
          </button>
          <button
            type="button"
            className={`inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-offset-1 ${styles.confirmBtn}`}
            onClick={onConfirm}>
            {opts.confirmLabel ?? "Confirm"}
          </button>
        </footer>
      </div>
    </div>
  );
}
