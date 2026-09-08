// Render the concept pictures in images/pictures/src to light and dark PNGs.
//
//   cd scripts && npm install && node render-pictures.mjs            # all pictures
//   node render-pictures.mjs lifecycle funding                        # some of them
//
// Needs a Chromium. Set CHROME to its path if it is not found automatically.
// Edit words in images/pictures/src/build.py, run `python build.py` there, then render.
import puppeteer from 'puppeteer-core';
import { existsSync, readdirSync } from 'fs';
import path from 'path';
import { pathToFileURL } from 'url';

const src = path.resolve(import.meta.dirname, '..', 'images', 'pictures', 'src');
const out = path.resolve(import.meta.dirname, '..', 'images', 'pictures');
const candidates = [process.env.CHROME,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome', '/usr/bin/chromium'].filter(Boolean);
const chrome = candidates.find(existsSync);
if (!chrome) { console.error('No Chromium found. Set CHROME=/path/to/chrome'); process.exit(1); }

const names = process.argv.length > 2 ? process.argv.slice(2)
  : readdirSync(src).filter(f => f.endsWith('.html')).map(f => f.slice(0, -5));

const browser = await puppeteer.launch({ executablePath: chrome, headless: true, defaultViewport: { width: 1540, height: 952 } });
const page = await browser.newPage();
for (const name of names) {
  const file = pathToFileURL(path.join(src, name + '.html')).href;
  for (const theme of ['light', 'dark']) {
    await page.goto(file + (theme === 'dark' ? '?dark' : ''), { waitUntil: 'networkidle0', timeout: 60000 });
    await page.evaluate(() => document.fonts.ready);
    await new Promise(r => setTimeout(r, 300));
    await page.screenshot({ path: path.join(out, `${name}-${theme}.png`) });
    console.log(`${name}-${theme}.png`);
  }
}
await browser.close();
