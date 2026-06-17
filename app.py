import html as html_lib

import bs4
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="Scraping Debugger", layout="wide")

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}

# ── Session state defaults ────────────────────────────────────────────────────
for key, default in {
    "html_source": "",
    "soup": None,
    "parser_used": "",
    "base_url": "",
    "nav_levels": [],
    "_lid_counter": 0,
    "explore": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ── Core helpers ──────────────────────────────────────────────────────────────
def parse_html(raw: str):
    try:
        soup = BeautifulSoup(raw, "lxml")
        return soup, "lxml"
    except Exception:
        return BeautifulSoup(raw, "html.parser"), "html.parser"


def resolve_url(src: str, base: str) -> str:
    if src.startswith(("http://", "https://", "data:")):
        return src
    return (base.rstrip("/") + "/" + src.lstrip("/")) if base else ""


def is_image_url(url: str) -> bool:
    from urllib.parse import urlparse
    return any(urlparse(url).path.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)


def normalize_result(result):
    if result is None:
        return None, "none"
    if isinstance(result, (bs4.ResultSet, list)):
        return list(result), "list"
    if isinstance(result, bs4.Tag):
        return [result], "list"
    if isinstance(result, (bs4.NavigableString, str)):
        return str(result), "string"
    return str(result), "string"


def _collapsed_tag_label(tag: bs4.Tag, count: int, max_len: int = 42) -> str:
    parts = [f"<{tag.name}"]
    for k, v in (tag.attrs or {}).items():
        val = " ".join(v) if isinstance(v, list) else str(v)
        parts.append(f' {k}="{val}"')
    opening = "".join(parts) + ">"
    if len(opening) > max_len:
        opening = opening[:max_len] + "…>"
    return opening + (f"  ×{count}" if count > 1 else "")


# ── DevTools tree renderer ────────────────────────────────────────────────────
def _node_to_html(node, depth: int = 0) -> str:
    if isinstance(node, bs4.NavigableString):
        text = str(node).strip()
        if not text:
            return ""
        escaped = html_lib.escape(text[:500])
        suffix = "…" if len(str(node).strip()) > 500 else ""
        return f'<span class="text-node">{escaped}{suffix}</span>'

    if not isinstance(node, bs4.Tag):
        return ""

    attrs_parts = []
    for k, v in (node.attrs or {}).items():
        val = " ".join(v) if isinstance(v, list) else str(v)
        attrs_parts.append(
            f'<span class="attr-name"> {html_lib.escape(k)}</span>'
            f'<span class="punct">=</span>'
            f'<span class="attr-val">"{html_lib.escape(val)}"</span>'
        )
    attrs_html = "".join(attrs_parts)
    tag = html_lib.escape(node.name)

    meaningful = [
        c for c in node.children
        if isinstance(c, bs4.Tag)
        or (isinstance(c, bs4.NavigableString) and str(c).strip())
    ]

    if not meaningful:
        return (
            f'<div class="node leaf">'
            f'<span class="punct">&lt;</span><span class="tag-name">{tag}</span>'
            f'{attrs_html}<span class="punct">&gt;&lt;/{tag}&gt;</span>'
            f'</div>'
        )

    children_html = "".join(_node_to_html(c, depth + 1) for c in meaningful)
    open_attr = "open" if depth < 2 else ""
    return (
        f'<details {open_attr} class="node">'
        f'<summary><span class="punct">&lt;</span>'
        f'<span class="tag-name">{tag}</span>{attrs_html}'
        f'<span class="punct">&gt;</span></summary>'
        f'<div class="children">{children_html}</div>'
        f'<div class="closing"><span class="punct">&lt;/</span>'
        f'<span class="tag-name">{tag}</span><span class="punct">&gt;</span></div>'
        f'</details>'
    )


_TREE_CSS = """
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 13px;
    background: #1e1e2e;
    color: #cdd6f4;
    padding: 10px 14px;
    line-height: 1.65;
  }
  details { margin-left: 18px; }
  summary {
    cursor: pointer;
    list-style: none;
    display: block;
    padding: 1px 2px;
    border-radius: 3px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  summary:hover { background: rgba(255,255,255,0.06); }
  summary::-webkit-details-marker { display: none; }
  summary::before {
    content: "▶";
    color: #585b70;
    font-size: 9px;
    margin-right: 5px;
    display: inline-block;
    width: 10px;
    text-align: center;
  }
  details[open] > summary::before { content: "▼"; }
  .tag-name { color: #f38ba8; }
  .punct    { color: #89b4fa; }
  .attr-name { color: #fab387; }
  .attr-val  { color: #a6e3a1; }
  .text-node {
    color: #bac2de;
    margin-left: 34px;
    display: block;
    padding: 1px 0;
    white-space: pre-wrap;
    word-break: break-all;
  }
  .children { border-left: 1px solid #313244; }
  .closing { margin-left: 18px; padding: 1px 0; }
  .leaf { margin-left: 34px; padding: 1px 0; }
  .result-sep {
    color: #585b70;
    font-size: 11px;
    margin: 8px 0 6px;
    border-top: 1px solid #313244;
    padding-top: 6px;
  }
</style>
"""


def render_devtools_tree(elements: list):
    parts = [_TREE_CSS, "<body>"]
    for i, el in enumerate(elements):
        if not isinstance(el, bs4.Tag):
            continue
        if i > 0:
            parts.append(f'<div class="result-sep">── [{i + 1}] ──</div>')
        parts.append(_node_to_html(el, depth=0))
    parts.append("</body>")
    height = min(max(250, len(elements) * 120), 850)
    components.html("\n".join(parts), height=height, scrolling=True)


# ── Nav level helpers ─────────────────────────────────────────────────────────
def next_lid() -> int:
    st.session_state["_lid_counter"] += 1
    return st.session_state["_lid_counter"]


def make_level(elements: list) -> dict:
    return {"lid": next_lid(), "elements": elements, "query": "", "history": [], "active_child": None}


def list_child_elements(source_elements: list, cap: int = 40) -> tuple:
    children, total = [], 0
    for el in source_elements:
        if isinstance(el, bs4.Tag):
            for c in el.children:
                if isinstance(c, bs4.Tag):
                    total += 1
                    if len(children) < cap:
                        children.append(c)
    return children, total


# ── Callbacks (run before widgets instantiate — safe to mutate session state) ─
def _find_level_idx(lid: int):
    for i, lv in enumerate(st.session_state["nav_levels"]):
        if lv["lid"] == lid:
            return i
    return None


def on_query_change(lid: int):
    idx = _find_level_idx(lid)
    if idx is None:
        return
    new_val = st.session_state.get(f"qbox_{lid}", "")
    level = st.session_state["nav_levels"][idx]
    level["query"] = new_val
    if new_val and new_val not in level["history"]:
        level["history"] = ([new_val] + level["history"])[:5]
    level["active_child"] = None
    st.session_state["nav_levels"] = st.session_state["nav_levels"][: idx + 1]


def drill_into(level_index: int, child_tag: bs4.Tag):
    levels = st.session_state["nav_levels"]
    if level_index >= len(levels):
        return
    levels[level_index]["active_child"] = child_tag
    st.session_state["nav_levels"] = levels[: level_index + 1] + [make_level([child_tag])]


def apply_history(lid: int, text: str):
    idx = _find_level_idx(lid)
    if idx is None:
        return
    st.session_state[f"qbox_{lid}"] = text
    level = st.session_state["nav_levels"][idx]
    level["query"] = text
    level["active_child"] = None
    st.session_state["nav_levels"] = st.session_state["nav_levels"][: idx + 1]


def on_scope_change():
    choice = st.session_state.get("scope_radio", "body")
    s = st.session_state.get("soup")
    if s:
        root_el = (s.body if s.body else s) if choice == "body" else s
        st.session_state["nav_levels"] = [make_level([root_el])]


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Scraping Debugger")
    st.radio("Mode", ["BS4 Parser"], label_visibility="collapsed")
    st.divider()
    st.caption("More modes coming soon.")

# ── Main ──────────────────────────────────────────────────────────────────────
st.header("BS4 Parser")

paste_tab, upload_tab = st.tabs(["Paste HTML", "Upload File"])

with paste_tab:
    pasted = st.text_area(
        "HTML source",
        height=250,
        placeholder="Paste raw HTML here…",
        value=st.session_state["html_source"] if st.session_state["html_source"] else "",
        key="paste_area",
    )
    if pasted and pasted != st.session_state["html_source"]:
        st.session_state["html_source"] = pasted
        st.session_state["soup"] = None
        st.session_state["nav_levels"] = []

with upload_tab:
    uploaded = st.file_uploader("Upload HTML file", type=["html", "htm", "txt"])
    if uploaded:
        content = uploaded.read().decode("utf-8", errors="replace")
        if content != st.session_state["html_source"]:
            st.session_state["html_source"] = content
            st.session_state["soup"] = None
            st.session_state["nav_levels"] = []
        st.success(f"Loaded {uploaded.name} ({len(content):,} chars)")

base_url = st.text_input(
    "Base URL (optional — used to resolve relative image paths)",
    value=st.session_state["base_url"],
    placeholder="https://example.com",
)
st.session_state["base_url"] = base_url

# Parse
html_source = st.session_state["html_source"]
if html_source and st.session_state["soup"] is None:
    soup, parser = parse_html(html_source)
    st.session_state["soup"] = soup
    st.session_state["parser_used"] = parser
    st.session_state["nav_levels"] = []

soup = st.session_state.get("soup")
if soup:
    st.caption(f"Parsed with **{st.session_state['parser_used']}** — {len(html_source):,} chars")

if not html_source:
    st.info("Paste or upload HTML above to get started.")

st.divider()

# ── Hierarchical drill-down ───────────────────────────────────────────────────
if soup:
    # Seed root level when nav_levels is empty
    if not st.session_state["nav_levels"]:
        scope_init = st.session_state.get("scope_radio", "body")
        root_el = (soup.body if soup.body else soup) if scope_init == "body" else soup
        st.session_state["nav_levels"] = [make_level([root_el])]

    st.radio(
        "Scope",
        ["body", "all"],
        horizontal=True,
        key="scope_radio",
        help="`body` → root is `soup.body`   `all` → root is `soup`",
        on_change=on_scope_change,
    )

    for i, level in enumerate(st.session_state["nav_levels"]):
        lid = level["lid"]
        is_deepest = i == len(st.session_state["nav_levels"]) - 1

        # Breadcrumb for child levels
        if i > 0:
            st.caption(f"└─ {_collapsed_tag_label(level['elements'][0], 1)}")

        # Per-level history buttons
        if level["history"]:
            st.caption("Recent:")
            hist_cols = st.columns(len(level["history"]))
            for j, h in enumerate(level["history"]):
                with hist_cols[j]:
                    label = (h[:22] + "…") if len(h) > 22 else h
                    st.button(
                        label,
                        key=f"hist_{lid}_{j}",
                        help=h,
                        use_container_width=True,
                        on_click=apply_history,
                        args=(lid, h),
                    )

        # Expression input — key is unique per lid; on_change fires on blur/Enter
        st.text_input(
            "BS4 expression" if i == 0 else f"Expression (level {i + 1})",
            placeholder='scope.select("div.title")  or  scope.find_all("a", href=True)',
            key=f"qbox_{lid}",
            on_change=on_query_change,
            args=(lid,),
        )

        # Eval query → compute source elements for child buttons
        source_elements = level["elements"]
        if level["query"]:
            scope_el = level["elements"][0] if level["elements"] else soup
            ns = {
                "soup": soup,
                "scope": scope_el,
                "results": level["elements"],
                "Tag": bs4.Tag,
                "NavigableString": bs4.NavigableString,
                "ResultSet": bs4.ResultSet,
                "BeautifulSoup": BeautifulSoup,
                "re": __import__("re"),
            }
            try:
                raw = eval(level["query"], ns)  # noqa: S307
                data, kind = normalize_result(raw)
                if kind == "none":
                    st.warning("Result: None")
                elif kind == "string":
                    st.code(data, language="text")
                else:
                    tags = [el for el in data if isinstance(el, bs4.Tag)]
                    non_tags = [el for el in data if not isinstance(el, bs4.Tag)]
                    st.metric("Results", len(data))
                    for item in non_tags:
                        st.code(str(item), language="text")
                    if tags:
                        source_elements = tags
                        if is_deepest:
                            render_devtools_tree(tags)
                        else:
                            with st.expander(f"Tree ({len(tags)} elements)", expanded=False):
                                render_devtools_tree(tags)
            except Exception as exc:
                st.error(f"Error: {exc}")

        # Child element buttons — one per direct Tag child, rows of 4
        children, total = list_child_elements(source_elements)
        if children:
            overflow = total - len(children)
            label_suffix = f" (showing {len(children)} of {total})" if overflow else f" ({total})"
            st.caption(f"Children{label_suffix}:")
            for row_start in range(0, len(children), 4):
                row = children[row_start : row_start + 4]
                cols = st.columns(len(row))
                for col_idx, child_tag in enumerate(row):
                    with cols[col_idx]:
                        is_active = child_tag is level.get("active_child")
                        st.button(
                            _collapsed_tag_label(child_tag, 1),
                            key=f"child_{lid}_{row_start + col_idx}",
                            use_container_width=True,
                            type="primary" if is_active else "secondary",
                            on_click=drill_into,
                            args=(i, child_tag),
                        )

        if not is_deepest:
            st.divider()
