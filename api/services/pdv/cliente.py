"""Conversa com o PDV Legal (plataforma Tablet Cloud).

⚠️ **Só a autenticação está implementada, e é de propósito.** O `POST /token`
é a única parte da API que a Tablet Cloud documenta publicamente; o catálogo de
endpoints — vendas do dia, itens, cancelamentos, cardápio — fica no portal de
parceiros, fechado. Escrever importador contra endereço adivinhado é o oposto
do que a integração com o Omie ensinou: lá, quatro campos que a documentação
previa vinham **vazios** na conta real, e um parâmetro inventado consumiu cota
até a conta ser bloqueada.

Então este arquivo faz o que dá para fazer com certeza:

* guarda e usa a credencial (cifrada em `integracoes`, como a do Omie);
* pega o Bearer token e **o reaproveita** até perto de expirar;
* oferece um `get()` genérico, que é onde os endpoints entram quando o catálogo
  chegar — sem que nada acima precise mudar.

⚠️ **O token vale ~6 horas (21.599 s) e fica só na MEMÓRIA.** Guardá-lo no banco
seria guardar uma credencial de acesso a mais, com prazo, para economizar uma
chamada a cada seis horas — troca ruim. Reiniciar a API pede um token novo, e
isso é barato.
"""

import json
import threading
import time
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).parent / "fixtures"

BASE = "https://api.tabletcloud.com.br"

# ⚠️ Renova com folga. O `expires_in` é o que o servidor promete; usar o token
# até o último segundo faz a requisição da virada falhar com 401 por causa de
# alguns milissegundos de rede — e um 401 no meio de uma importação parece
# credencial errada, não token vencido.
FOLGA_DE_RENOVACAO = 300


