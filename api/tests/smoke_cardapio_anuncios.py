"""Anúncios no Cardápio Vivo (migração 121, fase 1) e as aberturas de seção configuráveis.

🔑 Pedido do dono (16/10/2026): anúncios da casa ou de outra marca no meio do cardápio, com
período, dias, links, regras de exibição ajustáveis (5º prato, 8 de distância, máximo 2 — 1 na
mesa) e métricas que viram RELATÓRIO para apresentar ao parceiro.

    python tests/smoke_cardapio_anuncios.py        (API de pé na 9200)
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from base64 import b64decode
from datetime import timedelta

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import preservar_cardapio_vivo, preservar_reserva  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402
from relogio import agora_da_casa  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
MARCA = str(time.time_ns() // 100)[-6:]
FOTO = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+wSzIAAAABlBMVEX///+/v7+jQ3Y5AAAA"
                 "DklEQVQI12P4AIX8EAgALgAD/aNpbtEAAAAASUVORK5CYII=")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None, bruto=None, tipo="application/json"):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", tipo)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = bruto if bruto is not None else (
        json.dumps(corpo, default=str).encode() if corpo is not None else None)
    try:
        with urllib.request.urlopen(req, dados, timeout=120) as r:
            conteudo = r.read()
            if r.headers.get("Content-Type", "").startswith("application/json"):
                return r.status, json.loads(conteudo or b"null")
            return r.status, conteudo
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": b.decode(errors="replace")}


def enviar(caminho, token, conteudo, nome, tipo):
    limite = uuid.uuid4().hex
    corpo = (f"--{limite}\r\nContent-Disposition: form-data; name=\"arquivo\"; "
             f"filename=\"{nome}\"\r\nContent-Type: {tipo}\r\n\r\n").encode() + conteudo \
        + f"\r\n--{limite}--\r\n".encode()
    return chamar("POST", caminho, token=token, bruto=corpo, tipo=f"multipart/form-data; boundary={limite}")


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()
U = 1
preservar_reserva(U)
preservar_cardapio_vivo(U)
with get_cursor() as cur:
    cur.execute("SELECT anuncio_depois_de, anuncio_intervalo, anuncio_maximo, anuncio_maximo_mesa "
                "FROM cardapio_config WHERE id_unidade = %s", (U,))
    _REGRAS_ANTES = dict(cur.fetchone() or {})


def _limpar():
    with get_cursor() as cur:
        cur.execute("DELETE FROM cardapio_anuncios WHERE nome LIKE %s", (f"%{MARCA}%",))
        cur.execute("DELETE FROM catalogos WHERE nome LIKE %s", (f"%{MARCA}%",))
        cur.execute("DELETE FROM produtos WHERE nome LIKE %s", (f"%{MARCA}%",))
        cur.execute("DELETE FROM saloes WHERE nome LIKE %s", (f"%{MARCA}%",))
        if _REGRAS_ANTES:
            cur.execute("""UPDATE cardapio_config SET anuncio_depois_de = %(anuncio_depois_de)s,
                             anuncio_intervalo = %(anuncio_intervalo)s, anuncio_maximo = %(anuncio_maximo)s,
                             anuncio_maximo_mesa = %(anuncio_maximo_mesa)s WHERE id_unidade = 1""", _REGRAS_ANTES)


atexit.register(_limpar)
_st, par = chamar("GET", f"/unidades/{U}/parametros", token=token)
chamar("PUT", f"/unidades/{U}/parametros", {**par, "reservas_ligado": True}, token)


def produto(nome, preco):
    _st, p = chamar("POST", "/produtos", {"nome": f"{nome} {MARCA}", "tipo": "INSUMO",
                                          "um_estoque": "UN", "controla_estoque": False}, token)
    _st, atual = chamar("GET", f"/produtos/{p['id']}", token=token)
    chamar("PUT", f"/produtos/{p['id']}", {**atual, "integrado_pdv": True, "preco_venda": preco}, token)
    return p["id"]


print("0. cenário: o cardápio da mesa e o catálogo do Dia dos Namorados")
_st, cat = chamar("POST", "/catalogos", {"nome": f"Cardapio {MARCA}", "origem": "PRODUTOS", "situacao": "ATIVO"}, token)
_st, nam = chamar("POST", "/catalogos", {"nome": f"Namorados {MARCA}", "origem": "PRODUTOS", "situacao": "ATIVO"}, token)
ID, NAM = cat["id"], nam["id"]
_st, g = chamar("POST", f"/catalogos/{ID}/categorias", {"nome": "Massas"}, token)
_st, gn = chamar("POST", f"/catalogos/{NAM}/categorias", {"nome": "Para dois"}, token)
_st, it = chamar("POST", f"/catalogos/categorias/{g['id']}/itens", {"id_produto": produto("ANUNCIO MASSA", 40)}, token)
chamar("POST", f"/catalogos/categorias/{gn['id']}/itens", {"id_produto": produto("ANUNCIO FONDUE", 120)}, token)
chamar("PUT", f"/cardapio-vivo/vivos/{ID}", {"slug": f"anuncio-{MARCA}", "principal": True}, token)
chamar("PUT", f"/cardapio-vivo/vivos/{NAM}", {"slug": f"namorados-{MARCA}"}, token)
with get_cursor() as cur:
    cur.execute("INSERT INTO saloes (id_unidade, nome) VALUES (%s, %s) RETURNING id", (U, f"Anuncio {MARCA}"))
    salao = cur.fetchone()["id"]
    cur.execute("""INSERT INTO mesas (id_unidade, id_salao, nome, lugares, capacidade_max)
                   VALUES (%s, %s, 'A1', 2, 2) RETURNING token""", (U, salao))
    TOKEN_MESA = cur.fetchone()["token"]
LINK = f"/publico/cardapio/loja/{U}?cardapio=anuncio-{MARCA}"
LINK_NAM = f"/publico/cardapio/loja/{U}?cardapio=namorados-{MARCA}"

print("\n1. as regras da casa")
st, r = chamar("PUT", "/cardapio-vivo/anuncios/regras",
               {"anuncio_depois_de": 5, "anuncio_intervalo": 8, "anuncio_maximo": 2, "anuncio_maximo_mesa": 1}, token)
checar("as regras gravam (5º prato, 8 de distância, máximo 2 e 1 na mesa)", st == 200 and r["anuncio_intervalo"] == 8, (st, r))
st, cfg = chamar("GET", "/cardapio-vivo/config", token=token)
casa = {k: v for k, v in cfg["config"].items() if k not in ("id_unidade", "logo_url", "id_catalogo")}
chamar("PUT", "/cardapio-vivo/config", casa, token)
_st, lista = chamar("GET", "/cardapio-vivo/anuncios", token=token)
checar("gravar a aparência da casa NÃO volta as regras ao padrão", lista["regras"]["anuncio_maximo_mesa"] == 1, lista["regras"])
st, _r = chamar("PUT", "/cardapio-vivo/anuncios/regras",
                {"anuncio_depois_de": 0, "anuncio_intervalo": 8, "anuncio_maximo": 2, "anuncio_maximo_mesa": 1}, token)
checar("o 1º anúncio antes do 1º prato é recusado (422)", st == 422, st)

print("\n2. criar anúncios")
st, casa_ad = chamar("POST", "/cardapio-vivo/anuncios", {
    "nome": f"Namorados {MARCA}", "origem": "CASA", "titulo": "Dia dos Namorados", "texto": "Fondue para dois.",
    "acao": "CATALOGO", "acao_catalogo": NAM, "acao_rotulo": "Ver o cardápio"}, token)
checar("o anúncio da casa (abre o catálogo do Dia dos Namorados) grava", st == 201 and casa_ad["acao_catalogo"] == NAM, (st, casa_ad))
st, r = chamar("POST", "/cardapio-vivo/anuncios", {"nome": f"Sem marca {MARCA}", "origem": "EXTERNO", "titulo": "x"}, token)
checar("anúncio de outra marca SEM o anunciante é recusado (422)", st == 422 and "anunciante" in r.get("detail", ""), (st, r))
st, externo = chamar("POST", "/cardapio-vivo/anuncios", {
    "nome": f"Cerveja {MARCA}", "origem": "EXTERNO", "anunciante": "Cervejaria X", "titulo": "Cerveja gelada",
    "acao": "LINK", "acao_url": "https://exemplo.com.br/cerveja", "acao_rotulo": "Conhecer", "peso": 2}, token)
checar("o anúncio de outra marca, com link, grava", st == 201, (st, externo))
st, r = chamar("POST", "/cardapio-vivo/anuncios", {"nome": f"Link ruim {MARCA}", "titulo": "x", "acao": "LINK",
                                                   "acao_url": "exemplo.com"}, token)
checar("link sem https:// é recusado (422)", st == 422, (st, r))
st, r = chamar("POST", "/cardapio-vivo/anuncios", {"nome": f"Dia ruim {MARCA}", "titulo": "x", "dias": [8]}, token)
checar("dia da semana fora de 1–7 é recusado (422)", st == 422, st)
hoje = agora_da_casa().date()
st, futuro = chamar("POST", "/cardapio-vivo/anuncios", {"nome": f"Futuro {MARCA}", "titulo": "Em breve",
                                                         "inicio": str(hoje + timedelta(days=3))}, token)
outro_dia = (hoje.isoweekday() % 7) + 1
st, outrodia = chamar("POST", "/cardapio-vivo/anuncios", {"nome": f"Outro dia {MARCA}", "titulo": "Só amanhã",
                                                           "dias": [outro_dia]}, token)
st, so_mesa = chamar("POST", "/cardapio-vivo/anuncios", {"nome": f"Mesa {MARCA}", "titulo": "Só na mesa",
                                                          "canal": "MESA"}, token)
st, prato_ad = chamar("POST", "/cardapio-vivo/anuncios", {"nome": f"Prato {MARCA}", "titulo": "Prove a massa",
                                                           "acao": "PRATO", "acao_item": it["id"]}, token)

print("\n3. o feed recebe só o que vale agora")
_st, f = chamar("GET", LINK)
ids = {a["id"] for a in f.get("anuncios", [])}
checar("o anúncio da casa e o de outra marca aparecem", {casa_ad["id"], externo["id"]} <= ids, ids)
checar("o do futuro, o de outro dia e o só-da-mesa NÃO aparecem pelo link",
       not ids & {futuro["id"], outrodia["id"], so_mesa["id"]}, ids)
a = next(x for x in f["anuncios"] if x["id"] == casa_ad["id"])
checar("o da casa leva o catálogo e o nome no link dele", a["acao"]["tipo"] == "CATALOGO"
       and a["acao"]["slug"] == f"namorados-{MARCA}" and a["origem"] == "CASA", a)
e = next(x for x in f["anuncios"] if x["id"] == externo["id"])
checar("o externo leva o anunciante e o link", e["anunciante"] == "Cervejaria X" and e["acao"]["url"].startswith("https://"), e)
checar("pelo link, o teto é 2", f["regras_anuncio"] == {"depois_de": 5, "intervalo": 8, "maximo": 2}, f.get("regras_anuncio"))
_st, fm = chamar("GET", f"/publico/cardapio/mesa/{TOKEN_MESA}")
idsm = {x["id"] for x in fm.get("anuncios", [])}
checar("na mesa, o só-da-mesa aparece e o teto é 1", so_mesa["id"] in idsm and fm["regras_anuncio"]["maximo"] == 1, (idsm, fm.get("regras_anuncio")))
_st, fn = chamar("GET", LINK_NAM)
checar("o anúncio do Dia dos Namorados NÃO aparece no próprio cardápio do Dia dos Namorados",
       casa_ad["id"] not in {x["id"] for x in fn.get("anuncios", [])}, "")
_st, site = chamar("GET", f"/publico/{U}/catalogos")
checar("o site não recebe anúncio (só no feed)", "anuncios" not in json.dumps(site), "")
# 🔑 (1.1.109) A prévia do cadastro: sem anúncio, a não ser que se peça — e então como na mesa
# (o principal é o cardápio da mesa), com o teto da mesa.
_st, pv = chamar("GET", f"/cardapio-vivo/previa?id_catalogo={ID}", token=token)
checar("a prévia, por padrão, segue sem anúncio", pv.get("anuncios") == [], pv.get("anuncios"))
st, pv = chamar("GET", f"/cardapio-vivo/previa?id_catalogo={ID}&anuncios=true", token=token)
idsp = {x["id"] for x in pv.get("anuncios", [])}
checar("pedida com anúncios, mostra os que valem agora (o só-da-mesa, porque é o principal)",
       st == 200 and {casa_ad["id"], externo["id"], so_mesa["id"]} <= idsp and futuro["id"] not in idsp
       and pv["regras_anuncio"]["maximo"] == 1, (st, idsp, pv.get("regras_anuncio")))

print("\n4. a mídia")
st, r = enviar(f"/cardapio-vivo/anuncios/{externo['id']}/foto", token, FOTO, "cerveja.png", "image/png")
checar("a foto do anúncio grava", st == 200 and (r.get("foto_url") or "").startswith("/arquivos/"), (st, r))
_st, f = chamar("GET", LINK)
checar("e o feed mostra a FOTO", next(x for x in f["anuncios"] if x["id"] == externo["id"])["midia"]["tipo"] == "FOTO", "")

print("\n5. a medição e o relatório")
S1, S2 = str(uuid.uuid4()), str(uuid.uuid4())
for s, eventos in ((S1, [{"tipo": "viu_anuncio", "anuncio": externo["id"], "duracao_ms": 4200},
                         {"tipo": "clicou_anuncio", "anuncio": externo["id"]}]),
                   (S2, [{"tipo": "viu_anuncio", "anuncio": externo["id"], "duracao_ms": 600},
                         {"tipo": "viu_anuncio", "anuncio": 999999, "duracao_ms": 900}])):
    st, _r = chamar("POST", "/publico/cardapio/eventos", {"sessao": s, "loja": U, "modo": "VITRINE",
                                                           "catalogo": ID, "eventos": eventos})
checar("os eventos do anúncio são aceitos", st == 204, st)
with get_cursor() as cur:
    cur.execute("SELECT id_anuncio FROM cardapio_eventos WHERE id_sessao = %s ORDER BY id", (S2,))
    ev = [x["id_anuncio"] for x in cur.fetchall()]
checar("anúncio que não é desta loja vira nulo", ev == [externo["id"], None], ev)
_st, lista = chamar("GET", "/cardapio-vivo/anuncios", token=token)
m = next(x for x in lista["anuncios"] if x["id"] == externo["id"])
checar("a lista mostra aparições, pessoas, pulados e toques",
       m["aparicoes"] == 2 and m["sessoes"] == 2 and m["pulados"] == 1 and m["toques"] == 1, m)
checar("e a situação de cada um (no ar / agendado)", m["situacao"] == "NO_AR"
       and next(x for x in lista["anuncios"] if x["id"] == futuro["id"])["situacao"] == "AGENDADO", "")
st, rel = chamar("GET", f"/cardapio-vivo/anuncios/{externo['id']}/relatorio", token=token)
checar("o relatório traz o total, a taxa de toque e a de pulados",
       st == 200 and rel["total"]["sessoes"] == 2 and rel["total"]["taxa_toque"] == 0.5
       and rel["total"]["taxa_pulou"] == 0.5, (st, rel.get("total")))
checar("e o dia, o canal e a hora", len(rel["por_dia"]) >= 1 and rel["por_canal"][0]["canal"] == "LINK"
       and len(rel["por_hora"]) >= 1, rel.get("por_canal"))
st, _r = chamar("GET", f"/cardapio-vivo/anuncios/{externo['id']}/relatorio?de={hoje}&ate={hoje - timedelta(days=1)}", token=token)
checar("período ao contrário é recusado (422)", st == 422, st)

print("\n5b. de qual Cardápio Vivo veio o evento (122)")
with get_cursor() as cur:
    cur.execute("SELECT DISTINCT id_catalogo FROM cardapio_eventos WHERE id_sessao IN (%s, %s)", (S1, S2))
    gravados = {x["id_catalogo"] for x in cur.fetchall()}
checar("cada evento grava o cardápio do lote", gravados == {ID}, gravados)
S3 = str(uuid.uuid4())
chamar("POST", "/publico/cardapio/eventos", {"sessao": S3, "loja": U, "modo": "VITRINE", "catalogo": NAM,
                                             "eventos": [{"tipo": "viu_anuncio", "anuncio": externo["id"], "duracao_ms": 3000}]})
_st, rel = chamar("GET", f"/cardapio-vivo/anuncios/{externo['id']}/relatorio", token=token)
pc = {x["id_catalogo"]: x for x in rel.get("por_cardapio", [])}
checar("o relatório separa o anúncio por cardápio (a cafeteria e o do Dia dos Namorados)",
       pc.get(ID, {}).get("sessoes") == 2 and pc.get(NAM, {}).get("sessoes") == 1
       and pc[NAM]["cardapio"] == f"Namorados {MARCA}", rel.get("por_cardapio"))

print("\n5d. o resumo do dia guarda o anúncio, e o relatório o lê depois da retenção (124)")
from services import cardapio_vivo as cvs  # noqa: E402
with get_cursor() as cur:
    cvs.agregar_dia(cur, hoje, U)
    cur.execute("""SELECT id_catalogo, canal, vistas, sessoes, pulados, cliques, sessoes_clicaram
                     FROM cardapio_conteudo_dia
                    WHERE dia = %s AND id_unidade = %s AND tipo = 'ANUNCIO' AND id_ref = %s""",
                (hoje, U, externo["id"]))
    resumo = {x["id_catalogo"]: dict(x) for x in cur.fetchall()}
checar("o agendador resume o anúncio por cardápio e canal: 2 vistas, 2 pessoas, 1 pulou, 1 toque",
       resumo.get(ID) == {"id_catalogo": ID, "canal": "LINK", "vistas": 2, "sessoes": 2, "pulados": 1,
                          "cliques": 1, "sessoes_clicaram": 1} and resumo.get(NAM, {}).get("vistas") == 1, resumo)
with get_cursor() as cur:
    cur.execute("SELECT min(quando)::date AS d FROM cardapio_eventos WHERE id_unidade = %s", (U,))
    velho = cur.fetchone()["d"] - timedelta(days=10)  # um dia que o bruto já não tem
    cur.execute("""INSERT INTO cardapio_conteudo_dia (dia, id_unidade, tipo, id_ref, id_catalogo, canal,
                                                      vistas, sessoes, soma_ms, pulados, cliques, sessoes_clicaram)
                   VALUES (%s, %s, 'ANUNCIO', %s, %s, 'MESA', 4, 3, 20000, 0, 2, 2)""",
                (velho, U, externo["id"], ID))
_st, r_novo = chamar("GET", f"/cardapio-vivo/anuncios/{externo['id']}/relatorio?de={hoje}&ate={hoje}", token=token)
st, r_velho = chamar("GET", f"/cardapio-vivo/anuncios/{externo['id']}/relatorio?de={velho}&ate={hoje}", token=token)
checar("o período que vai antes do bruto soma o resumo: +4 aparições, +2 toques, um dia a mais",
       st == 200 and r_velho["total"]["aparicoes"] == r_novo["total"]["aparicoes"] + 4
       and r_velho["total"]["toques"] == r_novo["total"]["toques"] + 2
       and r_velho["por_dia"][0]["dia"] == str(velho), (st, r_velho.get("total"), r_velho.get("por_dia", [])[:1]))
checar("e diz até quando veio do resumo, e o porquê das pessoas",
       r_velho.get("resumido") and r_velho["resumido"]["dias"] == 1 and "por dia" in r_velho["resumido"]["aviso"]
       and r_novo.get("resumido") is None, r_velho.get("resumido"))
checar("o canal da mesa do resumo aparece junto do link do bruto",
       {x["canal"] for x in r_velho["por_canal"]} == {"MESA", "LINK"}, r_velho.get("por_canal"))
with get_cursor() as cur:
    cur.execute("DELETE FROM cardapio_conteudo_dia WHERE dia = %s AND id_ref = %s", (velho, externo["id"]))

print("\n5c. o anúncio que não aparece diz por quê (17/10/2026)")
st, vazio_ad = chamar("POST", "/cardapio-vivo/anuncios", {"nome": f"Vazio {MARCA}"}, token)
st, mesa_nam = chamar("POST", "/cardapio-vivo/anuncios", {"nome": f"Mesa errada {MARCA}", "titulo": "x",
                                                          "canal": "MESA", "cardapios": [NAM]}, token)
st, sem_prato = chamar("POST", "/cardapio-vivo/anuncios", {"nome": f"Sem prato {MARCA}", "titulo": "x",
                                                           "acao": "PRATO", "acao_item": it["id"]}, token)
with get_cursor() as cur:
    # O que o `ON DELETE SET NULL` faz quando o prato sai do cardápio.
    cur.execute("UPDATE cardapio_anuncios SET acao_item = NULL WHERE id = %s", (sem_prato["id"],))
    cur.execute("UPDATE catalogos SET situacao = 'INATIVO' WHERE id = %s", (NAM,))
_st, lista = chamar("GET", "/cardapio-vivo/anuncios", token=token)
por = {x["id"]: x for x in lista["anuncios"]}
checar("o anúncio vazio fica COM PROBLEMA, dizendo que não aparece",
       por[vazio_ad["id"]]["situacao"] == "COM_PROBLEMA" and "Sem título" in por[vazio_ad["id"]]["avisos"][0],
       por[vazio_ad["id"]].get("avisos"))
checar("o do botão para um catálogo fora do ar avisa",
       por[casa_ad["id"]]["situacao"] == "COM_PROBLEMA"
       and any("fora do ar" in t for t in por[casa_ad["id"]]["avisos"]), por[casa_ad["id"]].get("avisos"))
checar("o do prato que saiu do cardápio avisa que aparece sem botão",
       any("saiu do cardápio" in t for t in por[sem_prato["id"]]["avisos"]), por[sem_prato["id"]].get("avisos"))
checar("o só-da-mesa num cardápio que não é o principal avisa",
       any("Só na mesa" in t for t in por[mesa_nam["id"]]["avisos"]), por[mesa_nam["id"]].get("avisos"))
checar("e o que está certo continua NO AR, sem aviso",
       por[externo["id"]]["situacao"] == "NO_AR" and por[externo["id"]]["avisos"] == [], por[externo["id"]])
checar("o de outro dia está no ar, mas FORA DO HORÁRIO AGORA",
       por[outrodia["id"]]["fora_do_horario_agora"] is True and por[externo["id"]]["fora_do_horario_agora"] is False, "")
with get_cursor() as cur:
    cur.execute("UPDATE catalogos SET situacao = 'ATIVO' WHERE id = %s", (NAM,))

print("\n6. as aberturas de seção configuráveis")
enviar(f"/catalogos/secoes/categoria/{g['id']}/foto", token, FOTO, "massas.png", "image/png")
_st, f = chamar("GET", LINK)
checar("por padrão: AUTOMATICA, e a seção com abertura ligada", f["aberturas"] == "AUTOMATICA"
       and f["categorias"][0]["abertura"] is True, (f.get("aberturas"), f["categorias"][0].get("abertura")))
st, r = chamar("PUT", f"/catalogos/categorias/{g['id']}", {"nome": "Massas", "abertura": False}, token)
_st, f = chamar("GET", LINK)
checar("a seção desliga a abertura dela", st == 200 and f["categorias"][0]["abertura"] is False, (st, r))
chamar("PUT", f"/catalogos/categorias/{g['id']}", {"nome": "Massas frescas"}, token)
_st, f = chamar("GET", LINK)
checar("e renomear a seção (sem mandar o campo) NÃO a religa", f["categorias"][0]["abertura"] is False, "")
st, r = chamar("PUT", f"/cardapio-vivo/vivos/{ID}", {"slug": f"anuncio-{MARCA}", "principal": True, "aberturas": "NUNCA"}, token)
_st, f = chamar("GET", LINK)
checar("o Cardápio Vivo pode não abrir seção nenhuma (NUNCA)", st == 200 and f["aberturas"] == "NUNCA", (st, f.get("aberturas")))
st, _r = chamar("PUT", f"/cardapio-vivo/vivos/{ID}", {"slug": f"anuncio-{MARCA}", "aberturas": "AS_VEZES"}, token)
checar("valor desconhecido é recusado (422)", st == 422, st)

print("\n7. apagar")
st, r = chamar("DELETE", f"/cardapio-vivo/anuncios/{prato_ad['id']}", token=token)
checar("apagar o anúncio", st == 200, (st, r))
st, _r = chamar("PUT", f"/cardapio-vivo/anuncios/{prato_ad['id']}", {"nome": "x x"}, token)
checar("e ele não existe mais (404)", st == 404, st)
st, _r = chamar("GET", "/cardapio-vivo/anuncios")
checar("sem login, a lista recusa (401)", st == 401, st)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
sys.exit(1 if falhas else 0)
