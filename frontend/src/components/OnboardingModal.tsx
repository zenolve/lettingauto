import { useState } from "react";

import { api } from "../lib/api";
import { useAgency } from "../lib/agency";

/** First-login product tour — exactly 4 slides. Shown until the agency marks
 * onboarding complete (persisted on the agency record, not just locally). */
export default function OnboardingModal() {
  const agency = useAgency((s) => s.agency);
  const load = useAgency((s) => s.load);
  const [i, setI] = useState(0);
  const [closing, setClosing] = useState(false);

  if (!agency || agency.onboarding_completed || closing) return null;

  const fee = agency.billing?.pricing?.tenancy_setup_fee ?? 50;

  const slides: Slide[] = [
    {
      kicker: "Welcome",
      title: `${agency.name}, meet your new lettings engine`,
      body: "Every tenancy moves through a nine-stage pipeline — take-on, compliance, marketing, offer, referencing, signing, move-in, live, end. Gates between stages check the legal boxes for you, so nothing advances until it's safe.",
      art: <PipelineArt />,
    },
    {
      kicker: "Compliance autopilot",
      title: "Documents, deadlines and prescribed packs — handled",
      body: "Gas, EPC, EICR, How-to-Rent, deposit protection: the platform tracks expiry dates, blocks unsafe move-ins, serves prescribed documents as PDF attachments and keeps a full audit trail for possession proceedings.",
      art: <ShieldArt />,
    },
    {
      kicker: "Sign & get paid",
      title: "E-signatures and payments built in",
      body: "Offer letters, Terms of Business and tenancy agreements route to e-signature with your agency's branding. Stripe handles tenant payments and your subscription.",
      art: <SignArt />,
    },
    {
      kicker: "Simple pricing",
      title: `£${fee} per new tenancy — that's it`,
      body: "No seats, no tiers, no subscription. You pay a one-time £" + fee + " fee via Stripe each time you start a new tenancy, then landlord forms, verification, referencing and signing all flow from there automatically.",
      art: <PriceArt fee={fee} />,
    },
  ];

  const last = i === slides.length - 1;
  const s = slides[i];

  async function finish() {
    setClosing(true);
    try {
      await api.patch("/api/agencies/me", { onboarding_completed: true });
      await load(true);
    } catch {
      /* non-fatal — modal stays dismissed for this session */
    }
  }

  return (
    <div role="dialog" aria-modal="true" aria-label="Welcome tour"
      className="fixed inset-0 z-50 grid place-items-center p-4"
      style={{ background: "rgba(26, 26, 24, 0.45)", backdropFilter: "blur(4px)" }}>
      <div className="w-full max-w-xl rounded-3xl bg-white shadow-lift overflow-hidden border border-cream-300">
        {/* Art panel — pastel mesh paper with ink line-art. */}
        <div className="relative h-56 grid place-items-center overflow-hidden bg-mesh-hero border-b border-cream-300">
          {s.art}
        </div>

        <div className="p-7">
          <p className="kicker text-gold-600">{s.kicker}</p>
          <h2 className="font-serif text-2xl text-ink mt-1.5">{s.title}</h2>
          <p className="text-sm text-ink-soft leading-relaxed mt-3 min-h-[72px]">{s.body}</p>

          <div className="flex items-center justify-between mt-6">
            <div className="flex items-center gap-2" role="tablist" aria-label="Slides">
              {slides.map((_, d) => (
                <button key={d} onClick={() => setI(d)} aria-label={`Slide ${d + 1}`}
                  role="tab" aria-selected={d === i}
                  className={`h-2 rounded-full transition-all duration-200 ${d === i ? "w-6 bg-ink" : "w-2 bg-cream-400 hover:bg-navy-300"}`} />
              ))}
            </div>
            <div className="flex items-center gap-2">
              {i > 0 && (
                <button className="btn-secondary text-sm" onClick={() => setI(i - 1)}>
                  Back
                </button>
              )}
              {!last && (
                <button className="btn-ghost text-sm" onClick={finish}>
                  Skip
                </button>
              )}
              <button className="btn-primary px-6" onClick={() => (last ? finish() : setI(i + 1))}>
                {last ? "Get started" : "Next"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

type Slide = { kicker: string; title: string; body: string; art: JSX.Element };

/* --- inline SVG illustrations (white-on-navy line art) -------------------- */

function PipelineArt() {
  // Ink line-art on the pastel mesh panel (F's hand-drawn language).
  const INK = "#1a1a18";
  return (
    <svg width="380" height="120" viewBox="0 0 380 120" fill="none" className="relative" aria-hidden>
      <line x1="20" y1="60" x2="360" y2="60" stroke="rgba(26,26,24,0.25)" strokeWidth="2" strokeDasharray="6 6" />
      {[40, 115, 190, 265, 340].map((x, idx) => (
        <g key={x}>
          <circle cx={x} cy="60" r={idx === 2 ? 17 : 13}
            fill={idx <= 2 ? "#C9A24C" : "#ffffff"}
            stroke={INK} strokeWidth="2" />
          {idx <= 2 && <path d={`M${x - 5} 60 l4 4 l7 -8`} stroke={INK} strokeWidth="2.5" fill="none" strokeLinecap="round" />}
        </g>
      ))}
      <text x="190" y="100" textAnchor="middle" fill="rgba(26,26,24,0.65)" fontSize="11" fontFamily="Inter, sans-serif">
        Nine stages · gate-checked progression
      </text>
    </svg>
  );
}

function ShieldArt() {
  const INK = "#1a1a18";
  return (
    <svg width="160" height="140" viewBox="0 0 160 140" fill="none" className="relative" aria-hidden>
      <path d="M80 12 L132 30 V70 C132 102 108 122 80 130 C52 122 28 102 28 70 V30 Z"
        fill="#ffffff" stroke={INK} strokeWidth="2.5" />
      <path d="M58 70 l16 16 l30 -34" stroke="#C9A24C" strokeWidth="5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SignArt() {
  const INK = "#1a1a18";
  return (
    <svg width="220" height="140" viewBox="0 0 220 140" fill="none" className="relative" aria-hidden>
      <rect x="35" y="18" width="120" height="104" rx="10" fill="#ffffff" stroke={INK} strokeWidth="2.5"
        transform="rotate(-2 95 70)" />
      <g transform="rotate(-2 95 70)">
        <line x1="52" y1="42" x2="138" y2="42" stroke="rgba(26,26,24,0.35)" strokeWidth="2.5" strokeLinecap="round" />
        <line x1="52" y1="58" x2="138" y2="58" stroke="rgba(26,26,24,0.35)" strokeWidth="2.5" strokeLinecap="round" />
        <line x1="52" y1="74" x2="112" y2="74" stroke="rgba(26,26,24,0.35)" strokeWidth="2.5" strokeLinecap="round" />
        <path d="M52 102 C 64 88, 72 110, 84 96 S 104 92, 112 98" stroke="#C9A24C" strokeWidth="3.5" fill="none" strokeLinecap="round" />
      </g>
      <circle cx="172" cy="96" r="26" fill="#C9A24C" stroke={INK} strokeWidth="2.5" />
      <text x="172" y="103" textAnchor="middle" fill={INK} fontSize="20" fontWeight="700" fontFamily="Inter, sans-serif">£</text>
    </svg>
  );
}

function PriceArt({ fee }: { fee: number }) {
  return (
    <div className="relative text-ink">
      <div className="bg-white border border-cream-300 shadow-paper px-10 py-6 text-center -rotate-1"
        style={{ borderRadius: "26px 30px 24px 32px" }}>
        <div className="text-4xl font-semibold font-serif">£{fee}</div>
        <div className="text-[11px] uppercase tracking-kicker text-ink-muted mt-1.5">one-time · per new tenancy</div>
      </div>
    </div>
  );
}
