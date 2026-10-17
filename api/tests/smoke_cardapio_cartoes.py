"""Cartões de conteúdo do Cardápio Vivo (migração 120): abertura do cardápio, abertura de
seção e cartões entre os pratos — só no feed.

🔑 Pedido do dono (16/10/2026): *"colocar algo entre os pratos que vai além de pratos — um
cardápio de massas, e antes postar um vídeo, texto ou foto com uma introdução, bem como seções
entre os pratos"*. Abertura de seção automática, vídeo subido no sistema, só no feed.

    python tests/smoke_cardapio_cartoes.py        (API de pé na 9200)
"""

import atexit
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from base64 import b64decode
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import preservar_cardapio_vivo, preservar_reserva  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

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
    return chamar("POST", caminho, token=token, bruto=corpo,
                  tipo=f"multipart/form-data; boundary={limite}")


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


def _limpar():
    with get_cursor() as cur:
        cur.execute("DELETE FROM catalogos WHERE nome LIKE %s", (f"%{MARCA}%",))
        cur.execute("DELETE FROM produtos WHERE nome LIKE %s", (f"%{MARCA}%",))


atexit.register(_limpar)
_st, par = chamar("GET", f"/unidades/{U}/parametros", token=token)
chamar("PUT", f"/unidades/{U}/parametros", {**par, "reservas_ligado": True}, token)


def produto(nome, preco):
    _st, p = chamar("POST", "/produtos", {"nome": f"{nome} {MARCA}", "tipo": "INSUMO",
                                          "um_estoque": "UN", "controla_estoque": False}, token)
    _st, atual = chamar("GET", f"/produtos/{p['id']}", token=token)
    chamar("PUT", f"/produtos/{p['id']}", {**atual, "integrado_pdv": True, "preco_venda": preco}, token)
    return p["id"]


print("0. cenário: um cardápio de massas, duas seções, uma subdivisão")
_st, cat = chamar("POST", "/catalogos", {"nome": f"Massas {MARCA}", "origem": "PRODUTOS",
                                         "situacao": "ATIVO"}, token)
ID = cat["id"]
_st, outro = chamar("POST", "/catalogos", {"nome": f"Outro {MARCA}", "origem": "PRODUTOS",
                                           "situacao": "ATIVO"}, token)
_st, g1 = chamar("POST", f"/catalogos/{ID}/categorias", {"nome": "Frescas", "ordem": 1}, token)
_st, g2 = chamar("POST", f"/catalogos/{ID}/categorias", {"nome": "Molhos", "ordem": 2}, token)
_st, sub = chamar("POST", f"/catalogos/categorias/{g1['id']}/subcategorias", {"nome": "Recheadas"}, token)
_st, go = chamar("POST", f"/catalogos/{outro['id']}/categorias", {"nome": "Outra"}, token)
it = {}
for chave, nome, g, s in (("tal", "TALHARIM", g1, None), ("pap", "PAPPARDELLE", g1, None),
                          ("rav", "RAVIOLI", g1, sub), ("pom", "POMODORO", g2, None),
                          ("fora", "FORA", go, None)):
    _st, i = chamar("POST", f"/catalogos/categorias/{g['id']}/itens",
                    {"id_produto": produto(nome, 40), **({"id_subcategoria": s["id"]} if s else {})}, token)
    it[chave] = i["id"]
st, r = chamar("PUT", f"/cardapio-vivo/vivos/{ID}", {"slug": f"massas-{MARCA}", "principal": True}, token)
checar("o cardápio de massas liga como Cardápio Vivo", st == 200, (st, r))
LINK = f"/publico/cardapio/loja/{U}?cardapio=massas-{MARCA}"

print("\n1. criar cartões")
st, abertura = chamar("POST", f"/catalogos/{ID}/cartoes",
                      {"titulo": "Massas frescas, feitas aqui", "texto": "Farinha 00 e 48 h de descanso."}, token)
checar("a abertura do cardápio (sem seção) grava", st == 201 and abertura.get("id_categoria") is None, (st, abertura))
st, harmon = chamar("POST", f"/catalogos/{ID}/cartoes",
                    {"id_categoria": g1["id"], "antes_do_item": it["pap"], "titulo": "Vai bem com o Chianti",
                     "id_item_link": it["pap"]}, token)
