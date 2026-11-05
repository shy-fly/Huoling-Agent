# 运行时日志与 Project Recorder Agent

## 现状

项目已集成结构化运行时日志与 **Project Recorder Agent**（`app/agents/project_recorder.py`），用于：

1. **锁定问题**：通过 `trace_id` 串联 HTTP → LangGraph → 诊断 → LLM/RAG
2. **记录项目事项**：开发备注、数据口径、运维操作写入审计库

## 日志文件

| 文件 | 内容 |
|------|------|
| `backend/logs/app.log` | 全应用 JSON 行日志（轮转 10MB × 5） |
| `backend/logs/project_journal.jsonl` | Project Recorder 专用日记 |

## 查询方式

```bash
# 最近审计记录
curl http://localhost:8000/v1/logs/audit?limit=20

# 按 trace 查全链路（诊断 API 返回 trace_id）
curl http://localhost:8000/v1/logs/trace/<trace_id>

# 写入项目备注
curl -X POST http://localhost:8000/v1/logs/note \
  -H "X-Admin-Token: ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"message":"记录一次测试说明"}'

# 本地 grep
grep "trace_id" backend/logs/app.log | tail
```

## 自动记录的事件

- 每个 HTTP 请求（路径、状态码、耗时）
- 每次诊断（健康度、等级、故障、耗时）
- LLM 调用与 guardrail 拒绝
- RAG 检索命中数
- 预警创建与确认
- 数据上传与回测
- 应用启动/停止

## Cursor Agent

见根目录 [AGENTS.md](../AGENTS.md)（完整项目上下文：模块、API、前端、ML/RAG、MCP）与 Skill `record_project_note`。

## 安全

- 日志目录已加入 `.gitignore`
- 不记录 `LLM_API_KEY` 与业主原始数据全文
