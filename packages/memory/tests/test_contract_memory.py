"""contract.py（memory 套件）：插件全链路——注册、发现、执行。"""


def test_memory_contract_suite_passes_for_builtin(pytester):
    result = pytester.runpytest(
        "--tutelary-contract",
        "memory",
        "--tutelary-factory",
        "tutelary.memory.provider:MarkdownProvider",
    )
    result.assert_outcomes(passed=1)
