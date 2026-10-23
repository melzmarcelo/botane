"""Reclassificar produtos por PLANILHA: tipo, categoria, setor e local padrão, linha a linha.

🔑 **Pedido do dono (23/10/2026)**, com o documento "Tabelas tipo, categoria, setor" da
casa: reorganizar tipos, categorias, setores e locais e "já organizar os produtos em
seus respectivos locais/setores/categorias". São ~1.500 produtos, cada um com o SEU
destino — a alteração múltipla (`alteracao_multipla`) põe o MESMO valor em vários, e
pelo conector seriam 1.500 chamadas no sistema no ar.

O caminho: exportar o cadastro de produtos em planilha (a exportação que já existe),
corrigir no Excel as colunas Tipo, Categoria, Setor e Local padrão, e mandar de volta.

⚠️ **Prévia antes, sempre** (`simular=True`), pela mesma função que aplica — a regra
da alteração múltipla, da fusão e da colheita de EAN: quem mexe em 1.500 linhas não
confere uma a uma depois.
⚠️ **Célula vazia = não mexe.** A planilha volta com colunas que a pessoa não quis
tocar; apagar o setor de quem estava com a célula em branco seria o pior efeito
colateral possível de um "não mexi".
⚠️ **Pelo NOME**, ignorando maiúscula e acento — é o que a planilha exportada traz e
o que a pessoa digita. Nome que não existe (ou está inativo) recusa a LINHA, nomeada;
as outras seguem.
⚠️ Só os campos de CLASSIFICAÇÃO. Unidade, código e preço ficam fora pela razão da
alteração múltipla: a unidade converte custo e saldo (`troca_de_unidade`).
"""

from __future__ import annotations

import csv
import io
import unicodedata

import auditoria
from models.produtos import TIPOS, TIPOS_SEM_ESTOQUE
from services.alteracao_multipla import _recusa

# Cabeçalho da planilha (sem acento, minúsculo) → campo. São os da exportação de
# produtos (`exportacao_catalogo._produtos`), mais a grafia sem acento.
COLUNAS = {
    "codigo": "codigo",
    "tipo": "tipo",
    "categoria": "categoria",
    "setor": "setor",
    "local padrao": "local",
    "local": "local",
}
CAMPOS = ("tipo", "categoria", "setor", "local")
# Teto do arquivo: o cadastro inteiro exportado com todas as colunas cabe com folga.
MAXIMO_BYTES = 8 * 1024 * 1024


class PlanilhaInvalida(ValueError):
    """A planilha não dá para ler — a frase vai para a tela."""


def _chave(texto) -> str:
    """Sem acento, sem espaço sobrando, minúsculo: como se compara nome com nome."""
    t = unicodedata.normalize("NFKD", str(texto or ""))
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).lower().split())


def _tipo(texto: str) -> str | None:
    """"Material operacional", "MATERIAL_OPERACIONAL", "Utensílios" → o código."""
    codigo = _chave(texto).upper().replace(" ", "_").replace("-", "_")
    if codigo in TIPOS:
        return codigo
    # O plural que a tela mostra ("Utensílios") e o que se digita sem pensar.
    if codigo.endswith("S") and codigo[:-1] in TIPOS:
        return codigo[:-1]
    return None


def ler(conteudo: bytes) -> list[dict]:
    """As linhas da planilha: `{"linha": n, "codigo": ..., "tipo": ..., ...}`.

    ⚠️ **O cabeçalho é PROCURADO, não suposto na primeira linha**: a planilha exportada
    abre com o título, o carimbo e uma linha em branco antes das colunas.
    ⚠️ Ponto e vírgula ou vírgula — o Excel pt-BR salva com o primeiro, o resto do
    mundo com o segundo.
    """
    if len(conteudo) > MAXIMO_BYTES:
        raise PlanilhaInvalida("A planilha passa de 8 MB — mande só as colunas de "
                               "Código, Tipo, Categoria, Setor e Local padrão.")
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        # O Excel que salva "CSV" sem escolher UTF-8 grava em Windows-1252.
        texto = conteudo.decode("cp1252", errors="replace")
    amostra = texto[:4096]
    separador = ";" if amostra.count(";") >= amostra.count(",") else ","
    leitor = list(csv.reader(io.StringIO(texto), delimiter=separador))

    cabecalho, inicio = None, 0
    for i, linha in enumerate(leitor[:30]):
        chaves = [_chave(c) for c in linha]
        if "codigo" in chaves:
            cabecalho, inicio = chaves, i + 1
            break
    if cabecalho is None:
        raise PlanilhaInvalida("Não achei a coluna “Código” — é ela que diz qual produto "
                               "é cada linha. Use a planilha exportada do cadastro de produtos.")
    posicoes = {COLUNAS[c]: i for i, c in enumerate(cabecalho) if c in COLUNAS}
    if not any(c in posicoes for c in CAMPOS):
        raise PlanilhaInvalida("A planilha não tem nenhuma das colunas Tipo, Categoria, "
                               "Setor ou Local padrão — não há o que reclassificar.")

    linhas = []
    for n, bruta in enumerate(leitor[inicio:], start=inicio + 1):
        def celula(campo):
            i = posicoes.get(campo)
            return (bruta[i].strip() if i is not None and i < len(bruta) else "") or None
        codigo = celula("codigo")
        if not codigo:
            continue
        linhas.append({"linha": n, "codigo": codigo, **{c: celula(c) for c in CAMPOS}})
    if not linhas:
        raise PlanilhaInvalida("A planilha não tem nenhuma linha com código de produto.")
    return linhas


