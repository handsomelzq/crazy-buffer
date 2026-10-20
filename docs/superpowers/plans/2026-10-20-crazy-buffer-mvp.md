# Crazy Buffer MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 交付可导入、可组合的 Python 空间计算包，跑通缓冲邻域统计及最近直线距离，并提供质检、复现记录与小型案例。

**Architecture:** GeoDataFrame/DataFrame 作为公开数据接口；空间匹配、聚合和最近查询可独立组合，便捷函数复用同一实现。输入输出与计算分离，RunReport 是显式、可选的记录容器，GUI/CLI 均不进入本轮范围。

**Tech Stack:** Python 3.12、uv、GeoPandas、Shapely、pyproj、pyogrio、pandas；pytest 和 nbformat 仅用于开发检查。

**Spec:** [2026-10-20-crazy-buffer-design.md](../specs/2026-10-20-crazy-buffer-design.md)

**Status:** 2026-10-20 实现完成。121 项测试、离线锁定测试、源码包与 wheel 构建均通过；两个示例已回读。最终独立整项目审查因账户用量限制未能启动，已由控制系统执行本地只读审查并记录证据。

**Initial release:** 首轮成果标记为开发预览版；跨平台 CI 和 QGIS 对照没有实际执行前，不声称已达到跨平台稳定发行标准。

## Global Constraints

- 第一版先跑通底层能力，提供可自由编排的接口；第二版再建设快速操作的 GUI，面向 GIS 和 Python 初学者。
- 第一版采用 Python API + Notebook 案例，不强迫用户理解 JSON 配置或命令行任务协议。
- 函数不修改传入数据、不隐式联网、不隐式写文件，不依赖全局变量或界面状态。
- 第一版不自动选择或推断 CRS。
- 无效几何不静默修复；原文件不修改。
- 可复现承诺是相同输入、处理逻辑和参数得到容差内一致的指标，不承诺跨系统 GeoPackage 文件字节完全相同。
- 本机 8GB 内存；默认串行，不运行用户完整 Notebook pipeline；重任务前运行 `~/bin/memcheck.sh`，不终止其他进程。
- Python 环境仅使用项目 `.venv` 和 uv；依赖安装需先获用户同意，不向系统 Python 安装。
- 当前没有 Git 仓库。本计划审核通过后的执行阶段可初始化本地 Git 并建立开发分支，用于可审查提交；不创建远端、不推送、不发布。若无法写 Git 元数据，保留文件和逐任务审查记录，不冒充已提交。

## Review Focus

1. 非连续/重复 DataFrame index 与字符串前导零 ID：计算以稳定业务 ID 配对，索引不能替代 ID，CSV 不能吞掉前导零。（Task 1/2）
2. 阈值边缘、孔洞、不同投影及英尺单位：精确距离判断，无坐标猜测，不使用近似 buffer 多边形决定匹配。（Task 1/2）
3. 同址不同 ID、无匹配与全部缺失：不随意去重，计数/均值/状态可区分，结果保留全部有效起点。（Task 2/3）
4. 用户自定义关系表中的重复、孤立 ID 与高密度配对：先验证关系完整性；超限报错不截断，不生成全量两两矩阵。（Task 2/3）
5. 内存输入、外部清洗与导出中断：不夸大复现范围，显式保存快照与脚本，失败不留下可误认的完成目录。（Task 5/6）

## 环境核验与依赖计划

2026-10-20 已只读确认：uv 0.12.12，Python 3.12.14；当前 Python 中没有 geopandas、shapely、pyproj、pyogrio、pytest、nbformat。工作区仅有设计文档。

拟在 `pyproject.toml` 设置 Python `>=3.12,<3.13`；直接依赖 `geopandas>=1.0,<2`、`shapely>=2.0,<3`、`pyproj>=3.6,<4`、`pyogrio>=0.9,<1`、`pandas>=2.2,<3`。dev 组包含 `pytest>=8,<10`、`nbformat>=5,<6`；构建后端使用 hatchling。实际解析版本写入 uv.lock 并检验兼容性，版本范围不是已安装事实。

