"""Trocar o `JWT_SECRET` NÃO pode custar as credenciais guardadas.

    python tests/smoke_rotacao_segredo.py        (não precisa da API de pé)

🔑 **Nasceu de um deploy real que não subiu** (11/09/2026). A trava do segredo
parou o start em produção — `JWT_SECRET curto demais (16 caracteres)` — e a
pergunta seguinte foi se dava para trocá-lo sem perder Omie, PDV e a senha de
SMTP. Dava não: o segredo deriva a chave do Fernet, então trocá-lo tornava
ilegível tudo o que estava cifrado. E uma troca que custa redigitar as
integrações é uma troca que se adia para sempre — quer dizer, o segredo fraco
fica.

⚠️ **Este arquivo fala com o BANCO, não com a API.** A rotação acontece no start,
antes de existir porta aberta; testá-la por HTTP exigiria derrubar e subir a API
com outro ambiente, e o que importa provar é o efeito nas linhas.

⚠️ **Nenhuma credencial de verdade é tocada.** O cenário usa um `servico` só
dele, numa linha criada e apagada aqui — a casa já perdeu credencial uma vez
porque uma suíte gravou chave de teste na mesma linha da real (ver
`preservar_credenciais`).
"""

import sys

sys.path.insert(0, ".")
from database import get_cursor  # noqa: E402
from services import segredos  # noqa: E402

ok = 0
falhas: list[str] = []

SERVICO = "TESTE_ROTACAO"
VELHO = "segredo-curto-16b"
NOVO = "segredo-novo-com-folga-de-sobra-para-o-minimo"
TERCEIRO = "um-terceiro-segredo-que-ninguem-conhece"


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


def com_segredos(atual: str, anterior: str):
    """Põe o módulo no estado de um ambiente — é o que o deploy faz por variável."""
    segredos.JWT_SECRET = atual
    segredos.JWT_SECRET_ANTERIOR = anterior


def gravar(cur, dados: dict, com_qual_segredo: str) -> int:
    """Grava uma credencial cifrada com um segredo escolhido."""
    guardado = (segredos.JWT_SECRET, segredos.JWT_SECRET_ANTERIOR)
    com_segredos(com_qual_segredo, "")
    bruto = segredos.cifrar(dados)
    com_segredos(*guardado)
    cur.execute(
        """INSERT INTO integracoes (id_unidade, servico, ativa, modo, credenciais)
           VALUES (NULL, %s, false, 'simulado', %s)
           ON CONFLICT (servico) WHERE id_unidade IS NULL
           DO UPDATE SET credenciais = EXCLUDED.credenciais
           RETURNING id""",
        (SERVICO, bruto),
    )
    return cur.fetchone()["id"]


original = (segredos.JWT_SECRET, segredos.JWT_SECRET_ANTERIOR)
try:
    print("1. a chave anterior abre o que a atual não abre")
    with get_cursor() as cur:
        com_segredos(NOVO, VELHO)
        id_linha = gravar(cur, {"app_key": "1234", "app_secret": "abcd"}, VELHO)
        cur.execute("SELECT credenciais FROM integracoes WHERE id = %s", (id_linha,))
        bruto = cur.fetchone()["credenciais"]

        checar("a credencial cifrada com o segredo VELHO continua abrindo",
               segredos.decifrar(bruto).get("app_key") == "1234", segredos.decifrar(bruto))
        # ⚠️ Sem isto a tela acusaria "credencial ilegível" durante a troca e
        # mandaria a casa redigitar o que está intacto.
        checar("e ela não é marcada como ilegível", segredos.ilegivel(bruto) is False)

        print("2. a regravação passa tudo para a chave de hoje")
        regravadas, perdidas = segredos.regravar_com_a_chave_atual(cur)
        checar("uma linha foi regravada", regravadas >= 1, (regravadas, perdidas))

        # 🔑 **A prova é com a variável APAGADA.** Conferir com a chave anterior
        # ainda no ambiente provaria só que o caminho de exceção funciona — e é
        # justamente ele que vai embora no deploy seguinte.
        com_segredos(NOVO, "")
        cur.execute("SELECT credenciais FROM integracoes WHERE id = %s", (id_linha,))
        agora = cur.fetchone()["credenciais"]
        checar("e abre SÓ com o segredo novo, sem a variável de transição",
               segredos.decifrar(agora).get("app_secret") == "abcd", segredos.decifrar(agora))

        print("3. rodar de novo não faz nada (o deploy seguinte é inofensivo)")
        com_segredos(NOVO, VELHO)
        de_novo, _ = segredos.regravar_com_a_chave_atual(cur)
        checar("a segunda passada não regrava nada", de_novo == 0, de_novo)

        print("4. o que nenhuma das duas chaves abre é CONTADO e deixado em paz")
        # Pode ser de outro ambiente, de um terceiro segredo ou dado corrompido.
        # Regravar seria escrever lixo por cima de lixo; apagar destruiria a
        # única pista do que aconteceu.
        # ⚠️ **Medido por DELTA, e a primeira versão não era.** A base tem
        # credenciais de verdade (Omie, PDV, SMTP) cifradas com o segredo DESTE
        # ambiente, que não é nenhum dos dois do cenário — então elas também
        # caem na contagem. Cobrar `perdidas == 1` acusava erro onde o
        # comportamento estava certo: nenhuma delas foi tocada.
        _, base_perdidas = segredos.regravar_com_a_chave_atual(cur)
        id_orfa = gravar(cur, {"app_key": "9999"}, TERCEIRO)
        cur.execute("SELECT credenciais FROM integracoes WHERE id = %s", (id_orfa,))
        antes_orfa = bytes(cur.fetchone()["credenciais"])
        _, perdidas = segredos.regravar_com_a_chave_atual(cur)
        checar("ela entra na contagem de perdidas",
               perdidas == base_perdidas + 1, (base_perdidas, perdidas))
        cur.execute("SELECT credenciais FROM integracoes WHERE id = %s", (id_orfa,))
        checar("e o conteúdo dela NÃO foi tocado",
               bytes(cur.fetchone()["credenciais"]) == antes_orfa)
        checar("a tela continua denunciando que é ilegível",
               segredos.ilegivel(antes_orfa) is True)

        print("5. sem a variável, a rotação nem acontece")
        com_segredos(NOVO, "")
        checar("sem JWT_SECRET_ANTERIOR devolve (0, 0)",
               segredos.regravar_com_a_chave_atual(cur) == (0, 0))
        # ⚠️ E a chave anterior não pode ser consultada fora da troca: um segredo
        # aposentado esquecido no ambiente continuaria abrindo tudo.
        checar("e a chave anterior deixa de existir",
               segredos._chave_anterior() is None)

        print("6. limpeza")
        cur.execute("DELETE FROM integracoes WHERE servico = %s", (SERVICO,))
        cur.execute("SELECT count(*) AS n FROM integracoes WHERE servico = %s", (SERVICO,))
        checar("a linha de teste saiu da base", cur.fetchone()["n"] == 0)
finally:
    segredos.JWT_SECRET, segredos.JWT_SECRET_ANTERIOR = original

print()
print(f"{ok} passaram, {len(falhas)} falharam")
sys.exit(1 if falhas else 0)
