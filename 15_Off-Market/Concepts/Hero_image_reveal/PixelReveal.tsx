/**
 * PixelReveal — hero photo that resolves out of coarse pixel blocks,
 * the front sweeping from one corner toward the opposite one.
 *
 * Drop-in React component. No dependencies, no CSS file needed.
 *
 *   <PixelReveal src={photo} alt="12 Huntingdale Dr, Robina" />
 *
 * Concept build — see 12_Marketing/PixelReveal/README.md
 */

import { useEffect, useRef } from "react";

export type RevealOrigin = "bl" | "br" | "tl" | "tr" | "c";

export interface PixelRevealProps {
  /** Image URL. Must be same-origin or CORS-enabled (canvas reads it). */
  src: string;
  /** Accessible description of the photo. */
  alt?: string;
  /** Where the reveal starts. Default bottom-left. */
  origin?: RevealOrigin;
  /** Size of one reveal cell in device pixels. Default 28. */
  tile?: number;
  /** Total sweep time in ms. Default 2600. */
  duration?: number;
  /** 0 = straight diagonal wall, 1 = circular bloom from the corner. Default 0.55. */
  shape?: number;
  /** Randomises each cell's turn so the edge breaks up. 0–1. Default 0.22. */
  scatter?: number;
  /** How long one cell takes to sharpen, as a fraction of duration. Default 0.26. */
  trail?: number;
  /** Pixelation depth — a cell starts at 2^(levels+1) px blocks. Default 5 (64px). */
  levels?: number;
  /** Colour the photo emerges from. Default Fields grass-dark. */
  ground?: string;
  /** Warm tint on cells at the leading edge. Default Fields copper. Pass null to disable. */
  frontTint?: string | null;
  /** Replays whenever this value changes. */
  replayKey?: string | number;
  /** Only start once the element scrolls into view. Default true. */
  revealOnScroll?: boolean;
  className?: string;
  style?: React.CSSProperties;
  onDone?: () => void;
}

interface Mip { cv: HTMLCanvasElement; b: number }
interface Cell { x: number; y: number; w: number; h: number; start: number }

const MAX_RENDER_W = 1600;

/* Deterministic jitter so repeat views look identical. */
function makeRand(seed: number) {
  let s = seed >>> 0 || 1;
  return () => {
    s ^= s << 13; s >>>= 0;
    s ^= s >> 17;
    s ^= s << 5; s >>>= 0;
    return s / 4294967296;
  };
}

const easeOutCubic = (t: number) => { const u = 1 - t; return 1 - u * u * u; };
const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

