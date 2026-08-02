#!/usr/bin/env node
/**
 * shoot.js — step index.html through headless Chrome and write frames.
 *
 * Drives ?capture=1, which swaps the rAF loop for window.__swim.frame(t, fps).
 * Every frame re-integrates the simulation from t=0 at a fixed dt, so a frame
 * is reproducible on its own and the output does not depend on how fast the
 * machine draws.
 *
 *   node shoot.js --stills 8 --from 0 --to 5      # contact sheet
 *   node shoot.js --mp4 --dur 24 --fps 30         # a full crossing
 */
const { execFile } = require("child_process");
const fs = require("fs");
const path = require("path");
// puppeteer-core lives in the orchestrator root on this VM, not alongside this
// script. Try the normal resolution first so a checkout elsewhere works, then
// fall back to the known location rather than dying on a hardcoded path.
const puppeteer = (() => {
  for (const p of ["puppeteer-core",
                   "/home/fields/Fields_Orchestrator/node_modules/puppeteer-core"]) {
    try { return require(p); } catch (e) { /* try the next one */ }
  }
  console.error("puppeteer-core not found. npm i puppeteer-core, or set NODE_PATH.");
  process.exit(1);
})();

const HERE = __dirname;
const CHROME = process.env.SITE_INSPECTOR_CHROME_PATH || "/usr/bin/google-chrome";
const ARGS = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
  "--disable-gpu", "--disable-extensions", "--disable-crash-reporter",
  "--disable-breakpad", "--disable-crashpad", "--no-crash-upload",
  "--disable-features=Crashpad,OptimizationHints,MediaRouter",
  "--disable-background-networking", "--disable-component-update", "--mute-audio",
  "--no-first-run"];

const o = { stills: 0, from: 0, to: 5, dur: 20, fps: 30, mp4: false, width: 1200,
            out: "frames", params: "" };
const a = process.argv.slice(2);
for (let i = 0; i < a.length; i++) {
  const k = a[i].replace(/^--/, "");
  if (k === "mp4") { o.mp4 = true; continue; }
  const v = a[++i];
  if (["stills", "from", "to", "dur", "fps", "width"].includes(k)) o[k] = +v;
  else o[k] = v;
}

(async () => {
  const outDir = path.join(HERE, o.out);
  fs.rmSync(outDir, { recursive: true, force: true });
  fs.mkdirSync(outDir, { recursive: true });

  const browser = await puppeteer.launch({ executablePath: CHROME, args: ARGS,
    headless: "new", protocolTimeout: 180000 });
  const page = await browser.newPage();
  await page.setViewport({ width: 1700, height: 1000, deviceScaleFactor: 1 });
  const url = `file://${path.join(HERE, "index.html")}?capture=1${o.params ? "&" + o.params : ""}`;
  await page.goto(url, { waitUntil: "load", timeout: 120000 });
  await page.waitForFunction("window.__swim && window.__swim.frame", { timeout: 60000 });

  const times = o.stills
    ? Array.from({ length: o.stills }, (_, i) =>
        o.from + (i * (o.to - o.from)) / Math.max(o.stills - 1, 1))
    : Array.from({ length: Math.round(o.dur * o.fps) }, (_, i) => i / o.fps);

  const el = await page.$("#c");
  for (let i = 0; i < times.length; i++) {
    await page.evaluate((t, fps) => window.__swim.frame(t, fps), times[i], o.fps);
    await el.screenshot({ path: path.join(outDir, `f${String(i).padStart(4, "0")}.png`) });
    if (i % 30 === 0) process.stdout.write(`\r  ${i + 1}/${times.length}`);
  }
  process.stdout.write(`\r  ${times.length}/${times.length}\n`);
  await browser.close();

  if (o.stills) {
    // contact sheet
    await new Promise((res, rej) => execFile("montage", [
      path.join(outDir, "f*.png"), "-tile", "2x", "-geometry", `${o.width}x+6+6`,
      "-background", "#0a0f16", path.join(HERE, "contact_sheet.png"),
    ], (e) => e ? rej(e) : res())).catch(async () => {
      // ImageMagick may not be present — fall back to ffmpeg tile
      await new Promise((res, rej) => execFile("ffmpeg", ["-y", "-pattern_type", "glob",
        "-i", path.join(outDir, "f*.png"), "-filter_complex",
        `scale=${o.width}:-1,tile=2x${Math.ceil(times.length / 2)}:padding=6:color=0x0a0f16`,
        "-frames:v", "1", path.join(HERE, "contact_sheet.png")],
        (e, so, se) => e ? rej(new Error(se)) : res()));
    });
    console.log("wrote contact_sheet.png");
  } else if (o.mp4) {
    await new Promise((res, rej) => execFile("ffmpeg", ["-y", "-framerate", String(o.fps),
      "-i", path.join(outDir, "f%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
      "-crf", "18", "-vf", `scale=${o.width}:-2`, path.join(HERE, "whale_swim.mp4")],
      (e, so, se) => e ? rej(new Error(se)) : res()));
    console.log("wrote whale_swim.mp4");
  }
})().catch(e => { console.error(e); process.exit(1); });
