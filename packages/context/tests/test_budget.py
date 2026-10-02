"""budget.py：份额校验、额度换算与配置适配。"""

import pytest

from tutelary.context.budget import Budget, BudgetConfig
from tutelary.context.errors import ContextBudgetError


def test_default_shares_add_up_to_one():
    budget = Budget(total=8000)
    assert budget.section_tokens("history") == 4800
    assert budget.section_tokens("system") == 800
    assert budget.section_tokens("tools") == 800


def test_section_tokens_are_integer_floors():
    budget = Budget(total=1000, system=0.1, history=0.6, tools=0.1, memory=0.1, reserve=0.1)
    assert budget.section_tokens("history") == 600


def test_non_positive_total_raises():
    with pytest.raises(ContextBudgetError, match="必须为正"):
        Budget(total=0)


def test_share_drift_raises():
    with pytest.raises(ContextBudgetError, match=r"1\.0"):
        Budget(total=1000, system=0.2, history=0.6, tools=0.1, memory=0.1, reserve=0.1)


def test_budget_is_frozen():
    budget = Budget(total=1000)
    with pytest.raises(AttributeError):
        budget.total = 2000  # type: ignore[misc]


def test_budget_config_adapts_dict():
    budget = BudgetConfig.model_validate({"total": 4000})
    assert budget.total == 4000
    with pytest.raises(ValueError, match="非法预算字段"):
        BudgetConfig.model_validate({"total": 4000, "unknown": 1})
