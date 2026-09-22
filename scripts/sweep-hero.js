/* 多视口 hero 压字扫描：一次开浏览器，把一组常见视口全扫一遍。
   ── 为什么单独做 ──
   collide.js 一次只测一个视口，逐个跑要反复启停浏览器（还会被信号打断）。
   而「视口高度」正是 hero 最容易翻车的变量 —— 1600×900 干净、
   1600×720 却压到 48/255。这种问题只有成组扫才看得出来。
   这里只扫 hero 那几屏（问题都出在这里），所以比全页扫描快得多。

   用法：node scripts/sweep-hero.js [baseUrl] [warnDrop] [viewports]
     viewports 可选，形如 "1280x800,1600x860"；不传则跑下面的默认全集。
     单独跑某个视口是为了隔离变量 —— 排查「扫描报 A、单点报 B」这类不一致时用得上。 */
const { chromium } = require('playwright-core');
const path = require('path');
const fs = require('fs');

const BASE = process.argv[2] || 'http://127.0.0.1:8231/';
const WARN = parseFloat(process.argv[3] || '25');
const SAVE_SHOTS = process.env.SWEEP_SHOTS === '1';
const SETTLE_MS = parseInt(process.env.SWEEP_SETTLE || '1000', 10);
const SHOT_DIR = path.join(process.cwd(), '_diag');
if (SAVE_SHOTS) fs.mkdirSync(SHOT_DIR, { recursive: true });
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

// 常见桌面/笔记本 + 移动端；横屏手机 844×390 也要在列。
// 两端各留一个极端值（超宽屏 / 极窄屏）—— 版式最容易在两端翻车。
const DEFAULT_SIZES = [
  [2560, 1440], [1920, 1080], [1600, 900], [1600, 860], [1600, 800], [1600, 768], [1600, 720], [1600, 660],
  [1440, 900], [1440, 800], [1440, 720],
  [1366, 768], [1280, 800], [1280, 720], [1262, 624],
  [1024, 768], [390, 844], [844, 390], [320, 568],
];
const SIZES = process.argv[4]
  ? process.argv[4].split(',').map((s) => s.trim().split('x').map(Number))
  : DEFAULT_SIZES;

/* 关粒子的正确姿势。
   ── 为什么不能用 page.addStyleTag + [...styles].pop().remove() ──
   那个写法不可靠，实测会让「关」的那一帧字形渲染变粗（ON/OFF 裁到 6 倍一比就看得出
   笔画粗细不同），于是这个差被算成"粒子压字" —— 1280×800 虚报 25–28/255，
   而同一位置用干净切换测只有 0.8。虚报值恰好与文字边缘密度成正比（粗体大字最高），
   这就是栅格化差而不是粒子覆盖的指纹。
   ── 为什么用 visibility 而不是 display ──
   #gl 是 position:fixed 的合成层。display:none 会把它从合成树里摘掉，
   底下正文的抗锯齿方式可能随之改变。visibility:hidden 保留合成层，只藏像素。
   实测：两种写法在「干净切换」下都≈0，但 visibility 更保险。 */
const HIDE_GL = () => {
  if (document.getElementById('__cg_hide__')) return;
  const s = document.createElement('style');
  s.id = '__cg_hide__';
  s.textContent = '#gl{visibility:hidden !important}';
  document.head.appendChild(s);
};
const SHOW_GL = () => { const s = document.getElementById('__cg_hide__'); if (s) s.remove(); };

/* 等滚动真正静止，而不是靠固定 sleep 猜。
   ── 为什么必须这样 ──
   app.js 里有自定义平滑滚动器：SmoothScroll.update() 每帧
   `this.c = damp(this.c, this.t, 7.5, dt)` 然后 `window.scrollTo(0, this.c)`。
   也就是说程序化 scrollTo 之后，页面还会**自己继续动约 600ms**。
   而 collide 的指标是「两张截图的差」—— 只要这两张之间页面动了哪怕几 px，
   位移差就会被算成"粒子压字"。
   实测 1280×800 @y=640：300ms 时 scrollY=627（还在动）读数 29.2/255；
   600ms 起 scrollY=640（停住）读数 0.2/255。差了 100 倍，全是假的。
   固定 900ms 也不保险 —— 预热阶段的截图会拖慢动画循环，导致 900ms 时仍未收敛。
   所以：轮询 scrollY，连续 3 次等于目标值且不变，才认为停稳。 */
const waitSettled = async (page, target, maxMs = 4000) => {
  const t0 = Date.now();
  let last = -1, stable = 0;
  while (Date.now() - t0 < maxMs) {
    const y = await page.evaluate(() => Math.round(window.scrollY));
    if (y === last && Math.abs(y - target) <= 1) {
      if (++stable >= 3) return y;
    } else stable = 0;
    last = y;
    await page.waitForTimeout(60);
  }
  return last;
};

/* 等整页静止：滚动停了还不够，hero 的入场动画（.line > span 的 translateY 1.15s）
   也在动。y=0 时滚动本来就停着，如果不等入场动画播完就测，
   巨大的标题「一座桥」正在移动，位移差会被算成压字（实测虚报 30–49/255）。
   这里轮询「滚动位置 + 标题盒子」的组合签名，连续 3 次不变才算静止。 */
