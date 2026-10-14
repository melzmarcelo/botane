"""Todo rótulo que o código grava cabe na coluna que o recebe.

🔑 **Nasceu do incidente de 09 a 11/10/2026.** `venda_itens.origem_custo` era
`varchar(20)`, e em 02/09 o custo da venda ganhou dois rótulos maiores que isso
(`ficha_rascunho_parcial`, `ficha_rascunho_sem_custo`). Nenhuma suíte vendia
prato com ficha em rascunho incompleta, e o erro só apareceu em produção: a
busca das vendas do PDV parou três dias. O valor sai do código, a coluna sai da
migração, e ninguém confere um contra o outro — então esta suíte confere.

Duas varreduras, ambas lendo o CÓDIGO (sem API) e o tamanho do BANCO:

1. **Os produtores do custo da venda**, explicitamente: o rótulo de
   `origem_custo` viaja numa variável e é gravado por posição, e varredura
   genérica nenhuma o encontraria.
2. **Toda coluna cujo nome existe numa tabela só**: valor literal passado como
   argumento nomeado (`origem_tipo="VENDA"`), em dicionário
   (`{"origem_tipo": ...}`) ou no texto do SQL (`origem_tipo = 'VENDA'`).
   ⚠️ Nome repetido em várias tabelas (`status`, `tipo`, `origem`) fica de fora:
   não há como saber, pelo código, para qual delas o valor vai, e o menor
   tamanho entre elas acusaria o que não é problema.

    python tests/smoke_rotulos_cabem.py
"""

import ast
import pathlib
import re
import sys

sys.path.insert(0, ".")
import config  # noqa: E402
import psycopg2  # noqa: E402

RAIZ = pathlib.Path(".")
ROTULO = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# De onde sai o rótulo de `venda_itens.origem_custo`: a cascata do custo da venda.
# Nomes de coluna que também são palavra comum no código. `de` é o idioma alemão
# nas traduções (`{"en": …, "de": "nome_catalogo_de"}`), não o estado anterior
# de `pedido_historico`.
IGNORAR = {"de", "para"}

PRODUTORES_DO_CUSTO = ["services/cmv.py", "services/custos.py", "services/kits.py",
                       "services/custo_referencia.py", "routers/vendas.py"]

ok = 0
falhas: list[str] = []


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


def arquivos():
    for f in sorted(RAIZ.rglob("*.py")):
        if not any(p in f.parts for p in ("tests", "venv", ".venv", "__pycache__")):
            yield f


def constantes(no) -> list[str]:
    """As strings que uma expressão pode valer: literal, ou os dois lados de um `if`."""
    if isinstance(no, ast.Constant) and isinstance(no.value, str):
        return [no.value]
    if isinstance(no, ast.IfExp):
        return constantes(no.body) + constantes(no.orelse)
    return []


def rotulos_do_custo() -> dict[str, str]:
    """Rótulo → onde nasce, nos produtores do custo da venda.

    Pega o segundo elemento das tuplas devolvidas (`return valor, "ficha"`), o
    que se atribui a uma variável `origem` e as constantes `ORIGEM…` do módulo.
    ⚠️ Pega a mais (a conversão de unidade também devolve `(valor, "rótulo")`),
    e isso é de propósito: sobrar rótulo curto não acusa nada; faltar o longo
    é o que deixaria o incidente se repetir.
    """
    achados: dict[str, str] = {}

    def anotar(valores, f, no):
        for v in valores:
            if ROTULO.match(v):
                achados.setdefault(v, f"{f.as_posix()}:{no.lineno}")

    for nome in PRODUTORES_DO_CUSTO:
        f = RAIZ / nome
        for no in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Return) and isinstance(no.value, ast.Tuple) \
                    and len(no.value.elts) >= 2:
                anotar(constantes(no.value.elts[1]), f, no)
            if isinstance(no, ast.Assign):
                for alvo in no.targets:
                    if isinstance(alvo, ast.Name) and (
                            alvo.id == "origem" or alvo.id.startswith("ORIGEM")):
                        anotar(constantes(no.value), f, no)
                    # `custo, origem = (None, "sem_produto")` e parecidos
                    if isinstance(alvo, ast.Tuple) and isinstance(no.value, ast.Tuple):
                        for a, v in zip(alvo.elts, no.value.elts):
                            if isinstance(a, ast.Name) and a.id == "origem":
                                anotar(constantes(v), f, no)
    return achados


