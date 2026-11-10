import json
from collections import Counter

from src.dimensions import DIMENSIONS, DIMENSION_BY_ID, Dimension
from src.events import decision
from src.llm import LLM
from src.search import search
from src.sites import EFFECTIVE_SOURCES, SOURCE_BY_DOMAIN, Source


ANALYZE_SYSTEM = """你是论断分析专家。分析用户给出的问题或论断，判断它需要怎样的研究策略。
只返回JSON，不要markdown代码块。"""

ANALYZE_USER = """问题/论断：{claim}

请分析：
1. claim_type：问题类型（事实查询/因果归因/价值评价/趋势预测/开放研究）
2. topic：主题领域（科技/社会/历史/财经/政策/文化/其他）
3. contested：是否存在争议或多种叙事（true/false）
4. summary：一句话概括你打算怎么研究它
5. core_keywords：把论断提炼成 2-3 个最核心关键词（用空格分隔，不加引号），用于跨信源、跨时间窗的宽泛检索，要尽量保证召回

返回JSON：
{{"claim_type": "", "topic": "", "contested": false, "summary": "", "core_keywords": ""}}"""


DIMENSION_SYSTEM = """你是检索策略规划师。从给出的维度库中为当前问题挑选合适的分析维度。
只返回JSON，不要markdown代码块。"""

DIMENSION_USER = """问题/论断：{claim}
问题分析：{analysis}

可选维度库：
{dimensions}

请从中选择 2-4 个维度组成分析计划。注意：并非所有问题都需要全部维度；简单事实查询可能只需少数维度。对每个选择的维度说明理由，对未选择的也要说明为何不选。

返回JSON：
{{"chosen": [{{"id": "", "reason": ""}}], "not_chosen": [{{"id": "", "reason": ""}}]}}"""


SOURCE_SYSTEM = """你是信源选择策略师。基于实测可命中的信源库，为当前问题挑选用于多信源对比的信源。
注意规避与论断存在利益关联的信源（如评价某公司产品时，该公司自家媒体有立场风险）。
只返回JSON，不要markdown代码块。"""

SOURCE_USER = """问题/论断：{claim}
主题：{topic}

可用信源库（均为实测在元宝搜索中可命中的域名，hit_rate 为命中率百分比）：
{sources}

请选择 4-5 个信源，尽量覆盖不同立场与类型（新闻/社交/科技/知识/视频等），优先高命中信源，并规避利益关联信源。不要选择未列出的域名。

返回JSON：
{{"chosen": [{{"domain": "", "reason": ""}}], "note": ""}}"""


TIME_SYSTEM = """你是时间线分析专家。结合真实检索的日期分布与问题语义，判断问题是否适合做时间切分，并给出时间窗。
只返回JSON，不要markdown代码块。"""

TIME_USER = """问题/论断：{claim}
问题分析：{analysis}
真实检索日期分布：{date_profile}

如果该问题涉及可追踪的历史叙事，请结合“真实检索日期分布”与问题语义，推断相关时间范围并切分为 3-4 个时间窗。每个窗口给出 label 和 freshness。
注意：窗口应尽量对齐真实数据覆盖的区间，避免切出必然无数据的空窗（否则会产生假盲区）；若真实数据集中在某一段，可在该段内多切分。
freshness 格式三选一：日期范围 "YYYY-MM-DD,YYYY-MM-DD"；"y5" 表示最近5年；"dN" 表示最近N天。
如果真实检索几乎没有带日期的结果，或该问题不适合做时间切分（如当下天气、纯事实查询、历史太久远无可靠分期），返回空窗口列表。

返回JSON：
{{"range": "", "windows": [{{"label": "", "freshness": "", "reason": ""}}]}}"""


QUERY_SYSTEM = """你是搜索词生成助手。为指定分析维度生成精确的中文搜索词。
搜索词用空格分隔关键词，不加引号，不加 site: 前缀。只返回JSON，不要markdown代码块。"""

QUERY_USER = """问题/论断：{claim}
问题分析：{analysis}
当前分析维度：{dim_name} —— {dim_description}

请为该维度生成 1-2 个搜索词，并说明每个搜索词的意图。

返回JSON：
{{"queries": [{{"query": "", "intent": ""}}]}}"""


