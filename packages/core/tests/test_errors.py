"""errors.py：错误层级与消息保真。"""

from tutelary.core.errors import (
    BusContractError,
    CircularRequirementError,
    ConfigValidationError,
    DuplicatePortError,
    MissingPortError,
    TutelaryError,
)


def test_all_typed_errors_subclass_tutelary_error():
    error_types = (
        MissingPortError,
        DuplicatePortError,
        CircularRequirementError,
        ConfigValidationError,
        BusContractError,
    )
    assert all(issubclass(error_type, TutelaryError) for error_type in error_types)


def test_message_is_preserved():
    assert str(MissingPortError("端口 X 缺失")) == "端口 X 缺失"
