#!/usr/bin/env node
/**
 * render_video.js — render the pixel-reveal animation to MP4 / GIF / stills.
 *
 * Drives index.html in headless Chrome with ?capture=1, which swaps the rAF
 * playback loop for window.__reveal.frame(t). Frames are stepped by hand so the
 * output is deterministic and frame-exact regardless of how fast the machine
 * renders — no dropped frames, no timing drift.
 *
 * Usage:
 *   node render_video.js                                   # default mp4, 30fps
 *   node render_video.js --mode develop --dur 6000
 *   node render_video.js --gif                             # also write a gif
 *   node render_video.js --stills 6                        # just N contact frames
 *   node render_video.js --width 720 --fps 60 --hold 1.2
 */

const { execFile } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const puppeteer = require("/home/fields/Fields_Orchestrator/node_modules/puppeteer-core");

const HERE = __dirname;
const CHROME = process.env.SITE_INSPECTOR_CHROME_PATH || "/usr/bin/google-chrome";
const LAUNCH_ARGS = [
  "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
  "--disable-gpu", "--disable-extensions", "--disable-crash-reporter",
  "--disable-breakpad", "--disable-crashpad",
  "--disable-features=Crashpad,OptimizationHints,MediaRouter",
  "--disable-background-networking", "--disable-component-update",
  "--disable-sync", "--mute-audio", "--no-first-run", "--no-crash-upload",
];

function parseArgs() {
  const a = process.argv.slice(2);
  const o = {
    mode: "growth", theme: "light", block: 5, dur: 5000,
    chaos: 0.28, mosaic: 0.85, fade: 0.055,
    fps: 30, width: 1024, hold: 1.0, gif: false, stills: 0,
    out: null,
    // host-page matching (see reveal.template.html) — null means "leave theme alone"
    paper: null, ink: null, grain: null, vignette: null,
  };
  for (let i = 0; i < a.length; i++) {
    const k = a[i].replace(/^--/, "");
    const next = () => a[++i];
    switch (k) {
      case "mode": case "theme": case "paper": case "ink": o[k] = next(); break;
      case "grain": case "vignette": o[k] = next(); break;
      case "block": case "dur": case "fps": case "width": o[k] = +next(); break;
      case "chaos": case "mosaic": case "fade": case "hold": o[k] = +next(); break;
      case "stills": o.stills = +next(); break;
      case "gif": o.gif = true; break;
      case "out": o.out = next(); break;
      case "help": console.log(fs.readFileSync(__filename, "utf8").split("*/")[0]); process.exit(0);
      default: console.error(`unknown flag: ${a[i]}`); process.exit(1);
    }
  }
  // h264 needs even dimensions
  if (o.width % 2) o.width += 1;
  return o;
}

const run = (cmd, args) => new Promise((res, rej) => {
  execFile(cmd, args, { maxBuffer: 1 << 26 }, (err, stdout, stderr) =>
    err ? rej(new Error(`${cmd} failed: ${stderr || err.message}`)) : res(stdout));
});

async function main() {
  const o = parseArgs();
  const indexPath = path.join(HERE, "index.html");
  if (!fs.existsSync(indexPath)) {
    console.error("index.html missing — run: python3 build_master.py");
    process.exit(1);
  }

  const q = new URLSearchParams({
    capture: "1", w: String(o.width), mode: o.mode, theme: o.theme,
    block: String(o.block), dur: String(o.dur), chaos: String(o.chaos),
    mosaic: String(o.mosaic), fade: String(o.fade),
  });
  for (const k of ["paper", "ink", "grain", "vignette"]) {
    if (o[k] !== null) q.set(k, String(o[k]));
  }
  const url = `file://${indexPath}?${q}`;

  // stills never touch this; only create it when frames are actually written
  const frameDir = o.stills > 0 ? null : fs.mkdtempSync(path.join(os.tmpdir(), "palm-reveal-"));
  try {
    await render(o, url, frameDir);
  } finally {
    // a few hundred full-size PNGs — clear them however we got here, including
    // a browser crash part-way through capture
    if (frameDir) fs.rmSync(frameDir, { recursive: true, force: true });
  }
}

