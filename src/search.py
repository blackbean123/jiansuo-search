import json
from dataclasses import dataclass

from tencentcloud.common import credential
from tencentcloud.common.common_client import CommonClient
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile

from src.config import TENCENT_SECRET_ID, TENCENT_SECRET_KEY


@dataclass
class Page:
    title: str
    site: str
    date: str
    passage: str
    url: str
    score: float

    def brief(self) -> dict:
        return {
            "title": self.title[:80],
            "site": self.site,
            "date": self.date[:10] if self.date else "",
            "passage": self.passage[:120],
            "url": self.url[:100],
        }


_client = None


def _get_client() -> CommonClient:
    global _client
    if _client is None:
        cred = credential.Credential(TENCENT_SECRET_ID, TENCENT_SECRET_KEY)
        hp = HttpProfile()
        hp.endpoint = "wsa.tencentcloudapi.com"
        cp = ClientProfile()
        cp.http_profile = hp
        _client = CommonClient("wsa", "2025-05-08", cred, "", profile=cp)
    return _client


def search(
    query: str,
    mode: int = 2,
    cnt: int = 10,
    site: str = "",
    freshness: str = "",
    industry: str = "",
) -> list[Page]:
    client = _get_client()
    params: dict = {"Query": query, "Mode": mode, "Cnt": cnt}
    if site:
        params["Site"] = site
    if freshness:
        params["Freshness"] = freshness
    if industry:
        params["Industry"] = industry
    res = client.call_json("SearchPro", params)
    resp = res.get("Response", res)
    pages_raw = resp.get("Pages", [])
    results: list[Page] = []
    for p_raw in pages_raw:
        try:
            p = json.loads(p_raw) if isinstance(p_raw, str) else p_raw
        except (json.JSONDecodeError, TypeError):
            continue
        results.append(
            Page(
                title=p.get("title", ""),
                site=p.get("site", ""),
                date=p.get("date", ""),
                passage=p.get("passage", "") or "",
                url=p.get("url", ""),
                score=float(p.get("score", 0) or 0),
            )
        )
    return results