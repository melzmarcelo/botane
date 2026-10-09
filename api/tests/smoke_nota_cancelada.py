"""A nota cancelada no Omie deixa de ficar pendente aqui.

Relato do dono (09/10/2026): *"identifiquei que no Omie esta nota foi cancelada.
Esta é uma situação que deve ser tratada também, para não ficar notas pendentes
que estão canceladas."* A nota 87313 foi cancelada lá e seguia IMPORTADA aqui, com
o item na fila de conciliação.

O que esta suíte afirma:
1. a leitura da situação: a marca de cancelamento é reconhecida pelo SENTIDO do
   nome do campo, e "N" não é cancelada
2. nota que já chega cancelada nasce CANCELADA — fora da fila, sem lançar
3. "atualizar do Omie" cancela a nota que já estava aqui, e desfaz se voltar
4. o recálculo e a religação não ressuscitam a cancelada
5. a busca automática cancela pelo cabeçalho da lista; a LANÇADA não é mexida, e
   a resposta manda estornar
6. "atualizar do Omie" para TODAS as abertas, em levas: a cancelada, a de valor
   novo e a igual, sem tocar na lançada; uma falha não leva as outras, e falhas
   seguidas param a leva

⚠️ **Tudo numa transação DESFEITA no fim**, com um Omie de mentira montado aqui:
nada desta rodada fica na base, e a conta real não é tocada.
⚠️ O NOME do campo de cancelamento no Omie real não foi confirmado por fixture —
as daqui usam `infoCadastro.cCancelada`. A resposta da nota passou a devolver as
marcas lidas (`situacao_no_omie`) justamente para conferir isso no ar.

    python tests/smoke_nota_cancelada.py            (não precisa da API de pé)
"""

import sys
import time
from datetime import date

sys.path.insert(0, "tests")
sys.path.insert(0, ".")
from fastapi import HTTPException  # noqa: E402

from database import get_cursor  # noqa: E402
from services.omie import importador, mapeadores  # noqa: E402

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
HOJE = date.today().strftime("%d/%m/%Y")


def recebimento(sufixo: str, cancelada: str | None = None, valor: float = 280.0,
                **info) -> dict:
    """Um recebimento como o Omie devolve, com um item só."""
    cadastro = dict(info)
    if cancelada is not None:
        cadastro["cCancelada"] = cancelada
    return {
        "cabec": {"nIdReceb": int(f"77{marca}{sufixo}"),
                  "cChaveNFe": f"4226{marca}{sufixo}".ljust(44, "0"),
                  "cNumeroNFe": f"00{marca[-5:]}{sufixo}", "cSerieNFe": "1", "cEtapa": "40",
                  "dEmissaoNFe": HOJE, "cCNPJ_CPF": "12.968.266/0001-01",
                  "cRazaoSocial": f"Fornecedor cancelado {marca}"},
        "totais": {"vTotalNFe": valor, "vTotalProdutos": valor},
        "infoAdicionais": {"dRegistro": HOJE},
        "infoCadastro": cadastro,
        "itensRecebimento": [{"itensCabec": {
            "nSequencia": 1, "cCodigoProduto": f"C{marca}", "cIgnorarItem": "N",
            "cDescricaoProduto": f"DETERGENTE CANCELADO {marca}", "cUnidadeNfe": "BB",
            "nQtdeNFe": 1, "nPrecoUnit": valor, "vTotalItem": valor}}],
    }


class OmieDeMentira:
    """A lista devolve o que se disser; o detalhe é o mesmo registro."""

    modo = "real"

    def __init__(self, registros):
        self.registros = registros

    def paginar(self, _servico, call, _chave, **_resto):
        if call == importador.LISTA_NOTAS and self.registros:
            yield {}, self.registros

    def chamar(self, _modulo, _call, params):
        return next(r for r in self.registros
                    if r["cabec"]["nIdReceb"] == params["nIdReceb"])


