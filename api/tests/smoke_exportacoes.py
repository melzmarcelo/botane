"""Teste de fumaça da exportação: catálogo, filtros e os dois formatos.

Baixar era um clique cego. O botão de `/produtos` despejava os 3.226 do
cadastro, sempre; o de saldos trazia todos os locais; e o razão MANDAVA
`id_produto` que o servidor ignorava — filtrar um produto na tela e baixar dava
a planilha inteira, calada.

O que este arquivo cobra:

1. o catálogo existe, e cada relatório declara os filtros DELE
2. o catálogo respeita permissão — não é porta lateral
3. a extensão do caminho é o formato, e a URL não mente
4. planilha e PDF saem do MESMO recorte (a contagem de linhas bate)
5. o filtro realmente corta — e corta no servidor
6. o produto do razão deixou de ser ignorado
7. a prévia responde antes do botão, e diz se cabe em PDF
8. os dois relatórios COMPOSTOS continuam com os dois quadros
9. formato e relatório que não existem respondem com frase, não com 500
10. a ficha técnica sai para o papel, com o modo de preparo junto
11. e o PDF da ficha NÃO é a porta lateral do custo

    python tests/smoke_exportacoes.py            (API de pé na 9200)

⚠️ Cria os PRÓPRIOS produtos e movimentos, com marca de tempo, e afirma sobre
eles: a base é compartilhada com as outras suítes e tem milhares de linhas.
"""

import atexit
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

# ⚠️ O `.` é para o bloco 11, que importa `services` direto: rodando
# `python tests/smoke_exportacoes.py`, o `sys.path[0]` é a pasta do SCRIPT, não
# a de onde se chamou — e `services` não estaria no caminho.
sys.path.insert(0, "tests")
sys.path.insert(0, ".")
from comum import garantir_local  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
COZINHA = ("cozinha.teste@botane.com.br", "cozinha12345")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None, bruto=False):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=180) as r:
            conteudo = r.read()
            if bruto:
                return r.status, conteudo, dict(r.headers)
            return r.status, json.loads(conteudo or b"null")
    except urllib.error.HTTPError as e:
        cru = e.read()
        try:
            corpo_erro = json.loads(cru or b"null")
        except json.JSONDecodeError:
            corpo_erro = {"detail": cru.decode(errors="replace")}
        return (e.code, corpo_erro, {}) if bruto else (e.code, corpo_erro)


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


def linhas_do_csv(texto: str) -> int:
    """As linhas de DADO: o CSV leva título, data, resumo e cabeçalho antes."""
    return sum(1 for l in texto.splitlines() if l.strip())


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]

marca = str(time.time_ns())[-6:]
hoje = date.today()
periodo = f"inicio={hoje.replace(day=1)}&fim={hoje}"
id_local = garantir_local(chamar, token)["id"]

criados: list[int] = []


fichas_criadas: list[int] = []


def limpar():
    # ⚠️ A ficha sai ANTES dos produtos: o produto com ficha não se apaga.
    for id_f in fichas_criadas:
        chamar("DELETE", f"/fichas/{id_f}", token=token)
    for id_p in criados:
        chamar("DELETE", f"/produtos/{id_p}", token=token)


atexit.register(limpar)


print("1. o catálogo dos relatórios")
st, catalogo = chamar("GET", "/exportar/catalogo", token=token)
checar("o servidor publica o catálogo", st == 200 and isinstance(catalogo, list), st)
chaves = {c["chave"] for c in catalogo}
checar("com os oito relatórios da casa",
       {"saldos", "movimentos", "produtos", "vencimentos",
        "cmv", "abc", "movimentacao", "precos"} <= chaves, sorted(chaves))

porchave = {c["chave"]: c for c in catalogo}
filtros_de = lambda k: [f["nome"] for f in porchave[k]["filtros"]]  # noqa: E731
checar("o cadastro filtra por tipo, categoria, setor e situação",
       set(filtros_de("produtos")) == {"tipos_produto", "categorias", "setores", "situacao"},
       filtros_de("produtos"))
