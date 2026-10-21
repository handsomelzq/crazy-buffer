# 路网最近距离

`build_network(edges, edge_id='id', directed=False)` 创建独立快照；`nearest_network_distance(sources, targets, network, source_id='id', target_id='id', max_snap_distance_m=100)` 返回每个源的最近可达目标。分析 CRS 必须是投影米制，排除 Web Mercator。用户负责预筛步行道路与通行方向；不读取或推断 OSM 标签。

路网要求非空、有效有限二维、简单且正长度 LineString，业务 ID 唯一且统一为整数或字符串。默认只把完全相同坐标的端点连接；内部交叉不建立节点。`from_node`、`to_node` 必须同时提供，节点列统一为整数或字符串；同一节点的端点坐标必须完全一致。显式节点允许相同位置分属不同桥面/层级。平行边与闭合自环均支持。`directed=True` 沿线坐标起点到终点通行，节点列顺序须与坐标顺序一致。

每个点仅吸附最近道路，等距按 `str(edge_id)` 选择。接入点按沿线距离拆分道路，支持同边中间点直接通行和弯曲线累计长度。对于同几何、同端点拓扑的平行/反向道路，接入点共享，因而反向重叠道路能提供其合法方向。显式节点不同的重叠道路保持分离；其他等距道路只选择业务 ID 最小的一条。吸附不代表可跨越路边障碍，也不判断出入口或真实步行权限。

总距离 = 源接入距离 + 路网距离 + 目标接入距离。目标超过阈值排除，等于阈值保留。状态包括 `ok`、`source_too_far`、`no_reachable_target`（全部目标超限）和 `unreachable`。失败结果保留已知源接入距离，其余不可得距离为 NaN，目标为空。目标等距按 `str(target_id)` 决定，`tie_count` 统计引擎严格相等的最小距离目标，不使用近似容差。

路由使用延迟导入的 NetworkX：基础包与建网无需安装 NetworkX，调用路由时才需要。Network 的 edges 应视为只读，不应直接修改；建网时已经复制原始输入。临时图在每次调用中构造，不改变输入或 Network 快照。每个目标执行一次反向 Dijkstra，流式更新各源最小总距离和并列计数，不构造源目标完整矩阵。时间复杂度 O(T·((V+E) log V+S))，路由额外存储 O(V+S)，另含临时图、接入点及吸附几何处理成本。逐源比较实际计算得到的总距离，保留源接入距离相加后产生的浮点严格相等。适合区域尺度内存路网与适量目标，未承诺全城/全国道路规模性能；大量重叠边和大量严格等距目标需先基准测试。

只安装路网可选依赖并运行合成示例：`uv run --extra network python examples/scripts/network_station.py /tmp/network-run`（可将输出目录替换为自选 OUTPUT）。首次运行会同步依赖，不需要安装 GUI。导出目录包含输入三层 GeoPackage、脚本、结果、RunReport 与运行版本；在仓库外执行 `python /tmp/network-run/artifacts/script.py /tmp/network-replay` 可读取保存快照重新计算。输出目录必须不存在且父目录已存在。NetworkX/Streamlit 安装版本会随 export_run 记录，未安装显示 unknown。
