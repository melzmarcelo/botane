"""A situação no Omie dos custos de um bem — a compra e cada manutenção com nota fiscal.

🔑 **Pedido do dono (09/11/2026, entrega 2 da ficha do bem; escopo confirmado em 10/11/2026).**
A aba Custos diz quanto o bem custou; esta consulta diz se aquilo **já foi pago** no Omie.

🔑 **Só LÊ o Omie, e não grava nada aqui.** A situação de um título muda lá (pagou hoje, foi
cancelado); gravada aqui, mentiria no dia seguinte. Por isso é consulta NA HORA, por botão —
nunca ao abrir a ficha: cada chamada gasta a cota da conta do cliente, e o Omie bloqueia quem
consome demais (ver `services/omie/cliente.py`).

⚠️ **Em duas fases, e a conexão do banco NÃO fica presa durante a conversa com o Omie** (a
lição do envio de e-mail, `docs/o-que-falta.md`): `planejar` lê o banco e devolve o que
procurar; `consultar` fala com o Omie sem cursor nenhum.

Como cada linha acha o título (`ListarContasPagar`, em `financas/contapagar`):
  1. o FORNECEDOR com o código do Omie (`fornecedores.codigo_omie` = `codigo_cliente_fornecedor`)
     — o da compra pela nota de entrada daqui com o mesmo número, senão pelo NOME digitado no
     bem; o da manutenção pelo nome em "Feito por";
  2. uma busca por fornecedor (`filtrar_cliente`), paginada e com teto;
  3. o título cujo `numero_documento_fiscal` (ou `numero_documento`) é o número da NF, sem
     zeros à esquerda. Várias parcelas viram uma linha só: paga quando todas foram pagas.
⚠️ **Os nomes dos campos do contas a pagar NÃO foram confirmados contra a conta real** — o
cliente simulado responde pela fixture `financas_contapagar_ListarContasPagar.json`. Se o Omie
recusar a estrutura, a mensagem dele vai para a tela, e a correção é aqui.
"""

from __future__ import annotations

import re
from datetime import date

from fastapi import HTTPException

from services import segredos
from services.omie.cliente import ClienteOmie, ErroOmie

SERVICO_INTEGRACAO = "OMIE"
# Uma busca por fornecedor: até 5 páginas de 100 títulos. Fornecedor com mais títulos que
# isso tem o resto dito como "não achei nas últimas N", nunca varrido inteiro.
POR_PAGINA = 100
PAGINAS = 5
SITUACOES = {"PAGO": "Pago", "ABERTO": "Em aberto", "ATRASADO": "Atrasado",
             "CANCELADO": "Cancelado", "NAO_ACHADO": "Não achado no Omie",
             "SEM_FORNECEDOR": "Fornecedor sem código do Omie", "SEM_NOTA": "Sem nota fiscal"}


def _numero(nf: str | None) -> str:
    """"000123", "123" e "NF 123" são a mesma nota: só os dígitos, sem zero à esquerda."""
    d = re.sub(r"\D", "", nf or "")
    return d.lstrip("0") or ("0" if d else "")


def cliente(cur, id_unidade: int) -> ClienteOmie | None:
    """O cliente do Omie da loja, ou `None` sem integração cadastrada."""
    cur.execute("SELECT credenciais, modo FROM integracoes WHERE id_unidade = %s AND servico = %s",
                (id_unidade, SERVICO_INTEGRACAO))
    linha = cur.fetchone()
    if not linha:
        return None
    cred = segredos.decifrar(linha["credenciais"]) if linha["credenciais"] else {}
    return ClienteOmie(cred.get("app_key"), cred.get("app_secret"), linha["modo"])


def _fornecedor(cur, nome: str | None) -> dict | None:
    """O fornecedor pelo nome (razão social ou fantasia), sem diferença de maiúscula."""
    nome = " ".join((nome or "").split())
    if not nome:
        return None
    cur.execute(
        """SELECT id, nome, codigo_omie FROM fornecedores
            WHERE lower(nome) = lower(%s) OR lower(nome_fantasia) = lower(%s)
            ORDER BY (codigo_omie IS NULL), ativo DESC, id LIMIT 1""", (nome, nome))
    r = cur.fetchone()
    return dict(r) if r else None


