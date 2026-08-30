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
PRODUTO = "PRODUTO"

ADOTAR = "ADOTAR"
REATIVAR = "REATIVAR"
SEM_PAR = "SEM_PAR"
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


def corpo_do_produto(linha: dict, remoto: dict | None = None,
                    adotar: bool = False, grupo_la: int | None = None) -> dict:
    """`produtos` → o cadastro do cardápio (`produtos/save|update`).

    ⚠️ **Só o que o cardápio enxerga, e NADA de imposto.** Os campos fiscais da
    linha de preço (CFOP 5102, CSOSN 102, CST 00, PIS/Cofins, reforma
    tributária) estão preenchidos em 629 dos 630 no PDV, e o Botané não tem
    nenhum deles. Mandar `null` ali zeraria a emissão fiscal do cliente — muito
    pior que um preço errado, e sem botão de desfazer. Preço tem rota própria
    (`tabelapreco`), e mesmo lá só o `Valor` é nosso.

    ⚠️ **O grupo vai pelo `CodGrupoExterno`** — o id da nossa categoria. É o que
    a adoção das 29 categorias tornou possível: sem ela, cada produto teria de
    carregar o código do grupo de lá.
    ⚠️ A impressora, não: o modelo dela não tem código externo, então vai o
    `CodigoImpressora` guardado em `setores.codigo_pdv`.
    ⚠️ **`DescricaoCupom` é o `nome_curto`** — é ele que sai impresso no cupom e
    aparece no botão do PDV. Sem nome curto, cai no nome completo, porque um
    botão sem texto é pior que um botão com texto longo.
    """
    if adotar and remoto:
        return {**remoto, "codRefExterna": linha["id"]}
    corpo = {
        "codigo": int((remoto or {}).get("codigo") or linha.get("codigo_pdv") or 0),
        "codRefExterna": linha["id"],
        "descricaoCupom": (linha.get("nome_curto") or linha["nome"] or "").strip(),
        "descricaoDetalhada": (linha["nome"] or "").strip(),
        "status": bool(linha["ativo"]),
    }
    if linha.get("id_categoria"):
        # 🔑 **Quando a categoria já foi adotada, vai o código DELES.** O
        # `codGrupoExterno` obriga o PDV a resolver o nosso id, e ele só resolve
        # o que já foi adotado — mandar o número real é mais firme e não depende
        # de uma tradução do outro lado. O externo continua junto: é ele que
        # mantém o de-para visível lá.
        corpo["codGrupoExterno"] = linha["id_categoria"]
        if grupo_la:
            corpo["codGrupo"] = int(grupo_la)
    if linha.get("setor_codigo_pdv"):
        corpo["codigoImpressora"] = int(linha["setor_codigo_pdv"])
    for nosso, deles in (("um_estoque", "unidade"), ("ncm", "codigoNCM"),
                         ("cest", "codigoCest"), ("codigo_barras", "codigoEAN")):
        if linha.get(nosso):
            corpo[deles] = str(linha[nosso])
    return corpo


