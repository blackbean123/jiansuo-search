from datetime import datetime

from src.audit import Audit
from src.events import PipelineCancelled, decision, done_event, error_event, search_event
from src.llm import LLM
from src.matrix import Matrix
from src.planner import Planner
from src.search import search

ADVERSARIAL_DIMENSIONS = ("direct", "counter_example", "deep_cause", "cross_validation")


class Pipeline:
    def __init__(self, llm: LLM, on_event=None, cancel_event=None):
        self.llm = llm
        self.on_event = on_event or (lambda event: None)
        self.cancel_event = cancel_event

    def emit(self, event) -> None:
        self.on_event(event)

    def _check_cancel(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise PipelineCancelled()

    def _industry_lens(self, analysis: dict, core_query: str):
        topic = analysis.get("topic", "") or ""
        if any(k in topic for k in ("政策", "政府", "法规", "监管", "政务")):
            industry, label = "gov", "官方视角"
        elif any(k in topic for k in ("财经", "金融", "经济", "股市")):
            industry, label = "finance", "专业财经视角"
        else:
            return None

        self.emit(
            decision(
                "industry_lens",
                f"补充{label}",
                reason=(
                    f"问题主题为「{topic}」→ 用 Industry={industry} 定向检索官方/专业来源"
                    "（与 Site 不叠加，避免双重约束导致召回过低）"
                ),
            )
        )
        try:
            pages = search(core_query, industry=industry)
        except Exception:
            pages = []
        titles = [{"title": p.title[:60], "site": p.site, "date": p.date[:10], "url": p.url} for p in pages[:5]]
        self.emit(
            search_event(
                "industry_lens",
                f"{label}：{core_query}",
                detail={
                    "dimension": label,
                    "query": core_query,
                    "intent": "定向补充官方/专业视角",
                    "site": "",
                    "freshness": "",
                    "industry": industry,
                    "count": len(pages),
                    "top": titles[:3],
                },
            )
        )
        return {
            "industry": industry,
            "label": label,
            "query": core_query,
            "count": len(pages),
            "titles": titles,
        }

    def run(self, claim: str) -> dict:
        started = datetime.now()
        try:
            self._check_cancel()
            planner = Planner(self.llm, self.emit)

            analysis = planner.analyze(claim)
            dimensions = planner.choose_dimensions(claim, analysis)
            sources = planner.choose_sources(claim, analysis)
            date_profile = planner.probe_time_profile(claim)
            windows = planner.infer_time_windows(claim, analysis, date_profile)
            self._check_cancel()

            sources = sources[:6]
            windows = windows[:4]

            dimension_results = []
            for dim in dimensions:
                self._check_cancel()
                if dim.id not in ADVERSARIAL_DIMENSIONS:
                    continue
                queries = planner.generate_queries(claim, dim, analysis)
                query_results = []
                for q in queries:
                    self._check_cancel()
                    try:
                        pages = search(q["query"])
                    except Exception:
                        pages = []
                    query_results.append(
                        {
                            "query": q["query"],
                            "intent": q.get("intent", ""),
                            "count": len(pages),
                            "titles": [
                                {"title": p.title[:60], "site": p.site, "date": p.date[:10], "url": p.url}
                                for p in pages[:5]
                            ],
                        }
                    )
                    self.emit(
                        search_event(
                            dim.id,
                            f"{dim.name}：{q['query']}",
                            detail={
                                "dimension": dim.name,
                                "query": q["query"],
                                "intent": q.get("intent", ""),
                                "site": "",
                                "freshness": "",
                                "count": len(pages),
                                "top": [
                                    {"title": p.title[:60], "site": p.site, "date": p.date[:10], "url": p.url}
                                    for p in pages[:3]
                                ],
                            },
                        )
                    )
                dimension_results.append(
                    {
                        "dimension": dim.to_dict(),
                        "queries": [q["query"] for q in queries],
                        "results": query_results,
                    }
                )

            direct_queries = [
                qr["query"]
                for dr in dimension_results
                if dr["dimension"]["id"] == "direct"
                for qr in dr["results"]
            ]
            core_query = (
                analysis.get("core_keywords")
                or (direct_queries[0] if direct_queries else claim)
            )

            self._check_cancel()
            lens = self._industry_lens(analysis, core_query)
            if lens:
                dimension_results.append(
                    {
                        "dimension": {
                            "id": "industry_lens",
                            "name": lens["label"],
                            "description": f"Industry={lens['industry']} 定向补充",
                            "use_when": "",
                        },
                        "queries": [lens["query"]],
                        "results": [
                            {
                                "query": lens["query"],
                                "intent": "定向补充官方/专业视角",
                                "count": lens["count"],
                                "titles": lens["titles"],
                            }
                        ],
                    }
                )

            self._check_cancel()
            matrix = Matrix(self.llm, self.emit, cancel_event=self.cancel_event).build(
                claim, core_query, sources, windows
            )
            self._check_cancel()
            audit = Audit(self.llm, self.emit).build(claim, dimension_results, matrix)

            result = {
                "claim": claim,
                "timestamp": started.isoformat(timespec="seconds"),
                "analysis": analysis,
                "dimensions": [{"id": d.id, "name": d.name} for d in dimensions],
                "dimensions_detail": getattr(planner, "dimension_detail", {}),
                "sources_detail": getattr(planner, "source_detail", []),
                "sources_note": getattr(planner, "source_note", ""),
                "core_query": core_query,
                "sources": [s.to_dict() for s in sources],
                "time_probe": date_profile,
                "time_windows": windows,
                "industry_lens": lens,
                "dimension_results": dimension_results,
                "matrix": matrix,
                "audit": audit,
            }

            self.emit(
                done_event(
                    "深度搜索完成",
                    detail={
                        "claim": claim,
                        "matrix_rows": len(matrix["rows"]),
                        "matrix_columns": len(matrix["columns"]),
                        "verdict_level": audit["card"]["verdict_level"],
                    },
                )
            )
            return result
        except PipelineCancelled:
            raise
        except Exception as e:
            self.emit(error_event(f"{type(e).__name__}: {e}"))
            raise