def cenario(nome, corpo):
    print(nome)
    try:
        with get_cursor() as cur:
            cur.execute("SELECT id FROM unidades WHERE ativo ORDER BY id LIMIT 1")
            corpo(cur, cur.fetchone()["id"])
            raise Desfazer
    except Desfazer:
        pass


def status_de(cur, id_nota):
    cur.execute("SELECT status FROM notas_entrada WHERE id = %s", (id_nota,))
    return cur.fetchone()["status"]


def gravar(cur, id_unidade, bruto):
    id_nota, _nova = importador.gravar_nota(
        cur, id_unidade, mapeadores.recebimento_de_nfe(bruto), bruto)
    return id_nota


def na_fila(cur, id_nota) -> int:
    """Quantos itens desta nota a fila de conciliação mostraria."""
    cur.execute(
        """SELECT count(*) AS n FROM nota_itens i JOIN notas_entrada n ON n.id = i.id_nota
            WHERE i.id_nota = %s AND i.id_produto IS NULL AND NOT i.ignorado
              AND n.status <> 'CANCELADA'""", (id_nota,))
    return cur.fetchone()["n"]


print("1. a leitura da situação no Omie")
checar("`cCancelada: S` é cancelada",
       mapeadores.situacao_no_omie(recebimento("1", "S"))["cancelada"] is True)
checar("`cCancelada: N` NÃO é cancelada",
       mapeadores.situacao_no_omie(recebimento("1", "N"))["cancelada"] is False)
checar("sem a marca, não é cancelada",
       mapeadores.situacao_no_omie(recebimento("1"))["cancelada"] is False)
# ⚠️ Pelo SENTIDO, não por um nome fixo: outra grafia e a data do cancelamento valem.
checar("outra grafia da marca também vale",
       mapeadores.situacao_no_omie(recebimento("1", cCancelado="S"))["cancelada"] is True)
checar("a data do cancelamento preenchida também vale",
       mapeadores.situacao_no_omie(recebimento("1", "N", dCanc="09/10/2026"))["cancelada"]
       is True)
checar("data de cancelamento VAZIA não é cancelamento",
       mapeadores.situacao_no_omie(recebimento("1", "N", dCanc=""))["cancelada"] is False)
_lido = mapeadores.situacao_no_omie(recebimento("1", "S", cFaturado="N"))
checar("as marcas lidas voltam inteiras, com a etapa, para conferir no ar",
       _lido["marcas"].get("cCancelada") == "S" and _lido["marcas"].get("cEtapa") == "40"
       and "cFaturado" in _lido["marcas"], _lido["marcas"])
checar("resposta vazia não derruba a leitura",
       mapeadores.situacao_no_omie(None) == {"cancelada": False, "marcas": {}})


def ja_chega_cancelada(cur, id_unidade):
    id_nota = gravar(cur, id_unidade, recebimento("2", "S"))
    checar("a nota é gravada, e nasce CANCELADA", status_de(cur, id_nota) == "CANCELADA",
           status_de(cur, id_nota))
    checar("o item dela NÃO entra na fila de conciliação", na_fila(cur, id_nota) == 0)
    try:
        importador.lancar_nota(cur, id_nota, 1)
        recusa = None
    except HTTPException as e:
        recusa = e
    checar("lançar a cancelada é recusado, com a frase dizendo por quê",
           recusa is not None and recusa.status_code == 409
           and "cancelada no Omie" in str(recusa.detail), recusa)


