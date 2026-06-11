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
    <div className="fixed inset-0 z-50 grid place-items-center p-4"
      style={{ background: "rgba(15, 23, 42, 0.55)", backdropFilter: "blur(4px)" }}>
      <div className="w-full max-w-xl rounded-2xl bg-white shadow-2xl overflow-hidden border border-cream-300">
        {/* Art panel */}
        <div className="relative h-56 grid place-items-center overflow-hidden"
          style={{ background: "linear-gradient(135deg, #00306f 0%, #004AAD 55%, #1d6ae0 100%)" }}>
          <div className="absolute inset-0 opacity-20"
            style={{ backgroundImage: "radial-gradient(500px 240px at 85% -10%, #C9A24C, transparent 60%)" }} />
          {s.art}
        </div>

        <div className="p-7">
          <p className="text-xs uppercase tracking-kicker text-gold-600 font-semibold">{s.kicker}</p>
          <h2 className="font-serif text-2xl text-navy-700 mt-1.5">{s.title}</h2>
          <p className="text-sm text-ink-soft leading-relaxed mt-3 min-h-[72px]">{s.body}</p>

          <div className="flex items-center justify-between mt-6">
            <div className="flex items-center gap-2">
              {slides.map((_, d) => (
                <button key={d} onClick={() => setI(d)} aria-label={`Slide ${d + 1}`}
                  className="h-2 rounded-full transition-all"
                  style={{
                    width: d === i ? 22 : 8,
                    background: d === i ? "#004AAD" : "#e2d9c6",
                  }} />
              ))}
            </div>
            <div className="flex items-center gap-2">
              {i > 0 && (
                <button className="px-4 py-2 rounded-md border border-cream-400 text-sm text-ink-soft hover:bg-cream-100 transition"
                  onClick={() => setI(i - 1)}>
                  Back
                </button>
              )}
              {!last && (
                <button className="px-3 py-2 text-sm text-ink-muted hover:text-ink transition" onClick={finish}>
                  Skip
                </button>
              )}
              <button className="btn-primary px-5" onClick={() => (last ? finish() : setI(i + 1))}>
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
  return (
    <svg width="380" height="120" viewBox="0 0 380 120" fill="none" className="relative">
      <line x1="20" y1="60" x2="360" y2="60" stroke="rgba(255,255,255,0.35)" strokeWidth="2" strokeDasharray="6 6" />
      {[40, 115, 190, 265, 340].map((x, idx) => (
        <g key={x}>
          <circle cx={x} cy="60" r={idx === 2 ? 17 : 13}
            fill={idx <= 2 ? "#C9A24C" : "rgba(255,255,255,0.15)"}
            stroke="white" strokeWidth="2" />
          {idx <= 2 && <path d={`M${x - 5} 60 l4 4 l7 -8`} stroke="#00306f" strokeWidth="2.5" fill="none" strokeLinecap="round" />}
        </g>
      ))}
      <text x="190" y="100" textAnchor="middle" fill="rgba(255,255,255,0.85)" fontSize="11" fontFamily="Inter, sans-serif">
        Nine stages · gate-checked progression
      </text>
    </svg>
  );
}

function ShieldArt() {
  return (
    <svg width="160" height="140" viewBox="0 0 160 140" fill="none" className="relative">
      <path d="M80 12 L132 30 V70 C132 102 108 122 80 130 C52 122 28 102 28 70 V30 Z"
        fill="rgba(255,255,255,0.12)" stroke="white" strokeWidth="2.5" />
      <path d="M58 70 l16 16 l30 -34" stroke="#C9A24C" strokeWidth="5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SignArt() {
  return (
    <svg width="220" height="140" viewBox="0 0 220 140" fill="none" className="relative">
      <rect x="35" y="18" width="120" height="104" rx="8" fill="rgba(255,255,255,0.12)" stroke="white" strokeWidth="2.5" />
      <line x1="52" y1="42" x2="138" y2="42" stroke="rgba(255,255,255,0.5)" strokeWidth="2.5" strokeLinecap="round" />
      <line x1="52" y1="58" x2="138" y2="58" stroke="rgba(255,255,255,0.5)" strokeWidth="2.5" strokeLinecap="round" />
      <line x1="52" y1="74" x2="112" y2="74" stroke="rgba(255,255,255,0.5)" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M52 102 C 64 88, 72 110, 84 96 S 104 92, 112 98" stroke="#C9A24C" strokeWidth="3.5" fill="none" strokeLinecap="round" />
      <circle cx="168" cy="96" r="26" fill="#C9A24C" stroke="white" strokeWidth="2.5" />
      <text x="168" y="103" textAnchor="middle" fill="#00306f" fontSize="20" fontWeight="700" fontFamily="Inter, sans-serif">£</text>
    </svg>
  );
}

function PriceArt({ fee }: { fee: number }) {
  return (
    <div className="relative flex items-center gap-5 text-white">
      <div className="rounded-xl border border-white/40 bg-white/10 px-8 py-5 text-center">
        <div className="text-4xl font-bold font-serif">£{fee}</div>
        <div className="text-[11px] uppercase tracking-wider text-white/80 mt-1">one-time · per new tenancy</div>
      </div>
    </div>
  );
}