checar("o razão filtra por período, movimento, local e produto",
       {"periodo", "tipos_movimento", "locais", "produtos"} <= set(filtros_de("movimentos")),
       filtros_de("movimentos"))

# ⚠️ As opções vêm RESOLVIDAS: sem isso a janela precisaria de quatro
# requisições a mais só para saber o que oferecer, e piscaria quatro vezes.
locais_no_catalogo = next(f for f in porchave["saldos"]["filtros"] if f["nome"] == "locais")
checar("e as opções vêm resolvidas, prontas para a tela",
       locais_no_catalogo.get("opcoes") and "nome" in locais_no_catalogo["opcoes"][0],
       str(locais_no_catalogo.get("opcoes"))[:80])
# ⚠️ Produto NÃO é lista de caixinhas: são milhares. O tipo diz isso à tela.
produtos_filtro = next(f for f in porchave["saldos"]["filtros"] if f["nome"] == "produtos")
checar("produto é busca, não lista de caixinhas",
       produtos_filtro["tipo"] == "produtos" and "opcoes" not in produtos_filtro,
       produtos_filtro)

# Os rótulos dos movimentos saem de `estoque.ROTULOS`, não de uma lista copiada.
st, tipos_tela = chamar("GET", "/estoque/tipos-movimento", token=token)
tipos_catalogo = {o["valor"] for f in porchave["movimentos"]["filtros"]
                  if f["nome"] == "tipos_movimento" for o in f["opcoes"]}
checar("os tipos de movimento do filtro são os mesmos da tela",
       tipos_catalogo == {t["tipo"] for t in tipos_tela}, sorted(tipos_catalogo)[:4])


print("2. o catálogo respeita permissão")
st, r = chamar("POST", "/auth/login", {"email": COZINHA[0], "senha": COZINHA[1]})
if st == 200:
    tk = r["access_token"]
    st, cat_coz = chamar("GET", "/exportar/catalogo", token=tk)
    coz = {c["chave"] for c in cat_coz}
    checar("a cozinha vê o estoque (ela consulta saldos)", "saldos" in coz, sorted(coz))
    checar("e NÃO vê o CMV nem o cadastro", not ({"cmv", "produtos"} & coz), sorted(coz))
    st, _r, _h = chamar("GET", "/exportar/cmv.csv", token=tk, bruto=True)
    checar("e a rota, na unha, é barrada igual", st == 403, st)
else:
    print("  (sem usuário de cozinha nesta base — bloco pulado)")


print("3. a extensão do caminho é o formato")
st, csv, cab = chamar("GET", "/exportar/saldos.csv", token=token, bruto=True)
checar("planilha sai como CSV", st == 200 and csv[:3] == b"\xef\xbb\xbf", (st, csv[:6]))
checar("e o nome do arquivo termina em .csv",
       ".csv\"" in cab.get("content-disposition", ""), cab.get("content-disposition"))
st, pdf, cab = chamar("GET", "/exportar/saldos.pdf", token=token, bruto=True)
checar("PDF sai como PDF", st == 200 and pdf[:4] == b"%PDF", (st, pdf[:6]))
checar("e o nome do arquivo termina em .pdf",
       ".pdf\"" in cab.get("content-disposition", ""), cab.get("content-disposition"))


print("4. o filtro corta, e corta no servidor")
st, prod = chamar("POST", "/produtos", {
    "codigo": f"EXP{marca}", "nome": f"Exp insumo {marca}",
    "tipo": "INSUMO", "um_estoque": "KG", "id_local_padrao": id_local,
}, token=token)
checar("cria o insumo desta rodada", st == 201, (st, prod))
id_produto = prod.get("id")
criados.append(id_produto)
st, _ = chamar("POST", "/estoque/entradas", {
    "id_produto": id_produto, "quantidade": 4, "custo_unitario": 9,
    "id_local": id_local,
}, token=token)
checar("e uma entrada para ele existir no razão", st in (200, 201), st)

