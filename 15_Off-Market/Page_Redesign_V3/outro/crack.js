/**
 * crack.js — the screen cracks, then the glass falls away and leaves the code.
 *
 *   FieldsCrack.strike(x, y, { reveal: rainCanvas, onOpenStart, onDone });
 *
 * Two pieces of artwork and one piece of geometry:
 *
 *   cracked-glass.png      the impact chip. Dense, irregular, full of light —
 *                          the part that has to be drawn, because two rounds of
 *                          generating it in code read as a spider web.
 *   cracked-glass-v4.png   the whole-pane network, scaled over the screen.
 *   glass_pieces.json      that network cut into 75 tiling polygons by
 *                          cut_glass.py. Asking a generator for 200 shards gives
 *                          200 that do not fit; cutting one master image gives
 *                          pieces bounded by cracks that were actually drawn.
 *
 * Beats:
 *   1. IMPACT   chip under the pointer, one small hole, code visible through it
 *   2. EXTEND   a crack creeps then runs to the top
 *   3. GASH     that crack separates — two edges, widening, more code showing
 *   4. NETWORK  the fracture races across the whole pane, fast, like lightning
 *   5. FALL     pieces let go in waves from the impact outward, revealing the
 *               code that has been running behind the whole time
 *
 * The two-layer rule holds throughout: glass in front, code behind, and the
 * code is only ever visible where there is no glass.
 */
