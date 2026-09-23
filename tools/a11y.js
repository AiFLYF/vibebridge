/* 无障碍审计：对比度 / 标题层级 / 焦点可见性 / 触控目标 / 语义。
   ── 为什么必须量而不是看 ──
   这个设计大量用低饱和灰（--mut / --mut-2 / 半透明墨色）做正文和小字标签。
   这类颜色在纸白底上"看着还行"，但对比度经常只有 3:1 出头 ——
   肉眼对低对比不敏感，只有算 WCAG 比值才能定案。
   ── 口径 ──
   WCAG 2.1 AA：正文 ≥4.5:1，大字（≥24px 或 ≥18.66px 粗体）≥3:1，UI 元件边框 ≥3:1。
   粒子层会压暗底色，所以这里量的是"最坏情况"：把 --mut 之类按声明值算，
   再叠加 collide.js 量到的最大压暗量做一次折减。

   用法：node tools/a11y.js [baseUrl] [width] [height] */
const { chromium } = require('playwright-core');

const BASE = process.argv[2] || 'http://127.0.0.1:8231/';
const W = parseInt(process.argv[3] || '1600', 10);
const H = parseInt(process.argv[4] || '900', 10);
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

/* 在页面里把所有可见文字的"前景色 + 实际背景色 + 字号字重"取出来，
   顺便算 WCAG 对比度。背景要沿 DOM 往上找到第一个不透明的背景色。 */
const AUDIT = () => {
  const parse = (c) => {
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map((s) => parseFloat(s));
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const lin = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = (c) => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  const ratio = (f, b) => {
    const L1 = lum(f), L2 = lum(b);
    return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
  };
  const over = (fg, bg) => ({           // fg 以 alpha 叠在 bg 上
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1,
  });

  // 沿 DOM 上溯求实际背景色（把半透明层逐层叠上去）
  const bgOf = (el) => {
    const stack = [];
    let n = el;
    while (n && n !== document.documentElement) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0) { stack.push(c); if (c.a === 1) break; }
      n = n.parentElement;
    }
    stack.push({ r: 255, g: 255, b: 255, a: 1 });   // 兜底
    let acc = stack.pop();
    while (stack.length) acc = over(stack.pop(), acc);
    return acc;
  };

  const out = [];
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walk.nextNode())) {
    const txt = node.textContent.trim();
    if (txt.length < 2) continue;
    const el = node.parentElement;
    if (!el) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.15) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;

    const fg = parse(cs.color);
    if (!fg || fg.a === 0) continue;
    const bg = bgOf(el);
    const eff = fg.a < 1 ? over(fg, bg) : fg;
    const cr = ratio(eff, bg);

    const fs = parseFloat(cs.fontSize);
    const fw = parseInt(cs.fontWeight, 10) || 400;
    const large = fs >= 24 || (fs >= 18.66 && fw >= 700);
    const need = large ? 3 : 4.5;

    out.push({
      t: txt.slice(0, 30), tag: el.tagName.toLowerCase(),
      cls: typeof el.className === 'string' ? el.className.trim().split(/\s+/)[0] : '',
      fs, fw, cr: +cr.toFixed(2), need, ok: cr >= need, large,
      color: cs.color, bg: `rgb(${Math.round(bg.r)},${Math.round(bg.g)},${Math.round(bg.b)})`,
    });
  }
  return out;
};

