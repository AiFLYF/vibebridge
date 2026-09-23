/* 本地验收：截图 + 溢出/越界/console 检测。
   用法：node tools/shoot.js [baseUrl] [outDir] [width] [height] */
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright-core');

const BASE = process.argv[2] || 'http://localhost:8231/';
const OUT = process.argv[3] || '_shots';
const W = parseInt(process.argv[4] || '1600', 10);
const H = parseInt(process.argv[5] || '900', 10);
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

const SECTIONS = ['s0', 's1', 's2', 's3', 's4', 's5', 's6'];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({
    viewport: { width: W, height: H },
    deviceScaleFactor: 1,
  });

  const logs = [];
  const errors = [];
  page.on('console', (m) => {
    if (m.type() === 'error' || m.type() === 'warning') logs.push(`[${m.type()}] ${m.text()}`);
  });
  page.on('pageerror', (e) => errors.push(String(e)));

  const t0 = Date.now();
  await page.goto(BASE, { waitUntil: 'load', timeout: 45000 });
  await page.waitForFunction(() => document.body.classList.contains('is-loaded'), { timeout: 20000 });
  console.log(`loaded in ${Date.now() - t0}ms`);

  // ── 静态检测 ──────────────────────────────────────────────
  const diag = await page.evaluate(() => {
    const de = document.documentElement;
    const overflow = de.scrollWidth - de.clientWidth;

    // 横向溢出元素
    const wide = [];
    document.querySelectorAll('body *').forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width === 0) return;
      if (r.right > de.clientWidth + 1 || r.left < -1) {
        // marquee 轨道本身就是无限长的，装饰层也允许出血
        if (el.closest('.marquee, .grain, .vignette, .cursor')) return;
        const cls = el.className && typeof el.className === 'string' ? el.className.split(' ')[0] : '';
        if (/grain|gl|vignette|cursor|file-note/.test(cls)) return;
        // 故意可横向滚动的代码块（.tree-pre 保持 pre 不折，折了框线会错位）不算 bug
        const pre = el.closest('pre');
        if (pre && getComputedStyle(pre).overflowX === 'auto' && getComputedStyle(pre).whiteSpace === 'pre') return;
        wide.push(`${el.tagName.toLowerCase()}.${cls} L${Math.round(r.left)} R${Math.round(r.right)}`);
      }
    });

    // grid/flex 容器里混裸文本（窄屏"一字一行"的元凶）
    const bare = [];
    document.querySelectorAll('*').forEach((el) => {
      const d = getComputedStyle(el).display;
      if (!/^(grid|inline-grid)$/.test(d)) return;
      const texts = [...el.childNodes]
        .filter((n) => n.nodeType === 3 && n.textContent.trim())
        .map((n) => n.textContent.trim().slice(0, 24));
      if (texts.length) bare.push(`${el.tagName.toLowerCase()}.${el.className} :: ${texts.join(' | ')}`);
    });

    // 被挤成竖排的元素
    const squished = [];
    document.querySelectorAll('body *').forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.width < 60 && r.height > 60 && el.textContent.trim().length > 4) {
        squished.push(`${el.tagName.toLowerCase()}.${el.className} ${Math.round(r.width)}x${Math.round(r.height)}`);
      }
    });

    return {
      overflow, wide: wide.slice(0, 12), bare: bare.slice(0, 12), squished: squished.slice(0, 12),
      docH: de.scrollHeight, vh: innerHeight,
      acc: getComputedStyle(de).getPropertyValue('--acc').trim(),
      canvas: !!document.querySelector('canvas#gl'),
    };
  });

  console.log('\n── 静态检测 ──');
  console.log('  横向溢出 px :', diag.overflow, diag.overflow === 0 ? 'OK' : '← 要修');
  console.log('  文档高度    :', diag.docH, `(≈${(diag.docH / diag.vh).toFixed(1)} 屏)`);
  console.log('  --acc       :', diag.acc);
  console.log('  越界元素    :', diag.wide.length ? diag.wide : 'OK');
  console.log('  grid 裸文本 :', diag.bare.length ? diag.bare : 'OK');
  console.log('  竖排挤压    :', diag.squished.length ? diag.squished : 'OK');

  // ── 逐屏截图 ──────────────────────────────────────────────
  const tops = await page.evaluate((ids) => ids.map((id) => document.getElementById(id).offsetTop), SECTIONS);
  for (let i = 0; i < SECTIONS.length; i++) {
    await page.evaluate((y) => window.scrollTo(0, y), tops[i]);
    await page.waitForTimeout(1500);            // 等惯性滚动收敛 + 形态变形
    await page.screenshot({ path: path.join(OUT, `${SECTIONS[i]}.png`) });
  }
  // 首屏另存一份（形态已稳定）
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(1600);
  await page.screenshot({ path: path.join(OUT, 'hero.png') });

  // 章末形态（滚动到底）
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await page.waitForTimeout(1600);
  await page.screenshot({ path: path.join(OUT, 'end.png') });

  // 采样三章强调色
  const accs = [];
  for (const i of [0, 2, 4]) {
    await page.evaluate((y) => window.scrollTo(0, y), tops[i] + 10);
    await page.waitForTimeout(1400);
    accs.push(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--acc').trim()));
  }
  console.log('  章节换色    :', accs.join(' → '));

  console.log('\n── console ──');
  console.log(errors.length ? `  pageerror: ${errors.join('\n  ')}` : '  pageerror: 无');
  console.log(logs.length ? `  ${logs.join('\n  ')}` : '  console: 干净');

  await browser.close();
})().catch((e) => { console.error('FAILED:', e); process.exit(1); });
