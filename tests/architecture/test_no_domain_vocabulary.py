"""门禁 5（docs/05 §4）：core 源码禁止出现具体产品/场景词——内核是语法不是管家。

清单随外部域词汇的出现而增长；命中即说明内核长出了业务词汇，回 docs/03 砍。
"""

from _walk import package_sources

FORBIDDEN_VOCABULARY = (
    "annona",
    "cordis",
    "e2b",
    "flowcoder",
    "keel",
    "koishi",
    "langchain",
    "letta",
    "mem0",
    "zep",
)


def test_no_domain_vocabulary():
    violations: list[str] = []
    for source in package_sources("core"):
        text = source.path.read_text(encoding="utf-8").lower()
        for word in FORBIDDEN_VOCABULARY:
            if word in text:
                violations.append(f"{source.path}: 出现领域词 '{word}'")
    assert not violations, "core 长出了业务词汇：\n" + "\n".join(violations)
