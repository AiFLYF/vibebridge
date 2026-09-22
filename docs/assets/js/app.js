/* ══════════════════════════════════════════════════════════════
   VIBEBRIDGE — docs page engine
   --------------------------------------------------------------
   一个 THREE.Points（数万粒子）在 7 组目标坐标间按滚动进度变形。
   形态序列即叙事：
     00 桥        —— 左岸（内部的光）→ 桥面 → 右岸（更大的世界）
     01 中空球壳  —— 只围住，不填满（不打扰）
     02 螺旋      —— 只追加、不回头的真相源
     03 六根柱    —— 六个维度，不等高，不被拉平
     04 收敛核心  —— 证据 → 置信度
     05 晶格      —— 确定性的数据层（安装完就退到背景里）
     06 文字      —— VIBEBRIDGE

   两条硬规则：
   · 内容密集的章节粒子一律压暗（op ≤ 0.35），排版优先于特效。
   · 桥的纵向位置是为 hero 文案让过路的，改几何前先看 hero 的版式。
   ══════════════════════════════════════════════════════════════ */

import * as THREE from 'three';

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const lerp = (a, b, t) => a + (b - a) * t;
const damp = (a, b, l, dt) => lerp(a, b, 1 - Math.exp(-l * dt)); // 与帧率无关的平滑

const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
const finePointer = matchMedia('(pointer: fine)').matches;

/* 低端 / 省流设备探测：命中任何一条就把粒子数降到 30000。
   和项目同一个哲学 —— 不给对方的设备和流量添负担。 */
const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
const lowEnd =
  !!(conn && (conn.saveData || /(^|-)2g$/.test(conn.effectiveType || ''))) ||
  (typeof navigator.deviceMemory === 'number' && navigator.deviceMemory < 4);

history.scrollRestoration = 'manual';
window.scrollTo(0, 0);

/* ── clock ────────────────────────────────────────────────── */
const clockEl = document.getElementById('clock');
if (clockEl) {
  const fmt = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  const tick = () => { clockEl.textContent = fmt.format(new Date()); };
  tick();
  setInterval(tick, 1000);
}

/* ── 惯性滚动（wheel 劫持 + 指数平滑） ────────────────────── */
class SmoothScroll {
  constructor() {
    this.enabled = !reduced && finePointer;
    this.t = 0; this.c = 0; this.max = 1;
    this.measure();
    window.addEventListener('wheel', (e) => this.onWheel(e), { passive: false });
    window.addEventListener('scroll', () => this.onScroll(), { passive: true });
  }
  measure() {
    this.max = Math.max(1, document.documentElement.scrollHeight - innerHeight);
    this.t = clamp(this.t, 0, this.max);
  }
  onWheel(e) {
    if (!this.enabled || e.ctrlKey) return;
    e.preventDefault();
    let d = e.deltaY;
    if (e.deltaMode === 1) d *= 16;
    else if (e.deltaMode === 2) d *= innerHeight;
    this.t = clamp(this.t + clamp(d, -190, 190), 0, this.max);
  }
  onScroll() {
    const y = window.scrollY;
    if (Math.abs(y - this.c) > 2) {          // 键盘 / 触摸 / 锚点跳转
      this.t = clamp(y, 0, this.max);
      if (Math.abs(y - this.c) > 200) this.c = y;
    }
  }
  to(y) {
    this.t = clamp(y, 0, this.max);
    if (!this.enabled) window.scrollTo({ top: this.t, behavior: reduced ? 'auto' : 'smooth' });
  }
  update(dt) {
    if (!this.enabled) { this.c = window.scrollY; return this.c; }
    this.c = damp(this.c, this.t, 7.5, dt);
    if (Math.abs(this.c - this.t) < 0.05) this.c = this.t;
    window.scrollTo(0, this.c);
    return this.c;
  }
}
const smooth = new SmoothScroll();

/* ── sections / 滚动进度 ──────────────────────────────────── */
const sections = [...document.querySelectorAll('[data-sec]')];
const N_CH = sections.length;
let tops = [];
const measureSections = () => { tops = sections.map((s) => s.offsetTop); };
measureSections();

function progressFromY(y) {
  for (let i = 0; i < N_CH - 1; i++) {
    if (y < tops[i + 1]) {
      const span = Math.max(1, tops[i + 1] - tops[i]);
      return i + clamp((y - tops[i]) / span, 0, 1);
    }
  }
  return N_CH - 1;
}

/* ── 导航 ─────────────────────────────────────────────────── */
const navLinks = [...document.querySelectorAll('.site-nav a[data-target]')];
const sideBtns = [...document.querySelectorAll('.side-index button')];
document.querySelectorAll('[data-target]').forEach((el) => {
  el.addEventListener('click', (e) => {
    e.preventDefault();
    smooth.to(tops[parseInt(el.dataset.target, 10)] + 2);
  });
});

let activeIdx = -1;
function setActive(i) {
  if (i === activeIdx) return;
  activeIdx = i;
  navLinks.forEach((a) => {
    const on = +a.dataset.target === i;
    a.classList.toggle('active', on);
    if (on) a.setAttribute('aria-current', 'true');
    else a.removeAttribute('aria-current');
  });
  sideBtns.forEach((b, k) => {
    const on = k === i;
    b.classList.toggle('active', on);
    if (on) b.setAttribute('aria-current', 'true');
    else b.removeAttribute('aria-current');
  });
}

/* ── 阅读进度条 ───────────────────────────────────────────── */
const progBarEl = document.getElementById('progressBar');
let lastProgK = -1;

/* ── 滚动 reveal ──────────────────────────────────────────── */
const io = new IntersectionObserver((entries) => {
  for (const en of entries) {
    if (en.isIntersecting) { en.target.classList.add('in-view'); io.unobserve(en.target); }
  }
}, { threshold: 0.16 });
document.querySelectorAll('[data-reveal]').forEach((el) => io.observe(el));

/* ── marquee 无缝循环 ─────────────────────────────────────── */
const marqueeGroup = document.getElementById('marqueeGroup');
if (marqueeGroup) marqueeGroup.parentElement.appendChild(marqueeGroup.cloneNode(true));

/* ── 自定义光标 ───────────────────────────────────────────── */
const dotEl = document.querySelector('.c-dot');
const ringEl = document.querySelector('.c-ring');
const cur = { x: innerWidth / 2, y: innerHeight / 2, dx: 0, dy: 0, rx: 0, ry: 0, on: false };
if (finePointer && !reduced) {
  window.addEventListener('pointermove', (e) => {
    cur.x = e.clientX; cur.y = e.clientY;
    if (!cur.on) {
      cur.on = true;
      cur.dx = cur.rx = cur.x; cur.dy = cur.ry = cur.y;
      document.body.classList.add('cursor-on');
    }
  });
  document.addEventListener('mouseover', (e) => {
    document.body.dataset.cursor = e.target.closest('a, button, [data-hover]') ? 'hover' : '';
  });
}

