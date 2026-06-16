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
    "query_history": [],
    "base_url": "",
    "pending_query": "",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ── Helpers ───────────────────────────────────────────────────────────────────
def parse_html(html: str):
    try:
        soup = BeautifulSoup(html, "lxml")
        return soup, "lxml"
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
        return soup, "html.parser"


def resolve_url(src: str, base: str) -> str:
    if src.startswith(("http://", "https://", "data:")):
        return src
    if base:
        return base.rstrip("/") + "/" + src.lstrip("/")
    return ""


def is_image_url(url: str) -> bool:
    from urllib.parse import urlparse
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in IMAGE_EXTENSIONS)


def render_tag(element: bs4.Tag, base_url: str, index: int):
    # Build expander label: <tag> + id + class snippet
    tag_name = element.name or "?"
    parts = [f"<{tag_name}>"]
    if element.get("id"):
        parts.append(f'#{element["id"]}')
    if element.get("class"):
        cls = " ".join(element["class"])
        parts.append(f'.{cls[:40]}{"…" if len(cls) > 40 else ""}')
    label = " ".join(parts)

    with st.expander(f"[{index}] {label}", expanded=False):
        # Attributes
        if element.attrs:
            with st.expander("Attributes", expanded=False):
                rows = []
                for attr, val in element.attrs.items():
                    rows.append({"Attribute": attr, "Value": " ".join(val) if isinstance(val, list) else str(val)})
                st.table(rows)

        # Inner text
        text = element.get_text(strip=True)
        if text:
            st.caption("Inner text")
            st.text(text[:800] + ("…" if len(text) > 800 else ""))

        # Raw HTML
        st.caption("Raw HTML")
        raw = str(element)
        st.code(raw[:3000] + ("…" if len(raw) > 3000 else ""), language="html")

        # Image rendering
        src = element.get("src") or element.get("href", "")
        if tag_name == "img" or (src and is_image_url(src)):
            resolved = resolve_url(src, base_url)
            if resolved:
                try:
                    st.image(resolved)
                except Exception:
                    st.caption(f"Could not load image: {resolved}")


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


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Scraping Debugger")
    mode = st.radio("Mode", ["BS4 Parser"], label_visibility="collapsed")
    st.divider()
    st.caption("More modes coming soon.")

# ── Main ──────────────────────────────────────────────────────────────────────
st.header("BS4 Parser")

# HTML Input
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

with upload_tab:
    uploaded = st.file_uploader("Upload HTML file", type=["html", "htm", "txt"])
    if uploaded:
        content = uploaded.read().decode("utf-8", errors="replace")
        if content != st.session_state["html_source"]:
            st.session_state["html_source"] = content
            st.session_state["soup"] = None
        st.success(f"Loaded {uploaded.name} ({len(content):,} chars)")

# Base URL
base_url = st.text_input(
    "Base URL (optional — used to resolve relative image paths)",
    value=st.session_state["base_url"],
    placeholder="https://example.com",
)
st.session_state["base_url"] = base_url

# Parse on demand
html = st.session_state["html_source"]
if html and st.session_state["soup"] is None:
    soup, parser = parse_html(html)
    st.session_state["soup"] = soup
    st.session_state["parser_used"] = parser

if st.session_state["soup"]:
    st.caption(f"Parsed with **{st.session_state['parser_used']}** — {len(html):,} chars")

st.divider()

# ── Query ─────────────────────────────────────────────────────────────────────
st.subheader("Query")

history = st.session_state["query_history"]
prefill = st.session_state.pop("pending_query", "") or ""

col_hist, col_clear = st.columns([5, 1])
with col_hist:
    if history:
        selected = st.selectbox(
            "History",
            options=[""] + history,
            index=0,
            label_visibility="collapsed",
        )
        if selected and selected != prefill:
            prefill = selected

query = st.text_input(
    "BS4 expression",
    value=prefill,
    placeholder='soup.select("div.title")  or  soup.find_all("a", href=True)',
)

run = st.button("Run", type="primary", disabled=not (query and st.session_state["soup"]))

if not html:
    st.info("Paste or upload HTML above to get started.")
elif not st.session_state["soup"]:
    st.warning("HTML could not be parsed.")

st.divider()

# ── Results ───────────────────────────────────────────────────────────────────
if run and query and st.session_state["soup"]:
    # Update history
    if query not in history:
        history.insert(0, query)
        st.session_state["query_history"] = history[:20]

    soup = st.session_state["soup"]
    allowed_ns = {
        "soup": soup,
        "Tag": bs4.Tag,
        "NavigableString": bs4.NavigableString,
        "ResultSet": bs4.ResultSet,
        "BeautifulSoup": BeautifulSoup,
        "__builtins__": {},
    }

    try:
        raw_result = eval(query, allowed_ns)  # noqa: S307
    except Exception as exc:
        st.error(f"Error: {exc}")
        raw_result = None
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

        st.metric("Results", len(data))

        if non_tags:
            st.caption("Non-tag items")
            for item in non_tags:
                st.code(str(item), language="text")

        for i, element in enumerate(tags):
            render_tag(element, base_url, i + 1)