const waitPageStill = async (page, target, maxMs = 6000) => {
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
        t: n.textContent.trim().slice(0, 24),
        tag: p.tagName.toLowerCase() + (typeof p.className === 'string' && p.className ? '.' + p.className.trim().split(/\s+/)[0] : ''),
        fs: parseFloat(cs.fontSize),
      });
    }
  }
  return out;
};

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
  const A = mk(ia), B = mk(ib);
  const cw = ia.width, chh = ia.height;
  const sx = cw / innerWidth, sy = chh / innerHeight;
  const TOL = 12;
  return rects.map((r) => {
    const x0 = Math.max(0, Math.floor(r.x * sx)), x1 = Math.min(cw - 1, Math.ceil((r.x + r.w) * sx));
    const y0 = Math.max(0, Math.floor(r.y * sy)), y1 = Math.min(chh - 1, Math.ceil((r.y + r.h) * sy));
    // 只统计底色像素，并向字形方向腐蚀 2px —— 详见 collide.js 的"口径三次迭代"。
    // 全框平均会被字形栅格化差污染（切换 #gl 会让正文重新栅格化），虚报 30+。
    // 底色参考取 OFF 帧中位数 + 双侧容差：纸白主题字形比底色暗，暗底主题字形比底色亮。
    const vals = [];
    for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
      const i = (y * cw + x) * 4;
      vals.push((B[i] + B[i + 1] + B[i + 2]) / 3);
    }
    if (!vals.length) return { ...r, drop: 0 };
    vals.sort((p, q) => p - q);
    const bg = vals[Math.floor(vals.length * 0.5)];
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
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const results = [];
  for (const [W, H] of SIZES) {
    const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
    await page.goto(BASE, { waitUntil: 'load', timeout: 45000 });
    await page.waitForFunction(() => document.body.classList.contains('is-loaded'), { timeout: 20000 });
    await waitPageStill(page, 0);          // 等 hero 入场动画播完再开始

    let worst = 0, worstAt = 0, worstText = '', worstFs = 0, hits = 0, blocks = 0;
    let worstOn = null, worstOff = null;
    // hero 只占首屏；扫到 1.5 屏高就够，覆盖首屏和刚滚出去时的过渡
    for (const y of [0, H * 0.2, H * 0.4, H * 0.6, H * 0.8, H * 1.0, H * 1.3]) {
      const target = Math.round(y);
      await page.evaluate((v) => window.scrollTo(0, v), target);
      const got0 = await waitSettled(page, target);
      if (Math.abs(got0 - target) > 2) continue;   // 没停稳就跳过，别拿脏数据下结论
      /* 滚动停了还不够：粒子形态的 morph 是 `progC = damp(progC, progT, 4.5, dt)`，
         7.5 的滚动阻尼收敛后，形态还有几 % 没走完 —— 那点残余正好是"形态从正文上扫过"
         的瞬间，会被量成压字。实测 1920×1080 @y=864：只等滚动停稳读数 67.7/255，
         多静置 1s 后降到 24/255（和单点诊断一致）。 */
      await page.waitForTimeout(SETTLE_MS);
      await waitPageStill(page, target);           // 再等整页（含入场动画）静止
      const on = await page.screenshot();
      await page.evaluate(HIDE_GL);
      await page.waitForTimeout(80);
      const rects = await page.evaluate(COLLECT);
      const off = await page.screenshot();
      await page.evaluate(SHOW_GL);
      await page.waitForTimeout(80);
      if (!rects.length) continue;
      blocks += rects.length;
      const got = await page.evaluate(DIFF, { aB64: on.toString('base64'), bB64: off.toString('base64'), rects });
      const top = got.reduce((a, b) => (b.drop > a.drop ? b : a), got[0]);
      if (top.drop > worst) {
        worst = top.drop; worstAt = Math.round(y); worstText = top.t; worstFs = top.fs;
        worstOn = on; worstOff = off;
      }
      for (const g of got) if (g.drop >= WARN) hits++;
    }
    // 存最脏那一屏的 on/off 两张原图 —— 数字说"脏"但看不出脏在哪时，
    // 必须能对比这两张，否则无法判断是粒子造成的还是测量本身的问题
    if (worstOn && SAVE_SHOTS) {
      fs.writeFileSync(path.join(SHOT_DIR, `worst_${W}x${H}_y${worstAt}_ON.png`), worstOn);
      fs.writeFileSync(path.join(SHOT_DIR, `worst_${W}x${H}_y${worstAt}_OFF.png`), worstOff);
    }
    results.push({ vp: `${W}x${H}`, worst, worstAt, worstText, worstFs, hits, blocks });
    const flag = worst >= WARN ? '✗' : worst >= 15 ? '△' : '✓';
    console.log(
      `${flag} ${(`${W}x${H}`).padEnd(10)} 最深 ${worst.toFixed(1).padStart(6)}/255  @y=${String(worstAt).padStart(5)}` +
      `  超标 ${String(hits).padStart(3)} 处  ${worstFs ? worstFs + 'px' : ''}  「${worstText}」`
    );
    await page.close();
  }
  const bad = results.filter((r) => r.worst >= WARN);
  console.log(`\n${bad.length === 0 ? '✓ 全部视口通过' : `✗ ${bad.length}/${results.length} 个视口超标`}（阈值 ${WARN}）`);
  console.log('✓ <15 干净 · △ 15–25 薄雾 · ✗ ≥25 要修');
  await browser.close();
})().catch((e) => { console.error('FAILED:', e); process.exit(1); });