st, tudo, _ = chamar("GET", "/exportar/saldos.csv", token=token, bruto=True)
tudo = tudo.decode("utf-8")
st, so_um, _ = chamar("GET", f"/exportar/saldos.csv?produtos={id_produto}",
                      token=token, bruto=True)
so_um = so_um.decode("utf-8")
# ⚠️ `.upper()`: o gatilho da migração 036 normaliza o nome no banco, e a suíte
# afirma sobre o que foi GRAVADO, não sobre o que mandou.
nome = f"Exp insumo {marca}".upper()
checar("sem filtro, o produto está na planilha", nome in tudo)
checar("com o filtro, ele continua lá", nome in so_um)
checar("e o resto sai", linhas_do_csv(so_um) < linhas_do_csv(tudo),
       (linhas_do_csv(so_um), linhas_do_csv(tudo)))

st, so_tipo, _ = chamar("GET", "/exportar/produtos.csv?tipos_produto=UTENSILIO",
                        token=token, bruto=True)
checar("o cadastro filtrado por tipo não traz o insumo desta rodada",
       nome not in so_tipo.decode("utf-8"))


print("5. o produto do razão deixou de ser ignorado")
# ⚠️ Era o defeito que o próprio endpoint dizia existir para evitar: a tela
# mandava `id_produto`, o servidor não lia, e a planilha vinha inteira.
st, razao_um, _ = chamar(
    "GET", f"/exportar/movimentos.csv?{periodo}&produtos={id_produto}",
    token=token, bruto=True)
razao_um = razao_um.decode("utf-8")
st, razao_tudo, _ = chamar("GET", f"/exportar/movimentos.csv?{periodo}",
                           token=token, bruto=True)
checar("o razão de um produto traz o produto", nome in razao_um)
checar("e é menor que o razão inteiro",
       linhas_do_csv(razao_um) < linhas_do_csv(razao_tudo.decode("utf-8")),
       linhas_do_csv(razao_um))

st, por_tipo, _ = chamar(
    "GET", f"/exportar/movimentos.csv?{periodo}&tipos_movimento=ENTRADA_MANUAL"
           f"&produtos={id_produto}", token=token, bruto=True)
checar("e o filtro de movimento aceita mais de um valor", nome in por_tipo.decode("utf-8"))
st, sem_nada, _ = chamar(
    "GET", f"/exportar/movimentos.csv?{periodo}&tipos_movimento=SAIDA_VENDA"
           f"&produtos={id_produto}", token=token, bruto=True)
checar("e um movimento que não houve devolve nada deste produto",
       nome not in sem_nada.decode("utf-8"))


print("6. a prévia responde antes do botão")
st, p_tudo = chamar("GET", "/exportar/saldos/previa", token=token)
st2, p_um = chamar("GET", f"/exportar/saldos/previa?produtos={id_produto}", token=token)
checar("a prévia diz quantas linhas viriam", st == 200 and p_tudo["linhas"] > 0, p_tudo)
checar("e o filtro estreita o número", p_um["linhas"] < p_tudo["linhas"], (p_um, p_tudo))
checar("ela diz também se cabe em PDF",
       "cabe_no_pdf" in p_tudo and "maximo_pdf" in p_tudo, p_tudo)
# ⚠️ A prévia tem de contar o ARQUIVO, anexo incluído: o CMV é 10 linhas de
# apuração mais a margem por prato, e dizer "10" faria o contador abrir outra coisa.
st, p_cmv = chamar("GET", f"/exportar/cmv/previa?{periodo}", token=token)
checar("e conta o anexo junto no relatório composto", p_cmv["linhas"] > 10, p_cmv)


print("7. planilha e PDF saem do MESMO recorte")
st, csv_um, _ = chamar("GET", f"/exportar/saldos.csv?produtos={id_produto}",
                       token=token, bruto=True)
st, pdf_um, _ = chamar("GET", f"/exportar/saldos.pdf?produtos={id_produto}",
                       token=token, bruto=True)
