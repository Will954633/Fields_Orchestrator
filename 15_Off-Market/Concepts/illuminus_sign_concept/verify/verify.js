/**
 * Reproduces every measured number quoted in ../README.md.
 *
 *   cd /home/fields/Feilds_Website/01_Website
 *   node /home/fields/Fields_Orchestrator/15_Off-Market/Concepts/illuminus_sign_concept/verify/verify.js
 *
 * Run from the website directory because that is where puppeteer is installed.
 * Screenshots land in ./shots/ next to this file.
 *
 * These claims are the whole point of the concept, so they are measured rather
 * than asserted. If you change the physics constants, re-run this — the README
 * numbers are not decorative.
 */
const puppeteer = require("/home/fields/Feilds_Website/01_Website/node_modules/puppeteer");
const path = require("path");
const fs = require("fs");

const DIR   = path.resolve(__dirname, "..");
const SHOTS = path.join(__dirname, "shots");
const WALL  = "file://" + path.join(DIR, "index.html");
const ROAD  = "file://" + path.join(DIR, "roadside.html");

const stat = a => a.length
  ? { n: a.length,
      min:  +Math.min(...a).toFixed(3),
      max:  +Math.max(...a).toFixed(3),
      mean: +(a.reduce((x, y) => x + y, 0) / a.length).toFixed(3) }
  : null;

