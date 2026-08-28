"""Guarda de credencial de integração.

A chave do Omie não pode ficar legível no banco nem sair pela API. Aqui ela é
cifrada com uma chave derivada do `JWT_SECRET` — o mesmo segredo que já protege
a sessão, e que já mora fora do repositório.

Trocar o `JWT_SECRET` invalida as credenciais guardadas: é o preço de não ter um
cofre próprio, e está documentado na tela de integrações.
"""

import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken

from config import JWT_SECRET


def _chave() -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(JWT_SECRET.encode()).digest())


def cifrar(dados: dict) -> bytes:
    return Fernet(_chave()).encrypt(json.dumps(dados).encode())


def decifrar(bruto: bytes | memoryview | None) -> dict:
    if not bruto:
        return {}
    try:
        return json.loads(Fernet(_chave()).decrypt(bytes(bruto)))
    except (InvalidToken, ValueError):
        # Segredo trocado ou dado corrompido: melhor tratar como "sem credencial"
        # do que derrubar a tela inteira.
        #
        # ⚠️ Mas "sem credencial" e "credencial que não abre" NÃO são a mesma
        # coisa para quem está tentando entender por que não funciona — use
        # `ilegivel()` antes de concluir que ninguém configurou nada.
        return {}


def ilegivel(bruto: bytes | memoryview | None) -> bool:
    """Há credencial guardada, mas a chave atual não a abre.

    🔑 Existe porque o silêncio aqui manda procurar no lugar errado. O
    `JWT_SECRET` deriva a chave do Fernet: trocá-lo — ou subir a mesma base
    noutro ambiente — faz `decifrar` devolver `{}`, o envio sai com **senha
    vazia**, e o servidor responde *authentication failed*. Quem lê isso
    redigita a senha achando que errou a digitação, quando o que houve foi a
    chave do ambiente mudar. São dois problemas diferentes e o sistema dizia a
    mesma frase para os dois.

    ⚠️ Falso para credencial **ausente**: não configurar nada é um estado
    normal, e avisar sobre ele seria alarme onde não há problema.
    """
    if not bruto:
        return False
    try:
        Fernet(_chave()).decrypt(bytes(bruto))
        return False
    except (InvalidToken, ValueError):
        return True


def mascarar(valor: str | None) -> str | None:
    """`••••1234` — o suficiente para a pessoa reconhecer o que está lá."""
    if not valor:
        return None
    return "•" * max(0, len(valor) - 4) + valor[-4:] if len(valor) > 4 else "••••"