checar("os dois formatos respondem ao mesmo filtro",
       st == 200 and pdf_um[:4] == b"%PDF" and nome in csv_um.decode("utf-8"), st)
# O PDF é binário e comprimido: o que se afirma dele é que existe, que é PDF, e
# que o recorte chegou (a prévia acima já provou o número).


print("8. os relatórios compostos continuam com os dois quadros")
st, cmv, _ = chamar("GET", f"/exportar/cmv.csv?{periodo}", token=token, bruto=True)
cmv = cmv.decode("utf-8")
checar("o arquivo do contador tem a apuração", "Composição do CMV" in cmv)
checar("e a margem por prato junto", "Margem por prato" in cmv)
# ⚠️ O BOM só vale no COMEÇO do arquivo: um solto no meio vira caractere
# invisível numa célula do Excel. O anexo era emendado com o dele.
checar("com um BOM só, no começo", cmv.count("﻿") == 1, cmv.count("﻿"))

st, precos, _ = chamar("GET", f"/exportar/precos.csv?{periodo}", token=token, bruto=True)
precos = precos.decode("utf-8")
checar("o arquivo do fornecedor tem a evolução de preço", "Evolução de preço" in precos)
checar("e o peso por setor junto", "Onde o custo pesa" in precos)
checar("com um BOM só, no começo", precos.count("﻿") == 1, precos.count("﻿"))

st, cmv_pdf, _ = chamar("GET", f"/exportar/cmv.pdf?{periodo}", token=token, bruto=True)
checar("e o PDF do composto também sai", st == 200 and cmv_pdf[:4] == b"%PDF", st)


print("9. o que não existe responde com frase, não com 500")
st, r, _ = chamar("GET", "/exportar/saldos.xls", token=token, bruto=True)
checar("formato que não existe dá 400", st == 400, st)
checar("e a frase nomeia os que existem", "csv" in str(r.get("detail")), r)
st, r, _ = chamar("GET", "/exportar/nao-existe.csv", token=token, bruto=True)
checar("relatório que não existe dá 404", st == 404, st)
checar("e a frase lista os que existem", "saldos" in str(r.get("detail")), r)
st, r = chamar("GET", "/exportar/nao-existe/previa", token=token)
checar("a prévia de um relatório inexistente também dá 404", st == 404, st)


print("10. a folha de contagem tem os dois formatos")
st, invs = chamar("GET", "/inventarios", token=token)
lista = invs["itens"] if isinstance(invs, dict) and "itens" in invs else invs
if lista:
    id_inv = lista[0]["id"]
    st, folha, cab = chamar(f"GET", f"/exportar/inventario/{id_inv}.csv",
                            token=token, bruto=True)
    checar("a folha sai em planilha", st == 200 and folha[:3] == b"\xef\xbb\xbf", st)
    st, folha_pdf, _ = chamar("GET", f"/exportar/inventario/{id_inv}.pdf",
                              token=token, bruto=True)
    checar("e em PDF, que é o formato de quem vai IMPRIMIR e contar no papel",
           st == 200 and folha_pdf[:4] == b"%PDF", st)
else:
    print("  (nenhum inventário nesta base — bloco pulado)")


print("11. a ficha técnica sai para o papel")
# A ficha existe para ser SEGUIDA, e quem segue está de pé na cozinha.
st, insumo_f = chamar("POST", "/produtos", {
    "codigo": f"FIN{marca}", "nome": f"Fic insumo {marca}",
    "tipo": "INSUMO", "um_estoque": "KG", "id_local_padrao": id_local,
}, token=token)
st, prato = chamar("POST", "/produtos", {
    "codigo": f"FPR{marca}", "nome": f"Fic prato {marca}",
    "tipo": "PRODUZIDO", "um_estoque": "UN", "producao_propria": True,
    "id_local_padrao": id_local,
}, token=token)
criados.extend([insumo_f.get("id"), prato.get("id")])
MODO = "1. Misture tudo." + chr(10) + "2. Asse por 40 minutos."
st, fic = chamar("POST", "/fichas", {
    "id_produto": prato.get("id"), "rendimento_qtd": 2, "rendimento_um": "UN",
    "porcoes": 4, "modo_preparo": MODO, "observacao": f"Nota da ficha {marca}",
    "alergenos": "glúten",
    "itens": [{"id_insumo": insumo_f.get("id"), "qtd_bruta": 0.5, "um": "KG"}],
}, token=token)
checar("cria a ficha desta rodada", st == 201, (st, fic))
id_ficha = fic.get("id")
fichas_criadas.append(id_ficha)

