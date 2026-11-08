import base64
import os

import pytest

from app.services import wecom_crypto as crypto
from app.services.wecom import split_text
from app.services.wecom_chat import parse_command, parse_incoming

KEY = base64.b64encode(os.urandom(32)).decode().rstrip("=")
CORP = "wwtestcorp"


def test_crypto_roundtrip_and_signature():
    xml = "<xml><Content>你好，报价能不能便宜点</Content></xml>"
    enc = crypto.encrypt(KEY, xml, CORP)
    assert crypto.decrypt(KEY, enc, CORP) == xml
    sig = crypto._sha1("tok", "123", "abc", enc)
    assert crypto.verify_signature("tok", sig, "123", "abc", enc)
    assert not crypto.verify_signature("tok", "bad", "123", "abc", enc)


def test_crypto_rejects_wrong_corp():
    enc = crypto.encrypt(KEY, "<xml/>", CORP)
    with pytest.raises(ValueError):
        crypto.decrypt(KEY, enc, "other")


def test_url_verify_returns_echostr_plain():
    echo = "1234567890"
    enc = crypto.encrypt(KEY, echo, CORP)
    sig = crypto._sha1("tok", "1", "n", enc)
    assert crypto.verify_url("tok", KEY, CORP, sig, "1", "n", enc) == echo


def test_parse_incoming_text_voice_enter():
    text = "<xml><MsgType>text</MsgType><FromUserName>zs</FromUserName><MsgId>9</MsgId><Content> 1 </Content></xml>"
    m = parse_incoming(text)
    assert (m.kind, m.userid, m.content, m.msg_id) == ("text", "zs", "1", "9")
    voice = "<xml><MsgType>voice</MsgType><FromUserName>zs</FromUserName><Recognition>我想了解价格</Recognition></xml>"
    assert parse_incoming(voice).content == "我想了解价格"
    assert parse_incoming("<xml><MsgType>voice</MsgType><FromUserName>zs</FromUserName></xml>").content == ""
    enter = "<xml><MsgType>event</MsgType><Event>enter_agent</Event><FromUserName>zs</FromUserName></xml>"
    assert parse_incoming(enter).kind == "enter"
    assert parse_incoming("<xml><MsgType>image</MsgType><FromUserName>zs</FromUserName></xml>") is None


IDS = ["S01", "S02", "S03"]


@pytest.mark.parametrize(
    "text,ongoing,expected",
    [
        ("帮助", False, ("help", None)),
        ("菜单", True, ("menu", None)),
        ("1", False, ("start", "S01")),
        ("3", False, ("start", "S03")),
        ("s02", False, ("start", "S02")),
        ("开始 S03", False, ("start", "S03")),
        ("9", False, ("unknown", None)),
        ("1", True, ("message", "1")),
        ("求助", True, ("hint", None)),
        ("求助", False, ("help", None)),
        ("结束", True, ("end", None)),
        ("你好，报价能便宜吗", True, ("message", "你好，报价能便宜吗")),
    ],
)
def test_parse_command(text, ongoing, expected):
    assert parse_command(text, ongoing, IDS) == expected


def test_split_text_respects_bytes():
    text = "价格异议" * 800
    chunks = split_text(text, 2000)
    assert "".join(chunks) == text
    assert all(len(c.encode("utf-8")) <= 2000 for c in chunks)
    assert split_text("") == [""]