const skewEls = [...document.querySelectorAll('[data-skew]')];
let skewCur = 0;
const heroInner = document.querySelector('.hero-inner');

/* ══════════════════════════════════════════════════════════════
   章节参数
   rx/ry/rz 粒子群旋转 · z 相机距离 · noise 噪声振幅 · mouseF 鼠标排斥
   op 不透明度 · ps 点尺寸倍率（默认 1）· acc 强调色（写入 CSS 变量 --acc，全站自动跟随）
   ox / oy 整体偏移 —— 把形态推到「版面保证为空」的位置
   m  窄屏覆盖（**必须显式给 ox/oy/ps**，否则继承桌面的值会飞出画外或糊成一片）
   ══════════════════════════════════════════════════════════════

   落点不是凭感觉定的：用 scripts/occupancy.js 量出每屏的真实字形墨迹，
   再挑出空白区。结论是这一页的排版有个稳定规律 —— 巨型标题只占左侧
   （右侧 30–40% 空着），卡片从视口 50% 才开始。所以：

     00 桥      整条压在视口下方 1/4（y 74%–97%），标题与 facts 全让开
     01 球壳    右上 x70–85% / y20–45%
     02 螺旋    右上 x85–91% / y21–54%（立起来，不横穿面板）
     03 六根柱  右侧 42%（本来就对，是这一页唯一没出问题的形态）
     04 核心    右上 x73–87% / y20–44%
     05 晶格    右上 x62–88% / y19–44%
     06 文字    上半屏 y15%–39%，让开 06 标签与 closer 文案

   改动前：01 球壳压在 lede 上、02 螺旋横穿两个面板、04 核心糊在标题下、
   05 晶格铺满整屏像霉点、hero 两岸墨团压住 facts 行。根因是形态都堆在
   世界原点，而正文也在中间 —— 浅底深粒子叠黑字，就是糊。
   ══════════════════════════════════════════════════════════════ */
const CHAPTERS = [
  // 00 桥 —— 琥珀灯色（桥上的灯）。加色混合下密集处会过曝，op 从 0.92 压到 0.5
  /* 窄屏：横向的桥在竖屏里放不下，但旋转 -90° 会让桥塔变成两道横杠，
     必然横穿 facts 行（量到 13/255）。改成「不旋转 + 抬高视距 + 整体下移」，
     只露中央一跨（双塔 + 主缆 + 桥面）压在视口底部当一条地平线 ——
     内容一行都不碰，桥也照样认得出。两岸在竖屏下出画，是取舍。 */
  { rx: 0.16, ry: 0.0, rz: 0.0, z: 5.0, noise: 0.05, mouseF: 0.95, op: 0.55, acc: '#E8B44A',
    m: { rx: 0.16, ry: 0.0, rz: 0.0, z: 8.5, ox: 0, oy: -1.62, op: 0.5 } },
  // 01 中空球壳 —— 只围住不填满。月光银蓝，克制
  /* ps 0.62：默认点尺寸下，72000 个粒子挤在 111px 半径里，壳的前后两层投影重叠，
     整个球糊成一颗实心黑球，"中空"完全读不出来。点收小到 62% 后壳的结构才露出来。 */
  { rx: 0.30, ry: -0.5, rz: 0.0, z: 7.4, noise: 0.03, mouseF: 0.8, op: 0.30, acc: '#A8BCCB',
    ox: 3.35, oy: 1.20, ps: 0.62,
    m: { z: 9.6, ox: 0.70, oy: 3.05, op: 0.16, ps: 0.62 } },
  // 02 只追加的螺旋 —— 立起来：竖向线轴落在右上，冰蓝
  /* ps 0.62 同 01：默认点尺寸下螺旋的圈层糊成一坨，读不出"一圈圈往上长"。 */
  { rx: 0.10, ry: -0.42, rz: 0.0, z: 6.8, noise: 0.07, mouseF: 0.75, op: 0.32, acc: '#6FA8FF',
    ox: 4.29, oy: 0.82, ps: 0.62,
    m: { rx: 0.0, ry: -0.62, z: 9.6, ox: 0.95, oy: 3.05, op: 0.17, ps: 0.62 } },
  // 03 六根柱 —— 薄荷绿（柱子落在右侧 42%，见 formColumns）
  /* 柱体本来是模糊的黑色方块，跟左边清晰的绿色阶梯条并排显得脏。
     fuzz 来自 noise + 过大的点尺寸：ps 0.62 + noise 0.022 后柱面变细，
     边缘收干净；点变细覆盖下降，op 相应提到 0.46 保持存在感。
     竖屏：柱体极密（粒子全挤在 6 条窄柱里），op 0.14 都压到 42/255。
     而且 formColumns 的横坐标是按桌面视距 halfWidthAt(5.3) 算的，
     竖屏 z 变大后落点会漂到画面中央、正好压住 lede。
     和别章一样放到视口顶部那条带（内容之上），并抬高视距把柱体缩到 ~125px。 */
  { rx: 0.10, ry: -0.24, rz: 0.0, z: 5.3, noise: 0.022, mouseF: 0.7, op: 0.34, acc: '#4ED8A0', ps: 0.62,
    m: { rx: 0.0, ry: 0.0, z: 20.0, ox: 1.20, oy: 7.70, op: 0.26, ps: 0.62 } },
  // 04 收敛核心 —— 暖金（核心密度极高，op 比其它徽记再压一档才不显突兀）
  /* 竖屏：z 8.6 时核心半径 76px、中心落在 x284，正好压住小节标签尾部的「置信度」
     （30.4/255）。抬高视距缩到 ~50px 并右移到标签之外。 */
  { rx: 0.20, ry: 0.34, rz: 0.0, z: 6.2, noise: 0.05, mouseF: 0.85, op: 0.26, acc: '#E8B44A',
    ox: 3.08, oy: 1.04, ps: 0.62,
    m: { z: 13.0, ox: 2.10, oy: 4.20, op: 0.20, ps: 0.62 } },
  // 05 晶格 —— 暖骨白。线结构本来就比实心形态"轻"，op 给到 0.45 才不显灰淡
  { rx: 0.30, ry: -0.36, rz: 0.0, z: 7.2, noise: 0.035, mouseF: 0.6, op: 0.44, acc: '#BDB6A6',
    ox: 2.99, oy: 1.21,
    m: { z: 9.8, ox: 0.60, oy: 3.10, op: 0.20 } },
  // 06 文字 —— 星白（词标宽度按视口算，见 textWorldW）
  /* 窄屏 oy 上移到 nav 之下、06 标签之上那条带（y≈103–183px）。
     窄屏还要 ps=0.55 收小点尺寸：词标在 390px 上只有 347px 宽，
     笔画的屏幕宽度约 8.7px，而默认点尺寸 2–7px + 0.65px 采样间距
     会把笔画糊成实心黑 —— 点小一半，字形才出得来。 */
  { rx: 0.0, ry: 0.0, rz: 0.0, z: 6.4, noise: 0.028, mouseF: 0.6, op: 0.50, acc: '#F2EAD8',
    oy: 1.35, ps: 0.85, m: { oy: 1.97, ps: 0.5 } },
];

