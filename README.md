# plane-mcp-lite

[English](#english) | 中文

替代官方 [plane-mcp-server](https://github.com/makeplane/plane-mcp-server) 的精简 MCP 服务，专为 [Plane CE](https://github.com/makeplane/plane) 自托管实例设计：

- **8 个精选工具，schema 仅 ~1.1k token**（官方版 28+ 工具 ≈ 41k，约省 97%）
- **零依赖**：纯 Python 3.8+ 标准库，单文件 `server.py`，无需 pip 安装
- **人话参数**：项目写 `ABC`、issue 写 `ABC-12`、状态写 `Done`、负责人写邮箱，服务端自动解析成 uuid
- **紧凑返回**：状态/标签/负责人翻译成名字，附网页 URL；内置 Plane 限流（429）自动重试

| 工具 | 用途 |
|---|---|
| projects_list | 列全部项目 |
| issues_list | 列 issue（按 state / priority / assignee / label / 全文过滤） |
| issue_get | 详情 + 可选评论 |
| issue_create / issue_update / issue_delete | 增改删 |
| comments_list / comment_create | 评论读写 |

## 一键安装（Claude Code）

macOS / Linux / Git-Bash：

```bash
curl -fsSL https://raw.githubusercontent.com/Ewan-yuan/plane-mcp-lite/main/install.sh | bash
```

Windows PowerShell：

```powershell
irm https://raw.githubusercontent.com/Ewan-yuan/plane-mcp-lite/main/install.ps1 | iex
```

脚本会下载 `server.py` 到 `~/.plane-mcp-lite/`，问你三个问题（实例地址、workspace slug、API token），然后注册到 Claude Code（user scope）。可选再装一个 plane skill（平时 0 token 常驻，聊到 Plane 才加载一份 curl 直连说明书）。

token 在 Plane 网页 → 头像 → Settings → API Tokens 生成，每人自己的。

## 手动接入（任意 MCP 客户端）

三个环境变量：

| 变量 | 说明 |
|---|---|
| `PLANE_BASE_URL` | 实例地址，如 `https://plane.example.com` |
| `PLANE_WORKSPACE_SLUG` | workspace slug |
| `PLANE_API_KEY` | 个人 API token |

**Claude Code**：

```bash
claude mcp add plane-lite --scope user \
  --env PLANE_BASE_URL=https://plane.example.com \
  --env PLANE_WORKSPACE_SLUG=你的slug \
  --env PLANE_API_KEY=plane_api_你的token \
  -- python3 /path/to/server.py
```

**Codex CLI**（`~/.codex/config.toml`）：

```toml
[mcp_servers.plane-lite]
command = "python"
args = ["C:/Users/你/.plane-mcp-lite/server.py"]
env = { PLANE_BASE_URL = "https://plane.example.com", PLANE_WORKSPACE_SLUG = "你的slug", PLANE_API_KEY = "plane_api_你的token" }
```

**OpenCode**（`~/.config/opencode/opencode.json`）：

```json
{
  "mcp": {
    "plane-lite": {
      "type": "local",
      "command": ["python", "/home/你/.plane-mcp-lite/server.py"],
      "environment": {
        "PLANE_BASE_URL": "https://plane.example.com",
        "PLANE_WORKSPACE_SLUG": "你的slug",
        "PLANE_API_KEY": "plane_api_你的token"
      },
      "enabled": true
    }
  }
}
```

验证：`claude mcp list` 显示 `plane-lite ✔ Connected`，然后新开会话说"列出 Plane 项目"。

## 只装 skill（不要 MCP）

```bash
mkdir -p ~/.claude/skills/plane
curl -fsSL https://raw.githubusercontent.com/Ewan-yuan/plane-mcp-lite/main/skill/SKILL.md \
  -o ~/.claude/skills/plane/SKILL.md
```

再在 `~/.claude/settings.json` 的 `env` 段加 `"PLANE_API_KEY": "..."`，新会话提到 Plane 话题自动生效。

## 已知限制（Plane CE 实测）

- issue 列表无 label 服务端过滤（CE 忽略该参数），lite 已做本地过滤兜底
- 评论作者名依赖项目成员表；不在项目里的作者显示短 uuid
- Plane API 有内置限流（`429 RATE_LIMIT_EXCEEDED`，带 `Retry-After`）：lite 自动等待重试，连续多请求时工具调用会慢几秒，属正常

## License

MIT
