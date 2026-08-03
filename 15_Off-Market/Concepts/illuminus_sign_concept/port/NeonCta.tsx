/**
 * NeonCta — the discovery deck's strategy CTA as a neon sign.
 *
 * Drop-in replacement for DiscoveryDeck.tsx:278
 *   <a className={styles.cta} href="#build-strategy" onClick={onCta}>{card.cta_label} →</a>
 * becomes
 *   <NeonCta label={card.cta_label ?? ""} href="#build-strategy" onClick={onCta} />
 *
 * Physics notes live in ../README.md. The short version: a neon sign is a gas
 * discharge tube, not a lamp on a dimmer, so the tube edge is always a hard
 * step and every apparent fade belongs to the halo. Emission is simulated at
 * 1 kHz and box-integrated per frame, which is what an eye and a camera
 * shutter do — and which is what stops the 100 Hz mains ripple aliasing into a
 * 20 Hz strobe at 60 fps.
 *
 * Differs from the concept page in two deliberate ways:
 *   - plays ONCE on scroll-into-view, then holds steady lit (no forever-loop)
 *   - the rAF loop stops when steady, and whenever the card is off-screen
 */
import { useEffect, useRef } from "react";
import styles from "./NeonCta.module.css";

/* ---- constants ---------------------------------------------------------- */
const MAINS_HZ = 50;                    // AU
const RIPPLE_HZ = MAINS_HZ * 2;         // extinguish + restrike per cycle
const RIPPLE_DEPTH = 0.14;              // iron-core ballast modulation depth
const RIPPLE_NORM = 1 / (1 - RIPPLE_DEPTH / 2);
const SUB_MS = 1;                       // 1 kHz simulation step
const TAU_ATTACK = 12;                  // ms, bloom rise
const TAU_RELEASE = 55;                 // ms, bloom fall

const PULSES = 3;
const PULSE_MS = 1150;
const PULSE_FLOOR = 0.3;
const DARK_MS = 420;

/** WCAG 2.3.1: no more than three flashes in any one second. Raw physics
 *  peaks at 8. Padding only the LIT holds to 340 ms caps it at 3 by
 *  construction without ever softening a dropout edge. */
const SAFE_MIN_STRIKE_GAP = 340;

type Seg = {
  t0: number; t1: number;
  kind: "dark" | "pulse" | "off" | "partial" | "on" | "steady";
  a?: number; ph?: number;
};
type Take = { seg: Seg[]; total: number };

function mulberry32(a: number) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** One take: dark -> three swells -> a failure -> caught, and it stays caught. */
function buildTake(seed: number, safe: boolean): Take {
  const rnd = mulberry32(seed);
  const seg: Seg[] = [];
  let t = 0;
  const push = (dur: number, o: Omit<Seg, "t0" | "t1">) => {
    seg.push({ t0: t, t1: t + dur, ...o }); t += dur;
  };

  push(DARK_MS, { kind: "dark" });
  for (let i = 0; i < PULSES; i++) push(PULSE_MS, { kind: "pulse" });

  const n = 7 + Math.floor(rnd() * 4);
  for (let i = 0; i < n; i++) {
    const last = i === n - 1;
    // extinguish — mostly short stutters, roughly one in five a long gap
    push(rnd() < 0.22 ? 180 + rnd() * 260 : 14 + rnd() * 95, { kind: "off" });
    // hesitation — partial ionisation glows dim and pink before it fully fires
    if (rnd() < 0.55) push(5 + rnd() * 16, { kind: "partial", a: 0.18 + rnd() * 0.28 });
    // strike — the first ~40 ms of a bad strike streams and wobbles
    let on = last ? 240 + rnd() * 120 : 28 + rnd() * 190;
    if (safe) on = Math.max(on, SAFE_MIN_STRIKE_GAP);
    push(on, { kind: "on", a: 0.86 + rnd() * 0.14, ph: rnd() * 6.283 });
  }

  // Terminal: caught, and it stays caught. No loop back to dark.
  push(Number.MAX_SAFE_INTEGER - t, { kind: "steady" });
  return { seg, total: t };
}

/** 100 Hz ripple, normalised so its time-average is 1.0 — the eye integrates,
 *  so a tube at full current must AVERAGE full brightness. */
function ripple(t: number) {
  const ph = 2 * Math.PI * RIPPLE_HZ * (t / 1000);
  return (1 - RIPPLE_DEPTH * (0.5 - 0.5 * Math.cos(ph))) * RIPPLE_NORM;
}

/** Emission at an instant. Pure in t, so it can be supersampled. */
function emit(take: Take, t: number): { a: number; warm: number; done: boolean } {
  let s = take.seg[take.seg.length - 1];
  for (let i = 0; i < take.seg.length; i++) {
    if (t < take.seg[i].t1) { s = take.seg[i]; break; }
  }
  const u = (t - s.t0) / (s.t1 - s.t0);
  switch (s.kind) {
    case "dark": return { a: 0, warm: 0, done: false };
    case "off": return { a: 0, warm: 1, done: false };
    case "partial": return { a: s.a!, warm: 1, done: false };
    case "pulse": {
      const swell = Math.sin(Math.PI * u) ** 2;              // 0 -> 1 -> 0
      const a = PULSE_FLOOR + (1 - PULSE_FLOOR) * swell;     // strikes instantly to the floor
      return { a: Math.min(1, a * ripple(t)), warm: (1 - a) * 0.35, done: false };
    }
    case "on": {
      const age = t - s.t0;
      const wob = 1 + 0.13 * Math.sin(2 * Math.PI * 62 * (age / 1000) + s.ph!) * Math.exp(-age / 22);
      return { a: Math.min(1, s.a! * wob * ripple(t)), warm: 0.25 * Math.exp(-age / 60), done: false };
    }
    default: {
      const drift = 1 + 0.012 * Math.sin(t / 730) + 0.007 * Math.sin(t / 271);
      return { a: Math.min(1, ripple(t) * drift), warm: 0, done: true };
    }
  }
}