class Planner:
    def __init__(self, llm: LLM, emit):
        self.llm = llm
        self.emit = emit

    def analyze(self, claim: str) -> dict:
        self.emit(decision("analyze", "分析问题", reason="正在判断问题类型与研究策略"))
        result = self.llm.chat_json(ANALYZE_SYSTEM, ANALYZE_USER.format(claim=claim))
        self.emit(decision("analyze", "问题分析", detail=result, reason=result.get("summary", "")))
        return result

    def choose_dimensions(self, claim: str, analysis: dict) -> list[Dimension]:
        dimensions_text = "\n".join(
            f"- {d.id}（{d.name}）：{d.description}；适用：{d.use_when}" for d in DIMENSIONS
        )
        result = self.llm.chat_json(
            DIMENSION_SYSTEM,
            DIMENSION_USER.format(
                claim=claim,
                analysis=json.dumps(analysis, ensure_ascii=False),
                dimensions=dimensions_text,
            ),
        )
        chosen_entries = [c for c in result.get("chosen", []) if c.get("id") in DIMENSION_BY_ID]
        chosen = [DIMENSION_BY_ID[c["id"]] for c in chosen_entries]
        if not chosen:
            chosen = [DIMENSION_BY_ID["direct"]]
            chosen_entries = [{"id": "direct", "reason": "默认基础层"}]
        reason_by_id = {c["id"]: c.get("reason", "") for c in chosen_entries}
        not_chosen = []
        for x in result.get("not_chosen", []):
            dim = DIMENSION_BY_ID.get(x.get("id", ""))
            not_chosen.append({
                "id": x.get("id", ""),
                "name": dim.name if dim else x.get("id", ""),
                "reason": x.get("reason", ""),
            })
        detail = {
            "chosen": [
                {"id": c.id, "name": c.name, "reason": reason_by_id.get(c.id, "")}
                for c in chosen
            ],
            "not_chosen": not_chosen,
        }
        self.dimension_detail = detail
        self.emit(
            decision(
                "dimensions",
                "选择分析维度",
                detail=detail,
                reason="选择了 " + "、".join(c.name for c in chosen),
            )
        )
        return chosen

    def choose_sources(self, claim: str, analysis: dict) -> list[Source]:
        sources_text = "\n".join(
            f"- {s.name}（{s.domain}）类型：{s.category}，命中率：{s.hit_rate}%"
            for s in EFFECTIVE_SOURCES
        )
        result = self.llm.chat_json(
            SOURCE_SYSTEM,
            SOURCE_USER.format(
                claim=claim,
                topic=analysis.get("topic", ""),
                sources=sources_text,
            ),
        )
        chosen_sources: list[Source] = []
        chosen_detail = []
        for x in result.get("chosen", []):
            domain = x.get("domain", "")
            if domain in SOURCE_BY_DOMAIN:
                src = SOURCE_BY_DOMAIN[domain]
                chosen_sources.append(src)
                chosen_detail.append({"name": src.name, "domain": src.domain, "reason": x.get("reason", "")})
        if not chosen_sources:
            chosen_sources = EFFECTIVE_SOURCES[:5]
            chosen_detail = [{"name": s.name, "domain": s.domain, "reason": "默认选择"} for s in chosen_sources]
        self.source_detail = chosen_detail
        self.source_note = result.get("note", "")
        self.emit(
            decision(
                "sources",
                "选择信源",
                detail={"chosen": chosen_detail, "note": result.get("note", "")},
                reason="选择了 " + "、".join(s.name for s in chosen_sources),
            )
        )
        return chosen_sources

    def probe_time_profile(self, claim: str) -> dict:
        self.emit(
            decision(
                "time_probe",
                "探测真实时间分布",
                reason="先做一次自然检索，用真实结果的日期分布校准时间窗，避免切出必然无数据的空窗（假盲区）",
            )
        )
        try:
            pages = search(claim)
        except Exception:
            pages = []
        dates = sorted(p.date[:10].replace("/", "-") for p in pages if p.date)
        year_histogram = dict(sorted(Counter(d[:4] for d in dates).items()))
        profile = {
            "count": len(pages),
            "min_date": dates[0] if dates else "",
            "max_date": dates[-1] if dates else "",
            "year_histogram": year_histogram,
            "sample_titles": [
                {"title": p.title[:60], "site": p.site, "date": p.date[:10], "url": p.url} for p in pages[:5]
            ],
        }
        if dates:
            reason = (
                f"真实结果 {profile['count']} 条，覆盖 {profile['min_date']} ~ "
                f"{profile['max_date']}，年份分布 {year_histogram}"
            )
        else:
            reason = "自然检索未返回带日期的结果，时间窗将仅依据问题语义推断"
        self.emit(decision("time_probe", "时间分布探测结果", detail=profile, reason=reason))
        return profile

    def infer_time_windows(self, claim: str, analysis: dict, date_profile: dict | None = None) -> list[dict]:
        result = self.llm.chat_json(
            TIME_SYSTEM,
            TIME_USER.format(
                claim=claim,
                analysis=json.dumps(analysis, ensure_ascii=False),
                date_profile=json.dumps(date_profile or {}, ensure_ascii=False),
            ),
        )
        windows = []
        for w in result.get("windows", []):
            if not isinstance(w, dict):
                continue
            windows.append(
                {
                    "label": w.get("label") or "未命名窗口",
                    "freshness": w.get("freshness", ""),
                    "reason": w.get("reason", ""),
                }
            )
        if not windows:
            windows = [{"label": "不限", "freshness": "", "reason": "该问题不适合做时间切分，不做时间窗过滤"}]
        time_range = result.get("range", "")
        self.emit(
            decision(
                "time_windows",
                "推断时间窗",
                detail={"range": time_range, "windows": windows},
                reason=(time_range + "：" if time_range else "") + "、".join(w["label"] for w in windows),
            )
        )
        return windows

    def generate_queries(self, claim: str, dim: Dimension, analysis: dict) -> list[dict]:
        result = self.llm.chat_json(
            QUERY_SYSTEM,
            QUERY_USER.format(
                claim=claim,
                analysis=json.dumps(analysis, ensure_ascii=False),
                dim_name=dim.name,
                dim_description=dim.description,
            ),
        )
        queries = [q for q in result.get("queries", []) if isinstance(q, dict) and q.get("query")]
        if not queries:
            queries = [{"query": claim, "intent": "默认使用原问题"}]
        self.emit(
            decision(
                "queries",
                f"{dim.name} 的搜索词",
                detail={"dimension": dim.name, "queries": queries},
                reason="；".join(q.get("intent", "") for q in queries),
            )
        )
        return queries