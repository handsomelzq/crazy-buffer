# 数据来源与许可边界

核验日期：2026-10-20。以下仅核验官方页面；未下载数据、未验证具体图层完整性或真实房价。本项目不提供下载器，不分发第三方数据。实际使用前须再次核验具体数据集、版本、署名及服务政策。

| 来源 | 已核验页面信息 | 未完成核验与用途边界 |
| --- | --- | --- |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) | 数据 ODbL，须署名和注明许可，派生数据库分发受对应共享要求约束 | API、瓦片服务政策另行核查；公园/站点完整性未验收 |
| [Geofabrik 北京](https://download.geofabrik.de/asia/china/beijing.html) | 有北京独立 PBF、Shapefile zip、GeoPackage zip 及历史快照入口 | 未读取图层；预提取 GPKG 不保证全部 OSM 标签，不等于公园入口数据已可用 |
| [WorldPop](https://hub.worldpop.org/) | 人口计数、密度等目录，页脚 CC BY 4.0 | 未选中国具体年份/产品；每像元人数不能直接当每平方公里密度 |
| [GHSL 下载](https://human-settlement.emergency.copernicus.eu/download.php) / [引用说明](https://human-settlement.emergency.copernicus.eu/GHSLhowToCite.php) | CC BY 4.0，按年份、分辨率、CRS 选择，须引用发行版文献和具体产品 | 未选产品和读取栅格；当前库不做栅格分析 |
| [ESA WorldCover](https://esa-worldcover.org/en/data-access) | 2020 v100、2021 v200，CC BY 4.0；10m map、3×3 度 COG 瓦片及公开 S3 获取方式 | 两年含算法差异，不能直接当真实土地变化；本库不做栅格分析 |
| [北京市公共数据开放平台](https://data.beijing.gov.cn/) | 候选目录入口；本轮抓取超时 | 具体数据集和许可仍待核验，不能称为已授权来源 |

北京逐点房价尚无本轮核实、允许公开再分发的来源；使用合成数据或用户自备且有权处理的数据。商业地图 API 不等于开源数据库，其缓存、再分发和坐标限制需单独核查。

分类 POI 与现状用地均可从用户自备数据导入。OSM/Geofabrik 可用于道路、部分设施和土地利用/土地覆盖标签，但其标签不等于统一的科研分类体系，中国不同地区完整度差异较大。政府开放数据、规划现状图和统计年鉴往往更接近研究口径，但仍须逐数据集核查年份、空间粒度、分类标准、访问权限和再分发许可。项目的分类字段只负责统计，不自动把商业 POI 类别解释为规划用地分类。

仓库样例全由 sample_data.py 构造，独立使用 CC0，说明见 examples/data/README.md。用户数据不应提交到仓库；导出目录会复制输入和脚本，分享前检查精确位置、个人信息、密钥及许可。
