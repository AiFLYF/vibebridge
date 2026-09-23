/* 单点压字诊断：滚到指定位置，报出最脏的几块文字 + 存一张截图。
   ── 为什么不能只看 collide.js 的总分 ──
   全站扫描只给「最深遮盖」和坐标，看不到现场。而粒子有 morph 惯性
   （damp(progC, progT, 4.5, dt)），直接跳到某位置和「一路滚过来」的
   形态是不同的 —— 所以这里支持 --pre 预热序列，复现扫描时的真实状态。

   用法：
     node tools/probe-collide.js <w> <h> <y> [preStep]
     例：node tools/probe-collide.js 1280 800 640        # 预热步长默认 = h*0.2
   输出：该位置最脏的 6 个文字块 + _diag/<w>x<h>_y<y>.png */
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright-core');

const W = parseInt(process.argv[2] || '1280', 10);
const H = parseInt(process.argv[3] || '800', 10);
const Y = parseInt(process.argv[4] || '640', 10);
const PRE = parseInt(process.argv[5] || String(Math.round(H * 0.2)), 10);
const BASE = 'http://127.0.0.1:8231/';
const OUT = path.join(process.cwd(), '_diag');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

/* 测量方式：藏正文，而不是藏粒子（详见 collide.js 的说明）。
   藏 #gl 会让正文重新栅格化，字形边缘的差被算成压字（虚报 30–34/255）。
   改成藏正文，只量粒子在纸底上压暗了多少 —— 没有字形就没有栅格化问题。 */
const HIDE_TEXT = () => {
  if (document.getElementById('__cg_text__')) return;
  const s = document.createElement('style');
  s.id = '__cg_text__';
  s.textContent = 'main,header,footer,.site-nav,.grain,.cursor,.scroll-progress,.side-index{visibility:hidden !important}';
  document.head.appendChild(s);
};
const SHOW_TEXT = () => { const s = document.getElementById('__cg_text__'); if (s) s.remove(); };

const HIDE_GL = () => {
  if (document.getElementById('__cg_gl__')) return;
  const s = document.createElement('style');
  s.id = '__cg_gl__'; s.textContent = '#gl{visibility:hidden !important}';
  document.head.appendChild(s);
};
const SHOW_GL = () => { const s = document.getElementById('__cg_gl__'); if (s) s.remove(); };

/* 等滚动停稳：app.js 的平滑滚动器会让页面在 scrollTo 之后自己再动约 600ms，
   而本指标是两张截图的差 —— 页面在动就会被算成"粒子压字"（实测虚报 100 倍）。 */
const waitSettled = async (page, target, maxMs = 4000) => {
  const t0 = Date.now();
  let last = -1, stable = 0;
  while (Date.now() - t0 < maxMs) {
    const y = await page.evaluate(() => Math.round(window.scrollY));
    if (y === last && Math.abs(y - target) <= 1) { if (++stable >= 3) return y; }
    else stable = 0;
    last = y;
    await page.waitForTimeout(60);
  }
  return last;
};

/* 等整页静止：hero 入场动画也会让巨型标题虚报压字 */
const waitPageStill = async (page, maxMs = 6000) => {
  const t0 = Date.now();
  let last = '', stable = 0;
  while (Date.now() - t0 < maxMs) {
    const sig = await page.evaluate(() => {
      const t = document.querySelector('.hero-title');
      const r = t ? t.getBoundingClientRect() : { top: 0, left: 0, height: 0 };
      return `${Math.round(window.scrollY)}|${r.top.toFixed(1)}|${r.left.toFixed(1)}|${r.height.toFixed(1)}`;
    });
    if (sig === last) { if (++stable >= 3) return true; } else stable = 0;
    last = sig;
    await page.waitForTimeout(80);
  }
  return false;
};

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
      out.push({
        x: r.left, y: r.top, w: r.width, h: r.height,
        t: n.textContent.trim().slice(0, 30),
        tag: p.tagName.toLowerCase() + (typeof p.className === 'string' && p.className ? '.' + p.className.trim().split(/\s+/)[0] : ''),
        fs: parseFloat(cs.fontSize),
      });
    }
  }
  return out;
};

