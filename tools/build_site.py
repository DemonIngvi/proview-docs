"""Builds a static, cross-linked HTML site from docs/ into site/.

    python tools/build_site.py          # then open site/index.html

Features: sidebar navigation, per-page table of contents, client-side search
(works from file://), rendered mermaid diagrams, light/dark theme, automatic
cross-links (ADR ids, FR/NFR ids, technologies -> their ADR, repositories),
and "referenced by" backlinks on every page.
"""
from __future__ import annotations

import html
import json
import pathlib
import re
import shutil
import sys
import urllib.request

import markdown
from markdown.extensions.toc import slugify_unicode

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = ROOT / "site"
VENDOR = ROOT / "tools" / "vendor"
MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"
GH = "https://github.com/DemonIngvi"

sys.path.insert(0, str(ROOT / "tools"))
from adr_data import ADRS  # noqa: E402

# ---------------------------------------------------------------- page model
SECTIONS = [
    ("Обзор", ["brief.md", "prd.md"]),
    ("Архитектура", ["architecture.md", "front-end-spec.md"]),
    ("Решения (ADR)", ["adr/README.md"] + [f"adr/{a['id']}-{a['slug']}.md" for a in ADRS]),
    ("Истории", sorted(p.relative_to(DOCS).as_posix() for p in (DOCS / "stories").glob("*.md"))),
    ("Качество", ["qa/test-strategy.md"]),
    ("Эксплуатация", ["runbooks/install.md", "runbooks/operations.md"]),
]

REPOS = {
    "proview-banner-service": "выдача баннеров, API пула",
    "proview-event-collector": "приём событий → Kafka",
    "proview-event-ingester": "Kafka → ClickHouse, агрегаты",
    "proview-analytics": "API срезов и админка",
    "proview-web": "демо-страница и SDK",
    "proview-deploy": "compose, Helm, e2e, chaos, нагрузка",
    "proview-docs": "эта документация",
}

ADR_FILE = {a["id"]: f"adr/{a['id']}-{a['slug']}.html" for a in ADRS}

# Technology / concept -> ADR it is decided in. First mention per page is linked.
TERMS = [
    (r"\bKafka\b", "0003"), (r"\bClickHouse\b", "0005"), (r"\bPostgreSQL\b", "0009"),
    (r"\bfranz-go\b", "0004"), (r"\bnet/http\b", "0002"), (r"\bStrimzi\b", "0013"),
    (r"\bCloudNativePG\b", "0013"), (r"\bAltinity\b", "0013"), (r"\bHelm\b", "0013"),
    (r"\bKEDA\b", "0016"), (r"\bHPA\b", "0016"), (r"\bECharts\b", "0012"),
    (r"\bdistroless\b", "0015"), (r"\bsendBeacon\b", "0018"), (r"\bIntersectionObserver\b", "0018"),
    (r"\bAggregatingMergeTree\b", "0007"), (r"\bproview_agg\b", "0007"), (r"\bDLQ\b", "0006"),
    (r"\bPrometheus\b", "0014"), (r"\boauth2-proxy\b", "0017"), (r"\bSSO\b", "0017"),
    (r"\bGHCR\b", "0019"), (r"\bGitHub Actions\b", "0019"), (r"\bHMAC\b", "0010"),
    (r"токен[а-я]* показа", "0010"), (r"\bat-least-once\b", "0008"), (r"\bGo\b(?![-/])", "0001"),
]


def title_of(md: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", md, re.M)
    return m.group(1).strip() if m else fallback


def short_title(path: str, title: str) -> str:
    if path.startswith("adr/") and path != "adr/README.md":
        return re.sub(r"^ADR-(\d+)\.\s*", r"\1 · ", title)
    if path.startswith("stories/"):
        return re.sub(r"^Story\s+", "", title)
    return {"brief.md": "Project Brief", "prd.md": "PRD — требования", "architecture.md": "Архитектура",
            "front-end-spec.md": "UI/UX спецификация", "adr/README.md": "Все решения",
            "qa/test-strategy.md": "Тест-стратегия и результаты", "runbooks/install.md": "Установка",
            "runbooks/operations.md": "Эксплуатация и инциденты"}.get(path, title)


# ---------------------------------------------------------------- rendering
MD = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists", "toc", "attr_list"],
                       extension_configs={"toc": {"slugify": slugify_unicode, "toc_depth": "2-3"}})