def cancelada_depois_de_importada(cur, id_unidade):
    id_nota = gravar(cur, id_unidade, recebimento("3", "N"))
    checar("a nota entra aberta, com o item na fila",
           status_de(cur, id_nota) == "IMPORTADA" and na_fila(cur, id_nota) == 1,
           status_de(cur, id_nota))
    # 🔑 O caso do dono: cancelada no Omie depois, e "atualizar do Omie" aqui.
    bruto = recebimento("3", "S")
    r = importador.atualizar_nota(cur, id_nota, mapeadores.recebimento_de_nfe(bruto), bruto)
    checar("atualizar do Omie cancela a nota", status_de(cur, id_nota) == "CANCELADA"
           and r.get("cancelada") is True, (status_de(cur, id_nota), r))
    checar("e o item sai da fila", na_fila(cur, id_nota) == 0)
    # ⚠️ O recálculo roda em toda religação e em toda correção de cadastro: ele
    # devolvia a nota para IMPORTADA, de volta à fila.
    importador.calcular_nota(cur, id_nota)
    checar("o recálculo não ressuscita a cancelada", status_de(cur, id_nota) == "CANCELADA",
           status_de(cur, id_nota))
    importador.reconciliar(cur, id_unidade)
    checar("nem a religação", status_de(cur, id_nota) == "CANCELADA", status_de(cur, id_nota))
    # E o caminho de volta: cancelamento desfeito no Omie.
    bruto = recebimento("3", "N")
    r = importador.atualizar_nota(cur, id_nota, mapeadores.recebimento_de_nfe(bruto), bruto)
    checar("cancelamento desfeito no Omie devolve a nota à fila",
           status_de(cur, id_nota) == "IMPORTADA" and na_fila(cur, id_nota) == 1
           and r.get("cancelada") is False, (status_de(cur, id_nota), r))


def a_busca_automatica_cancela(cur, id_unidade):
    aberta = gravar(cur, id_unidade, recebimento("4", "N"))
    lancada = gravar(cur, id_unidade, recebimento("5", "N"))
    # A segunda já foi para o estoque: é a que NÃO pode ser mexida.
    cur.execute("UPDATE notas_entrada SET status = 'LANCADA' WHERE id = %s", (lancada,))
    omie = OmieDeMentira([recebimento("4", "S"), recebimento("5", "S")])
    r = importador.sincronizar(cur, id_unidade, omie, 5, None)
    checar("a busca percebe o cancelamento sem o valor ter mudado",
           r.get("atualizadas") == 1, {k: r.get(k) for k in ("atualizadas", "repetidas")})
    checar("e cancela a nota aberta", status_de(cur, aberta) == "CANCELADA",
           status_de(cur, aberta))
    # ⚠️ A mercadoria já está no estoque: nada é estornado sozinho.
    checar("a nota LANÇADA não é mexida", status_de(cur, lancada) == "LANCADA",
           status_de(cur, lancada))
    travadas = r.get("travadas") or []
    checar("mas a resposta a aponta, com o motivo: cancelada",
           any(t["id"] == lancada and "cancelada" in t["campos"] for t in travadas), travadas)
    # A segunda busca não refaz nada: a aberta já está cancelada.
    r2 = importador.sincronizar(cur, id_unidade, omie, 5, None)
    checar("buscar de novo não reprocessa a que já foi cancelada",
           r2.get("atualizadas") == 0, r2.get("atualizadas"))


class OmieQueRecusa:
    """Toda consulta falha — a conta bloqueada."""

    modo = "real"

    def __init__(self):
        self.chamadas = 0

    def chamar(self, *_a, **_k):
        self.chamadas += 1
        raise importador.ErroOmie("consumo indevido: aguarde", 425)


