/* 指标自检：collide 的「关粒子」方式本身会不会污染读数？
   ── 怀疑 ──
   collide 用 `#gl{display:none}` 关粒子。但 #gl 是 position:fixed 的合成层，
   盖在正文上时 Chrome 对正文用灰度抗锯齿，拿掉合成层后可能切成次像素抗锯齿 ——
   字形边缘的像素值就变了，这个差会被算成"粒子压字"。
   症状：读数与文字的边缘密度成正比（粗体大字最高、小字最低），而不是与粒子位置相关。

   这个脚本对比四种拍法，把「真粒子差」和「栅格化差」分开：
     A. display:none 切换      → 现用口径
     B. visibility:hidden 切换 → 保留合成层，只藏像素
     C. 两张都 display:none    → 纯底噪（应≈0）
     D. 两张都可见             → 只有粒子自身漂移（应很小）
   若 A 明显大于 B，说明现用口径高估了压字。

   用法：node scripts/metric-selftest.js [w] [h] [y] */
const { chromium } = require('playwright-core');

const W = parseInt(process.argv[2] || '1280', 10);
const H = parseInt(process.argv[3] || '800', 10);
const Y = parseInt(process.argv[4] || '640', 10);
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

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
    const rg = document.createRange();
    rg.selectNodeContents(n);
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
      // |ON−OFF| 绝对差：暗色主题粒子是加色点亮，方向无关
      sum += Math.abs((A[i] + A[i + 1] + A[i + 2]) / 3 - (B[i] + B[i + 1] + B[i + 2]) / 3);
      cnt++;
    }
    return { ...r, drop: cnt ? sum / cnt : 0 };
  });
};

const HIDE = (mode) => {
  const s = document.createElement('style');
  s.id = '__probe_gl__';
  s.textContent = mode === 'none' ? '#gl{display:none !important}' : '#gl{visibility:hidden !important}';
  document.head.appendChild(s);
};
const SHOW = () => { const s = document.getElementById('__probe_gl__'); if (s) s.remove(); };

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
  await page.waitForTimeout(950);

  const rects = await page.evaluate(COLLECT);
  const measure = async (aHide, bHide, gap) => {
    await page.evaluate(SHOW); await page.waitForTimeout(120);
    if (aHide) { await page.evaluate(HIDE, aHide); await page.waitForTimeout(150); }
    const a = await page.screenshot();
    await page.waitForTimeout(gap);
    if (bHide && bHide !== aHide) { await page.evaluate(HIDE, bHide); await page.waitForTimeout(150); }
    const c = await page.screenshot();
    await page.evaluate(SHOW); await page.waitForTimeout(120);
    const got = await page.evaluate(DIFF, { aB64: a.toString('base64'), bB64: c.toString('base64'), rects });
    got.sort((x, y) => y.drop - x.drop);
    return got;
  };

  console.log(`\n${W}x${H} @y=${Y}  ${rects.length} 个文字块\n`);
  console.log('拍法                                 最深    平均   ← 只有 B/D 才是"真粒子差"');
  console.log('─'.repeat(76));

  const cases = [
    ['A. display:none 切换（现用口径）', 'none', 'none', 220],
    ['B. visibility:hidden 切换',        'vis',  'vis',  220],
    ['C. 两张都 display:none（底噪）',    'none', null,   220],
    ['D. 两张都可见（只测粒子漂移）',      null,   null,   220],
  ];
  const store = {};
  for (const [label, ah, bh, gap] of cases) {
    const got = await measure(ah, bh, gap);
    const avg = got.reduce((s, g) => s + g.drop, 0) / got.length;
    store[label[0]] = got;
    console.log(`${label.padEnd(34)} ${got[0].drop.toFixed(1).padStart(6)}  ${avg.toFixed(2).padStart(6)}`);
  }
  console.log('\n最深 3 块对比（A 现用口径 vs B 保留合成层）：');
  for (let i = 0; i < 3; i++) {
    const a = store.A[i], b = store.B[i];
    console.log(`  ${String(a.fs).padStart(6)}px  A=${a.drop.toFixed(1).padStart(5)}  B=${b.drop.toFixed(1).padStart(5)}  「${a.t}」`);
  }
  await b.close();
})().catch((e) => { console.error('FAILED:', e); process.exit(1); });
