import clsx from "clsx";

import { STAGES } from "../../lib/stages";

export type StagePipelineProps = {
  /** Stage the user is currently *viewing* (from URL ?stage=N). */
  viewing: number;
  /** Stage the property is *actually at*. Highlighted distinctly. */
  current: number;
  gateStatus?: string;
  /** Called when a chip is clicked. Receives the chosen stage order. */
  onSelect: (order: number) => void;
};

export function StagePipeline({ viewing, current, gateStatus = "Clear", onSelect }: StagePipelineProps) {
  const blocked = gateStatus === "Blocked";
  return (
    <div className="card p-4">
      <ol className="flex flex-wrap items-center gap-1">
        {STAGES.map((s, i) => {
          const isCurrent = s.order === current;
          const isViewing = s.order === viewing;
          const isPast = s.order < current;
          return (
            <li key={s.key} className="flex items-center">
              <button
                type="button"
                onClick={() => onSelect(s.order)}
                aria-current={isViewing ? "step" : undefined}
                title={s.blurb}
                className={clsx(
                  "px-3 py-1.5 rounded-full text-xs font-medium border transition-colors",
                  // Past, current, future bases.
                  isPast && !isViewing && "bg-cream-200 text-ink border-cream-400 hover:bg-cream-300/70",
                  isCurrent && !isViewing && !blocked && "bg-navy-700 text-white border-navy-800 hover:bg-navy-800",
                  isCurrent && !isViewing && blocked  && "bg-rose-600 text-white border-rose-700 hover:bg-rose-700",
                  !isPast && !isCurrent && !isViewing && "bg-white text-ink-muted border-cream-300 hover:bg-cream-100",
                  // Viewing overlay — gold double-ring.
                  isViewing && "bg-white text-navy-700 border-navy-700 ring-2 ring-gold-500 ring-offset-2 ring-offset-white",
                )}>
                <span className="font-serif text-[11px] text-ink-muted mr-1">0{s.order}</span>
                {s.name}
              </button>
              {i < STAGES.length - 1 && (
                <span className={clsx("mx-1 h-px w-4", isPast ? "bg-gold-400" : "bg-cream-300")} />
              )}
            </li>
          );
        })}
      </ol>
      <p className="text-xs text-ink-muted mt-3">
        Currently at stage <strong className="text-ink">{current}</strong>.
        {viewing !== current && (
          <> Viewing stage <strong className="text-ink">{viewing}</strong> (read-only preview).</>
        )}
      </p>
    </div>
  );
}
