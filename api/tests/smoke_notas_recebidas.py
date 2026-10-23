"""As duas opções de notas do Omie: "somente recebidas" e "lançar notas recebidas".

🔑 Pedido do dono (23/10/2026): *"Criar dois parametros no Omie. 1-Lançar notas
recebidas (ao puxar uma nota recebida, já fazer o lançamento no estoque) 2-Somente
recebidas (irá buscar somente as notas recebidas)"*.

O que esta suíte afirma:
1. a leitura: `cRecebido` S é recebida, N não é, e sem a marca é "não sei" (None)
2. desligada, a busca traz tudo, como sempre trouxe
3. "somente recebidas": a não recebida fica de fora — pela LISTA, sem gastar o
   detalhe, ou pelo detalhe quando a lista não traz a marca; a busca lembra a data
   dela e a próxima janela a alcança (até 60 dias); recebida depois, ela entra
4. "lançar notas recebidas": a recebida e pronta vai ao estoque na própria busca,
   com a auditoria marcada; a não recebida, a importada ANTES de ligar e a de item
   pendente ficam; sem quem assine, não lança; recebida depois de importada, a
   busca relê e lança
5. a configuração pela API (só se a API estiver de pé): grava, devolve, e um PUT
   sem os campos mantém

⚠️ **As partes 1 a 4 numa transação DESFEITA no fim**, com um Omie de mentira: nada
fica na base, e a conta real não é tocada.

    python tests/smoke_notas_recebidas.py      (a parte 5 usa a API; BOTANE_API muda a porta)
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, "tests")
sys.path.insert(0, ".")

from database import get_cursor, init_pool  # noqa: E402
from services.omie import importador, mapeadores  # noqa: E402

BASE = os.environ.get("BOTANE_API", "http://127.0.0.1:9200")
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


class Desfazer(Exception):
    """Levantada no fim de cada cenário: a transação inteira volta atrás."""


marca = str(time.time_ns() // 100)[-8:]
HOJE = date.today()


def recebimento(sufixo: str, recebido: str | None, produto: dict | None = None,
                quando: date = HOJE, na_lista: bool = True) -> dict:
    """Um recebimento como o Omie devolve, com um item só.

    `produto` liga o item a um cadastro pelo código do Omie; sem ele, o item fica
    pendente. `na_lista=False` tira o bloco de cadastro — a lista sem a marca.
    """
    dia = quando.strftime("%d/%m/%Y")
    item = {"nSequencia": 1, "cCodigoProduto": f"R{marca}{sufixo}", "cIgnorarItem": "N",
            "cDescricaoProduto": f"ITEM RECEBIDO {marca}{sufixo}",
            "cUnidadeNfe": (produto or {}).get("um_estoque") or "UN",
            "nQtdeNFe": 2, "nPrecoUnit": 10.0, "vTotalItem": 20.0}
    if produto:
        item["nIdProduto"] = produto["codigo_omie"]
    bruto = {
        "cabec": {"nIdReceb": int(f"88{marca}{sufixo}"),
                  "cChaveNFe": f"4226{marca}{sufixo}".ljust(44, "7"),
                  "cNumeroNFe": f"00{marca[-5:]}{sufixo}", "cSerieNFe": "1", "cEtapa": "40",
                  "dEmissaoNFe": dia, "cCNPJ_CPF": "12.968.266/0001-01",
                  "cRazaoSocial": f"Fornecedor recebido {marca}"},
        "totais": {"vTotalNFe": 20.0, "vTotalProdutos": 20.0},
        "infoAdicionais": {"dRegistro": dia},
        "itensRecebimento": [{"itensCabec": item}],
    }
    if recebido is not None and na_lista:
        bruto["infoCadastro"] = {"cFaturado": "S", "cRecebido": recebido, "cCancelada": "N"}
    return bruto


class OmieDeMentira:
    """A lista devolve o que se disser; o detalhe, o registro de `detalhes` (ou o da lista)."""

    modo = "real"

    def __init__(self, lista, detalhes=None):
        self.lista, self.detalhes, self.detalhes_pedidos = lista, detalhes or {}, 0

    def paginar(self, _servico, call, _chave, **_resto):
        if call == importador.LISTA_NOTAS and self.lista:
            yield {}, self.lista

    def chamar(self, _modulo, _call, params):
        self.detalhes_pedidos += 1
        id_receb = params["nIdReceb"]
        if id_receb in self.detalhes:
            return self.detalhes[id_receb]
        return next(r for r in self.lista if r["cabec"]["nIdReceb"] == id_receb)


def cenario(nome, corpo):
    print(nome)
    try:
        with get_cursor() as cur:
            cur.execute("SELECT id FROM unidades WHERE ativo ORDER BY id LIMIT 1")
            corpo(cur, cur.fetchone()["id"])
            raise Desfazer
    except Desfazer:
        pass


def opcoes(cur, id_unidade, so=False, lancar=False, desde_agora=True, ultima=None,
           aguardando=None, assina=True):
    """Liga/desliga as opções na linha da integração (dentro da transação desfeita)."""
    cur.execute("UPDATE produtos SET codigo_omie = %s WHERE id = %s",
                (PRODUTO["codigo_omie"], PRODUTO["id"]))
    cur.execute(
        """INSERT INTO integracoes (id_unidade, servico, modo, so_recebidas, lancar_recebidas,
                                    lancar_recebidas_desde, ultima_sincronizacao,
                                    aguardando_recebimento_desde, agenda_id_usuario)
           VALUES (%s, 'OMIE', 'simulado', %s, %s, CASE WHEN %s THEN now() END, %s, %s, %s)
           ON CONFLICT (id_unidade, servico) DO UPDATE
               SET so_recebidas = EXCLUDED.so_recebidas,
                   lancar_recebidas = EXCLUDED.lancar_recebidas,
                   lancar_recebidas_desde = EXCLUDED.lancar_recebidas_desde,
                   ultima_sincronizacao = EXCLUDED.ultima_sincronizacao,
                   aguardando_recebimento_desde = EXCLUDED.aguardando_recebimento_desde,
                   agenda_id_usuario = EXCLUDED.agenda_id_usuario""",
        (id_unidade, so, lancar, lancar and desde_agora, ultima, aguardando,
         USUARIO if assina else None),
    )


def nota_de(cur, sufixo):
    cur.execute("SELECT id, status FROM notas_entrada WHERE id_omie = %s",
                (f"88{marca}{sufixo}",))
    return cur.fetchone()


def aguardando_desde(cur, id_unidade):
    cur.execute("""SELECT aguardando_recebimento_desde AS d FROM integracoes
                    WHERE id_unidade = %s AND servico = 'OMIE'""", (id_unidade,))
    return cur.fetchone()["d"]


init_pool()
with get_cursor() as _cur:
    # Um produto pronto para entrar no estoque: ativo, com unidade e local. O código do
    # Omie é dado a ele dentro de cada cenário (`opcoes`), na transação desfeita.
    _cur.execute(
        """SELECT id, um_estoque FROM produtos
            WHERE ativo AND controla_estoque AND um_estoque IS NOT NULL
              AND id_local_padrao IS NOT NULL
            ORDER BY id LIMIT 1""")
    PRODUTO = dict(_cur.fetchone()) | {"codigo_omie": f"99{marca}"}
    _cur.execute("SELECT id FROM usuarios WHERE ativo ORDER BY id LIMIT 1")
    USUARIO = _cur.fetchone()["id"]

print("1. a leitura da marca de recebimento")
checar("`cRecebido: S` é recebida",
       mapeadores.situacao_no_omie(recebimento("1", "S"))["recebida"] is True)
checar("`cRecebido: N` NÃO é recebida",
       mapeadores.situacao_no_omie(recebimento("1", "N"))["recebida"] is False)
checar("sem a marca é \"não sei\" (None), não \"não recebida\"",
       mapeadores.situacao_no_omie(recebimento("1", None))["recebida"] is None)
checar("o mapeador da nota carrega a marca",
       mapeadores.recebimento_de_nfe(recebimento("1", "S"))["recebida"] is True)


def desligada_traz_tudo(cur, id_unidade):
    opcoes(cur, id_unidade)
    omie = OmieDeMentira([recebimento("2", "N"), recebimento("3", "S")])
    r = importador.sincronizar(cur, id_unidade, omie, 5, None)
    checar("desligada, a não recebida entra como sempre",
           bool(nota_de(cur, "2")) and bool(nota_de(cur, "3")), r.get("novas"))
    checar("e nada fica esperando", r.get("aguardando_recebimento") == 0, r)


def so_recebidas(cur, id_unidade):
    antiga = HOJE - timedelta(days=3)
    opcoes(cur, id_unidade, so=True)
    omie = OmieDeMentira([recebimento("4", "N", quando=antiga), recebimento("5", "S")])
    r = importador.sincronizar(cur, id_unidade, omie, 5, None)
    checar("a recebida entra", bool(nota_de(cur, "5")))
    checar("a NÃO recebida fica de fora", nota_de(cur, "4") is None)
    checar("decidida pela LISTA: o detalhe só foi pedido para a que entrou",
           omie.detalhes_pedidos == 1, omie.detalhes_pedidos)
    checar("a resposta conta a que ficou esperando", r.get("aguardando_recebimento") == 1, r)
    cur.execute("SELECT mensagem FROM sync_log WHERE chamada = %s ORDER BY id DESC LIMIT 1",
                (importador.LISTA_NOTAS,))
    checar("e a frase do log diz", "ainda não recebida" in (cur.fetchone()["mensagem"] or ""))
    checar("a busca lembra a data da que espera", aguardando_desde(cur, id_unidade) == antiga,
           aguardando_desde(cur, id_unidade))

    # A lista SEM a marca: decide pelo detalhe.
    sem_marca = OmieDeMentira([recebimento("6", "N", na_lista=False)],
                              {int(f"88{marca}6"): recebimento("6", "N")})
    importador.sincronizar(cur, id_unidade, sem_marca, 5, None)
    checar("lista sem a marca: o detalhe decide, e a não recebida fica de fora",
           nota_de(cur, "6") is None and sem_marca.detalhes_pedidos == 1)
    # Sem a marca nem no detalhe: entra (não sei ≠ não recebida).
    nada = OmieDeMentira([recebimento("7", None)])
    importador.sincronizar(cur, id_unidade, nada, 5, None)
    checar("sem a marca em lugar nenhum, a nota entra", bool(nota_de(cur, "7")))

    # Recebida depois: a próxima busca a traz e esquece a espera.
    depois = OmieDeMentira([recebimento("4", "S", quando=antiga), recebimento("5", "S")])
    r = importador.sincronizar(cur, id_unidade, depois, 5, None)
    checar("recebida depois, ela entra", bool(nota_de(cur, "4")), r)
    checar("e a espera é esquecida", aguardando_desde(cur, id_unidade) is None,
           aguardando_desde(cur, id_unidade))


def janela_alcanca_a_que_espera(cur, id_unidade):
    from datetime import datetime
    agora = datetime.now().astimezone()
    vinte = HOJE - timedelta(days=20)
    opcoes(cur, id_unidade, so=True, ultima=agora, aguardando=vinte)
    inicio, motivo = importador.janela(cur, id_unidade)
    checar("a janela automática recua até a nota que espera recebimento",
           inicio == vinte and "esperava recebimento" in motivo, (inicio, motivo))
    opcoes(cur, id_unidade, so=True, ultima=agora, aguardando=HOJE - timedelta(days=90))
    inicio, _ = importador.janela(cur, id_unidade)
    checar("mas no máximo 60 dias", inicio == HOJE - timedelta(days=importador.JANELA_PADRAO),
           inicio)
    opcoes(cur, id_unidade, so=False, ultima=agora, aguardando=vinte)
    inicio, _ = importador.janela(cur, id_unidade)
    checar("com a opção desligada, a espera não mexe na janela",
           inicio == HOJE - timedelta(days=importador.FOLGA_DIAS), inicio)
    # Uma busca curta que não alcançou a espera não a apaga.
    opcoes(cur, id_unidade, so=True, aguardando=vinte)
    importador.sincronizar(cur, id_unidade, OmieDeMentira([recebimento("8", "S")]), 1, None)
    checar("busca curta que não varreu a espera não a esquece",
           aguardando_desde(cur, id_unidade) == vinte, aguardando_desde(cur, id_unidade))


def lancar_recebidas(cur, id_unidade):
    # A importada ANTES de ligar a opção: recebida e pronta, mas não é lançada sozinha.
    antes = importador.gravar_nota(
        cur, id_unidade, mapeadores.recebimento_de_nfe(recebimento("9", "S", PRODUTO)),
        recebimento("9", "S", PRODUTO))[0]
    cur.execute("UPDATE notas_entrada SET importada_em = now() - interval '1 day' WHERE id = %s",
                (antes,))
    opcoes(cur, id_unidade, lancar=True)
    omie = OmieDeMentira([recebimento("10", "S", PRODUTO), recebimento("11", "N", PRODUTO),
                          recebimento("12", "S")])
    r = importador.sincronizar_completo(cur, id_unidade, omie, USUARIO, 5, None,
                                        catalogo=False)
    auto = r.get("lancamento_automatico") or {}
    checar("a recebida e pronta é lançada na própria busca",
           nota_de(cur, "10")["status"] == "LANCADA", (nota_de(cur, "10"), auto))
    checar("a resposta conta", auto.get("lancadas") == 1, auto)
    cur.execute("""SELECT depois FROM auditoria WHERE entidade = 'nota' AND acao = 'lancar'
                    AND id_entidade::text = %s""", (str(nota_de(cur, "10")["id"]),))
    linha = cur.fetchone()
    checar("a auditoria marca o lançamento como automático",
           linha is not None and (linha["depois"] or {}).get("automatico") is True, linha)
    cur.execute("SELECT lancada_por FROM notas_entrada WHERE id = %s",
                (nota_de(cur, "10")["id"],))
    checar("assinado por quem LIGOU a opção", cur.fetchone()["lancada_por"] == USUARIO)
    checar("a NÃO recebida fica para depois", nota_de(cur, "11")["status"] != "LANCADA",
           nota_de(cur, "11"))
    checar("a recebida com item sem produto fica na fila",
           nota_de(cur, "12")["status"] != "LANCADA", nota_de(cur, "12"))
    checar("a importada ANTES de ligar a opção não é lançada sozinha",
           nota_de(cur, "9")["status"] != "LANCADA", nota_de(cur, "9"))

    # Recebida no Omie depois de importada: a busca relê pela lista e lança.
    recebida_depois = OmieDeMentira([recebimento("11", "S", PRODUTO)])
    r = importador.sincronizar_completo(cur, id_unidade, recebida_depois, USUARIO, 5, None,
                                        catalogo=False)
    checar("recebida depois de importada, a busca relê e lança",
           nota_de(cur, "11")["status"] == "LANCADA",
           (nota_de(cur, "11"), r.get("atualizadas"), r.get("lancamento_automatico")))


def sem_quem_assine(cur, id_unidade):
    opcoes(cur, id_unidade, lancar=True, assina=False)
    r = importador.sincronizar_completo(
        cur, id_unidade, OmieDeMentira([recebimento("13", "S", PRODUTO)]), USUARIO, 5, None,
        catalogo=False)
    auto = r.get("lancamento_automatico") or {}
    checar("sem quem assine, não lança — e diz por quê",
           nota_de(cur, "13")["status"] != "LANCADA" and "assina" in (auto.get("erro") or ""),
           auto)


def desligada_nao_lanca(cur, id_unidade):
    opcoes(cur, id_unidade)
    r = importador.sincronizar_completo(
        cur, id_unidade, OmieDeMentira([recebimento("14", "S", PRODUTO)]), USUARIO, 5, None,
        catalogo=False)
    checar("com a opção desligada, a recebida só é importada",
           nota_de(cur, "14")["status"] != "LANCADA"
           and r.get("lancamento_automatico") is None, r.get("lancamento_automatico"))


cenario("\n2. desligada, a busca traz tudo", desligada_traz_tudo)
cenario("\n3. somente recebidas", so_recebidas)
cenario("\n3b. a janela alcança a que espera recebimento", janela_alcanca_a_que_espera)
cenario("\n4. lançar notas recebidas", lancar_recebidas)
cenario("\n4b. sem quem assine", sem_quem_assine)
cenario("\n4c. desligada, não lança", desligada_nao_lanca)


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


print("\n5. a configuração pela API")
try:
    _st, _r = chamar("POST", "/auth/login", {"email": "admin@botane.com.br", "senha": "botane123"})
    token = (_r or {}).get("access_token")
except OSError:
    token = None
if not token:
    print("  (API fora do ar — parte 5 pulada)")
else:
    _st, original = chamar("GET", "/omie/config", token=token)
    # ⚠️ O PUT regrava tudo: volta com o que estava (a chave em branco mantém a guardada).
    corpo = {"modo": original["modo"], "ativa": original["ativa"],
             "tag_fornecedor": original.get("tag_fornecedor"),
             "agenda_frequencia": original["agenda_frequencia"],
             "agenda_hora": original["agenda_hora"],
             "agenda_janela_dias": original.get("agenda_janela_dias")}
    try:
        st, r = chamar("PUT", "/omie/config",
                       corpo | {"so_recebidas": True, "lancar_recebidas": True}, token)
        _st, c = chamar("GET", "/omie/config", token=token)
        checar("ligar as duas grava, e a config devolve",
               st == 200 and c.get("so_recebidas") is True and c.get("lancar_recebidas") is True,
               (st, r, c.get("so_recebidas"), c.get("lancar_recebidas")))
        checar("ligar marca desde quando lançar", bool(c.get("lancar_recebidas_desde")), c)
        desde = c.get("lancar_recebidas_desde")
        chamar("PUT", "/omie/config", corpo, token)
        _st, c = chamar("GET", "/omie/config", token=token)
        checar("um PUT sem os campos MANTÉM as opções e a data",
               c.get("so_recebidas") is True and c.get("lancar_recebidas") is True
               and c.get("lancar_recebidas_desde") == desde, c)
        chamar("PUT", "/omie/config", corpo | {"lancar_recebidas": False}, token)
        _st, c = chamar("GET", "/omie/config", token=token)
        checar("desligar o lançamento limpa a data",
               c.get("lancar_recebidas") is False and c.get("lancar_recebidas_desde") is None, c)
    finally:
        chamar("PUT", "/omie/config",
               corpo | {"so_recebidas": bool(original.get("so_recebidas")),
                        "lancar_recebidas": bool(original.get("lancar_recebidas"))}, token)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
