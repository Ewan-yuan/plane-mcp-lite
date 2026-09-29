#!/usr/bin/env python3
"""plane-mcp-lite: zero-dependency stdio MCP server for Plane CE.

A lean replacement for the official plane-mcp-server (28+ tools, ~40k tokens of
schema): 8 tools, ~1.1k tokens. Friendly names (project identifier, state name,
assignee email/name, label names, ISSUE-12 sequence refs) are all resolved
server-side, and responses are compact summaries with a web URL.

Required env:
  PLANE_BASE_URL        your Plane instance, e.g. https://plane.example.com
  PLANE_API_KEY         personal API token (Plane -> avatar -> Settings -> API Tokens)
  PLANE_WORKSPACE_SLUG  workspace slug
"""
import html as html_mod
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("PLANE_BASE_URL", "").rstrip("/")
API_KEY = os.environ.get("PLANE_API_KEY", "")
WS = os.environ.get("PLANE_WORKSPACE_SLUG", "")

PRIORITIES = ["urgent", "high", "medium", "low", "none"]


class PlaneError(Exception):
    pass


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def api(method, path, body=None, params=None):
    if not API_KEY:
        raise PlaneError("PLANE_API_KEY env is not set")
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(3):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("X-API-Key", API_KEY)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:  # Plane built-in rate limit: honor Retry-After
                try:
                    wait = min(float(e.headers.get("Retry-After")), 20)
                except (TypeError, ValueError):
                    wait = 10
                log(f"429 rate limited, retrying in {wait:.0f}s ({method} {path})")
                time.sleep(max(wait, 1))
                continue
            detail = e.read().decode("utf-8", "replace")[:300]
            raise PlaneError(f"Plane API {e.code} {method} {path}: {detail}") from None
        except urllib.error.URLError as e:
            raise PlaneError(f"cannot reach {BASE}: {e.reason}") from None
        return json.loads(raw) if raw.strip() else {}


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</(p|div|li|h[1-6]|tr|blockquote)>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html_mod.unescape(s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def text_to_html(s):
    return "<p>" + html_mod.escape(s).replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"


def clean(d):
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


# ---------- caches / resolvers ----------

_projects = None  # list of raw project dicts


def projects():
    global _projects
    if _projects is None:
        _projects = api("GET", f"/api/v1/workspaces/{WS}/projects/")["results"]
    return _projects


def resolve_project(ref):
    ref = str(ref).strip()
    for p in projects():
        if ref.lower() in (p["id"], p["identifier"].lower(), p["name"].lower()):
            return p
    raise PlaneError(f"project '{ref}' not found; available: " + ", ".join(p["identifier"] for p in projects()))


_states = {}  # project_id -> list of {id,name,group}
_labels = {}  # project_id -> list of raw label dicts
_members = {}  # project_id -> list of member dicts


def states(pid):
    if pid not in _states:
        _states[pid] = api("GET", f"/api/v1/workspaces/{WS}/projects/{pid}/states/")["results"]
    return _states[pid]


def labels(pid):
    if pid not in _labels:
        r = api("GET", f"/api/v1/workspaces/{WS}/projects/{pid}/labels/")
        _labels[pid] = r["results"] if isinstance(r, dict) else r
    return _labels[pid]


def members(pid):
    if pid not in _members:
        r = api("GET", f"/api/v1/workspaces/{WS}/projects/{pid}/members/")
        _members[pid] = r["results"] if isinstance(r, dict) else r
    return _members[pid]


def state_name(pid, sid):
    for s in states(pid):
        if s["id"] == sid:
            return s["name"]
    return sid[:8]


def resolve_state(pid, ref):
    ref = str(ref).strip().lower()
    for s in states(pid):
        if ref in (s["id"], s["name"].lower(), s["group"]):
            return s["id"]
    raise PlaneError(f"state '{ref}' not found; available: " + ", ".join(s["name"] for s in states(pid)))


def resolve_labels(pid, names):
    if isinstance(names, str):
        names = [names]
    out = []
    for n in names:
        n = str(n).strip().lower()
        hit = [l for l in labels(pid) if n in (l["name"].lower(), l.get("id"))]
        if not hit:
            raise PlaneError(f"label '{n}' not found; available: " + ", ".join(l["name"] for l in labels(pid)))
        out.append(hit[0]["id"])
    return out


def label_names(pid, ids):
    m = {l["id"]: l["name"] for l in labels(pid)}
    return [m.get(i, i[:8]) for i in ids or []]


def resolve_assignees(pid, refs):
    if isinstance(refs, str):
        refs = [refs]
    out = []
    for r in refs:
        r = str(r).strip().lower()
        exact = [m for m in members(pid) if r in (m.get("email", "").lower(), m["id"])]
        fuzzy = [m for m in members(pid) if r in (m.get("display_name", "").lower(), f"{m.get('first_name','')} {m.get('last_name','')}".strip().lower())]
        hit = exact or fuzzy
        if not hit:
            raise PlaneError(f"member '{r}' not in project; members: " + ", ".join(m.get("email") or m.get("display_name", "?") for m in members(pid)))
        out.append(hit[0]["id"])
    return out


def member_names(pid, ids):
    m = {x["id"]: (x.get("display_name") or x.get("first_name") or x.get("email", "?")) for x in members(pid)}
    return [m.get(i, i[:8]) for i in ids or []]


UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
SEQ_RE = re.compile(r"^([A-Za-z]+)-(\d+)$")


def resolve_issue(pid, ref):
    """Accept issue uuid or 'IDENT-12' sequence reference."""
    ref = str(ref).strip()
    if UUID_RE.match(ref):
        return ref
    m = SEQ_RE.match(ref)
    if not m:
        raise PlaneError(f"issue ref '{ref}': use the issue uuid or 'IDENT-<seq>' (e.g. ABC-12)")
    seq = int(m.group(2))
    cursor, seen = None, 0
    while True:
        r = api("GET", f"/api/v1/workspaces/{WS}/projects/{pid}/issues/", params={"per_page": 100, "cursor": cursor})
        for i in r["results"]:
            if i["sequence_id"] == seq:
                return i["id"]
        seen += len(r["results"])
        cursor = r.get("next_cursor")
        if not r["results"] or not cursor or seen >= 500:
            raise PlaneError(f"no issue with sequence {seq} in this project")


# ---------- tool implementations ----------

def compact_issue(i, proj):
    pid = proj["id"]
    return clean({
        "id": i["id"],
        "ref": f"{proj['identifier']}-{i.get('sequence_id')}",
        "title": i.get("name"),
        "state": state_name(pid, i.get("state")) if i.get("state") else None,
        "priority": i.get("priority"),
        "assignees": member_names(pid, i.get("assignees")),
        "labels": label_names(pid, i.get("labels")),
        "parent": i.get("parent"),
        "target_date": i.get("target_date"),
        "external_id": i.get("external_id"),
        "updated": (i.get("updated_at") or "")[:10],
        "url": f"{BASE}/{WS}/{proj['identifier']}/work-item/{i['id']}",
    })


def t_projects_list(a):
    return [clean({"identifier": p["identifier"], "id": p["id"], "name": p["name"]}) for p in projects()]


def t_issues_list(a):
    proj = resolve_project(a["project"])
    pid = proj["id"]
    limit = min(int(a.get("limit") or 20), 100)
    params = {"per_page": limit}
    if a.get("state"):
        params["state"] = resolve_state(pid, a["state"])
    if a.get("priority"):
        params["priority"] = a["priority"]
    if a.get("assignee"):
        ids = resolve_assignees(pid, a["assignee"])
        params["assignee"] = ",".join(ids)
    if a.get("search"):
        params["search"] = a["search"]
    r = api("GET", f"/api/v1/workspaces/{WS}/projects/{pid}/issues/", params=params)
    rows = [compact_issue(i, proj) for i in r["results"][:limit]]
    if a.get("label"):  # CE ignores ?label= server-side; filter locally
        want = a["label"].strip().lower()
        rows = [x for x in rows if any(want == l.lower() for l in x.get("labels", []))]
    return {"total": r.get("total_count", len(rows)), "count": len(rows), "issues": rows}


def t_issue_get(a):
    proj = resolve_project(a["project"])
    pid = proj["id"]
    iid = resolve_issue(pid, a["issue"])
    i = api("GET", f"/api/v1/workspaces/{WS}/projects/{pid}/issues/{iid}/")
    out = compact_issue(i, proj)
    out["description"] = strip_html(i.get("description_html"))
    if a.get("comments"):
        out["comments"] = t_comments_list({"project": a["project"], "issue": a["issue"]})  # noqa
    return out


def t_issue_create(a):
    proj = resolve_project(a["project"])
    pid = proj["id"]
    body = {"name": a["title"]}
    if a.get("description"):
        body["description_html"] = text_to_html(a["description"])
    if a.get("state"):
        body["state"] = resolve_state(pid, a["state"])
    if a.get("priority"):
        body["priority"] = a["priority"]
    if a.get("assignees"):
        body["assignees"] = resolve_assignees(pid, a["assignees"])
    if a.get("labels"):
        body["labels"] = resolve_labels(pid, a["labels"])
    if a.get("parent"):
        body["parent"] = resolve_issue(pid, a["parent"])
    if a.get("target_date"):
        body["target_date"] = a["target_date"]
    i = api("POST", f"/api/v1/workspaces/{WS}/projects/{pid}/issues/", body)
    return compact_issue(i, proj)


def t_issue_update(a):
    proj = resolve_project(a["project"])
    pid = proj["id"]
    iid = resolve_issue(pid, a["issue"])
    body = {}
    if "title" in a:
        body["name"] = a["title"]
    if "description" in a:
        body["description_html"] = text_to_html(a["description"]) if a["description"] else ""
    if a.get("state"):
        body["state"] = resolve_state(pid, a["state"])
    if a.get("priority"):
        body["priority"] = a["priority"]
    if a.get("assignees"):
        body["assignees"] = resolve_assignees(pid, a["assignees"])
    if a.get("labels"):
        body["labels"] = resolve_labels(pid, a["labels"])
    if a.get("parent"):
        body["parent"] = resolve_issue(pid, a["parent"])
    if a.get("target_date"):
        body["target_date"] = a["target_date"]
    i = api("PATCH", f"/api/v1/workspaces/{WS}/projects/{pid}/issues/{iid}/", body)
    return compact_issue(i, proj)


def t_issue_delete(a):
    proj = resolve_project(a["project"])
    iid = resolve_issue(proj["id"], a["issue"])
    api("DELETE", f"/api/v1/workspaces/{WS}/projects/{proj['id']}/issues/{iid}/")
    return {"deleted": True, "id": iid}


def t_comments_list(a):
    proj = resolve_project(a["project"])
    pid = proj["id"]
    iid = resolve_issue(pid, a["issue"])
    r = api("GET", f"/api/v1/workspaces/{WS}/projects/{pid}/issues/{iid}/comments/")
    rows = r["results"] if isinstance(r, dict) else r
    name_map = {x["id"]: (x.get("display_name") or x.get("first_name") or x.get("email", "?")) for x in members(pid)}
    out = []
    for c in rows:
        actor = c.get("actor") or c.get("created_by") or ""
        out.append(clean({
            "author": name_map.get(actor, actor[:8] if actor else "?"),
            "created": (c.get("created_at") or "")[:16],
            "text": strip_html(c.get("comment_html")),
        }))
    return out


def t_comment_create(a):
    proj = resolve_project(a["project"])
    pid = proj["id"]
    iid = resolve_issue(pid, a["issue"])
    c = api("POST", f"/api/v1/workspaces/{WS}/projects/{pid}/issues/{iid}/comments/", {"comment_html": text_to_html(a["text"])})
    return {"created": True, "id": c.get("id")}


def _p(desc, **kw):
    kw["description"] = desc
    return kw


PROJECT_PARAM = _p("project identifier (e.g. ABC), name, or uuid", type="string")
ISSUE_PARAM = _p("issue uuid or ref like ABC-12", type="string")

TOOLS = [
    {
        "name": "projects_list",
        "description": "List all Plane projects (identifier, id, name).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "issues_list",
        "description": "List work items in a project, newest first. Filters: state, priority, assignee, label (name), free-text search.",
        "inputSchema": {
            "type": "object",
            "required": ["project"],
            "properties": {
                "project": PROJECT_PARAM,
                "state": _p("Backlog|Todo|In Progress|Done|Cancelled", type="string"),
                "priority": _p("", type="string", enum=PRIORITIES),
                "assignee": _p("email or display name", type="string"),
                "label": _p("label name", type="string"),
                "search": _p("free text", type="string"),
                "limit": _p("max rows, default 20", type="integer"),
            },
        },
    },
    {
        "name": "issue_get",
        "description": "Get one work item: description, metadata, url; optionally comments.",
        "inputSchema": {
            "type": "object",
            "required": ["project", "issue"],
            "properties": {
                "project": PROJECT_PARAM,
                "issue": ISSUE_PARAM,
                "comments": _p("also include comments", type="boolean"),
            },
        },
    },
    {
        "name": "issue_create",
        "description": "Create a work item. state/assignees/labels/parent accept friendly names, resolved automatically.",
        "inputSchema": {
            "type": "object",
            "required": ["project", "title"],
            "properties": {
                "project": PROJECT_PARAM,
                "title": _p("", type="string"),
                "description": _p("plain text / markdown-ish", type="string"),
                "state": _p("", type="string"),
                "priority": _p("", type="string", enum=PRIORITIES),
                "assignees": _p("email or name; string or array", type="array", items={"type": "string"}),
                "labels": _p("label names", type="array", items={"type": "string"}),
                "parent": ISSUE_PARAM,
                "target_date": _p("YYYY-MM-DD", type="string"),
            },
        },
    },
    {
        "name": "issue_update",
        "description": "Update a work item; only provided fields change (title, description, state, priority, assignees, labels, parent, target_date).",
        "inputSchema": {
            "type": "object",
            "required": ["project", "issue"],
            "properties": {
                "project": PROJECT_PARAM,
                "issue": ISSUE_PARAM,
                "title": _p("", type="string"),
                "description": _p("plain text; replaces existing", type="string"),
                "state": _p("", type="string"),
                "priority": _p("", type="string", enum=PRIORITIES),
                "assignees": _p("email or name; replaces existing", type="array", items={"type": "string"}),
                "labels": _p("label names; replaces existing", type="array", items={"type": "string"}),
                "parent": ISSUE_PARAM,
                "target_date": _p("YYYY-MM-DD", type="string"),
            },
        },
    },
    {
        "name": "issue_delete",
        "description": "Permanently delete a work item.",
        "inputSchema": {
            "type": "object",
            "required": ["project", "issue"],
            "properties": {"project": PROJECT_PARAM, "issue": ISSUE_PARAM},
        },
    },
    {
        "name": "comments_list",
        "description": "List comments of a work item.",
        "inputSchema": {
            "type": "object",
            "required": ["project", "issue"],
            "properties": {"project": PROJECT_PARAM, "issue": ISSUE_PARAM},
        },
    },
    {
        "name": "comment_create",
        "description": "Add a comment to a work item (plain text).",
        "inputSchema": {
            "type": "object",
            "required": ["project", "issue", "text"],
            "properties": {"project": PROJECT_PARAM, "issue": ISSUE_PARAM, "text": _p("", type="string")},
        },
    },
]

HANDLERS = {
    "projects_list": t_projects_list,
    "issues_list": t_issues_list,
    "issue_get": t_issue_get,
    "issue_create": t_issue_create,
    "issue_update": t_issue_update,
    "issue_delete": t_issue_delete,
    "comments_list": t_comments_list,
    "comment_create": t_comment_create,
}


def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    missing = [n for n, v in (("PLANE_BASE_URL", BASE), ("PLANE_API_KEY", API_KEY), ("PLANE_WORKSPACE_SLUG", WS)) if not v]
    if missing:
        log("missing required env: " + ", ".join(missing))
        sys.exit(2)
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if "id" not in msg:
            continue
        method, params = msg.get("method"), msg.get("params") or {}
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "plane-mcp-lite", "version": "0.3.0"},
                }
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                name = params.get("name")
                handler = HANDLERS.get(name)
                if not handler:
                    result = {"content": [{"type": "text", "text": f"unknown tool {name}"}], "isError": True}
                else:
                    data = handler(params.get("arguments") or {})
                    result = {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]}
            elif method == "ping":
                result = {}
            else:
                send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": f"unknown method {method}"}})
                continue
            send({"jsonrpc": "2.0", "id": msg["id"], "result": result})
        except PlaneError as e:
            if method == "tools/call":
                send({"jsonrpc": "2.0", "id": msg["id"], "result": {"content": [{"type": "text", "text": str(e)}], "isError": True}})
            else:
                send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32000, "message": str(e)}})
        except Exception as e:  # noqa: BLE001
            log("internal error:", repr(e))
            send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32603, "message": f"internal error: {e}"}})


if __name__ == "__main__":
    main()
