/* 粒子压字检测：量文字被粒子盖了多少。
   ── 为什么不用 drawImage 读 GL canvas ──
   WebGL canvas 默认 preserveDrawingBuffer:false，合成后绘制缓冲就被清了，
   drawImage 读回来全是 0 —— 全站报 0.0% 那种"完美结果"其实是测量坏了。
   改成截两张图做差：粒子图层开 / 关，其余（纸底、噪点、暗角）在差里互相抵消，
   剩下的就是粒子对每块文字的实际遮盖量。用浏览器解 PNG，不需要任何图像库。

   ── 为什么是滚动扫描而不是逐章采样 ──
   逐章采样只看到每章静止时的样子，漏掉 morph 过渡态 —— 而过渡态恰恰是
   形态横穿屏幕、最容易压字的时候。这里从顶到底每 STEP 像素采一次，
   每次都把视口内所有文字块量一遍。

   ── 最大的坑：两张截图之间页面不能动 ──
   app.js 有自定义平滑滚动器，SmoothScroll.update() 每帧
   `this.c = damp(this.c, this.t, 7.5, dt)` 后重新 `window.scrollTo(0, this.c)` ——
   程序化 scrollTo 之后页面还会**自己继续动约 600ms**。
   而本指标是两张截图的差，只要这两张之间页面动了哪怕几 px，位移差就被算成"压字"。
   实测 1280×800 @y=640：300ms 时 scrollY=627（还在动）读数 29.2/255；
   600ms 起 scrollY=640（停住）读数 0.2/255 —— 差 100 倍，全是假的。
   hero 的入场动画（.line > span translateY 1.15s）同理，会让巨型标题虚报 30–49/255。
   所以：必须等「滚动停稳」+「整页盒子不再变化」才拍，不能靠固定 sleep。

   用法：node scripts/collide.js [baseUrl] [width] [height] [warnDrop] [step]
   怎么读这个数（"文字块区域的 |ON−OFF| 平均亮度差 0–255"，方向无关）：
     深空底 #0b0e13、文字 #ede8dc。粒子是加色发光，落在文字区只会把底色**点亮**；
     纸白主题时代粒子是把底色压暗。两种情况对"脏不脏"的含义一样，所以量绝对差。
     < 8     看不见，纯当底纹
     8–25    一层薄雾，底色约偏 3–10%，对比度掉不到 1 档，当氛围可以接受
     25–60   看得出有一层灰/光，小字开始发闷
     > 60    明显压字，要修
     > 150   实心压字
   注意：这个指标衡量的是"看起来脏不脏"，不是"能不能读" ——
   别拿它当可读性红线。 */
const { chromium } = require('playwright-core');
const path = require('path');
const fs = require('fs');

const BASE = process.argv[2] || 'http://localhost:8231/';
const W = parseInt(process.argv[3] || '1600', 10);
const H = parseInt(process.argv[4] || '900', 10);
const WARN = parseFloat(process.argv[5] || '25');
const STEP = parseInt(process.argv[6] || '260', 10);
// 滚动停稳后额外静置多久才拍（毫秒）。形态 morph 的残余会虚报，见下方说明。
const SETTLE_MS = parseInt(process.env.COLLIDE_SETTLE || '1000', 10);
// COLLIDE_SHOTS=1 时把最脏那一屏的 on/off 两张原图存到 _diag/
// 数字说"脏"但看不出脏在哪时，必须能对比这两张才能定案
const SAVE_SHOTS = process.env.COLLIDE_SHOTS === '1';
const SHOT_DIR = path.join(process.cwd(), '_diag');
if (SAVE_SHOTS) fs.mkdirSync(SHOT_DIR, { recursive: true });
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

/* ── 测量方式：藏正文，而不是藏粒子 ──────────────────────────
   最初的做法是「关掉粒子层，看哪些文字变亮了」。错的。
   把 #gl 藏掉会改变合成树，正文被**重新栅格化**，字形边缘的像素值就变了 ——
   这个差被算成"粒子压字"。实测把差异像素涂红，红色精确描出每一个笔画轮廓
   （粒子应该是一颗颗散点），1600×900 因此虚报 31–34/255。
   换 display / visibility / opacity 都躲不掉，因为问题在合成树本身。

   现在改成：把正文（main/nav/footer）和 grain 藏起来，只留粒子浮在纸底上。
   两张图一张有粒子一张没有，差就是纯粹的"粒子把纸底压暗了多少"。
   没有字形参与 → 不存在栅格化差异。 */
const HIDE_TEXT = () => {
  if (document.getElementById('__cg_text__')) return;
  const s = document.createElement('style');
  s.id = '__cg_text__';
  s.textContent = 'main,header,footer,.site-nav,.grain,.cursor,.scroll-progress,.side-index{visibility:hidden !important}';
  document.head.appendChild(s);
};
const SHOW_TEXT = () => { const s = document.getElementById('__cg_text__'); if (s) s.remove(); };