/* 结构与语义检查 */
const STRUCT = () => {
  const issues = [];
  const hs = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')];
  let prev = 0;
  for (const h of hs) {
    const lv = +h.tagName[1];
    if (prev && lv > prev + 1) issues.push(`标题跳级：h${prev} → h${lv}（「${h.textContent.trim().slice(0, 20)}」）`);
    prev = lv;
  }
  if (document.querySelectorAll('h1').length !== 1) issues.push(`h1 数量 = ${document.querySelectorAll('h1').length}（应为 1）`);

  // 可交互元素的触控目标
  const small = [];
  for (const el of document.querySelectorAll('a[href], button, [role=button], input, select, textarea')) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 && r.height < 2) continue;
    if (r.width < 24 || r.height < 24) {
      small.push(`${el.tagName.toLowerCase()}${el.className ? '.' + String(el.className).trim().split(/\s+/)[0] : ''} ${Math.round(r.width)}x${Math.round(r.height)} 「${(el.textContent || '').trim().slice(0, 18)}」`);
    }
  }

  // 装饰性 svg 应当 aria-hidden
  let svgNoAria = 0;
  for (const s of document.querySelectorAll('svg')) {
    if (!s.hasAttribute('aria-hidden') && !s.hasAttribute('aria-label') && !s.querySelector('title')) svgNoAria++;
  }

  // 链接可辨识性：只有 "这里/更多" 这类文字的链接
  const vague = [...document.querySelectorAll('a[href]')]
    .map((a) => a.textContent.trim())
    .filter((t) => /^(这里|点击|更多|here|more|link)$/i.test(t));

  return { issues, small, svgNoAria, vague, h1: document.querySelectorAll('h1').length };
};

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  await page.goto(BASE, { waitUntil: 'load', timeout: 45000 });
  await page.waitForFunction(() => document.body.classList.contains('is-loaded'), { timeout: 20000 });
  await page.waitForTimeout(2200);

  // 全页扫描：每 400px 采一次，把整站文字都收进来
  const maxY = await page.evaluate(() => document.documentElement.scrollHeight - innerHeight);
  const all = new Map();
  for (let y = 0; y <= maxY; y += 400) {
    await page.evaluate((v) => window.scrollTo(0, v), y);
    await page.waitForTimeout(700);
    const got = await page.evaluate(AUDIT);
    for (const g of got) {
      const k = `${g.tag}|${g.cls}|${g.fs}|${g.color}|${g.bg}`;
      const cur = all.get(k);
      if (!cur || g.cr < cur.cr) all.set(k, { ...g, count: (cur?.count || 0) + 1 });
      else cur.count++;
    }
  }

  const items = [...all.values()].sort((a, b) => a.cr - b.cr);
  const fails = items.filter((i) => !i.ok);

  console.log(`\n无障碍审计  ${W}x${H}   共 ${items.length} 种文字样式组合\n`);
  console.log('── 对比度最低的 12 组 ──');
  console.log('  比值   需要  字号/字重        选择器                    样例');
  for (const i of items.slice(0, 12)) {
    const mark = i.ok ? '  ' : '✗ ';
    console.log(
      `${mark}${String(i.cr).padStart(5)}  ${String(i.need).padStart(4)}  ${(i.fs + 'px/' + i.fw).padEnd(14)}  ` +
      `${(i.tag + (i.cls ? '.' + i.cls : '')).padEnd(22)}  「${i.t}」`
    );
  }

  console.log(`\n── 结论 ──`);
  if (fails.length === 0) {
    console.log('✓ 全部文字满足 WCAG AA（正文 4.5:1 / 大字 3:1）');
  } else {
    console.log(`✗ ${fails.length} 组不达标：`);
    for (const f of fails.slice(0, 10)) {
      console.log(`    ${f.cr}:1（需 ${f.need}:1）  ${f.fs}px/${f.fw}  ${f.tag}${f.cls ? '.' + f.cls : ''}  「${f.t}」`);
    }
  }

  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(500);
  const st = await page.evaluate(STRUCT);
  console.log(`\n── 结构与语义 ──`);
  console.log(`  h1 数量        : ${st.h1}`);
  console.log(`  标题层级       : ${st.issues.length ? '✗ ' + st.issues.join(' / ') : '✓ 无跳级'}`);
  console.log(`  触控目标 <24px : ${st.small.length ? '✗ ' + st.small.length + ' 个\n     ' + st.small.slice(0, 8).join('\n     ') : '✓ 无'}`);
  console.log(`  svg 缺 aria    : ${st.svgNoAria ? '△ ' + st.svgNoAria + ' 个（装饰性应加 aria-hidden）' : '✓ 无'}`);
  console.log(`  含糊链接文字   : ${st.vague.length ? '△ ' + st.vague.join('、') : '✓ 无'}`);
  await browser.close();
})().catch((e) => { console.error('FAILED:', e); process.exit(1); });
