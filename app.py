import html as html_lib
from collections import Counter

import bs4
import streamlit as st
import streamlit.components.v1 as components
from bs4 import BeautifulSoup

st.set_page_config(page_title="Scraping Debugger", layout="wide")

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}

# ── Session state defaults ────────────────────────────────────────────────────
for key, default in {
    "html_source": "",
    "soup": None,
    "parser_used": "",
    "query_history": [],
    "base_url": "",
    "last_results": [],
    "auto_run": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

if "query_input" not in st.session_state:
    st.session_state["query_input"] = ""


# ── Helpers ───────────────────────────────────────────────────────────────────
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


def get_child_tag_counts(elements: list) -> dict:
    counts: Counter = Counter()
    for el in elements:
        if isinstance(el, bs4.Tag):
            for child in el.children:
                if isinstance(child, bs4.Tag):
                    counts[child.name] += 1
    return counts


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


# ── Programmatic navigation ───────────────────────────────────────────────────
def push_query(new_query: str):
    st.session_state["query_input"] = new_query
    st.session_state["auto_run"] = True
    st.rerun()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Scraping Debugger")
    st.radio("Mode", ["BS4 Parser"], label_visibility="collapsed")
    st.divider()
    st.caption("More modes coming soon.")

# ── Main ──────────────────────────────────────────────────────────────────────
st.header("BS4 Parser")

# HTML input
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
        st.session_state["last_results"] = []

with upload_tab:
    uploaded = st.file_uploader("Upload HTML file", type=["html", "htm", "txt"])
    if uploaded:
        content = uploaded.read().decode("utf-8", errors="replace")
        if content != st.session_state["html_source"]:
            st.session_state["html_source"] = content
            st.session_state["soup"] = None
            st.session_state["last_results"] = []
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

soup = st.session_state.get("soup")
if soup:
    st.caption(f"Parsed with **{st.session_state['parser_used']}** — {len(html_source):,} chars")

st.divider()

# ── Query ─────────────────────────────────────────────────────────────────────
st.subheader("Query")

# Scope selector
scope_choice = st.radio(
    "Scope",
    ["body", "all"],
    horizontal=True,
    help="`body` → `scope = soup.body`   `all` → `scope = soup`",
)
scope = (soup.body if soup and soup.body else soup) if scope_choice == "body" else soup

# History (max 5, shown as buttons)
history: list = st.session_state["query_history"]
if history:
    st.caption("Recent:")
    hist_cols = st.columns(len(history))
    for i, h in enumerate(history):
        with hist_cols[i]:
            label = (h[:22] + "…") if len(h) > 22 else h
            if st.button(label, key=f"hist_{i}", help=h, use_container_width=True):
                push_query(h)

# Expression input
query: str = st.text_input(
    "BS4 expression",
    placeholder='scope.select("div.title")  or  scope.find_all("a", href=True)',
    key="query_input",
)

run = st.button("Run", type="primary", disabled=not (query and soup))

if not html_source:
    st.info("Paste or upload HTML above to get started.")

st.divider()

# ── Eval ──────────────────────────────────────────────────────────────────────
auto_run = st.session_state.get("auto_run", False)
if auto_run:
    del st.session_state["auto_run"]

should_run = (run or auto_run) and query and soup

if should_run:
    if query not in history:
        history.insert(0, query)
        st.session_state["query_history"] = history[:5]

    allowed_ns = {
        "soup": soup,
        "scope": scope,
        "results": st.session_state["last_results"],
        "Tag": bs4.Tag,
        "NavigableString": bs4.NavigableString,
        "ResultSet": bs4.ResultSet,
        "BeautifulSoup": BeautifulSoup,
        "re": __import__("re"),
    }

    try:
        raw_result = eval(query, allowed_ns)  # noqa: S307
    except Exception as exc:
        st.error(f"Error: {exc}")
        st.stop()

    data, kind = normalize_result(raw_result)

    if kind == "none":
        st.warning("Result: None")
    elif kind == "string":
        st.subheader("Result")
        st.code(data, language="text")
    else:
        tags = [el for el in data if isinstance(el, bs4.Tag)]
        non_tags = [el for el in data if not isinstance(el, bs4.Tag)]

        # Persist for next eval + children buttons
        st.session_state["last_results"] = tags

        st.metric("Results", len(data))

        if non_tags:
            st.caption("Non-tag items")
            for item in non_tags:
                st.code(str(item), language="text")

        if tags:
            render_devtools_tree(tags)

        # ── Children drill-down buttons ───────────────────────────────────────
        child_counts = get_child_tag_counts(tags)
        if child_counts:
            st.caption("Children — click to drill in:")
            # Sort by count desc, cap at 8 buttons
            sorted_children = sorted(child_counts.items(), key=lambda x: -x[1])[:8]
            btn_cols = st.columns(len(sorted_children))
            for i, (tag_name, count) in enumerate(sorted_children):
                with btn_cols[i]:
                    if st.button(
                        f"<{tag_name}>  {count}",
                        key=f"child_{tag_name}",
                        use_container_width=True,
                    ):
                        new_q = (
                            f"[c for el in results for c in el.children"
                            f" if getattr(c, 'name', None) == '{tag_name}']"
                        )
                        push_query(new_q)
