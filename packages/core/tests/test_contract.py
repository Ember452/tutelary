"""contract.py：插件骨架行为——选项可解析、未就绪套件报明确 UsageError。"""

import pytest


def test_contract_option_on_unready_port_gives_usage_error(pytester):
    result = pytester.runpytest("--tutelary-contract", "memory")
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    # UsageError 走 stderr；消息点名套件未就绪与就绪计划
    result.stderr.fnmatch_lines(["*尚未就绪*"])


def test_without_option_pytest_runs_normally(pytester):
    result = pytester.runpytest()
    assert result.ret == pytest.ExitCode.NO_TESTS_COLLECTED
