/* 每屏「真实字形」占位图。
   关键：块级元素盒子是全宽，但字形只占一部分。用 Range.getClientRects()
   量文本节点的真实墨迹范围，才能找出真正的空白区。
   用法：node scripts/occupancy.js [baseUrl] [width] [height] */
const { chromium } = require('playwright-core');

const BASE = process.argv[2] || 'http://localhost:8231/';
const W = parseInt(process.argv[3] || '1600', 10);
const H = parseInt(process.argv[4] || '900', 10);
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

const SECTIONS = ['s0', 's1', 's2', 's3', 's4', 's5', 's6'];
const COLS = 48, ROWS = 20;

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  await page.goto(BASE, { waitUntil: 'load', timeout: 45000 });
  await page.waitForFunction(() => document.body.classList.contains('is-loaded'), { timeout: 20000 });

  for (const id of SECTIONS) {
    const top = await page.evaluate((i) => document.getElementById(i).offsetTop, id);
    await page.evaluate((y) => window.scrollTo(0, y), top);
    await page.waitForTimeout(700);

    const rects = await page.evaluate((secId) => {
      const sec = document.getElementById(secId);
      const out = [];

      // 1) 文本节点 → Range 真实墨迹
      const walk = document.createTreeWalker(sec, NodeFilter.SHOW_TEXT);
      let n;
      while ((n = walk.nextNode())) {
        if (!n.textContent.trim()) continue;
        const p = n.parentElement;
        if (!p || p.closest('.marquee')) continue;          // 跑马灯是装饰带
        const cs = getComputedStyle(p);
        if (cs.display === 'none' || cs.visibility === 'hidden') continue;
        const rg = document.createRange();
        rg.selectNodeContents(n);
        for (const r of rg.getClientRects()) {
          if (r.width < 1 || r.height < 1) continue;
          if (r.bottom < 0 || r.top > innerHeight) continue;
          out.push({ k: 'text', x: r.left, y: r.top, w: r.width, h: r.height });
        }
      }

      // 2) 有可见背景/边框的块（面板、代码块、按钮）→ 盒子就是墨迹
      sec.querySelectorAll('.panel, .code, .btn, .stack-row, .insight, .flow span, .split-path, .marquee').forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.width < 2 || r.height < 2) return;
        if (r.bottom < 0 || r.top > innerHeight) return;
        out.push({ k: 'box', x: r.left, y: r.top, w: r.width, h: r.height });
      });
      return out;
    }, id);

    const grid = Array.from({ length: ROWS }, () => Array(COLS).fill(0));
    for (const b of rects) {
      const c0 = Math.max(0, Math.floor((b.x / W) * COLS));
      const c1 = Math.min(COLS - 1, Math.ceil(((b.x + b.w) / W) * COLS) - 1);
      const r0 = Math.max(0, Math.floor((b.y / H) * ROWS));
      const r1 = Math.min(ROWS - 1, Math.ceil(((b.y + b.h) / H) * ROWS) - 1);
      for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) grid[r][c]++;
    }

    console.log(`\n══ ${id}  真实墨迹占位（${rects.length} 个 rect）══`);
    console.log('    ' + '0123456789'.repeat(4) + '8'.repeat(0) + '   ← 0=左 4=中 9=右');
    for (let r = 0; r < ROWS; r++) {
      let line = '';
      for (let c = 0; c < COLS; c++) {
        const v = grid[r][c];
        line += v === 0 ? ' ' : v <= 1 ? '░' : v <= 4 ? '▒' : '█';
      }
      console.log(`  ${String(Math.round((r / ROWS) * 100)).padStart(2)}% ${line}`);
    }

    // 找「最大空白矩形」——按行扫描出连续空白段，再合并成带状区
    const bands = [];
    for (let r = 0; r < ROWS; r++) {
      let cur = 0, at = 0, best = 0, bestAt = 0;
      for (let c = 0; c < COLS; c++) {
        if (grid[r][c] === 0) { cur++; if (cur > best) { best = cur; bestAt = c - cur + 1; } } else cur = 0;
      }
      bands.push(best >= 5 ? { r, x0: bestAt, w: best } : null);
    }
    // 合并相邻行的相似空白段
    const merged = [];
    for (const b of bands) {
      if (!b) continue;
      const last = merged[merged.length - 1];
      if (last && b.r === last.r1 + 1 && Math.abs(b.x0 - last.x0) <= 3 && Math.abs(b.w - last.w) <= 6) {
        last.r1 = b.r; last.w = Math.min(last.w, b.w); last.x0 = Math.max(last.x0, b.x0);
      } else merged.push({ r0: b.r, r1: b.r, x0: b.x0, w: b.w });
    }
    console.log('  ── 可用空白区（≥5格宽）──');
    for (const m of merged) {
      if (m.r1 - m.r0 < 1) continue;
      const px = (v, tot) => Math.round((v / tot) * 100);
      console.log(`     y ${px(m.r0, ROWS)}%–${px(m.r1 + 1, ROWS)}%  ·  x ${px(m.x0, COLS)}%–${px(m.x0 + m.w, COLS)}%   ≈ ${Math.round((m.w / COLS) * W)}×${Math.round(((m.r1 - m.r0 + 1) / ROWS) * H)}px`);
    }
  }

  await browser.close();
})().catch((e) => { console.error('FAILED:', e); process.exit(1); });
