# 路网与本地 GUI 实施计划

日期：2026-10-21。用户已授权继续路网计算与轻量 GUI，取消用量停止限制；跳过真实北京与 QGIS 核对。

## Global Constraints

- 保留现有 Python API 行为；新路网 API 可自由编排。GUI 是同一 API 的薄层。
- 所有计算使用相同局部米制投影；拒绝经纬度、英尺和 Web Mercator。坐标偏移不自动转换。
- 本地数据，不隐式联网下载；新增依赖放在项目 uv .venv。network/gui 为可选依赖，基础安装仍可使用原功能。
- 路网值称为“估计路网步行距离”。接入段是几何近似，不验证障碍、步行权限或真实通行条件。
- 道路已经筛选为可走且有正确拓扑：仅相同显式节点或完全重合端点相连，不自动连接内部交叉或跨层道路。
- 最近道路接入后拆边，计算接入距离 + 路网长度 + 目标离网距离；按总距离选目标。不可达、超出吸附阈值不写为零。
- 本次只做小型合成测试、GUI 冒烟、导出重放与构建；不下载北京数据、不跑用户 Notebook 重计算、不发布 GitHub。
- 内存 Warn：安装、测试串行；实现任务顺序推进，可并行进行只读审查。

## Task 1: 路网计算 API

Ownership: src/crazy_buffer/network.py（必要时可拆 network/ 包）, api.py, __init__.py, io.py, provenance.py, tests/test_network.py, docs/network.md, examples/scripts/network_station.py。不修改 GUI 或已有算法行为。

实现 `build_network(edges, *, edge_id, from_node=None, to_node=None, directed=False, report=None)` 与 `nearest_network_distance(sources, targets, network, *, source_id, target_id, max_snap_distance_m=100.0, report=None)`，公开 Network 数据对象。

- edges 为非空有效有限 2D LineString 米制 GeoDataFrame，唯一同类型业务 ID，正长度、简单线。可选节点列必须成对指定，ID 合法且同一节点的端点位置完全一致；无节点列以完全相同端点坐标建拓扑。支持平行边、自环；内部交叉不自动相连。
- directed=False 表示全部双向；True 按线坐标起点到终点单向。显式节点顺序同线方向。不推断 OSM 标签；用户须预筛步行道路并明确方向。
- sources/targets 为 Point，CRS 同路网。仅对各点的最近道路吸附，等距边按 str(edge_id) 选最小。同一道路多个接入点按沿线位置拆分，不绕路到端点、不修改输入网络；平行与反向同几何边必须避免选择某一边导致方向路由错误（解释并测试策略）。
- 最大接入距离非负有限数字，含边界；拒绝 bool。目标超限被排除并记录报告；所有目标超限产生 no_reachable_target，源超限 source_too_far，拓扑不连通 unreachable。空目标集报错，空源返回完整列结构。
- 输出 source_id,target_id,source_access_m,network_distance_m,target_access_m,total_distance_m,tie_count,status；不可得数值为 NaN，目标为空；等距总距离按 str(target_id) 决定，tie_count 为严格相等候选数。
- 使用 NetworkX，依赖延迟导入；不要构造源目标完整矩阵。通过带目标接入代价的反向最短路或其他有界方法计算，明确复杂度与支持规模。
- 保留现有验证与 RunReport 习惯，记录阈值、方向、连通规则、排除目标数；runtime_versions 增加安装时的 networkx/streamlit 版本。
- read_geopackage 可读 LineString，其他验证保持一致。新增合成可复现演示脚本，可调用现有 export_run 保存 sources/targets/edges 与脚本，仓库外可重放。
- 测试已知长度、接入/离网距离、同边中间点、弯曲道路、断开组件、单向正反向、平行边与反向几何、显式跨层节点、交叉不连接、并列最近、阈值边界、输入不变、无效输入、零源、全目标超限。

## Task 2: 本地轻量 GUI

Ownership: src/crazy_buffer/gui/（app.py, service.py, __init__.py, launcher.py 可合理划分）, tests/test_gui*.py, docs/gui.md, README.md, pyproject.toml 入口, .github/workflows/tests.yml。

- Streamlit 本地浏览器 GUI，`crazy-buffer-gui` 启动入口，默认只监听 127.0.0.1，禁用使用统计。支持 `uv run --extra gui crazy-buffer-gui`；基础包 import 不依赖 streamlit/networkx。
- 缓冲统计的源对象支持 Point/Polygon/MultiPolygon（包括公园 AOI）；最近距离两种任务的源对象为 Point。GUI 导出复用 export_run 清单与哈希规范，允许把输入另存为带 dtype/CRS 的严格 JSON+WKB 快照。
- 中文标签，按步骤选择分析 → 使用合成示例/上传数据 → 字段与 CRS → 运行 → 查看与下载。三个任务：缓冲均值统计、直线最近点距离、估计路网步行距离。
- 内置确定性合成示例，无外部下载。上传 CSV 点文件或 GPKG（明确选择图层），自动列出字段供选择；CSV 指定 x/y 和原始 CRS；GPKG 使用其原始 CRS。道路为 GPKG LineString，显式节点列可选，默认双向并解释拓扑规则。
- 显式分析 CRS，默认 EPSG:32650 仅用于示例；北京示例文字不暗示全球通用。显示坐标偏移、道路拓扑、样本均值口径的必要提示。
- 参数：半径、统计值列、最大接入距离、方向；可预览输入行数/CRS与结果表。点击运行后调用公共 API，错误显示可理解原因和质检信息；修改输入或参数时不显示旧结果为新结果。
- 提供 CSV 下载和可复现 ZIP（结果、quality、manifest、输入快照、生成的可运行 replay.py/保存 script.py）；保存完整参数和 dtype。重放脚本使用包接口，读取快照，不依赖原绝对路径或 GUI，不执行任意上传代码。
- 上传仅临时本地文件，匿名化文件名，不长期落盘；文件和行数明确限制避免新手耗尽内存。可做最多 20MB/文件、5000源、5000目标、20000边，说明内存型试用范围，不承诺城市级吞吐。
- 路网逐目标反向 Dijkstra 时，GUI 在计算前另限制 `目标数 × (源数 + 道路数)` 不超过 2000000；超限提示先按研究区裁剪/减少目标。Python API 无此 GUI 预算限制，复杂度写入方法说明。
- 小型 Streamlit AppTest 覆盖三个 demo、异常输入/阈值、修改参数清除旧结果；服务测试覆盖 CSV 首零 ID、GPKG 图层选择、ZIP 内容、导出脚本仓库外重放、上传限制。
- 更新文档、启动说明、方法限制和 CI 可选依赖测试配置。不得声称浏览器人工测试、真实数据核对或跨平台 CI 已执行。

## Task 3: 集成验收与独立审查

全套 pytest、uv pip check、uv build；示例脚本与下载脚本仓库外重放。审查 Task 1/2 的接口、科学含义、输入与错误边界、可复现性。修复实质问题后再做定向验证。保留实际验证结果与未验证范围。
