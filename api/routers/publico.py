"""O que o SITE DO CLIENTE pode ler — sem login, sem token, sem cabeçalho.

🔑 **Pedido do dono (21/09/2026):** *"agora vamos criar o site para o cliente,
onde o front será separado, no oficial vamos colocar em
reserva.botanedeliecafe.com.br. Os itens serão: Reserva, Catálogos cadastrados e
ativos, Entre em Contato (onde vai abrir o whatsapp para enviar mensagem para o
número cadastrado para a empresa)."*

⚠️ **Este é o único router SEM permissão, e por isso ele é o mais estreito do
sistema.** Todo o resto da casa declara a chave que exige; aqui quem entra é o
público da internet. A regra que substitui a permissão é a do CONTEÚDO: só sai
daqui o que a casa já decidiu publicar — o catálogo que ela marcou como ativo, o
telefone que ela cadastrou, os horários que o salão comporta.

⚠️ **Nada de `id` interno, nada de contagem, nada de dado de negócio.** A
tentação num endpoint público é reaproveitar o serializador de dentro; o preço é
vazar o que ninguém pediu — quantas mesas a casa tem, quantas reservas existem
hoje, o nome de quem atendeu. Cada resposta aqui é montada à mão.

⚠️ **A loja vem no CAMINHO, não no cabeçalho `X-Unidade`.** O site do cliente não
tem sessão para guardar loja; e um dia haverá duas casas com reserva, cada uma no
seu endereço. `/publico/{id_unidade}/...` deixa isso resolvido desde já.

🔑 **A porta continua sendo `parametros.reservas_ligado`**: casa que não faz
reserva não aparece aqui — nem o catálogo dela, que é do site de reservas.
"""

from datetime import date, datetime, time

from fastapi import APIRouter, HTTPException, Query, Request

from database import get_cursor
from relogio import agora_da_casa
from models.catalogos import ORIGEM_PRODUTOS
from models.reservas import CancelamentoDoSite, ClienteDoSite, IdentificacaoDoSite, ReservaCreate, ReservaDoSite, TelefoneDoSite
from services import reserva_clientes as clientes
from services import reservas as reservas_servico
from services import reservas_agenda as agenda

router = APIRouter(prefix="/publico", tags=["site do cliente"])


def _so_digitos(v: str | None) -> str | None:
    """O telefone como o `wa.me` pede: só números, sem máscara.

    ⚠️ **O cadastro aceita o número digitado de qualquer jeito** — "(47) 99910-5033"
    é o normal —, e o link do WhatsApp não aceita nada além de dígitos. Quem
    limpa é aqui, não a tela: o site do cliente não deve saber o formato do
    cadastro da casa.
    """
    if not v:
        return None
    d = "".join(c for c in str(v) if c.isdigit())
    return d or None


def _casa_aberta(cur, id_unidade: int) -> dict:
    """A loja, se ela existe, está ativa e faz reserva. Senão, 404.

    ⚠️ **404, não 403.** Loja que não faz reserva não é um segredo guardado: do
    ponto de vista do site do cliente, ela simplesmente não existe. Um 403 diria
    ao público que aquele número corresponde a uma casa real.
    """
    cur.execute(
        """SELECT id, nome, apelido, cidade, uf, telefone, whatsapp, email,
                  logradouro, numero, bairro
             FROM unidades WHERE id = %s AND ativo""",
        (id_unidade,),
    )
    loja = cur.fetchone()
    if not loja or not reservas_servico.ligado(cur, id_unidade):
        raise HTTPException(status_code=404, detail="Casa não encontrada.")
    return dict(loja)


@router.get("/lojas")
def lojas() -> list[dict]:
    """As casas que recebem pelo site — o "Qual casa?" da página inicial.

    🔑 **Pedido do dono (24/09/2026):** duas lojas com reserva ligada no mesmo
    site. O cliente escolhe a casa; reserva, catálogos e contato são dela.
    ⚠️ **Só o NOME** (pedido do dono, 24/09/2026: *"no seletor de loja, colocar
    somente o nome; o endereço só ao selecionar, no rodapé"*). O endereço sai
    de `/casa`, depois da escolha. Nada de CNPJ, nada de quantas mesas.
    ⚠️ **Declarada ANTES de `/{id_unidade}/...`** por clareza; o caminho não
    colide, mas quem ler procura a lista antes do detalhe.
    """
    with get_cursor() as cur:
        cur.execute(
            """SELECT u.id, coalesce(nullif(u.apelido, ''), u.nome) AS nome
                 FROM unidades u JOIN parametros p ON p.id_unidade = u.id
                WHERE u.ativo AND p.reservas_ligado
                ORDER BY u.matriz DESC, u.nome""")
        return [{"id": r["id"], "nome": r["nome"]} for r in cur.fetchall()]