def _por_nome(cur, sql: str, params: tuple = ()) -> dict:
    """`{nome sem acento: (id, nome, ativo)}`; nome repetido vira `None` (ambíguo)."""
    cur.execute(sql, params)
    grupos: dict[str, list] = {}
    for r in cur.fetchall():
        grupos.setdefault(_chave(r["nome"]), []).append((r["id"], r["nome"], r["ativo"]))
    mapa: dict = {}
    for k, todos in grupos.items():
        # ⚠️ Duas ATIVAS com o mesmo nome (diferindo só em acento) não se resolvem pela
        # planilha; uma ativa e inativas, sim — vale a ativa. Só inativas: a primeira,
        # para a recusa dizer "está inativo" em vez de "não existe".
        ativos = [x for x in todos if x[2]]
        mapa[k] = None if len(ativos) > 1 else (ativos[0] if ativos else todos[0])
    return mapa


def _resolver(mapa: dict, texto: str, rotulo: str) -> tuple[int | None, str | None]:
    """(id, recusa). Recusa nomeada: a pessoa precisa saber QUAL célula consertar."""
    achado = mapa.get(_chave(texto), False)
    if achado is False:
        return None, f"{rotulo} “{texto}” não existe — crie em Tabelas de apoio ou corrija o nome"
    if achado is None:
        return None, (f"há mais de uma categoria chamada “{texto}”" if rotulo == "Categoria"
                      else f"há mais de um {rotulo.lower()} chamado “{texto}”")
    if not achado[2]:
        return None, f"{rotulo} “{achado[1]}” está {'inativa' if rotulo == 'Categoria' else 'inativo'}"
    return achado[0], None


