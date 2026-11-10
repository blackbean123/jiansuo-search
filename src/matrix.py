from src.events import PipelineCancelled, matrix_cell
from src.llm import LLM
from src.search import search
from src.sites import Source


BATCH_NARRATIVE_SYSTEM = """你是叙事提炼者。给定同一信源在多个时间窗下的检索结果，为每个时间窗各提炼一句话的主流叙事（每句不超过40字）。
如实概括标题与摘要信息，不要编造；某窗口无结果则对应叙事为空字符串；某窗口结果说法明显不一致时，概括为“多种说法并存”。
只返回JSON，不要markdown代码块。"""

BATCH_NARRATIVE_USER = """论断：{claim}
信源：{source}
时间窗与检索结果：
{window_blocks}

返回JSON（narratives 数组顺序与时间窗顺序一致，无结果的窗口 narrative 为空字符串）：
{{"narratives": [{{"narrative": ""}}]}}"""


SINGLE_NARRATIVE_SYSTEM = """你是叙事提炼者。把同一信源在同一时期关于某论断的多条搜索结果，浓缩成一句话的主流叙事（不超过40字）。
如实概括标题与摘要信息，不要编造；若结果说法明显不一致，概括为“多种说法并存”。只输出这一句话，不要任何前后缀。"""

SINGLE_NARRATIVE_USER = """论断：{claim}
信源：{source}
时间窗：{window}
搜索结果：
{results}

请给出一句话的主流叙事概括。"""

DATE_GAP_REASON = "该信源结果缺少日期信息，时间窗过滤后为空（疑似日期缺失导致的假盲区）"
INDEX_GAP_REASON = "该信源对当前问题无结果或索引缺失"


class Matrix:
    def __init__(self, llm: LLM, emit, cancel_event=None):
        self.llm = llm
        self.emit = emit
        self.cancel_event = cancel_event

    def _check_cancel(self):
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise PipelineCancelled()

    def build(self, claim: str, core_query: str, sources: list[Source], windows: list[dict]) -> dict:
        rows = []
        blind_cells = 0
        index_gap_sources = []
        date_gap_sources = []

        for row_index, src in enumerate(sources):
            self._check_cancel()
            raw = []
            for window in windows:
                self._check_cancel()
                freshness = window.get("freshness", "")
                try:
                    pages = search(core_query, site=src.domain, freshness=freshness)
                except Exception:
                    pages = []
                raw.append((window, freshness, pages))

            self._check_cancel()
            narratives = self._row_narratives(claim, src, raw)

            cells = []
            row_total = 0
            for idx, (window, freshness, pages) in enumerate(raw):
                count = len(pages)
                row_total += count
                if count == 0:
                    narrative = ""
                    empty = True
                    blind_cells += 1
                else:
                    empty = False
                    narrative = narratives[idx] if idx < len(narratives) else ""
                    if not narrative:
                        narrative = f"{count}条"
                cell = {
                    "window": window.get("label", ""),
                    "freshness": freshness,
                    "count": count,
                    "empty": empty,
                    "narrative": narrative,
                    "titles": [
                        {"title": p.title[:60], "site": p.site, "date": p.date[:10], "url": p.url} for p in pages[:3]
                    ],
                }
                cells.append(cell)
                self.emit(
                    matrix_cell(
                        "matrix",
                        f"{src.name} × {window.get('label', '')}",
                        detail=dict(cell, source=src.to_dict(), row_index=row_index, col_index=idx),
                    )
                )

            row_fallback = None
            empty_reason = ""
            if row_total == 0:
                index_gap_sources.append(src.name)
                try:
                    fallback_pages = search(core_query, site=src.domain)
                except Exception:
                    fallback_pages = []
                if fallback_pages:
                    date_gap_sources.append(src.name)
                    empty_reason = DATE_GAP_REASON
                else:
                    empty_reason = INDEX_GAP_REASON
                row_fallback = {
                    "query": core_query,
                    "site": src.domain,
                    "count": len(fallback_pages),
                    "titles": [
                        {"title": p.title[:60], "site": p.site, "date": p.date[:10] or "无日期", "url": p.url}
                        for p in fallback_pages[:3]
                    ],
                }
                self.emit(
                    matrix_cell(
                        "matrix",
                        f"{src.name} 整行为空的原因诊断",
                        detail={"empty_reason": empty_reason, "source": src.to_dict(), "row_index": row_index},
                    )
                )

            rows.append(
                {
                    "source": src.to_dict(),
                    "cells": cells,
                    "row_total": row_total,
                    "possible_index_gap": row_total == 0,
                    "empty_reason": empty_reason,
                    "fallback": row_fallback,
                }
            )

        return {
            "columns": [{"label": w.get("label", ""), "freshness": w.get("freshness", "")} for w in windows],
            "rows": rows,
            "blind_cells": blind_cells,
            "index_gap_sources": index_gap_sources,
            "date_gap_sources": date_gap_sources,
        }

    def _row_narratives(self, claim: str, src: Source, raw: list) -> list[str]:
        n = len(raw)
        window_blocks = []
        for idx, (window, freshness, pages) in enumerate(raw):
            label = window.get("label", "")
            fresh = freshness or "不限"
            if pages:
                results_text = "\n".join(f"- {p.title}：{p.passage[:80]}" for p in pages[:5])
                window_blocks.append(f"窗口{idx}（{label}，{fresh}）：\n{results_text}")
            else:
                window_blocks.append(f"窗口{idx}（{label}，{fresh}）：无结果")

        try:
            result = self.llm.chat_json(
                BATCH_NARRATIVE_SYSTEM,
                BATCH_NARRATIVE_USER.format(
                    claim=claim,
                    source=src.name,
                    window_blocks="\n".join(window_blocks),
                ),
            )
            arr = result.get("narratives", [])
            out: list[str] = []
            for idx in range(n):
                if idx < len(arr) and isinstance(arr[idx], dict):
                    out.append((arr[idx].get("narrative") or "").strip().replace("\n", " ")[:80])
                elif idx < len(arr) and isinstance(arr[idx], str):
                    out.append(arr[idx].strip().replace("\n", " ")[:80])
                else:
                    out.append("")
            has_pages = any(raw[i][2] for i in range(n))
            has_narrative = any(out[i] for i in range(n) if raw[i][2])
            if has_pages and not has_narrative:
                raise ValueError("batch narratives empty")
            return out
        except Exception:
            return self._fallback_narratives(claim, src, raw)

    def _fallback_narratives(self, claim: str, src: Source, raw: list) -> list[str]:
        out: list[str] = []
        for window, freshness, pages in raw:
            if not pages:
                out.append("")
                continue
            try:
                text = self.llm.chat(
                    SINGLE_NARRATIVE_SYSTEM,
                    SINGLE_NARRATIVE_USER.format(
                        claim=claim,
                        source=src.name,
                        window=window.get("label", ""),
                        results="\n".join(f"- {p.title}：{p.passage[:100]}" for p in pages[:6]),
                    ),
                    temperature=0.2,
                )
                out.append(text.strip().replace("\n", " ")[:80])
            except Exception:
                out.append("")
        return out