安装前检查内存；获同意后使用项目隔离缓存与环境，例如 `UV_CACHE_DIR=.cache/uv uv sync --python /Users/liuziqiang/.local/bin/python3.12 --group dev`。把 `.venv/`、`.cache/`、运行结果加入忽略文件。任何下载失败都先保留错误证据，不能假装测试已通过。

## 模块与共享契约

| 文件 | 责任 |
| --- | --- |
| `src/crazy_buffer/errors.py` | `SpatialInputError(code, message, issues)`，issues 为 JSON 可序列化列表，包含原对象 ID/字段/原因 |
| `src/crazy_buffer/provenance.py` | `RunReport` 与运行清单构建；不隐式写文件 |
| `src/crazy_buffer/validate.py` | 公开输入契约及关系表校验 |
| `src/crazy_buffer/prepare.py` | 显式投影与可选排除问题要素 |
| `src/crazy_buffer/io.py` | CSV/GPKG 输入；导出在独立 `export.py` 中实现 |
| `src/crazy_buffer/operations/{buffer,neighbors,aggregate,nearest}.py` | 四类可单独调用的空间/统计能力 |
| `src/crazy_buffer/recipes/buffer_stats.py` | 分批复用匹配和聚合逻辑的便捷组合 |
| `src/crazy_buffer/api.py`、`__init__.py` | 显式公开函数，不做动态插件发现 |
| `tests/`、`examples/`、`docs/api.md`、`docs/methods.md` | 正确性证据、两个完整案例、接口和方法说明 |

所有 ID 列必须非空、唯一，单列仅允许全字符串或全整数（排除布尔和混合类型），输出保留原值和类型。并列目标按 `str(target_id)` 的字典序选择，整数 ID 也采用此明示规则；不按输入排序选取。

公共空间操作要求输入 CRS 已知、相同、投影坐标、两轴单位为米；检测到 Web Mercator 或非米单位时拒绝并说明。prepare 由用户指定研究区合适的投影，不能从数据猜出 GCJ-02/BD-09；读取及 prepare 接受坐标制式声明，显式声明为这两者时拒绝直接混算。验证 CRS 只能检查形式条件，不保证其适合研究目的，文档必须说明。

输入几何只允许二维非空有效 Point（目标）、Point/Polygon/MultiPolygon（邻域起点）；Z/M 几何须明确报错，不静默忽略维度。有限数值参数拒绝 bool、NaN、Infinity；半径严格大于零。

`RunReport()` 具有 `steps: list[dict]`、`issues: list[dict]`、`metadata: dict`，以及 `add_step(name, parameters, counts)`。公开函数接受 `report: RunReport | None = None`；无 report 时结果照常返回，但不宣称完整追踪。`on_invalid="drop"` 只用于 prepare，必须传 report；其余公开计算接口严格验证，避免对象悄悄消失。错误携带明细；不捕获成空结果。

统计状态固定：`ok`、`no_matches`、`no_valid_values`。非法起点由 prepare 显式排除并记入报告，不伪装成 `no_matches`。每次操作向 report 记录名称、规范化参数、数量和 CRS，不依赖 DataFrame.attrs 保存必要信息。

## Task 1: 可安装包、数据入口与输入契约

**Files:** Create `pyproject.toml`, `uv.lock`, `.gitignore`, `src/crazy_buffer/{__init__,api,errors,provenance,validate,prepare,io}.py`, `tests/{conftest,test_prepare,test_io}.py`。

