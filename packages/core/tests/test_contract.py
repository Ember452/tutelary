"""contract.py：插件骨架行为——选项可解析、未注册套件报明确 UsageError。"""

import pytest


def test_contract_option_on_unregistered_port_gives_usage_error(pytester):
    result = pytester.runpytest("--tutelary-contract", "not-a-port")
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    # UsageError 走 stderr；消息点名未注册与注册途径
    result.stderr.fnmatch_lines(["*未注册*"])


def test_without_option_pytest_runs_normally(pytester):
    result = pytester.runpytest()
    assert result.ret == pytest.ExitCode.NO_TESTS_COLLECTED
