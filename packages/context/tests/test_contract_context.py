"""contract.py（context 套件）：插件全链路——注册、发现、执行、未注册与缺工厂的错误。"""

import pytest


def test_context_contract_suite_passes_for_builtin(pytester):
    result = pytester.runpytest(
        "--tutelary-contract",
        "context",
        "--tutelary-factory",
        "tutelary.context.governor:ContextGovernor",
    )
    result.assert_outcomes(passed=1)


def test_contract_option_without_factory_gives_usage_error(pytester):
    result = pytester.runpytest("--tutelary-contract", "context")
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["*--tutelary-factory*"])