**Interfaces:**
- `RunReport()`、`SpatialInputError(code: str, message: str, issues: list[dict])`。
- `read_points_csv(path, *, id_column, x_column, y_column, crs, coordinate_system="declared_crs", report=None) -> GeoDataFrame`，默认将 CSV ID 作为字符串读取，原始缺失字段必须仍被识别为空；其他列正常读取。
- `read_geopackage(path, *, layer, id_column, coordinate_system="declared_crs", report=None) -> GeoDataFrame`。
- `prepare_layer(frame, *, id_column, analysis_crs, geometry_types, coordinate_system="declared_crs", on_invalid="error", report=None) -> GeoDataFrame`；`geometry_types` 为允许类型的 tuple；返回新对象。坐标和投影后结果都检查有限性。
- 内部 `validate_layer(frame, *, id_column, geometry_types, require_metric=False) -> None`，供后续任务复用。

- [x] 写 `test_prepare.py`：无 CRS/重复 ID/混合 ID/英尺分析 CRS/空几何/非法几何/Z 坐标/无穷坐标都抛带 code 的异常；重复 index 不报业务 ID 重复；输入不变；显式 drop 必须带 report 且报告被排除 ID。
- [x] 写 `test_io.py`：临时 CSV 的 ID `001` 保留字符串，空 ID 报错；GPKG 指定图层读回；缺少图层和字段可定位；WGS84 点显式投影后满足米制且原始数据不变；声明 GCJ-02/BD-09 拒绝。

  该 CSV 测试的核心断言：
  ```python
  assert result.loc[0, "id"] == "001"
  assert result.crs.to_epsg() == 4326
  assert (result.geometry.x.iloc[0], result.geometry.y.iloc[0]) == (116.4, 39.9)
  ```
- [x] 安装获准后运行 `uv run --locked pytest tests/test_prepare.py tests/test_io.py -q`，保存预期缺少实现的失败证据，再实现上述接口；不得把依赖失败当成测试证明。
- [x] 最小实现包装、读取、校验、prepare 和 RunReport；输入阶段记录字段/几何/CRS 问题，不自动纠错或联网。
- [x] 重跑上述测试，预期全部通过；确认 `uv run --locked python -c 'import crazy_buffer'` 成功。
- [x] 独立审查本任务 diff、测试证据与公开签名；修正问题后提交本地检查点（若已初始化 Git）。

## Task 2: 缓冲几何与精确邻域关系

**Files:** Create `src/crazy_buffer/operations/{__init__,buffer,neighbors}.py`, `tests/{test_buffer,test_neighbors}.py`; modify `api.py`, `__init__.py`。

**Interfaces:**
- Consumes Task 1 的 validate_layer、RunReport、SpatialInputError。
- `make_buffers(sources, *, source_id, radius_m, quad_segs=32, report=None) -> GeoDataFrame`，保留来源 ID、输出 radius_m 与 buffer geometry、CRS；`quad_segs` 为正整数。
- `neighbors_within(sources, targets, *, source_id, target_id, radius_m, max_matches=1_000_000, report=None) -> DataFrame`；列为 `source_id,target_id,distance_m,radius_m`，空结果也保留列与正确 ID dtype。
- 内部 `iter_neighbor_batches(...)` 每个起点批次产生关系表，供 Task 3 使用；单起点候选用目标索引筛选，再精确距离过滤。匹配上限为最终关系数量，在扩展累计结果前检查。

- [x] 写 `test_neighbors.py`：本地米制坐标加偏移 `(500000,4400000)`，起点 `(0,0)`，目标 `(3,4),(5,0),(5.001,0),(0,0)`，半径 5；恰好匹配前三个中的前两个及重合点，共 3 条，距离分别 5、5、0。

  四个目标 ID 依次为 `a,b,c,d`，该测试断言：
  ```python
  assert set(links["target_id"]) == {"a", "b", "d"}
  assert sorted(links["distance_m"].tolist()) == [0.0, 5.0, 5.0]
  ```
