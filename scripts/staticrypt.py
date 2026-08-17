"""
Implementação em Python do StatiCrypt (o mesmo esquema usado pelo painel.html).

Permite descriptografar o payload embutido no HTML, alterar o conteúdo e
re-criptografar mantendo o MESMO salt — assim os links "remember me" que já
estão no navegador do time continuam funcionando.

Esquema (compatível com StatiCrypt v3):
  chave  = PBKDF2-SHA1(senha, salt, 1k) -> PBKDF2-SHA256(hex, salt, 14k)
                                        -> PBKDF2-SHA256(hex, salt, 585k)
  payload = HMAC-SHA256 (64 hex) + IV (32 hex) + AES-256-CBC (hex)
"""

from __future__ import annotations

import binascii
import hashlib
import hmac
import os
import re

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

RE_MSG = re.compile(r'("staticryptEncryptedMsgUniqueVariableName":")([0-9a-f]+)(")')
RE_SALT = re.compile(r'"staticryptSaltUniqueVariableName":"([0-9a-f]+)"')


def _pbkdf2(senha: str, salt: str, iteracoes: int, alg: str) -> str:
    bruto = hashlib.pbkdf2_hmac(alg, senha.encode(), salt.encode(), iteracoes, 32)
    return binascii.hexlify(bruto).decode()


def derivar_chave(senha: str, salt: str) -> bytes:
    h = _pbkdf2(senha, salt, 1_000, "sha1")
    h = _pbkdf2(h, salt, 14_000, "sha256")
    h = _pbkdf2(h, salt, 585_000, "sha256")
    return binascii.unhexlify(h)


def extrair(html: str) -> tuple[str, str]:
    """Devolve (payload_hex, salt_hex) de um HTML criptografado."""
    msg = RE_MSG.search(html)
    salt = RE_SALT.search(html)
    if not msg or not salt:
        raise ValueError("HTML não parece estar criptografado com StatiCrypt.")
    return msg.group(2), salt.group(1)


def descriptografar(html: str, senha: str) -> str:
    payload, salt = extrair(html)
    chave = derivar_chave(senha, salt)

    assinatura, corpo = payload[:64], payload[64:]
    esperado = hmac.new(chave, corpo.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(esperado, assinatura):
        raise ValueError("Senha incorreta: o HMAC do payload não confere.")

    iv = binascii.unhexlify(corpo[:32])
    cifrado = binascii.unhexlify(corpo[32:])
    decifrador = Cipher(algorithms.AES(chave), modes.CBC(iv)).decryptor()
    bruto = decifrador.update(cifrado) + decifrador.finalize()
    return bruto[: -bruto[-1]].decode("utf-8")  # remove padding PKCS#7


def recriptografar(html_original: str, conteudo: str, senha: str) -> str:
    """
    Devolve o HTML criptografado com `conteudo` no lugar do payload antigo,
    preservando o salt (e portanto os links já salvos no navegador).
    """
    _, salt = extrair(html_original)
    chave = derivar_chave(senha, salt)

    dados = conteudo.encode("utf-8")
    pad = 16 - (len(dados) % 16)
    dados += bytes([pad]) * pad

    iv = os.urandom(16)
    cifrador = Cipher(algorithms.AES(chave), modes.CBC(iv)).encryptor()
    corpo = binascii.hexlify(iv).decode() + binascii.hexlify(
        cifrador.update(dados) + cifrador.finalize()
    ).decode()
    assinatura = hmac.new(chave, corpo.encode(), hashlib.sha256).hexdigest()

    return RE_MSG.sub(lambda m: m.group(1) + assinatura + corpo + m.group(3), html_original)
