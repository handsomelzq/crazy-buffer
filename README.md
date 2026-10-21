# crazy-buffer

```python
import geopandas as gpd
from shapely.geometry import Point
from crazy_buffer import buffer_stats

# 合成米制平面，不代表真实地点
parks = gpd.GeoDataFrame({'id': ['P1']}, geometry=[Point(0, 0)], crs='EPSG:32650')
homes = gpd.GeoDataFrame({'id': ['H1', 'H2'], 'price': [10000., 30000.]},
                         geometry=[Point(0, 0), Point(3, 4)], crs=parks.crs)
result = buffer_stats(parks, homes, source_id='id', target_id='id',
                      radius_m=5, value_column='price')
assert result.loc[0, 'mean_value'] == 20000.0
```

面向 Python 3.12 的小型空间分析库：缓冲区、范围内点关系与均值、点到点最近距离。提供可组合 Python API 和可选本地 GUI；支持直线距离与估计路网距离，不作因果推断。

安装和运行（先安装 uv；首次同步需要下载依赖）：

```sh
uv sync --locked
uv run --locked python examples/scripts/park_prices.py park-run
uv run --locked python examples/scripts/nearest_station.py station-run
uv run --locked pytest -q
```

输出目录的父目录须存在、目标目录须不存在。两个例子均只用 CC0 合成数据，不下载外部资料。首例 P1 均价为 20000 元/平方米；次例 001 最近站为 A、距离 5 米、等距数为 2。Notebook 位于 examples/notebooks，仅通过结构和代码语法检查，未预执行。Notebook 运行时须选择安装本项目的 Python 3.12 内核。

用户应准备有唯一业务 ID、明确 CRS 的 GeoDataFrame，或用 `read_points_csv` / `read_geopackage` 读取。原始经纬度需经 `prepare_layer` 显式投影；请按区域选择投影，不能将 GCJ-02/BD-09 坐标直接声明为 WGS84。当前不支持转换这些偏移坐标。

`report=RunReport()` 对计算可选；需要记录步骤时，将同一 report 传给每一步。完整复现材料还需保存原始输入或内存快照、分析脚本及环境依赖，`export_run` 不会自动发现工作流。它产生 results.csv、可选 results.gpkg、quality.json、有问题时的 issues.csv，以及 run_manifest.json。清单的 `complete` 只表示声明的输入和脚本已保存，并不保证脚本已验证、依赖完整或未来环境可重放。示例已单独测试导出脚本在仓库外读取快照重算：

```sh
uv run --locked python park-run/artifacts/script.py park-replay
```

输入快照可能包含原始个人信息和位置，分享整个运行目录前请脱敏并核查授权。本库不上传数据；仓库合成数据不含真实用户信息。

详见 [API](docs/api.md)、[方法边界](docs/methods.md)、[数据来源](docs/data-sources.md)、[合成数据说明](examples/data/README.md)。代码使用 [MIT](LICENSE)；合成数据另用 [CC0](examples/data/LICENSE)。第三方数据不随包分发。CI 已编写 Windows/macOS/Linux Python 3.12 测试矩阵；是否通过以实际 GitHub 运行记录为准。

本地 GUI：`uv run --extra gui crazy-buffer-gui`，浏览器访问终端显示的 `127.0.0.1` 地址。包含三个确定性合成示例、CSV/GPKG 上传、结果 CSV 与可重放 ZIP。详见 [GUI 使用说明](docs/gui.md) 和 [路网方法](docs/network.md)。
