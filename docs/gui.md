# 本地 GUI

安装项目的 Python 3.12 环境与可选 GUI 依赖后，运行 `uv run --extra gui crazy-buffer-gui`。首次同步需要下载依赖。入口仅监听 `127.0.0.1`，关闭 Streamlit 使用统计；浏览器访问终端所示本机地址。基础 API 导入不需要 Streamlit 或 NetworkX。

依次选择分析、合成示例或上传、字段与 CRS、运行、下载。支持缓冲均值统计、直线最近点距离和估计路网步行距离。示例均为确定性合成坐标，无外部下载，不是真实北京数据；EPSG:32650 只是示例默认投影，实际数据须按研究区指定米制投影。GCJ-02 / BD-09 须事先转换，不能改 CRS 标签替代转换。

CSV 点数据需选择 X/Y 字段、原始 CRS 与唯一 ID；ID 按字符串保留前导零。统计值字段会显式转为数值。GPKG 必须选择图层，沿用其原始 CRS。缓冲源允许 Point、Polygon、MultiPolygon；两个最近距离任务源与目标均为 Point。面内目标距离为零，均值是目标样本等权均值。

道路上传为 GPKG LineString，可选成对起终节点字段；默认双向，单向沿坐标顺序通行。未指定节点时仅完全相同端点连接，线内部交叉不连接。明确节点可区分桥面与地面。最大接入距离限制点与道路的接入；结果不验证围墙、入口和真实通行权限。详见 [路网方法](network.md)。

上限为每文件 20 MB、5000 源、5000 目标、20000 道路。加载按行数有界读取；计算前检查 `目标数 × (源数 + 道路数) <= 2000000` 的路网预算。超限先裁剪研究区或减少目标。此界限仅是内存型试用保护，不承诺城市级吞吐。上传以匿名临时文件处理并清理，不长期保存。修改输入、任务或参数会清除旧结果，需重新运行。

结果可下载 CSV 与 ZIP。ZIP 复用 `export_run`，包含 results.csv、quality.json、run_manifest.json、带 dtype/CRS 的 JSON+WKB 输入快照、完整参数、artifacts/script.py 与根目录 replay.py。JSON 使用严格格式，缺失值为 null。快照仅保留该任务使用的 ID、数值、节点和活动几何字段，其他属性不纳入重放范围；快照可能包含敏感位置，分享前自行脱敏。

将 ZIP 解压到任意目录，在已安装同版本 `crazy-buffer[gui]` 的 Python 环境运行 `python /绝对路径/replay.py`（或 artifacts/script.py）。脚本使用包接口、不启动 Streamlit、不依赖仓库路径，不执行上传代码；输出 replayed.csv 与 replayed-quality.json。保留项目 uv.lock 可帮助恢复依赖。清单中的 complete 只代表输入与脚本齐备，不意味着自动验证科学结论或未来环境兼容。

验证使用合成数据的服务测试、仓库外脚本重放与 Streamlit AppTest；没有执行真实北京数据核对、QGIS 核对或浏览器人工验收。CI 配置了三平台可选 GUI 测试，云端状态以实际运行记录为准。