@router.get("/{id_unidade}/casa")
def casa(id_unidade: int) -> dict:
    """Quem é a casa, e como falar com ela.

    🔑 **É o que alimenta o "Entre em Contato"**: o WhatsApp sai daqui, do
    cadastro da empresa, e não escrito no site. O dia em que a casa trocar de
    número, ela troca em Administração ▸ Empresa e o site acompanha.
    ⚠️ **`whatsapp` pode vir nulo, e o site precisa lidar com isso** — hoje o
    campo está em branco nesta base. Devolver um número inventado seria pior que
    devolver nada: o cliente mandaria mensagem para um desconhecido.
    """
    with get_cursor() as cur:
        loja = _casa_aberta(cur, id_unidade)
        cur.execute(
            """SELECT nome_fantasia, razao_social, whatsapp, telefone, email,
                      instagram, logradouro, numero, bairro, cidade, uf, logo_url,
                      cor_primaria
                 FROM empresa WHERE id = 1""",
        )
        e = dict(cur.fetchone() or {})

        # ⚠️ O telefone da LOJA ganha do da empresa: é para ele que quem quer
        # falar com esta casa deve ligar. O WhatsApp é da empresa porque é o
        # canal único que o dono cadastrou.
        # 🔑 **O contato é da LOJA, com a empresa como segundo degrau** (pedido do
        # dono, 24/09/2026: *"o entre em contato separado por loja"*). Loja sem
        # WhatsApp próprio continua mostrando o da empresa, que é o de sempre.
        zap = _so_digitos(loja.get("whatsapp")) or _so_digitos(e.get("whatsapp"))
        # ⚠️ O endereço vai INTEIRO de um lado ou do outro: misturar a rua da
        # empresa com o bairro da loja daria um endereço que não existe.
        fonte = loja if loja.get("logradouro") else e
        endereco = ", ".join(
            [p for p in (fonte.get("logradouro"), fonte.get("numero"), fonte.get("bairro"))
             if p])

        return {
            "loja": loja["apelido"] or loja["nome"],
            "casa": e.get("nome_fantasia") or e.get("razao_social") or "Botané",
            "cidade": loja.get("cidade") or e.get("cidade"),
            "uf": loja.get("uf") or e.get("uf"),
            "endereco": endereco or None,
            "telefone": loja.get("telefone") or e.get("telefone"),
            # 🔑 Só os dígitos: é o que o `https://wa.me/<numero>` pede.
            "whatsapp": zap,
            "email": loja.get("email") or e.get("email"),
            "instagram": e.get("instagram"),
            # 🔑 **A logo cadastrada** (pedido do dono, 21/09/2026). Nula quando
            # a casa ainda não enviou uma — e aí o site desenha o medalhão com o
            # nome, como o protótipo. ⚠️ Inventar uma imagem seria pior: o
            # cliente veria a marca de outra pessoa.
            "logo_url": e.get("logo_url"),
            # A cor da casa, que o cadastro já guarda. O site pinta a capa com
            # ela em vez de trazer um verde escrito no HTML.
            "cor": e.get("cor_primaria"),
            **_quando_atende(cur, id_unidade),
            **_textos_do_zap(cur, id_unidade),
        }


# 🔑 **Os nomes dos dias, na voz de quem lê** — "Ter" e "Qua", não "2" e "3". A
# tela do cliente mostra "Ter · Qua · Qui · Sex · Sáb", como o protótipo.
# ⚠️ ISO: 1 = segunda … 7 = domingo. É a convenção da casa desde
# `parametros.fechamento_dia_semana`, e duas convenções de dia da semana no
# mesmo sistema não dão erro em lugar nenhum — só marcam no dia errado.
_DIAS = {1: "Seg", 2: "Ter", 3: "Qua", 4: "Qui", 5: "Sex", 6: "Sáb", 7: "Dom"}


def _textos_do_zap(cur, id_unidade: int) -> dict:
    """As mensagens que a casa escreveu para o WhatsApp (migração 081).

    🔑 **Pedido do dono (21/09/2026):** *"em configurações da reserva, colocar o
    texto padrão configurável para o whatsapp."* Estavam escritas no site, e
    texto de cliente escrito em código só muda quando alguém publica.

    ⚠️ **Os marcadores são trocados no SITE, não aqui.** `{pessoas}`, `{data}` e
    `{hora}` só existem no instante do clique — o servidor não sabe o que o
    cliente escolheu, e montar a frase aqui exigiria mandar a escolha de volta
    para receber um texto.
    """
    cur.execute(
        """SELECT whatsapp_texto, whatsapp_texto_reserva
             FROM reserva_config WHERE id_unidade = %s""",
        (id_unidade,),
    )
    t = dict(cur.fetchone() or {})
    return {
        "zap_texto": t.get("whatsapp_texto"),
        "zap_texto_reserva": t.get("whatsapp_texto_reserva"),
    }


def _quando_atende(cur, id_unidade: int) -> dict:
    """Em que dias a casa atende, e se ela está aberta AGORA.

    🔑 **É o que a capa do protótipo mostra**: a tarja "Aberto agora" e a linha
    com os dias. Sem isso o cliente abre o site às 23h, vê "Reservar uma mesa" e
    só descobre que a casa está fechada depois de escolher dia e horário.

    ⚠️ **"Aberto agora" é sobre a CASA, não sobre a reserva.** A última reserva
    é mais cedo que o fechamento de propósito — quem chega às 17h55 numa casa
    que fecha às 18h ainda é atendido, mas já não se reserva mesa.
    """
    cur.execute(
        """SELECT dia_semana, aberto, abre, fecha FROM reserva_horarios
            WHERE id_unidade = %s ORDER BY dia_semana""",
        (id_unidade,),
    )
    linhas = [dict(r) for r in cur.fetchall()]
    abertos = [d for d in linhas if d["aberto"]]
    # ⚠️ **A hora da CASA, nunca a do contêiner.** Era `datetime.now()`, e no
    # App Platform o processo roda em UTC: às 15:25 em Blumenau o servidor via
    # 18:25, passava do fechamento das 18:00 e a tarja dizia "Fechado · abre Qua
    # 09:30" com a casa cheia. Errava TODO dia, nas três últimas horas do
    # expediente. Ver `relogio.py` — é a segunda vez que este erro aparece.
    agora = agora_da_casa()
    hoje = next((d for d in abertos if d["dia_semana"] == agora.isoweekday()), None)
    return {
        "dias": [_DIAS[d["dia_semana"]] for d in abertos],
        "aberta_agora": bool(hoje and hoje["abre"] <= agora.time() <= hoje["fecha"]),
        # ⚠️ Quando a casa abre de novo, para a tarja poder dizer "abre Sáb 11:00"
        # em vez de só "fechado" — que é uma porta na cara de quem chegou.
        "hoje": (f'{hoje["abre"].strftime("%H:%M")} às {hoje["fecha"].strftime("%H:%M")}'
                 if hoje else None),
        # ⚠️ **O `i` começa em ZERO**: hoje entra quando a casa ainda não abriu.
        # Começava em 1, e numa quarta às 08:00 com abertura às 09:30 a tarja
        # dizia "abre Qui 09:30" — pulava o próprio dia. Hoje só conta se a
        # abertura ainda está à frente; depois do fechamento, o próximo é outro dia.
        "proximo": next(
            (f'{_DIAS[d["dia_semana"]]} às {d["abre"].strftime("%H:%M")}'
             for i in range(0, 8)
             for d in abertos
             if d["dia_semana"] == ((agora.isoweekday() + i - 1) % 7) + 1
             and (i > 0 or agora.time() < d["abre"])),
            None),
    }