- [x] 加入孔洞案例：外框 `[0,10]²`、洞 `[4,6]²`，点 `(5,5)` 到面距离 1；半径 1 包含、0.5 排除；面内点距离 0；MultiPolygon 两部分都参与。
- [x] 加入重复行 index、同址不同 ID、两个起点都匹配同一目标、空目标、错位 CRS、max_matches=2 时抛 `MATCH_LIMIT_EXCEEDED` 且不返回截断结果。
- [x] 写 `test_buffer.py`：同一半径下返回有效面及原 CRS/ID，面积在离散精度对应容差内接近 πr²；参数被记录，输入不变。统计边界不通过 buffer polygon containment 决定。
- [x] 运行 `uv run --locked pytest tests/test_buffer.py tests/test_neighbors.py -q`，确认测试先因缺少功能失败，再实现索引候选+精确距离与缓冲导出。
- [x] 重跑并通过；独立审查代码与测试证据，确认不存在全量距离矩阵后提交本地检查点。

## Task 3: 属性聚合与 buffer_stats 完整案例

**Files:** Create `src/crazy_buffer/operations/aggregate.py`, `src/crazy_buffer/recipes/{__init__,buffer_stats}.py`, `tests/{test_aggregate,test_buffer_stats}.py`; modify public exports。

**Interfaces:**
- `summarize_neighbors(links, *, sources, targets, source_id, target_id, value_column, radius_m=None, report=None) -> DataFrame`。
- `buffer_stats(sources, targets, *, source_id, target_id, radius_m, value_column, batch_size=256, report=None) -> DataFrame`。
- 输出 `source_id,radius_m,n_matches,n_valid_values,mean_value,status`。非空 links 内半径必须唯一；显式 radius_m 必须一致；空 links 要求传 radius_m；非空 links 含多个尺度时报错。保留 sources 全集及其顺序。
- 关系表中重复 `(source_id,target_id)`、不存在的 ID、负/非有限距离、距离大于半径均报错；用户可删减关系，不能伪造重复记录制造统计偏差。

- [x] 写 `test_aggregate.py`：P1 有 4 个住房匹配，值 `[10000,20000,None,30000]`，预期 n_matches=4、n_valid_values=3、mean=20000、status=ok；P2 无匹配为 0/0/空/no_matches；P3 仅缺失值为 1/0/空/no_valid_values。

  按 source_id 取行后的核心断言：
  ```python
  assert (p1.n_matches, p1.n_valid_values, p1.mean_value, p1.status) == (4, 3, 20000.0, "ok")
  assert (p2.n_matches, p2.n_valid_values, p2.status) == (0, 0, "no_matches")
  assert (p3.n_matches, p3.n_valid_values, p3.status) == (1, 0, "no_valid_values")
  assert pd.isna(p2.mean_value) and pd.isna(p3.mean_value)
  ```
- [x] 检查 null 允许排除；价格文本、bool、Infinity 报错而不是自动强转；值为 0 作为普通有效数值，价格是否应排除 0 由调用者筛选并说明。唯一 ID 不因同址而去重。
- [x] 检查空关系的半径、混合半径、重复关系、孤立 ID 和负距离；用户过滤有效关系后聚合结果按过滤后的记录正确更新。
- [x] 写 `test_buffer_stats.py`：便捷函数与独立 neighbors + summarize 完全对应；batch_size=1 与 256 结果一致；零目标返回完整 source 行及 no_matches；函数不改输入。
- [x] 运行 `uv run --locked pytest tests/test_aggregate.py tests/test_buffer_stats.py -q` 记录失败；实现关系验证与聚合，便捷函数调用同一批次匹配/统计核心，不物化全部起点的配对表。
- [x] 重跑上述测试与 Task 2 受影响测试，预期通过；独立审查后提交本地检查点。此时应已能在内存里跑通第一个研究案例。

## Task 4: 最近直线距离

**Files:** Create `src/crazy_buffer/operations/nearest.py`, `tests/test_nearest.py`; modify public exports。

**Interfaces:**
- `nearest_distance(sources, targets, *, source_id, target_id, report=None) -> DataFrame`，两者均为 Point，使用共同米制投影；返回 `source_id,target_id,distance_m,tie_count,status`。
- 有效源为空时返回固定 schema 空表；目标为空时报 `EMPTY_TARGETS`。使用索引最近查询获取所有精确等距项，再按 str(ID) 稳定选择；相等指当前几何引擎返回的双精度数值严格相等，数值断言容差不得偷偷变成并列判定容差。