checar("o cartão antes de um prato grava", st == 201 and harmon.get("antes_do_item") == it["pap"], (st, harmon))
st, fim = chamar("POST", f"/catalogos/{ID}/cartoes",
                 {"id_categoria": g1["id"], "id_subcategoria": sub["id"], "texto": "Recheios do dia."}, token)
checar("o cartão no fim de uma subdivisão grava", st == 201, (st, fim))
st, r = chamar("POST", f"/catalogos/{ID}/cartoes",
               {"id_categoria": g2["id"], "antes_do_item": it["pap"], "titulo": "x"}, token)
checar("antes de um prato de OUTRA lista é recusado (422)", st == 422, (st, r))
st, r = chamar("POST", f"/catalogos/{ID}/cartoes",
               {"id_categoria": go["id"], "titulo": "x"}, token)
checar("seção de outro cardápio é recusada (422)", st == 422, (st, r))
st, r = chamar("POST", f"/catalogos/{ID}/cartoes",
               {"id_categoria": g1["id"], "titulo": "x", "id_item_link": it["fora"]}, token)
checar("o botão para prato de outro cardápio é recusado (422)", st == 422, (st, r))
st, r = chamar("POST", f"/catalogos/{ID}/cartoes", {"antes_do_item": it["tal"], "titulo": "x"}, token)
checar("a abertura do cardápio não fica antes de um prato (422)", st == 422, (st, r))
st, r = chamar("POST", f"/catalogos/{outro['id']}/cartoes", {"titulo": "sem vivo"}, token)
OUTRO_CARTAO = r.get("id")
st, vazio = chamar("POST", f"/catalogos/{ID}/cartoes", {"id_categoria": g2["id"]}, token)
checar("o cartão vazio (o de só vídeo, antes do vídeo) grava", st == 201, (st, vazio))
st, desligado = chamar("POST", f"/catalogos/{ID}/cartoes",
                       {"id_categoria": g2["id"], "titulo": "Desligado", "ativo": False}, token)

print("\n2. o feed recebe os cartões")
_st, f = chamar("GET", LINK)
ids = [c["id"] for c in f.get("cartoes", [])]
checar("o feed traz a abertura, o cartão do prato e o do fim",
       {abertura["id"], harmon["id"], fim["id"]} <= set(ids), ids)
checar("e NÃO traz o cartão vazio nem o desligado", vazio["id"] not in ids and desligado["id"] not in ids, ids)
c = next(x for x in f["cartoes"] if x["id"] == harmon["id"])
checar("o cartão leva a posição e o botão", c["antes_do_item"] == it["pap"] and c["id_item_link"] == it["pap"]
       and c["midia"]["tipo"] == "NENHUMA", c)
_st, site = chamar("GET", f"/publico/{U}/catalogos")
checar("o site não recebe cartão nenhum (só no feed)", "cartoes" not in json.dumps(site), "")

print("\n3. a mídia: foto OU vídeo")
st, r = enviar(f"/catalogos/cartoes/{abertura['id']}/foto", token, FOTO, "massa.png", "image/png")
checar("a foto do cartão grava", st == 200 and (r.get("foto_url") or "").startswith("/arquivos/"), (st, r))
import imageio_ffmpeg  # noqa: E402
with tempfile.TemporaryDirectory() as pasta:
    bruto = Path(pasta) / "teste.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc=duration=2:size=720x1280:rate=30", "-pix_fmt", "yuv420p",
                    str(bruto)], check=True)
    VIDEO = bruto.read_bytes()
st, r = enviar(f"/catalogos/cartoes/{vazio['id']}/video", token, VIDEO, "abre.mp4", "video/mp4")
checar("o vídeo do cartão é convertido", st == 200 and (r.get("video_url") or "").endswith(".mp4")
       and r.get("video_capa_url"), (st, r))