/* 粒子层开关：此时页面只剩纸底 + 粒子，切换不会引起任何字形重栅格化 */
const HIDE_GL = () => {
  if (document.getElementById('__cg_gl__')) return;
  const s = document.createElement('style');
  s.id = '__cg_gl__';
  s.textContent = '#gl{visibility:hidden !important}';
  document.head.appendChild(s);
};
const SHOW_GL = () => { const s = document.getElementById('__cg_gl__'); if (s) s.remove(); };

/* 等滚动真正停稳（app.js 的平滑滚动器会让页面自己再动 ~600ms） */
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

/* 视口内所有可见文字的 Range 包围盒 */
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
        t: n.textContent.trim().slice(0, 24),
        tag: p.tagName.toLowerCase() + (typeof p.className === 'string' && p.className ? '.' + p.className.trim().split(/\s+/)[0] : ''),
        fs: parseFloat(cs.fontSize),
      });
    }
  }
  return out;
};

/* ── 测量口径的三次迭代（每次都是被假数据打脸之后改的）────────
   ① 只关粒子、全框平均 → 被「字形栅格化差」污染。
      切换 #gl 会改变合成树，正文被重新栅格化，字形边缘像素值变了；
      这个差被算成压字。把差异涂红，红色精确描出每一道笔画轮廓（粒子应是散点），
      1600×900 因此虚报 31–34/255。换 display/visibility/opacity 都躲不掉。
   ② 藏正文、只留粒子 → 又过头了。main 是 z-index:10、#gl 是 1，
      粒子本来就在内容**下面**，面板的 0.88 白底会把它挡掉大半。
      藏了 main 等于把面板一起藏了，量到的是"裸纸底上的粒子密度"，
      160/255 的读数对应的实际观感只有约 24/255（面板上一团浅灰薄雾）。

   现在：两张图都**保留正文**，只切粒子；但**只统计底色像素**。
   底色像素从 OFF 帧取（分位数当底色参考，容差内的才算），字形像素全部排除 ——
   栅格化差只发生在字形边缘，排除掉就不影响；面板遮挡也如实反映在结果里。 */
