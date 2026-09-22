/* 读数随时间的变化：到达某滚动位置后，隔多久测才稳定？
   动机：同一位置（1280×800 @y=640），扫描等 900ms 测出 28/255，
   自检等约 1200ms 测出 0.8/255。怀疑 morph 惯性没收敛。
   用法：node scripts/settle-test.js [w] [h] [y] */
const { chromium } = require('playwright-core');

const W = parseInt(process.argv[2] || '1280', 10);
const H = parseInt(process.argv[3] || '800', 10);
const Y = parseInt(process.argv[4] || '640', 10);
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

const HIDE_GL = () => {
  if (document.getElementById('__cg_hide__')) return;
  const s = document.createElement('style');
  s.id = '__cg_hide__'; s.textContent = '#gl{visibility:hidden !important}';
  document.head.appendChild(s);
};
const SHOW_GL = () => { const s = document.getElementById('__cg_hide__'); if (s) s.remove(); };

const COLLECT = () => {
  const out = [];
  const walk = document.createTreeWalker(document.querySelector('main'), NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walk.nextNode())) {
    if (!n.textContent.trim()) continue;
    const p = n.parentElement;
    if (!p || p.closest('.marquee')) continue;
    const cs = getComputedStyle(p);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const rg = document.createRange(); rg.selectNodeContents(n);
    for (const r of rg.getClientRects()) {
      if (r.width < 8 || r.height < 6) continue;
      if (r.bottom < 0 || r.top > innerHeight) continue;
      out.push({ x: r.left, y: r.top, w: r.width, h: r.height,
        t: n.textContent.trim().slice(0, 22), fs: parseFloat(cs.fontSize) });
    }
  }
  return out;
};

const DIFF = async ({ aB64, bB64, rects }) => {
  const load = (b) => new Promise((res, rej) => {
    const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = 'data:image/png;base64,' + b;
  });
  const [ia, ib] = await Promise.all([load(aB64), load(bB64)]);
  const mk = (im) => {
    const c = document.createElement('canvas');
    c.width = im.width; c.height = im.height;
    const x = c.getContext('2d', { willReadFrequently: true });
    x.drawImage(im, 0, 0);
    return x.getImageData(0, 0, c.width, c.height).data;
  };
  const A = mk(ia), B = mk(ib);
  const cw = ia.width, chh = ia.height;
  const sx = cw / innerWidth, sy = chh / innerHeight;
  return rects.map((r) => {
    const x0 = Math.max(0, Math.floor(r.x * sx)), x1 = Math.min(cw - 1, Math.ceil((r.x + r.w) * sx));
    const y0 = Math.max(0, Math.floor(r.y * sy)), y1 = Math.min(chh - 1, Math.ceil((r.y + r.h) * sy));
    let sum = 0, cnt = 0;
    for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
      const i = (y * cw + x) * 4;
      sum += Math.max(0, (B[i] + B[i + 1] + B[i + 2]) / 3 - (A[i] + A[i + 1] + A[i + 2]) / 3);
      cnt++;
    }
    return { ...r, drop: cnt ? sum / cnt : 0 };
  });
};

(async () => {
  const b = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await b.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  await page.goto('http://127.0.0.1:8231/', { waitUntil: 'load' });
  await page.waitForFunction(() => document.body.classList.contains('is-loaded'), { timeout: 20000 });
  for (const y of [0, H * 0.2, H * 0.4, H * 0.6]) {
    await page.evaluate((v) => window.scrollTo(0, v), Math.round(y));
    await page.waitForTimeout(900);
  }
  await page.evaluate((v) => window.scrollTo(0, v), Y);

  console.log(`\n${W}x${H} 滚到 y=${Y} 后，读数随等待时长变化：\n`);
  console.log('  等待    最深    平均   scrollY   progC');
  console.log('─'.repeat(52));
  const t0 = Date.now();
  for (const wait of [300, 600, 900, 1200, 1600, 2200, 3000, 4000]) {
    while (Date.now() - t0 < wait) await page.waitForTimeout(40);
    const st = await page.evaluate(() => ({
      sy: Math.round(window.scrollY),
      prog: window.__progC !== undefined ? window.__progC : null,
    }));
    const on = await page.screenshot();
    await page.evaluate(HIDE_GL); await page.waitForTimeout(70);
    const rects = await page.evaluate(COLLECT);
    const off = await page.screenshot();
    await page.evaluate(SHOW_GL); await page.waitForTimeout(70);
    const got = await page.evaluate(DIFF, { aB64: on.toString('base64'), bB64: off.toString('base64'), rects });
    got.sort((x, y) => y.drop - x.drop);
    const avg = got.reduce((s, g) => s + g.drop, 0) / got.length;
    console.log(`  ${String(wait + 'ms').padStart(6)} ${got[0].drop.toFixed(1).padStart(7)} ${avg.toFixed(2).padStart(7)}   ${String(st.sy).padStart(6)}   ${st.prog === null ? '—' : st.prog}`);
  }
  await b.close();
})().catch((e) => { console.error('FAILED:', e); process.exit(1); });
