"""企业微信回调加解密（与企微官方 WXBizMsgCrypt 算法一致，AES-256-CBC + PKCS7(32)）。"""

import base64
import hashlib
import os
import struct

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def _aes_key(encoding_aes_key: str) -> bytes:
    return base64.b64decode(encoding_aes_key + "=")


def _sha1(*parts: str) -> str:
    return hashlib.sha1("".join(sorted(parts)).encode("utf-8")).hexdigest()


def verify_signature(token: str, signature: str, timestamp: str, nonce: str, encrypted: str) -> bool:
    return _sha1(token, timestamp, nonce, encrypted) == signature


def decrypt(encoding_aes_key: str, encrypted: str, corp_id: str) -> str:
    """解密密文，并校验末尾的 CorpID（接收方标识）。"""
    key = _aes_key(encoding_aes_key)
    dec = Cipher(algorithms.AES(key), modes.CBC(key[:16])).decryptor()
    plain = dec.update(base64.b64decode(encrypted)) + dec.finalize()
    unpadder = padding.PKCS7(256).unpadder()
    plain = unpadder.update(plain) + unpadder.finalize()
    msg_len = struct.unpack(">I", plain[16:20])[0]
    xml = plain[20 : 20 + msg_len].decode("utf-8")
    receive_id = plain[20 + msg_len :].decode("utf-8")
    if receive_id != corp_id:
        raise ValueError("接收方 CorpID 不匹配")
    return xml


def encrypt(encoding_aes_key: str, xml: str, corp_id: str) -> str:
    key = _aes_key(encoding_aes_key)
    body = (
        os.urandom(16)
        + struct.pack(">I", len(xml.encode("utf-8")))
        + xml.encode("utf-8")
        + corp_id.encode("utf-8")
    )
    padder = padding.PKCS7(256).padder()
    enc = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
    return base64.b64encode(enc.update(padder.update(body) + padder.finalize()) + enc.finalize()).decode(
        "utf-8"
    )


def verify_url(
    token: str, encoding_aes_key: str, corp_id: str, signature: str, timestamp: str, nonce: str, echostr: str
) -> str:
    if not verify_signature(token, signature, timestamp, nonce, echostr):
        raise ValueError("签名校验失败")
    return decrypt(encoding_aes_key, echostr, corp_id)
