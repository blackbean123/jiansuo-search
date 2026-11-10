from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str
    domain: str
    category: str
    hit_rate: int

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "domain": self.domain,
            "category": self.category,
            "hit_rate": self.hit_rate,
        }


EFFECTIVE_SOURCES: list[Source] = [
    Source("腾讯新闻", "news.qq.com", "新闻", 100),
    Source("微博", "weibo.com", "社交", 100),
    Source("百度百科", "baike.baidu.com", "知识", 100),
    Source("36氪", "36kr.com", "科技", 100),
    Source("澎湃新闻", "thepaper.cn", "新闻", 100),
    Source("掘金", "juejin.cn", "科技", 100),
    Source("少数派", "sspai.com", "科技", 100),
    Source("搜狐", "sohu.com", "新闻", 100),
    Source("新浪", "sina.com.cn", "新闻", 100),
    Source("新华社", "xinhuanet.com", "新闻", 100),
    Source("网易", "163.com", "新闻", 83),
    Source("界面新闻", "jiemian.com", "新闻", 83),
    Source("哔哩哔哩", "bilibili.com", "视频", 83),
    Source("人民日报", "people.com.cn", "新闻", 83),
    Source("凤凰网", "ifeng.com", "新闻", 67),
    Source("财新网", "caixin.com", "财经", 67),
]

SOURCE_BY_DOMAIN: dict[str, Source] = {s.domain: s for s in EFFECTIVE_SOURCES}