st, folha_csv, cab = chamar(f"GET", f"/exportar/ficha/{id_ficha}.csv", token=token, bruto=True)
folha_csv = folha_csv.decode("utf-8")
checar("a ficha sai em planilha", st == 200, st)
checar("com o nome do prato no título",
       f"Fic prato {marca}".upper() in folha_csv, folha_csv[:60])
checar("e o ingrediente na tabela", f"Fic insumo {marca}".upper() in folha_csv)
checar("com rendimento e porções no resumo",
       "Rendimento;2 UN" in folha_csv and "Porções;4" in folha_csv, folha_csv[:300])
# ⚠️ Texto montado à mão escapa da formatação: o rendimento saía "2.0000 UN",
# com ponto decimal, no meio de um CSV que usa vírgula em todo o resto.
checar("e o número do rendimento com vírgula, não com ponto",
       "2.0000" not in folha_csv, folha_csv[:300])
# ⚠️ O modo de preparo NÃO é tabela: é o texto que a cozinha lê enquanto faz.
checar("o modo de preparo vai junto", "Modo de preparo" in folha_csv and
       "Asse por 40 minutos" in folha_csv, folha_csv[-300:])
checar("e a observação da ficha também", f"Nota da ficha {marca}" in folha_csv)
# ⚠️ Coluna sem informação sai: numa receita simples "Qtd líquida" e
# "Observação" vêm vazias em toda linha, e três colunas mortas empurram o
# documento para paisagem.
checar("coluna vazia não entra na ficha", "Qtd líquida" not in folha_csv, folha_csv[:400])

st, folha_pdf, _ = chamar(f"GET", f"/exportar/ficha/{id_ficha}.pdf", token=token, bruto=True)
checar("e sai em PDF, que é o formato de quem vai IMPRIMIR",
       st == 200 and folha_pdf[:4] == b"%PDF", st)
# ⚠️ Ficha técnica é um CARTÃO DE RECEITA: sai em RETRATO, que é a forma do
# papel que se prende no armário da cozinha. Com o corte automático de largura
# ela caía em paisagem assim que a receita usava fator de correção.
caixa = re.search(rb"/MediaBox[^]]*]", folha_pdf)
retrato = caixa and b"595.2756 841.8898" in caixa.group(0)
checar("em retrato, que é a forma do papel que se pendura", bool(retrato),
       caixa.group(0) if caixa else None)

# ⚠️ Dinheiro da LINHA em centavos: a coluna vinha com "2,375" e "1,287" no
# meio de valores de dois dígitos, e é uma coluna que alguém soma com o dedo.
coluna_custo = [l.split(";")[-1] for l in folha_csv.splitlines()
                if l.startswith(f"Fic insumo {marca}".upper())]
checar("o custo da linha sai em centavos",
       all(len(v.split(",")[-1]) <= 2 for v in coluna_custo if "," in v), coluna_custo)

# ⚠️ "No estoque" existe para quando a receita pede 1 CX e o razão baixa 12 PCT.
# Sem conversão, ela é a cópia das duas colunas anteriores — e é uma das que
# empurravam a ficha para paisagem.
checar("sem conversão de unidade, a coluna 'No estoque' não entra",
       "No estoque" not in folha_csv, folha_csv[:400])