const isNarrow = () => innerWidth < 760 && innerHeight > innerWidth;
function ch(i) {
  const c = CHAPTERS[clamp(i, 0, N_CH - 1)];
  return isNarrow() && c.m ? Object.assign({}, c, c.m) : c;
}

/* 给定相机距离和当前宽高比，返回可见半宽（世界单位） */
const halfWidthAt = (z) => Math.tan((50 * Math.PI) / 360) * z * (innerWidth / innerHeight);

/* 末章词标的宽度：占可见宽度的 ~89%，这样竖屏也不会被切掉。
   9 个字符在竖屏塞不进 9 个世界单位，所以它必须跟着视口变。
   （窄屏不给它缩小 —— 缩了粒子密度会翻倍，字就糊成一团黑。
     竖屏的空间是靠 .sec-closer 的 padding-top 让出来的，见 style.css。） */
const TEXT_Z = 6.4;
const textWorldW = () => clamp(halfWidthAt(TEXT_Z) * 1.78, 2.2, 9.2);

/* ══════════════════════════════════════════════════════════════
   七个粒子形态
   ══════════════════════════════════════════════════════════════ */

/* 00 — 桥 ------------------------------------------------------
   这是整页的招牌意象，比例必须经得起看。改动前的问题：
     · 桥面 y=-2.28 而 z=5.0 时视口半高只有 2.33 —— 桥面贴着底边被切；
     · 两岸用 cbrt 均匀采样 = 实心球，边缘一刀切，白底上读成两坨墨渍；
     · 两岸压到 y≈67%，正好糊在 hero 的 facts 行和正文上。
   现在：整条桥收进视口下方 1/4，两岸改成「中心密、边缘散」的墨晕。 */
function formBridge(count) {
  const out = new Float32Array(count * 3);

  /* 纵向位置是为 hero 排版让过路的：塔顶落在视口 ~74%，桥面 ~93%。
     再高就会压住「一座桥」和正文，再低桥面就被视口底边切掉。 */
  const L = -3.55, R = 3.55;
  const DECK_Y = -2.02, DECK_Z = 0.085;
  const TOW_X = 1.45, TOW_TOP = -1.14, TOW_HW = 0.05;
  const SAG = 0.52;
  const BANK_L = [-3.62, -1.95];   // 左岸：一个人内部的光 —— 小、紧、中心密
  const BANK_R = [3.80, -2.02];    // 右岸：更大的世界 —— 大、散、漫出画外

  // 主缆高度：塔内悬垂（抛物线），塔外缓降
  const cableY = (x) => {
    const ax = Math.abs(x);
    if (ax <= TOW_X) {
      const t = ax / TOW_X;
      return TOW_TOP - SAG * (1 - t * t);
    }
    const t = Math.min(1, (ax - TOW_X) / (R - TOW_X));
    return TOW_TOP + (DECK_Y - TOW_TOP) * (t * t * 0.55 + t * 0.45);
  };

  const hangerX = [];
  for (let x = -3.26; x <= R - 0.06; x += 0.42) hangerX.push(x);

  const segs = [
    // 桥面 —— 权重最大，它得读成一条实打实的路，不是虚线
    { w: 0.30, f: () => [
      L + Math.random() * (R - L),
      DECK_Y + (Math.random() - 0.62) * 0.115,
      (Math.random() * 2 - 1) * DECK_Z,
    ] },
    // 桥塔（四面壳体）
    { w: 0.078, f: () => {
      const sx = Math.random() < 0.5 ? -1 : 1;
      let dx, dz;
      if (Math.random() < 0.5) { dx = (Math.random() * 2 - 1) * TOW_HW; dz = Math.random() < 0.5 ? -TOW_HW : TOW_HW; }
      else { dz = (Math.random() * 2 - 1) * TOW_HW; dx = Math.random() < 0.5 ? -TOW_HW : TOW_HW; }
      return [sx * TOW_X + dx, DECK_Y + Math.random() * (TOW_TOP - DECK_Y), dz];
    } },
    // 主缆
    { w: 0.135, f: () => {
      const sx = Math.random() < 0.5 ? -1 : 1;
      const x = Math.random() < 0.5
        ? sx * (TOW_X + Math.random() * (R - TOW_X))
        : sx * Math.random() * TOW_X;
      const j = 0.020;
      return [x + (Math.random() * 2 - 1) * j, cableY(x) + (Math.random() * 2 - 1) * j, (Math.random() * 2 - 1) * j];
    } },
    // 吊索 —— 权重压到 0.05：竖屏旋转后它最容易读成"梯子"，少给点粒子
    { w: 0.05, f: () => {
      const x = hangerX[(Math.random() * hangerX.length) | 0];
      const cy = cableY(x);
      return [x + (Math.random() * 2 - 1) * 0.012, cy + (DECK_Y - cy) * Math.random(), (Math.random() * 2 - 1) * 0.012];
    } },
    // 左岸 —— 一个人内部的光。pow(rand,1.5) 让密度向中心聚，边缘自然散掉，
    // 读起来是墨晕而不是墨块。25% 的粒子放宽一点当外晕。
    { w: 0.115, f: () => {
      const halo = Math.random() < 0.25;
      const r = (halo ? 0.42 : 0.40) * Math.pow(Math.random(), halo ? 0.6 : 1.5);
      const a = Math.random() * Math.PI * 2;
      const b = Math.acos(2 * Math.random() - 1);
      return [BANK_L[0] + r * Math.sin(b) * Math.cos(a),
              BANK_L[1] + r * Math.sin(b) * Math.sin(a) * 0.70,
              r * Math.cos(b) * 0.82];
    } },
    // 右岸 —— 更大的世界。半径往外偏（pow<1），铺得更开更薄，还会漫出画外。
    // 竖向压到 0.40：抬到 y≈84% 以下，别糊住右下角的 SCROLL 提示。
    { w: 0.13, f: () => {
      const r = 0.22 + 0.82 * Math.pow(Math.random(), 0.42);
      const a = Math.random() * Math.PI * 2;
      const b = Math.acos(2 * Math.random() - 1);
      return [BANK_R[0] + r * Math.sin(b) * Math.cos(a) * 1.15,
              BANK_R[1] + r * Math.sin(b) * Math.sin(a) * 0.40,
              r * Math.cos(b) * 0.62];
    } },
    // 空气中的浮尘 —— 只留在桥那一条带里（y ∈ [-2.32,-1.15] → 视口 72%–100%）。
    // 原来撒到 y=+1.7，整片标题和「一座桥」上全是麻点；
    // 上沿从 -0.95 再抬到 -1.15，让开右下角的 SCROLL 提示（scripts/collide.js 量出来的）。
    { w: 0.05, f: () => [
      (Math.random() * 2 - 1) * 4.3,
      -2.32 + Math.random() * 1.17,
      (Math.random() * 2 - 1) * 1.5,
    ] },
  ];

  const total = segs.reduce((s, x) => s + x.w, 0);
  const cum = [];
  let acc = 0;
  for (const s of segs) { acc += s.w / total; cum.push(acc); }

  for (let i = 0; i < count; i++) {
    const r = Math.random();
    let k = 0;
    while (k < cum.length - 1 && r > cum[k]) k++;
    const p = segs[k].f();
    out[i * 3] = p[0]; out[i * 3 + 1] = p[1]; out[i * 3 + 2] = p[2];
  }
  return out;
}

