/**
 * Feynman — public marketing landing page (the product's front door).
 *
 * Aesthetic: "The Living Notebook." The product is a teacher who draws on a
 * board in real time as it explains — so the page is a warm sheet of paper and,
 * as you scroll, ink draws itself: the trig board assembles stroke-by-stroke,
 * the doubt-branch draws and merges, equations write themselves, a hand circles
 * a word. Light, minimal, editorial. Scoped entirely under `.fey-mkt`.
 *
 * "Try Now" (top-right) + every CTA opens <TryNowModal/>, which runs the real
 * Firebase Google sign-in. On success the AuthGate advances and this page
 * unmounts. A `?preview=landing` route in App renders this standalone so it can
 * be viewed without a live auth session.
 *
 * SVG note: ink colours / handwriting faces are applied via CSS classes
 * (`s-blue`, `f-coral`, `t-hand`…) rather than `stroke="var(--…)"` attributes —
 * `var()` does not resolve inside SVG presentation attributes in Safari.
 */

import { useRef, useState } from "react";
import "../styles/notebook-theme.css";
import "./marketing.css";
import { TryNowModal } from "./TryNowModal";
import { useScrollReveal, useStuckNav } from "./useScrollReveal";

export function MarketingLanding() {
  const scrollRef = useRef<HTMLDivElement>(null);
  const navRef = useRef<HTMLElement>(null);
  const [modalOpen, setModalOpen] = useState(false);

  useScrollReveal(scrollRef);
  useStuckNav(scrollRef, navRef);

  const openModal = () => setModalOpen(true);

  const scrollTo = (id: string) => {
    scrollRef.current
      ?.querySelector(`#${id}`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="fey-mkt notebook" ref={scrollRef}>
      <div className="fey-mkt__grain" aria-hidden />

      <header className="fey-mkt__nav" ref={navRef}>
        <div className="fey-mkt__nav-inner">
          <a
            className="fey-mkt__brand reveal"
            href="#top"
            onClick={(e) => {
              e.preventDefault();
              scrollRef.current?.scrollTo({ top: 0, behavior: "smooth" });
            }}
          >
            Feynman<span className="dot">.</span>
            <svg className="fey-mkt__brand-underline" viewBox="0 0 100 8" aria-hidden>
              <path className="pen s-blue" d="M2 5 C 22 2, 52 7, 98 3" strokeWidth="2.4" data-draw="500" />
            </svg>
          </a>

          <nav className="fey-mkt__nav-links">
            <a className="fey-mkt__nav-link" href="#how" onClick={(e) => { e.preventDefault(); scrollTo("how"); }}>
              How it works
            </a>
            <a className="fey-mkt__nav-link" href="#board" onClick={(e) => { e.preventDefault(); scrollTo("board"); }}>
              The board
            </a>
            <a className="fey-mkt__nav-link" href="#pricing" onClick={(e) => { e.preventDefault(); scrollTo("pricing"); }}>
              Pricing
            </a>
            <button type="button" className="fey-mkt__btn fey-mkt__btn--primary" onClick={openModal}>
              <span className="spark" aria-hidden />
              Try now
            </button>
          </nav>
        </div>
      </header>

      <main className="fey-mkt__content" id="top">
        <Hero onTry={openModal} onSee={() => scrollTo("how")} />
        <HowItWorks />
        <BoardShowcase />
        <ParentTrust />
        <Pricing onTry={openModal} />
        <FinalCta onTry={openModal} />
        <Footer />
      </main>

      {modalOpen && <TryNowModal onClose={() => setModalOpen(false)} />}
    </div>
  );
}

/* ── Hero ─────────────────────────────────────────────────────────────────── */

function Hero({ onTry, onSee }: { readonly onTry: () => void; readonly onSee: () => void }) {
  return (
    <section className="fey-mkt__hero">
      <div className="fey-mkt__grid" aria-hidden />
      <div className="fey-mkt__wrap">
        <div className="fey-mkt__hero-grid">
          <div>
            <span className="eyebrow reveal" style={cssVar(0)}>
              <span className="tick" /> AI teacher · Cambridge IGCSE
            </span>
            <h1 className="reveal" style={cssVar(1)}>
              The teacher who{" "}
              <span className="circled">
                draws
                <svg viewBox="0 0 100 60" aria-hidden>
                  <path
                    className="pen s-coral"
                    d="M9 36 C 6 14, 42 6, 64 9 C 90 12, 97 26, 90 39 C 83 53, 46 56, 24 51 C 9 47, 9 41, 16 35"
                    strokeWidth="2.4"
                    data-draw="900"
                  />
                </svg>
              </span>{" "}
              every idea until it clicks.
            </h1>
            <p className="lede reveal" style={cssVar(2)}>
              Feynman explains out loud and sketches the diagram as it speaks. The
              moment you say “wait, why?”, it branches back to first principles,
              redraws, and brings you right back — patient, one-on-one, and built
              for the IGCSE syllabus.
            </p>
            <div className="fey-mkt__hero-cta reveal" style={cssVar(3)}>
              <button type="button" className="fey-mkt__btn fey-mkt__btn--primary fey-mkt__btn--lg" onClick={onTry}>
                Try it tonight <span className="arrow" aria-hidden>→</span>
              </button>
              <button type="button" className="fey-mkt__btn fey-mkt__btn--ghost fey-mkt__btn--lg" onClick={onSee}>
                See it teach
              </button>
            </div>
            <p className="fey-mkt__hero-note reveal" style={cssVar(4)}>
              No card to start · Maths 0580 today · Physics &amp; Chemistry next
            </p>
          </div>

          <HeroBoard />
        </div>
      </div>
    </section>
  );
}

/** The hero's live board: a right-triangle (ladder-against-wall) drawing itself. */
function HeroBoard() {
  return (
    <div className="fey-mkt__board reveal" style={cssVar(2)}>
      <div className="fey-mkt__board-bar">
        <span className="fey-mkt__board-title">right-angled trig</span>
        <LiveBadge seeds={[0, 140, 70, 220, 110]} />
      </div>

      <svg className="board-svg" viewBox="0 0 380 280" aria-label="A right-angled triangle being drawn">
        {/* ground (adjacent) */}
        <path className="pen s-ink" d="M62 236 L300 236" strokeWidth="2.4" data-draw="120" />
        {/* wall (opposite) */}
        <path className="pen s-ink" d="M300 236 L300 86" strokeWidth="2.4" data-draw="460" />
        {/* ladder (hypotenuse) */}
        <path className="pen s-blue" d="M62 236 L300 86" strokeWidth="2.8" data-draw="820" />
        {/* rungs */}
        <path className="pen s-blue" d="M120 220 L132 200" strokeWidth="1.6" data-draw="1250" />
        <path className="pen s-blue" d="M176 184 L188 164" strokeWidth="1.6" data-draw="1330" />
        <path className="pen s-blue" d="M232 148 L244 128" strokeWidth="1.6" data-draw="1410" />
        {/* right-angle marker at the wall foot */}
        <path className="pen s-soft" d="M284 236 L284 220 L300 220" strokeWidth="1.8" data-draw="1500" />
        {/* angle arc θ */}
        <path className="pen s-coral" d="M104 236 A42 42 0 0 0 96 213" strokeWidth="2.2" data-draw="1620" />
        {/* arrow from the margin note down to the angle */}
        <path className="pen s-coral" d="M150 196 C 130 200, 120 214, 112 224" strokeWidth="1.6" data-draw="1900" />
        <path className="pen s-coral" d="M112 224 L120 218 M112 224 L120 226" strokeWidth="1.6" data-draw="2050" />

        <text className="lbl f-coral t-hand" x="120" y="232" fontSize="20" style={delay("1.8s")}>θ</text>
        <text className="lbl f-soft t-body" x="150" y="252" fontSize="13" textAnchor="middle" style={delay("0.5s")}>adjacent</text>
        <text className="lbl f-soft t-body" x="316" y="166" fontSize="13" style={delay("0.9s")}>opposite</text>
        <text className="lbl f-blue t-body" transform="rotate(-32 184 150)" x="150" y="150" fontSize="13" style={delay("1.3s")}>hypotenuse</text>
      </svg>

      <div className="note" style={{ top: 96, left: 150 }}>just similar triangles!</div>

      <div className="reveal" style={cssVar(2)}>
        <div className="mkt-eq">
          <span className="wipe">
            <span className="var">sin θ</span> ={" "}
            <span className="frac">
              <span className="num">opposite</span>
              <span className="den">hypotenuse</span>
            </span>
          </span>
          <span className="caret" aria-hidden />
        </div>
      </div>
    </div>
  );
}

/* ── How it works (the Feynman loop) ──────────────────────────────────────── */

function HowItWorks() {
  return (
    <section className="fey-mkt__section" id="how">
      <div className="fey-mkt__wrap">
        <div className="fey-mkt__head reveal" style={cssVar(0)}>
          <span className="eyebrow"><span className="tick" /> The Feynman loop</span>
          <h2>It teaches the way a great teacher actually does.</h2>
          <p className="lede">
            Not a wall of text you scroll past. A real explanation that{" "}
            <span className="hl">notices the second you’re lost</span> — and
            chases the gap down to the fundamentals.
          </p>
        </div>

        <div className="fey-mkt__loop reveal" style={cssVar(1)}>
          <BranchGraphic />
        </div>

        <div className="fey-mkt__beats">
          <Beat i={0} num="01" title="Explain simply" body="It starts from the idea, in plain language, drawing the picture as it talks — never the formula first." />
          <Beat i={1} num="02" title="Find the gap" body="The instant you’re confused — out loud, mid-sentence — it stops and figures out exactly what didn’t land." />
          <Beat i={2} num="03" title="Branch & return" body="It rewinds to the fundamental, re-explains with a fresh angle, then picks up exactly where you left off." />
        </div>
      </div>
    </section>
  );
}

function Beat({ i, num, title, body }: { readonly i: number; readonly num: string; readonly title: string; readonly body: string }) {
  return (
    <div className="fey-mkt__beat reveal" style={cssVar(i)}>
      <span className="num">{num}</span>
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}

/** Git-style lesson timeline: a doubt branch dips off the main line and merges back. */
function BranchGraphic() {
  return (
    <svg className="fey-mkt__branch" viewBox="0 0 680 190" aria-label="A lesson timeline with a doubt branch that splits off and merges back">
      {/* main lesson line */}
      <path className="pen s-ink" d="M28 64 L640 64" strokeWidth="2.6" data-draw="120" />
      {/* arrowhead at the end */}
      <path className="pen s-ink" d="M640 64 L628 57 M640 64 L628 71" strokeWidth="2.4" data-draw="520" />
      {/* doubt branch dipping down and merging back */}
      <path className="pen s-coral" d="M250 64 C 300 150, 410 150, 460 64" strokeWidth="2.6" data-draw="700" />

      {/* checkpoint nodes on the main line */}
      <circle className="lbl f-blue" cx="120" cy="64" r="6" style={delay("0.3s")} />
      <circle className="lbl f-blue" cx="250" cy="64" r="6" style={delay("0.7s")} />
      <circle className="lbl f-blue" cx="460" cy="64" r="6" style={delay("1.2s")} />
      <circle className="lbl f-blue" cx="600" cy="64" r="6" style={delay("1.5s")} />
      {/* the doubt node */}
      <circle className="lbl f-coral" cx="355" cy="132" r="7" style={delay("1.1s")} />

      <text className="lbl f-soft t-body" x="120" y="44" fontSize="13" textAnchor="middle" style={delay("0.4s")}>explaining</text>
      <text className="lbl f-soft t-body" x="600" y="44" fontSize="13" textAnchor="middle" style={delay("1.6s")}>right back on track</text>
      <text className="lbl f-coral t-hand" x="355" y="166" fontSize="22" textAnchor="middle" style={delay("1.3s")}>“wait, why?”</text>
    </svg>
  );
}

/* ── The living board showcase ────────────────────────────────────────────── */

function BoardShowcase() {
  return (
    <section className="fey-mkt__section fey-mkt__section--alt" id="board">
      <div className="fey-mkt__wrap">
        <div className="fey-mkt__show">
          <div>
            <div className="fey-mkt__head reveal" style={cssVar(0)}>
              <span className="eyebrow"><span className="tick" /> The board</span>
              <h2>A board that never goes blank.</h2>
              <p className="lede">
                Diagrams, equations and annotations appear as it speaks. It
                points, highlights, circles and connects — the screen is part of
                the explanation, not a slideshow behind it.
              </p>
            </div>

            <ul className="fey-mkt__capabilities reveal" style={cssVar(1)}>
              <Capability b="Draws as it talks" s="Geometry, graphs and diagrams sketched live, in sync with the voice." />
              <Capability b="Writes the maths" s="Equations build up term by term, exactly when they’re spoken." />
              <Capability b="Points and highlights" s="It circles the part that matters and traces the line you’re following." />
              <Capability b="Remembers the board" s="It builds on what’s already drawn instead of wiping and starting over." />
            </ul>
          </div>

          <ProjectileBoard />
        </div>
      </div>
    </section>
  );
}

function Capability({ b, s }: { readonly b: string; readonly s: string }) {
  return (
    <li>
      <span className="ic" aria-hidden>
        <CheckIcon />
      </span>
      <span>
        <b>{b}.</b> {s}
      </span>
    </li>
  );
}

/** Showcase board: a projectile parabola drawing itself, with a live annotation. */
function ProjectileBoard() {
  return (
    <div className="fey-mkt__board reveal" style={cssVar(1)}>
      <div className="fey-mkt__board-bar">
        <span className="fey-mkt__board-title">projectile motion</span>
        <LiveBadge seeds={[60, 190, 20, 150, 90]} />
      </div>

      <svg className="board-svg" viewBox="0 0 400 280" aria-label="A projectile-motion parabola being drawn">
        {/* axes */}
        <path className="pen s-ink" d="M60 44 L60 240" strokeWidth="2.2" data-draw="120" />
        <path className="pen s-ink" d="M60 240 L376 240" strokeWidth="2.2" data-draw="300" />
        <path className="pen s-ink" d="M60 44 L54 56 M60 44 L66 56" strokeWidth="2" data-draw="480" />
        <path className="pen s-ink" d="M376 240 L364 234 M376 240 L364 246" strokeWidth="2" data-draw="480" />
        {/* the trajectory */}
        <path className="pen s-blue" d="M60 240 Q 218 24 376 240" strokeWidth="3" data-draw="640" />
        {/* guide to peak */}
        <path className="guide s-coral" d="M218 132 L218 240" strokeWidth="1.6" />
        {/* peak dot */}
        <circle className="lbl f-coral" cx="218" cy="132" r="6" style={delay("1.5s")} />

        <text className="lbl f-soft t-body" x="44" y="50" fontSize="13" textAnchor="middle" style={delay("0.7s")}>h</text>
        <text className="lbl f-soft t-body" x="372" y="262" fontSize="13" textAnchor="middle" style={delay("0.7s")}>x</text>
      </svg>

      <div className="note" style={{ top: 92, right: 30 }}>max height ↑</div>

      <div className="reveal" style={cssVar(1)}>
        <div className="mkt-eq">
          <span className="wipe">
            <span className="var">h</span> ={" "}
            <span className="frac">
              <span className="num">u² sin²θ</span>
              <span className="den">2g</span>
            </span>
          </span>
          <span className="caret" aria-hidden />
        </div>
      </div>
    </div>
  );
}

/* ── Parent / trust beat ──────────────────────────────────────────────────── */

function ParentTrust() {
  return (
    <section className="fey-mkt__section">
      <div className="fey-mkt__wrap">
        <div className="fey-mkt__trust-grid">
          <div className="reveal" style={cssVar(0)}>
            <span className="eyebrow"><span className="tick" /> For parents</span>
            <h2 style={{ marginTop: 18 }}>For the 8 p.m. “I still don’t get it.”</h2>
            <p className="lede" style={{ maxWidth: "52ch", marginTop: 20 }}>
              The tutor’s gone home. The textbook isn’t helping. Feynman sits with
              your child for as long as it takes —{" "}
              <span className="hl">never rushed, never irritated</span>, never
              makes them feel small. And it teaches exactly what they’re studying:
              Cambridge IGCSE, syllabus and exam style.
            </p>
            <div className="fey-mkt__chips">
              <span className="fey-mkt__chip"><span className="d" /> Syllabus-aligned (0580)</span>
              <span className="fey-mkt__chip"><span className="d" /> Voice-first</span>
              <span className="fey-mkt__chip"><span className="d" /> Infinitely patient</span>
              <span className="fey-mkt__chip"><span className="d" /> You see every session</span>
            </div>
          </div>

          <blockquote className="fey-mkt__quote reveal" style={cssVar(1)}>
            “The best teachers don’t just answer the question. They find the gap
            you didn’t know you had — and fill it.”
          </blockquote>
        </div>
      </div>
    </section>
  );
}

/* ── Pricing ──────────────────────────────────────────────────────────────── */

function Pricing({ onTry }: { readonly onTry: () => void }) {
  return (
    <section className="fey-mkt__section fey-mkt__section--alt" id="pricing">
      <div className="fey-mkt__wrap">
        <div className="fey-mkt__head reveal" style={cssVar(0)}>
          <span className="eyebrow"><span className="tick" /> Pricing</span>
          <h2>Less than two tutoring sessions. Every night of the month.</h2>
        </div>

        <div className="fey-mkt__price reveal" style={cssVar(1)}>
          <div>
            <div className="amount">
              ₹4,000<sub> / month</sub>
            </div>
            <ul className="plist">
              <PriceLine s="One subject — IGCSE Mathematics 0580" />
              <PriceLine s="Unlimited live lessons and doubts" />
              <PriceLine s="A parent view of every session" />
              <PriceLine s="30% off on annual · all-subjects bundle coming" />
            </ul>
          </div>
          <button type="button" className="fey-mkt__btn fey-mkt__btn--primary fey-mkt__btn--lg" onClick={onTry}>
            Start now <span className="arrow" aria-hidden>→</span>
          </button>
        </div>
      </div>
    </section>
  );
}

function PriceLine({ s }: { readonly s: string }) {
  return (
    <li>
      <span className="ic" aria-hidden>
        <CheckIcon />
      </span>
      {s}
    </li>
  );
}

/* ── Final CTA ────────────────────────────────────────────────────────────── */

function FinalCta({ onTry }: { readonly onTry: () => void }) {
  return (
    <section className="fey-mkt__final">
      <div className="fey-mkt__wrap reveal" style={cssVar(0)}>
        <h2>Some nights the homework wins. Not tonight.</h2>
        <p className="lede">
          Give your child the patient, brilliant teacher you wish you’d had.
        </p>
        <button type="button" className="fey-mkt__btn fey-mkt__btn--primary fey-mkt__btn--lg" onClick={onTry}>
          <span className="spark" aria-hidden />
          Try Feynman free
        </button>
      </div>
    </section>
  );
}

/* ── Footer ───────────────────────────────────────────────────────────────── */

function Footer() {
  return (
    <footer className="fey-mkt__footer">
      <div className="fey-mkt__wrap">
        <div className="fey-mkt__footer-inner">
          <span className="fey-mkt__brand" style={{ fontSize: "1.1rem" }}>
            Feynman<span className="dot">.</span>
          </span>
          <span className="made">made with care in India · for IGCSE</span>
          <span>© {new Date().getFullYear()} Feynman</span>
        </div>
      </div>
    </footer>
  );
}

/* ── small shared bits ────────────────────────────────────────────────────── */

function LiveBadge({ seeds }: { readonly seeds: readonly number[] }) {
  return (
    <span className="fey-mkt__live">
      <span className="live-dot" aria-hidden />
      live
      <span className="fey-mkt__wave" aria-hidden>
        {seeds.map((ms, i) => (
          <i key={i} style={waveDelay(ms)} />
        ))}
      </span>
    </span>
  );
}

function CheckIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
      <path d="M5 12.5 L10 17.5 L19 6.5" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ── tiny style helpers (custom props need a cast through CSSProperties) ───── */

function cssVar(i: number): React.CSSProperties {
  return { "--i": i } as React.CSSProperties;
}

function waveDelay(ms: number): React.CSSProperties {
  return { "--d": ms } as React.CSSProperties;
}

function delay(d: string): React.CSSProperties {
  return { transitionDelay: d };
}