class ErroPdv(Exception):
    def __init__(self, mensagem: str, status: int | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


class ClientePdv:
    """Um cliente por chamada. O token, esse sim, é compartilhado."""

    # ⚠️ O cache do token é de CLASSE e protegido por lock: cada requisição HTTP
    # monta um cliente novo, e sem isso duas telas abertas ao mesmo tempo
    # pediriam dois tokens — a Tablet Cloud não gosta de quem pede token demais,
    # e o segundo invalidaria o primeiro em algumas plataformas.
    _tokens: dict[str, tuple[str, float]] = {}
    _lock = threading.Lock()

    def __init__(self, username: str | None = None, password: str | None = None,
                 client_id: str | None = None, client_secret: str | None = None,
                 modo: str = "simulado"):
        self.username = username
        self.password = password
        self.client_id = client_id
        self.client_secret = client_secret
        # Sem credencial completa não existe modo real, mesmo que peçam — a
        # mesma regra do cliente do Omie.
        completa = all((username, password, client_id, client_secret))
        self.modo = "real" if (modo == "real" and completa) else "simulado"

    # ---------------------------------------------------------------- token

    @property
    def _chave_do_cache(self) -> str:
        """Identifica a conta sem guardar a senha na chave do dicionário."""
        return f"{self.client_id}:{self.username}"

    def token(self, forcar: bool = False) -> str:
        """O Bearer token, do cache ou novo.

        ⚠️ O lock cobre a checagem E a renovação: sem ele, duas threads que
        acham o token vencido no mesmo instante pedem dois.
        """
        if self.modo == "simulado":
            return "token-simulado"

        with self._lock:
            guardado = self._tokens.get(self._chave_do_cache)
            if guardado and not forcar and guardado[1] > time.time():
                return guardado[0]

            token, expira_em = self._pedir_token()
            self._tokens[self._chave_do_cache] = (
                token, time.time() + max(60, expira_em - FOLGA_DE_RENOVACAO)
            )
            return token

    def _pedir_token(self) -> tuple[str, int]:
        """`POST /token` — a única parte documentada publicamente.

        ⚠️ **Formulário, não JSON.** É o `password grant` do OAuth 2, e o padrão
        manda `application/x-www-form-urlencoded`. Mandar JSON costuma devolver
        400 com uma mensagem que não diz isso.
        """
        dados = {
            "grant_type": "password",
            "username": self.username,
            "password": self.password,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        try:
            r = httpx.post(f"{BASE}/token", data=dados, timeout=45)
        except httpx.HTTPError as e:
            raise ErroPdv(f"Não deu para falar com o PDV Legal: {e}") from e

        if r.status_code != 200:
            # ⚠️ A mensagem do servidor entra na exceção, mas NUNCA o que foi
            # enviado: o corpo do pedido tem a senha, e exceção vira log.
            raise ErroPdv(_mensagem_de_erro(r), r.status_code)

        try:
            corpo = r.json()
        except ValueError as e:
            raise ErroPdv("O PDV Legal respondeu algo que não é JSON.") from e

        token = corpo.get("access_token")
        if not token:
            raise ErroPdv("O PDV Legal respondeu sem `access_token`.")
        return token, int(corpo.get("expires_in") or 21599)

    # --------------------------------------------------------------- chamada

    def get(self, caminho: str, params: dict | None = None) -> Any:
        """Uma leitura autenticada. É por aqui que os endpoints entram.

        ⚠️ **Existe vazio de propósito**: o catálogo de endereços do PDV Legal
        não é público, e nenhum caminho está escrito no código porque nenhum foi
        verificado. Quando a documentação chegar, o importador chama este método
        e nada abaixo dele muda.

        ⚠️ **Um 401 tenta UMA vez com token novo.** Token de seis horas vence no
        meio de uma importação longa, e o 401 dali é vencimento, não credencial
        errada. Repetir mais de uma vez, não: aí o 401 é o que ele diz ser, e
        insistir só queima tentativa de login.
        """
        if self.modo == "simulado":
            return self._fixture(caminho)

        for tentativa in (1, 2):
            r = httpx.get(
                f"{BASE}{caminho}",
                params=params or {},
                headers={"Authorization": f"Bearer {self.token(forcar=tentativa == 2)}"},
                timeout=60,
            )
            if r.status_code == 401 and tentativa == 1:
                continue
            if r.status_code >= 400:
                raise ErroPdv(_mensagem_de_erro(r), r.status_code)
            try:
                return r.json()
            except ValueError as e:
                raise ErroPdv("O PDV Legal respondeu algo que não é JSON.") from e
        raise ErroPdv("O PDV Legal recusou o token duas vezes.", 401)

    def _fixture(self, caminho: str) -> Any:
        """Resposta gravada, para o modo simulado.

        Sem arquivo, devolve lista vazia em vez de estourar: o modo simulado
        existe para a tela funcionar sem credencial, e um endpoint que ainda não
        tem fixture é o caso normal enquanto o catálogo não chega.
        """
        nome = caminho.strip("/").replace("/", "_") or "raiz"
        arquivo = FIXTURES / f"{nome}.json"
        if not arquivo.exists():
            return []
        return json.loads(arquivo.read_text(encoding="utf-8"))

    # ----------------------------------------------------------------- teste

    def testar(self) -> dict:
        """Pega um token e diz se deu. É o que o botão da tela chama."""
        if self.modo == "simulado":
            return {"ok": True, "modo": "simulado",
                    "detalhe": "modo simulado — nenhuma chamada foi feita ao PDV Legal"}
        try:
            self.token(forcar=True)
        except ErroPdv as e:
            return {"ok": False, "modo": "real", "detalhe": e.mensagem}
        return {"ok": True, "modo": "real",
                "detalhe": "autenticou e recebeu um token válido"}


def _mensagem_de_erro(r: httpx.Response) -> str:
    """A frase do servidor, quando existe; o status, quando não.

    O OAuth 2 devolve `error` e `error_description`; a Tablet Cloud às vezes
    devolve `message`. Nenhuma das três é garantida.
    """
    try:
        corpo = r.json()
    except ValueError:
        return f"HTTP {r.status_code}"
    for chave in ("error_description", "message", "error", "Message"):
        if corpo.get(chave):
            return f"{corpo[chave]} (HTTP {r.status_code})"
    return f"HTTP {r.status_code}"
