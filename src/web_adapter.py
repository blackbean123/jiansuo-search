
DIM_ID_MAP = {
    "direct": "direct",
    "multi_source": "multi",
    "time_evolution": "time",
    "counter_example": "counter",
    "deep_cause": "deep",
    "cross_validation": "cross",
}

PROTO_DIMS = [
    ("direct", "直接搜索"),
    ("multi", "多信源对比"),
    ("time", "时间演变"),
    ("counter", "反例检验"),
    ("deep", "深层归因"),
    ("cross", "交叉验证"),
]

LEVEL_SCORE = {"高": 82, "中高": 74, "中": 60, "中低": 40, "低": 24}


def _range_label(freshness: str) -> str:
    if not freshness:
        return "不限"
    if "," in freshness:
        a, b = [x.strip() for x in freshness.split(",", 1)]
        return a[:7].replace("-", ".") + "–" + b[:7].replace("-", ".")
    if freshness.startswith("y"):
        return "近" + freshness[1:] + "年"
    if freshness.startswith("m"):
        return "近" + freshness[1:] + "月"
    if freshness.startswith("d"):
        return "近" + freshness[1:] + "天"
    return freshness


def _titles(items: list[dict]) -> list[dict]:
    out = []
    for it in items or []:
        out.append(
            {
                "t": it.get("title", ""),
                "s": it.get("site", ""),
                "d": it.get("date", "") or "无日期",
                "u": it.get("url", ""),
            }
        )
    return out


def _core(analysis: dict) -> str:
    return analysis.get("core_keywords") or (analysis.get("summary", "") or "")[:24]


def _kind_for(name: str) -> str:
    if any(k in name for k in ("人民", "新华", "政府", "央视", "央广", "人民日报")):
        return "official"
    if any(k in name for k in ("36氪", "掘金", "少数派", "开源中国")):
        return "industry"
    if any(k in name for k in ("微博", "网易", "今日头条", "头条")):
        return "noisy"
    return "deep"