const DIFF = async ({ aB64, bB64, rects }) => {
  const load = (b64) => new Promise((res, rej) => {
    const im = new Image();
    im.onload = () => res(im);
    im.onerror = rej;
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
  const A = mk(ia), B = mk(ib);          // A = 粒子开, B = 粒子关
  const cw = ia.width, chh = ia.height;
  const sx = cw / innerWidth, sy = chh / innerHeight;
  const TOL = 12;                         // 底色容差：偏离底色超过这个值就算字形像素

  return rects.map((r) => {
    const x0 = Math.max(0, Math.floor(r.x * sx)), x1 = Math.min(cw - 1, Math.ceil((r.x + r.w) * sx));
    const y0 = Math.max(0, Math.floor(r.y * sy)), y1 = Math.min(chh - 1, Math.ceil((r.y + r.h) * sy));

    // 先用 OFF 帧求这块的底色（取中位数：OFF 帧里没有粒子，底色就是多数像素；
    // 90 分位在纸白主题下抗"字形拉低"，但在暗底大字块里会把亮字本身当底色）
    const vals = [];
    for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
      const i = (y * cw + x) * 4;
      vals.push((B[i] + B[i + 1] + B[i + 2]) / 3);
    }
    if (!vals.length) return { ...r, drop: 0, bgPx: 0 };
    vals.sort((p, q) => p - q);
    const bg = vals[Math.floor(vals.length * 0.5)];

    // 底色像素 = 与底色参考值的差在 ±TOL 内（两侧都算：纸白主题字形比底色暗，
    // 暗色主题字形比底色亮，单向筛选会把亮字误当底色）。
    // 再向字形方向腐蚀 EDGE px —— 字形抗锯齿边缘本来就会经过底色值，
    // 栅格化一变（笔画粗细差 1px）这些边缘像素就被算成"粒子压暗"
    // （实测虚报 36/255，而同一位置肉眼与截图都干净）。
    // 栅格化差只发生在字形边界 ±1px 内，腐蚀 2px 就干净了。
    const EDGE = 2;
    const pad = EDGE + 1;
    const bw = x1 - x0 + 1, bh = y1 - y0 + 1;
    const isBg = new Uint8Array(bw * bh);
    for (let y = 0; y < bh; y++) for (let x = 0; x < bw; x++) {
      const i = ((y0 + y) * cw + (x0 + x)) * 4;
      const vb = (B[i] + B[i + 1] + B[i + 2]) / 3;
      isBg[y * bw + x] = Math.abs(vb - bg) <= TOL ? 1 : 0;
    }

    let sum = 0, cnt = 0;
    for (let y = 0; y < bh; y++) {
      for (let x = 0; x < bw; x++) {
        if (!isBg[y * bw + x]) continue;
        let clean = true;
        for (let dy = -EDGE; dy <= EDGE && clean; dy++) {
          for (let dx = -EDGE; dx <= EDGE; dx++) {
            const ny = y + dy, nx = x + dx;
            // 出块即视为边界：块外可能是字形，保守排除
            if (ny < 0 || nx < 0 || ny >= bh || nx >= bw || !isBg[ny * bw + nx]) { clean = false; break; }
          }
        }
        if (!clean) continue;
        const i = ((y0 + y) * cw + (x0 + x)) * 4;
        const vb = (B[i] + B[i + 1] + B[i + 2]) / 3;
        const va = (A[i] + A[i + 1] + A[i + 2]) / 3;
        // 绝对差：暗底发光粒子是"点亮"，纸白时代是"压暗"，方向无关
        sum += Math.abs(va - vb);
        cnt++;
      }
    }
    return { ...r, drop: cnt ? sum / cnt : 0, bgPx: cnt };
  });
};

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  await page.goto(BASE, { waitUntil: 'load', timeout: 45000 });
  await page.waitForFunction(() => document.body.classList.contains('is-loaded'), { timeout: 20000 });
  await waitPageStill(page);                 // 等 hero 入场动画播完

  const maxY = await page.evaluate(() => document.documentElement.scrollHeight - innerHeight);
  let worst = 0, worstAt = 0, checked = 0, blocks = 0, skipped = 0;
  let worstOn = null, worstOff = null, worstBlock = null;
  const hits = [];

  for (let y = 0; y <= maxY + 1; y += STEP) {
    const target = Math.min(Math.round(y), Math.round(maxY));
    await page.evaluate((v) => window.scrollTo(0, v), target);
    const settled = await waitSettled(page, target);
    if (Math.abs(settled - target) > 2) { skipped++; continue; }   // 没停稳 → 跳过，不拿脏数据下结论
    /* 滚动停了还不够。粒子形态的 morph 是 `progC = damp(progC, progT, 4.5, dt)`：
       7.5 的滚动阻尼收敛之后，形态还剩几 % 没走完 —— 那点残余正好是
       "形态从正文上扫过去"的瞬间，会被量成压字。
       实测 1920×1080 @y=864：只等滚动停稳读数 67.7/255；多静置 1s 后 0.5/255。
       差了 130 倍，全是假的。 */
    await page.waitForTimeout(SETTLE_MS);
    await waitPageStill(page);

    const rects = await page.evaluate(COLLECT);
    if (!rects.length) continue;                // 这一屏没文字，跳过（空检不算数）

    const on = await page.screenshot();          // 粒子开（正文照常渲染）
    await page.evaluate(HIDE_GL);
    await page.waitForTimeout(110);
    const off = await page.screenshot();         // 粒子关
    await page.evaluate(SHOW_GL);
    await page.waitForTimeout(90);

    checked++; blocks += rects.length;

    const got = await page.evaluate(DIFF, { aB64: on.toString('base64'), bB64: off.toString('base64'), rects });
    const top = got.reduce((a, b) => (b.drop > a.drop ? b : a), got[0]);
    if (top.drop > worst) {
      worst = top.drop; worstAt = target;
      worstOn = on; worstOff = off; worstBlock = top;
    }
    for (const g of got) if (g.drop >= WARN) hits.push({ y: target, ...g });
  }

  if (SAVE_SHOTS && worstOn) {
    fs.writeFileSync(path.join(SHOT_DIR, `collide_${W}x${H}_y${worstAt}_ON.png`), worstOn);
    fs.writeFileSync(path.join(SHOT_DIR, `collide_${W}x${H}_y${worstAt}_OFF.png`), worstOff);
    console.log(`\n最脏那一屏的原图已存 _diag/collide_${W}x${H}_y${worstAt}_{ON,OFF}.png` +
      `\n  被量的块：(${worstBlock.x.toFixed(0)},${worstBlock.y.toFixed(0)}) ${worstBlock.w.toFixed(0)}x${worstBlock.h.toFixed(0)}` +
      ` 「${worstBlock.t}」`);
  }

  hits.sort((a, b) => b.drop - a.drop);
  console.log(`\n扫描 ${Math.round(maxY / STEP) + 1} 个位置 · 有效 ${checked} 屏 · 累计 ${blocks} 个文字块` +
    (skipped ? ` · 跳过 ${skipped} 个未停稳位置` : ''));
  console.log(`全站最深遮盖：${worst.toFixed(1)}/255  @scrollY=${worstAt}`);
  if (hits.length) {
    console.log(`\n超过阈值 ${WARN} 的 ${hits.length} 处：`);
    for (const h of hits.slice(0, 12)) {
      console.log(`   ${h.drop.toFixed(1).padStart(6)}/255  y${String(h.y).padStart(5)}  ${String(h.fs).padStart(5)}px  ${h.tag.padEnd(20)} 「${h.t}」`);
    }
  } else {
    console.log(`✓ 没有一处超过阈值 ${WARN}`);
  }
  console.log('参考：<8 看不见 · 8–25 薄雾可接受 · 25–60 发闷 · >60 要修 · >150 实心压字');
  await browser.close();
})().catch((e) => { console.error('FAILED:', e); process.exit(1); });