st, r = enviar(f"/catalogos/cartoes/{vazio['id']}/foto", token, FOTO, "f.png", "image/png")
checar("a foto enviada depois TROCA o vídeo (uma mídia só)", st == 200 and r.get("video_url") is None
       and r.get("foto_url"), r)
enviar(f"/catalogos/cartoes/{vazio['id']}/video", token, VIDEO, "abre.mp4", "video/mp4")
_st, f = chamar("GET", LINK)
por = {x["id"]: x for x in f["cartoes"]}
checar("com vídeo, o cartão vazio passa a aparecer no feed, como VIDEO",
       por.get(vazio["id"], {}).get("midia", {}).get("tipo") == "VIDEO", por.get(vazio["id"]))
checar("e a abertura sai com a FOTO", por[abertura["id"]]["midia"]["tipo"] == "FOTO", por[abertura["id"]])
st, r = chamar("DELETE", f"/catalogos/cartoes/{abertura['id']}/midia", token=token)
checar("tirar a mídia volta o cartão a só texto", st == 200 and r.get("foto_url") is None, (st, r))

print("\n4. a abertura automática da seção")
enviar(f"/catalogos/secoes/categoria/{g1['id']}/foto", token, FOTO, "frescas.png", "image/png")
st, r = enviar(f"/catalogos/secoes/subcategoria/{sub['id']}/video", token, VIDEO, "rec.mp4", "video/mp4")
checar("o vídeo da subdivisão é convertido", st == 200 and (r.get("video_url") or "").endswith(".mp4"), (st, r))
_st, f = chamar("GET", LINK)
cat1 = next(x for x in f["categorias"] if x["id"] == g1["id"])
checar("o feed leva a foto da seção (a abertura automática)", bool(cat1.get("foto")), cat1)
checar("e o vídeo da subdivisão, com a capa", cat1["subcategorias"][0].get("video", "").endswith(".mp4")
       and cat1["subcategorias"][0].get("capa"), cat1["subcategorias"])
_st, conteudo = chamar("GET", f"/catalogos/{ID}/conteudo", token=token)
checar("o editor recebe o vídeo da seção",
       conteudo["categorias"][0]["subcategorias"][0].get("video_url", "").endswith(".mp4"), "")
st, r = chamar("DELETE", f"/catalogos/secoes/subcategoria/{sub['id']}/video", token=token)
checar("tirar o vídeo da seção", st == 200 and r.get("video_url") is None, (st, r))

print("\n5. a medição")
S = str(uuid.uuid4())
st, _r = chamar("POST", "/publico/cardapio/eventos", {
    "sessao": S, "loja": U, "modo": "VITRINE", "catalogo": ID, "eventos": [
        {"tipo": "viu_cartao", "cartao": harmon["id"], "duracao_ms": 4000},
        {"tipo": "clicou_cartao", "cartao": harmon["id"], "item": it["pap"]},
        {"tipo": "viu_secao", "categoria": g1["id"], "subcategoria": sub["id"], "duracao_ms": 2000},
        {"tipo": "viu_cartao", "cartao": OUTRO_CARTAO, "duracao_ms": 1000}]})
checar("os eventos dos cartões são aceitos", st == 204, st)
with get_cursor() as cur:
    cur.execute("SELECT tipo, id_cartao, id_subcategoria FROM cardapio_eventos WHERE id_sessao = %s ORDER BY id", (S,))
    ev = [dict(x) for x in cur.fetchall()]
checar("o cartão deste cardápio é gravado; o de OUTRO cardápio vira nulo",
       ev[0]["id_cartao"] == harmon["id"] and ev[3]["id_cartao"] is None, ev)
checar("a abertura da subdivisão grava a subdivisão", ev[2]["id_subcategoria"] == sub["id"], ev)
_st, lista = chamar("GET", f"/catalogos/{ID}/cartoes", token=token)
h = next(x for x in lista["cartoes"] if x["id"] == harmon["id"])
checar("o editor vê as vistas, os segundos e os cliques do cartão",
       h["vistas"] == 1 and float(h["segundos"]) == 4.0 and h["cliques"] == 1, h)
