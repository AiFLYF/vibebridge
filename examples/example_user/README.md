# 示例数据集

这是一个**完全虚构**的用户，模拟了大约 8 周的自然使用。
本仓库不包含任何真实个人数据。

## 如何查看

直接打开 `../demo_report.html`，或者：

```bash
export VIBEBRIDGE_HOME=$(pwd)/examples/example_user
python core/vb.py report --open
```

Windows PowerShell：

```powershell
$env:VIBEBRIDGE_HOME = "$PWD\examples\example_user"
python core\vb.py report --open
```

## 重新生成

```bash
python scripts/build_examples.py
```
