# Python API

均从 `crazy_buffer` 导入。除另有说明，输入为 GeoDataFrame，ID 为唯一、非空、同类字符串或整数（不接受 bool 或混合类型）；计算保留业务 ID，CSV 回读带前导零 ID 时指定 `dtype`。计算不修改输入。

| 入口 | 关键签名与返回 |
| --- | --- |
| `read_points_csv` | `(path, *, id_column, x_column, y_column, crs, coordinate_system='declared_crs', report=None)` → 点图层；ID 读为字符串 |
| `read_geopackage` | `(path, *, layer, id_column, coordinate_system='declared_crs', report=None)` → 指定图层 |
| `prepare_layer` | `(frame, *, id_column, analysis_crs, geometry_types, coordinate_system='declared_crs', on_invalid='error', report=None)` → 投影副本 |
| `make_buffers` | `(sources, *, source_id, radius_m, quad_segs=32, report=None)` → ID、radius_m、geometry |
| `neighbors_within` | `(sources, targets, *, source_id, target_id, radius_m, max_matches=1000000, report=None)` → 关系 DataFrame |
| `iter_neighbor_batches` | `(sources, targets, *, source_id, target_id, radius_m, batch_size=256, max_matches=None)` → 关系批次迭代器 |
| `summarize_neighbors` | `(links, *, sources, targets, source_id, target_id, value_column, radius_m=None, report=None)` → 统计 DataFrame |
| `buffer_stats` | `(sources, targets, *, source_id, target_id, radius_m, value_column, batch_size=256, report=None)` → 分批计算统计表 |
| `nearest_distance` | `(sources, targets, *, source_id, target_id, report=None)` → 最近目标表 |
| `export_run` | `(results, output_dir, *, report, spatial=None, input_files=None, input_frames=None, script_path=None, metadata=None)` → 输出目录 Path |

`RunReport()` 保存 steps、issues、metadata；为需要记录的每一步显式传入同一对象。`SpatialInputError` 提供 code 和 issues；失败应处理异常，不能当作零匹配。

准备图层时 `geometry_types` 显式给出，例如 `('Point',)` 或 `('Polygon', 'MultiPolygon')`。默认无效几何报错；`on_invalid='drop'` 必须提供 report，仅排除几何问题，ID/CRS 错误仍报错；不会自动修复几何。计算阶段不会跳过无效行。

源图层支持 Point、Polygon、MultiPolygon，范围查询目标只支持 Point；最近距离两端均只支持 Point。图层必须使用相同、以米计量的投影 CRS；EPSG:3857 不接受。半径须为有限正数。`make_buffers` 的 source_id 不得为保留列名 `radius_m` 或 `geometry`。

关系表列：source_id、target_id、distance_m、radius_m。`summarize_neighbors` 可汇总经过筛选的关系子集，但不是检查空间关系真实性的独立证明；空关系须显式传 radius_m。统计表保留所有源行，列为 source_id、radius_m、n_matches、n_valid_values、mean_value、status。最近目标表列为 source_id、target_id、distance_m、tie_count、status；空目标报错。

导出时 results 必须是普通 DataFrame，spatial 另传 GeoDataFrame。input_files 按安全名称复制文件；input_frames 按名称保存 `inputs/name.gpkg`，所有 GeoPackage 图层名为 `data`；script_path 复制到 `artifacts/script.py`（后缀沿用原文件）。空间快照非活动几何属性不得叫 `fid` 或 `geom`（忽略大小写），避免 GDAL 保留字段吞掉业务属性。清单保存哈希、版本、字段类型及显式记录的参数；CSV 本身不存类型。导出使用临时目录与互斥锁，失败清理临时产物，已有输出不会覆盖。

metadata 与 report.metadata 均为未核验用户声明；清单 `status=success` 指导出成功，`reproducibility=complete` 指声明输入和脚本齐备，不表示自动执行脚本或科学结论已验证。用户需另存依赖锁和外部资源，并核查隐私。
