import asyncio
import json
import threading
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.routing import Route

from src.config import DEFAULT_PROVIDER, PROVIDERS
from src.events import Event, PipelineCancelled
from src.llm import LLM
from src.pipeline import Pipeline
from src.web_adapter import build_case

ROOT = Path(__file__).parent
PROTOTYPE = ROOT / "web" / "index.html"
CASE_MI = ROOT / "web" / "cases" / "mi.js"
CASE_FEIXIN = ROOT / "web" / "cases" / "feixin.js"

PROVIDER_LABELS = {
    "deepseek": "DeepSeek",
    "glm": "GLM",
    "hunyuan": "混元",
    "custom": "自定义",
}


def resolve_llm(provider: str):
    name = provider if provider in PROVIDERS else DEFAULT_PROVIDER
    cfg = PROVIDERS.get(name)
    if cfg is None or not cfg.api_key:
        name = DEFAULT_PROVIDER
    return LLM(name), PROVIDER_LABELS.get(name, name)


def progress_text(event: Event) -> str:
    data = event.to_dict()
    etype = data.get("type")
    stage = data.get("stage")
    title = data.get("title", "")
    if etype == "decision":
        mapping = {
            "analyze": "正在分析问题…",
            "dimensions": "正在选择分析维度…",
            "sources": "正在选择信源…",
            "time_probe": "正在探测真实时间分布…",
            "time_windows": "正在推断时间窗…",
            "industry_lens": "正在补充官方/专业视角…",
        }
        if stage in mapping:
            return mapping[stage]
        if stage == "queries":
            return f"正在生成搜索词：{title}"
        return f"决策：{title}"
    if etype == "search":
        return f"检索中：{title}"
    if etype == "matrix_cell":
        return f"填充矩阵：{title}"
    if etype == "audit":
        return "正在生成审计结论…"
    if etype == "done":
        return "完成"
    if etype == "error":
        return f"错误：{title}"
    return title or "运行中"


async def index(request: Request):
    return FileResponse(
        str(PROTOTYPE),
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


async def case_mi(request: Request):
    return FileResponse(
        str(CASE_MI),
        media_type="application/javascript; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


async def case_feixin(request: Request):
    return FileResponse(
        str(CASE_FEIXIN),
        media_type="application/javascript; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


async def health(request: Request):
    return JSONResponse({"ok": True, "default_provider": DEFAULT_PROVIDER})


async def run(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    claim = (body.get("claim") or "").strip()
    provider = (body.get("provider") or "").strip()
    if not claim:
        return JSONResponse({"error": "claim required"}, status_code=400)

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    cancel_event = threading.Event()

    def on_event(event):
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def worker():
        try:
            llm, label = resolve_llm(provider)
            result = Pipeline(llm, on_event=on_event, cancel_event=cancel_event).run(claim)
            case = build_case(claim, result, label)
            loop.call_soon_threadsafe(queue.put_nowait, {"_case": case, "_label": label})
        except PipelineCancelled:
            loop.call_soon_threadsafe(queue.put_nowait, {"_aborted": True})
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, {"_error": f"{type(exc).__name__}: {exc}"})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    async def gen():
        executor = loop.run_in_executor(None, worker)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, Event):
                    payload = {"type": "progress", "message": progress_text(item), "event": item.to_dict()}
                elif isinstance(item, dict) and "_case" in item:
                    payload = {"type": "case", "case": item["_case"], "provider": item.get("_label", "")}
                elif isinstance(item, dict) and "_aborted" in item:
                    payload = {"type": "aborted"}
                elif isinstance(item, dict) and "_error" in item:
                    payload = {"type": "error", "message": item["_error"]}
                else:
                    payload = {"type": "progress", "message": str(item)}
                yield "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
            await executor
        finally:
            cancel_event.set()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


app = Starlette(
    routes=[
        Route("/", index, methods=["GET"]),
        Route("/case/mi.js", case_mi, methods=["GET"]),
        Route("/case/feixin.js", case_feixin, methods=["GET"]),
        Route("/api/health", health, methods=["GET"]),
        Route("/api/run", run, methods=["POST"]),
    ]
)