@router.get("/{id_unidade}/catalogos")
def catalogos(id_unidade: int) -> list[dict]:
    """Os catálogos que a casa está publicando HOJE.

    🔑 *"Catálogos cadastrados e ativos"* — e "ativo" aqui é mais estreito que a
    situação: entra o que está `ATIVO`, **dentro do período** e **com arquivo**.
    ⚠️ **Sem PDF não entra na lista.** Um catálogo ativo sem arquivo é uma capa
    sem conteúdo; mostrá-lo ao cliente seria oferecer um cardápio que não abre.
    A tela de dentro avisa a casa exatamente sobre isso.
    ⚠️ **A regra do "no ar" é a MESMA de `services/catalogos.py`**, escrita em
    SQL aqui porque a consulta é outra — se ela mudar lá, muda aqui. É o preço de
    não trazer o serializador de dentro para uma rota pública.
    """
    with get_cursor() as cur:
        _casa_aberta(cur, id_unidade)
        cur.execute(
            """SELECT c.id, c.nome, c.origem, c.arquivo_url, c.arquivo_bytes,
                      c.publica_ate, c.exige_cadastro,
                      -- 🔑 **Quantos produtos VIVOS o cardápio tem.** É o que
                      -- diz se um catálogo de PRODUTOS tem o que mostrar — o
                      -- equivalente do `arquivo_url IS NOT NULL` do PDF.
                      (SELECT count(*)
                         FROM catalogo_itens i
                         JOIN catalogo_categorias g ON g.id = i.id_categoria
                         JOIN produtos p ON p.id = i.id_produto
                        WHERE g.id_catalogo = c.id AND p.ativo) AS itens
                 FROM catalogos c
                -- 🔑 **Visível NESTA loja** (migração 087), e não "dono é esta
                -- loja": a casa marca em que lojas cada catálogo aparece.
                WHERE EXISTS (SELECT 1 FROM catalogo_lojas l
                               WHERE l.id_catalogo = c.id AND l.id_unidade = %s)
                  AND c.situacao = 'ATIVO'
                  AND (c.publica_de IS NULL OR c.publica_de <= current_date)
                  AND (c.publica_ate IS NULL OR c.publica_ate >= current_date)
                ORDER BY c.publica_de NULLS FIRST, lower(c.nome)""",
            (id_unidade,),
        )
        saida = []
        for r in cur.fetchall():
            # ⚠️ **Capa sem conteúdo não entra**, e cada origem tem o seu
            # conteúdo: o PDF é o arquivo, o PRODUTOS são os itens. Mostrar
            # qualquer uma das duas vazia seria oferecer um cardápio que não
            # abre. A tela de dentro avisa a casa exatamente sobre isso.
            if r["origem"] == ORIGEM_PRODUTOS:
                if not r["itens"]:
                    continue
                saida.append({
                    "nome": r["nome"], "origem": ORIGEM_PRODUTOS,
                    "exige_cadastro": r["exige_cadastro"],
                    # ⚠️ **O id entra aqui, e é a exceção da regra "nada de id
                    # interno".** Sem ele o site não tem como pedir o cardápio
                    # de volta. Não é segredo: é a chave de algo que a casa
                    # DECIDIU publicar, como o sufixo do PDF também é.
                    "id": r["id"],
                    "arquivo_url": None, "bytes": None,
                    "ate": r["publica_ate"],
                })
                continue
            if not r["arquivo_url"]:
                continue
            # 🔑 **Catálogo que exige cadastro NÃO entrega o endereço do PDF aqui**
            # (pedido do dono, 24/09/2026). O site recebe o id e pede o arquivo
            # por `/catalogos/{id}/abrir`, com telefone e nome. Esconder o botão
            # só na tela seria validação de enfeite: o link estaria na resposta.
            fechado = r["exige_cadastro"]
            saida.append({
                "nome": r["nome"], "origem": r["origem"],
                "exige_cadastro": fechado,
                "id": r["id"] if fechado else None,
                "arquivo_url": None if fechado else r["arquivo_url"],
                "bytes": r["arquivo_bytes"],
                # ⚠️ Quando termina, para o site poder dizer "até domingo". Só
                # isso — a data de início não interessa a quem já está vendo.
                "ate": r["publica_ate"],
            })
        return saida