export function NeonCta({
  label, href, onClick, seed,
}: {
  label: string;
  href: string;
  onClick?: (e: React.MouseEvent) => void;
  seed?: number;
}) {
  const ref = useRef<HTMLAnchorElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  /* -- the border tube: path measured from the live box so radii never distort */
  useEffect(() => {
    const el = ref.current, svg = svgRef.current;
    if (!el || !svg) return;
    const draw = () => {
      const { width: w, height: h } = el.getBoundingClientRect();
      if (!w || !h) return;
      const rad = Math.min(h / 2, 46);
      const gap = 26;                       // where the tube exits to the transformer
      // clockwise from bottom-centre-left round to bottom-centre-right — an OPEN
      // path, because real tube has two ends
      const d = [
        `M ${w / 2 - gap / 2} ${h}`,
        `H ${rad}`, `A ${rad} ${rad} 0 0 1 0 ${h - rad}`,
        `V ${rad}`, `A ${rad} ${rad} 0 0 1 ${rad} 0`,
        `H ${w - rad}`, `A ${rad} ${rad} 0 0 1 ${w} ${rad}`,
        `V ${h - rad}`, `A ${rad} ${rad} 0 0 1 ${w - rad} ${h}`,
        `H ${w / 2 + gap / 2}`,
      ].join(" ");
      const L = w / 2 - gap / 2, R = w / 2 + gap / 2;
      svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
      svg.innerHTML =
        `<path class="${styles.tGlass}" d="${d}"/>` +
        `<path class="${styles.tOuter}" d="${d}"/>` +
        `<path class="${styles.tMid}"   d="${d}"/>` +
        `<path class="${styles.tNear}"  d="${d}"/>` +
        `<line class="${styles.tElec}" x1="${L - 18}" y1="${h}" x2="${L}" y2="${h}"/>` +
        `<line class="${styles.tElec}" x1="${R}" y1="${h}" x2="${R + 18}" y2="${h}"/>` +
        `<path class="${styles.tCore}"    d="${d}"/>` +
        `<path class="${styles.tGlassHi}" d="${d}" transform="translate(0,-1.6)"/>` +
        `<line class="${styles.lead}" x1="${L}" y1="${h}" x2="${L}" y2="${h + 11}"/>` +
        `<line class="${styles.lead}" x1="${R}" y1="${h}" x2="${R}" y2="${h + 11}"/>` +
        `<rect class="${styles.housing}" x="${L - 4}" y="${h + 9}" width="${gap + 8}" height="7" rx="2"/>`;
    };
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  /* -- run the take once, on scroll-into-view -------------------------------- */
  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const set = (lvl: number, bloom: number, warm: number) => {
      el.style.setProperty("--lvl", lvl.toFixed(4));
      el.style.setProperty("--bloom", bloom.toFixed(4));
      el.style.setProperty("--warm", warm.toFixed(4));
    };

    // Anyone who has asked their OS for reduced motion gets a sign that is
    // simply lit. No pulse, no flicker, no exceptions.
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      set(1, 1, 0);
      return;
    }

    set(0, 0, 0);
    const take = buildTake(seed ?? 20260803, true);
    let raf = 0, start = 0, prevT = 0, bloom = 0, warmS = 0, running = false;

    const step = (now: number) => {
      if (!running) return;
      const t = now - start;
      // Integrate emission across this frame's exposure window at 1 kHz — this
      // is what keeps the 100 Hz ripple from aliasing into a 20 Hz strobe.
      const win = Math.min(t - prevT, 120);          // clamp after a tab switch
      const steps = Math.max(1, Math.round(win / SUB_MS));
      const dt = win / steps;
      let sum = 0, warmSum = 0, done = false;
      for (let i = 0; i < steps; i++) {
        const e = emit(take, prevT + dt * (i + 0.5));
        sum += e.a; warmSum += e.warm; done = e.done;
        const tau = e.a > bloom ? TAU_ATTACK : TAU_RELEASE;
        bloom += (e.a - bloom) * (1 - Math.exp(-dt / tau));
      }
      prevT = t;
      warmS += (warmSum / steps - warmS) * 0.25;
      set(sum / steps, bloom, warmS);

      // Caught and settled — park it lit and stop burning frames.
      if (done && t > take.total + 700) { set(1, 1, 0); running = false; return; }
      raf = requestAnimationFrame(step);
    };

    let played = false;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !played) {
          played = true; running = true;
          start = performance.now(); prevT = 0; bloom = 0; warmS = 0;
          raf = requestAnimationFrame(step);
        } else if (!entry.isIntersecting && running) {
          running = false; cancelAnimationFrame(raf);   // don't animate off-screen
        } else if (entry.isIntersecting && played && !running) {
          set(1, 1, 0);                                  // already done: just lit
        }
      },
      { threshold: 0.35 },
    );
    io.observe(el);
    return () => { running = false; cancelAnimationFrame(raf); io.disconnect(); };
  }, [seed]);

  return (
    <a ref={ref} className={styles.sign} href={href} onClick={onClick}>
      <svg ref={svgRef} className={styles.frame} aria-hidden="true" />
      <span className={styles.word}>
        <span className={styles.glass} aria-hidden="true">{label} &#8594;</span>
        <span className={styles.lit}>{label} &#8594;</span>
      </span>
    </a>
  );
}