/* 01 — 中空球壳（只围住，不填满） ------------------------------
   半径由章节参数决定：它要装进右上那块 700×225px 的空白区，不能压到 lede。 */
function formShell(count, RAD = 0.85) {
  const out = new Float32Array(count * 3);
  const GA = Math.PI * (3 - Math.sqrt(5));

  for (let i = 0; i < count; i++) {
    // 斐波那契球均匀采样 + 壳厚抖动；半径扰动让它不像数学教具
    const t = (i + 0.5) / count;
    const y = 1 - 2 * t;
    const rad = Math.sqrt(Math.max(0, 1 - y * y));
    const th = GA * i;
    const wob = 0.055 * (Math.sin(th * 2.3) * 0.5 + Math.sin(y * 5.1) * 0.5);
    const R = RAD + wob + (Math.random() - 0.5) * 0.035;
    out[i * 3] = Math.cos(th) * rad * R;
    out[i * 3 + 1] = y * R;
    out[i * 3 + 2] = Math.sin(th) * rad * R;
  }
  return out;
}

/* 02 — 只追加的螺旋 --------------------------------------------
   立起来：轴沿 y。横向的螺旋必然横穿面板，竖着放才能落进右上空白区，
   而且"向上生长"比"向右延伸"更贴"只追加、不回头"。
   高度 ±1.05 世界单位，配上 ox=4.29 / oy=0.82 落在 x85–91% / y21–54%。 */
function formHelix(count) {
  const out = new Float32Array(count * 3);
  const TURNS = 11.0, HALF = 1.05, AXIS_HW = 0.020;

  for (let i = 0; i < count; i++) {
    if (Math.random() < 0.14) {
      // 轴心：那条永不回头的直线
      out[i * 3] = (Math.random() * 2 - 1) * AXIS_HW;
      out[i * 3 + 1] = -HALF + Math.random() * HALF * 2;
      out[i * 3 + 2] = (Math.random() * 2 - 1) * AXIS_HW;
      continue;
    }
    const t = Math.random();
    const ang = t * TURNS * Math.PI * 2;
    const r = 0.145 + 0.135 * t;                  // 越往上越宽：日志在长
    const tube = 0.016 * Math.cbrt(Math.random());
    const a = Math.random() * Math.PI * 2;
    const b = Math.acos(2 * Math.random() - 1);
    out[i * 3] = r * Math.cos(ang) + tube * Math.sin(b) * Math.cos(a);
    out[i * 3 + 1] = -HALF + HALF * 2 * t + (Math.random() - 0.5) * 0.012;
    out[i * 3 + 2] = r * Math.sin(ang) + tube * Math.sin(b) * Math.sin(a);
  }
  return out;
}

/* 03 — 六个维度，六根不等高的柱 ---------------------------------
   x 范围按视口半宽算，落在正文右侧那 42% 里，避免和阶梯列表打架。 */
function formColumns(count) {
  const out = new Float32Array(count * 3);
  // L5 / L3 / L2 / L7 / L4 / L2 —— 与页面上的示意一致，刻意不平均
  const LEVELS = [5, 3, 2, 7, 4, 2];
  const BASE = -1.88, MAXH = 2.77, HALF_W = 0.115;

  const hw = halfWidthAt(5.3);
  const x1 = Math.min(hw * 0.86, 3.6);
  const x0 = Math.max(x1 - 2.6, 0.5);
  const step = (x1 - x0) / (LEVELS.length - 1);

  for (let i = 0; i < count; i++) {
    const k = (Math.random() * LEVELS.length) | 0;
    const h = (LEVELS[k] / 10) * MAXH;
    const x = x0 + k * step;
    // 15% 的粒子贴在柱顶，形成一道亮边
    const cap = Math.random() < 0.15;
    out[i * 3] = x + (Math.random() * 2 - 1) * HALF_W;
    out[i * 3 + 1] = BASE + (cap ? h + (Math.random() - 0.5) * 0.05 : Math.random() * h);
    out[i * 3 + 2] = (Math.random() * 2 - 1) * HALF_W * (cap ? 1.15 : 1);
  }
  return out;
}

/* 04 — 收敛核心（证据 → 置信度） -------------------------------
   整体缩到 0.49 倍：原始尺寸半径 1.47 世界单位，在 z=6.2 下直径 400px，
   正好糊在 H2 第二行和 formula 面板上。现在装进右上 700×225px 的空白区。 */
function formCore(count, S = 0.49) {
  const out = new Float32Array(count * 3);

  for (let i = 0; i < count; i++) {
    const roll = Math.random();

    if (roll > 0.84) {
      // 两圈轨道：结构感
      const ring = (Math.random() < 0.5 ? 0.92 : 1.26) * S;
      const ang = Math.random() * Math.PI * 2;
      const tilt = ring < 1.1 * S ? 0.52 : -0.42;
      const x0 = ring * Math.cos(ang), y0 = ring * Math.sin(ang);
      out[i * 3] = x0;
      out[i * 3 + 1] = y0 * Math.cos(tilt) + (Math.random() - 0.5) * 0.04 * S;
      out[i * 3 + 2] = y0 * Math.sin(tilt) + (Math.random() - 0.5) * 0.04 * S;
      continue;
    }

    let r;
    if (roll < 0.38) r = 0.36 * Math.cbrt(Math.random());            // 核
    else r = 0.42 + 1.05 * Math.pow(Math.random(), 2.2);             // 向心汇聚的证据流
    r *= S;

    const a = Math.random() * Math.PI * 2;
    const b = Math.acos(2 * Math.random() - 1);
    out[i * 3] = r * Math.sin(b) * Math.cos(a);
    out[i * 3 + 1] = r * Math.sin(b) * Math.sin(a);
    out[i * 3 + 2] = r * Math.cos(b) * 0.88;
  }
  return out;
}

