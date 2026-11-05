# 接口与数据

运行后查看 /docs 和 /openapi.json 以获取当前 Pydantic 契约。
科研前缀为 /v1/research。

| 路径 | 方法 | 输入重点 |
| --- | --- | --- |
| qa / qa/stream | POST | question、top_k、history |
| compare | POST | question、paperLimit、dimensions、includeIds |
| falsification | POST | hypothesis、sourceId、sourcePage |
| gaps | POST | question、xAxis、yAxis、includeIds、sourcePages |
| experiment-design | POST | question、context、factors、control、replicates |
| media/search | POST | question、kind、number、paperIds |
| knowledge-graph/build | POST | question、paperIds、sourcePages |
| reliability-audit | POST | type、paperId 或 graphId/entityId |
| evolution | POST | question、paperIds 或 graphId/claimId |
| literature/{filename} | GET | collection、page |

媒体详情及 PNG 通过 chunkId/mediaId 查询。图谱支持节点、边、邻接和路径查询。
QA NDJSON 包含 evidence、delta、result 或 error。本地摘录模式只返回 evidence/result。
知识库管理及模型配置由管理员 Token 保护。初始化优先使用 scripts/initialize.py。


compare 可接收 qaContext：question、traceId、evidence[]。
每项 evidence 必须含 chunkId、source、collection、page；由 QA 返回值组成。
服务器从当前数据库生成 paperId 与优先页码，覆盖客户端 includeIds，仍遵守 excludeIds。
旧历史记录若与当前库来源不一致返回 409。返回 qaContext 为经校验并去重后的原证据。
