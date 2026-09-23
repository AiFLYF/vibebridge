/* 从 PNG 里裁一块放大存出来（用浏览器解码，零图像库依赖）。
   用途：collide 报某块文字"脏"但整屏截图看不出来时，裁到 1:1 甚至放大看清。
   用法：node tools/crop.js <in.png> <x> <y> <w> <h> [out.png] [scale] */
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright-core');

const IN = process.argv[2];
const X = parseInt(process.argv[3], 10), Y = parseInt(process.argv[4], 10);
const W = parseInt(process.argv[5], 10), H = parseInt(process.argv[6], 10);
const OUT = process.argv[7] || path.join(process.cwd(), '_diag', 'crop.png');
const SCALE = parseInt(process.argv[8] || '4', 10);

(async () => {
  const b64 = fs.readFileSync(IN).toString('base64');
  const browser = await chromium.launch({ executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', headless: true });
  const page = await browser.newPage();
  await page.goto('about:blank');
  const outB64 = await page.evaluate(async ({ b64, X, Y, W, H, SCALE }) => {
    const im = await new Promise((res, rej) => {
      const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = 'data:image/png;base64,' + b64;
    });
    const pad = 14;   // 多裁一圈，方便看边界
    const sx = Math.max(0, X - pad), sy = Math.max(0, Y - pad);
    const sw = Math.min(im.width - sx, W + pad * 2), sh = Math.min(im.height - sy, H + pad * 2);
    const c = document.createElement('canvas');
    c.width = sw * SCALE; c.height = sh * SCALE;
    const x = c.getContext('2d');
    x.imageSmoothingEnabled = false;
    x.fillStyle = '#ff0000';
    x.fillRect(0, 0, c.width, c.height);
    x.drawImage(im, sx, sy, sw, sh, 0, 0, c.width, c.height);
    // 用红框标出被量到的那一块本身
    x.strokeStyle = '#ff0000';
    x.lineWidth = Math.max(2, SCALE / 2);
    x.strokeRect((X - sx) * SCALE, (Y - sy) * SCALE, W * SCALE, H * SCALE);
    return c.toDataURL('image/png').split(',')[1];
  }, { b64, X, Y, W, H, SCALE });
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, Buffer.from(outB64, 'base64'));
  console.log(`裁剪 ${W}x${H} @(${X},${Y}) ×${SCALE} → ${OUT}`);
  await browser.close();
})().catch((e) => { console.error('FAILED:', e); process.exit(1); });