@router.get("/{id_unidade}/catalogos/{id_catalogo}")
def cardapio(id_unidade: int, id_catalogo: int) -> dict:
    """O cardápio montado: categorias, subcategorias, itens e PREÇO.

    🔑 **Pedido do dono (22/09/2026):** apresentar o catálogo na tela do site,
    com a estrutura dos dois prints — categoria com foto e descrição, tira de
    subcategorias, e o item com nome, preço e descrição.

    ⚠️ **Só produto ATIVO sai daqui.** A tela de configuração mostra o
    desativado marcado, para a casa descobrir que publicou algo que saiu de
    linha; o site é quem o esconde. São papéis diferentes da mesma informação.

    ⚠️ **Seção vazia não sai.** Uma categoria sem item nenhum vivo viraria um
    título com nada embaixo — o cliente rolaria procurando o que não existe.

    🔑 **O preço é o VIGENTE da loja**, com o da casa como segundo degrau — a
    mesma cascata que o PDV usa (`produto_precos`, `id_unidade` primeiro).
    ⚠️ **Produto sem preço sai sem preço, não com zero.** Zero é um número, e um
    número no cardápio é uma promessa.
    """
    with get_cursor() as cur:
        _casa_aberta(cur, id_unidade)
        capa = _no_ar(cur, id_unidade, id_catalogo)
        if not capa or capa["origem"] != ORIGEM_PRODUTOS:
            raise HTTPException(status_code=404, detail="Cardápio não encontrado.")
        # ⚠️ **403 com a frase, não o cardápio.** Sem isto, a exigência de
        # cadastro seria só do botão: quem chamasse a rota direto leria tudo.
        if capa["exige_cadastro"]:
            raise HTTPException(status_code=403,
                                detail="Identifique-se para ver este cardápio.")
        return _montar_cardapio(cur, id_unidade, id_catalogo, capa["nome"])


def _no_ar(cur, id_unidade: int, id_catalogo: int) -> dict | None:
    """O catálogo, se ele está publicado HOJE nesta casa. Senão, None.

    ⚠️ **A regra do "no ar" é a mesma da lista** (ativo e dentro do período).
    Rascunho, fora do período ou de outra casa simplesmente não existe para o
    público — por isso quem chama responde 404.
    """
    cur.execute(
        """SELECT nome, origem, arquivo_url, exige_cadastro FROM catalogos
            WHERE id = %s AND situacao = 'ATIVO'
              AND EXISTS (SELECT 1 FROM catalogo_lojas l
                           WHERE l.id_catalogo = catalogos.id AND l.id_unidade = %s)
              AND (publica_de IS NULL OR publica_de <= current_date)
              AND (publica_ate IS NULL OR publica_ate >= current_date)""",
        (id_catalogo, id_unidade),
    )
    linha = cur.fetchone()
    return dict(linha) if linha else None


def _montar_cardapio(cur, id_unidade: int, id_catalogo: int, nome: str) -> dict:
    """A árvore do cardápio montado por produtos: categorias, subcategorias, itens."""
    cur.execute(
        """SELECT g.id AS id_categoria, g.nome AS categoria,
                  g.descricao AS categoria_descricao, g.foto_url AS categoria_foto,
                  g.ordem AS categoria_ordem,
                  s.id AS id_subcategoria, s.nome AS subcategoria,
                  s.descricao AS subcategoria_descricao,
                  s.foto_url AS subcategoria_foto, s.ordem AS subcategoria_ordem,
                  i.id AS id_item, i.ordem AS item_ordem,
                  -- 🔑 **O nome de vitrine ganha do nome do cadastro**
                  -- (migração 085): o cadastro normaliza em CAIXA ALTA, e o
                  -- cardápio do cliente não é lugar de gritar. Nulo cai no
                  -- nome de sempre — a casa só escreve o segundo quando o
                  -- primeiro não serve.
                  coalesce(nullif(btrim(p.nome_catalogo), ''), p.nome) AS produto,
                  p.foto_url AS produto_foto,
                  p.informacao_adicional,
                  -- 🔑 O preço da LOJA primeiro, o da casa depois: é a
                  -- cascata de `services/precos.py`, e uma segunda regra
                  -- aqui faria o site cobrar diferente do balcão.
                  (SELECT pr.preco_venda FROM produto_precos pr
                    WHERE pr.id_produto = p.id AND pr.vigente_ate IS NULL
                      AND (pr.id_unidade = %(u)s OR pr.id_unidade IS NULL)
                    ORDER BY pr.id_unidade NULLS LAST LIMIT 1) AS preco
             FROM catalogo_itens i
             JOIN catalogo_categorias g ON g.id = i.id_categoria
             LEFT JOIN catalogo_subcategorias s ON s.id = i.id_subcategoria
             JOIN produtos p ON p.id = i.id_produto
            WHERE g.id_catalogo = %(c)s AND p.ativo
            ORDER BY g.ordem, lower(g.nome),
                     s.ordem NULLS FIRST, lower(s.nome),
                     i.ordem, lower(p.nome)""",
        {"c": id_catalogo, "u": id_unidade},
    )
    linhas = [dict(r) for r in cur.fetchall()]

    # 🔑 **A árvore é montada aqui, em memória, a partir de UMA consulta.**
    # Uma consulta por categoria transformaria um cardápio de dez seções em
    # dezenas de idas ao banco — e este é o caminho que o público percorre.
    categorias: list[dict] = []
    por_categoria: dict[int, dict] = {}
    por_subcategoria: dict[int, dict] = {}
    for l in linhas:
        cat = por_categoria.get(l["id_categoria"])
        if cat is None:
            cat = {"nome": l["categoria"], "descricao": l["categoria_descricao"],
                   "foto": l["categoria_foto"], "subcategorias": [], "itens": []}
            por_categoria[l["id_categoria"]] = cat
            categorias.append(cat)

        item = {
            "nome": l["produto"],
            "descricao": l["informacao_adicional"],
            "foto": l["produto_foto"],
            # ⚠️ `float` e não `Decimal`: o JSON não fala decimal, e deixar o
            # FastAPI resolver mandaria string para a tela.
            "preco": float(l["preco"]) if l["preco"] is not None else None,
        }
        if l["id_subcategoria"] is None:
            cat["itens"].append(item)
            continue
        sub = por_subcategoria.get(l["id_subcategoria"])
        if sub is None:
            sub = {"nome": l["subcategoria"],
                   "descricao": l["subcategoria_descricao"],
                   "foto": l["subcategoria_foto"], "itens": []}
            por_subcategoria[l["id_subcategoria"]] = sub
            cat["subcategorias"].append(sub)
        sub["itens"].append(item)

    return {"nome": nome, "categorias": categorias}