def _fornecedor_da_compra(cur, id_unidade: int, bem: dict) -> dict | None:
    """A nota de entrada daqui com o mesmo número diz quem vendeu; sem ela, o nome digitado."""
    numero = _numero(bem.get("nota_fiscal"))
    if numero:
        cur.execute(
            """SELECT f.id, f.nome, f.codigo_omie, n.nome_emitente
                 FROM notas_entrada n JOIN fornecedores f ON f.id = n.id_fornecedor
                WHERE n.id_unidade = %s AND ltrim(n.numero, '0') = %s
                  AND n.status <> 'CANCELADA'
                ORDER BY (lower(f.nome) = lower(coalesce(%s, ''))) DESC,
                         n.data_emissao DESC NULLS LAST LIMIT 1""",
            (id_unidade, numero, bem.get("fornecedor")))
        r = cur.fetchone()
        if r:
            return dict(r)
    return _fornecedor(cur, bem.get("fornecedor"))


def planejar(cur, id_bem: int, id_unidade: int) -> dict:
    """O que procurar no Omie: uma linha por lançamento de custo do bem. Só lê o banco."""
    from services.patrimonio import _do_bem
    bem = _do_bem(cur, id_bem, id_unidade)
    cur.execute(
        """SELECT id, tipo, data, custo, nota_fiscal, executado_por, coberta_garantia
             FROM bem_manutencoes WHERE id_bem = %s ORDER BY data, id""", (id_bem,))
    # ⚠️ Lidas JÁ: achar o fornecedor da compra usa o mesmo cursor e apagaria este resultado.
    manutencoes = cur.fetchall()
    linhas = []

    def linha(chave, o_que, data, valor, nf, forn, nome_digitado):
        l = {"chave": chave, "o_que": o_que, "data": data, "valor": valor,
             "nota_fiscal": nf, "numero": _numero(nf),
             "fornecedor": (forn or {}).get("nome") or nome_digitado,
             "codigo_omie": (forn or {}).get("codigo_omie")}
        if not l["numero"]:
            l["situacao"] = "SEM_NOTA"
            l["detalhe"] = "Sem o número da nota fiscal, não há como achar o título."
        elif not l["codigo_omie"]:
            l["situacao"] = "SEM_FORNECEDOR"
            l["detalhe"] = (f"“{nome_digitado}” não está no cadastro de fornecedores com o código "
                            "do Omie." if nome_digitado and not forn else
                            f"{forn['nome']} não tem o código do Omie — importe os fornecedores "
                            "em Integrações ▸ Omie." if forn else
                            "Diga quem vendeu (fornecedor) para achar o título.")
        linhas.append(l)

    if bem["valor_compra"] is not None or bem.get("nota_fiscal"):
        linha("compra", "Compra", bem["data_compra"],
              float(bem["valor_compra"]) if bem["valor_compra"] is not None else None,
              bem.get("nota_fiscal"), _fornecedor_da_compra(cur, id_unidade, bem),
              bem.get("fornecedor"))
    for m in manutencoes:
        # A visita sem custo e sem nota (a garantia pagou, o funcionário fez) não tem título.
        if not m["custo"] and not m["nota_fiscal"]:
            continue
        linha(f"m{m['id']}", "Preventiva" if m["tipo"] == "PREVENTIVA" else "Corretiva",
              m["data"], float(m["custo"]) if m["custo"] is not None else None,
              m["nota_fiscal"], _fornecedor(cur, m["executado_por"]), m["executado_por"])
    return {"codigo": bem["codigo"], "linhas": linhas}


def _status(texto: str | None) -> str:
    """O `status_titulo` do Omie nas quatro situações daqui. ⚠️ O Omie escreve com e sem
    espaço ("A VENCER", "AVENCER", "VENCE HOJE"); compara-se sem espaço nem sublinhado."""
    t = re.sub(r"[\s_]", "", (texto or "").upper())
    if t in ("PAGO", "LIQUIDADO", "QUITADO", "BAIXADO"):
        return "PAGO"
    if t.startswith("CANCEL"):
        return "CANCELADO"
    if t in ("ATRASADO", "VENCIDO"):
        return "ATRASADO"
    return "ABERTO"