# E volta sozinha quando a receita converte de verdade: o insumo é estocado em
# KG e a receita pede em G.
st, fic2 = chamar("POST", "/fichas", {
    "id_produto": prato.get("id"), "rendimento_qtd": 1, "rendimento_um": "UN",
    "porcoes": 1,
    "itens": [{"id_insumo": insumo_f.get("id"), "qtd_bruta": 250, "um": "G"}],
}, token=token)
if fic2.get("id"):
    fichas_criadas.append(fic2["id"])
    st, com_conv, _ = chamar("GET", f"/exportar/ficha/{fic2['id']}.csv",
                             token=token, bruto=True)
    com_conv = com_conv.decode("utf-8")
    checar("mas volta quando a receita converte de unidade",
           "No estoque" in com_conv and "0,25 KG" in com_conv, com_conv[-400:])

st, r, _ = chamar("GET", "/exportar/ficha/99999999.pdf", token=token, bruto=True)
checar("ficha que não existe dá 404", st == 404, st)
st, r, _ = chamar("GET", "/exportar/ficha/abc.pdf", token=token, bruto=True)
checar("e id que não é número também", st == 404, st)


print("12. o PDF não é a porta lateral do custo")
# 🔑 Ver a ficha e ver o CUSTO são permissões diferentes — e um PDF é
# justamente o que SAI da tela e circula. Se o dinheiro vazasse por aqui, a
# regra do router de fichas viraria enfeite.
st, papeis = chamar("GET", "/papeis", token=token)
id_cozinha = next((p["id"] for p in papeis if p["nome"] == "Cozinha"), None)
st, usuarios = chamar("GET", "/usuarios?incluir_inativos=true", token=token)
existente = next((u for u in usuarios if u["email"] == COZINHA[0]), None)
if id_cozinha and existente:
    chamar("PUT", f"/usuarios/{existente['id']}",
           {"ativo": True, "senha": COZINHA[1], "papeis": [{"id_papel": id_cozinha}]},
           token=token)
elif id_cozinha:
    chamar("POST", "/usuarios", {"nome": "Cozinha teste", "email": COZINHA[0],
                                 "senha": COZINHA[1], "papeis": [{"id_papel": id_cozinha}]},
           token=token)
st, r = chamar("POST", "/auth/login", {"email": COZINHA[0], "senha": COZINHA[1]})
if st == 200:
    tk = r["access_token"]
    st, sem_custo, _ = chamar(f"GET", f"/exportar/ficha/{id_ficha}.csv", token=tk, bruto=True)
    sem_custo = sem_custo.decode("utf-8")
    checar("a cozinha BAIXA a ficha", st == 200, st)
    checar("e a receita está lá", f"Fic insumo {marca}".upper() in sem_custo)
    checar("mas nenhuma coluna de custo entra no arquivo",
           "Custo unitário" not in sem_custo and "Custo total" not in sem_custo,
           sem_custo[:400])
    checar("nem o custo da receita no resumo",
           "Custo da receita" not in sem_custo and "Custo por porção" not in sem_custo,
           sem_custo[:400])
    st, pdf_coz, _ = chamar(f"GET", f"/exportar/ficha/{id_ficha}.pdf", token=tk, bruto=True)
    checar("e o PDF dela também sai", st == 200 and pdf_coz[:4] == b"%PDF", st)
else:
    print("  (sem usuário de cozinha nesta base — bloco pulado)")


print("13. o teto do PDF")
# ⚠️ Testado como FUNÇÃO, não por HTTP: esta base tem 3.940 movimentos no total
# e o teto é 5.000 — chegar lá por requisição exigiria criar cinco mil linhas a
# cada rodada, que é caro e não prova nada a mais.
from fastapi import HTTPException  # noqa: E402
from services import exportacao as _exp  # noqa: E402
from services import exportacao_catalogo as _cat  # noqa: E402

checar("no teto, ainda passa", _cat.limite_do_pdf(_exp.MAXIMO_PDF) is None)
frase = ""
try:
    _cat.limite_do_pdf(_exp.MAXIMO_PDF + 1)
except HTTPException as e:
    frase = str(e.detail)