def build_case(claim: str, result: dict, provider_label: str) -> dict:
    analysis = result.get("analysis", {}) or {}
    dims_detail = result.get("dimensions_detail", {}) or {}
    sources = result.get("sources", []) or []
    sources_detail = result.get("sources_detail", []) or []
    windows = result.get("time_windows", []) or []
    probe = result.get("time_probe", {}) or {}
    dims_results = result.get("dimension_results", []) or []
    matrix = result.get("matrix", {}) or {}
    audit = result.get("audit", {}) or {}
    lens = result.get("industry_lens")
    core = _core(analysis)

    chosen_ids = {c.get("id") for c in dims_detail.get("chosen", [])}
    chosen_reason = {c.get("id"): c.get("reason", "") for c in dims_detail.get("chosen", [])}
    not_reason = {c.get("id"): c.get("reason", "") for c in dims_detail.get("not_chosen", [])}
    reverse_map = {v: k for k, v in DIM_ID_MAP.items()}
    dims = []
    for pid, pname in PROTO_DIMS:
        src_id = reverse_map.get(pid, pid)
        on = src_id in chosen_ids
        why = chosen_reason.get(src_id) if on else not_reason.get(src_id, "")
        dims.append({"id": pid, "name": pname, "on": on, "why": why or "——"})

    reason_by_domain = {d.get("domain", ""): d.get("reason", "") for d in sources_detail}
    src_rows = []
    for s in sources:
        src_rows.append(
            {
                "name": s.get("name", ""),
                "domain": s.get("domain", ""),
                "hit": s.get("hit_rate", 0),
                "why": reason_by_domain.get(s.get("domain", ""), ""),
            }
        )

    win_rows = []
    for i, w in enumerate(windows):
        fresh = w.get("freshness", "")
        label = _range_label(fresh)
        title = w.get("label", "") or "时间窗"
        if title == label:
            title = "未做时间切分"
        win_rows.append(
            {
                "id": f"w{i+1}",
                "label": label,
                "title": title,
                "freshness": fresh,
                "why": w.get("reason", ""),
            }
        )

    hist = probe.get("year_histogram", {}) or {}
    years = sorted(int(y) for y in hist.keys()) if hist else []
    counts = [hist.get(str(y), 0) for y in years]
    dated = sum(counts)
    probe_obj = {
        "query": core,
        "count": probe.get("count", 0),
        "dated": dated,
        "span": f"{probe.get('min_date', '')} – {probe.get('max_date', '')}" if hist else "无日期",
        "ms": 300,
        "probe": True,
        "label": "时间窗探测",
        "titles": _titles(probe.get("sample_titles", [])),
        "years": years,
        "counts": counts,
        "note": (
            f"{probe.get('count', 0)} 条结果，{dated} 条带日期；"
            f"覆盖 {probe.get('min_date', '')} ~ {probe.get('max_date', '')}。"
        ),
    }

    queries = []
    direct = None
    counter_searches = []
    deep_searches = []
    cross_searches = []
    for dr in dims_results:
        dim = dr.get("dimension", {}) or {}
        dim_id = dim.get("id", "")
        dim_name = dim.get("name", "")
        for qr in dr.get("results", []) or []:
            queries.append({"dim": dim_name, "q": qr.get("query", ""), "intent": qr.get("intent", "")})
            cfg = {
                "id": f"{dim_id}-{len(queries)}",
                "query": qr.get("query", ""),
                "site": "",
                "freshness": "",
                "count": qr.get("count", 0),
                "ms": 320,
                "titles": _titles(qr.get("titles", [])),
                "note": qr.get("intent", ""),
            }
            if dim_id == "direct" and direct is None:
                direct = cfg
            elif dim_id == "counter_example":
                counter_searches.append(cfg)
            elif dim_id == "deep_cause":
                deep_searches.append(cfg)
            elif dim_id == "cross_validation":
                cross_searches.append(cfg)

    if matrix:
        queries.append(
            {
                "dim": "矩阵 · 多信源 × 时间",
                "q": f"{core} × Site × Freshness",
                "intent": "核心词宽检索；用参数过滤替代长 query，避免三重约束压低召回。",
            }
        )
    if lens:
        queries.append(
            {
                "dim": "定向补充",
                "q": f"{lens.get('query', '')} × Industry={lens.get('industry', '')}",
                "intent": "政策/财经类补官方或专业视角，不与 Site 叠加。",
            }
        )

    if direct is None:
        direct = {
            "id": "d0",
            "query": core,
            "site": "",
            "freshness": "",
            "count": probe.get("count", 0),
            "ms": 300,
            "titles": probe_obj["titles"],
            "note": "自然检索基线。",
        }

    cols = []
    for i, c in enumerate(matrix.get("columns", []) or []):
        fresh = c.get("freshness", "")
        cols.append({"id": f"w{i+1}", "label": _range_label(fresh), "range": _range_label(fresh), "freshness": fresh})

    date_gap = set(matrix.get("date_gap_sources", []) or [])
    rows = []
    filled = blind = fake = 0
    for i, r in enumerate(matrix.get("rows", []) or []):
        src = r.get("source", {}) or {}
        cells = {}
        for j, cell in enumerate(r.get("cells", []) or []):
            colid = f"w{j+1}"
            count = cell.get("count", 0)
            if count > 0:
                filled += 1
                cells[colid] = {
                    "count": count,
                    "ms": 300,
                    "summary": cell.get("narrative") or f"{count} 条",
                    "titles": _titles(cell.get("titles", [])),
                }
            else:
                if src.get("name") in date_gap:
                    fake += 1
                    cells[colid] = {"count": 0, "fake": True, "reason": r.get("empty_reason", "日期缺失假盲区")}
                else:
                    blind += 1
                    cells[colid] = {"count": 0, "reason": r.get("empty_reason", "该窗口无结果")}

        row = {
            "id": f"r{i}",
            "name": src.get("name", ""),
            "domain": src.get("domain", ""),
            "hit": src.get("hit_rate", 0),
            "cells": cells,
        }
        if r.get("possible_index_gap"):
            is_fake = src.get("name") in date_gap
            row["note"] = "补检判定：日期缺失假盲区" if is_fake else "补检判定：无结果/索引缺失"
            fb = r.get("fallback")
            if fb:
                row["fallback"] = {
                    "query": fb.get("query", core),
                    "site": fb.get("site", src.get("domain", "")),
                    "count": fb.get("count", 0),
                    "ms": 300,
                    "titles": _titles(fb.get("titles", [])),
                    "note": "去掉时间窗后的补检结果。",
                }
        rows.append(row)

    matrix_obj = {"query": core, "cols": cols, "rows": rows} if cols and rows else None
    insight = (
        f"{filled + blind + fake} 格里 {filled} 格有结果、{blind} 格真盲区、{fake} 格假盲区。"
        "真盲区与假盲区（日期缺失）分别标注，不把空白当成「没有人讨论」。"
        if matrix_obj
        else ""
    )

    industry_obj = None
    if lens:
        industry_obj = {
            "id": "i1",
            "query": lens.get("query", ""),
            "industry": lens.get("industry", ""),
            "count": lens.get("count", 0),
            "ms": 320,
            "label": "定向补充",
            "titles": _titles(lens.get("titles", [])),
            "note": f"Industry={lens.get('industry', '')} 定向补充，绕开 Site 域名盲区。",
        }

    def ev_item(it: dict) -> dict:
        src = it.get("source", "")
        date = it.get("date", "")
        return {
            "src": src + (f" · {date}" if date else ""),
            "title": it.get("point", ""),
            "note": "检索证据" if not it.get("inferred") else "推理，不是检索结果",
        }

    support = [ev_item(x) for x in audit.get("supporting", []) or []]
    counter_ev = [ev_item(x) for x in audit.get("contradicting", []) or []]
    evidence = {"support": support, "counter": counter_ev} if (support or counter_ev) else None

    verdict_d = audit.get("verdict", {}) or {}
    card = audit.get("card", {}) or {}
    verdict = None
    if verdict_d:
        level = verdict_d.get("level", "中")
        verdict = {
            "level": level,
            "score": LEVEL_SCORE.get(level, 50),
            "summary": verdict_d.get("reason", ""),
            "rows": [],
            "blind": f"{card.get('blind_count', 0)} 格",
            "counterCount": f"{card.get('counter_count', 0)} 条",
            "drift": card.get("drift_note", ""),
        }

    narrative = None
    if rows:
        nrows = []
        for row in rows:
            tone = ""
            sample = ""
            for col in cols:
                cell = row["cells"].get(col["id"])
                if cell and cell.get("count", 0) > 0:
                    if not tone:
                        tone = cell.get("summary", "")
                    if not sample and cell.get("titles"):
                        sample = cell["titles"][0].get("t", "")
            if not tone:
                continue
            nrows.append(
                {
                    "src": row["name"],
                    "domain": row["domain"],
                    "tone": tone,
                    "sample": sample,
                    "kind": _kind_for(row["name"]),
                }
            )
        if nrows:
            narrative = {"summary": insight, "rows": nrows}

    tabs = []
    if matrix_obj:
        tabs.append({"id": "matrix", "label": "叙事矩阵"})
    if evidence:
        tabs.append({"id": "evidence", "label": "支持与反例"})
    if verdict:
        tabs.append({"id": "card", "label": "诊断卡"})
    if narrative:
        tabs.append({"id": "narrative", "label": "叙事对照"})
    if not tabs:
        tabs.append({"id": "matrix", "label": "叙事矩阵"})

    analysis_obj = {
        "kicker": "01 / 问题分析",
        "title": f"{analysis.get('claim_type', '问题')} · {analysis.get('topic', '')}".strip(" ·"),
        "text": analysis.get("summary", ""),
        "facts": [
            ["问题类型", analysis.get("claim_type", "")],
            ["主题", analysis.get("topic", "")],
            ["是否有争议", "是" if analysis.get("contested") else "否"],
            ["核心检索词", core],
        ],
    }

    return {
        "id": "live",
        "custom": False,
        "claim": claim,
        "claimMeta": f"{analysis.get('claim_type', '')} · {analysis.get('topic', '')}".strip(" ·"),
        "providerLabel": provider_label,
        "analysis": analysis_obj,
        "dims": dims,
        "sources": src_rows,
        "windows": win_rows,
        "coreKeywords": core,
        "probe": probe_obj,
        "queries": queries,
        "direct": direct,
        "counterSearches": counter_searches,
        "deepSearches": deep_searches,
        "crossSearches": cross_searches,
        "industry": industry_obj,
        "matrix": matrix_obj,
        "insight": insight,
        "evidence": evidence,
        "verdict": verdict,
        "narrative": narrative,
        "tabs": tabs,
    }