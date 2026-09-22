/* 对比两张 PNG 的逐像素差，输出可视化 + 差异的空间分布特征。
   用途：collide 报某块"脏"，但截图看不出粒子时，判断差异到底是
     (a) 字形边缘整体变粗  → 栅格化差异，测量有问题
     (b) 零散圆点          → 真的是粒子
   用法：node scripts/diff-viz.js <a.png> <b.png> <x> <y> <w> <h> [out.png] */
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright-core');

const A = process.argv[2], B = process.argv[3];
const X = parseInt(process.argv[4], 10), Y = parseInt(process.argv[5], 10);
const W = parseInt(process.argv[6], 10), H = parseInt(process.argv[7], 10);
const OUT = process.argv[8] || path.join(process.cwd(), '_diag', 'diffviz.png');

(async () => {
  const aB64 = fs.readFileSync(A).toString('base64');
  const bB64 = fs.readFileSync(B).toString('base64');
  const browser = await chromium.launch({ executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', headless: true });
  const page = await browser.newPage();
  await page.goto('about:blank');
  const res = await page.evaluate(async ({ aB64, bB64, X, Y, W, H }) => {
    const load = (s) => new Promise((r, j) => { const i = new Image(); i.onload = () => r(i); i.onerror = j; i.src = 'data:image/png;base64,' + s; });
    const [ia, ib] = await Promise.all([load(aB64), load(bB64)]);
    const get = (im) => {
      const c = document.createElement('canvas'); c.width = im.width; c.height = im.height;
      const x = c.getContext('2d', { willReadFrequently: true }); x.drawImage(im, 0, 0);
      return x.getImageData(0, 0, c.width, c.height).data;
    };
    const da = get(ia), db = get(ib);
    const cw = ia.width, chh = ia.height;

    // 在目标块内统计：差 > 6 的像素占比、最大差、差的空间聚集度
    let n = 0, over6 = 0, over20 = 0, sum = 0, max = 0;
    let minX = 1e9, maxX = -1, minY = 1e9, maxY = -1;
    for (let y = Y; y < Math.min(Y + H, chh); y++) {
      for (let x = X; x < Math.min(X + W, cw); x++) {
        const i = (y * cw + x) * 4;
        const va = (da[i] + da[i + 1] + da[i + 2]) / 3;
        const vb = (db[i] + db[i + 1] + db[i + 2]) / 3;
        const d = Math.max(0, vb - va);   // 变暗幅度，和 collide 口径一致
        n++; sum += d;
        if (d > max) max = d;
        if (d > 6) { over6++; if (x < minX) minX = x; if (x > maxX) maxX = x; if (y < minY) minY = y; if (y > maxY) maxY = y; }
        if (d > 20) over20++;
      }
    }

    // 可视化：把块放大 5 倍，差异 > 6 的像素涂红
    const S = 5, pad = 10;
    const sx = Math.max(0, X - pad), sy = Math.max(0, Y - pad);
    const sw = Math.min(cw - sx, W + pad * 2), sh = Math.min(chh - sy, H + pad * 2);
    const c = document.createElement('canvas');
    c.width = sw * S; c.height = sh * S;
    const x2 = c.getContext('2d');
    x2.imageSmoothingEnabled = false;
    x2.drawImage(ia, sx, sy, sw, sh, 0, 0, c.width, c.height);
    const img = x2.getImageData(0, 0, c.width, c.height);
    for (let y = sy; y < sy + sh; y++) {
      for (let x = sx; x < sx + sw; x++) {
        const i = (y * cw + x) * 4;
        const va = (da[i] + da[i + 1] + da[i + 2]) / 3;
        const vb = (db[i] + db[i + 1] + db[i + 2]) / 3;
        if (Math.max(0, vb - va) <= 6) continue;
        for (let dy = 0; dy < S; dy++) for (let dx = 0; dx < S; dx++) {
          const j = ((y - sy) * S + dy) * (c.width * 4) + ((x - sx) * S + dx) * 4;
          img.data[j] = 255; img.data[j + 1] = 0; img.data[j + 2] = 0; img.data[j + 3] = 255;
        }
      }
    }
    x2.putImageData(img, 0, 0);
    return {
      n, avg: sum / n, max, pctOver6: over6 / n, pctOver20: over20 / n,
      bbox: over6 ? { w: maxX - minX + 1, h: maxY - minY + 1 } : null,
      png: c.toDataURL('image/png').split(',')[1],
    };
  }, { aB64, bB64, X, Y, W, H });

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, Buffer.from(res.png, 'base64'));
  console.log(`\n块 (${X},${Y}) ${W}x${H}  共 ${res.n} px`);
  console.log(`  平均差 ${res.avg.toFixed(2)}/255   最大差 ${res.max.toFixed(0)}`);
  console.log(`  >6 的像素占 ${(res.pctOver6 * 100).toFixed(1)}%   >20 的占 ${(res.pctOver20 * 100).toFixed(1)}%`);
  console.log(`  差异包围盒 ${res.bbox ? res.bbox.w + 'x' + res.bbox.h : '无'}`);
  console.log('  判读：差异像素遍布字形轮廓 → 栅格化差（测量问题）');
  console.log('        差异是孤立小圆点、包围盒远小于块 → 真粒子');
  console.log(`  可视化（差异>6 涂红）→ ${OUT}`);
  await browser.close();
})().catch((e) => { console.error('FAILED:', e); process.exit(1); });