/* 05 — 确定性数据层：稀疏晶格 ----------------------------------
   画「线」，不画「点」。
   原来的实现把 273 个格点各做成一团 ~264 粒子的球（抖动 ±0.07 ≈ 19px），
   在纸白底上就是满屏深色霉点，直接把 H2 和两个面板盖住。
   改成沿网格棱线铺粒子：线读得出"确定的结构"，点只会读成脏。
   HW/HH/HD 是半宽/半高/半深，由章节的 ox/oy 定位到右上空白区。 */
/* 05 — 晶格：画「线」不画「点」。
   原来只在四角连进深线，正面看就是个平面网格，像块纱窗。
   改成每个格点都连进深 —— 厚度全程可见，才读得出是个立体的笼子。
   抖动 J 只有 0.006（原值 0.07 的 1/12），线才是线而不是霉点。 */
function formLattice(count, HW = 1.55, HH = 0.80, HD = 0.26) {
  const out = new Float32Array(count * 3);
  const NX = 7, NY = 5, NZ = 3;

  const lines = [];
  const push = (a, b) => lines.push([a, b, Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2])]);
  const xAt = (ix) => (ix / (NX - 1) - 0.5) * 2 * HW;
  const yAt = (iy) => (iy / (NY - 1) - 0.5) * 2 * HH;

  // 竖向棱线（沿 y），前后两层
  for (let ix = 0; ix < NX; ix++) for (const iz of [0, NZ - 1]) {
    push([xAt(ix), -HH, (iz / (NZ - 1) - 0.5) * 2 * HD], [xAt(ix), HH, (iz / (NZ - 1) - 0.5) * 2 * HD]);
  }
  // 横向棱线（沿 x），前后两层
  for (let iy = 0; iy < NY; iy++) for (const iz of [0, NZ - 1]) {
    push([-HW, yAt(iy), (iz / (NZ - 1) - 0.5) * 2 * HD], [HW, yAt(iy), (iz / (NZ - 1) - 0.5) * 2 * HD]);
  }
  // 进深连线：每个格点都连（原来只连四角 → 平面感）
  for (let ix = 0; ix < NX; ix++) for (let iy = 0; iy < NY; iy++) {
    push([xAt(ix), yAt(iy), -HD], [xAt(ix), yAt(iy), HD]);
  }

  const total = lines.reduce((s, l) => s + l[2], 0);
  const J = 0.006;
  let i = 0;
  for (const [a, b, len] of lines) {
    const n = Math.max(1, Math.round((len / total) * count));
    for (let k = 0; k < n && i < count; k++, i++) {
      const t = Math.random();
      out[i * 3] = a[0] + (b[0] - a[0]) * t + (Math.random() * 2 - 1) * J;
      out[i * 3 + 1] = a[1] + (b[1] - a[1]) * t + (Math.random() * 2 - 1) * J;
      out[i * 3 + 2] = a[2] + (b[2] - a[2]) * t + (Math.random() * 2 - 1) * J;
    }
  }
  // 余量当框内浮尘，别浪费（否则这批粒子会留在原点，糊在画面中央）
  for (; i < count; i++) {
    out[i * 3] = (Math.random() * 2 - 1) * HW;
    out[i * 3 + 1] = (Math.random() * 2 - 1) * HH;
    out[i * 3 + 2] = (Math.random() * 2 - 1) * HD;
  }
  return out;
}

/* 06 — 文字粒子 ------------------------------------------------ */
function formText(count, str, worldW) {
  const out = new Float32Array(count * 3);
  const pts = sampleText(str, worldW);
  for (let i = 0; i < count; i++) {
    const p = pts[i % pts.length];
    out[i * 3] = p[0] + (Math.random() - 0.5) * 0.026;
    out[i * 3 + 1] = p[1] + (Math.random() - 0.5) * 0.026;
    out[i * 3 + 2] = (Math.random() - 0.5) * 0.34;
  }
  return out;
}

function sampleText(str, worldW) {
  const cw = 1600, ch = 460;
  const cv = document.createElement('canvas');
  cv.width = cw; cv.height = ch;
  const cx = cv.getContext('2d', { willReadFrequently: true });
  // CJK 必须带中文字体栈，否则 fillText 画出豆腐块，采样为空
  const stack = '"Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", Arial, sans-serif';
  let size = 340;
  cx.font = `900 ${size}px ${stack}`;
  const w = cx.measureText(str).width;
  size = Math.floor(size * Math.min((cw * 0.9) / w, (ch * 0.8) / size));
  cx.font = `900 ${size}px ${stack}`;
  cx.textAlign = 'center';
  cx.textBaseline = 'middle';
  cx.fillStyle = '#fff';
  cx.fillText(str, cw / 2, ch / 2 + size * 0.03);

  const img = cx.getImageData(0, 0, cw, ch).data;
  const pts = [];
  const worldH = worldW * (ch / cw);
  for (let py = 0; py < ch; py += 3) {
    for (let px = 0; px < cw; px += 3) {
      if (img[(py * cw + px) * 4 + 3] > 128) {
        pts.push([(px / cw - 0.5) * worldW, -(py / ch - 0.5) * worldH]);
      }
    }
  }
  return pts.length ? pts : [[0, 0]];
}

/* ══════════════════════════════════════════════════════════════
   shaders
   ══════════════════════════════════════════════════════════════ */