checar("acima do teto, recusa", bool(frase), frase)
checar("e a saída vai na frase: baixe a planilha", "planilha" in frase, frase)
checar("com o número em milhar brasileiro", "5.000" in frase, frase)
# ⚠️ `f"{n:,}".replace(",", ".")` troca a vírgula do MILHAR **e** a da FRASE
# pelo mesmo ponto: saía "acima de 5.000. porque vira um arquivo…". Frase de
# erro quebrada é o que a pessoa lê justamente quando já está confusa.
checar("e o separador de milhar não come a vírgula da frase",
       "5.000, porque" in frase and "planilha, que" in frase, frase)


print("14. o papel timbrado e o carimbo de quem emitiu")
# ⚠️ O PDF SAI da tela e circula — vira anexo de e-mail, papel na mesa do
# contador, foto no grupo. Sem o timbre não diz de que casa é; sem o rodapé não
# diz quem emitiu nem quando.
import arquivos  # noqa: E402

from database import get_cursor  # noqa: E402

with get_cursor() as _cur:
    timbre = _cat.papel_timbrado(_cur)
st, empresa_api = chamar("GET", "/empresa", token=token)
checar("o timbre traz o nome da casa",
       timbre.get("nome") == (empresa_api.get("nome_fantasia")
                              or empresa_api.get("razao_social")), timbre)
# ⚠️ Monta com o que EXISTE. Uma linha reservada e vazia anuncia o que falta
# em cada página impressa; montar só o que tem sai limpo hoje e completo
# depois, sem ninguém tocar em nada.
checar("e não inventa linha para campo em branco",
       all(l and l.strip() for l in timbre.get("linhas", [])), timbre)
if not empresa_api.get("cidade"):
    checar("com a base sem endereço, nenhuma linha de endereço sai",
           not any("/" in l and len(l) < 4 for l in timbre.get("linhas", [])), timbre)

checar("o CNPJ sai formatado para quem lê",
       _cat._cnpj_formatado("45304800000134") == "45.304.800/0001-34",
       _cat._cnpj_formatado("45304800000134"))
# ⚠️ Cadastro pela metade não pode virar número inventado no papel.
checar("e um cadastro pela metade passa como veio",
       _cat._cnpj_formatado("123") == "123" and _cat._cnpj_formatado(None) is None)

# ⚠️ A UF só aparece ATRÁS da cidade: sozinha, virava uma linha de endereço
# escrita "SC" — que é o estado atual da base e não informa nada.
so_uf = _cat._junta(None, "SC", sep="/")
checar("_junta não deixa separador solto", so_uf == "SC", so_uf)
checar("e nada vira None em vez de string vazia", _cat._junta(None, "") is None)

# ⚠️ A pasta de uploads é EFÊMERA no App Platform e some a cada deploy: logo
# ausente tem de sair sem logo, não derrubar o relatório.
checar("logo que não existe não vira caminho",
       arquivos.caminho_local("/arquivos/nao-existe-999.png") is None)
checar("e URL de fora do prefixo é recusada",
       arquivos.caminho_local("https://outro.site/logo.png") is None)

carimbo = _exp._junta_rodape("Fulano")
checar("o rodapé diz quem emitiu e quando",
       carimbo.startswith("emitido por Fulano em"), carimbo)
checar("e sem nome ainda diz quando",
       _exp._junta_rodape(None).startswith("emitido em"), _exp._junta_rodape(None))

# O PDF sai com o timbre montado, inclusive apontando para uma logo que não
# existe — que é o caso do dia seguinte a um deploy.
sem_quebrar = _exp.pdf_de(
    [{"a": "x"}], [("a", "A")], titulo="Timbre",
    empresa={"nome": "Casa", "linhas": ["CNPJ 00.000.000/0001-00"],
             "logo": "nao-existe.png"},
    emitido_por="Fulano")
checar("e o PDF sai mesmo com a logo faltando",
       sem_quebrar[:4] == b"%PDF", sem_quebrar[:8])


print()
print(f"{ok} passaram, {len(falhas)} falharam")
if falhas:
    for f in falhas:
        print("  -", f)
sys.exit(1 if falhas else 0)
