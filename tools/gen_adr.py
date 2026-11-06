"""Generates docs/adr/*.md and docs/adr/README.md from tools/adr_data.py."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from adr_data import ADRS  # noqa: E402

out = pathlib.Path(__file__).resolve().parent.parent / "docs" / "adr"
out.mkdir(parents=True, exist_ok=True)

index = ["# Architecture Decision Records", "",
         "Каждое техническое решение ProView: контекст, решение, обоснование, рассмотренные альтернативы и почему они не выбраны, последствия и условие пересмотра.", "",
         "Источник: `tools/adr_data.py` → `python tools/gen_adr.py`.", "",
         "| № | Решение | Альтернативы |", "|---|---|---|"]

for a in ADRS:
    name = f"{a['id']}-{a['slug']}.md"
    lines = [f"# ADR-{a['id']}. {a['title']}", "",
             "- **Статус:** принято", "- **Дата:** 2026-11-06", "",
             "## Контекст", "", a["context"], "",
             "## Решение", "", a["decision"], "",
             "## Обоснование", ""]
    lines += [f"- {w}" for w in a["why"]]
    lines += ["", "## Рассмотренные альтернативы", "",
              "| Вариант | Плюсы | Минусы | Почему не выбран |", "|---|---|---|---|"]
    lines += [f"| {o} | {p} | {c} | {v} |" for o, p, c, v in a["alts"]]
    lines += ["", "## Последствия", ""]
    lines += [f"- {'✅' if s == '+' else '⚠️'} {t}" for s, t in a["cons"]]
    lines += ["", "## Когда пересмотреть", "", a["revisit"], ""]
    (out / name).write_text("\n".join(lines), encoding="utf-8", newline="\n")
    index.append(f"| [{a['id']}]({name}) | {a['title']} | {', '.join(o for o, *_ in a['alts'])} |")

(out / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8", newline="\n")
print(f"generated {len(ADRS)} ADRs")
