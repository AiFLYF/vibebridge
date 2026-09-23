# 示例数据集

这是一个**完全虚构**的用户，模拟了大约 8 周的自然使用。
本仓库不包含任何真实个人数据。

## 如何查看

直接打开 `../demo_report.html`，或者：

```bash
cd skills/vibebridge
export VIBEBRIDGE_HOME=$(pwd)/examples/example_user
python scripts/vb.py report --open
```

Windows PowerShell：

```powershell
cd skills\vibebridge
$env:VIBEBRIDGE_HOME = "$PWD\examples\example_user"
python scripts\vb.py report --open
```

## 重新生成

在仓库根目录执行：

```bash
python tools/build_examples.py
```