def rel(from_page: str, to_page: str) -> str:
    """Relative URL between two site pages (paths relative to site root)."""
    depth = from_page.count("/")
    return "../" * depth + to_page


SKIP_TAGS = {"a", "code", "pre", "h1", "h2", "h3", "h4", "script", "style", "th"}
TAG_RE = re.compile(r"(<[^>]+>)")


def autolink(body: str, page: str) -> str:
    """Adds cross-links in text nodes outside links, code and headings."""
    linked_terms: set[str] = set()
    stack: list[str] = []
    out = []

    def sub_text(text: str) -> str:
        # Inserted anchors are parked as <NUL>N<NUL> placeholders so later
        # patterns never match inside an anchor's attributes or text.
        parked: list[str] = []

        def park(fragment: str) -> str:
            parked.append(fragment)
            return f"\x00{len(parked) - 1}\x00"

        def link(href: str, label: str, title: str, cls: str = "xref") -> str:
            target = href if href.startswith("http") else rel(page, href)
            return park(f'<a class="{cls}" href="{target}" title="{html.escape(title)}">{label}</a>')

        def adr(m):
            target = ADR_FILE.get(m.group(1))
            if not target or target == page:
                return m.group(0)
            return link(target, m.group(0), next(a["title"] for a in ADRS if a["id"] == m.group(1)))
        text = re.sub(r"ADR-(\d{4})", adr, text)

        if page != "prd.html":
            text = re.sub(r"\b(N?FR\d{1,2})\b",
                          lambda m: link(f"prd.html#{m.group(1).lower()}", m.group(1), "Требование " + m.group(1)), text)

        # Repositories and short service names (banner-service → proview-banner-service).
        names = [(r, r, d) for r, d in REPOS.items()]
        names += [(r.removeprefix("proview-"), r, d) for r, d in REPOS.items() if r.count("-") >= 2]
        for name, repo, desc in names:
            if repo in linked_terms:
                continue
            pat = re.compile(rf"(?<![\w/-]){re.escape(name)}(?![\w-])")
            if pat.search(text):
                text = pat.sub(lambda m: link(f"{GH}/{repo}", m.group(0), f"GitHub {repo}: {desc}", "xref ext"), text, count=1)
                linked_terms.add(repo)

        for pattern, adr_id in TERMS:
            target = ADR_FILE[adr_id]
            if target == page or pattern in linked_terms:
                continue
            rx = re.compile(pattern)
            if rx.search(text):
                title = next(a["title"] for a in ADRS if a["id"] == adr_id)
                text = rx.sub(lambda m: link(target, m.group(0), f"Почему: {title}"), text, count=1)
                linked_terms.add(pattern)
        return re.sub("\x00(\\d+)\x00", lambda m: parked[int(m.group(1))], text)

    for part in TAG_RE.split(body):
        if part.startswith("<"):
            m = re.match(r"<\s*(/)?\s*([a-zA-Z0-9]+)", part)
            if m:
                name = m.group(2).lower()
                if name in SKIP_TAGS and not part.endswith("/>"):
                    if m.group(1):
                        if name in stack:
                            while stack and stack.pop() != name:
                                pass
                    else:
                        stack.append(name)
            out.append(part)
        elif stack or not part.strip():
            out.append(part)
        else:
            # Protect already inserted anchors from re-processing within this text node.
            out.append(sub_text(part))
    return "".join(out)