@router.get("/{id_unidade}/horarios")
def horarios(
    id_unidade: int,
    dia: date,
    pessoas: int = Query(ge=1, le=50),
) -> dict:
    """Os horários que aceitam um grupo neste dia.

    🔑 **É a MESMA regra que a agenda do balcão usa** (`reservas_agenda`), e isso
    é o ponto: uma segunda regra para o público divergiria da primeira, e a
    divergência apareceria como mesa prometida ao cliente e não disponível na
    casa.

    ⚠️ **O cliente não escolhe mesa** — ele vê "19:00 disponível" e a casa decide
    onde sentar. É o que o esboço já dizia, e é o que evita que a escolha do
    cliente trave a operação.

    ⚠️ **Esta rota LÊ e não grava.** Gravar a reserva pela internet é outra
    conversa — precisa identificar a pessoa e conter abuso — e é a próxima fatia.
    """
    with get_cursor() as cur:
        _casa_aberta(cur, id_unidade)
        r = agenda.disponibilidade(cur, id_unidade, dia, pessoas)
        livres = [h["hora"] for h in (r.get("horarios") or []) if h["livre"]]
        motivo = r.get("motivo")

        # 🔑 **Só o que ainda dá tempo de marcar** (pedido do dono, 23/09/2026):
        # hoje, antes de abrir, o dia inteiro vale; às 10:00 com 2h de
        # antecedência, só das 12:00 em diante. É o MESMO limite que
        # `agenda.criar` confere ao gravar — oferecer o que a gravação recusa
        # era o "toco no horário e nada acontece".
        cur.execute(
            "SELECT antecedencia_min_horas FROM reserva_config WHERE id_unidade = %s",
            (id_unidade,),
        )
        cfg = cur.fetchone()
        horas = int(cfg["antecedencia_min_horas"]) if cfg else 0
        agora = agora_da_casa().replace(tzinfo=None)
        limite = agenda.limite_do_site(agora, horas)
        cedo = [h for h in livres
                if datetime.combine(dia, time.fromisoformat(h)) < limite]
        if cedo:
            livres = [h for h in livres if h not in cedo]
            if not livres:
                # ⚠️ **A frase diz POR QUE a lista ficou vazia.** "Nenhum horário
                # livre" num dia de casa vazia faria o cliente achar que lotou.
                motivo = ("Esse dia já passou." if dia < agora.date() else
                          ("Os horários de hoje já passaram" if dia == agora.date()
                           else "Ainda não dá para marcar esse dia pelo site")
                          + (f" (reserva pelo site com {horas}h de antecedência)"
                             if horas else "")
                          + ". Escolha outro dia ou fale com a casa.")

        # ⚠️ **Só o que o cliente precisa, e nada de operação.** A resposta de
        # dentro traz `mesas_livres` por horário — quantas mesas a casa ainda
        # tem —, e isso é informação de negócio: o público não precisa saber se
        # o salão está cheio ou vazio para escolher as 19h.
        return {
            "dia": dia.isoformat(),
            "pessoas": pessoas,
            "abre": r.get("abre"),
            "fecha": r.get("fecha"),
            # 🔑 Só os LIVRES, já em texto. Mandar os ocupados junto faria a tela
            # ter de filtrar — e uma tela que filtra é uma tela que pode errar o
            # filtro e oferecer o que não há.
            "horarios": livres,
            # ⚠️ **O teto do site é do CADASTRO**, e o maior grupo é do SALÃO:
            # teto maior que a maior junta é uma promessa que a casa não cumpre,
            # e o site precisa dos dois para não oferecer mesa para 12 quando a
            # maior junta senta 8.
            "teto": min(int(r.get("teto_online") or 0) or 99,
                        int(r.get("maior_grupo") or 0) or 99),
            "motivo": motivo,
        }


# ---------------------------------------------------------------------------
# A reserva pelo site — o único lugar em que a INTERNET grava neste sistema.
# ---------------------------------------------------------------------------
#
# 🔑 **Pedido do dono (21/09/2026):** *"para a realização de reserva, precisamos
# de um cadastro simples do usuário. Clica em Reserve sua Mesa, abre uma tela com
# o número do telefone; caso não tenha cadastrada, realiza o cadastro com Nome,
# telefone, gênero e cidade."*
#
# ⚠️ **Gravar muda o problema.** Tudo acima nesta arquivo só mostra o que a casa
# já publicou; aqui nasce registro, e a pergunta deixa de ser "o que pode sair" e
# passa a ser também "quanto pode entrar". O limite mora em
# `services/reserva_clientes.py`, e é por telefone E por origem: são dois ataques
# diferentes.