def _data(texto: str | None) -> date | None:
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", texto or "")
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def _juntar(titulos: list[dict]) -> dict:
    """As parcelas de uma nota numa situação só."""
    vivos = [t for t in titulos if _status(t.get("status_titulo")) != "CANCELADO"]
    if not vivos:
        return {"situacao": "CANCELADO", "parcelas": len(titulos), "pagas": 0,
                "detalhe": "Título cancelado no Omie."}
    st = [_status(t.get("status_titulo")) for t in vivos]
    pagas = st.count("PAGO")
    abertos = sorted((d for t, s in zip(vivos, st) if s != "PAGO"
                      for d in [_data(t.get("data_vencimento"))] if d))
    situacao = ("ATRASADO" if "ATRASADO" in st else "PAGO" if pagas == len(vivos) else "ABERTO")
    total = sum(float(t.get("valor_documento") or 0) for t in vivos)
    detalhe = (f"{pagas} de {len(vivos)} parcelas pagas" if len(vivos) > 1
               else "Pago" if situacao == "PAGO" else None)
    return {"situacao": situacao, "parcelas": len(vivos), "pagas": pagas,
            "valor_omie": round(total, 2),
            "proximo_vencimento": abertos[0] if abertos else None, "detalhe": detalhe}


def consultar(cli: ClienteOmie, plano: dict) -> dict:
    """Fala com o Omie — SEM cursor. Uma busca por fornecedor, não por linha."""
    linhas = plano["linhas"]
    codigos = sorted({l["codigo_omie"] for l in linhas if l.get("codigo_omie") and l["numero"]
                      and "situacao" not in l})
    por_fornecedor: dict[str, list[dict]] = {}
    truncados: set[str] = set()
    for codigo in codigos:
        try:
            filtro = int(codigo)
        except ValueError:
            filtro = codigo
        titulos: list[dict] = []
        try:
            for dados, registros in cli.paginar(
                    "financas/contapagar", "ListarContasPagar", "conta_pagar_cadastro",
                    {"filtrar_cliente": filtro}, por_pagina=POR_PAGINA, maximo=PAGINAS,
                    ao_truncar=lambda *_a, c=codigo: truncados.add(c)):
                titulos += registros
        except ErroOmie as e:
            if not e.nao_existe:
                raise HTTPException(status_code=502,
                                    detail=f"O Omie não respondeu a consulta: {e.mensagem}")
        # ⚠️ Confere o fornecedor também aqui: a fixture (e um filtro ignorado) devolve tudo.
        por_fornecedor[codigo] = [t for t in titulos
                                  if str(t.get("codigo_cliente_fornecedor") or "") == str(codigo)]
    for l in linhas:
        if "situacao" in l:
            continue
        achados = [t for t in por_fornecedor.get(l["codigo_omie"], [])
                   if l["numero"] in (_numero(str(t.get("numero_documento_fiscal") or "")),
                                      _numero(str(t.get("numero_documento") or "")))]
        if achados:
            l.update(_juntar(achados))
        else:
            l["situacao"] = "NAO_ACHADO"
            l["detalhe"] = (f"Nenhum título da NF {l['nota_fiscal']} de {l['fornecedor']}"
                            + (f" nos últimos {POR_PAGINA * PAGINAS} títulos do fornecedor."
                               if l["codigo_omie"] in truncados else "."))
    for l in linhas:
        l["situacao_txt"] = SITUACOES[l["situacao"]]
        l.pop("numero", None)
    return {"codigo": plano["codigo"], "modo": cli.modo, "linhas": linhas,
            "pagos": sum(1 for l in linhas if l["situacao"] == "PAGO"),
            "em_aberto": sum(1 for l in linhas if l["situacao"] in ("ABERTO", "ATRASADO")),
            "atrasados": sum(1 for l in linhas if l["situacao"] == "ATRASADO")}
