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

from config import JWT_SECRET, JWT_SECRET_ANTERIOR


def _chave_de(segredo: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(segredo.encode()).digest())


def _chave() -> bytes:
    return _chave_de(JWT_SECRET)


def _chave_anterior() -> bytes | None:
    """A chave do segredo aposentado, enquanto a troca não terminou.

    🔑 **Existe para a troca do `JWT_SECRET` não custar as credenciais.** Sem
    ela, trocar o segredo deixava Omie, PDV e a senha de SMTP ilegíveis, e a
    casa tinha de redigitar tudo — o que, na prática, faz a troca ser adiada
    para sempre e o segredo fraco ficar.

    ⚠️ Nula quando a variável não está definida, que é o estado normal: a
    leitura com a chave anterior é a exceção de um deploy, não um caminho
    permanente.
    """
    return _chave_de(JWT_SECRET_ANTERIOR) if JWT_SECRET_ANTERIOR else None


def cifrar(dados: dict) -> bytes:
    return Fernet(_chave()).encrypt(json.dumps(dados).encode())


def decifrar(bruto: bytes | memoryview | None) -> dict:
    if not bruto:
        return {}
    try:
        return json.loads(Fernet(_chave()).decrypt(bytes(bruto)))
    except (InvalidToken, ValueError):
        # ⚠️ **A chave anterior é tentada DEPOIS, nunca antes.** Terminada a
        # regravação, nenhuma linha precisa dela — e uma ordem invertida faria
        # o sistema preferir o segredo aposentado enquanto a variável
        # estivesse esquecida no ambiente.
        anterior = _chave_anterior()
        if anterior is not None:
            try:
                return json.loads(Fernet(anterior).decrypt(bytes(bruto)))
            except (InvalidToken, ValueError):
                pass
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
    for chave in (_chave(), _chave_anterior()):
        if chave is None:
            continue
        try:
            Fernet(chave).decrypt(bytes(bruto))
            return False
        except (InvalidToken, ValueError):
            continue
    return True


def mascarar(valor: str | None) -> str | None:
    """`••••1234` — o suficiente para a pessoa reconhecer o que está lá."""
    if not valor:
        return None
    return "•" * max(0, len(valor) - 4) + valor[-4:] if len(valor) > 4 else "••••"


def regravar_com_a_chave_atual(cur) -> tuple[int, int]:
    """Recifra com a chave de hoje o que só abre com a anterior. (regravadas, ilegíveis)

    🔑 **É o que torna a troca do `JWT_SECRET` uma operação sem perda.** O
    segredo deriva a chave do Fernet, então trocá-lo tornava ilegível toda
    credencial guardada: Omie, PDV e a senha de SMTP teriam de ser redigitadas.
    Com `JWT_SECRET_ANTERIOR` definido por um deploy, cada linha é aberta com a
    chave velha e regravada com a nova.

    ⚠️ **Só toca no que a chave ATUAL não abre.** Rodar duas vezes não faz nada
    na segunda: a primeira já deixou tudo legível pela chave de hoje — e é isso
    que permite a variável ficar esquecida no ambiente por um tempo sem
    estragar nada.

    ⚠️ **Linha que nenhuma das duas abre é contada e deixada em paz.** Pode ser
    de um terceiro segredo, de outro ambiente ou dado corrompido; regravá-la
    seria escrever lixo cifrado por cima de lixo, e apagá-la destruiria a única
    pista do que aconteceu. `ilegivel()` continua denunciando na tela.
    """
    anterior = _chave_anterior()
    if anterior is None:
        return (0, 0)

    cur.execute("SELECT id, credenciais FROM integracoes WHERE credenciais IS NOT NULL")
    linhas = [(r["id"], bytes(r["credenciais"])) for r in cur.fetchall()]

    regravadas = perdidas = 0
    for id_linha, bruto in linhas:
        try:
            Fernet(_chave()).decrypt(bruto)
            continue                      # já está na chave de hoje
        except (InvalidToken, ValueError):
            pass
        try:
            dados = json.loads(Fernet(anterior).decrypt(bruto))
        except (InvalidToken, ValueError):
            perdidas += 1
            continue
        cur.execute("UPDATE integracoes SET credenciais = %s WHERE id = %s",
                    (cifrar(dados), id_linha))
        regravadas += 1
    return (regravadas, perdidas)