async function open(browser, url, h = 620) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1000, height: h, deviceScaleFactor: 2 });
  const errs = [];
  page.on("pageerror", e => errs.push("PAGEERROR: " + e.message));
  page.on("console", m => { if (m.type() === "error") errs.push("CONSOLE: " + m.text()); });
  await page.goto(url);
  await new Promise(r => setTimeout(r, 400));
  return { page, errs };
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await puppeteer.launch({
    headless: "new", args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  /* ---- 1. the discharge, over one untouched take ------------------------ */
  console.log("\n=== WALL SIGN — discharge ===");
  {
    const { page, errs } = await open(browser, WALL);
    const log = await page.evaluate(() => new Promise(res => {
      const rows = [];
      restart(20260803);
      const total = take.total, start = performance.now();
      (function poll() {
        const t = performance.now() - start;
        rows.push([t,
          parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--lvl")),
          document.getElementById("r-phase").textContent]);
        if (t < total) requestAnimationFrame(poll); else res(rows);
      })();
    }));
    const by = p => log.filter(r => r[2] === p).map(r => r[1]);

    // README: "steady burn lands at 97.4% mean with a 6% residual shimmer"
    console.log("steady  :", JSON.stringify(stat(by("steady"))),
                "<- ripple must NOT alias into a visible strobe");
    console.log("dark    :", JSON.stringify(stat(by("dark"))));
    for (let i = 1; i <= 3; i++)
      console.log(`pulse ${i}/3 :`, JSON.stringify(stat(by(`pulse ${i}/3`))));
    console.log("flicker :", JSON.stringify(stat(by("flicker"))));
    console.log(errs.length ? errs.join("\n") : "no js errors");
    await page.close();
  }

  /* ---- 2. flash safety, across many seeds ------------------------------ */
  console.log("\n=== WALL SIGN — flash safety (WCAG 2.3.1: max 3 flashes/sec) ===");
  {
    const { page, errs } = await open(browser, WALL);
    for (const safe of [true, false]) {
      // Strike onsets are read from the segment list rather than from rendered
      // frames — far more reliable than sampling at 60 Hz.
      const r = await page.evaluate((safe) => {
        SAFE = safe;
        let worst = 0, worstSeed = 0, rates = [];
        for (let s = 0; s < 400; s++) {
          const tk = buildTake(s * 7919 + 13);
          const on = tk.seg.filter(x => x.kind === "on").map(x => x.t0);
          let w = 0;
          for (let i = 0; i < on.length; i++) {
            let c = 0;
            for (let j = i; j < on.length && on[j] - on[i] < 1000; j++) c++;
            if (c > w) w = c;
          }
          rates.push(on.length / ((on[on.length - 1] - on[0]) / 1000));
          if (w > worst) { worst = w; worstSeed = s * 7919 + 13; }
        }
        return { worst, worstSeed, mean: rates.reduce((a, b) => a + b, 0) / rates.length };
      }, safe);
      // README: SAFE=false -> 8, SAFE=true -> 3
      console.log(`SAFE=${String(safe).padEnd(5)} worst strikes in any 1 s window: ${r.worst}` +
                  `   (mean ${r.mean.toFixed(2)}/s, worst seed ${r.worstSeed})`);
    }
    console.log(errs.length ? errs.join("\n") : "no js errors");
    await page.close();
  }

  /* ---- 3. states worth looking at -------------------------------------- */
  console.log("\n=== WALL SIGN — screenshots ===");
  {
    const { page } = await open(browser, WALL);
    for (const [name, ms] of [["dark", 200], ["pulse-peak", 995],
                              ["steady", 420 + 1150 * 3 + 3000]]) {
      await page.evaluate(ms => { calm = false; t0 = performance.now() - ms; prevT = ms - 16; }, ms);
      await new Promise(r => setTimeout(r, 150));
      await page.screenshot({ path: path.join(SHOTS, `wall-${name}.png`) });
    }
    // A hard dropout: pin emission rather than hunting for one in the timeline.
    await page.evaluate(() => { window.emit = () => ({ a: 0, warm: 1, phase: "flicker" }); });
    await new Promise(r => setTimeout(r, 500));
    await page.screenshot({ path: path.join(SHOTS, "wall-dropout.png") });
    console.log("wrote wall-{dark,pulse-peak,steady,dropout}.png");
    await page.close();
  }

  /* ---- 4. the filaments ------------------------------------------------- */
  console.log("\n=== ROADSIDE — filament thermal model ===");
  {
    const { page, errs } = await open(browser, ROAD, 760);
    // Park inside the STEADY phase — a free-running wait can land in the dark
    // rest, where the bulbs are merely cooling rather than actively chasing.
    await page.evaluate(() => {
      const s = take.seg.find(x => x.kind === "steady");
      t0 = performance.now() - (s.t0 + 400); prevT = s.t0 + 384;
    });
    await new Promise(r => setTimeout(r, 1400));       // let filaments reach chase equilibrium
    const r = await page.evaluate(() => {
      const live = bulbs.filter(b => !b.dead && !b.failing).map(b => b.T);
      const hist = [0, 0, 0, 0, 0];
      live.forEach(T => hist[Math.min(4, Math.floor(T * 5))]++);
      return { n: live.length, hist,
        partial: live.filter(T => T > 0.05 && T < 0.95).length,
        phase: document.getElementById("r-phase").textContent,
        fil: document.getElementById("r-fil").textContent };
    });
    // README: "22 of 36 live bulbs are mid-transition", histogram 10/12/0/0/14
    console.log("phase:", r.phase, "| mean filament", r.fil);
    console.log("temperature histogram (cold -> hot quintiles):", r.hist.join("  "));
    console.log(`mid-transition (0.05<T<0.95): ${r.partial}/${r.n}`,
      r.partial > 0 ? "-> filaments SMEAR (not binary)" : "-> BINARY, thermal model broken");
    await page.screenshot({ path: path.join(SHOTS, "roadside-steady.png") });

    // chase held off = every bulb driven, which is how to check arrow geometry
    await page.evaluate(() => { chaseOn = false; });
    await new Promise(r => setTimeout(r, 900));
    await page.screenshot({ path: path.join(SHOTS, "roadside-all-lit.png") });
    console.log("wrote roadside-{steady,all-lit}.png");
    console.log(errs.length ? errs.join("\n") : "no js errors");
    await page.close();
  }

  console.log("\nshots ->", SHOTS, "\n");
  await browser.close();
})();
