"""Enviar cadastros do Botané PARA o cardápio do PDV.

Até aqui a integração era de mão única. Este arquivo abre a outra, e tudo nele
sai de medição contra a conta real (29/08/2026) — o estudo está em
`docs/pdv-envio.md`.

🔑 **A fila é DERIVADA, não mantida.** `pdv_envios` guarda o que FOI enviado,
nunca o que falta. Pendente é uma pergunta: *está marcado para integrar E (nunca
foi enviado OU o que seria enviado agora difere do último envio que deu certo)*.
Uma coluna "pendente" marcada na hora de salvar teria de ser alimentada em todos
os lugares que escrevem um cadastro — e o próximo, que vai existir, nasceria sem
ela: o registro mudaria aqui e nunca apareceria na fila. É a lição do gatilho de
maiúsculas, aplicada ao contrário.

🔑 **A impressão (hash) é do CORPO que vai ser mandado**, não dos campos que
alguém listou. Assim, o dia em que o corpo ganhar um campo novo, a fila passa a
notar mudanças nele sozinha — sem ninguém lembrar de acrescentá-lo a uma lista
de comparação.

⚠️ **Categoria e setor não são simétricos, e a API é que decide isso:**

| | corpo no PDV | de-para |
|---|---|---|
| categoria → `grupoprodutos` | `codigo, nome, corIcone, codRefExterna, ativo` | **`codRefExterna` = o nosso id**, e `get/{nosso_id}` responde |
| setor → `impressoras` | `codigo, nome, kds` | **não existe** campo externo: guardamos `setores.codigo_pdv` |

⚠️ **"Excluir" no PDV é DESATIVAR.** O `delete` responde "deleted successfully"
e o registro continua na lista com `ativo: false`. Para impressora não há nem
isso — o modelo não tem `ativo` —, então setor não tem ação de desativar.
"""

import hashlib
import json
from typing import Any

from fastapi import HTTPException

from services.pdv.cliente import ClientePdv, ErroPdv

CATEGORIA = "CATEGORIA"
SETOR = "SETOR"

ADOTAR = "ADOTAR"
CRIAR = "CRIAR"
ATUALIZAR = "ATUALIZAR"
DESATIVAR = "DESATIVAR"