def literais_por_coluna(colunas: set[str]) -> dict[tuple[str, str], str]:
    """(coluna, valor) → onde aparece, para as colunas pedidas."""
    achados: dict[tuple[str, str], str] = {}

    def anotar(coluna, valor, f, linha):
        if coluna in colunas and isinstance(valor, str) and ROTULO.match(valor):
            achados.setdefault((coluna, valor), f"{f.as_posix()}:{linha}")

    for f in arquivos():
        for no in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Call):
                for kw in no.keywords:
                    for v in constantes(kw.value):
                        anotar(kw.arg, v, f, no.lineno)
            elif isinstance(no, ast.Dict):
                for k, v in zip(no.keys, no.values):
                    if isinstance(k, ast.Constant):
                        for valor in constantes(v):
                            anotar(k.value, valor, f, k.lineno)
            elif isinstance(no, ast.Constant) and isinstance(no.value, str) \
                    and re.search(r"\b(SELECT|INSERT|UPDATE)\b", no.value):
                for m in re.finditer(r"\b([a-z_]+)\s*(?:=|<>)\s*'([A-Za-z0-9_]+)'", no.value):
                    anotar(m.group(1), m.group(2), f, no.lineno)
                for m in re.finditer(r"\b([a-z_]+)\s+(?:NOT\s+)?IN\s*\(([^)]*)\)", no.value):
                    for v in re.findall(r"'([A-Za-z0-9_]+)'", m.group(2)):
                        anotar(m.group(1), v, f, no.lineno)
    return achados


conexao = psycopg2.connect(host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER,
                           password=config.DB_PASSWORD, dbname=config.DB_NAME)
cur = conexao.cursor()
cur.execute("""SELECT table_name, column_name, character_maximum_length
                 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND data_type = 'character varying'
                  AND character_maximum_length IS NOT NULL""")
tamanhos: dict[str, list[tuple[str, int]]] = {}
for tabela, coluna, n in cur.fetchall():
    tamanhos.setdefault(coluna, []).append((tabela, n))
conexao.close()

print("1. o rótulo do custo da venda cabe em venda_itens.origem_custo")
limite = dict(tamanhos.get("origem_custo", [])).get("venda_itens")
checar("a coluna existe e tem tamanho", limite, tamanhos.get("origem_custo"))
rotulos = rotulos_do_custo()
# ⚠️ Prova de que o coletor enxerga os produtores: se a cascata mudar de lugar
# e ele passar a não achar nada, a suíte seguiria verde sem conferir coisa alguma.
checar("o coletor acha o rótulo que derrubou a busca em 10/2026",
       "ficha_rascunho_sem_custo" in rotulos, sorted(rotulos))
checar("e o do item sem produto", "sem_produto" in rotulos, sorted(rotulos))
if limite:
    grandes = {r: onde for r, onde in rotulos.items() if len(r) > limite}
    checar(f"todos cabem nos {limite} caracteres", not grandes,
           [f"{r} ({len(r)}) em {onde}" for r, onde in grandes.items()])

print("2. o literal gravado em coluna de nome único cabe nela")
unicas = {c for c, lista in tamanhos.items() if len(lista) == 1} - IGNORAR
achados = literais_por_coluna(unicas)
checar("a varredura encontra literais", len(achados) > 20, len(achados))
checar("e enxerga o origem_tipo do razão",
       ("origem_tipo", "VENDA") in achados, sorted(k for k in achados if k[0] == "origem_tipo"))
grandes = [f"{t}.{c} ({n}) recebe '{v}' ({len(v)}) em {onde}"
           for (c, v), onde in sorted(achados.items())
           for t, n in tamanhos[c] if len(v) > n]
checar("nenhum passa do tamanho da coluna", not grandes, grandes)

print(f"\n{ok} ok, {len(falhas)} falha(s)")
sys.exit(1 if falhas else 0)