(function (global) {
  "use strict";

  // Assets resolve against the DOCUMENT, and this now runs from two places: the
  // demo in this folder, and the deck two directories away. Set
  // window.FIELDS_OUTRO_BASE before loading to point at this folder; the default
  // of "" keeps the demo working unchanged.
  const BASE = (global.FIELDS_OUTRO_BASE || "");
  const CHIP_SRC = BASE + "cracked-glass.png";
  const NET_SRC = BASE + "cracked-glass-v4.png";
  const PIECES_SRC = BASE + "glass_pieces.json";
  // The same cut, simplified: 886 vertices against 2178, for the same 67-odd
  // pieces. Vertex count is what the per-frame path cost scales with, and on a
  // phone the difference between a 29-sided shard and a 13-sided one is
  // invisible while it is tumbling.
  const PIECES_LO_SRC = BASE + "glass_pieces_lo.json";
  const SMALL_SCREEN = Math.min(innerWidth, innerHeight) < 520;
  const TAU = Math.PI * 2;

  function rng(seed) {
    let s = seed >>> 0 || 1;
    return function () {
      s ^= s << 13; s >>>= 0; s ^= s >> 17; s ^= s << 5; s >>>= 0;
      return s / 4294967296;
    };
  }

  // ── assets ────────────────────────────────────────────────────────────────
  // Each PNG is opaque black with bright cracks, so `source-in` against it
  // would keep everything. Rebuild once as white-with-alpha-from-luminance.
  function toMask(img) {
    const c = document.createElement("canvas");
    c.width = img.naturalWidth; c.height = img.naturalHeight;
    const g = c.getContext("2d");
    g.drawImage(img, 0, 0);
    const d = g.getImageData(0, 0, c.width, c.height), px = d.data;
    for (let i = 0; i < px.length; i += 4) {
      const l = (px[i] * 0.299 + px[i + 1] * 0.587 + px[i + 2] * 0.114) / 255;
      px[i] = px[i + 1] = px[i + 2] = 255;
      px[i + 3] = Math.round(Math.min(1, Math.pow(l, 0.75) * 1.25) * 255);
    }
    g.putImageData(d, 0, 0);
    return c;
  }
  const loadImg = (src) => new Promise((res, rej) => {
    const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src;
  });

  let ASSETS = null, assetsReady = null;
  function loadAssets() {
    if (assetsReady) return assetsReady;
    assetsReady = Promise.all([
      loadImg(CHIP_SRC), loadImg(NET_SRC),
      fetch(SMALL_SCREEN ? PIECES_LO_SRC : PIECES_SRC).then((r) => r.json()),
    ]).then(([chip, net, pieces]) => {
      ASSETS = { chip: toMask(chip), net: toMask(net), pieces };
      return ASSETS;
    });
    return assetsReady;
  }
  // NOT called at module load any more. Doing so downloaded 1.9MB of PNGs and
  // decoded two 1254x1254 images into canvases the instant any deck opened —
  // before the reader had seen card 00, and for every reader including the ones
  // who never reach the button. On a phone that is real bandwidth and real
  // memory pressure. `strike()` loads them itself if they are not ready, so
  // preload() is purely an optimisation: the deck calls it when card 11 comes
  // into view, which is early enough to be ready and late enough to be free.

  function jaggedRay(cx, cy, angle, len, rand, steps) {
    const pts = [[cx, cy]];
    let a = angle;
    const n = steps || Math.max(6, Math.round(len / 26));
    for (let i = 1; i <= n; i++) {
      const t = i / n;
      a += (rand() - 0.5) * 0.26 * t;
      pts.push([cx + Math.cos(a) * len * t, cy + Math.sin(a) * len * t]);
    }
    return pts;
  }

  /** A path offset into a band with near-parallel edges — a separated crack. */
  function band(pts, w0) {
    const n = pts.length, left = [], right = [];
    for (let i = 0; i < n; i++) {
      const t = i / Math.max(1, n - 1);
      const p = pts[i];
      const q = pts[Math.min(n - 1, i + 1)], r = pts[Math.max(0, i - 1)];
      let dx = q[0] - r[0], dy = q[1] - r[1];
      const L = Math.hypot(dx, dy) || 1; dx /= L; dy /= L;
      const w = w0 * (0.55 + 0.45 * (1 - t));   // never vanishes at the tip
      left.push([p[0] - dy * w, p[1] + dx * w]);
      right.push([p[0] + dy * w, p[1] - dx * w]);
    }
    return { poly: left.concat(right.reverse()), left, right };
  }

  function tracePoly(ctx, poly) {
    ctx.moveTo(poly[0][0], poly[0][1]);
    for (let i = 1; i < poly.length; i++) ctx.lineTo(poly[i][0], poly[i][1]);
    ctx.closePath();
  }

  /**
   * Fines. Only 75 large pieces fall, which on its own reads like cut paper —
   * real breakage throws a cloud of fragments far smaller and far faster than
   * the panes, plus a puff of dust at the strike. Cheap, and it is most of the
   * difference between "graphic" and "that just broke".
   */
  function burst(list, x, y, n, speed, rand, spread) {
    for (let i = 0; i < n; i++) {
      const a = rand() * TAU;
      const v = speed * (0.25 + rand() * rand() * 1.6);   // long tail: a few go far
      list.push({
        x, y,
        vx: Math.cos(a) * v * (spread || 1),
        vy: Math.sin(a) * v * (spread || 1) - v * 0.25,   // slight upward bias
        r: 0.5 + rand() * 1.9,
        life: 0, ttl: 0.5 + rand() * 1.1,
        spin: (rand() - 0.5) * 8,
        dust: rand() < 0.42,
      });
    }
  }

  function stepParticles(list, dt) {
    for (let i = list.length - 1; i >= 0; i--) {
      const q = list[i];
      q.life += dt;
      if (q.life > q.ttl) { list.splice(i, 1); continue; }
      q.vy += 1500 * dt;               // gravity
      q.vx *= 0.995; q.vy *= 0.995;
      q.x += q.vx * dt; q.y += q.vy * dt;
    }
  }

  function drawParticles(ctx, list) {
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    for (const q of list) {
      const k = 1 - q.life / q.ttl;
      if (q.dust) {
        ctx.globalAlpha = k * 0.16;
        ctx.fillStyle = "rgba(190,215,240,1)";
        ctx.beginPath(); ctx.arc(q.x, q.y, q.r * 5, 0, TAU); ctx.fill();
      } else {
        ctx.globalAlpha = k * 0.95;
        ctx.fillStyle = "rgba(255,255,255,1)";
        ctx.fillRect(q.x - q.r / 2, q.y - q.r / 2, q.r, q.r * (1 + k));
      }
    }
    ctx.restore();
  }

  // ── strike ────────────────────────────────────────────────────────────────

  function strike(x, y, o) {
    o = o || {};
    const W = innerWidth, H = innerHeight;
    // Two full-screen canvases at 2x on a phone is 2.6M pixels a frame before
    // anything is drawn into them. 1.5x is indistinguishable here — this is a
    // dark field of thin bright lines, not type — and it drops the fill cost by
    // over 40%.
    const small = Math.min(W, H) < 520;
    const dpr = Math.min(small ? 1.5 : 2, devicePixelRatio || 1);
    const rand = rng(o.seed || ((Date.now() ^ (x * 73856093)) >>> 0));
    const DIAG = Math.hypot(W, H);

    const host = document.createElement("div");
    host.className = "fx-crack";
    host.setAttribute("aria-hidden", "true");
    const cv = document.createElement("canvas");
    cv.width = W * dpr; cv.height = H * dpr;
    cv.style.cssText =
      "position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:40";
    host.appendChild(cv);
    (o.mount || document.body).appendChild(host);
    const ctx = cv.getContext("2d");
    ctx.scale(dpr, dpr);

    const chip0 = o.radius || Math.max(150, Math.min(W, H) * 0.20);
    const start = [x + (rand() - 0.5) * chip0 * 0.3, y - chip0 * 0.42];
    const runner = jaggedRay(start[0], start[1],
      -Math.PI / 2 + (rand() - 0.5) * 0.18, start[1] + 30, rand, 34);

    // The hole punched at the impact — the only thing you can see through until
    // the gash opens. The surrounding fractures are cracks, not gaps.
    const voidR = Math.max(11, chip0 * 0.09);
    const voidPoly = [];
    for (let i = 0; i < 11; i++) {
      const a = (i / 11) * TAU, rr = voidR * (0.5 + rand() * 0.85);
      voidPoly.push([x + Math.cos(a) * rr, y + Math.sin(a) * rr]);
    }

    // The whole-pane network is centred on the impact and scaled so it reaches
    // every corner, whichever corner the reader happened to press nearest.
    const reach = Math.max(
      Math.hypot(x, y), Math.hypot(W - x, y),
      Math.hypot(x, H - y), Math.hypot(W - x, H - y)) * 2.05;
    const px = (u) => x + (u - 0.5) * reach;
    const py = (v) => y + (v - 0.5) * reach;

    // `skipGash` runs impact -> network -> fall only, dropping the crack that
    // travels to the top and the gap that opens along it. They are two separate
    // ideas and they muddle each other when both play in one strike.
    const SKIP = !!o.skipGash;
    const IMPACT_HOLD = o.impactHold == null ? 1000 : o.impactHold;
    const EXTEND_MS   = SKIP ? 0 : (o.extendMs == null ? 1900 : o.extendMs);
    const GASH_MS     = SKIP ? 0 : (o.gashMs   == null ? 2600 : o.gashMs);
    const NETWORK_MS  = o.networkMs  == null ?  900 : o.networkMs;   // lightning
    const SETTLE_MS   = o.settleMs   == null ?  500 : o.settleMs;
    const FALL_MS     = o.fallMs     == null ? 3800 : o.fallMs;
    const easeRun = (t) => Math.pow(t, 3.2);

    // A phone has a fraction of the fill rate and every particle is a draw
    // call. Two thirds of them there is invisible; the frame rate is not.
    const FINES_IMPACT = small ? 55 : 130;
    const FINES_PER_PIECE = small ? 2 : 5;
    // Both artworks were being scaled from 1254x1254 up to the screen EVERY
    // frame, under `lighter`, twice. Profiling put the pre-fall phases at 11-13
    // fps against the fall's 38 - the opposite of what I assumed. Pre-render
    // them to screen-sized layers once and blit 1:1 thereafter.
    let chipLayer = null, netLayer = null;
    function prerender() {
      const mk = () => {
        const c = document.createElement("canvas");
        c.width = W * dpr; c.height = H * dpr;
        const g = c.getContext("2d"); g.scale(dpr, dpr);
        return { c, g };
      };
      const a = mk(), b2 = mk(), cw = chip0 * 2;
      a.g.drawImage(ASSETS.chip, x - cw / 2, y - cw / 2, cw, cw);
      b2.g.drawImage(ASSETS.net, px(0), py(0), reach, reach);
      chipLayer = a.c; netLayer = b2.c;
    }

    let pieces = null, gashBand = null, fines = [], lastT = 0;
    const perf = { frames: 0, worst: 0, fallFrames: 0, fallMs: 0,
                   byPhase: {}, worstAt: null };
    global.__crackPerf = perf;
    let netCalled = false, doneCalled = false, openCalled = false,
        fallCalled = false, t0 = null;

    // Adaptive degrade. The crack itself is cheap now; the fall is 67 tumbling
    // polygons and a particle field, and on a genuinely slow device that lands
    // at 18-30fps however much it is tuned. Rather than ship a stutter, measure
    // the opening second on the actual device and, if it cannot hold up, keep
    // the fracture — which is the good part — and swap the fall for a quick
    // dissolve. Decided from real frames, not a user-agent guess.
    let degraded = false;
    function checkBudget() {
      const c = perf.byPhase.chip;
      if (!c || c.n < 8) return;
      degraded = (c.ms / c.n) > 34;      // slower than ~29fps
    }

    function initPieces() {
      const r2 = rng(0x51ed270b);
      pieces = ASSETS.pieces.pieces.map((p) => {
        const cx = px(p.c[0]), cy = py(p.c[1]);
        const d = Math.hypot(cx - x, cy - y) || 1;
        return {
          poly: p.poly.map(([u, v]) => [px(u), py(v)]),
          cx, cy,
          // Waves outward from the impact, and bigger pieces sooner — the order
          // real safety glass releases in, rather than everything at once.
          delay: Math.min(0.7, (d / (reach * 0.55)) * 0.55)
                 + (1 - Math.min(1, p.a / 0.03)) * 0.12 + r2() * 0.10,
          spin: (r2() - 0.5) * 3.4,
          phase: r2() * TAU,
          drift: (r2() - 0.5) * 240,
          fall: 900 + r2() * 900,
        };
      });
    }

    function draw(phase, runT, open, net, fall, flash) {
      ctx.clearRect(0, 0, W, H);
      const chipW = chip0 * 2;

      if (phase === "fall") {
        // The pane is over the code now. Pieces that have not let go are still
        // glass; the ones that have are tumbling away, and what they leave
        // behind is what was always running underneath.
        // Black, not the reveal canvas. The code deliberately does not start
        // until the glass has completely gone, so through the whole fall the
        // reveal IS a blank black canvas — blitting a full-screen canvas every
        // frame to paint black was pure cost.
        ctx.fillStyle = "#000";
        ctx.fillRect(0, 0, W, H);
        for (const p of pieces) {
          const t = Math.max(0, Math.min(1, (fall - p.delay) / (1 - p.delay || 1)));
          if (t >= 0.53) continue;          // fully faded (1 - t*1.9 <= 0)
          if (t > 0 && !p.threw) {
            // a puff as each piece lets go, not one burst for the whole pane
            p.threw = true;
            burst(fines, p.cx, p.cy, FINES_PER_PIECE, 210, rand, 0.8);
          }
          ctx.save();
          let lit = 1;
          if (t > 0) {
            const e = t * t;                       // gravity, not linear
            ctx.translate(p.drift * e, p.fall * e);
            const ang = p.spin * e;
            ctx.translate(p.cx, p.cy); ctx.rotate(ang); ctx.translate(-p.cx, -p.cy);
            // Glass flashes as a facet swings through the light. Constant
            // brightness while tumbling is what made the pieces read as flat.
            lit = small ? 1 : 0.55 + 0.45 * Math.abs(Math.cos(ang * 1.6 + p.phase));
            // Fade out hard enough to be gone before the phase ends — at 1.25
            // they were still ghosting across the screen when the code arrived.
            ctx.globalAlpha = Math.max(0, 1 - t * 1.9);
          }
          ctx.beginPath(); tracePoly(ctx, p.poly);
          if (small) {
            // One paint per piece instead of two. A stroke on a phone is a
            // second full path traversal for a hairline nobody can resolve.
            ctx.fillStyle = "rgba(165,195,225,0.16)"; ctx.fill();
          } else {
            ctx.fillStyle = `rgba(150,180,210,${0.06 + 0.09 * lit})`; ctx.fill();
            ctx.strokeStyle = `rgba(255,255,255,${0.25 + 0.5 * lit})`;
            ctx.lineWidth = 1; ctx.stroke();
          }
          ctx.restore();
        }
        // The chip is the best-looking thing in the whole effect and it was
        // switching off at the exact moment of most drama. It goes with the
        // pieces around it instead.
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        ctx.globalAlpha = Math.max(0, 0.95 - fall * 1.6);
        ctx.drawImage(chipLayer, 0, 0, W, H);
        ctx.restore();
        drawParticles(ctx, fines);
        return;
      }

      // --- the holes ------------------------------------------------------
      // Filled black, directly. The code deliberately does not start until the
      // glass has completely gone, so throughout the break every hole looks
      // into darkness - which meant the mask-and-composite dance (clear an
      // offscreen, fill it, source-in the reveal, blit it back) was three
      // full-screen operations a frame just to paint black.
      ctx.fillStyle = "#000";
      ctx.beginPath();
      tracePoly(ctx, voidPoly);
      if (open > 0 && !SKIP) {
        const w = open < 0.66
          ? 1 + Math.pow(open / 0.66, 1.5) * 95
          : 95 + Math.pow((open - 0.66) / 0.34, 2.4) * DIAG * 0.55;
        gashBand = band([[x, y]].concat(runner), w);
        tracePoly(ctx, gashBand.poly);
      }
      ctx.fill();

      // --- the pane ---------------------------------------------------------
      // Black glass over a black background is invisible. `destination-over`
      // lays this UNDER what is already drawn, so it tints the glass and never
      // the holes: the glass reads as faintly smoky, the holes as true black
      // with code in them.
      ctx.save();
      ctx.globalCompositeOperation = "destination-over";
      ctx.fillStyle = "rgba(140,170,200,0.075)";
      ctx.fillRect(0, 0, W, H);
      ctx.restore();

      // --- the fractures ----------------------------------------------------
      ctx.save();
      ctx.globalCompositeOperation = "lighter";
      ctx.globalAlpha = 0.95;
      ctx.drawImage(chipLayer, 0, 0, W, H);
      if (net > 0) {
        // Clipped to a growing disc, so the fracture PROPAGATES out from the
        // impact rather than fading in everywhere at once.
        ctx.save();
        ctx.beginPath(); ctx.arc(x, y, reach * 0.5 * net, 0, TAU); ctx.clip();
        ctx.globalAlpha = 0.9;
        ctx.drawImage(netLayer, 0, 0, W, H);
        ctx.restore();
      }
      // The flash. Two frames of it, no more — long enough to register as an
      // impact, short enough that you do not consciously see a white circle.
      if (flash > 0) {
        const g = ctx.createRadialGradient(x, y, 0, x, y, chipW * 0.9 * (1 + flash));
        g.addColorStop(0, `rgba(255,255,255,${0.85 * flash})`);
        g.addColorStop(0.4, `rgba(210,235,255,${0.3 * flash})`);
        g.addColorStop(1, "rgba(255,255,255,0)");
        ctx.globalAlpha = 1; ctx.fillStyle = g;
        ctx.fillRect(0, 0, W, H);
      }
      ctx.globalAlpha = 0.92;
      ctx.strokeStyle = "rgba(255,255,255,0.95)";
      ctx.lineWidth = 1.3; ctx.lineCap = "round";
      if (open > 0 && gashBand && !SKIP) {
        // Once it has separated there is no single crack any more — there are
        // two edges with a gap between them, and both have to be drawn.
        for (const side of [gashBand.left, gashBand.right]) {
          ctx.beginPath();
          ctx.moveTo(side[0][0], side[0][1]);
          for (let i = 1; i < side.length; i++) ctx.lineTo(side[i][0], side[i][1]);
          ctx.stroke();
        }
      } else if (runT > 0 && !SKIP) {
        const n = Math.max(2, Math.ceil(runner.length * runT));
        ctx.beginPath();
        ctx.moveTo(runner[0][0], runner[0][1]);
        for (let i = 1; i < n; i++) ctx.lineTo(runner[i][0], runner[i][1]);
        ctx.stroke();
      }
      ctx.restore();
      drawParticles(ctx, fines);
    }

    const T1 = IMPACT_HOLD, T2 = T1 + EXTEND_MS, T3 = T2 + GASH_MS,
          T4 = T3 + NETWORK_MS, T5 = T4 + SETTLE_MS, T6 = T5 + FALL_MS;

    function frame(now) {
      if (t0 == null) {
        t0 = now; lastT = now;
        // dust and fines thrown at the moment of contact
        burst(fines, x, y, FINES_IMPACT, 520, rand, 1);
        o.onImpact && o.onImpact();
      }
      const t = now - t0;
      const dtMs = now - lastT;
      perf.frames++;
      const ph = t < T1 ? "chip" : t < T4 ? "network" : t < T5 ? "settle"
               : t < T6 ? "fall" : "done";
      const rec = perf.byPhase[ph] || (perf.byPhase[ph] = { n: 0, ms: 0, worst: 0 });
      rec.n++; rec.ms += dtMs;
      if (perf.frames > 3) {
        rec.worst = Math.max(rec.worst, dtMs);
        if (dtMs > perf.worst) { perf.worst = dtMs; perf.worstAt = ph + "@" + Math.round(t) + "ms"; }
      }
      if (t >= T5 && t < T6) { perf.fallFrames++; perf.fallMs += dtMs; }
      stepParticles(fines, Math.min(0.05, dtMs / 1000));
      lastT = now;
      if (t < T1)      draw("chip", 0, 0, 0, 0, Math.max(0, 1 - t / 150));
      else if (t < T2) draw("chip", easeRun((t - T1) / EXTEND_MS), 0, 0, 0);
      else if (t < T3) {
        if (!openCalled) { openCalled = true; o.onOpenStart && o.onOpenStart(); }
        draw("gash", 1, (t - T2) / GASH_MS, 0, 0);
      } else if (t < T4) {
        if (!netCalled) {
          netCalled = true; checkBudget();
          if (!degraded) initPieces();     // no point building 67 pieces to skip
          o.onNetwork && o.onNetwork();
        }
        draw("gash", 1, 1, Math.pow((t - T3) / NETWORK_MS, 0.55), 0);
      } else if (t < T5) {
        draw("gash", 1, 1, 1, 0);                    // it holds, then lets go
      } else if (degraded) {
        // Too slow for the fall. Dissolve the pane instead — the fracture is
        // still what the reader remembers, and a clean dissolve beats a
        // stuttering shatter.
        if (!fallCalled) { fallCalled = true; o.onFall && o.onFall(); }
        const k = Math.min(1, (t - T5) / 700);
        ctx.globalAlpha = 1 - k;
        draw("gash", 1, 1, 1, 0);
        ctx.globalAlpha = 1;
        if (k >= 1) {
          ctx.clearRect(0, 0, W, H);
          host.style.display = "none";
          if (!doneCalled) { doneCalled = true; o.onDone && o.onDone(); }
          return;
        }
      } else if (t < T6) {
        if (!fallCalled) { fallCalled = true; o.onFall && o.onFall(); }
        draw("fall", 1, 1, 1, (t - T5) / FALL_MS);
      } else {
        // The glass is gone. Stand down completely rather than holding a final
        // frame — the code only starts once there is nothing left in front of it.
        ctx.clearRect(0, 0, W, H);
        host.style.display = "none";
        if (!doneCalled) { doneCalled = true; o.onDone && o.onDone(); }
        return;
      }
      requestAnimationFrame(frame);
    }

    // Motion sensitivity. A screen that appears to shatter is close to the top
    // of the list of things this setting exists to prevent, so the whole
    // sequence is skipped rather than shortened: the reader gets a straight cut
    // to what is behind it, and every callback still fires in order so the host
    // does not have to know which path it took.
    if (matchMedia("(prefers-reduced-motion: reduce)").matches && !o.forceMotion) {
      host.style.transition = "opacity .45s ease";
      o.onImpact && o.onImpact();
      o.onFall && o.onFall();
      setTimeout(() => {
        host.style.display = "none";
        o.onDone && o.onDone();
      }, 480);
      return { host, canvas: cv, cancel: () => host.remove(), reduced: true };
    }

    loadAssets().then(() => { prerender(); requestAnimationFrame(frame); })
                .catch(() => { o.onOpenStart && o.onOpenStart();
                               o.onDone && o.onDone(); });

    return { host, canvas: cv, cancel: () => host.remove() };
  }

  global.FieldsCrack = {
    preload: () => loadAssets().catch(() => {}), strike, loadAssets };
})(window);
