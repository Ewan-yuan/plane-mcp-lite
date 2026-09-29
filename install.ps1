# plane-mcp-lite one-click installer (Windows PowerShell)
$ErrorActionPreference = "Stop"

$RepoRaw = "https://raw.githubusercontent.com/Ewan-yuan/plane-mcp-lite/main"
$Dest = "$HOME\.plane-mcp-lite"

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { throw "未找到 claude CLI，请先安装 Claude Code" }
$Py = Get-Command python -ErrorAction SilentlyContinue
if (-not $Py) { $Py = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $Py) { throw "需要 Python 3.8+（python.org 安装后重试）" }

New-Item -ItemType Directory -Force -Path $Dest | Out-Null
try {
    Invoke-WebRequest -Uri "$RepoRaw/server.py" -OutFile "$Dest\server.py" -UseBasicParsing
} catch { throw "下载 server.py 失败: $_" }

Write-Host "plane-mcp-lite 安装（3 个问题，token 见 Plane 网页 → 头像 → Settings → API Tokens）"
$BaseUrl = Read-Host "Plane 实例地址（如 https://plane.example.com）"
$Ws = Read-Host "Workspace slug"
$Token = Read-Host "Plane API Token"

claude mcp remove plane-lite --scope user 2>$null
if ($LASTEXITCODE -ne 0) { }
claude mcp add plane-lite --scope user `
  --env "PLANE_BASE_URL=$BaseUrl" `
  --env "PLANE_WORKSPACE_SLUG=$Ws" `
  --env "PLANE_API_KEY=$Token" `
  -- $Py.Source "$Dest\server.py"

Write-Host "MCP 注册完成（claude mcp list 可验证）"

$Ans = Read-Host "也安装 plane skill 吗？（可选，平时 0 token 常驻）[y/N]"
if ($Ans -eq "y" -or $Ans -eq "Y") {
    New-Item -ItemType Directory -Force -Path "$HOME\.claude\skills\plane" | Out-Null
    Invoke-WebRequest -Uri "$RepoRaw/skill/SKILL.md" -OutFile "$HOME\.claude\skills\plane\SKILL.md" -UseBasicParsing
    Write-Host "skill 已装到 ~/.claude/skills/plane/；需在 ~/.claude/settings.json 的 env 段加 PLANE_API_KEY"
}

Write-Host "完成。新开会话说「列出 Plane 项目」验收。"
