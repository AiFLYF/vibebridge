/* 对照实验：两张图都在「粒子关闭」状态下拍。
   若读数仍明显非零 → 指标被非粒子因素污染（亚像素位移、grain 动画等），
   那 collide 的高分就不能直接归因于粒子压字。
   用法：node scripts/control-noise.js [w] [h] [y] */
const { chromium } = require('playwright-core');
const W = parseInt(process.argv[2] || '1280', 10);
const H = parseInt(process.argv[3] || '800', 10);
const Y = parseInt(process.argv[4] || '640', 10);

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
        t: n.textContent.trim().slice(0, 24), tag: p.tagName.toLowerCase(), fs: parseFloat(cs.fontSize) });
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
  const b = await chromium.launch({ executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', headless: true });
  const page = await b.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  await page.goto('http://127.0.0.1:8231/', { waitUntil: 'load' });
  await page.waitForFunction(() => document.body.classList.contains('is-loaded'), { timeout: 20000 });
  for (const y of [0, H * 0.2, H * 0.4, H * 0.6]) {
    await page.evaluate((v) => window.scrollTo(0, v), Math.round(y));
    await page.waitForTimeout(900);
  }
  await page.evaluate((v) => window.scrollTo(0, v), Y);
  await page.waitForTimeout(950);

  // 先关粒子，两张图都在「关」的状态下拍 —— 理论上差应为 0
  await page.addStyleTag({ content: '#gl{display:none !important}' });
  await page.waitForTimeout(300);
  const a = await page.screenshot();
  await page.waitForTimeout(220);
  const rects = await page.evaluate(COLLECT);
  const c = await page.screenshot();

  const got = await page.evaluate(DIFF, { aB64: a.toString('base64'), bB64: c.toString('base64'), rects });
  got.sort((x, y) => y.drop - x.drop);
  const avg = got.reduce((s, g) => s + g.drop, 0) / got.length;
  console.log(`\n【对照：两张图都关粒子】${W}x${H} @y=${Y}  ${got.length} 块`);
  console.log(`  平均 ${avg.toFixed(2)}/255   最深 ${got[0].drop.toFixed(1)}/255`);
  console.log('  最深 5 块（这些数不是粒子造成的）：');
  for (const g of got.slice(0, 5)) {
    console.log(`    ${g.drop.toFixed(1).padStart(6)}/255  ${String(g.fs).padStart(6)}px  ${g.tag.padEnd(6)} 「${g.t}」`);
  }
  await b.close();
})().catch((e) => { console.error('FAILED:', e); process.exit(1); });
