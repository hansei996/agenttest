"""示例里 run_tests 的检查目标（假 agent 只读它的源码，不真跑 pytest）。"""


def test_current_user_reads_id():
    from src.auth import current_user

    assert current_user({"user": {"id": 7}}) == 7


def test_display_name_reads_name():
    from src.auth import display_name

    assert display_name({"user": {"name": "ada"}}) == "ada"