def render_md(src: str, page: str) -> tuple[str, str]:
    MD.reset()
    body = MD.convert(src)
    toc = MD.toc
    # mermaid fences → <pre class="mermaid">
    body = re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>',
                  lambda m: f'<div class="diagram"><pre class="mermaid">{m.group(1)}</pre></div>', body, flags=re.S)
    # .md links → .html
    body = re.sub(r'href="(?!https?:)([^"#]*?)\.md(#[^"]*)?"', lambda m: f'href="{m.group(1)}.html{m.group(2) or ""}"', body)
    body = re.sub(r'href="(?!https?:|#)([^"]*?/)?stories"', r'href="\1stories/index.html"', body)
    # FR/NFR anchors in the PRD tables
    if page == "prd.html":
        body = re.sub(r"<td>(N?FR\d{1,2})</td>", lambda m: f'<td id="{m.group(1).lower()}" class="req-id">{m.group(1)}</td>', body)
    # wrap tables for horizontal scroll on small screens
    body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
    return autolink(body, page), toc


# ---------------------------------------------------------------- layout
ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="12" width="4" height="9" rx="1"/><rect x="10" y="7" width="4" height="14" rx="1"/><rect x="17" y="3" width="4" height="18" rx="1"/></svg>'


def nav_html(current: str, pages: dict) -> str:
    parts = []
    for section, items in SECTIONS:
        is_open = any(p.replace(".md", ".html") == current for p in items) or section in ("Обзор", "Архитектура")
        lis = []
        for p in items:
            href = p.replace(".md", ".html")
            cls = ' class="active"' if href == current else ""
            lis.append(f'<li><a{cls} href="{rel(current, href)}">{html.escape(pages[p]["short"])}</a></li>')
        parts.append(f'<details{" open" if is_open else ""}><summary>{section}</summary><ul>{"".join(lis)}</ul></details>')
    return "".join(parts)


def page_shell(current: str, title: str, content: str, nav: str, toc: str = "", backlinks: str = "", pager: str = "") -> str:
    up = "../" * current.count("/")
    toc_block = f'<aside class="toc"><div class="toc-title">На странице</div>{toc}</aside>' if toc and "<li>" in toc else '<aside class="toc"></aside>'
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · ProView Docs</title>
<link rel="icon" href="{up}assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{up}assets/site.css">
<script>try{{const t=localStorage.getItem('pv-docs-theme');if(t)document.documentElement.dataset.theme=t}}catch(e){{}}</script>
</head>
<body>
<header class="top">
  <button class="menu-btn" type="button" aria-label="Меню" onclick="document.body.classList.toggle('nav-open')">☰</button>
  <a class="brand" href="{up}index.html">{ICON}<span>ProView <b>Docs</b></span></a>
  <div class="search"><input id="q" type="search" placeholder="Поиск по документации…" autocomplete="off" aria-label="Поиск"><div id="results" class="results" hidden></div></div>
  <a class="gh" href="{GH}/proview-docs" title="Исходники документации на GitHub">GitHub</a>
  <button id="theme" class="theme-btn" type="button" aria-label="Переключить тему">◐</button>
</header>
<div class="layout">
  <nav class="side" aria-label="Разделы">{nav}</nav>
  <main class="content">
    <article class="doc">{content}</article>
    {backlinks}
    {pager}
  </main>
  {toc_block}
