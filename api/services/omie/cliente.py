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
import re
import time
from pathlib import Path
from typing import Any

import httpx

BASE = "https://app.omie.com.br/api/v1"
FIXTURES = Path(__file__).parent / "fixtures"

# O Omie recusa consumo redundante e limita chamadas: espera crescente entre as
# tentativas, e nunca mais do que isso.
TENTATIVAS = 4
ESPERA_INICIAL = 2.0
TEMPO_LIMITE = 40.0
# Quando o Omie limita, ele DIZ quanto esperar ("Aguarde 56 segundos"). Obedecer
# é mais barato que insistir: numa carga real, ignorar isso fez a sincronização
# desistir depois de três tentativas de dois segundos.
ESPERA_MAXIMA = 90.0
# ⚠️ O Omie BLOQUEIA a conta por "consumo indevido" quando as chamadas vêm
# rápido demais — e o bloqueio pega a integração inteira, não só a varredura
# que exagerou. Varrer um catálogo de 2.198 produtos derrubou a conta numa
# tarde. Um intervalo mínimo entre chamadas custa segundos e evita horas.
INTERVALO_MINIMO = 0.6
_ultima_chamada = 0.0
_SEGUNDOS_PEDIDOS = re.compile(r"[Aa]guarde\s+(\d+)\s*segundo")