MONTADORES = {CATEGORIA: corpo_da_categoria, SETOR: corpo_do_setor,
              PRODUTO: corpo_do_produto}


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

    # ⚠️ **Só os que participam.** São 6.945 produtos na base; montar o corpo de
    # todos a cada abertura da tela seria varrer o cadastro inteiro para achar
    # 533. O desmarcado entra pela pendência aberta — é ela que carrega o
    # pedido de saída.
    cur.execute(
        """SELECT p.id, p.nome, p.nome_curto, p.ativo, p.integrado_pdv, p.codigo_pdv,
                  p.id_categoria, p.id_setor, p.um_estoque, p.ncm, p.cest,
                  p.codigo_barras, s.codigo_pdv AS setor_codigo_pdv,
                  c.nome AS categoria_nome, c.integrado_pdv AS categoria_integrada,
                  (SELECT pp.preco_venda FROM produto_precos pp
                    WHERE pp.id_produto = p.id AND pp.vigente_ate IS NULL
                    ORDER BY pp.vigente_de DESC LIMIT 1) AS preco_venda
             FROM produtos p
             LEFT JOIN setores s ON s.id = p.id_setor
             LEFT JOIN categorias c ON c.id = p.id_categoria
            WHERE p.integrado_pdv
               OR EXISTS (SELECT 1 FROM pdv_pendencias q
                           WHERE q.tipo = 'PRODUTO' AND q.id_registro = p.id
                             AND q.resolvido_em IS NULL)
            ORDER BY p.nome""")
    linhas += [{**dict(r), "tipo": PRODUTO} for r in cur.fetchall()]
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
    produtos = cliente.get("/produtos/get") or []
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
        PRODUTO: {
            "por_ref": {int(p["codRefExterna"]): p for p in produtos
                        if p.get("codRefExterna")},
            # 🔑 **Produto NÃO casa por nome, e a ausência é deliberada.** A
            # cascata por nome foi REMOVIDA da importação do cardápio depois de
            # ligar REDBULL a LIMÃO TAITY e PÃO COM MANTEIGA a MANJERICÃO —
            # nenhum piso separa o acerto do erro, porque a diferença não está
            # no texto. Aqui quem reconhece é o `produtos.codigo_pdv`, que já
            # existe em 744 cadastros e foi posto lá por gente.
            "por_nome": {},
            "por_codigo": {str(p.get("codigo")): p for p in produtos},
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
    if la:
        # 🔑 **Grupo cujo dono daqui NÃO EXISTE MAIS volta a ser adotável.** O
        # `codRefExterna` guardado no PDV aponta para o id de uma categoria
        # nossa; se essa categoria for apagada, aquele grupo some do `por_ref`
        # (ninguém o reivindica) **e do `por_nome`** (que só recebe grupo sem
        # dono). Resultado: a categoria recadastrada com o MESMO nome não acha
        # nada dos dois lados e a fila propõe **CRIAR** — duplicando o cardápio
        # do cliente, que é exatamente o desastre que esta leitura existe para
        # impedir. Basta apagar uma categoria para cair nisso.
        cur.execute("SELECT id FROM categorias")
        nossas = {r["id"] for r in cur.fetchall()}
        orfaos = [g for ref, g in la[CATEGORIA]["por_ref"].items() if ref not in nossas]
        for g in orfaos:
            la[CATEGORIA]["por_ref"].pop(int(g["codRefExterna"]), None)
            la[CATEGORIA]["por_nome"].setdefault(
                str(g.get("nome", "")).strip().upper(), g)
    abertas = _pendencias_abertas(cur)
    pendentes: list[dict] = []
    integrados: list[dict] = []

    def grupo_do(linha: dict) -> int | None:
        """O código do grupo do PDV em que a categoria deste produto foi adotada."""
        if not la or not linha.get("id_categoria"):
            return None
        g = la[CATEGORIA]["por_ref"].get(linha["id_categoria"])
        return g.get("codigo") if g else None

    def montar(linha: dict, remoto: dict | None = None, adotar: bool = False) -> dict:
        if linha["tipo"] != PRODUTO:
            return MONTADORES[linha["tipo"]](linha, remoto, adotar=adotar)
        return corpo_do_produto(linha, remoto, adotar=adotar, grupo_la=grupo_do(linha))

    def trava(linha: dict) -> str | None:
        """O que impede este registro de sair — dito com as palavras da casa.

        ⚠️ **A categoria vai ANTES do produto, e sem ela o PDV recusa.** O
        produto carrega o grupo pelo `codGrupoExterno`, que o PDV só resolve se
        aquela categoria já tiver sido adotada lá. Sem isso o envio volta com a
        frase DELES, que não nomeia a categoria nem diz o caminho.
        """
        if linha["tipo"] != PRODUTO or not linha.get("id_categoria"):
            return None
        if grupo_do(linha):
            return None
        nome = linha.get("categoria_nome") or f"#{linha['id_categoria']}"
        if not linha.get("categoria_integrada"):
            return (f"A categoria “{nome}” não está marcada para integrar com o PDV. "
                    "Marque-a no cadastro da categoria e envie a categoria primeiro — "
                    "o produto precisa do grupo já existir lá.")
        return (f"A categoria “{nome}” ainda não chegou ao PDV. Ela está nesta mesma "
                "fila: envie a categoria primeiro e depois o produto.")

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
            elif tem_pendencia and ja_e_nosso and tipo == PRODUTO and remoto.get("status"):
                # ⚠️ No produto o campo chama `status`, não `ativo` — é o modelo
                # deles, e trocar um pelo outro mandaria um campo que o PDV
                # ignora: o produto continuaria no cardápio e a tela diria que
                # saiu.
                pendentes.append(_item(linha, DESATIVAR,
                                       {**remoto, "status": False}, anterior, remoto))
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

        # ⚠️ **Produto desativado AQUI sai do cardápio — categoria não.** No
        # produto você mandou que desativar aqui desative lá; na categoria o
        # `ativo` tem donos diferentes (PASCOA fica ativa aqui o ano todo e é
        # ligada e desligada lá conforme a época).
        # 🔑 O que impede o ping-pong é a PENDÊNCIA: é a mudança feita AQUI que
        # autoriza mexer no `ativo` de LÁ. Alguém desativou no PDV e nada mudou
        # aqui? Sem pendência, sem ação — e nada é reativado por engano.
        if tipo == PRODUTO and ja_e_nosso and tem_pendencia:
            if not linha["ativo"] and remoto.get("status"):
                pendentes.append(_item(linha, DESATIVAR,
                                       {**remoto, "status": False}, anterior, remoto))
                continue
            if linha["ativo"] and not remoto.get("status"):
                corpo = montar(linha, remoto)
                pendentes.append(_item(linha, REATIVAR, corpo, anterior, remoto,
                                       trava(linha)))
                continue

        # 1. Existe lá e já é nosso (o `codRefExterna` aponta para cá).
        if ja_e_nosso:
            corpo = montar(linha, remoto)
            # ⚠️ **A pendência manda, mas a REALIDADE tem voto.** Se o banco
            # registrou uma mudança, é pendente; se não registrou, ainda assim
            # entra quando o que está lá difere do que temos — é a rede que
            # pega o que mudou por fora (uma carga, um `UPDATE` na mão) e o
            # que o gatilho não viu porque nasceu depois dele.
            grupo_la = grupo_do(linha)
            if tem_pendencia or _difere(tipo, corpo, remoto, grupo_la):
                pendentes.append(_item(linha, ATUALIZAR, corpo, anterior, remoto,
                                       trava(linha)))
            else:
                integrados.append(_item(linha, ATUALIZAR, corpo, anterior, remoto))
            continue

        # 2. Existe lá com o mesmo nome e sem dono: ADOTAR, nunca criar.
        # ⚠️ Sempre pendente, com ou sem pendência registrada: enquanto o
        # `codRefExterna` não estiver gravado lá, o vínculo não existe — e é
        # exatamente isso que a adoção conserta.
        if remoto:
            corpo = montar(linha, remoto, adotar=True)
            pendentes.append(_item(linha, ADOTAR, corpo, anterior, remoto))
            continue

        # 3. Não existe lá.
        if tipo == PRODUTO:
            # ⚠️ **Produto INATIVO aqui não nasce no cardápio.** Criar lá algo
            # que esta casa já não vende é povoar o PDV com o que ninguém quer
            # ver — e foram 67 assim, todos resíduo de suíte.
            if not linha["ativo"]:
                continue
            # 🔑 **Vínculo PERDIDO não vira cadastro novo.** Tem `codigo_pdv`
            # guardado e esse código não está mais no cardápio: o produto foi
            # removido de lá, ou o código nunca foi de verdade (137 assim, com
            # nomes de teste). Criar um segundo cadastro deixaria o código
            # velho apontando para o nada e um duplicado no lugar. Fica à
            # VISTA, sem agir — quem resolve é gente, tirando a marca ou
            # limpando o código.
            if linha.get("codigo_pdv"):
                integrados.append(_item(linha, SEM_PAR, {"codigo_pdv": linha["codigo_pdv"]},
                                        anterior, None))
                continue
        corpo = montar(linha)
        pendentes.append(_item(linha, CRIAR, corpo, anterior, None, trava(linha)))

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
    elif tipo == PRODUTO:
        # 🔑 **No produto quem manda é o `codigo_pdv` guardado AQUI, não o
        # `codRefExterna` de lá — e a razão é medida: `produtos/update`
        # RESPONDE "Registry updated successfully!" e IGNORA o campo.** As 630
        # adoções da primeira versão saíram todas "com sucesso" e o
        # `codRefExterna` continuou `0` no cardápio; a fila relia, não achava
        # dono, e propunha as mesmas 630 adoções de novo. Uma fila que nunca
        # esvazia e reescreve o cardápio inteiro a cada clique.
        # ⚠️ É a mesma lição do SETOR: **onde não há onde gravar o vínculo, o
        # vínculo mora deste lado.** E aqui ele já morava — `produtos.codigo_pdv`
        # é único, visível e editável desde a migração 035.
        cod = str(linha.get("codigo_pdv") or "")
        if cod:
            achado = la[tipo]["por_codigo"].get(cod)
            if achado:
                return achado, True
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


def _difere(tipo: str, corpo: dict, remoto: dict, grupo_la: int | None = None) -> bool:
    """Mudou algo que o PDV precisa saber?

    ⚠️ Compara só os campos que ENVIAMOS. O PDV devolve mais coisas que não
    controlamos (e a cor, que ele às vezes troca sozinho): incluí-las faria
    todo registro parecer eternamente pendente.
    """
    # ⚠️ `ativo` fica FORA da comparação pelo mesmo motivo: com ele, as quatro
    # categorias sazonais apareceriam como pendentes para sempre, e cada envio
    # as reativaria no cardápio.
    if tipo == PRODUTO:
        # ⚠️ Só o que ENVIAMOS. O PDV devolve dezenas de campos que não
        # controlamos (favorito, destaque, modificadores…); compará-los faria
        # todo produto parecer eternamente pendente.
        if any(corpo.get(c) != remoto.get(c)
               for c in ("descricaoCupom", "descricaoDetalhada", "codigoImpressora")
               if c in corpo):
            return True
        # 🔑 **O grupo NÃO se compara pelo campo que mandamos.** Mandamos
        # `codGrupoExterno` (o id da nossa categoria) e o PDV devolve **sempre
        # `0`** nele — ele resolve o grupo e guarda em `codGrupo`. Comparar um
        # com o outro fazia os 630 produtos ficarem eternamente pendentes, e
        # cada Enviar reescrever o cardápio inteiro sem nada ter mudado. É a
        # mesma doença que a cor e o `ativo` já tinham: **campo que o outro lado
        # não devolve não serve de comparação.**
        # A pergunta certa é: o grupo que o produto tem LÁ é o mesmo em que a
        # nossa categoria foi adotada?
        if "codGrupoExterno" in corpo:
            return grupo_la is None or int(remoto.get("codGrupo") or 0) != int(grupo_la)
        return False
    campos = ("nome",)
    return any(corpo.get(c) != remoto.get(c) for c in campos)


def _item(linha: dict, acao: str, corpo: dict, anterior: dict | None,
          remoto: dict | None = None, impedimento: str | None = None) -> dict:
    return {
        # 🔑 **O que trava o envio é dito AQUI, não pelo PDV.** Um produto cuja
        # categoria ainda não existe lá volta com "O código ou o nome do Grupo
        # devem ser informados" — a frase do outro sistema, que não diz qual
        # grupo nem o que fazer. A recusa daqui nomeia a categoria e a saída.
        "impedimento": impedimento,
        "tipo": linha["tipo"],
        "id_registro": linha["id"],
        "nome": linha["nome"],
        "acao": acao,
        "corpo": corpo,
        "impressao": impressao(corpo),
        # ⚠️ FORA do corpo: o corpo é o que vai para o cadastro, e o preço tem
        # rota própria. Misturá-lo ali mandaria um campo que `produtos/update`
        # ignora — e a tela diria que o preço saiu.
        "preco": linha.get("preco_venda"),
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
    PRODUTO: {"criar": "/produtos/save", "atualizar": "/produtos/update",
              # Desativar e reativar são o MESMO update, com `status` trocado —
              # não existe rota própria, e `produtos/delete` fica fora de
              # propósito: quem tira um item do cardápio de vez é gente, lá.
              "desativar": "/produtos/update", "reativar": "/produtos/update"},
}


PRECO = "PRECO"


def enviar_preco(cliente, filial: int, codigo_pdv: str, valor) -> dict:
    """Muda SÓ o preço na linha da tabela do PDV, preservando o resto.

    🔑 **Os impostos moram no PDV e o Botané não tem nenhum deles.** Medido na
    conta real: `codCFOP` 5102, `codCSOSN` 102, `codCST` 00 e `codPisCofins`
    preenchidos em 629 dos 630, além de PIS/Cofins em 44 e do objeto inteiro da
    `reformaTributaria` em todos. Mandar um `tabelapreco/update` com apenas
    `CodProduto` e `Valor` — e o PUT substituindo a linha — **zeraria a emissão
    fiscal do cliente**. Não se desfaz com um botão, e ninguém percebe até o
    primeiro cupom recusado.

    Então é leitura-alteração-escrita: pega a linha como ela está, troca o
    `valor`, devolve tudo o mais idêntico. A divisão fica limpa — o Botané
    decide **quanto custa**, o PDV continua sabendo **como tributar**.

    ⚠️ `CodProduto` é o código DELES e é o único campo obrigatório: preço só sai
    depois de o cadastro existir lá e o `codigo_pdv` estar guardado aqui.
    """
    linhas = cliente.get(f"/tabelapreco/get/{filial}") or []
    atual = next((l for l in linhas if str(l.get("codProduto")) == str(codigo_pdv)), None)
    if atual is None:
        raise ErroPdv(
            f"O produto {codigo_pdv} não tem linha na tabela de preços da filial {filial}. "
            "O preço é gravado sobre a linha que já existe — criar uma do zero exigiria "
            "inventar os impostos, que são do PDV.")
    if float(atual.get("valor") or 0) == float(valor or 0):
        return {"sem_mudanca": True, "valor": atual.get("valor")}
    return cliente.enviar("PUT", "/tabelapreco/update", {**atual, "valor": float(valor)})


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


def enviar_um(cliente: ClientePdv, item: dict, filial: int | None = None) -> dict:
    """Manda UM registro. Devolve o que voltou; levanta `ErroPdv` no que falhar.

    ⚠️ **O preço vai DEPOIS do cadastro, e só quando o produto já existe lá.**
    `tabelapreco` exige o `CodProduto` — o código DELES —, então um produto
    recém-criado só ganha preço no envio seguinte, quando o código já está
    guardado aqui. Mandar antes daria um erro que fala de um campo obrigatório
    e não da ordem das coisas.
    """
    if item.get("impedimento"):
        # ⚠️ Recusa ANTES de falar com o PDV: a chamada voltaria com a frase
        # dele, que não nomeia o que falta. E uma tentativa que já se sabe
        # perdida é cota gasta.
        raise ErroPdv(item["impedimento"])
    rotas = ROTAS[item["tipo"]]
    acao = item["acao"]

    # 🔑 **Adotar um SETOR não escreve no PDV — não há onde.** A impressora não
    # tem campo de código externo (`{codigo, nome, kds}` é o modelo inteiro),
    # então "reconhecer" uma impressora é guardar o código DELA deste lado, e
    # mais nada. A primeira versão mandava um `impressoras/update` aqui: uma
    # escrita sem propósito no cardápio de quem está vendendo, que ainda por
    # cima falhou e derrubou o lote.
    # 🔑 **Adotar não escreve no PDV — nem setor, nem produto.** A impressora
    # não tem campo de código externo (`{codigo, nome, kds}` é o modelo
    # inteiro), e o produto TEM o campo mas o `update` o ignora, medido contra a
    # conta real. Nos dois casos "reconhecer" é guardar o código DELES deste
    # lado, e mais nada. Escrever assim mesmo seria uma volta no cardápio de
    # quem está vendendo que não muda nada — e a primeira versão deu 630 delas.
    if acao == ADOTAR and item["tipo"] in (SETOR, PRODUTO):
        return {"id": item["corpo"].get("codigo") or item.get("codigo_pdv"),
                "somente_local": True}

    if acao == DESATIVAR and "desativar" not in rotas:
        raise ErroPdv("Este cadastro não pode ser desativado no PDV — "
                      "o modelo de impressora não tem o campo.")
    caminho = rotas["criar" if acao == CRIAR else
                    ("desativar" if acao == DESATIVAR else "atualizar")]
    metodo = "POST" if acao == CRIAR else "PUT"
    resposta = cliente.enviar(metodo, caminho, item["corpo"])

    if (item["tipo"] == PRODUTO and acao != DESATIVAR
            and item.get("preco") is not None and filial):
        codigo = str((resposta or {}).get("id") or item.get("codigo_pdv") or "")
        if codigo:
            try:
                resposta = {**(resposta or {}),
                            "preco": enviar_preco(cliente, filial, codigo, item["preco"])}
            except ErroPdv as e:
                # ⚠️ O cadastro FOI. Estourar aqui faria o item inteiro contar
                # como erro e voltar para a fila, e o próximo envio repetiria um
                # cadastro que já está certo. O que falhou foi o preço, e é isso
                # que a resposta diz.
                resposta = {**(resposta or {}), "preco_falhou": str(e)}
    return resposta