</div>
<script>window.PV_ROOT="{up}";</script>
<script src="{up}assets/search-index.js"></script>
<script src="{up}assets/mermaid.min.js"></script>
<script src="{up}assets/site.js"></script>
</body>
</html>
"""


# ---------------------------------------------------------------- build
def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True)
    VENDOR.mkdir(parents=True, exist_ok=True)
    mermaid = VENDOR / "mermaid.min.js"
    if not mermaid.exists():
        print("downloading mermaid …")
        urllib.request.urlretrieve(MERMAID_URL, mermaid)
    shutil.copy(mermaid, OUT / "assets" / "mermaid.min.js")
    shutil.copytree(DOCS / "images", OUT / "images")
    shutil.copy(ROOT / "tools" / "site" / "site.css", OUT / "assets" / "site.css")
    shutil.copy(ROOT / "tools" / "site" / "site.js", OUT / "assets" / "site.js")
    shutil.copy(ROOT / "tools" / "site" / "favicon.svg", OUT / "assets" / "favicon.svg")

    pages: dict[str, dict] = {}
    for _, items in SECTIONS:
        for p in items:
            src = (DOCS / p).read_text(encoding="utf-8")
            t = title_of(src, p)
            pages[p] = {"src": src, "title": t, "short": short_title(p, t)}

    # render
    rendered = {}
    for p, meta in pages.items():
        page = p.replace(".md", ".html")
        body, toc = render_md(meta["src"], page)
        rendered[page] = (meta, body, toc)

    # backlinks: who links to whom
    back: dict[str, set[str]] = {k: set() for k in rendered}
    for page, (_, body, _) in rendered.items():
        base = pathlib.PurePosixPath(page).parent
        for href in re.findall(r'href="([^"#]+\.html)', body):
            if href.startswith("http"):
                continue
            target = pathlib.PurePosixPath(*(base / href).parts)
            parts = []
            for seg in target.parts:
                if seg == "..":
                    parts.pop()
                elif seg != ".":
                    parts.append(seg)
            t = "/".join(parts)
            if t in back and t != page:
                back[t].add(page)

    search = []
    order = [p.replace(".md", ".html") for _, items in SECTIONS for p in items]
    for page, (meta, body, toc) in rendered.items():
        nav = nav_html(page, pages)
        bl = ""
        if back[page]:
            items = "".join(f'<li><a href="{rel(page, b)}">{html.escape(rendered[b][0]["short"])}</a></li>'
                            for b in sorted(back[page], key=order.index))
            bl = f'<section class="backlinks"><h2>На эту страницу ссылаются</h2><ul>{items}</ul></section>'
        i = order.index(page)
        prev_ = f'<a class="prev" href="{rel(page, order[i-1])}">← {html.escape(rendered[order[i-1]][0]["short"])}</a>' if i > 0 else "<span></span>"
        next_ = f'<a class="next" href="{rel(page, order[i+1])}">{html.escape(rendered[order[i+1]][0]["short"])} →</a>' if i + 1 < len(order) else "<span></span>"
        pager = f'<nav class="pager">{prev_}{next_}</nav>'
        out = OUT / page
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page_shell(page, meta["title"], body, nav, toc, bl, pager), encoding="utf-8", newline="\n")
        text = re.sub(r"<[^>]+>", " ", body)
        text = html.unescape(re.sub(r"\s+", " ", text))
        search.append({"t": meta["title"], "u": page, "s": text[:6000]})

    # stories index
    st_items = [p for p in order if p.startswith("stories/")]
    rows = "".join(f'<tr><td><a href="{rel("stories/index.html", s)}">{html.escape(rendered[s][0]["title"])}</a></td><td>Done</td></tr>' for s in st_items)
    st_body = f'<h1>Истории разработки</h1><p>13 историй в формате BMAD: история, критерии приёмки, задачи, тесты, результат QA. Эпики и их цели — в <a href="../prd.html#5-эпики-и-истории">PRD</a>.</p><div class="table-wrap"><table><thead><tr><th>История</th><th>Статус</th></tr></thead><tbody>{rows}</tbody></table></div>'
    (OUT / "stories" / "index.html").write_text(page_shell("stories/index.html", "Истории", st_body, nav_html("stories/index.html", pages)), encoding="utf-8", newline="\n")

    # home page
    (OUT / "index.html").write_text(page_shell("index.html", "ProView", home(rendered), nav_html("index.html", pages)), encoding="utf-8", newline="\n")
    (OUT / "assets" / "search-index.js").write_text("window.PV_SEARCH=" + json.dumps(search, ensure_ascii=False) + ";\n", encoding="utf-8", newline="\n")
    print(f"site: {len(rendered) + 2} pages -> {OUT / 'index.html'}")


def home(rendered) -> str:
    arch_src = (DOCS / "architecture.md").read_text(encoding="utf-8")
    overview = re.search(r"```mermaid\n(.*?)```", arch_src, re.S).group(1)
    cards = [
        ("brief.html", "Project Brief", "Проблема, пользователи, цели и метрики успеха, объём MVP, риски."),
        ("prd.html", "PRD", "16 функциональных и 12 нефункциональных требований, 6 эпиков."),
        ("architecture.html", "Архитектура", "C1/C2/C3, потоки, контракты, ёмкость на 20k RPS, отказоустойчивость, безопасность."),
        ("adr/README.html", "19 решений (ADR)", "Почему выбрана каждая технология и какие альтернативы отвергнуты."),
        ("front-end-spec.html", "UI/UX", "Админка: структура, правила визуализации, доступность, скриншоты."),
        ("stories/index.html", "Истории", "13 историй с критериями приёмки и ссылками на тесты."),
        ("qa/test-strategy.html", "Качество", "Пирамида тестов, фактические результаты, найденные дефекты."),
        ("runbooks/install.html", "Эксплуатация", "Установка в Kubernetes, инциденты, ротация ключей."),
    ]
    card_html = "".join(f'<a class="card" href="{h}"><div class="card-t">{t}</div><div class="card-d">{d}</div></a>' for h, t, d in cards)
    adr_html = "".join(
        f'<a class="adr" href="{ADR_FILE[a["id"]]}"><span class="adr-id">{a["id"]}</span><span class="adr-t">{html.escape(a["title"])}</span>'
        f'<span class="adr-alt">vs {html.escape(", ".join(o for o, *_ in a["alts"][:3]))}</span></a>' for a in ADRS)
    repo_html = "".join(f'<a class="repo" href="{GH}/{r}"><b>{r}</b><span>{d}</span></a>' for r, d in REPOS.items())
    facts = [("20k", "RPS — целевая нагрузка"), ("0", "потерь при отказе ClickHouse и загрузчика"), ("~2 с", "от события до агрегата"),
             ("230 нс", "выбор баннера"), ("19", "архитектурных решений"), ("7", "репозиториев")]
    fact_html = "".join(f'<div class="fact"><div class="fact-v">{v}</div><div class="fact-l">{l}</div></div>' for v, l in facts)
    return f"""
