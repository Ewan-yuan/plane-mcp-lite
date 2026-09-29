---
name: plane
description: 管理 Plane 工作项/议题：查询、创建、更新 issue 与评论、列项目。当用户提到 Plane、issue、议题、工作项、issue 编号（如 ABC-12）或在 Plane 里建/改/查任务时使用。
---

# Plane REST API 直连手册

用 curl 直接调 Plane CE 的 REST API，不需要 MCP。依赖三个环境变量（与
plane-mcp-lite 共用）：

- `PLANE_BASE_URL`：实例地址，如 `https://plane.example.com`
- `PLANE_WORKSPACE_SLUG`：workspace slug
- `PLANE_API_KEY`：个人 token（Plane 网页 → 头像 → Settings → API Tokens 生成）

认证头是 `X-API-Key`（**不是** Bearer）。环境变量没设时，用实际值替换，或先
向用户要 token 并 `export`。

先设一个复用变量：

```bash
B="$PLANE_BASE_URL/api/v1/workspaces/$PLANE_WORKSPACE_SLUG"
```

## 端点速查（Plane CE 实测）

| 用途 | 方法与路径 |
|---|---|
| 项目列表 | GET `$B/projects/` |
| issue 列表 | GET `$B/projects/{pid}/issues/?per_page=50` |
| issue 详情 | GET `$B/projects/{pid}/issues/{iid}/` |
| 建 issue | POST `$B/projects/{pid}/issues/` |
| 改 issue | PATCH `$B/projects/{pid}/issues/{iid}/` |
| 删 issue | DELETE `$B/projects/{pid}/issues/{iid}/` |
| 评论列表 | GET `$B/projects/{pid}/issues/{iid}/comments/` |
| 发评论 | POST 同上路径，body `{"comment_html": "<p>…</p>"}` |
| 状态列表 | GET `$B/projects/{pid}/states/` |
| 标签列表 | GET `$B/projects/{pid}/labels/` |
| 成员列表 | GET `$B/projects/{pid}/members/` |

issue 列表可用查询参数：`state=<状态uuid>`、`priority=urgent|high|medium|low|none`、
`assignee=<成员uuid>`、`search=<全文>`、`per_page=`（max 100）。**`label=` 参数会被
CE 静默忽略**——按标签筛要取回后本地过滤 `labels` 字段。翻页：响应里有
`next_cursor`（形如 `1000:1:0`），原样传 `?cursor=<该值>` 取下一页。

路径里的 `{pid}` `{iid}` 都是 **uuid**（不是序号）。人类口径的 `ABC-12` 要先列
issue，按 `sequence_id` 字段匹配出 uuid。

## curl 模板

```bash
# 列项目（拿 identifier 和 pid）
curl -s -H "X-API-Key: $PLANE_API_KEY" "$B/projects/" \
  | python -c "import json,sys; [print(p['identifier'], p['id'], p['name']) for p in json.load(sys.stdin)['results']]"

# 列某项目 issue（紧凑输出）
curl -s -H "X-API-Key: $PLANE_API_KEY" "$B/projects/$PID/issues/?per_page=50" \
  | python -c "import json,sys; [print(i['sequence_id'], i['id'][:8], i['priority'], i['name']) for i in json.load(sys.stdin)['results']]"

# 建 issue（state/labels/assignees 必须传 uuid，先查 states/ labels/ members/ 端点）
curl -s -X POST -H "X-API-Key: $PLANE_API_KEY" -H "Content-Type: application/json" \
  -d '{"name":"标题","description_html":"<p>正文</p>","priority":"high","state":"<uuid>"}' \
  "$B/projects/$PID/issues/"

# 改 issue（只传要改的字段）
curl -s -X PATCH -H "X-API-Key: $PLANE_API_KEY" -H "Content-Type: application/json" \
  -d '{"state":"<新状态uuid>"}' \
  "$B/projects/$PID/issues/$IID/"

# 发评论
curl -s -X POST -H "X-API-Key: $PLANE_API_KEY" -H "Content-Type: application/json" \
  -d '{"comment_html":"<p>评论内容</p>"}' \
  "$B/projects/$PID/issues/$IID/comments/"
```

## 数据形状与坑（都是实测踩过的）

1. **分页信封**：projects/issues/states/labels/comments 都返回
   `{"results":[…],"total_count":N,"next_cursor":"…"}`；**members 是裸数组**。
2. issue 的标题字段叫 `name`；正文是 `description_html`，读取时去标签：
   `python -c "import json,re,html,sys; h=json.load(sys.stdin)['description_html']; print(html.unescape(re.sub(r'<[^>]+>','',h)))"`
   （多行内容再补 `<br>`→`\n` 替换）。
3. state/label/assignee 在 issue 对象里都是 **uuid**，展示给人看之前先查
   states/labels/members 端点做映射；反过来创建/更新时也要把名字换成 uuid。
   - states 条目：`{id, name, group}`；labels 条目：`{id, name, …}`。
   - members 是**裸数组**，条目 `{id, email, display_name, first_name}`；按
     `email` 或 `display_name` 找到 `id`。
4. 评论对象的字段：正文 `comment_html`（去标签同上）、作者 `actor`（**成员
   uuid**，用 members 映射成人名）、时间 `created_at`（ISO 格式）、自身 `id`。
5. 状态组固定五档：Backlog / Todo / In Progress / Done / Cancelled。
6. **项目名（name）禁止 `-` 和 `.`**（报错信息会说 special characters，有误导，
   实际只禁这两个）；issue 标题和评论不受限。
7. issue 引用方式：uuid 精确；人类口径是 `{identifier}-{sequence_id}`（如
   ABC-12），按 sequence_id 在列表里匹配。
8. 网页 URL 规则：`{PLANE_BASE_URL}/{workspace}/{identifier}/work-item/{uuid}`。
9. **Plane API 有内置限流**：连续快速请求会回 `429` + JSON
   `{"error_code":5900,"error_message":"RATE_LIMIT_EXCEEDED"}`，响应头带
   `Retry-After`（秒数，一般 ≤10）。遇到就 `sleep` 该秒数后**原样重发同一条
   curl** 即可成功。要点：请求一律串行、别并发刷；要看 Retry-After 就加 `-i`
   头（`curl -s -i ... | head -5`）。
