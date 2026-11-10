from dataclasses import dataclass


@dataclass(frozen=True)
class Dimension:
    id: str
    name: str
    description: str
    use_when: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "use_when": self.use_when,
        }


DIMENSIONS: list[Dimension] = [
    Dimension("direct", "直接搜索", "直接搜索问题本身，看自然结果与信源分布", "几乎必选，作为基础层"),
    Dimension("multi_source", "多信源对比", "对不同信源分别检索，对比叙事差异与盲区", "论断有争议、不同来源可能说法不同"),
    Dimension("time_evolution", "时间演变", "按多个时间窗检索，看叙事随时间如何变化", "事件跨度较长、叙事可能漂移"),
    Dimension("counter_example", "反例检验", "生成反例查询进行检索，检验论断是否成立", "因果归因、绝对化论断"),
    Dimension("deep_cause", "深层归因", "挖掘深层原因或前提，追问为什么", "因果归因、现象解释"),
    Dimension("cross_validation", "交叉验证", "查多个来源的说法，交叉验证事实", "事实陈述、数据核验"),
]

DIMENSION_BY_ID: dict[str, Dimension] = {d.id: d for d in DIMENSIONS}