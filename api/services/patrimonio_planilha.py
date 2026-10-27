"""Importar os bens por planilha — a da casa (uma aba por setor) ou a exportada daqui.

🔑 **Pedido do dono (27/10/2026)**, com `Inventario_Equipamentos_Botane.xlsx`: os
equipamentos vêm de uma planilha com uma aba por setor (Administrativo, Bar, Cozinha…),
título e instruções em cima e o cabeçalho na quarta linha. A mesma rota lê o CSV que o
relatório "Patrimônio" exporta — dá para corrigir no Excel e mandar de volta.

As regras são as da reclassificação de produtos (`services/reclassificacao.py`):
⚠️ **Prévia antes, sempre** (`simular=True`), pela mesma função que aplica.
⚠️ **Célula vazia = não mexe.** Na segunda importação, a coluna que a pessoa não
preencheu não apaga o que já foi cadastrado na tela.
⚠️ **Pelo NOME**, sem maiúscula nem acento: setor e local como estão nas Tabelas de
apoio. Nome que não existe recusa a LINHA, dizendo qual célula; as outras seguem.
🔑 **Como a linha acha o bem que já existe**: pelo código da plaqueta (PAT-0001), quando a
planilha é a exportada daqui; senão pelo código da casa (BAR-02), que vira o APELIDO do
bem — é o que faz a segunda importação da mesma planilha atualizar, e não duplicar.
🔑 **"Sugestão"** (a origem dos equipamentos comuns em cafeteria que ninguém conferiu)
entra como **A confirmar**, fora dos alertas — ou fica de fora, se a pessoa pedir.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation

import auditoria
from services import patrimonio, planilha_xlsx
from services.reclassificacao import _chave, _por_nome

MAXIMO_BYTES = 8 * 1024 * 1024

# Cabeçalho (sem acento, minúsculo) → campo. Os da planilha da casa e os do relatório.
COLUNAS = {
    "codigo": "codigo", "apelido": "apelido",
    "equipamento": "descricao", "descricao": "descricao", "bem": "descricao",
    "setor": "setor", "local no sistema": "local", "local": "local",
    "origem do registro": "origem", "origem": "origem",
    "marca": "marca", "modelo": "modelo",
    "no de serie / patrimonio": "numero_serie", "n de serie / patrimonio": "numero_serie",
    "numero de serie": "numero_serie", "serie": "numero_serie",
    "tensao": "tensao",
    "data de compra": "data_compra", "valor de compra": "valor_compra",
    "fornecedor da compra": "fornecedor", "nota fiscal": "nota_fiscal",
    "garantia ate": "garantia_ate",
    "fornecedor / assistencia": "assistencia", "assistencia": "assistencia",
    "assistencia tecnica": "assistencia",
    "contato": "assistencia_contato",
    "criticidade": "criticidade", "situacao": "situacao",
    "preventiva a cada (meses)": "preventiva_meses",
    "ultima preventiva": "ultima_preventiva",
    "observacoes": "observacao", "observacao": "observacao",
    # 🔑 O produto Patrimônio do bem (27/10/2026): pelo código, senão pelo nome.
    "produto": "produto", "codigo do produto": "codigo_produto",
}
_SITUACAO = {_chave(v): k for k, v in patrimonio.SITUACOES.items()}
_CRITICIDADE = {_chave(v): k for k, v in patrimonio.CRITICIDADES.items()}
_TENSAO = {_chave(v): k for k, v in patrimonio.TENSOES.items()} | {
    "110v": "110V", "220v": "220V", "380v": "380V", "na": "NA", "n/a": "NA"}
# A ordem e o rótulo com que a prévia mostra o que muda.
ROTULOS = {"apelido": "Apelido", "descricao": "Equipamento", "id_produto": "Produto",
           "id_setor": "Setor",
           "id_local": "Local", "marca": "Marca", "modelo": "Modelo",
           "numero_serie": "Série", "tensao": "Tensão", "data_compra": "Compra",
           "valor_compra": "Valor", "fornecedor": "Fornecedor", "nota_fiscal": "Nota",
           "garantia_ate": "Garantia até", "assistencia": "Assistência",
           "assistencia_contato": "Contato", "criticidade": "Criticidade",
           "situacao": "Situação", "preventiva_meses": "Preventiva (meses)",
           "ultima_preventiva": "Última preventiva", "observacao": "Observações"}


class PlanilhaInvalida(ValueError):
    """A planilha não dá para ler — a frase vai para a tela."""


def _tabelas(conteudo: bytes) -> list[tuple[str, list[list[str]]]]:
    if planilha_xlsx.e_xlsx(conteudo):
        try:
            return planilha_xlsx.ler(conteudo)
        except planilha_xlsx.XlsxInvalido as e:
            raise PlanilhaInvalida(str(e)) from e
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("cp1252", errors="replace")
    amostra = texto[:4096]
    sep = ";" if amostra.count(";") >= amostra.count(",") else ","
    return [("", [[c.strip() for c in l] for l in csv.reader(io.StringIO(texto), delimiter=sep)])]


def _setor_da_aba(acima: list[list[str]]) -> str | None:
    """"Setor no sistema Botané: BAR · Loja: …" nas linhas de cima da aba."""
    for linha in acima:
        for c in linha:
            m = re.match(r"\s*setor no sistema[^:]*:\s*(.+?)\s*(·|$)", c, re.IGNORECASE)
            if m:
                return m.group(1).strip()
    return None


def ler(conteudo: bytes) -> list[dict]:
    """As linhas de todas as abas que têm o cabeçalho de equipamentos.

    ⚠️ **O cabeçalho é PROCURADO** em cada aba (a da casa abre com título e instrução);
    aba sem ele (Resumo, Como usar, Listas) é pulada. Linha sem o nome do equipamento
    é linha vazia do modelo — também pulada.
    """
    if len(conteudo) > MAXIMO_BYTES:
        raise PlanilhaInvalida("A planilha passa de 8 MB.")
    linhas: list[dict] = []
    achou = False
    for aba, tabela in _tabelas(conteudo):
        inicio, posicoes = None, {}
        for i, linha in enumerate(tabela[:30]):
            chaves = [_chave(c) for c in linha]
            mapa = {COLUNAS[c]: j for j, c in enumerate(chaves) if c in COLUNAS}
            if "descricao" in mapa and len(mapa) >= 2:
                inicio, posicoes = i + 1, mapa
                break
        if inicio is None:
            continue
        achou = True
        setor_da_aba = _setor_da_aba(tabela[:inicio])
        anterior_vazia = False
        for n, bruta in enumerate(tabela[inicio:], start=inicio + 1):
            preenchidas = [c for c in bruta if c]
            # ⚠️ **Linha vazia seguida de um TÍTULO (uma célula só) é outra seção**: o
            # relatório exportado daqui traz, depois dos bens, o quadro "Por setor" — sem
            # parar, os totais dele virariam equipamentos chamados "Criticidade alta".
            if anterior_vazia and len(preenchidas) == 1:
                break
            anterior_vazia = not preenchidas

            def celula(campo):
                j = posicoes.get(campo)
                return (bruta[j].strip() if j is not None and j < len(bruta) else "") or None
            if not celula("descricao"):
                continue
            d = {campo: celula(campo) for campo in posicoes}
            if not d.get("setor") and setor_da_aba:
                d["setor"] = setor_da_aba
            # ⚠️ **O NOME da aba é só palpite**: vale se houver setor com esse nome, e não
            # recusa a linha se não houver — uma aba chamada "Bens" ou "Planilha1" não é
            # erro de ninguém. A linha "Setor no sistema" e a coluna Setor, essas sim, são
            # ditas pela pessoa e recusam quando o nome não existe.
            if not d.get("setor") and aba:
                d["setor_aba"] = aba
            linhas.append({"aba": aba, "linha": n, **d})
    if not achou:
        raise PlanilhaInvalida("Não achei a coluna “Equipamento” em nenhuma aba — use a "
                               "planilha de inventário de equipamentos ou a exportada do "
                               "Patrimônio.")
    if not linhas:
        raise PlanilhaInvalida("A planilha não tem nenhum equipamento preenchido.")
    return linhas


def _numero(texto: str) -> Decimal:
    t = texto.replace("R$", "").replace(" ", "")
    # "1.234,56" (pt-BR) ou "1234.56" (o Excel guarda o número cru).
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return Decimal(t)
    except InvalidOperation as e:
        raise ValueError(f"“{texto}” não é um número") from e


def _converter(l: dict, setores: dict, locais: dict,
               produtos: tuple[dict, dict]) -> tuple[dict, str | None]:
    """A linha nos campos do bem — só os PREENCHIDOS. (campos, recusa)."""
    from services.reclassificacao import _resolver
    d: dict = {}
    for campo in ("descricao", "marca", "modelo", "numero_serie", "fornecedor", "nota_fiscal",
                  "assistencia", "assistencia_contato", "observacao", "apelido"):
        if l.get(campo):
            d[campo] = l[campo][:{"descricao": 120, "observacao": 500, "apelido": 20,
                                  "nota_fiscal": 40, "assistencia_contato": 80,
                                  "fornecedor": 120, "assistencia": 120}.get(campo, 60)]
    if l.get("codigo_produto") or l.get("produto"):
        por_codigo, por_nome = produtos
        if l.get("codigo_produto"):
            achado = por_codigo.get(l["codigo_produto"].strip().upper())
        else:
            achado = por_nome.get(_chave(l["produto"]), False)
            if achado is None:
                return {}, f"há mais de um produto Patrimônio chamado “{l['produto']}” — use o código"
        if not achado:
            return {}, (f"Não há produto do tipo Patrimônio "
                        f"“{l.get('codigo_produto') or l.get('produto')}” — confira o código, "
                        "ou reclassifique o produto como Patrimônio")
        d["id_produto"] = achado
    if l.get("setor"):
        d["id_setor"], recusa = _resolver(setores, l["setor"], "Setor")
        if recusa:
            return {}, recusa
    elif l.get("setor_aba"):
        achado, recusa = _resolver(setores, l["setor_aba"], "Setor")
        if not recusa:
            d["id_setor"] = achado
    if l.get("local") and _chave(l["local"]) not in ("outro", "outros", "-"):
        d["id_local"], recusa = _resolver(locais, l["local"], "Local")
        if recusa:
            return {}, recusa
    for campo, mapa, rotulo in (("situacao", _SITUACAO, "Situação"),
                                ("criticidade", _CRITICIDADE, "Criticidade"),
                                ("tensao", _TENSAO, "Tensão")):
        if l.get(campo):
            valor = mapa.get(_chave(l[campo]))
            if not valor:
                return {}, f"{rotulo} “{l[campo]}” não existe — use: " + ", ".join(
                    {"situacao": patrimonio.SITUACOES, "criticidade": patrimonio.CRITICIDADES,
                     "tensao": patrimonio.TENSOES}[campo].values())
            d[campo] = valor
    for campo in ("data_compra", "garantia_ate", "ultima_preventiva"):
        if l.get(campo):
            try:
                d[campo] = planilha_xlsx.data_do_excel(l[campo])
            except ValueError:
                return {}, f"{ROTULOS[campo]}: “{l[campo]}” não é uma data (use 15/03/2022)"
    if l.get("valor_compra"):
        try:
            v = _numero(l["valor_compra"])
        except ValueError as e:
            return {}, f"Valor de compra: {e}"
        if v < 0:
            return {}, "Valor de compra negativo"
        d["valor_compra"] = v.quantize(Decimal("0.01"))
    if l.get("preventiva_meses"):
        try:
            meses = int(_numero(l["preventiva_meses"]))
        except (ValueError, ArithmeticError):
            meses = 0
        if not 1 <= meses <= 120:
            return {}, f"Preventiva a cada “{l['preventiva_meses']}” meses — use de 1 a 120"
        d["preventiva_meses"] = meses
    if d.get("situacao") == "BAIXADO":
        d["motivo_baixa"] = (l.get("observacao") or "baixado na planilha")[:200]
    return d, None


def _mostrar(campo: str, valor, nomes: dict) -> str | None:
    if valor is None:
        return None
    if campo in ("id_setor", "id_local", "id_produto"):
        return nomes.get((campo, valor), str(valor))
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    if campo == "situacao":
        return patrimonio.SITUACOES.get(valor, valor)
    if campo == "criticidade":
        return patrimonio.CRITICIDADES.get(valor, valor)
    if campo == "tensao":
        return patrimonio.TENSOES.get(valor, valor)
    return str(valor)


def aplicar(cur, id_unidade: int, linhas: list[dict], id_usuario: int, *,
            simular: bool = True, incluir_sugestoes: bool = True) -> dict:
    """A prévia (ou a gravação) da planilha: novos, os que mudam, os iguais e as recusas."""
    setores = _por_nome(cur, """SELECT id, nome, ativo FROM setores
                                 WHERE id_unidade IS NULL OR id_unidade = %s""", (id_unidade,))
    locais = _por_nome(cur, "SELECT id, nome, ativo FROM locais_estoque WHERE id_unidade = %s",
                       (id_unidade,))
    cur.execute("SELECT id, nome FROM setores")
    nomes = {("id_setor", r["id"]): r["nome"] for r in cur.fetchall()}
    cur.execute("SELECT id, nome FROM locais_estoque WHERE id_unidade = %s", (id_unidade,))
    nomes |= {("id_local", r["id"]): r["nome"] for r in cur.fetchall()}
    cur.execute("SELECT id, codigo, nome FROM produtos WHERE tipo = 'PATRIMONIO'")
    patrimonios = [dict(r) for r in cur.fetchall()]
    nomes |= {("id_produto", p["id"]): p["nome"] for p in patrimonios}
    por_nome: dict = {}
    for p in patrimonios:
        k = _chave(p["nome"])
        por_nome[k] = None if k in por_nome else p["id"]
    produtos = ({p["codigo"].upper(): p["id"] for p in patrimonios if p["codigo"]}, por_nome)
    cur.execute("SELECT * FROM bens WHERE id_unidade = %s", (id_unidade,))
    existentes = [dict(r) for r in cur.fetchall()]
    por_codigo = {b["codigo"].upper(): b for b in existentes}
    por_apelido = {b["apelido"].lower(): b for b in existentes if b["apelido"]}

    novos, mudam, recusados = [], [], []
    iguais = sugestoes = 0
    vistos: set = set()
    for l in linhas:
        ref = {"aba": l["aba"], "linha": l["linha"], "descricao": l.get("descricao")}
        sugestao = _chave(l.get("origem")) == "sugestao"
        if sugestao:
            sugestoes += 1
            if not incluir_sugestoes:
                continue
        codigo = (l.get("codigo") or "").strip()
        plaqueta = codigo.upper() if re.fullmatch(r"PAT-\d+", codigo, re.IGNORECASE) else None
        if not plaqueta and codigo and not l.get("apelido"):
            l["apelido"] = codigo
        d, recusa = _converter(l, setores, locais, produtos)
        if recusa:
            recusados.append(ref | {"motivo": recusa})
            continue
        chave = plaqueta or (d.get("apelido") or "").lower() or None
        if chave and chave in vistos:
            recusados.append(ref | {"motivo": f"“{codigo or d.get('apelido')}” aparece duas "
                                              "vezes na planilha"})
            continue
        if chave:
            vistos.add(chave)
        if plaqueta:
            atual = por_codigo.get(plaqueta)
            if not atual:
                recusados.append(ref | {"motivo": f"Não há bem {plaqueta} nesta loja — apague o "
                                                  "código para cadastrar como novo"})
                continue
        else:
            atual = por_apelido.get((d.get("apelido") or "").lower()) if d.get("apelido") else None

        if atual is None:
            d.setdefault("situacao", "A_CONFIRMAR" if sugestao else "EM_USO")
            novos.append(ref | {"apelido": d.get("apelido"), "dados": d,
                                "campos": {ROTULOS[k]: _mostrar(k, v, nomes)
                                           for k, v in d.items() if k in ROTULOS}})
            continue
        # ⚠️ Só o que a célula TRAZ e é diferente — vazia não apaga.
        diferentes = {k: v for k, v in d.items()
                      if k in ROTULOS and v != atual.get(k)
                      and not (isinstance(v, Decimal) and atual.get(k) is not None
                               and Decimal(str(atual[k])) == v)}
        if d.get("motivo_baixa") and "situacao" in diferentes:
            diferentes["motivo_baixa"] = d["motivo_baixa"]
        if not diferentes:
            iguais += 1
            continue
        mudam.append(ref | {"id": atual["id"], "codigo": atual["codigo"],
                            "dados": diferentes,
                            "de": {ROTULOS[k]: _mostrar(k, atual.get(k), nomes)
                                   for k in diferentes if k in ROTULOS},
                            "para": {ROTULOS[k]: _mostrar(k, v, nomes)
                                     for k, v in diferentes.items() if k in ROTULOS}})

    if not simular:
        for n in novos:
            bem = patrimonio.criar(cur, id_unidade, id_usuario, n["dados"])
            n["codigo"] = bem["codigo"]
            auditoria.registrar(cur, id_usuario, "bem", bem["id"], "importar",
                                depois={"codigo": bem["codigo"], "descricao": bem["descricao"]},
                                id_unidade=id_unidade)
        for m in mudam:
            antes, depois = patrimonio.atualizar(cur, m["id"], id_unidade, m["dados"])
            auditoria.registrar(cur, id_usuario, "bem", m["id"], "importar",
                                antes=m["de"], depois=m["para"], id_unidade=id_unidade)
    for x in novos + mudam:
        x.pop("dados", None)

    partes = [f"{len(novos)} novo(s)", f"{len(mudam)} a atualizar", f"{iguais} sem mudança"]
    if recusados:
        partes.append(f"{len(recusados)} recusada(s)")
    if sugestoes:
        partes.append(f"{sugestoes} sugestão(ões) "
                      + ("entram como “A confirmar”" if incluir_sugestoes else "deixadas de fora"))
    feito = "Importado" if not simular else "Prévia"
    return {"novos": novos, "mudam": mudam, "iguais": iguais, "recusados": recusados,
            "sugestoes": sugestoes, "linhas": len(linhas), "aplicado": not simular,
            "message": f"{feito}: " + ", ".join(partes) + "."}