def _de_onde_veio(pedido: Request) -> str | None:
    """O endereço de quem chamou, para CONTAR — nunca para guardar.

    ⚠️ **`X-Forwarded-For` é o que vale atrás do App Platform**: sem ele, todas as
    requisições chegam com o IP do balanceador e o limite por origem vira um
    limite global que barra a casa inteira quando um visitante exagera.
    ⚠️ E só o PRIMEIRO da lista — o resto é cadeia de proxy, que qualquer um pode
    inventar acrescentando um cabeçalho.
    """
    encaminhado = pedido.headers.get("x-forwarded-for")
    if encaminhado:
        return encaminhado.split(",")[0].strip() or None
    return pedido.client.host if pedido.client else None


def _reserva_online(cur, id_unidade: int) -> dict:
    """A configuração da reserva do site, se a casa a estiver aceitando.

    🔑 **`aceita_online` existia desde a migração 068 e não fazia nada** — o
    terreno estava preparado e a porta, fechada. É aqui que ela abre.
    ⚠️ **409 com a frase, não 404**: a casa existe e o site dela está no ar; o
    que não está ligado é marcar sozinho. O site cai no WhatsApp, que continua
    funcionando.
    """
    cur.execute(
        """SELECT aceita_online, confirmacao, cadastro_completo, teto_online,
                  antecedencia_min_horas, antecedencia_max_dias
             FROM reserva_config WHERE id_unidade = %s""",
        (id_unidade,),
    )
    cfg = cur.fetchone()
    if not cfg or not cfg["aceita_online"]:
        raise HTTPException(
            status_code=409,
            detail="Esta casa ainda não marca reserva pelo site. Fale com a gente.",
        )
    return dict(cfg)


@router.get("/{id_unidade}/reserva")
def reserva_ligada(id_unidade: int) -> dict:
    """O site pergunta ANTES de mostrar o botão: dá para marcar por aqui?

    🔑 **Sem isto a tela mentiria por um clique inteiro.** O cliente escolheria
    dia, pessoas e horário para só então descobrir que a casa não aceita reserva
    online — e a saída dele seria fechar o site, não pegar o WhatsApp.
    ⚠️ **Não é 409 aqui.** Esta rota RESPONDE a pergunta; recusar seria obrigar o
    site a tratar um erro para saber de um estado normal.
    """
    with get_cursor() as cur:
        _casa_aberta(cur, id_unidade)
        cur.execute(
            """SELECT aceita_online, cadastro_completo, confirmacao, teto_online
                 FROM reserva_config WHERE id_unidade = %s""",
            (id_unidade,),
        )
        cfg = cur.fetchone()
        if not cfg:
            return {"aceita": False}
        return {
            "aceita": bool(cfg["aceita_online"]),
            # 🔑 O site pergunta gênero e cidade só se a casa quiser.
            "cadastro_completo": bool(cfg["cadastro_completo"]),
            # ⚠️ O cliente precisa saber ANTES se a reserva ainda vai ser
            # confirmada por alguém — senão ele sai achando que tem mesa.
            "confirma_na_hora": cfg["confirmacao"] == "AUTOMATICA",
            "teto": int(cfg["teto_online"]),
        }


@router.post("/{id_unidade}/reserva/telefone")
def procurar_cadastro(id_unidade: int, corpo: TelefoneDoSite, pedido: Request) -> dict:
    """Já existe cadastro neste telefone? Sem dizer de quem é.

    🔑 **Decisão do dono (21/09/2026)**: a tela CONFIRMA o nome, não o revela.
    ⚠️ **Sem isso o site seria uma consulta aberta de telefone→nome** — não há
    login nenhum na frente, e bastaria digitar números em sequência para colher o
    dono de cada um. A dica (`M••• S•••`) chega para a pessoa reconhecer o
    próprio cadastro e não chega para descobrir o alheio.
    ⚠️ **Conta como tentativa.** Esta rota não grava nada, mas é por ela que uma
    varredura passaria — limitar só a que grava deixaria a porta de leitura
    aberta justamente para o uso que se quer conter.
    """
    with get_cursor() as cur:
        _casa_aberta(cur, id_unidade)
        _reserva_online(cur, id_unidade)
        clientes.marcar_tentativa(cur, id_unidade, _de_onde_veio(pedido))
        telefone = clientes.telefone_valido(corpo.telefone)
        return clientes.procurar(cur, id_unidade, telefone)


