# Third Party Notices

VibeBridge 本身是 MIT 许可（见 [LICENSE](LICENSE)），运行期零第三方依赖。
本文件列出仓库内随附的第三方素材，它们全部只用于 `docs/`（GitHub Pages 展示站点），
**不参与 Skill 运行**，也不会被 `npx skills add` 安装到用户机器上。

## 字体（docs/assets/fonts/，自托管，无 CDN 请求）

| 文件 | 字体 | 来源 | 许可 |
|---|---|---|---|
| `cd500.woff2` `cd600.woff2` `cd700.woff2` | Clash Display | Fontshare（Indian Type Foundry） | Fontshare License — 免费用于商业用途 |
| `sm4.woff2` `sm7.woff2` | Space Mono | Google Fonts | SIL Open Font License 1.1 |
| `is-it.woff2` `is-rg.woff2` | Instrument Serif | Google Fonts | SIL Open Font License 1.1 |

字体由 `tools/fetch_fonts.py` 下载其 latin 子集后本地化，仓库因此完全离线可用。
如需替换或重新下载，运行该脚本即可重新生成 `docs/assets/fonts/` 与 `docs/assets/css/fonts.css`。

## JavaScript（docs/assets/vendor/）

| 文件 | 项目 | 许可 |
|---|---|---|
| `three.module.min.js` | three.js r170（Three.js Authors） | MIT |

## 说明

上述许可信息依据各上游项目在文件头或官方页面中的声明整理。若上游变更许可条款，
以上游官方声明为准。字体与 three.js 的版权归各自作者所有。