- [x] 写测试：源 `(0,0)`，目标 A=`(-3,4)`、B=`(3,4)`，距离 5、tie_count=2、选 A；打乱目标顺序仍选 A。整数 ID `[2,10]` 并列时按明示字典序选 10；结果保留整数类型。

  第一个案例的断言：
  ```python
  assert result.loc[0, "target_id"] == "A"
  assert result.loc[0, "distance_m"] == 5.0
  assert result.loc[0, "tie_count"] == 2
  pd.testing.assert_frame_equal(result, reordered_result)
  ```
- [x] 加入重合点距离 0、空目标异常、非 Point 异常、空源 schema、不同 CRS、输入不变、重复行 index 案例。
- [x] 运行 `uv run --locked pytest tests/test_nearest.py -q`，确认先失败；实现索引查询与稳定并列规则，再运行通过。
- [x] 独立审查测试证据与单位/排序口径，提交本地检查点。

## Task 5: 显式导出与可复现记录

**Files:** Create `src/crazy_buffer/export.py`, `tests/{test_export,test_provenance}.py`; modify `provenance.py`, public exports。

**Interfaces:**
- `export_run(results, output_dir, *, report, spatial=None, input_files=None, input_frames=None, script_path=None, metadata=None) -> Path`；results 为普通指标表，spatial 为可选 GDF；input_files/input_frames 为 name→Path/GDF 映射。
- report 仅记录实际已发生的操作。metadata 包含数据定义、单位、覆盖、时间及用户自定义步骤说明，不能把用户提供的任意 dict 当作库自动验证的事实。
- `run_manifest.json` 包含 `schema_version=1,status="success",reproducibility="complete"|"partial",inputs,script,steps,metadata,versions,outputs`。complete 仅表示执行所需工件已声明并保存，不表示已自动复跑或已验证用户代码；未提供输入快照或脚本为 partial，并列出缺项。
- 内存输入显式快照到 `inputs/<name>.gpkg`；文件输入显式复制到 inputs 下，哈希复制前后核对；script 复制到 artifacts。限制 name 为安全单段文件名，不能目录穿越；结果清单记录数据类型以解释 CSV ID。

- [x] 写 `test_export.py`：指标 CSV、可选 spatial GPKG、quality.json、必要 issues.csv、manifest、输入和脚本副本均能读回；文件哈希匹配，输出目录已存在时报错。
- [x] 注入 GPKG 写入或复制失败，断言最终目录不存在、临时产物被清理、原输入没修改；manifest 不包含自己的哈希。并发导出到同一路径必须有排他保护，不覆盖竞争者结果。

  对写入故障注入的核心断言：
  ```python
  with pytest.raises(OSError):
      export_run(results, output_dir, report=report, spatial=spatial)
  assert not output_dir.exists()
  assert list(output_dir.parent.iterdir()) == original_parent_entries
  ```
- [x] 写 `test_provenance.py`：无脚本/输入为 partial；外部过滤需用户脚本证明，不自动声称已捕获；记录 Python/包/GEOS/GDAL/PROJ 版本，未知版本明确为 unknown；没有 Git 时 git_commit 为 null。
- [x] 运行 `uv run --locked pytest tests/test_export.py tests/test_provenance.py -q` 先失败；实现同一文件系统临时目录写入、完整性验证、受保护发布和异常清理。
- [x] 重跑通过；独立审查失败路径、数据泄漏边界与证据，提交本地检查点。

## Task 6: 两个可运行案例、文档与发布前检查

**Files:** Create `examples/{scripts,notebooks,data}/`, `tests/test_examples.py`, `README.md`, `docs/{api,methods,data-sources}.md`, `LICENSE`, `CONTRIBUTING.md`, `.github/workflows/tests.yml`。

