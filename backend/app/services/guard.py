"""数据安全护栏：进入模型前的敏感信息脱敏（见 doc/05-data-and-security.md）。"""

import re

_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[邮箱]"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[身份证号]"),
    (re.compile(r"(?<!\d)\d{16,19}(?!\d)"), "[银行卡号]"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[手机号]"),
    (re.compile(r"(?<!\d)0\d{2,3}-?\d{7,8}(?!\d)"), "[电话]"),
]


def mask_pii(text: str) -> str:
    for pattern, repl in _RULES:
        text = pattern.sub(repl, text)
    return text