checar("e a atenção da abertura da seção",
       any(a["id_subcategoria"] == sub["id"] and a["vistas"] == 1 for a in lista["aberturas"]), lista["aberturas"])

print("\n5b. a tradução corrigida à mão (16/10/2026)")
st, tr = chamar("GET", f"/traducao/cartao/{harmon['id']}", token=token)
checar("a tradução do cartão abre, com o título como origem",
       st == 200 and tr["origem"]["nome"] == "Vai bem com o Chianti" and tr["campos"] == ["nome", "descricao"], (st, tr))
st, tr = chamar("PUT", f"/traducao/cartao/{harmon['id']}", {"en": {"nome": "Pairs well with Chianti"}}, token)
checar("corrigir o inglês grava e marca como feito à mão",
       st == 200 and tr["en"]["nome"] == "Pairs well with Chianti" and "titulo_en" in tr["editada"], (st, tr))
_st, f = chamar("GET", LINK + "&idioma=en")
c = next(x for x in f["cartoes"] if x["id"] == harmon["id"])
checar("e o feed em inglês mostra a correção", c["titulo"] == "Pairs well with Chianti", c)
st, r = chamar("PUT", f"/traducao/cartao/{harmon['id']}", {"de": {"nome": "x" * 130}}, token)
checar("título traduzido maior que 120 letras é recusado (422), não um erro do banco", st == 422, (st, r))

print("\n6. mexer e apagar")
st, r = chamar("PUT", f"/catalogos/cartoes/{harmon['id']}",
               {"id_categoria": g1["id"], "antes_do_item": it["tal"], "titulo": "Vai bem com o Chianti",
                "id_item_link": it["pap"], "ativo": True}, token)
checar("mudar a posição grava", st == 200 and r.get("antes_do_item") == it["tal"], (st, r))
chamar("DELETE", f"/catalogos/itens/{it['tal']}", token=token)
_st, f = chamar("GET", LINK)
c = next(x for x in f["cartoes"] if x["id"] == harmon["id"])
checar("o prato da posição saiu do cardápio: o cartão fica, no fim da lista", c["antes_do_item"] is None, c)
st, r = chamar("DELETE", f"/catalogos/cartoes/{fim['id']}", token=token)
checar("apagar o cartão", st == 200, (st, r))
st, _r = chamar("PUT", f"/catalogos/cartoes/{fim['id']}", {"titulo": "x"}, token)
checar("e ele não existe mais (404)", st == 404, st)
st, _r = chamar("GET", f"/catalogos/{ID}/cartoes")
checar("sem login, a lista recusa (401)", st == 401, st)


def _arquivos_de(sql: str, valores: tuple) -> list[str]:
    """Os nomes guardados em `arquivos` que as URLs do SELECT apontam."""
    with get_cursor() as cur:
        cur.execute(sql, valores)
        return [u.split("/arquivos/", 1)[1] for r in cur.fetchall() for u in r.values() if u]


def _existem(nomes: list[str]) -> int:
    with get_cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM arquivos WHERE nome = ANY(%s)", (nomes,))
        return cur.fetchone()["n"]


print("\n7. excluir leva a mídia junto (17/10/2026)")
# ⚠️ Até a 1.1.108 excluir a seção apagava só a FOTO dela: o vídeo, a mídia das subdivisões e a
# dos cartões ficavam na tabela `arquivos` sem ninguém apontando para eles.
enviar(f"/catalogos/secoes/subcategoria/{sub['id']}/video", token, VIDEO, "rec.mp4", "video/mp4")
enviar(f"/catalogos/cartoes/{harmon['id']}/foto", token, FOTO, "h.png", "image/png")
_st, na_sub = chamar("POST", f"/catalogos/{ID}/cartoes",
                     {"id_categoria": g1["id"], "id_subcategoria": sub["id"], "titulo": "Na subdivisão"}, token)
enviar(f"/catalogos/cartoes/{na_sub['id']}/foto", token, FOTO, "s.png", "image/png")
midias = _arquivos_de(
    """SELECT foto_url, video_url, video_capa_url FROM catalogo_categorias WHERE id = %s
       UNION ALL SELECT foto_url, video_url, video_capa_url FROM catalogo_subcategorias WHERE id = %s
       UNION ALL SELECT foto_url, video_url, video_capa_url FROM catalogo_cartoes WHERE id IN (%s, %s)""",
    (g1["id"], sub["id"], harmon["id"], na_sub["id"]))
