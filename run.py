import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.config import DEFAULT_PROVIDER
from src.llm import LLM
from src.pipeline import Pipeline


def print_event(event) -> None:
    data = event.to_dict()
    etype = data["type"]
    if etype == "decision":
        print(f"\n[决策·{data['stage']}] {data['title']}")
        if data["reason"]:
            print(f"  理由：{data['reason']}")
        if data["detail"]:
            print(f"  详情：{data['detail']}")
    elif etype == "search":
        detail = data["detail"] or {}
        print(f"[搜索·{data.get('stage')}] {data['title']} → {detail.get('count')} 条")
        for item in (detail.get("top") or [])[:3]:
            print(f"    · {item.get('title')}")
    elif etype == "matrix_cell":
        detail = data["detail"] or {}
        if detail.get("empty"):
            print(f"[矩阵] {data['title']}：盲区（0 条）")
        else:
            print(f"[矩阵] {data['title']}：{detail.get('count')} 条 · {detail.get('narrative')}")
    elif etype == "audit":
        detail = data["detail"] or {}
        verdict = detail.get("verdict") or {}
        print(f"\n[审计] 成立度：{verdict.get('level')}")
    elif etype == "done":
        print(f"\n[完成] {data['title']}")
    elif etype == "error":
        print(f"\n[错误] {data['title']}")


def render_matrix(matrix: dict) -> str:
    labels = [c["label"] for c in matrix["columns"]]
    lines = []
    lines.append("| 信源／时间窗 | " + " | ".join(labels) + " |")
    lines.append("|" + "---|" * (len(labels) + 1))
    for row in matrix["rows"]:
        values = []
        for cell in row["cells"]:
            if cell["empty"]:
                values.append("盲区")
            else:
                values.append(cell["narrative"] or f"{cell['count']}条")
        row_name = row["source"]["name"]
        if row.get("possible_index_gap"):
            if row.get("empty_reason", "").startswith("该信源结果缺少日期"):
                row_name += " †"
            else:
                row_name += " ‡"
        lines.append("| " + row_name + " | " + " | ".join(values) + " |")
    if any(r.get("possible_index_gap") for r in matrix["rows"]):
        lines.append("")
        lines.append("† 该信源结果缺少日期信息，时间窗过滤后为空（假盲区）　‡ 该信源对此问题无结果或索引缺失")
    return "\n".join(lines)


def main() -> None:
    claim = sys.argv[1] if len(sys.argv) > 1 else "飞信是被微信打死的"
    provider = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PROVIDER

    llm = LLM(provider)
    pipeline = Pipeline(llm, on_event=print_event)
    result = pipeline.run(claim)

    print("\n" + "=" * 70)
    print("叙事矩阵")
    print("=" * 70)
    print(render_matrix(result["matrix"]))

    print("\n" + "=" * 70)
    print("诊断卡片")
    print("=" * 70)
    card = result["audit"]["card"]
    print(f"论断：{card['claim']}")
    print(f"成立度：{card['verdict_level']}")
    print(f"盲区格：{card['blind_count']}")
    print(f"反例数：{card['counter_count']}")
    print(f"叙事漂移：{card['drift_note']}")

    print("\n支持证据：")
    for item in result["audit"]["supporting"]:
        print(f"  + [{item.get('source')}] {item.get('point')}")
    print("反例/反对证据：")
    for item in result["audit"]["contradicting"]:
        print(f"  - [{item.get('source')}] {item.get('point')}")

    print(f"\n审计理由：{result['audit']['verdict']['reason']}")


if __name__ == "__main__":
    main()