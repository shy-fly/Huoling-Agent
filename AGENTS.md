# Release candidate note

Current release: backend 126 passed / 1 skipped, six real model cases, 26 desktop/mobile screenshots, and nine real HTTP workflows on a newly initialized 4846-chunk database. User authorized local packaging of 58 demo PDFs. QA-to-Compare handoff is implemented. See docs/release-report.md; all older counts and blockers below are historical.

# fireFairy — 厌氧消化科研问答智能体 · Agent 上下文

面向 Cursor Agent / MCP / Project Recorder 的项目总览。人类读者见 [README.md](README.md)。

## 项目定位

fireFairy（比赛版）是厌氧消化**科研文献问答**智能体：从 58 篇厌氧消化文献中检索证据，由 DeepSeek 生成「研究结论 / 文献证据对照 / 机理与差异解释 / 证据局限」四段结构回答，并给出可追溯的文献引用与 PDF 原文页码定位。

| 能力 | 实现 | 说明 |
|------|------|------|
| **文献检索** | TF-IDF 向量 + 关键词混合 | 3 个文献集合（inhibition / theory / engineering） |
| **科研问答** | LangGraph 编排 + DeepSeek | 四段结构，`answer_mode=model_with_references` |
| **证据定位** | `citations` + `chunks.page` | 前端点击跳转 PDF 原文对应页 |
| **降级** | 本地模板 | 无 API Key 时仍按四段结构给出模板回答 |

版本 `4.0.0`（`firefairy-contest-4.0.0`）；后端 `firefairy`、前端 `firefairy-research-frontend`。

## 目录结构

```
fireFairyContest/
├── backend/app/
│   ├── main.py              # FastAPI 入口（薄路由）
│   ├── config.py            # Settings（pydantic-settings）
│   ├── models/db.py         # KnowledgeChunk（SQLite 单表）
│   ├── graph/               # LangGraph：state / graphs / nodes(explain)
│   ├── rag/                 # ingest / parsers / chunking / vector_index / retriever / literature_extract / sanitize
│   ├── services/            # agent_registry / agent_prompts / project_context / knowledge_admin / llm_runtime
│   ├── llm/                 # provider（DeepSeek）、guardrails
│   ├── prompts/             # registry + system/research_guardrails、tasks/research_qa
│   ├── agents/              # Project Recorder
│   └── observability/       # logging_config / middleware / context
├── frontend/src/
│   ├── App.tsx              # 单页壳
│   ├── api.ts               # API 客户端与类型
│   ├── pages/ResearchQA.tsx # 科研问答
│   └── components/MarkdownBody.tsx
├── knowledge/
│   ├── manifests/sources.yaml
│   └── literature_corpus/{inhibition,theory,engineering}/   # 58 篇 PDF
├── backend/data/
│   ├── agents.yaml + agents/research/prompts/   # agent 注册与 Prompt 覆盖
│   ├── digester.db           # SQLite 知识库（4,846 chunks）
│   └── knowledge/            # TF-IDF 索引 tfidf_index.joblib + meta
└── backend/tests/            # 科研专项测试
```

## 模块分层

- **数据层**：`models/db.py`（KnowledgeChunk）、`rag/ingest`、`rag/parsers`、`rag/chunking`、`rag/literature_extract`
- **检索层**：`rag/vector_index`（TF-IDF）、`rag/retriever`（混合检索）、`rag/sanitize`
- **智能体层**：`services/agent_registry`（只读注册）、`services/agent_prompts`（Prompt 覆盖）
- **编排层**：`graph/graphs`（`build_research_qa_graph`）、`graph/nodes/explain`（科研 QA 节点）
- **LLM 层**：`llm/provider`（DeepSeek provider）、`llm/guardrails`、`services/llm_runtime`（运行态配置）
- **可观测**：`agents/project_recorder`、`observability/*`

`main.py` 保持薄路由，业务逻辑已下沉到 services / rag / graph。

## HTTP API

| 端点 | 说明 |
|------|------|
| `GET /health` | 健康检查、`release`、`use_llm`、`llm_provider` |
| `POST /v1/research/qa/stream` | NDJSON 流式问答，逐段输出正文，最后返回引用与回答元数据 |
| `POST /v1/research/qa` | 科研问答：四段结构 `answer` + `citations` + `chunks` |
| `GET /v1/research/chunks/{chunkId}/visuals` | 按引用分块查询 PDF 页的可靠图表预览 |
| `GET /v1/research/literature/{filename}` | PDF 原文；`page` 参数 → 响应头 `X-PDF-Page` |
| `GET /v1/agents` | 智能体列表（仅 `research`） |
| `GET /v1/agents/{agent_id}` | 智能体详情 |
| `GET /v1/agents/{agent_id}/prompts` | 智能体 Prompt 列表 |
| `GET /v1/knowledge/stats` | chunks 统计 |
| `GET /v1/knowledge/collections` | 可管理集合列表 |
| `GET /v1/knowledge/chunks` | 分块列表（按 collection / 关键词过滤） |
| `GET /v1/knowledge/references` | 文献引用列表 |
| `POST /v1/knowledge/ingest` | 全量入库（admin） |
| `GET /v1/llm/status` | LLM 运行态状态 |
| `PUT /v1/llm/config` | 更新模型、Provider 和启用状态（admin）。凭据和上游地址来自启动配置 |
| `POST /v1/llm/ping` | LLM 连通性测试（admin） |
| `GET /v1/project/context` | 项目上下文（admin 可用 `write=true` 持久化 `project_agent_context.json`） |
| `GET /v1/logs/audit` | 审计日志查询（admin） |
| `GET /v1/logs/trace/{trace_id}` | 按 trace 查全链路（admin） |
| `POST /v1/logs/note` | 写入项目备注（admin） |
| `GET /v1/admin/session` | 管理员会话校验 |

