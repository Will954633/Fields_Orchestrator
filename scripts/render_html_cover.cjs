// Render the first "page" of a self-contained HTML report to a JPEG cover.
// Usage: node render_html_cover.cjs <input.html> <output.jpg>
// Clips from the top down to just above the first <button> (the download bar),
// giving a document-cover crop. Used by publish_offmarket_artifacts.py.
const puppeteer = require("puppeteer");

(async () => {
  const [, , inPath, outPath] = process.argv;
  if (!inPath || !outPath) {
    console.error("usage: node render_html_cover.cjs <input.html> <output.jpg>");
    process.exit(2);
  }
  const browser = await puppeteer.launch({
    executablePath: process.env.SITE_INSPECTOR_CHROME_PATH || "/usr/bin/google-chrome",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    defaultViewport: { width: 840, height: 1200, deviceScaleFactor: 2 },
  });
  try {
    const page = await browser.newPage();
    await page.goto("file://" + inPath, { waitUntil: "networkidle2", timeout: 30000 });
    await new Promise((r) => setTimeout(r, 500));
    const clipH = await page.evaluate(() => {
      const btn = document.querySelector("button");
      const y = btn ? btn.getBoundingClientRect().top + window.scrollY : 1120;
      return Math.min(Math.max(y - 10, 700), 1180);
    });
    await page.screenshot({
      path: outPath,
      type: "jpeg",
      quality: 82,
      clip: { x: 0, y: 0, width: 840, height: clipH },
    });
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error("ERR", e.message);
  process.exit(1);
});