const VERT = /* glsl */ `
attribute vec3 aT1;
attribute vec3 aT2;
attribute vec3 aT3;
attribute vec3 aT4;
attribute vec3 aT5;
attribute vec3 aT6;
attribute vec4 aRand;
uniform float uTime;
uniform float uProg;
uniform float uNoise;
uniform vec3  uMouse;
uniform float uMouseF;
uniform float uSize;
varying float vMix;
varying float vFade;
varying float vTw;
varying float vTrans;

vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0);
  const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy));
  vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz);
  vec3 l=1.0-g;
  vec3 i1=min(g.xyz,l.zxy);
  vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx;
  vec3 x2=x0-i2+C.yyy;
  vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857;
  vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z);
  vec4 x_=floor(j*ns.z);
  vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy;
  vec4 y=y_*ns.x+ns.yyyy;
  vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy);
  vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0;
  vec4 s1=floor(b1)*2.0+1.0;
  vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;
  vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x);
  vec3 p1=vec3(a0.zw,h.y);
  vec3 p2=vec3(a1.xy,h.z);
  vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0);
  m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}

void main(){
  float s1 = smoothstep(0.0, 1.0, clamp(uProg - 0.0, 0.0, 1.0));
  float s2 = smoothstep(0.0, 1.0, clamp(uProg - 1.0, 0.0, 1.0));
  float s3 = smoothstep(0.0, 1.0, clamp(uProg - 2.0, 0.0, 1.0));
  float s4 = smoothstep(0.0, 1.0, clamp(uProg - 3.0, 0.0, 1.0));
  float s5 = smoothstep(0.0, 1.0, clamp(uProg - 4.0, 0.0, 1.0));
  float s6 = smoothstep(0.0, 1.0, clamp(uProg - 5.0, 0.0, 1.0));

  vec3 pos = position;
  pos = mix(pos, aT1, s1);
  pos = mix(pos, aT2, s2);
  pos = mix(pos, aT3, s3);
  pos = mix(pos, aT4, s4);
  pos = mix(pos, aT5, s5);
  pos = mix(pos, aT6, s6);

  // 变形中的湍流：噪声 ×9，粒子先炸开再收拢 —— 高级感的关键
  float trans = s1*(1.0-s1) + s2*(1.0-s2) + s3*(1.0-s3)
              + s4*(1.0-s4) + s5*(1.0-s5) + s6*(1.0-s6);
  // 过渡期压暗：形态变形时会从正文上扫过去，那一瞬间把粒子淡掉，
  // 读起来像"一次呼吸"而不是"一坨糊在字上"。静止时 vTrans≈0，不影响成稿。
  // 系数 0.68：扫描发现 hero→球壳的过渡态会飘出粒子薄雾，落在下方小字列表上
  // （1280×800 @y=640 量到 20–28/255，且这个指标本身有 ±4 噪声）。
  vTrans = clamp(trans * 2.2, 0.0, 1.0);
  float amp = uNoise * (1.0 + trans * 9.0);
  float t = uTime * (0.22 + aRand.z * 0.18);
  vec3 n = vec3(
    snoise(pos * 0.85 + vec3(t, 0.0, aRand.y * 7.1)),
    snoise(pos * 0.85 + vec3(0.0, t + 13.7, aRand.y * 3.3)),
    snoise(pos * 0.85 + vec3(t * 0.7, aRand.y * 5.2, 0.0))
  );
  pos += n * amp;

  // 螺旋章节的轻微涌动：日志还在追加
  float waveW = s2 * (1.0 - s3);
  pos.y += waveW * sin(pos.x * 2.1 + uTime * 1.1) * 0.10;

  // 鼠标排斥（世界空间）
  vec4 wp = modelMatrix * vec4(pos, 1.0);
  vec3 dm = wp.xyz - uMouse;
  float f = smoothstep(0.95, 0.0, length(dm)) * uMouseF;
  wp.xyz += normalize(dm + 0.0001) * f * 0.34;

  vec4 mv = viewMatrix * wp;
  gl_Position = projectionMatrix * mv;

  float dist = max(0.1, -mv.z);
  // sprite 放大 1.6 倍给晕留出面积；FRAG 里核乘回 1.6，屏幕上的核径不变。
  // 填充率 ×2.56 —— perf.js 掉到 50fps 以下就把这个系数降到 1.3。
  gl_PointSize = uSize * (0.55 + aRand.x * 1.15) * (4.6 / dist) * 1.6;

  vMix = smoothstep(0.80, 0.97, aRand.w);
  vFade = smoothstep(13.0, 3.0, dist);
  vTw = 0.45 + 0.55 * sin(uTime * 2.0 + aRand.y * 43.0);
}
`;

const FRAG = /* glsl */ `
uniform vec3 uColA;
uniform vec3 uColB;
uniform float uOpacity;
varying float vMix;
varying float vFade;
varying float vTw;
varying float vTrans;

void main(){
  // 暗底加色发光：亮核 + 宽晕两项衰减，在 point sprite 内假 bloom。
  // sprite 被放大 1.6 倍（见 VERT 的 gl_PointSize），所以核要乘回 1.6
  // 才和旧 disc 同尺寸；晕铺满整个 sprite，稀疏处读作星尘。
  // 密集处（桥面、词标笔画）加色叠加会削顶死白 —— 软膝 1-exp() 压住。
  float d = length(gl_PointCoord - 0.5) * 2.0;
  if (d > 1.0) discard;
  float core = pow(max(0.0, 1.0 - d * 1.6), 3.0);
  float halo = pow(max(0.0, 1.0 - d), 1.6) * 0.30;
  vec3 base = mix(uColA, uColB, vMix);
  vec3 col = base + vec3(1.0) * pow(core, 3.0) * 0.55;   // 核芯趋白热
  float a = (core + halo) * vFade * vTw * uOpacity * (1.0 - vTrans * 0.68);
  a = 1.0 - exp(-a * 1.6);
  gl_FragColor = vec4(col * a, a);
}
`;

/* ══════════════════════════════════════════════════════════════
   GL 初始化
   ══════════════════════════════════════════════════════════════ */
let renderer, scene, camera, points, uni, aT6;
let progT = 0, progC = 0, glTime = 0;
let hasPointer = false;
const mouseW = new THREE.Vector3(999, 999, 0);
const mouseT = new THREE.Vector3(0, 0, 0);
let halfW = 1, halfH = 1;
const glState = { ok: false };

/* 自适应画质：帧率持续不达标时逐级下调像素比。
   只降不升 —— 升回去会造成可见的振荡。 */
const DPR_STEPS = [1.75, 1.3, 1.0];
let dprStep = 0;
let basePtSize = 4.6;
let dprCur = 1;
function applyPixelRatio() {
  dprCur = Math.min(clamp(devicePixelRatio || 1, 1, 1.75), DPR_STEPS[dprStep]);
  renderer.setPixelRatio(dprCur);
  renderer.setSize(innerWidth, innerHeight);
  // uSize 每帧按章节的 ps 重算（见 renderGL），这里不写死
  return dprCur;
}

const accCur = new THREE.Color(CHAPTERS[0].acc);
const accTarget = new THREE.Color();
const accA = new THREE.Color(), accB = new THREE.Color();
let lastAccHex = '';