def impressao(corpo: dict) -> str:
    """O hash do corpo, estável entre execuções.

    ⚠️ `sort_keys` não é detalhe: sem ele a ordem das chaves entra no hash, e o
    mesmo cadastro pareceria mudado a cada leitura do banco.
    """
    bruto = json.dumps(corpo, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# O corpo de cada tipo — a única coisa que sabe traduzir o Botané para o PDV
# ---------------------------------------------------------------------------

def corpo_da_categoria(linha: dict, remoto: dict | None = None,
                       adotar: bool = False) -> dict:
    """`categorias` → `grupoprodutos`.

    ⚠️ **Adotar é um update que só toca no de-para.** Medido na conta real: com
    `{**o_que_esta_la, "codRefExterna": nosso_id}`, o nome, a cor e o `ativo`
    ficam intactos, e o grupo passa a responder por `get/{nosso_id}`. Mandar os
    NOSSOS campos numa adoção reescreveria a cor que alguém escolheu no PDV —
    adotar é reconhecer, não impor.

    ⚠️ `codigo` é o id DELES: vai o deles quando existe, 0 quando é criação.
    Quem resolve o registro depois é o `codRefExterna`.
    """
    if adotar and remoto:
        return {**remoto, "codRefExterna": linha["id"]}
    return {
        "codigo": int((remoto or {}).get("codigo") or 0),
        # A cor de lá quando o grupo já existe; a da casa só no que nasce aqui.
        "corIcone": (remoto or {}).get("corIcone") or "2C6A4A",
        "nome": (linha["nome"] or "").strip(),
        "codRefExterna": linha["id"],
        # 🔑 **`ativo` NÃO se sincroniza, e isso custou caro para descobrir.**
        # O campo tem donos diferentes dos dois lados: aqui quer dizer "uso este
        # cadastro"; lá quer dizer "aparece no cardápio para vender AGORA".
        # PASCOA e DIA DOS NAMORADOS ficam ativas aqui o ano todo e são ligadas
        # e desligadas lá conforme a época — quatro categorias estavam
        # exatamente assim. Mandar o nosso `ativo` reativaria a Páscoa em agosto
        # no cardápio de quem está vendendo.
        # Quem existe lá fica com o `ativo` DE LÁ; só o que nasce daqui nasce
        # visível. Desativar continua existindo, mas como ação explícita de
        # quem desmarcou aqui — nunca como efeito de sincronização.
        "ativo": bool(remoto["ativo"]) if remoto else True,
    }


def corpo_do_setor(linha: dict, remoto: dict | None = None,
                   adotar: bool = False) -> dict:
    """`setores` → `impressoras`. Sem `ativo` e sem código externo — é o modelo.

    ⚠️ Como não há campo externo, **adotar aqui é só guardar o código deles
    deste lado** (`setores.codigo_pdv`) — não há o que escrever lá. Por isso a
    adoção de setor não manda nada: ela grava o de-para e pronto.
    """
    return {
        "codigo": int((remoto or {}).get("codigo") or linha.get("codigo_pdv") or 0),
        "nome": (linha["nome"] or "").strip(),
        "kds": bool((remoto or {}).get("kds", False)),
    }


def corpo_de_saida(linha: dict, remoto: dict | None) -> dict:
    """O que mostrar de quem saiu da integração e continua vinculado lá."""
    return {"nome": (linha["nome"] or "").strip(),
            "codigo": (remoto or {}).get("codigo"),
            "ativo_no_pdv": (remoto or {}).get("ativo")}


MONTADORES = {CATEGORIA: corpo_da_categoria, SETOR: corpo_do_setor}


# ---------------------------------------------------------------------------
# A fila
# ---------------------------------------------------------------------------

def _ultimos_ok(cur, id_unidade: int) -> dict[tuple[str, int], dict]:
    """O último envio BEM-SUCEDIDO de cada registro."""
    cur.execute(
        """SELECT DISTINCT ON (tipo, id_registro)
                  tipo, id_registro, impressao, acao, codigo_pdv, criado_em
             FROM pdv_envios
            WHERE id_unidade = %s AND estado = 'OK'
            ORDER BY tipo, id_registro, id DESC""",
        (id_unidade,),
    )
    return {(r["tipo"], r["id_registro"]): dict(r) for r in cur.fetchall()}


def _erros_abertos(cur, id_unidade: int) -> dict[tuple[str, int], dict]:
    """A última tentativa de cada registro, quando ela falhou.

    ⚠️ "Último" e não "algum": um erro consertado e reenviado com sucesso não
    pode continuar na aba de erros — senão a aba vira um cemitério que ninguém
    mais lê.
    """
    cur.execute(
        """SELECT DISTINCT ON (tipo, id_registro)
                  tipo, id_registro, estado, acao, erro, enviado, criado_em, id
             FROM pdv_envios
            WHERE id_unidade = %s
            ORDER BY tipo, id_registro, id DESC""",
        (id_unidade,),
    )
    return {(r["tipo"], r["id_registro"]): dict(r)
            for r in cur.fetchall() if r["estado"] == "ERRO"}


def _registros(cur, id_unidade: int) -> list[dict]:
    """Quem está marcado para integrar, dos dois tipos, já com o corpo montado.

    ⚠️ Traz também o DESMARCADO que já foi enviado: ele é a fila de desativação.
    Sem isso, tirar a marca de uma categoria não teria efeito nenhum lá, e a
    tela mentiria dizendo que ela não é mais integrada.
    """
    cur.execute(
        """SELECT id, nome, ativo, integrado_pdv FROM categorias ORDER BY nome""")
    linhas = [{**dict(r), "tipo": CATEGORIA} for r in cur.fetchall()]
    cur.execute(
        """SELECT id, nome, ativo, integrado_pdv, codigo_pdv FROM setores
            WHERE id_unidade IS NULL OR id_unidade = %s ORDER BY nome""",
        (id_unidade,),
    )
    linhas += [{**dict(r), "tipo": SETOR} for r in cur.fetchall()]
    return linhas


def _o_que_existe_la(cliente) -> dict[str, dict]:
    """O estado do outro lado, por tipo: o que já existe no cardápio do PDV.

    🔑 **Sem esta leitura a fila é PERIGOSA.** `pdv_envios` só sabe o que ESTE
    sistema mandou; numa casa que já usa o PDV há anos, ele nunca mandou nada —
    e a fila concluiria "nunca foi enviado, logo CRIAR" para os 30 grupos que
    já estão lá. Apertar Enviar duplicaria o cardápio inteiro do cliente.

    O de-para verdadeiro mora no PDV (`codRefExterna`), e hoje ele está zerado
    em todos os 30. Quem responde "isto já existe?" é esta chamada.

    ⚠️ **Falhar aqui NÃO pode virar "então crie tudo".** O erro sobe, e a tela
    diz que não deu para falar com o PDV — o padrão seguro é não fazer nada.
    """
    grupos = cliente.get("/grupoprodutos/get") or []
    impressoras = cliente.get("/impressoras/get") or []
    return {
        CATEGORIA: {
            "por_ref": {int(g["codRefExterna"]): g for g in grupos if g.get("codRefExterna")},
            "por_nome": {str(g.get("nome", "")).strip().upper(): g for g in grupos
                         if not g.get("codRefExterna")},
        },
        SETOR: {
            "por_ref": {},   # impressora não tem código externo — é o modelo dela
            "por_nome": {str(i.get("nome", "")).strip().upper(): i for i in impressoras},
        },
    }


def _pendencias_abertas(cur) -> dict[tuple[str, int], dict]:
    """O que o BANCO registrou como mudado e ainda não foi ao PDV.

    🔑 **É esta tabela que responde "o que falta", não uma varredura.** Alterar
    um cadastro aqui não escreve no PDV: gera uma pendência, que espera alguém
    conferir e mandar. E quem a alimenta é o gatilho da 043 — nenhum caminho da
    aplicação consegue esquecer, nem o que ainda vai ser escrito.

    ⚠️ O `motivo` diz o que aconteceu AQUI (criado, alterado, removido). O que
    será feito LÁ — adotar, criar, atualizar, desativar — é outra pergunta, e
    quem responde é o envio, olhando o que o PDV já tem.
    """
    cur.execute(
        """SELECT tipo, id_registro, motivo, detectado_em
             FROM pdv_pendencias WHERE resolvido_em IS NULL""")
    return {(r["tipo"], r["id_registro"]): dict(r) for r in cur.fetchall()}


def fila(cur, id_unidade: int, cliente=None) -> dict[str, list[dict]]:
    """As três abas da tela, numa consulta só.

    - **pendentes**: marcado e nunca enviado, ou mudou desde o último envio OK
    - **integrados**: enviado com sucesso e igual ao que está aqui
    - **erros**: a última tentativa falhou, com a mensagem e o corpo mandado
    """
    ok = _ultimos_ok(cur, id_unidade)
    erros = _erros_abertos(cur, id_unidade)
    # 🔑 Sem saber o que existe do outro lado, a fila mandaria CRIAR para os 30
    # grupos que já estão no cardápio — e duplicaria o cardápio do cliente.
    la = _o_que_existe_la(cliente) if cliente is not None else None
    abertas = _pendencias_abertas(cur)
    pendentes: list[dict] = []
    integrados: list[dict] = []

    for linha in _registros(cur, id_unidade):
        tipo = linha["tipo"]
        chave = (tipo, linha["id"])
        anterior = ok.get(chave)
        remoto, ja_e_nosso = _remoto(la, linha) if la else (None, False)

        tem_pendencia = chave in abertas

        if not linha["integrado_pdv"]:
            # Só entra na fila quem JÁ está lá por nossa conta: desmarcar algo
            # que nunca saiu daqui não é pendência, é o estado normal de
            # milhares de cadastros que não têm o que fazer no PDV.
            if tem_pendencia and ja_e_nosso and tipo == CATEGORIA and remoto.get("ativo"):
                corpo = {**remoto, "ativo": False}
                pendentes.append(_item(linha, DESATIVAR, corpo, anterior, remoto))
            elif anterior or ja_e_nosso:
                # ⚠️ **Desmarcado que JÁ SAIU daqui não some da tela.** O ciclo
                # é: tirar do PDV → pendente como desativar → enviar → e então
                # ele precisa aparecer em INTEGRADOS dizendo o que virou. Antes
                # ele desaparecia das três abas no instante do envio, e quem
                # tinha acabado de desativar uma categoria não via nada — nem
                # que deu certo, nem que ela continua vinculada lá.
                # ⚠️ No SETOR este é o estado FINAL: a impressora não tem campo
                # `ativo`, então não há como desativá-la pela API. Ele fica
                # ligado lá para sempre, e sumir da tela esconderia isso.
                integrados.append(_item(linha, DESATIVAR, corpo_de_saida(linha, remoto),
                                        anterior, remoto))
            continue

        # 1. Existe lá e já é nosso (o `codRefExterna` aponta para cá).
        if ja_e_nosso:
            corpo = MONTADORES[tipo](linha, remoto)
            # ⚠️ **A pendência manda, mas a REALIDADE tem voto.** Se o banco
            # registrou uma mudança, é pendente; se não registrou, ainda assim
            # entra quando o que está lá difere do que temos — é a rede que
            # pega o que mudou por fora (uma carga, um `UPDATE` na mão) e o
            # que o gatilho não viu porque nasceu depois dele.
            if tem_pendencia or _difere(tipo, corpo, remoto):
                pendentes.append(_item(linha, ATUALIZAR, corpo, anterior, remoto))
            else:
                integrados.append(_item(linha, ATUALIZAR, corpo, anterior, remoto))
            continue

        # 2. Existe lá com o mesmo nome e sem dono: ADOTAR, nunca criar.
        # ⚠️ Sempre pendente, com ou sem pendência registrada: enquanto o
        # `codRefExterna` não estiver gravado lá, o vínculo não existe — e é
        # exatamente isso que a adoção conserta.
        if remoto:
            corpo = MONTADORES[tipo](linha, remoto, adotar=True)
            pendentes.append(_item(linha, ADOTAR, corpo, anterior, remoto))
            continue

        # 3. Não existe lá.
        corpo = MONTADORES[tipo](linha)
        pendentes.append(_item(linha, CRIAR, corpo, anterior, None))

    em_erro = []
    for chave, e in erros.items():
        nome = next((linha["nome"] for linha in _registros(cur, id_unidade)
                     if (linha["tipo"], linha["id"]) == chave), "(registro removido)")
        em_erro.append({
            "tipo": chave[0], "id_registro": chave[1], "nome": nome,
            "acao": e["acao"], "erro": e["erro"], "enviado": e["enviado"],
            "quando": e["criado_em"],
        })

    return {"pendentes": pendentes, "integrados": integrados, "erros": em_erro}


def _remoto(la: dict, linha: dict) -> tuple[dict | None, bool]:
    """O registro do outro lado que corresponde a este, e se ele JÁ é nosso.

    ⚠️ O casamento por NOME só decide a ADOÇÃO, e uma vez: dali em diante quem
    manda é o `codRefExterna` (categoria) ou o `codigo_pdv` guardado (setor).
    Não é a cascata por semelhança que este projeto removeu — é igualdade
    exata de nome, e a pessoa confirma na tela antes de qualquer envio.
    """
    tipo = linha["tipo"]
    if tipo == CATEGORIA:
        achado = la[tipo]["por_ref"].get(linha["id"])
        if achado:
            return achado, True
    else:
        cod = str(linha.get("codigo_pdv") or "")
        if cod:
            achado = next((i for i in la[tipo]["por_nome"].values()
                           if str(i.get("codigo")) == cod), None)
            if achado:
                return achado, True
    return la[tipo]["por_nome"].get((linha["nome"] or "").strip().upper()), False


def _difere(tipo: str, corpo: dict, remoto: dict) -> bool:
    """Mudou algo que o PDV precisa saber?

    ⚠️ Compara só os campos que ENVIAMOS. O PDV devolve mais coisas que não
    controlamos (e a cor, que ele às vezes troca sozinho): incluí-las faria
    todo registro parecer eternamente pendente.
    """
    # ⚠️ `ativo` fica FORA da comparação pelo mesmo motivo: com ele, as quatro
    # categorias sazonais apareceriam como pendentes para sempre, e cada envio
    # as reativaria no cardápio.
    campos = ("nome",)
    return any(corpo.get(c) != remoto.get(c) for c in campos)


def _item(linha: dict, acao: str, corpo: dict, anterior: dict | None,
          remoto: dict | None = None) -> dict:
    return {
        "tipo": linha["tipo"],
        "id_registro": linha["id"],
        "nome": linha["nome"],
        "acao": acao,
        "corpo": corpo,
        "impressao": impressao(corpo),
        "codigo_pdv": (str((remoto or {}).get("codigo") or "")
                       or (anterior or {}).get("codigo_pdv")
                       or linha.get("codigo_pdv")),
        "nome_no_pdv": (remoto or {}).get("nome"),
        "enviado_em": (anterior or {}).get("criado_em"),
    }


# ---------------------------------------------------------------------------
# O envio
# ---------------------------------------------------------------------------

ROTAS = {
    CATEGORIA: {"criar": "/grupoprodutos/save", "atualizar": "/grupoprodutos/update",
                "desativar": "/grupoprodutos/update"},
    SETOR: {"criar": "/impressoras/save", "atualizar": "/impressoras/update"},
}


def conferir_a_conta(cliente: ClientePdv, cnpj_da_casa: str | None) -> None:
    """🔑 De quem é a conta — ANTES de escrever qualquer coisa.

    Credencial de integração não diz de quem ela é. O primeiro par de chaves
    testado neste projeto autenticava, respondia tudo e apontava para outra
    empresa; foram 46 vendas e 165 pratos de terceiro dentro da base antes de
    alguém reparar no nome. **Lendo**, o erro custa dado estranho aqui;
    **escrevendo**, cadastra produto do Botané no PDV de outra empresa — e lá
    não existe "desfazer importação".

    ⚠️ Compara só os DÍGITOS: esta conta devolve o CNPJ sem pontuação e a outra
    devolvia com.
    """
    so_digitos = lambda v: "".join(c for c in str(v or "") if c.isdigit())  # noqa: E731
    esperado = so_digitos(cnpj_da_casa)
    if not esperado:
        raise HTTPException(
            status_code=400,
            detail=("O CNPJ da empresa não está preenchido em Administração ▸ Empresa. "
                    "Sem ele não dá para conferir se a conta do PDV é mesmo desta casa — "
                    "e escrever na conta errada cadastra os produtos daqui no PDV de "
                    "outra empresa."),
        )
    try:
        filiais = cliente.get("/filial/get") or []
    except ErroPdv as e:
        raise HTTPException(status_code=502, detail=f"Não deu para falar com o PDV: {e}")

    achados = [so_digitos(f.get("cnpj") or f.get("CNPJ")) for f in filiais]
    if esperado not in achados:
        nomes = ", ".join(str(f.get("razaoSocial") or f.get("nome") or "?") for f in filiais)
        raise HTTPException(
            status_code=409,
            detail=(f"A conta do PDV é de outra empresa: {nomes or 'nenhuma filial'}. "
                    f"O CNPJ desta casa ({cnpj_da_casa}) não está entre as filiais. "
                    "Nada foi enviado."),
        )


def enviar_um(cliente: ClientePdv, item: dict) -> dict:
    """Manda UM registro. Devolve o que voltou; levanta `ErroPdv` no que falhar."""
    rotas = ROTAS[item["tipo"]]
    acao = item["acao"]

    # 🔑 **Adotar um SETOR não escreve no PDV — não há onde.** A impressora não
    # tem campo de código externo (`{codigo, nome, kds}` é o modelo inteiro),
    # então "reconhecer" uma impressora é guardar o código DELA deste lado, e
    # mais nada. A primeira versão mandava um `impressoras/update` aqui: uma
    # escrita sem propósito no cardápio de quem está vendendo, que ainda por
    # cima falhou e derrubou o lote.
    if item["tipo"] == SETOR and acao == ADOTAR:
        return {"id": item["corpo"].get("codigo"), "somente_local": True}

    if acao == DESATIVAR and "desativar" not in rotas:
        raise ErroPdv("Este cadastro não pode ser desativado no PDV — "
                      "o modelo de impressora não tem o campo.")
    caminho = rotas["criar" if acao == CRIAR else
                    ("desativar" if acao == DESATIVAR else "atualizar")]
    metodo = "POST" if acao == CRIAR else "PUT"
    return cliente.enviar(metodo, caminho, item["corpo"])
