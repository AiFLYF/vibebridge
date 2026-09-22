/* 降级路径验收：file:// 静态兜底、prefers-reduced-motion、no-WebGL。
   用法：node scripts/shoot-fallback.js [baseUrl] [outDir] */
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright-core');

const BASE = process.argv[2] || 'http://localhost:8231/';
const OUT = process.argv[3] || '_shots_fallback';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const FILE_URL = 'file:///' + path.resolve(__dirname, '..', 'docs', 'index.html').replace(/\\/g, '/');

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  let fails = 0;

  // ── 1. reduced motion ─────────────────────────────────────
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', (e) => errs.push(String(e)));
    await page.goto(BASE, { waitUntil: 'load', timeout: 45000 });
    await page.waitForTimeout(1200);
    const r = await page.evaluate(() => {
      const pre = document.getElementById('preloader');
      const hidden = [...document.querySelectorAll('[data-reveal]')]
        .filter((el) => getComputedStyle(el).opacity === '0').length;
      return {
        preloader: getComputedStyle(pre).display,
        revealHidden: hidden,
        heroVisible: getComputedStyle(document.querySelector('.line-a > span')).transform,
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      };
    });
    console.log('── reduced-motion ──');
    console.log('  preloader       :', r.preloader, r.preloader === 'none' ? 'OK' : '← 应隐藏');
    console.log('  未显现的 reveal :', r.revealHidden, r.revealHidden === 0 ? 'OK' : '← 应全部可见');
    console.log('  hero transform  :', r.heroVisible, r.heroVisible === 'none' ? 'OK' : '← 应无位移');
    console.log('  横向溢出        :', r.overflow);
    if (r.preloader !== 'none' || r.revealHidden !== 0) fails++;
    console.log('  pageerror       :', errs.length ? errs.join('; ') : '无');
    await page.screenshot({ path: path.join(OUT, 'reduced-motion.png') });
    await ctx.close();
  }

  // ── 2. file:// 静态兜底 ────────────────────────────────────
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', (e) => errs.push(String(e)));
    await page.goto(FILE_URL, { waitUntil: 'load', timeout: 45000 });
    await page.waitForTimeout(1500);
    const r = await page.evaluate(() => ({
      htmlClass: document.documentElement.className,
      noteShown: getComputedStyle(document.querySelector('.file-note')).display,
      heroOpacity: getComputedStyle(document.querySelector('.line-a > span')).opacity,
      titleVisible: document.querySelector('.hero-title').getBoundingClientRect().height > 40,
      bodyText: document.body.innerText.length,
    }));
    console.log('\n── file:// 兜底 ──');
    console.log('  html class   :', r.htmlClass, /is-file/.test(r.htmlClass) ? 'OK' : '← 应含 is-file');
    console.log('  提示条       :', r.noteShown, r.noteShown !== 'none' ? 'OK' : '← 应显示');
    console.log('  hero 透明度  :', r.heroOpacity, r.heroOpacity === '1' ? 'OK（内容没被藏起来）' : '← 内容被藏了');
    console.log('  可见正文字数 :', r.bodyText);
    if (!/is-file/.test(r.htmlClass) || r.heroOpacity !== '1') fails++;
    console.log('  pageerror    :', errs.length ? errs.slice(0, 2).join('; ') : '无（CORS 拦截属预期）');
    await page.screenshot({ path: path.join(OUT, 'file-protocol.png') });
    await ctx.close();
  }

  // ── 3. 禁 WebGL ───────────────────────────────────────────
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await ctx.addInitScript(() => {
      const orig = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (t, ...a) {
        if (String(t).includes('webgl')) return null;
        return orig.call(this, t, ...a);
      };
    });
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', (e) => errs.push(String(e)));
    await page.goto(BASE, { waitUntil: 'load', timeout: 45000 });
    await page.waitForTimeout(2000);
    const r = await page.evaluate(() => ({
      noWebgl: document.body.classList.contains('no-webgl'),
      loaded: document.body.classList.contains('is-loaded'),
      bg: getComputedStyle(document.body).backgroundImage.slice(0, 40),
    }));
    console.log('\n── no-WebGL ──');
    console.log('  body.no-webgl :', r.noWebgl, r.noWebgl ? 'OK' : '← 应降级');
    console.log('  preloader 收起:', r.loaded, r.loaded ? 'OK（页面没卡住）' : '← 卡住了');
    console.log('  CSS 兜底背景  :', r.bg || '(无)');
    console.log('  pageerror     :', errs.length ? errs.join('; ') : '无');
    if (!r.noWebgl || !r.loaded) fails++;
    await page.screenshot({ path: path.join(OUT, 'no-webgl.png') });
    await ctx.close();
  }

  await browser.close();
  console.log(fails ? `\n${fails} 项不通过` : '\n全部通过');
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error('FAILED:', e); process.exit(1); });
