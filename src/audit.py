import json

from src.events import audit_event
from src.llm import LLM


AUDIT_SYSTEM = """你是论断审计员。基于对同一论断的多维度、多信源、多时间窗检索证据，给出一个审计结论。
保持克制与诚实：证据不足就说不足，不要为了给出结论而编造证据。
只返回JSON，不要markdown代码块。"""

AUDIT_USER = """论断：{claim}

多维度检索证据：
{dimension_evidence}

信源×时间叙事矩阵：
{matrix_evidence}

矩阵统计：空格（盲区格）{blind_cells} 个；整行无结果的信源：{index_gap_sources}；其中疑似“结果缺少日期、时间窗过滤后为空”的假盲区信源：{date_gap_sources}

请给出：
1. supporting：支持该论断的证据清单（每条含 point 要点、source 信源、date 日期），最多5条
2. contradicting：反对或反例证据清单（同上），最多5条
3. verdict：审计结论，level 为 高/中/中低/低，reason 说明理由并引用证据而非空谈
4. drift_note：叙事是否随时间漂移的一句话概括（若无明显漂移写“未观察到明显漂移”）

返回JSON：
{{"supporting": [{{"point": "", "source": "", "date": ""}}], "contradicting": [{{"point": "", "source": "", "date": ""}}], "verdict": {{"level": "", "reason": ""}}, "drift_note": ""}}"""


class Audit:
    def __init__(self, llm: LLM, emit):
        self.llm = llm
        self.emit = emit

    def build(self, claim: str, dimension_results: list[dict], matrix: dict) -> dict:
        dimension_evidence = []
        for dr in dimension_results:
            dimension_evidence.append(
                {
                    "dimension": dr["dimension"]["name"],
                    "queries": [
                        {
                            "query": qr["query"],
                            "intent": qr.get("intent", ""),
                            "count": qr["count"],
                            "top": qr.get("titles", []),
                        }
                        for qr in dr["results"]
                    ],
                }
            )

        matrix_evidence = {
            "columns": [c["label"] for c in matrix["columns"]],
            "rows": [
                {
                    "source": r["source"]["name"],
                    "possible_index_gap": r.get("possible_index_gap", False),
                    "empty_reason": r.get("empty_reason", ""),
                    "cells": [
                        {"window": c["window"], "count": c["count"], "narrative": c["narrative"]}
                        for c in r["cells"]
                    ],
                }
                for r in matrix["rows"]
            ],
        }

        result = self.llm.chat_json(
            AUDIT_SYSTEM,
            AUDIT_USER.format(
                claim=claim,
                dimension_evidence=json.dumps(dimension_evidence, ensure_ascii=False),
                matrix_evidence=json.dumps(matrix_evidence, ensure_ascii=False),
                blind_cells=matrix["blind_cells"],
                index_gap_sources="、".join(matrix["index_gap_sources"]) or "无",
                date_gap_sources="、".join(matrix.get("date_gap_sources", [])) or "无",
            ),
        )

        result.setdefault("supporting", [])
        result.setdefault("contradicting", [])
        verdict = result.setdefault("verdict", {"level": "中", "reason": ""})
        result.setdefault("drift_note", "")

        card = {
            "claim": claim,
            "verdict_level": verdict.get("level", ""),
            "blind_count": matrix["blind_cells"],
            "counter_count": len(result["contradicting"]),
            "drift_note": result.get("drift_note", ""),
        }
        result["card"] = card

        self.emit(
            audit_event(
                "audit",
                "审计结论",
                detail={"verdict": verdict, "card": card},
            )
        )
        return result