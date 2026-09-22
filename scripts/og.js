/* 生成社交分享图 docs/assets/og.jpg。
   index.html 的 og:image 一直指向 docs/assets/og.png，但仓库里从来没有这个文件
   —— 分享出去是空白卡。尺寸对齐 meta 里声明的 1600x838。
   出 JPEG 不出 PNG：同样画面 PNG 961KB，JPEG q88 只要 ~200KB，分享卡加载快得多。
   用法：node scripts/og.js [baseUrl] [outPath] */
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright-core');

const BASE = process.argv[2] || 'http://localhost:8231/';
const OUT = process.argv[3] || path.join(__dirname, '..', 'docs', 'assets', 'og.jpg');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const W = 1600, H = 838;
const JPEG = /\.jpe?g$/i.test(OUT);

(async () => {
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  await page.goto(BASE, { waitUntil: 'load', timeout: 45000 });
  await page.waitForFunction(() => document.body.classList.contains('is-loaded'), { timeout: 20000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(2200);   // 等桥的形态稳定 + 自定义光标不要入镜

  // 分享图不要光标、不要阅读进度条、不要侧边索引、不要 SCROLL 提示
  // —— 这些是页面 UI 部件，进了分享卡只会显得杂乱
  await page.addStyleTag({
    content: '.cursor,.scroll-progress,.side-index,.hero-scroll,.file-note{display:none !important}',
  });
  await page.waitForTimeout(300);

  await page.screenshot({
    path: OUT,
    clip: { x: 0, y: 0, width: W, height: H },
    ...(JPEG ? { type: 'jpeg', quality: 88 } : {}),
  });
  const kb = (fs.statSync(OUT).size / 1024).toFixed(0);
  console.log(`分享图已生成 ${OUT}  ${W}x${H}  ${kb} KB`);
  await browser.close();
})().catch((e) => { console.error('FAILED:', e); process.exit(1); });
