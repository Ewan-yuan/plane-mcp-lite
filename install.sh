#!/usr/bin/env bash
# plane-mcp-lite one-click installer (macOS / Linux / Git-Bash)
set -euo pipefail

REPO_RAW="https://raw.githubusercontent.com/Ewan-yuan/plane-mcp-lite/main"
DEST="$HOME/.plane-mcp-lite"

command -v claude >/dev/null 2>&1 || { echo "未找到 claude CLI，请先安装 Claude Code"; exit 1; }
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
else echo "需要 Python 3.8+（python3.org 安装后重试）"; exit 1; fi

mkdir -p "$DEST"
curl -fsSL "$REPO_RAW/server.py" -o "$DEST/server.py" || { echo "下载 server.py 失败"; exit 1; }

echo "plane-mcp-lite 安装（3 个问题，token 见 Plane 网页 → 头像 → Settings → API Tokens）"
read -r -p "Plane 实例地址（如 https://plane.example.com）: " BASE_URL < /dev/tty
read -r -p "Workspace slug: " WS < /dev/tty
read -r -s -p "Plane API Token（输入不回显）: " TOKEN < /dev/tty
echo

claude mcp remove plane-lite --scope user >/dev/null 2>&1 || true
claude mcp add plane-lite --scope user \
  --env "PLANE_BASE_URL=$BASE_URL" \
  --env "PLANE_WORKSPACE_SLUG=$WS" \
  --env "PLANE_API_KEY=$TOKEN" \
  -- "$PY" "$DEST/server.py"

echo "✔ MCP 注册完成（claude mcp list 可验证）"

read -r -p "也安装 plane skill 吗？（可选，平时 0 token 常驻，聊到 Plane 才加载说明书）[y/N] " ANS < /dev/tty
if [ "${ANS:-n}" = "y" ] || [ "${ANS:-n}" = "Y" ]; then
  mkdir -p "$HOME/.claude/skills/plane"
  curl -fsSL "$REPO_RAW/skill/SKILL.md" -o "$HOME/.claude/skills/plane/SKILL.md"
  echo "✔ skill 已装到 ~/.claude/skills/plane/"
  echo "  skill 走 curl 直连，需在 ~/.claude/settings.json 的 \"env\" 段加：\"PLANE_API_KEY\": \"<你的token>\""
fi

echo "完成。新开会话说「列出 Plane 项目」验收。"