function initGL() {
  const canvas = document.getElementById('gl');

  /* 上下文丢失（切后台久了 / 驱动重置 / 内存压力）不能让整页死掉：
     preventDefault 才收得到 restored；three 会自动重建 program 和 buffer，
     期间 CSS 兜底背景顶上。 */
  canvas.addEventListener('webglcontextlost', (e) => {
    e.preventDefault();
    glState.ok = false;
    document.body.classList.add('ctx-lost');
  }, false);
  canvas.addEventListener('webglcontextrestored', () => {
    glState.ok = true;
    document.body.classList.remove('ctx-lost');
  }, false);

  renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true, powerPreference: 'high-performance' });
  renderer.setClearColor(0x000000, 0);

  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 0.1, 60);
  camera.position.z = CHAPTERS[0].z;

  const small = Math.min(innerWidth, innerHeight) < 720 || !finePointer;
  const COUNT = (small || lowEnd) ? 30000 : 72000;

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(formBridge(COUNT), 3));
  geo.setAttribute('aT1', new THREE.BufferAttribute(formShell(COUNT), 3));
  geo.setAttribute('aT2', new THREE.BufferAttribute(formHelix(COUNT), 3));
  geo.setAttribute('aT3', new THREE.BufferAttribute(formColumns(COUNT), 3));
  geo.setAttribute('aT4', new THREE.BufferAttribute(formCore(COUNT), 3));
  geo.setAttribute('aT5', new THREE.BufferAttribute(formLattice(COUNT), 3));
  aT6 = new THREE.BufferAttribute(formText(COUNT, 'VIBEBRIDGE', textWorldW()), 3);
  geo.setAttribute('aT6', aT6);

  const rnd = new Float32Array(COUNT * 4);
  for (let i = 0; i < COUNT * 4; i++) rnd[i] = Math.random();
  geo.setAttribute('aRand', new THREE.BufferAttribute(rnd, 4));

  uni = {
    uTime: { value: 0 },
    uProg: { value: 0 },
    uNoise: { value: CHAPTERS[0].noise },
    uMouse: { value: mouseW },
    uMouseF: { value: finePointer ? 1 : 0 },
    uSize: { value: small ? 5.6 : 4.6 },
    // 暗底：主体粒子是冷灰蓝的星尘，vMix 挑出的少数粒子走章节强调色
    uColA: { value: new THREE.Color('#5D6B82') },
    uColB: { value: new THREE.Color(CHAPTERS[0].acc) },
    uOpacity: { value: CHAPTERS[0].op },
  };
  basePtSize = uni.uSize.value;
  applyPixelRatio();

  const mat = new THREE.ShaderMaterial({
    uniforms: uni,
    vertexShader: VERT,
    fragmentShader: FRAG,
    transparent: true,
    depthWrite: false,
    depthTest: false,
    // 暗底发光：加色混合让密集处自然过曝成灯芯白。
    blending: THREE.AdditiveBlending,
  });

  points = new THREE.Points(geo, mat);
  points.frustumCulled = false;
  scene.add(points);

  computeHalfExtents();
  glState.ok = true;
}

function computeHalfExtents() {
  halfH = Math.tan((camera.fov * Math.PI) / 360) * camera.position.z;
  halfW = halfH * camera.aspect;
}

if (finePointer) {
  window.addEventListener('pointermove', (e) => {
    hasPointer = true;
    mouseT.x = (e.clientX / innerWidth) * 2 - 1;
    mouseT.y = -((e.clientY / innerHeight) * 2 - 1);
  });
}

function renderGL(dt) {
  if (!glState.ok) return;
  glTime += dt;
  progC = damp(progC, progT, 4.5, dt);

  const i = clamp(Math.floor(progC), 0, N_CH - 2);
  const f = progC - i;
  const sf = f * f * (3 - 2 * f);
  const A = ch(i), B = ch(i + 1);

  // 末章文字要稳定可读，别让它继续晃
  const textW = clamp(progC - (N_CH - 1) + 0.8, 0, 0.8) / 0.8;
  const idle = Math.sin(glTime * 0.1) * 0.14 * (1 - textW);

  points.rotation.set(
    lerp(A.rx, B.rx, sf),
    lerp(A.ry, B.ry, sf) + idle,
    lerp(A.rz, B.rz, sf)
  );

  /* 末章词标要跟着 closer 章节一起上移。
     粒子层是 position:fixed 的，正文却在滚 —— 不跟的话，滚过 06 之后
     正文会从词标底下穿过去，实心压住「06 — START」和 closer 文案
     （全页扫描量到 49.8/255）。1:1 跟随滚动后，词标下沿和 06 标签
     永远保持 9px 的固定间距，怎么滚都不碰。 */
  const pastCloserPx = clamp(scrollY - tops[N_CH - 1], 0, innerHeight * 1.4);
  const pxToWorld = (2 * Math.tan((camera.fov * Math.PI) / 360) * camera.position.z) / innerHeight;
  points.position.set(
    lerp(A.ox || 0, B.ox || 0, sf),
    lerp(A.oy || 0, B.oy || 0, sf) + pastCloserPx * pxToWorld,
    0
  );

  camera.position.z = lerp(A.z, B.z, sf);
  camera.position.x = damp(camera.position.x, mouseT.x * 0.22, 3, dt);
  camera.position.y = damp(camera.position.y, mouseT.y * 0.16, 3, dt);
  camera.lookAt(0, 0, 0);

  uni.uNoise.value = lerp(A.noise, B.noise, sf) * (reduced ? 0.5 : 1);
  // 点尺寸随章节变：小尺寸的词标需要更小的点，否则笔画糊成实心
  uni.uSize.value = basePtSize * dprCur * lerp(A.ps || 1, B.ps || 1, sf);
  // 末屏之后淡出：词标属于那一屏，翻过去就该让位给免责声明。
  // 位置已经 1:1 跟随滚动了，这里只负责让它在接近导航条时安静退场。
  const pastCloser = clamp(pastCloserPx / (innerHeight * 0.55), 0, 1);

  /* 矮视口（横屏手机 844×390 这类「宽而矮」）：
     章节正文会铺满整屏，粒子形态找不到任何空位 —— 往哪挪都压字
     （实测球体实心压住 lede，55.2/255）。硬挪是没用的，因为没有空位。
     所以把非 hero 章节的粒子降级成背景纹理，让正文优先；
     第 0 章的桥是主角，不降级 —— 用 progC 平滑过渡，不跳变。 */
  const shortFade = innerHeight < 640
    ? clamp((innerHeight - 360) / 280, 0.18, 1)
    : 1;
  const fade = lerp(1, shortFade, clamp(progC, 0, 1));

  uni.uOpacity.value = lerp(A.op, B.op, sf) * (1 - pastCloser * 0.95) * fade;
  uni.uMouseF.value = finePointer ? lerp(A.mouseF, B.mouseF, sf) : 0;
  uni.uProg.value = progC;
  uni.uTime.value = glTime;

  // 章节强调色 → 粒子 + CSS 变量（全站的选中色/光标/下划线自动跟随）
  accA.set(A.acc); accB.set(B.acc);
  accTarget.lerpColors(accA, accB, sf);
  accCur.lerp(accTarget, 1 - Math.exp(-6 * dt));
  uni.uColB.value.copy(accCur);
  const hex = '#' + accCur.getHexString();
  if (hex !== lastAccHex) {
    lastAccHex = hex;
    document.documentElement.style.setProperty('--acc', hex);
  }

  computeHalfExtents();
  if (hasPointer) {
    mouseW.x = damp(mouseW.x, mouseT.x * halfW, 5, dt);
    mouseW.y = damp(mouseW.y, mouseT.y * halfH, 5, dt);
  }

  renderer.render(scene, camera);
}