@router.post("/{id_unidade}/reserva", status_code=201)
def marcar_reserva(id_unidade: int, corpo: ReservaDoSite, pedido: Request) -> dict:
    """Cadastra quem é (se for novo) e marca a mesa — na MESMA transação.

    🔑 **A regra que decide a mesa é a MESMA do balcão** (`reservas_agenda.criar`,
    com `pg_advisory_xact_lock` por loja e dia). Uma segunda regra para o público
    divergiria, e a divergência apareceria como mesa prometida ao cliente e
    indisponível na casa.
    ⚠️ **Nada de `id_pessoa` aqui**: aquela coluna aponta para `fornecedores`, que
    é o cadastro do balcão. Quem vem do site mora em `reserva_clientes` e entra
    por `id_cliente`.
    """
    with get_cursor() as cur:
        _casa_aberta(cur, id_unidade)
        cfg = _reserva_online(cur, id_unidade)
        clientes.marcar_tentativa(cur, id_unidade, _de_onde_veio(pedido))

        cliente = clientes.resolver(cur, id_unidade, corpo, bool(cfg["cadastro_completo"]))

        # 🔑 **O status sai da configuração da casa**, como `status_inicial` já
        # decidia: AUTOMATICA nasce confirmada, MANUAL nasce pendente esperando
        # alguém olhar. É a diferença entre a casa prometer a mesa e a casa
        # prometer uma resposta.
        pedido_de_reserva = ReservaCreate(
            data=corpo.data, hora=corpo.hora, pessoas=corpo.pessoas,
            nome=cliente["nome"], telefone=cliente["telefone"],
            origem="SITE", observacao_cliente=corpo.observacao_cliente,
            confirmacao_da_loja=cfg["confirmacao"],
        )
        feita = agenda.criar(cur, id_unidade, pedido_de_reserva, None)
        cur.execute("UPDATE reservas SET id_cliente = %s WHERE id = %s",
                    (cliente["id"], feita["id"]))

        return {
            "status": feita["status"],
            # ⚠️ **A tela não pode dizer "reservado" quando a casa ainda vai
            # olhar.** É a mesma regra que impediu o site de prometer o que não
            # fazia; agora ele faz, e continua não podendo prometer demais.
            "confirmada": feita["status"] == "CONFIRMADA",
            # ⚠️ Só o primeiro nome, como nas outras portas do site: desde 24/09
            # basta o telefone, e o nome inteiro aqui vazaria quem é o dono dele.
            "nome": clientes._primeiro_nome_exibido(cliente["nome"]),
            "cadastro_novo": cliente["novo"],
            "data": corpo.data.isoformat(),
            "hora": corpo.hora.strftime("%H:%M"),
            "pessoas": corpo.pessoas,
        }


# 🔑 **"As reservas desta pessoa", escrito UMA vez**: a lista e o cancelamento
# precisam concordar sobre o que é dela — se divergissem, o site mostraria uma
# reserva que o botão de cancelar não acha.
_DO_CLIENTE = """id_unidade = %s
                  AND (id_cliente = %s
                       OR regexp_replace(coalesce(telefone, ''), '[^0-9]', '', 'g') = %s)
                  AND status IN ('PENDENTE', 'CONFIRMADA')
                  AND data >= current_date"""


@router.post("/{id_unidade}/reserva/minhas")
def minhas_reservas(id_unidade: int, corpo: ClienteDoSite, pedido: Request) -> dict:
    """As reservas em aberto de quem se identificou — o "Suas reservas".

    🔑 **Pedido do dono (23/09/2026):** *"podemos ter uma área dentro de Reserve
    sua mesa para Suas Reservas."*
    ⚠️ **Desde 24/09/2026 basta o TELEFONE** (pedido do dono: *"não solicitar a
    confirmação do nome, somente com o telefone já confirmamos os dados"*). A
    consequência, aceita pelo dono: quem souber o telefone de alguém vê as
    reservas em aberto dele. O limite por origem é o que resta de contenção.
    ⚠️ **Telefone sem cadastro devolve lista vazia, não 404** — pelo mesmo
    motivo de `procurar`: o código de status não pode dizer quem existe.
    """
    with get_cursor() as cur:
        _casa_aberta(cur, id_unidade)
        _reserva_online(cur, id_unidade)
        clientes.marcar_tentativa(cur, id_unidade, _de_onde_veio(pedido))
        telefone = clientes.telefone_valido(corpo.telefone)
        cliente = clientes.conferir(cur, id_unidade, telefone, corpo.nome)
        if not cliente:
            return {"reservas": []}
        # 🔑 **As do balcão entram também**: quem ligou e deu o mesmo telefone
        # é a mesma pessoa, e "Suas reservas" sem a que ela marcou por telefone
        # a faria marcar de novo. O balcão grava o número com máscara; a
        # comparação é pelos dígitos.
        cur.execute(
            f"""SELECT data, hora, pessoas, status, observacao_cliente
                  FROM reservas
                 WHERE {_DO_CLIENTE}
                 ORDER BY data, hora""",
            (id_unidade, cliente["id"], telefone),
        )
        # ⚠️ **Nada de id nem de mesa**, como no resto deste arquivo.
        return {"reservas": [{
            "data": r["data"].isoformat(),
            "hora": r["hora"].strftime("%H:%M"),
            "pessoas": r["pessoas"],
            "confirmada": r["status"] == "CONFIRMADA",
            "observacao": r["observacao_cliente"],
        } for r in cur.fetchall()]}


@router.post("/{id_unidade}/reserva/cancelar")
def cancelar_reserva(id_unidade: int, corpo: CancelamentoDoSite, pedido: Request) -> dict:
    """O cliente cancela uma das próprias reservas, em "Suas reservas".

    🔑 **O mesmo caminho do balcão** (`agenda.mudar_status` → `CANCELADA`): a
    linha não se apaga, a mesa se solta, e a agenda mostra a reserva riscada.
    ⚠️ **Desde 24/09/2026 basta o TELEFONE**, como na lista (pedido do dono). A
    consequência, dita ao dono: quem souber o telefone de alguém pode cancelar a
    mesa dele. O limite por origem é o que resta de contenção.
    ⚠️ **Reserva cujo horário já passou não se cancela pelo site.** Nesse ponto
    a pessoa ou veio ou não veio — `NAO_COMPARECEU` é a casa quem marca.
    """
    with get_cursor() as cur:
        _casa_aberta(cur, id_unidade)
        _reserva_online(cur, id_unidade)
        clientes.marcar_tentativa(cur, id_unidade, _de_onde_veio(pedido))
        telefone = clientes.telefone_valido(corpo.telefone)
        cliente = clientes.conferir(cur, id_unidade, telefone, corpo.nome)
        # ⚠️ Sem cadastro, a mesma resposta de "não achei": o código de status
        # não pode dizer se o telefone existe.
        achada = None
        if cliente:
            cur.execute(
                f"""SELECT id FROM reservas
                     WHERE {_DO_CLIENTE} AND data = %s AND hora = %s
                     ORDER BY id LIMIT 1 FOR UPDATE""",
                (id_unidade, cliente["id"], telefone, corpo.data, corpo.hora),
            )
            achada = cur.fetchone()
        if not achada:
            raise HTTPException(status_code=404, detail="Reserva não encontrada.")
        if datetime.combine(corpo.data, corpo.hora) <= agora_da_casa().replace(tzinfo=None):
            raise HTTPException(
                status_code=409,
                detail="O horário desta reserva já passou. Fale com a casa.",
            )
        agenda.mudar_status(cur, id_unidade, achada["id"], "CANCELADA")
        # 🔑 A recepção precisa saber que foi o CLIENTE, e não alguém da casa,
        # quem cancelou — é a diferença entre um recado e um engano.
        cur.execute(
            """UPDATE reservas
                  SET observacao_interna = concat_ws(' · ', nullif(observacao_interna, ''),
                                                     'Cancelada pelo cliente no site')
                WHERE id = %s""",
            (achada["id"],),
        )
        return {"cancelada": True}


