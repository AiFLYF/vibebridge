/* 无依赖 PNG 统计：解码截图，算平均亮度 / 墨点覆盖率 / 主色。
   用来在"看不见图"的时候客观验收配色是否成立。
   用法：node tools/png-stats.js [--dark] <file.png> [file2.png ...]
   --dark：暗色主题口径 —— "墨点"= 亮像素 lum>0.55（发光内容），"纸面"= 暗底 lum<0.14。
   默认（纸白口径）：墨点 lum<0.45，纸面 lum>0.86。 */
const fs = require('fs');
const zlib = require('zlib');

const DARK = process.argv.includes('--dark');
const files = process.argv.slice(2).filter((a) => a !== '--dark');

function decodePNG(buf) {
  let pos = 8;
  let w = 0, h = 0, bitDepth = 0, colorType = 0;
  const idat = [];
  while (pos < buf.length) {
    const len = buf.readUInt32BE(pos);
    const type = buf.toString('ascii', pos + 4, pos + 8);
    const data = buf.slice(pos + 8, pos + 8 + len);
    if (type === 'IHDR') {
      w = data.readUInt32BE(0);
      h = data.readUInt32BE(4);
      bitDepth = data[8];
      colorType = data[9];
    } else if (type === 'IDAT') {
      idat.push(data);
    } else if (type === 'IEND') break;
    pos += 12 + len;
  }
  if (bitDepth !== 8) throw new Error('only 8-bit PNG supported, got ' + bitDepth);
  const channels = { 0: 1, 2: 3, 4: 2, 6: 4 }[colorType];
  if (!channels) throw new Error('unsupported colorType ' + colorType);

  const raw = zlib.inflateSync(Buffer.concat(idat));
  const stride = w * channels;
  const out = Buffer.alloc(h * stride);
  let p = 0;
  for (let y = 0; y < h; y++) {
    const filter = raw[p++];
    const row = y * stride;
    const prev = row - stride;
    for (let x = 0; x < stride; x++) {
      const a = x >= channels ? out[row + x - channels] : 0;
      const b = y > 0 ? out[prev + x] : 0;
      const c = x >= channels && y > 0 ? out[prev + x - channels] : 0;
      let v = raw[p++];
      switch (filter) {
        case 0: break;
        case 1: v = (v + a) & 255; break;
        case 2: v = (v + b) & 255; break;
        case 3: v = (v + ((a + b) >> 1)) & 255; break;
        case 4: {
          const pa = Math.abs(b - c), pb = Math.abs(a - c), pc = Math.abs(a + b - 2 * c);
          const pr = pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
          v = (v + pr) & 255;
          break;
        }
        default: throw new Error('bad filter ' + filter);
      }
      out[row + x] = v;
    }
  }
  return { w, h, channels, data: out };
}

for (const file of files) {
  const { w, h, channels, data } = decodePNG(fs.readFileSync(file));
  let sum = 0, n = 0, ink = 0, paper = 0;
  const hist = new Map();
  for (let y = 0; y < h; y += 2) {
    for (let x = 0; x < w; x += 2) {
      const i = (y * w + x) * channels;
      const r = data[i], g = data[i + 1], b = data[i + 2];
      const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
      sum += lum; n++;
      if (DARK) {
        if (lum > 0.55) ink++;
        if (lum < 0.14) paper++;
      } else {
        if (lum < 0.45) ink++;
        if (lum > 0.86) paper++;
      }
      const key = `${r >> 4},${g >> 4},${b >> 4}`;
      hist.set(key, (hist.get(key) || 0) + 1);
    }
  }
  const top = [...hist.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3)
    .map(([k, v]) => `${k} ${(100 * v / n).toFixed(0)}%`);
  console.log(
    `${file.split(/[\\/]/).pop().padEnd(16)} 亮度 ${(sum / n).toFixed(2)}` +
    `  ${DARK ? '亮点' : '墨点'} ${(100 * ink / n).toFixed(1)}%  ${DARK ? '暗底' : '纸面'} ${(100 * paper / n).toFixed(1)}%  主色 ${top.join(' | ')}`
  );
}
