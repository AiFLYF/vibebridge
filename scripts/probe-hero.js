/* 量 hero 的纵向几何：文字块底 vs 粒子桥顶，判断会不会撞。
   ── 为什么需要这个 ──
   .sec 是 flex 垂直居中，hero 内容块高度由 vw 定死（1600 宽下恒 455px），
   而粒子桥锚在世界坐标、永远占视口高度的底部 25%（桥顶在 0.745H）。
   两个基准不一致 → 视口一变矮，内容被居中往下推、桥往上顶，必然交叉。
   这个脚本把两边真实数字打出来，用来定「要收多少」。
   用法：node scripts/probe-hero.js [baseUrl] */
const { chromium } = require('playwright-core');
const BASE = process.argv[2] || 'http://127.0.0.1:8231/';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

// formBridge 里桥的粒子云纵向范围（世界坐标），配合 camera.z 投影出屏幕位置
const TOW_TOP = -1.14, DUST_BOT = -2.32, FOV = 50;
const Z0 = 5.0;      // 00 章桌面 z
const Z0M = 8.5;     // 00 章窄屏 z

const SIZES = [
  [1600, 900], [1600, 860], [1600, 800], [1600, 768], [1600, 720], [1600, 660], [1600, 600],
  [1440, 900], [1440, 800], [1440, 720],
  [1366, 768], [1280, 800], [1280, 720], [1262, 624],
  [390, 844], [844, 390],
];

(async () => {
  const b = await chromium.launch({ executablePath: CHROME, headless: true });
  console.log('视口        桥顶  桥底 | facts底 标题底 内容高 | 余量  判定');
  console.log('─'.repeat(72));
  let bad = 0;
  for (const [W, H] of SIZES) {
    const p = await b.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
    await p.goto(BASE, { waitUntil: 'load' });
    await p.waitForTimeout(1300);
    const r = await p.evaluate(({ TOW_TOP, DUST_BOT, FOV, Z0, Z0M, H, W }) => {
      const box = (s) => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); return { top: b.top, bottom: b.bottom }; };
      // 窄屏判定要和 app.js 的 isNarrow() 一致
      const narrow = W < 760 && H > W;
      const z = narrow ? Z0M : Z0;
      const oy = narrow ? -1.62 : 0;   // 00 章窄屏把桥整体下移
      const halfH = Math.tan((FOV * Math.PI) / 360) * z;
      const toScreen = (wy) => (1 - (wy + oy + halfH) / (2 * halfH)) * H;
      const eyebrow = box('.eyebrow'), facts = box('.hero-facts'), title = box('.hero-title');
      return {
        factsBottom: facts ? facts.bottom : null,
        titleBottom: title ? title.bottom : null,
        contentH: eyebrow && facts ? facts.bottom - eyebrow.top : null,
        bridgeTop: toScreen(TOW_TOP), bridgeBot: toScreen(DUST_BOT),
      };
    }, { TOW_TOP, DUST_BOT, FOV, Z0, Z0M, H, W });

    // 余量 = facts 底 到 桥顶 的距离。桥塔顶部粒子稀疏，贴边可接受；
    // 真正判据是 collide.js 的 25 阈值，这里只要别让 facts 落进桥的主体。
    const margin = r.factsBottom - r.bridgeTop;
    const ok = margin <= -30 ? 'OK' : margin <= 0 ? '贴边' : '✗ 撞上';
    if (margin > 0) bad++;
    console.log(
      `${(W + 'x' + H).padEnd(11)} ${r.bridgeTop.toFixed(0).padStart(5)} ${r.bridgeBot.toFixed(0).padStart(5)} |` +
      `${r.factsBottom.toFixed(0).padStart(7)} ${r.titleBottom.toFixed(0).padStart(7)} ${r.contentH.toFixed(0).padStart(6)} |` +
      `${margin.toFixed(0).padStart(6)}  ${ok}`
    );
    await p.close();
  }
  console.log(bad === 0 ? '\n✓ 全部视口都没让 facts 行落进桥体' : `\n✗ ${bad} 个视口仍有交叉`);
  await b.close();
})();
