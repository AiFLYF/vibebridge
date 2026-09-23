/* 滚动中的帧率测量：中位数 fps + p95 帧时间。
   ── 为什么要边滚边测 ──
   静止画面下 GPU 可能什么都不用做，帧率虚高。真正的负载在滚动时：
   粒子每帧要重算 morph 插值 + 上传 uniform + 重绘 72000 个点。
   ── 为什么看 p95 而不只看中位数 ──
   中位数好看但 p95 差 = 有明显的卡顿感。两个都要看。
   ── 为什么要测"关粒子"的对照 ──
   才知道帧率是粒子吃掉的还是版面本身吃掉的。
   ── 本机 headless 拿到的是真 GPU（不是软件光栅），所以这些数可以当下限信。

   用法：node tools/perf.js [baseUrl] [width] [height] [rollSteps]
         node tools/perf.js http://127.0.0.1:8231/ 1600 900
   默认会测一组视口；给 width/height 则只测那一个。 */
const { chromium } = require('playwright-core');

const BASE = process.argv[2] || 'http://127.0.0.1:8231/';
const ONLY_W = process.argv[3] ? parseInt(process.argv[3], 10) : null;
const ONLY_H = process.argv[4] ? parseInt(process.argv[4], 10) : null;
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

const SIZES = ONLY_W
  ? [[ONLY_W, ONLY_H]]
  : [[1920, 1080], [1600, 900], [1366, 768], [390, 844], [2560, 1440]];

/* 在页面里连续滚动 durationMs 毫秒，逐帧收集 rAF 间隔；同一状态跑 rounds 轮取最快的一轮。
   ── 为什么不用"滚一下停一下" ──
   停着的那些帧几乎不干活，会把中位数拉好看；而且每段滚动都有启动尖峰。
   改成在 rAF 回调里直接推进滚动位置 —— 每一帧都是新的滚动位置，
   测到的就是"一直在滚"的真实负载。
   ── 为什么要丢前 N 帧 ──
   首帧要编译 shader / 建纹理，那几帧是尖峰，不代表稳态。
   ── 为什么要跑多轮取最快 ──
   本机后台任务会抢 CPU，单轮很容易被偶发卡顿污染。
   取最快的一轮 = "这台机器能做到的水平"，可复现性最好。
   ── 为什么整个测量必须写在一个函数里 ──
   page.evaluate 只序列化传入的那一个函数，函数内部引用不到模块作用域的别的东西。 */
const BEST = async ({ durationMs, warmFrames, rounds }) => {
  const runOnce = () => new Promise((resolve) => {
    const maxY = Math.max(1, document.documentElement.scrollHeight - innerHeight);
    const times = [];
    let last = performance.now();
    let frames = 0;
    const t0 = last;
    let y = 0, dir = 1;

    const tick = () => {
      const now = performance.now();
      frames++;
      if (frames > warmFrames) times.push(now - last);
      last = now;

      // 匀速往返滚动：每帧推进量按 60fps 折算，滚动速度与实测帧率无关
      y += dir * (maxY / (durationMs / 16.7));
      if (y >= maxY) { y = maxY; dir = -1; }
      if (y <= 0) { y = 0; dir = 1; }
      window.scrollTo(0, Math.round(y));

      if (now - t0 < durationMs) requestAnimationFrame(tick);
      else resolve(times);
    };
    requestAnimationFrame(tick);
  });

  let best = null;
  for (let i = 0; i < rounds; i++) {
    const t = (await runOnce()).sort((a, b) => a - b);
    if (!t.length) continue;
    const q = (p) => t[Math.min(t.length - 1, Math.floor(t.length * p))];
    const r = { n: t.length, med: q(0.5), p95: q(0.95), fps: 1000 / q(0.5), fpsLow: 1000 / q(0.95) };
    if (!best || r.fps > best.fps) best = r;
  }
  return best || { n: 0, fps: 0, p95: 0, fpsLow: 0 };
};

const SET_GL = (hide) => {
  const old = document.getElementById('__perf__');
  if (old) old.remove();
  if (!hide) return;
  const s = document.createElement('style');
  s.id = '__perf__'; s.textContent = '#gl{visibility:hidden !important}';
  document.head.appendChild(s);
};

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });

  /* 预热：批测时第一个视口会被冷启动污染 —— 实测 1920×1080 在批测里报 27.9 fps，
     单独跑却是 57.5。先开一个丢弃页把 GPU 管线 / shader 缓存 / 字体预热掉。 */
  {
    const warm = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
    await warm.goto(BASE, { waitUntil: 'load', timeout: 60000 });
    await warm.waitForFunction(() => document.body.classList.contains('is-loaded'), { timeout: 25000 });
    await warm.evaluate(BEST, { durationMs: 1500, warmFrames: 20, rounds: 1 });
    await warm.close();
  }

  console.log('\n滚动中的帧率（中位数 / p95 帧时间 / p95 对应的 fps）');
  console.log('─'.repeat(74));
  let worstFps = Infinity, worstAt = '';

  for (const [W, H] of SIZES) {
    const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
    await page.goto(BASE, { waitUntil: 'load', timeout: 60000 });
    await page.waitForFunction(() => document.body.classList.contains('is-loaded'), { timeout: 25000 });
    await page.waitForTimeout(2500);          // 等入场动画和首屏 shader 编译过去

    // A/B 交替：有粒子 → 无粒子 → 有粒子，抵消"越测越热/越测越稳"的漂移
    await page.evaluate(SET_GL, false);
    await page.waitForTimeout(200);
    const gl1 = await page.evaluate(BEST, { durationMs: 3000, warmFrames: 30, rounds: 3 });

    await page.evaluate(SET_GL, true);
    await page.waitForTimeout(400);
    const noGL = await page.evaluate(BEST, { durationMs: 3000, warmFrames: 30, rounds: 3 });

    await page.evaluate(SET_GL, false);
    await page.waitForTimeout(400);
    const gl2 = await page.evaluate(BEST, { durationMs: 3000, warmFrames: 30, rounds: 3 });

    const withGL = gl1.fps >= gl2.fps ? gl1 : gl2;

    const flag = withGL.fps >= 50 ? '✓' : withGL.fps >= 35 ? '△' : '✗';
    const cost = noGL.fps > 0 ? (1000 / withGL.fps - 1000 / noGL.fps) : NaN;
    console.log(
      `${flag} ${(`${W}x${H}`).padEnd(10)} 有粒子 ${withGL.fps.toFixed(1).padStart(5)} fps` +
      ` (p95 ${withGL.p95.toFixed(1).padStart(5)}ms → ${withGL.fpsLow.toFixed(1).padStart(5)} fps)` +
      `   无粒子 ${noGL.fps.toFixed(1).padStart(5)} fps` +
      `   粒子开销 ${isNaN(cost) ? '—' : cost.toFixed(2) + 'ms/帧'}`
    );
    if (withGL.fps < worstFps) { worstFps = withGL.fps; worstAt = `${W}x${H}`; }
    await page.close();
  }

  console.log(`\n最差：${worstAt} → ${worstFps.toFixed(1)} fps`);
  console.log('✓ ≥50 流畅 · △ 35–50 可接受 · ✗ <35 要优化');
  await browser.close();
})().catch((e) => { console.error('FAILED:', e); process.exit(1); });
