# 话术知识库

教练点评与求助提示会检索这里的优秀话术（RAG）。

- 每个 `.md` 文件开头可写 front matter：`title`、`tags`、`scenarios`（适用场景 ID，留空表示通用）。
- 按 `## 二级标题` 切分为知识片段。
- **只能放虚构或已脱敏的内容**，真实材料先放 `data/private/` 脱敏后再整理进来。
- 修改后执行 `uv run python -m app.cli ingest-knowledge`（在 backend 目录下）重新入库。