try {
  initGL();
} catch (err) {
  document.body.classList.add('no-webgl');
  console.warn('WebGL unavailable:', err);
}

/* ── preloader ──────────────────────────────────────────────
   进度条不再说谎：数字由「时间进度 × 0.5 + 首帧已渲染 × 0.5」构成。
   收起条件 = 至少展示 LOAD_MIN（保留仪式感）且 GL 首帧已出（或本就没
   WebGL / reduced-motion），LOAD_MAX 是保险丝 —— 任何情况都不卡死。 */
const preCount = document.getElementById('preCount');
const preBar = document.getElementById('preBar');
const LOAD_MIN = reduced ? 200 : 900;
const LOAD_MAX = reduced ? 500 : 7000;
const loadStart = performance.now();
let firstFrameDone = !glState.ok;
let loaded = false;

function loaderTick(now) {
  if (loaded) return;
  const el = now - loadStart;
  const timeP = clamp(el / LOAD_MIN, 0, 1);
  const eased = 1 - Math.pow(1 - (timeP * 0.5 + (firstFrameDone ? 0.5 : 0)), 2);
  if (preCount) preCount.textContent = String(Math.floor(eased * 100)).padStart(2, '0');
  if (preBar) preBar.style.transform = `scaleX(${eased})`;
  if (!(el >= LOAD_MIN && firstFrameDone) && el < LOAD_MAX) {
    requestAnimationFrame(loaderTick);
    return;
  }
  loaded = true;
  if (preCount) preCount.textContent = '100';
  if (preBar) preBar.style.transform = 'scaleX(1)';
  // 等字体就绪再收起，避免 FOUT；但不能无限等
  Promise.race([document.fonts.ready, new Promise((r) => setTimeout(r, 1500))]).then(() => {
    document.body.classList.add('is-loaded');
    measureSections();
    smooth.measure();
  });
}
requestAnimationFrame(loaderTick);

/* ── 主循环 ───────────────────────────────────────────────── */
let last = performance.now();
let rafId = 0;

/* 画质看门狗：前 3s 是编译/预热期不评估，之后每 2s 一个窗口，
   窗口均值 > 30ms（≈33fps）就降一档像素比，降到底为止。 */
let perfAccum = 0, perfFrames = 0, perfWarm = 0;
function perfWatch(rawMs) {
  if (!glState.ok || dprStep >= DPR_STEPS.length - 1) return;
  perfWarm += rawMs;
  if (perfWarm < 3000) return;
  perfAccum += rawMs;
  perfFrames++;
  if (perfAccum < 2000) return;
  if (perfAccum / perfFrames > 30) {
    dprStep++;
    applyPixelRatio();
  }
  perfAccum = 0;
  perfFrames = 0;
}

let skewLast = NaN;

function frame(now) {
  rafId = requestAnimationFrame(frame);
  const rawMs = now - last;
  const dt = Math.min(rawMs / 1000, 0.05);
  last = now;
  if (rawMs < 200) perfWatch(rawMs);   // 切标签页回来的超长帧不算数

  const y = smooth.update(dt);
  const vel = smooth.enabled ? (smooth.t - smooth.c) : 0;

  progT = progressFromY(y);
  setActive(clamp(Math.round(progressFromY(y + innerHeight * 0.25)), 0, N_CH - 1));
  document.body.classList.toggle('scrolled', y > 80);

  if (progBarEl) {
    const k = Math.round(clamp(y / smooth.max, 0, 1) * 1000);
    if (k !== lastProgK) {
      progBarEl.style.transform = `scaleX(${k / 1000})`;
      lastProgK = k;
    }
  }

  if (!reduced) {
    const target = clamp(vel * 0.0032, -3, 3);
    skewCur = damp(skewCur, target, 8, dt);
    const sk = Math.abs(skewCur) < 0.01 ? 0 : skewCur;
    if (sk !== skewLast) {             // 静止时不写 DOM
      skewLast = sk;
      for (const el of skewEls) el.style.transform = `skewY(${sk}deg)`;
    }

    if (heroInner && y < innerHeight * 1.2) {
      heroInner.style.transform = `translate3d(0, ${y * 0.22}px, 0)`;
    }

    if (cur.on && dotEl && ringEl) {
      cur.dx = damp(cur.dx, cur.x, 30, dt);
      cur.dy = damp(cur.dy, cur.y, 30, dt);
      cur.rx = damp(cur.rx, cur.x, 12, dt);
      cur.ry = damp(cur.ry, cur.y, 12, dt);
      dotEl.style.transform = `translate(${cur.dx - 3}px, ${cur.dy - 3}px)`;
      ringEl.style.transform = `translate(${cur.rx}px, ${cur.ry}px) translate(-50%, -50%)`;
    }
  }

  try {
    renderGL(dt);
  } catch (err) {
    // 渲染中丢上下文等意外：落到 CSS 兜底，文字内容不受影响
    glState.ok = false;
    document.body.classList.add('no-webgl');
    console.warn('WebGL render failed, falling back:', err);
  }
  firstFrameDone = true;
}
rafId = requestAnimationFrame(frame);

document.addEventListener('visibilitychange', () => {
  if (document.hidden) cancelAnimationFrame(rafId);
  else { last = performance.now(); rafId = requestAnimationFrame(frame); }
});

/* ── resize ───────────────────────────────────────────────── */
let resizeT = 0;
window.addEventListener('resize', () => {
  clearTimeout(resizeT);
  resizeT = setTimeout(() => {
    measureSections();
    smooth.measure();
    if (glState.ok) {
      camera.aspect = innerWidth / innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(innerWidth, innerHeight);
      computeHalfExtents();
      // 词标宽度依赖视口，旋转设备后必须重采样
      if (aT6) {
        aT6.array.set(formText(aT6.count, 'VIBEBRIDGE', textWorldW()));
        aT6.needsUpdate = true;
      }
    }
  }, 120);
});
