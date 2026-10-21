# 参与开发

使用 Python 3.12 和 uv：`uv sync --locked --extra gui`，然后 `uv run --locked --extra gui pytest -q`。依赖已缓存时可用 `uv run --offline --locked --extra gui pytest -q` 检查计算不需要下载。构建用 `uv build`；发布前须将 wheel 安装至临时环境并从仓库外验证导入及合成小例。

新增算子先给手算小例和失败测试，保持 ID、CRS、无效几何及空结果契约；避免静默修复和隐式网络调用。记录公开 API 与科学边界变化。Notebook 用 JSON 编辑（ensure_ascii=False, indent=1），保持无执行输出；本项目测试只检查 nbformat/AST，不运行完整 Notebook。

请勿提交真实用户位置、价格数据、运行快照、令牌或未经许可的第三方文件。漏洞或含私人数据的复现材料应先脱敏。代码贡献按 MIT，合成样例数据按 CC0。CI 文件表示计划运行的矩阵，不能替代实际云端结果。