# ⚠️ **O Omie tem DOIS dialetos de paginação**, e o mesmo importador fala os
# dois. Os módulos antigos usam nomes em português (`pagina`,
# `registros_por_pagina`); `produtos/recebimentonfe` — o que traz as notas de
# verdade — usa notação húngara (`nPagina`, `nRegistrosPorPagina`) e RECUSA a
# outra forma com "Tag [PAGINA] não faz parte da estrutura". Cada chamada
# recusada gasta cota, e cota gasta é o que bloqueia a conta: por isso o dialeto
# é declarado, não tentado.
DIALETO_PADRAO = {
    "pagina": "pagina",
    "por_pagina": "registros_por_pagina",
    "total_paginas": "total_de_paginas",
    "total": "total_de_registros",
}
DIALETO_HUNGARO = {
    "pagina": "nPagina",
    "por_pagina": "nRegistrosPorPagina",
    "total_paginas": "nTotalPaginas",
    "total": "nTotalRegistros",
}


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
            self._respirar()
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
                # Erro de ESTRUTURA não melhora com insistência: o parâmetro
                # errado continua errado na quarta tentativa, e cada tentativa
                # gasta a cota que faz o Omie bloquear a conta. (Foi assim que
                # um "apenas_importado" indevido virou bloqueio de API.)
                if "Client-5001" in (r.text or "") or "não faz parte da estrutura" in (r.text or ""):
                    raise ErroOmie(f"o Omie recusou os parâmetros de {call}: "
                                   f"{r.text[:200]}", r.status_code)
                # "Aguarde N segundos": o Omie diz o tempo. Chutar menos é
                # garantir outra recusa; chutar mais é perder tempo à toa.
                pedidos = _SEGUNDOS_PEDIDOS.search(r.text or "")
                if pedidos:
                    espera = min(float(pedidos.group(1)) + 2, ESPERA_MAXIMA)

            if tentativa < TENTATIVAS:
                time.sleep(espera)
                espera = min(espera * 2, ESPERA_MAXIMA)
        raise ErroOmie(f"{call} falhou após {TENTATIVAS} tentativas — {ultimo_erro}")

    def _fixture(self, servico: str, call: str, param: dict) -> Any:
        nome = f"{servico.replace('/', '_')}_{call}.json"
        caminho = FIXTURES / nome
        if not caminho.exists():
            raise ErroOmie(f"modo simulado sem fixture para {call} (esperado: {nome})")
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        # Consulta por id: a fixture é um dicionário de respostas, e a chamada
        # devolve a de um registro só (é assim que o `ConsultarRecebimento` fala).
        if "nIdReceb" in param:
            achado = dados.get(str(param["nIdReceb"]))
            if achado is None:
                raise ErroOmie(f"modo simulado: recebimento {param['nIdReceb']} não está na fixture")
            return achado
        # Simula a paginação: a fixture traz tudo, a chamada devolve a página.
        pagina = int(param.get("pagina") or param.get("nPagina") or 1)
        if pagina > 1:
            for chave in ("nfe_encontradas", "produto_servico_cadastro", "clientes_cadastro",
                          "recebimentos"):
                if chave in dados:
                    dados = {**dados, chave: [], "pagina": pagina, "nPagina": pagina}
        return dados

    def _respirar(self) -> None:
        """Segura o ritmo entre chamadas — o Omie bloqueia quem corre demais."""
        global _ultima_chamada
        if self.modo != "real":
            return
        agora = time.monotonic()
        falta = INTERVALO_MINIMO - (agora - _ultima_chamada)
        if falta > 0:
            time.sleep(falta)
        _ultima_chamada = time.monotonic()

    # ---------------------------------------------------------------- páginas

    def paginar(self, servico: str, call: str, chave_lista: str,
                param: dict | None = None, por_pagina: int = 50, maximo: int = 60,
                ao_truncar=None, dialeto: dict | None = None, do_fim: bool = False):
        """Percorre as páginas. Nunca puxa tudo de uma vez — o Omie não gosta.

        ⚠️ O teto existe para não varrer uma conta inteira sem querer, mas ele
        **precisa ser dito**: num catálogo real de 2.198 produtos, o teto de 20
        páginas trouxe 992 e a mensagem foi "992 criado(s)" — indistinguível de
        "o catálogo tem 992". `ao_truncar` recebe (trazidos, total_no_omie)
        quando a varredura para pelo teto, para quem chamou poder contar.

        `do_fim=True` percorre **da última página para a primeira**. Existe
        porque `ListarRecebimentos` não aceita filtro de data e devolve da nota
        mais VELHA para a mais nova: numa conta com 3.670 notas de três anos, a
        página 1 é de 2023 e as de hoje estão na 74. Varrendo de trás, quem só
        quer as novas para na primeira página que já for velha demais — em vez
        de atravessar o histórico inteiro toda madrugada.
        """
        d = dialeto or DIALETO_PADRAO
        pagina, trazidos, total = 1, 0, 0

        def buscar(n: int) -> dict:
            return self.chamar(servico, call,
                               {**(param or {}), d["pagina"]: n, d["por_pagina"]: por_pagina})

        if do_fim:
            # A primeira página é a sonda: diz quantas existem. Se a varredura
            # chegar até ela, o resultado é reaproveitado — nada se pede duas vezes.
            primeira = buscar(1)
            ultima = int(primeira.get(d["total_paginas"]) or 1)
            for n in range(ultima, 0, -1):
                if trazidos and ultima - n + 1 > maximo:
                    if ao_truncar:
                        ao_truncar(trazidos, int(primeira.get(d["total"]) or 0))
                    return
                dados = primeira if n == 1 else buscar(n)
                registros = dados.get(chave_lista) or []
                if not registros:
                    return
                trazidos += len(registros)
                yield dados, registros
            return

        while pagina <= maximo:
            dados = buscar(pagina)
            registros = dados.get(chave_lista) or []
            total = int(dados.get(d["total"]) or 0)
            if not registros:
                return
            trazidos += len(registros)
            yield dados, registros
            total_paginas = int(dados.get(d["total_paginas"]) or 1)
            if pagina >= total_paginas:
                return
            pagina += 1
        if ao_truncar:
            ao_truncar(trazidos, total)


def testar(cliente: ClienteOmie) -> dict:
    """Bate numa chamada barata só para dizer se a credencial responde."""
    try:
        dados = cliente.chamar("geral/clientes", "ListarClientes",
                               {"pagina": 1, "registros_por_pagina": 1})
        return {"ok": True, "modo": cliente.modo,
                "detalhe": f"{dados.get('total_de_registros', '?')} cadastro(s) do lado do Omie"}
    except ErroOmie as e:
        return {"ok": False, "modo": cliente.modo, "detalhe": e.mensagem}