def aplicar(cur, id_unidade: int, linhas: list[dict], id_usuario: int | None,
            simular: bool = True) -> dict:
    """O que a planilha faria, ou fez. O mesmo formato nos dois casos."""
    categorias = _por_nome(cur, "SELECT id, nome, ativo FROM categorias")
    setores = _por_nome(cur, "SELECT id, nome, ativo FROM setores")
    # O local é da LOJA: o mesmo nome noutra loja é outro local.
    locais = _por_nome(cur, "SELECT id, nome, ativo FROM locais_estoque WHERE id_unidade = %s",
                       (id_unidade,))

    codigos = sorted({l["codigo"].lower() for l in linhas})
    cur.execute(
        """SELECT p.id, p.codigo, p.nome, p.tipo, p.id_categoria, p.id_setor,
                  p.id_local_padrao, p.ativo, p.producao_propria, p.fundido_em,
                  p.controla_estoque,
                  c.nome AS categoria, s.nome AS setor, lp.nome AS local,
                  f.nome AS sobrevivente,
                  coalesce((SELECT sum(abs(es.quantidade)) FROM estoque_saldos es
                             WHERE es.id_produto = p.id), 0) AS saldo
             FROM produtos p
             LEFT JOIN categorias c ON c.id = p.id_categoria
             LEFT JOIN setores s ON s.id = p.id_setor
             LEFT JOIN locais_estoque lp ON lp.id = p.id_local_padrao
             LEFT JOIN produtos f ON f.id = p.fundido_em
            WHERE lower(p.codigo) = ANY(%s)""",
        (codigos,),
    )
    produtos = {r["codigo"].lower(): dict(r) for r in cur.fetchall()}

    mudam, iguais, recusados, vistos = [], 0, [], set()
    for l in linhas:
        def recusa(motivo, produto=None):
            recusados.append({"linha": l["linha"], "codigo": l["codigo"],
                              "nome": (produto or {}).get("nome"), "motivo": motivo})

        p = produtos.get(l["codigo"].lower())
        if not p:
            recusa("código não encontrado no cadastro")
            continue
        if p["id"] in vistos:
            # ⚠️ Duas linhas do mesmo produto com destinos diferentes: valer "a última"
            # seria decidir calado. A primeira vale; a repetida é apontada.
            recusa("o produto aparece de novo na planilha — vale a primeira linha", p)
            continue
        vistos.add(p["id"])

        novo, motivos = {}, []
        if l["tipo"]:
            t = _tipo(l["tipo"])
            if t:
                novo["tipo"] = t
            else:
                motivos.append(f"tipo “{l['tipo']}” não existe (use: {', '.join(TIPOS)})")
        for campo, mapa, rotulo, coluna in (("categoria", categorias, "Categoria", "id_categoria"),
                                            ("setor", setores, "Setor", "id_setor"),
                                            ("local", locais, "Local", "id_local_padrao")):
            # 🔑 **Igual ao que já está = não é mudança, nem passa pela validação.** A
            # planilha exportada volta com TODAS as células preenchidas: a linha não
            # mexida de um produto numa categoria já desativada (as antigas, depois da
            # reestruturação) seria recusada por "está inativa" sem ninguém ter pedido nada.
            atual = {"categoria": p["categoria"], "setor": p["setor"], "local": p["local"]}[campo]
            if l[campo] and _chave(l[campo]) == _chave(atual):
                continue
            if l[campo]:
                valor, motivo = _resolver(mapa, l[campo], rotulo)
                if motivo:
                    motivos.append(motivo)
                else:
                    novo[coluna] = valor
        if motivos:
            recusa("; ".join(motivos), p)
            continue
        # As travas do cadastro, pela mesma função da alteração múltipla.
        motivo = _recusa(p, {"tipo": novo.get("tipo")})
        if not motivo and novo.get("tipo") in TIPOS_SEM_ESTOQUE and p["tipo"] != novo["tipo"] \
                and p["saldo"]:
            # ⚠️ Serviço não tem estoque: o saldo que existe ficaria órfão no razão.
            motivo = "tem saldo em estoque, e serviço não tem estoque — zere o saldo antes"
        if motivo:
            recusa(motivo, p)
            continue

        if novo.get("tipo") in TIPOS_SEM_ESTOQUE and p["controla_estoque"]:
            novo["controla_estoque"] = False
        diferentes = {c: v for c, v in novo.items() if p[c] != v}
        if not diferentes:
            iguais += 1
            continue
        mudam.append({"id": p["id"], "codigo": p["codigo"], "nome": p["nome"],
                      "de": _legivel(p, diferentes, p), "para": _legivel(p, diferentes, None,
                                                                         categorias, setores,
                                                                         locais),
                      "_campos": diferentes,
                      "_antes": {c: p[c] for c in diferentes}})

    if not simular and mudam:
        for m in mudam:
            campos = m["_campos"]
            sets = ", ".join(f"{c} = %s" for c in campos)
            cur.execute(f"UPDATE produtos SET {sets} WHERE id = %s",  # noqa: S608
                        [*campos.values(), m["id"]])
            # ⚠️ Um registro por PRODUTO, como na alteração múltipla: quem procurar
            # daqui a seis meses por que este produto mudou de categoria procura por ele.
            auditoria.registrar(cur, id_usuario, "produto", m["id"], "reclassificar",
                                antes=m["_antes"], depois=campos, id_unidade=id_unidade)

    for m in mudam:
        m.pop("_campos")
        m.pop("_antes")
    verbo = "mudariam" if simular else "mudaram"
    partes = [f"{len(mudam)} produto(s) {verbo}"]
    if iguais:
        partes.append(f"{iguais} já estava(m) assim")
    if recusados:
        partes.append(f"{len(recusados)} linha(s) recusada(s)")
    return {"mudam": mudam, "iguais": iguais, "recusados": recusados,
            "linhas": len(linhas), "aplicado": not simular,
            "message": ", ".join(partes) + "."}


def _legivel(p: dict, campos: dict, antes: dict | None, categorias=None, setores=None,
             locais=None) -> dict:
    """Os campos que mudam, pelo NOME — "de" lido do produto, "para" dos mapas."""
    if antes is not None:
        return {_ROTULO[c]: _nome_antes(p, c) for c in campos}
    nomes = {}
    for c, v in campos.items():
        if c == "tipo":
            nomes["tipo"] = v
        elif c == "controla_estoque":
            nomes["controla estoque"] = "não"
        else:
            mapa = {"id_categoria": categorias, "id_setor": setores,
                    "id_local_padrao": locais}[c]
            nomes[_ROTULO[c]] = next((x[1] for x in mapa.values() if x and x[0] == v), None)
    return nomes


_ROTULO = {"tipo": "tipo", "id_categoria": "categoria", "id_setor": "setor",
           "id_local_padrao": "local padrão", "controla_estoque": "controla estoque"}


def _nome_antes(p: dict, campo: str):
    return {"tipo": p["tipo"], "id_categoria": p["categoria"], "id_setor": p["setor"],
            "id_local_padrao": p["local"],
            "controla_estoque": "sim" if p["controla_estoque"] else "não"}[campo]