const DIFF = async ({ aB64, bB64, rects }) => {
  const load = (b64) => new Promise((res, rej) => {
    const im = new Image(); im.onload = () => res(im); im.onerror = rej;
    im.src = 'data:image/png;base64,' + b64;
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
  const TOL = 12;
  return rects.map((r) => {
    const x0 = Math.max(0, Math.floor(r.x * sx)), x1 = Math.min(cw - 1, Math.ceil((r.x + r.w) * sx));
    const y0 = Math.max(0, Math.floor(r.y * sy)), y1 = Math.min(chh - 1, Math.ceil((r.y + r.h) * sy));
    // 用 OFF 帧的中位数当底色参考；双侧容差外的算字形像素，排除（躲开栅格化差）。
    // 中位数而非 90 分位：纸白主题取高分位抗"字形拉低"，暗底主题字形比底色亮，
    // 高分位会把亮字本身当底色参考。
    const vals = [];
    for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
      const i = (y * cw + x) * 4;
      vals.push((B[i] + B[i + 1] + B[i + 2]) / 3);
    }
    if (!vals.length) return { ...r, drop: 0 };
    vals.sort((p, q) => p - q);
    const bg = vals[Math.floor(vals.length * 0.5)];

    // 底色掩码再向字形方向腐蚀 2px：字形抗锯齿边缘会经过底色值，
    // 栅格化一变就被算成压暗（详见 collide.js 的口径说明）
    const EDGE = 2;
    const bw = x1 - x0 + 1, bh = y1 - y0 + 1;
    const isBg = new Uint8Array(bw * bh);
    for (let y = 0; y < bh; y++) for (let x = 0; x < bw; x++) {
      const i = ((y0 + y) * cw + (x0 + x)) * 4;
      isBg[y * bw + x] = Math.abs(((B[i] + B[i + 1] + B[i + 2]) / 3) - bg) <= TOL ? 1 : 0;
    }
    let sum = 0, cnt = 0;
    for (let y = 0; y < bh; y++) for (let x = 0; x < bw; x++) {
      if (!isBg[y * bw + x]) continue;
      let clean = true;
      for (let dy = -EDGE; dy <= EDGE && clean; dy++) {
        for (let dx = -EDGE; dx <= EDGE; dx++) {
          const ny = y + dy, nx = x + dx;
          if (ny < 0 || nx < 0 || ny >= bh || nx >= bw || !isBg[ny * bw + nx]) { clean = false; break; }
        }
      }
      if (!clean) continue;
      const i = ((y0 + y) * cw + (x0 + x)) * 4;
      const vb = (B[i] + B[i + 1] + B[i + 2]) / 3;
      const va = (A[i] + A[i + 1] + A[i + 2]) / 3;
      sum += Math.abs(va - vb); cnt++;   // 绝对差：暗底发光粒子是"点亮"，方向无关
    }
    return { ...r, drop: cnt ? sum / cnt : 0 };
  });
};

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  await page.goto(BASE, { waitUntil: 'load' });
  await page.waitForFunction(() => document.body.classList.contains('is-loaded'), { timeout: 20000 });
  await waitPageStill(page);

  // 预热：从 0 按 PRE 步长滚到 Y，让 morph 惯性进入和全站扫描一致的状态
  for (let y = 0; y < Y; y += PRE) {
    await page.evaluate((v) => window.scrollTo(0, v), y);
    await waitSettled(page, y);
  }
  await page.evaluate((v) => window.scrollTo(0, v), Y);
  await waitSettled(page, Y);
  // 滚动停了还不够：形态 morph 的残余会虚报（见 collide.js 的说明）
  await page.waitForTimeout(parseInt(process.env.COLLIDE_SETTLE || '1000', 10));
  await waitPageStill(page);

  const rects = await page.evaluate(COLLECT);
  const on = await page.screenshot();           // 粒子开（正文照常渲染）
  await page.evaluate(HIDE_GL);
  await page.waitForTimeout(110);
  const off = await page.screenshot();          // 粒子关
  await page.evaluate(SHOW_GL);

  const got = await page.evaluate(DIFF, { aB64: on.toString('base64'), bB64: off.toString('base64'), rects });
  got.sort((a, b) => b.drop - a.drop);

  const shot = path.join(OUT, `${W}x${H}_y${Y}.png`);
  fs.writeFileSync(shot, on);
  console.log(`\n${W}x${H} @y=${Y}  共 ${got.length} 个文字块`);
  console.log('最脏的 6 块：');
  for (const g of got.slice(0, 6)) {
    console.log(`  ${g.drop.toFixed(1).padStart(6)}/255  (x${g.x.toFixed(0)},y${g.y.toFixed(0)} ${g.w.toFixed(0)}x${g.h.toFixed(0)})  ${String(g.fs).padStart(6)}px  ${g.tag.padEnd(22)} 「${g.t}」`);
  }
  console.log(`截图：${shot}`);
  await browser.close();
})().catch((e) => { console.error('FAILED:', e); process.exit(1); });