<section class="hero">
  <p class="kicker">Документация · BMAD Method · v0.1.0</p>
  <h1>ProView — показ баннеров и измерение вовлечённости</h1>
  <p class="lead">Баннер из пула по преднастройке места → SDK измеряет показ, видимость, наведение, клик и активное время →
  <a href="{ADR_FILE['0003']}">Kafka</a> → <a href="{ADR_FILE['0005']}">ClickHouse</a> → <a href="{ADR_FILE['0007']}">база-агрегатор</a> →
  админка со срезами. Рассчитано на 20 000 запросов в секунду, масштабируется горизонтально и не теряет события при сбоях.</p>
  <div class="facts">{fact_html}</div>
</section>
<h2 id="map">Как устроено</h2>
<div class="diagram"><pre class="mermaid">{html.escape(overview)}</pre></div>
<p class="muted">Подробно — <a href="architecture.html">архитектура</a>: <a href="architecture.html#3-контейнеры-c2">контейнеры</a>,
<a href="architecture.html#5-ключевые-потоки">потоки</a>, <a href="architecture.html#7-ёмкость-и-масштабирование">ёмкость</a>,
<a href="architecture.html#8-надёжность-и-отказоустойчивость">отказоустойчивость</a>.</p>
<h2 id="docs">Документы</h2>
<div class="cards">{card_html}</div>
<h2 id="decisions">Почему такие технологии</h2>
<p class="muted">Каждое решение — отдельная страница: контекст, обоснование, альтернативы с причинами отказа, последствия, условие пересмотра.</p>
<div class="adrs">{adr_html}</div>
<h2 id="repos">Репозитории</h2>
<div class="repos">{repo_html}</div>
<h2 id="look">Как это выглядит</h2>
<div class="shots"><a href="front-end-spec.html#5-проверка-вёрстки"><img src="images/analytics-light.png" alt="Админка, светлая тема" loading="lazy"></a>
<a href="front-end-spec.html#5-проверка-вёрстки"><img src="images/analytics-dark.png" alt="Админка, тёмная тема" loading="lazy"></a></div>
"""


if __name__ == "__main__":
    main()