checar("o cenário tem a foto da seção, o vídeo e a capa da subdivisão e a foto de dois cartões",
       len(midias) == 5 and _existem(midias) == 5, midias)
st, r = chamar("DELETE", f"/catalogos/categorias/{g1['id']}", token=token)
checar("excluir a seção", st == 200, (st, r))
checar("e NENHUM desses arquivos fica no banco", _existem(midias) == 0, _existem(midias))

_st, rasc = chamar("POST", "/catalogos", {"nome": f"Rascunho {MARCA}", "origem": "PRODUTOS"}, token)
_st, gr = chamar("POST", f"/catalogos/{rasc['id']}/categorias", {"nome": "Uma"}, token)
enviar(f"/catalogos/secoes/categoria/{gr['id']}/foto", token, FOTO, "r.png", "image/png")
_st, ab = chamar("POST", f"/catalogos/{rasc['id']}/cartoes", {"titulo": "Abertura"}, token)
enviar(f"/catalogos/cartoes/{ab['id']}/foto", token, FOTO, "a.png", "image/png")
midias = _arquivos_de(
    """SELECT foto_url FROM catalogo_categorias WHERE id = %s
       UNION ALL SELECT foto_url FROM catalogo_cartoes WHERE id = %s""", (gr["id"], ab["id"]))
st, r = chamar("DELETE", f"/catalogos/{rasc['id']}", token=token)
checar("excluir o catálogo rascunho leva a foto da seção e a da abertura",
       st == 200 and len(midias) == 2 and _existem(midias) == 0, (st, midias, _existem(midias)))

print("\n8. a varredura dos arquivos sem dono (Administração ▸ Empresa)")
with get_cursor() as cur:
    for nome, idade in ((f"orfao-velho-{MARCA}.png", "3 days"), (f"orfao-novo-{MARCA}.png", "1 minute")):
        cur.execute(f"""INSERT INTO arquivos (nome, dono, tipo, conteudo, bytes, criado_em)
                        VALUES (%s, 'teste', 'image/png', %s, %s, now() - interval '{idade}')""",  # noqa: S608
                    (nome, FOTO, len(FOTO)))
st, orf = chamar("GET", "/empresa/arquivos-orfaos", token=token)
nomes = {o["nome"] for o in (orf or {}).get("orfaos", [])}
checar("a varredura acha o arquivo velho sem dono", st == 200 and f"orfao-velho-{MARCA}.png" in nomes, st)
checar("e deixa de fora o enviado há menos de um dia", f"orfao-novo-{MARCA}.png" not in nomes, "")
with get_cursor() as cur:
    cur.execute("SELECT foto_url FROM produtos WHERE foto_url IS NOT NULL LIMIT 1")
    em_uso = cur.fetchone()
if em_uso:
    checar("e nunca lista um arquivo em uso (a foto de um produto)",
           em_uso["foto_url"].split("/arquivos/", 1)[1] not in nomes, em_uso)
alvo = [f"orfao-velho-{MARCA}.png", f"orfao-novo-{MARCA}.png"] + ([em_uso["foto_url"].split("/arquivos/", 1)[1]] if em_uso else [])
st, r = chamar("POST", "/empresa/arquivos-orfaos/apagar", {"nomes": alvo}, token)
checar("apagar leva só o órfão velho — o novo e o em uso ficam, mesmo pedidos",
       st == 200 and r["apagados"] == 1 and _existem(alvo[1:]) == len(alvo) - 1, (st, r))
st, _r = chamar("GET", "/empresa/arquivos-orfaos")
checar("sem login, a varredura recusa (401)", st == 401, st)
with get_cursor() as cur:
    cur.execute("DELETE FROM arquivos WHERE nome LIKE %s", (f"orfao-%-{MARCA}.png",))

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
sys.exit(1 if falhas else 0)