export default function PixelReveal({
  src,
  alt = "",
  origin = "bl",
  tile = 28,
  duration = 2600,
  shape = 0.55,
  scatter = 0.22,
  trail = 0.26,
  levels = 5,
  ground = "#0d1611",
  frontTint = "#c97a57",
  replayKey,
  revealOnScroll = true,
  className,
  style,
  onDone,
}: PixelRevealProps) {
  const cvRef = useRef<HTMLCanvasElement>(null);
  const doneRef = useRef(onDone);
  doneRef.current = onDone;

  useEffect(() => {
    const cv = cvRef.current;
    if (!cv) return;
    const ctx = cv.getContext("2d", { alpha: false });
    if (!ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let img: HTMLImageElement | null = null;
    let rw = 0, rh = 0;
    let mips: Mip[] = [];
    let settled: HTMLCanvasElement | null = null;
    let sctx: CanvasRenderingContext2D | null = null;
    let cells: Cell[] = [];
    let settledIdx = 0, activeEnd = 0;
    let raf = 0, startedAt = 0, cancelled = false;
    let resizeTimer: number | undefined;

    /* ---- pixelation stack: full res, 2px, 4px … 2^(levels+1) ---- */
    function buildMips() {
      if (!img) return;
      mips = [];
      for (let i = 0; i < levels + 2; i++) {
        const b = 1 << i;
        const w = Math.max(1, Math.ceil(rw / b));
        const h = Math.max(1, Math.ceil(rh / b));
        const c = document.createElement("canvas");
        c.width = w; c.height = h;
        const g = c.getContext("2d")!;
        g.imageSmoothingEnabled = true;
        g.imageSmoothingQuality = "high";
        g.drawImage(img, 0, 0, w, h);
        mips.push({ cv: c, b });
      }
    }

    /* ---- the delay field: every cell's start time ---- */
    function buildCells() {
      const cols = Math.ceil(rw / tile);
      const rows = Math.ceil(rh / tile);
      const ox = origin === "br" || origin === "tr" ? rw : origin === "c" ? rw / 2 : 0;
      const oy = origin === "bl" || origin === "br" ? rh : origin === "c" ? rh / 2 : 0;

      // diagonal direction = origin -> centre (degenerate when origin IS the centre)
      const vx = rw / 2 - ox, vy = rh / 2 - oy;
      const vlen = Math.hypot(vx, vy);
      const hasDiag = vlen > 1;
      const dirX = hasDiag ? vx / vlen : 0;
      const dirY = hasDiag ? vy / vlen : 0;
      const mixToRadial = hasDiag ? shape : 1;

      const rand = makeRand(0x9e3779b9 ^ (cols * 73856093) ^ (rows * 19349663));
      const raw: Array<Cell & { diag: number; radial: number; jitter: number }> = [];

      for (let j = 0; j < rows; j++) {
        for (let i = 0; i < cols; i++) {
          const x = i * tile, y = j * tile;
          const w = Math.min(tile, rw - x), h = Math.min(tile, rh - y);
          const dx = x + w / 2 - ox, dy = y + h / 2 - oy;
          raw.push({
            x, y, w, h, start: 0,
            diag: hasDiag ? dx * dirX + dy * dirY : 0,
            radial: Math.hypot(dx, dy),
            jitter: rand() - 0.5,
          });
        }
      }

      let dMin = Infinity, dMax = -Infinity, rMax = 0;
      for (const c of raw) {
        if (c.diag < dMin) dMin = c.diag;
        if (c.diag > dMax) dMax = c.diag;
        if (c.radial > rMax) rMax = c.radial;
      }
      const dSpan = dMax - dMin || 1;
      rMax = rMax || 1;

      for (const c of raw) {
        const nd = (c.diag - dMin) / dSpan;
        const nr = c.radial / rMax;
        const d = nd + (nr - nd) * mixToRadial;
        c.start = clamp01(d + c.jitter * scatter) * (1 - trail);
      }

      raw.sort((a, b) => a.start - b.start);
      cells = raw;
    }

    function layout(): boolean {
      if (!img) return false;
      const cssW = cv!.parentElement?.clientWidth || cv!.clientWidth || 900;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = Math.min(Math.round(cssW * dpr), MAX_RENDER_W, img.naturalWidth * 2);
      const h = Math.round((w * img.naturalHeight) / img.naturalWidth);
      if (w === rw && h === rh) return false;
      rw = w; rh = h;
      cv!.width = rw; cv!.height = rh;
      cv!.style.aspectRatio = `${img.naturalWidth} / ${img.naturalHeight}`;
      settled = document.createElement("canvas");
      settled.width = rw; settled.height = rh;
      sctx = settled.getContext("2d");
      buildMips();
      return true;
    }

    function finish() {
      if (!img || !sctx) return;
      ctx!.fillStyle = ground;
      ctx!.fillRect(0, 0, rw, rh);
      ctx!.imageSmoothingEnabled = true;
      ctx!.drawImage(img, 0, 0, rw, rh);
      sctx.imageSmoothingEnabled = true;
      sctx.drawImage(img, 0, 0, rw, rh);
      settledIdx = cells.length;
      doneRef.current?.();
    }

    function frame(now: number) {
      if (cancelled) return;
      const T = (now - startedAt) / duration;
      if (T >= 1) { finish(); return; }

      // retire finished cells into the settled layer — drawn once, never again
      while (settledIdx < cells.length && cells[settledIdx].start + trail <= T) {
        const s = cells[settledIdx];
        sctx!.imageSmoothingEnabled = true;
        sctx!.drawImage(mips[0].cv, s.x, s.y, s.w, s.h, s.x, s.y, s.w, s.h);
        settledIdx++;
      }
      while (activeEnd < cells.length && cells[activeEnd].start <= T) activeEnd++;

      ctx!.fillStyle = ground;
      ctx!.fillRect(0, 0, rw, rh);
      ctx!.imageSmoothingEnabled = false;
      ctx!.drawImage(settled!, 0, 0);

      for (let i = settledIdx; i < activeEnd; i++) {
        const c = cells[i];
        const p = clamp01((T - c.start) / trail);
        const e = easeOutCubic(p);
        const lv = Math.min(mips.length - 1, Math.max(0, Math.floor((1 - e) * mips.length)));
        const m = mips[lv];

        ctx!.globalAlpha = p < 0.34 ? p / 0.34 : 1;
        ctx!.drawImage(m.cv, c.x / m.b, c.y / m.b, c.w / m.b, c.h / m.b, c.x, c.y, c.w, c.h);

        if (e < 1) {
          ctx!.globalAlpha = (1 - e) * 0.62;
          ctx!.fillStyle = ground;
          ctx!.fillRect(c.x, c.y, c.w, c.h);
        }
        if (frontTint && p < 0.3) {
          ctx!.globalAlpha = (0.3 - p) * 0.9;
          ctx!.fillStyle = frontTint;
          ctx!.fillRect(c.x, c.y, c.w, c.h);
        }
      }
      ctx!.globalAlpha = 1;
      raf = requestAnimationFrame(frame);
    }

    function play() {
      if (!img || cancelled) return;
      buildCells();
      settledIdx = 0; activeEnd = 0;
      sctx!.clearRect(0, 0, rw, rh);
      ctx!.fillStyle = ground;
      ctx!.fillRect(0, 0, rw, rh);
      if (reduced) { finish(); return; }
      startedAt = performance.now();
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(frame);
    }

    let io: IntersectionObserver | null = null;
    function begin() {
      if (!revealOnScroll) { play(); return; }
      io = new IntersectionObserver((entries) => {
        if (entries.some((en) => en.isIntersecting)) { io?.disconnect(); io = null; play(); }
      }, { threshold: 0.25 });
      io.observe(cv!);
    }

    const loader = new Image();
    loader.crossOrigin = "anonymous";
    loader.onload = () => {
      if (cancelled) return;
      img = loader;
      rw = 0; rh = 0;
      layout();
      begin();
    };
    loader.src = src;

    const onResize = () => {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => { if (layout()) play(); }, 180);
    };
    window.addEventListener("resize", onResize);

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      window.clearTimeout(resizeTimer);
      window.removeEventListener("resize", onResize);
      io?.disconnect();
    };
  }, [src, origin, tile, duration, shape, scatter, trail, levels, ground, frontTint, replayKey, revealOnScroll]);

  return (
    <canvas
      ref={cvRef}
      role="img"
      aria-label={alt}
      className={className}
      style={{ display: "block", width: "100%", height: "auto", background: ground, ...style }}
    />
  );
}