**Interfaces:**
- `examples/scripts/park_prices.py` 与 `nearest_station.py` 使用前述公开 API；`main(output_dir)` 可在测试临时目录执行，脚本不得在 import 时写文件。
- 两份 Notebook 仅组织分析和解释，通过 JSON 写入（ensure_ascii=False, indent=1），没有执行输出；共享示例数据构建逻辑放在 `examples/scripts/sample_data.py`。
- 所有样例均为合成数据。数据说明明确来源、单位、坐标语义、许可和预期答案，不包装为真实北京数据。

- [x] 先写 `test_examples.py`：两个脚本的小型案例可在临时目录执行、核心结果等于手算值、导出可回读；Notebook 仅做 nbformat 校验和 code cell AST（排除 magic 行），不运行完整 Notebook。

  两份脚本采用 Task 3 的 P1 房价与 Task 4 的等距 A/B 作为首个对象，其回读断言：
  ```python
  assert prices.loc[0, "mean_value"] == 20000.0
  assert nearest.loc[0, "target_id"] == "A"
  assert nearest.loc[0, "distance_m"] == 5.0
  assert manifest["status"] == "success"
  ```
- [x] 实现脚本、Notebook、说明文档；README 以 Python API 示例开头，明确 CLI/GUI 未实现，解释输入准备和 report 是可选但完整复现需保存的材料。
- [x] 数据源目录迁入独立文档，并保留许可待核验状态；不得宣称下载器、真实房价或跨平台已验证。代码建议采用 MIT（用户审核本计划时一并确认），合成数据以明确独立许可发布，第三方数据不混入。
- [x] CI 使用 Windows/macOS/Linux 与 Python 3.12、uv lock 执行测试；只写工作流，GitHub 未运行时不得声称云端已通过。
- [x] 运行 `uv run --locked pytest -q`、`uv build`，以及产物安装到临时环境后的 import/合成小例冒烟。依赖已缓存时用离线模式验证计算不联网；没有缓存则如实记录限制。
- [x] 全项目独立审查：与批准设计逐项核对、回读示例导出、核对文档命令与签名；所有影响正确性的发现修复并复测，再提交本地检查点。

## 执行与验收顺序

任务依赖：1 → 2 → 3；4 依赖 1；5 依赖 1/3/4 的稳定结果；6 依赖全部。实现按序执行，避免多 agent 同时改公共 API、依赖和锁文件；无写入冲突的只读方法评审、测试设计审查可并行。

每任务先有具体失败测试，再实现，再验证，再由独立 reviewer 审查；不需要逐任务向用户重复申请继续。阶段性完成不夸大为整个项目已发布。若环境安装或 Git 操作被权限阻止，记录真实状态，保留已完成工作。

本轮最终交付应包含可安装包、两个案例、测试证据、用户文档和已知限制。实时开源数据许可核验、真实北京数据验证、大规模性能基准、第二版 GUI 和路网均不作为本轮完成条件。

## 计划自审

两位只读 reviewer 已分别审阅 API 边界与科学验收。采纳原值 ID、严格等距、空间关系上限和故障注入建议；返回值保持设计要求的 DataFrame，使用显式 RunReport 而非强制 `(table, info)` 元组。排除无效起点只允许发生在显式 prepare 阶段并带报告，计算阶段不跳过对象，避免将失败伪装为零匹配。半径固定大于零；零半径相交查询不在本轮范围。

- [x] 已将 API 优先、少量算子、两个案例与第二版 GUI 边界落实到任务。
- [x] 明确公共签名、ID/CRS/错误约定，以及空关系的 radius_m 传递方式。
- [x] 分步关系表与便捷批次计算共享语义，区别物化结果与分批聚合内存需求。
- [x] 复现记录覆盖内存输入和用户脚本，避免把最终表格误当完整工作流。
- [x] 每个 Review Focus 均对应任务测试；无代码实现或测试通过声明。
- [x] 用户审核实施计划与环境安装范围。