async function render(o, url, frameDir) {
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: "new", args: LAUNCH_ARGS,
  });

  let written = 0;
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: o.width + 40, height: 1400, deviceScaleFactor: 1 });
    page.on("pageerror", (e) => console.error("page error:", e.message));
    await page.goto(url, { waitUntil: "load", timeout: 60000 });
    await page.waitForFunction("window.__reveal && window.__reveal.ready", { timeout: 60000 });

    const dims = await page.evaluate(() => {
      const c = document.getElementById("c");
      return { w: c.width, h: c.height };
    });
    console.log(`canvas ${dims.w}x${dims.h} · mode=${o.mode} theme=${o.theme} block=${o.block}px`);

    if (o.stills > 0) {
      // contact sheet of N moments across the reveal
      for (let i = 0; i < o.stills; i++) {
        const t = (i / (o.stills - 1)) * o.dur;
        const b64 = await page.evaluate((tt) => {
          window.__reveal.reset();
          window.__reveal.frame(tt);
          return document.getElementById("c").toDataURL("image/png").split(",")[1];
        }, t);
        const f = path.join(HERE, `still_${o.mode}_${o.theme}_${String(i).padStart(2, "0")}.png`);
        fs.writeFileSync(f, Buffer.from(b64, "base64"));
        console.log(`  ${path.basename(f)}  (t=${(t / 1000).toFixed(2)}s)`);
      }
      return;
    }

    const nFrames = Math.round((o.dur / 1000) * o.fps);
    const holdFrames = Math.round(o.hold * o.fps);
    console.log(`rendering ${nFrames} frames + ${holdFrames} hold @ ${o.fps}fps`);

    await page.evaluate(() => window.__reveal.reset());
    for (let i = 0; i <= nFrames; i++) {
      const t = (i / o.fps) * 1000;
      const b64 = await page.evaluate((tt) => {
        window.__reveal.frame(tt);
        return document.getElementById("c").toDataURL("image/png").split(",")[1];
      }, t);
      fs.writeFileSync(path.join(frameDir, `f_${String(written++).padStart(5, "0")}.png`),
                       Buffer.from(b64, "base64"));
      if (i % Math.max(1, Math.round(nFrames / 10)) === 0) {
        process.stdout.write(`  ${Math.round((i / nFrames) * 100)}%\r`);
      }
    }
    // hold the finished drawing
    const lastFrame = path.join(frameDir, `f_${String(written - 1).padStart(5, "0")}.png`);
    for (let i = 0; i < holdFrames; i++) {
      fs.copyFileSync(lastFrame, path.join(frameDir, `f_${String(written++).padStart(5, "0")}.png`));
    }
    console.log(`  100% — ${written} frames`);
  } finally {
    await browser.close();
  }

  // resolve, not join — so an absolute --out lands where it was asked to,
  // rather than being pasted onto HERE and written somewhere that isn't there
  const stem = path.resolve(HERE, (o.out || `palm_reveal_${o.mode}`).replace(/\.(mp4|gif)$/, ""));
  const mp4 = `${stem}.mp4`;
  const pattern = path.join(frameDir, "f_%05d.png");
  const evenScale = "scale=trunc(iw/2)*2:trunc(ih/2)*2";

  console.log("encoding mp4...");
  await run("ffmpeg", [
    "-y", "-loglevel", "error", "-framerate", String(o.fps), "-i", pattern,
    "-vf", `${evenScale},format=yuv420p`,
    "-c:v", "libx264", "-preset", "slow", "-crf", "17",
    "-movflags", "+faststart", mp4,
  ]);
  console.log(`  ${path.basename(mp4)}  (${(fs.statSync(mp4).size / 1048576).toFixed(1)} MB)`);

  if (o.gif) {
    console.log("encoding gif...");
    const palette = path.join(frameDir, "palette.png");
    const gifFps = Math.min(o.fps, 25);
    const gifScale = "scale=640:-1:flags=lanczos";
    await run("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(o.fps), "-i", pattern,
      "-vf", `fps=${gifFps},${gifScale},palettegen=stats_mode=diff`, palette]);
    const gif = `${stem}.gif`;
    await run("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(o.fps), "-i", pattern,
      "-i", palette, "-lavfi", `fps=${gifFps},${gifScale}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3`,
      gif]);
    console.log(`  ${path.basename(gif)}  (${(fs.statSync(gif).size / 1048576).toFixed(1)} MB)`);
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