# ---------------------------------------------------------------------------
# Quem é a pessoa, sem reserva junto — a porta do catálogo que exige cadastro
# ---------------------------------------------------------------------------
#
# 🔑 **Pedido do dono (24/09/2026):** *"adicionar a validação do cliente ao
# acessar o catálogo, colocar no cadastro do catálogo se exige cadastro."*
# ⚠️ **Não passam por `_reserva_online`**: a casa pode publicar cardápio que exige
# cadastro sem marcar mesa pelo site. As batidas contam no mesmo limite por
# origem das rotas de reserva — é a mesma porta de consulta de telefone.


def _cadastro_completo(cur, id_unidade: int) -> bool:
    cur.execute("SELECT cadastro_completo FROM reserva_config WHERE id_unidade = %s",
                (id_unidade,))
    cfg = cur.fetchone()
    return bool(cfg and cfg["cadastro_completo"])


@router.post("/{id_unidade}/cliente/telefone")
def cliente_por_telefone(id_unidade: int, corpo: TelefoneDoSite, pedido: Request) -> dict:
    """Já existe cadastro neste telefone? Confirma, não revela — como na reserva.

    Devolve também se a casa pede cadastro completo, para o site saber o que
    perguntar a quem é novo sem depender da configuração de reserva online.
    """
    with get_cursor() as cur:
        _casa_aberta(cur, id_unidade)
        clientes.marcar_tentativa(cur, id_unidade, _de_onde_veio(pedido))
        telefone = clientes.telefone_valido(corpo.telefone)
        return {**clientes.procurar(cur, id_unidade, telefone),
                "cadastro_completo": _cadastro_completo(cur, id_unidade)}


@router.post("/{id_unidade}/cliente")
def identificar_cliente(id_unidade: int, corpo: IdentificacaoDoSite,
                        pedido: Request) -> dict:
    """Confere quem já tem cadastro, ou cadastra quem é novo.

    ⚠️ **A mesma regra da reserva** (`clientes.identificar`): primeiro nome que
    não confere é 409, e o que o cadastro novo exige sai da configuração da loja.
    """
    with get_cursor() as cur:
        _casa_aberta(cur, id_unidade)
        clientes.marcar_tentativa(cur, id_unidade, _de_onde_veio(pedido))
        cliente = clientes.identificar(cur, id_unidade, corpo,
                                       _cadastro_completo(cur, id_unidade))
        # ⚠️ Só o PRIMEIRO nome: desde 24/09 basta o telefone para chegar aqui, e o
        # nome inteiro completaria a consulta telefone→pessoa.
        return {"nome": clientes._primeiro_nome_exibido(cliente["nome"]),
                "cadastro_novo": cliente["novo"]}


@router.post("/{id_unidade}/catalogos/{id_catalogo}/abrir")
def abrir_catalogo(id_unidade: int, id_catalogo: int, corpo: ClienteDoSite,
                   pedido: Request) -> dict:
    """O conteúdo de um catálogo, para quem se identificou.

    🔑 **É por aqui que o catálogo que exige cadastro se abre**: o PDF devolve o
    endereço do arquivo; o montado por produtos, o cardápio inteiro.
    ⚠️ **Telefone sem cadastro é 403 dizendo o que fazer**, não 404: o catálogo
    existe e está no ar — o que falta é a pessoa se cadastrar.
    """
    with get_cursor() as cur:
        _casa_aberta(cur, id_unidade)
        clientes.marcar_tentativa(cur, id_unidade, _de_onde_veio(pedido))
        telefone = clientes.telefone_valido(corpo.telefone)
        capa = _no_ar(cur, id_unidade, id_catalogo)
        if not capa:
            raise HTTPException(status_code=404, detail="Cardápio não encontrado.")
        if not clientes.conferir(cur, id_unidade, telefone, corpo.nome):
            raise HTTPException(status_code=403,
                                detail="Faça seu cadastro para abrir este cardápio.")
        if capa["origem"] == ORIGEM_PRODUTOS:
            return {"origem": ORIGEM_PRODUTOS,
                    "cardapio": _montar_cardapio(cur, id_unidade, id_catalogo,
                                                 capa["nome"])}
        if not capa["arquivo_url"]:
            raise HTTPException(status_code=404, detail="Cardápio não encontrado.")
        return {"origem": capa["origem"], "arquivo_url": capa["arquivo_url"]}
