# 贡献指南

请为一种独立资产增加插件，而不是让引擎导入主应用。
新增能力需提供版本化参数模型、简化假设、解析或独立基准数据以及真实 OCCT 测试。
不要把 `shape.Volume()` 的结果复制为预期值再宣称通过独立验算。

```bash
python -m pytest -q
python -m compileall -q src examples/third_party_plugin
python scripts/export_contracts.py --check
```

Ruff 配置已提供；本次环境无法联网安装 Ruff，因此不能宣称本次 lint 已通过。后续可运行 `ruff check .`。
格式变更不得替代几何测试。CI 尚未远程运行时请保持披露，不添加成功徽章。

PR 应写明范围、验证命令、未验证平台，以及 AI 辅助使用情况。不要修改无关模块。
