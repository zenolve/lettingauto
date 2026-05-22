import React from "react";

export function Field({
  label, hint, error, children, required,
}: {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    // grid rows keep label, input, helper text aligned across all siblings in
    // the same row even when individual labels wrap to two lines. Helper text
    // row collapses to 0 when absent so non-helper Fields don't gain a gap.
    <label className="grid content-start items-start [grid-template-rows:auto_auto_auto] gap-y-1">
      <span className="label min-h-[2.6em] leading-tight self-end">
        {label}
        {required && <span className="text-rose-600 ml-0.5">*</span>}
      </span>
      <span className="self-start">{children}</span>
      {hint && !error && <span className="text-xs text-ink-muted">{hint}</span>}
      {error && <span className="text-xs text-rose-600">{error}</span>}
    </label>
  );
}

export function Section({ title, description, children }: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="card p-6 md:p-7 space-y-5">
      <header className="border-b border-cream-300 pb-3">
        <h3 className="font-serif text-lg font-semibold text-navy-700">{title}</h3>
        {description && <p className="text-sm text-ink-muted mt-1">{description}</p>}
      </header>
      <div className="grid gap-4 md:grid-cols-2">{children}</div>
    </section>
  );
}
