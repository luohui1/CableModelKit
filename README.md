> **当前交付：Professional Suite 0.3.0 / Core 0.2.1。请先阅读 [START-HERE-0.3.md](START-HERE-0.3.md)。**
> 下文及旧验收文件保留基础版本历史，不能替代本版验证范围。

# CableModelKit — 电缆行业参数化建模插件

**v0.2.0 / 本地研究原型。独立于 CableSimPro；没有主程序 UI、仿真求解器或网络服务。**

输入明确的工程尺寸，输出可追溯的 OCCT B-Rep 几何资产。参数来源与数值检查结果随模型保存；几何有效不等于产品认证。

## 本版交付

9 个内置模板、132 个明确的参数化几何变体；完整批产的独立实体数为 968。全部配方为 `synthetic_demo`，不代表厂家实际规格、额定电压或合格施工设计。新品种覆盖不是靠改名或改材料颜色凑数。

| 模板 | 范围 | 首批变体 |
|---|---|---:|
| `cable.round` | 同心多层圆电缆，简单/屏蔽/等效铠装层 | 12 |
| `cable.multicore` | 2/3/4/5 个等圆线芯、整体填充及共护套 | 24 |
| `installation.cable_group` | 三根独立单芯的品字/水平/竖直排列 | 24 |
| `installation.duct_bank` | 1×1 至 4×4 的选定排管组合、独立管壁 | 12 |
| `installation.tube` | 空心直圆管 | 12 |
| `installation.pipe_bend` | 等壁厚环面弯管；目录样例 30/60/90° | 12 |
| `installation.channel` | 未开孔 U 槽 | 12 |
| `installation.ladder_tray` | 理想化矩形纵梁/横档桥架 | 12 |
| `environment.layered_box` | 尚未切出电缆空腔的分层环境块 | 12 |

另有独立打包的 `asset.tube` 示例插件，验证第三方 entry-point 扩展；不默认加载。

## 轻量边界

核心只有 Pydantic 运行依赖；参数校验/列举模板不加载 CAD。CadQuery/OCCT 为 `occt` 可选依赖，但它们的现成二进制依赖并不小（实测见验收文档）。**所有当前精确建模仍需 OCCT**；不能把“只导出 GLB”宣传为绕过 CAD。

源码、配方、原生运行环境、生成资产分别分发，主软件无需为每个建模插件复制一套 CAD 库。当前没有私自裁剪第三方二进制依赖。

## 使用

声明 Python 3.11–3.13；当前实际验证的是 Linux/Python 3.13.5。建议独立虚拟环境。

```bash
# 只使用契约与参数校验
python -m pip install -e .
cable-modelkit plugins
cable-modelkit validate examples/multicore.json

# 显式启用精确建模
python -m pip install -e ".[occt]"
cable-modelkit build examples/multicore.json --output artifacts/multicore-001

# 批量生产、回读校验与离线目录（审计工具需要 dev 依赖）
python -m pip install -e ".[occt,dev]"
python scripts/build_catalogue.py --output artifacts/foundation
python scripts/make_gallery.py artifacts/foundation

# 中断后只复用并重新审计已有检查点，不覆盖模型
python scripts/build_catalogue.py --output artifacts/foundation --resume

python -m pytest -q
python scripts/export_contracts.py --check
```

`examples/` 中提供现有九类模板的具体输入。根目录输出必须是新目录；恢复模式要求同一配方哈希、家族筛选和引擎版本。

公开协议使用米；CAD 后端/STEP/BRep 使用毫米；GLB 使用米、Y-up。默认局部直线轴为 +Z，不能把局部轴当作重力方向。选择导出格式可在 JSON 中写 `"outputs": ["step"]`，省去 BRep/GLB 导出。

## 插件 API

```python
import json
from pathlib import Path
from cable_modelkit.engine import default_engine

engine = default_engine()
request = json.loads(Path("examples/multicore.json").read_text(encoding="utf-8"))
prepared = engine.prepare(request)          # 仅参数校验；不加载 CAD
result = engine.build(prepared.request)     # 显式建立并检查精确几何
result.export("artifacts/job-001")          # 不覆盖已有目录
```

第三方插件只需 Manifest、Pydantic 参数类型、`build()`，见 `examples/third_party_plugin`。插件是受信任 Python 代码；白名单不是安全沙箱。进程隔离、资源上限、队列、项目 revision 和审核由宿主负责。

## 资产与证据

每个资产默认包含 STEP、逐域 BRep、GLB、规范化输入、材料域/逻辑界面、来源声明、简化假设、几何校验和文件哈希。批产再加入 `exchange-audit.json`，并生成 `catalogue.json` 与离线 `index.html`。

多芯填充模型与三根单芯排列严格区分。导体、屏蔽丝和铠装的等效几何不自动保证热/电磁等效。所有资产保持 `fem_ready=false`、`manufacturing_ready=false`、`standards_compliance=not_assessed`。尚无稳定 CAD 面选择器、共享拓扑、仿真边界或材料物理参数。

STEP/BRep 不保留本 SDK 的完整参数历史，应同时保存 `request.json`。GLB 是显示网格，不是 FEM 网格。详细依据见系统设计中的官方技术文档。

## 文档与验证范围

- [系统设计 v0.2](docs/SYSTEM_DESIGN_V02.md)：职责、单位、来源、质量门槛与后续范围。
- [资产验收契约](docs/ASSET_ACCEPTANCE.md)：每份资产必须通过的检查。
- [本地验收记录](docs/LOCAL_VALIDATION.md)：真实测试、批产、包体和性能数据。
- [机器可读测量](docs/local-validation.json)：原始统计，不是跨设备性能承诺。

没有修改 CableSimPro，没有宣称远程仓库已创建/推送或 GitHub CI 已通过。Windows、macOS、联网干净安装、Ruff 和官方 Khronos validator 尚未验证。此版本由 AI 辅助实现，需维护者评审。许可证由项目所有者决定，见 `LICENSE_STATUS.md`。

## Optional asset review demo

See [`review/README.md`](review/README.md) for a separate, offline, read-only model
review prototype. It adds no dependency to the modeling core and does not change
the 0.2.0 geometry engine. Display dependencies are a local demonstration baseline,
not a production release recommendation.
