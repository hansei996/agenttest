"""被假 agent 修的小模块：故意用了会炸的下标取值。"""


def current_user(payload):
    user = payload["user"]
    return user['id']


def display_name(payload):
    user = payload["user"]
    return user['name']