响应头含 `X-Trace-Id`，用于串联日志。管理写操作依赖 `ADMIN_TOKEN`（`X-Admin-Token` 头）。

## 前端

单页科研问答 [ResearchQA.tsx](frontend/src/pages/ResearchQA.tsx)：输入问题 → `POST /v1/research/qa/stream` → 展示四段结构回答 + 可展开的文献引用卡片，点击引用跳转 PDF 原文对应页码。

## 知识库 RAG

- 清单：`knowledge/manifests/sources.yaml`
- 文献：`knowledge/literature_corpus/{inhibition,theory,engineering}/`（58 篇 PDF）
- 分块：4,846（`literature_theory` 2,375 / `literature_engineering` 1,505 / `literature_inhibition` 966）
- 检索：TF-IDF 向量 + 关键词混合（`rag/vector_index.py` / `rag/retriever.py`）
- 索引：`backend/data/knowledge/tfidf_index.joblib` + `tfidf_index.meta.json`

## Prompt 机制（四段结构）

- 覆盖优先级：`backend/data/agents/{agent_id}/prompts/` 优先于 `backend/app/prompts/`
- research 模板：`system/research_guardrails.jinja` + `tasks/research_qa.jinja`
- 四段结构：研究结论 / 文献证据对照 / 机理与差异解释 / 证据局限
- 加载入口：`services/agent_prompts.render_agent_prompt(agent_id, key)`

## 运行与测试

```bash
# 后端（端口 8001，见 .env 的 API_PORT）
cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8001

# 前端（端口 5174，代理 /api → 127.0.0.1:8001）
cd frontend && npm run dev

# 知识全量入库（慢，数分钟）
cd backend && .venv/Scripts/python -m app.rag.ingest  # 或 POST /v1/knowledge/ingest

# 测试
cd backend && .venv/Scripts/python -m pytest tests/ -q   # 49 passed, 1 skipped
```

环境变量（`.env`）：`DEEPSEEK_API_KEY` / `LLM_API_KEY`、`USE_LLM`、`LLM_PROVIDER=deepseek`、`LLM_MODEL=deepseek-flash`、`DATABASE_URL`、`ADMIN_TOKEN`、`API_PORT`、`APP_RELEASE` 等，见 `.env.example`。

## Project Recorder Agent

记录运行时事件、链路与开发备注（`app/agents/project_recorder.py`）。

- **结构化日志**：`backend/logs/app.log`（JSON 行，可 grep）
- **项目日记**：`backend/logs/project_journal.jsonl`
- **数据库审计表**：`audit_logs`（SQLite）
- **trace_id 关联**：HTTP 响应头 `X-Trace-Id`

事件分类 `EventCategory`：`api` · `graph` · `llm` · `rag` · `data` · `system` · `error` · `dev`

记录方式：

```bash
curl -X POST http://localhost:8001/v1/logs/note \
  -H "X-Admin-Token: ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"message":"变更说明","detail":{"version":"4.0.0"}}'
```

开发约定：新增关键路径调用 `recorder.record()` 或 `get_logger()`；**禁止**在日志中写入 API Key 或文献全文；错误必须 `level=error` 并带 `trace_id`。详见 [docs/logging.md](docs/logging.md)。

## 设计原则（Agent 须遵守）

1. **科研定位**：面向全学科科研人员的知识挖掘与证据推理 Agent，当前知识库为厌氧消化文献。
2. **证据可溯**：回答必须带 `citations` 与 `chunks.page`，可跳转 PDF 原文。
3. **四段结构**：研究结论 / 文献证据对照 / 机理与差异解释 / 证据局限。
4. **数据优先读库**：`load_knowledge_base(force_db=True)` 优先读 SQLite。
5. **最小改动**：新功能放入 service / rag / graph 模块，避免加厚 `main.py`。
6. **测试**：改动后跑 `pytest tests/ -q`；新端点补集成测试。

## 当前状态快照（2026-11-03）

- 知识库：4,846 chunks（`literature_theory` 2,375 / `literature_engineering` 1,505 / `literature_inhibition` 966）
- 后端测试：49 passed, 1 skipped
- 前端：暖纸纹理和天蓝色科研工作台，桌面正文与证据双栏，窄屏单栏。TypeScript 检查、Vite 构建及 Chrome 模拟问答通过。

---

*Agent 修改代码后应更新本文件「当前状态快照」或通过 `POST /v1/logs/note` 记录变更。*

## 共享 GitHub 同步规则

- 本项目共享仓库为 `https://github.com/12gch138/fgnb.git`，远程名称使用 `origin`，默认分支为 `main`。
- 只有用户明确认可的功能、修复、界面版本和必要修改日志才允许提交并推送；讨论稿、未验收尝试和临时生成物不得上传。
- 每次准备同步前必须先更新根目录 `开发日志.md`，记录目标、修改文件、验证证据、截图或接口检查以及剩余限制。
- 提交前必须检查分支、远程状态、工作区、暂存区和目标文件差异；在脏工作区中只精确暂存本次获认可的文件，禁止使用 `git add .`、`git add -A` 或把无关历史改动混入提交。
- 代码修改必须完成与风险相称的 Docker 构建、测试、接口检查或截图复查后再推送；未执行的验证要写入日志和提交说明。
- 用户确认认可后，可按上述范围提交并推送到共享仓库；若远程更新、冲突或历史脏改动使边界不清，先停止同步并报告，不得强推、覆盖或重写共享历史。