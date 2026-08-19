"""Cliente HTTP do Omie.

Todas as chamadas do Omie são `POST` JSON para
`https://app.omie.com.br/api/v1/<serviço>/` com o corpo:

    {"call": "ListarNotaEnt", "app_key": "...", "app_secret": "...",
     "param": [{"pagina": 1, "registros_por_pagina": 50}]}

**Modo simulado**: sem credencial, o cliente responde com as fixtures de
`fixtures/`. É o que permite construir e testar o importador inteiro antes de a
chave chegar — e serve de demonstração para o cliente.

⚠️ O formato exato de cada campo da resposta **só se confirma com credencial
real**. Por isso a tradução vive em `mapeadores.py`, e não aqui.
"""

import json
import time
from pathlib import Path
from typing import Any

import httpx

BASE = "https://app.omie.com.br/api/v1"
FIXTURES = Path(__file__).parent / "fixtures"

# O Omie recusa consumo redundante e limita chamadas: espera crescente entre as
# tentativas, e nunca mais do que isso.
TENTATIVAS = 3
ESPERA_INICIAL = 2.0
TEMPO_LIMITE = 40.0


class ErroOmie(Exception):
    def __init__(self, mensagem: str, status: int | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


class ClienteOmie:
    def __init__(self, app_key: str | None = None, app_secret: str | None = None,
                 modo: str = "simulado"):
        self.app_key = app_key
        self.app_secret = app_secret
        # Sem credencial não existe modo real, mesmo que peçam.
        self.modo = "real" if (modo == "real" and app_key and app_secret) else "simulado"

    # ---------------------------------------------------------------- chamada

    def chamar(self, servico: str, call: str, param: dict | None = None) -> dict:
        if self.modo == "simulado":
            return self._fixture(servico, call, param or {})
        return self._http(servico, call, param or {})

    def _http(self, servico: str, call: str, param: dict) -> dict:
        corpo = {
            "call": call,
            "app_key": self.app_key,
            "app_secret": self.app_secret,
            "param": [param],
        }
        espera = ESPERA_INICIAL
        ultimo_erro = ""
        for tentativa in range(1, TENTATIVAS + 1):
            try:
                r = httpx.post(f"{BASE}/{servico}/", json=corpo, timeout=TEMPO_LIMITE)
            except httpx.HTTPError as e:
                ultimo_erro = f"falha de rede: {e}"
            else:
                if r.status_code == 200:
                    dados = r.json()
                    # O Omie devolve 200 com faultstring quando recusa.
                    if isinstance(dados, dict) and dados.get("faultstring"):
                        raise ErroOmie(str(dados["faultstring"]), r.status_code)
                    return dados
                # 425/429/5xx: vale esperar e tentar de novo. 4xx de credencial, não.
                if r.status_code in (400, 401, 403):
                    raise ErroOmie(f"o Omie recusou a chamada ({r.status_code}): {r.text[:200]}",
                                   r.status_code)
                ultimo_erro = f"HTTP {r.status_code}: {r.text[:200]}"

            if tentativa < TENTATIVAS:
                time.sleep(espera)
                espera *= 2
        raise ErroOmie(f"{call} falhou após {TENTATIVAS} tentativas — {ultimo_erro}")

    def _fixture(self, servico: str, call: str, param: dict) -> Any:
        nome = f"{servico.replace('/', '_')}_{call}.json"
        caminho = FIXTURES / nome
        if not caminho.exists():
            raise ErroOmie(f"modo simulado sem fixture para {call} (esperado: {nome})")
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        # Simula a paginação: a fixture traz tudo, a chamada devolve a página.
        pagina = int(param.get("pagina", 1))
        if pagina > 1:
            for chave in ("nfe_encontradas", "produto_servico_cadastro", "clientes_cadastro"):
                if chave in dados:
                    dados = {**dados, chave: [], "pagina": pagina}
        return dados

    # ---------------------------------------------------------------- páginas

    def paginar(self, servico: str, call: str, chave_lista: str,
                param: dict | None = None, por_pagina: int = 50, maximo: int = 20):
        """Percorre as páginas. Nunca puxa tudo de uma vez — o Omie não gosta."""
        pagina = 1
        while pagina <= maximo:
            corpo = {**(param or {}), "pagina": pagina, "registros_por_pagina": por_pagina}
            dados = self.chamar(servico, call, corpo)
            registros = dados.get(chave_lista) or []
            if not registros:
                return
            yield dados, registros
            total_paginas = int(dados.get("total_de_paginas") or 1)
            if pagina >= total_paginas:
                return
            pagina += 1


def testar(cliente: ClienteOmie) -> dict:
    """Bate numa chamada barata só para dizer se a credencial responde."""
    try:
        dados = cliente.chamar("geral/clientes", "ListarClientes",
                               {"pagina": 1, "registros_por_pagina": 1})
        return {"ok": True, "modo": cliente.modo,
                "detalhe": f"{dados.get('total_de_registros', '?')} cadastro(s) do lado do Omie"}
    except ErroOmie as e:
        return {"ok": False, "modo": cliente.modo, "detalhe": e.mensagem}