def atualizar_todas_as_abertas(cur, id_unidade):
    # ⚠️ Gravadas nesta ordem: a leva vai da mais NOVA para a mais velha, e as desta
    # rodada têm os ids mais altos da base — é o que as põe na frente das outras.
    lancada = gravar(cur, id_unidade, recebimento("6", "N"))
    igual = gravar(cur, id_unidade, recebimento("7", "N"))
    mudou = gravar(cur, id_unidade, recebimento("8", "N"))
    some = gravar(cur, id_unidade, recebimento("9", "N"))
    cur.execute("UPDATE notas_entrada SET status = 'LANCADA' WHERE id = %s", (lancada,))
    omie = OmieDeMentira([recebimento("6", "S"), recebimento("7", "N"),
                          recebimento("8", "N", valor=300.0), recebimento("9", "S")])

    # Primeira leva: só duas, para provar o encadeamento.
    r1 = importador.atualizar_abertas(cur, id_unidade, omie, limite=2)
    checar("a primeira leva confere as duas notas mais novas", r1["conferidas"] == 2, r1)
    checar("a que foi cancelada no Omie vira cancelada aqui",
           [n["id"] for n in r1["canceladas"]] == [some]
           and status_de(cur, some) == "CANCELADA", r1["canceladas"])
    checar("a de valor corrigido é atualizada, com o antes e o depois",
           [(n["id"], n["de"], n["para"]) for n in r1["atualizadas"]] == [(mudou, 280.0, 300.0)],
           r1["atualizadas"])
    checar("e a leva diz de onde a próxima continua", r1["proximo"] == mudou
           and r1["restantes"] >= 1, (r1["proximo"], r1["restantes"]))

    # Segunda leva, a partir de onde a primeira parou.
    r2 = importador.atualizar_abertas(cur, id_unidade, omie, limite=1,
                                      antes_de=r1["proximo"])
    checar("a segunda leva pega a seguinte, que está igual no Omie",
           r2["conferidas"] == 1 and r2["iguais"] == 1 and not r2["atualizadas"]
           and not r2["canceladas"], r2)
    checar("e a nota igual continua como estava", status_de(cur, igual) == "IMPORTADA",
           status_de(cur, igual))
    # ⚠️ A lançada não é nem consultada: a mercadoria já está no razão.
    checar("a nota LANÇADA não é mexida, mesmo cancelada no Omie",
           status_de(cur, lancada) == "LANCADA", status_de(cur, lancada))

    # Uma nota que não abre não leva as outras: a "9" some do Omie de mentira.
    cur.execute("UPDATE notas_entrada SET status = 'IMPORTADA' WHERE id = %s", (some,))
    sem_a_nove = OmieDeMentira([recebimento("7", "N"), recebimento("8", "N", valor=310.0)])
    r3 = importador.atualizar_abertas(cur, id_unidade, sem_a_nove, limite=2)
    checar("uma nota que falha é contada, com o motivo",
           [f["id"] for f in r3["falhas"]] == [some] and r3["falhas"][0]["motivo"], r3["falhas"])
    checar("e a seguinte é atualizada mesmo assim",
           [n["id"] for n in r3["atualizadas"]] == [mudou], r3["atualizadas"])
    checar("uma falha isolada não para a leva", r3["parou_por_falhas"] is False)

    # A conta bloqueada: falhas SEGUIDAS param a leva, para não piorar o bloqueio.
    bloqueado = OmieQueRecusa()
    r4 = importador.atualizar_abertas(cur, id_unidade, bloqueado, limite=50)
    checar("cinco recusas seguidas param a leva",
           r4["parou_por_falhas"] is True and bloqueado.chamadas == importador.FALHAS_SEGUIDAS,
           (r4["parou_por_falhas"], bloqueado.chamadas))
    checar("e ela não manda continuar", r4["proximo"] is None, r4["proximo"])
    # ⚠️ O ponto de retorno de cada nota: depois das falhas a transação segue usável.
    cur.execute("SELECT 1 AS vivo")
    checar("depois das falhas a transação continua de pé", cur.fetchone()["vivo"] == 1)


cenario("\n2. a nota que já chega cancelada", ja_chega_cancelada)
cenario("\n3. cancelada no Omie depois de importada", cancelada_depois_de_importada)
cenario("\n4. a busca automática", a_busca_automatica_cancela)
cenario("\n6. atualizar do Omie para todas as abertas", atualizar_todas_as_abertas)

print("\n5. nada ficou na base")
with get_cursor() as cur:
    cur.execute("SELECT count(*) AS n FROM notas_entrada WHERE nome_emitente = %s",
                (f"Fornecedor cancelado {marca}",))
    checar("nenhuma nota desta rodada", cur.fetchone()["n"] == 0)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print(f"  - {x}")
sys.exit(1 if falhas else 0)
