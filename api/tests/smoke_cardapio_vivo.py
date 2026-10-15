"""Cardápio Vivo, fase 1 (migração 113): acesso por mesa, feed, VITRINE, cadastro e eventos.

🔑 **Pedido do dono (14/10/2026)**, estudo em `docs/cardapio-vivo-estudo.md`.

⚠️ **Metade desta suíte é sobre o que a rota PÚBLICA recusa**: o QR antigo, a loja
errada, o item de outro cardápio e o lote grande. É a única porta sem login que
grava alguma coisa.

    python tests/smoke_cardapio_vivo.py        (API de pé na 9200)
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
from datetime import datetime, time as hora, timedelta
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import preservar_reserva  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
MARCA = str(time.time_ns() // 100)[-6:]

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
_st, eu = chamar("GET", "/auth/me", token=token)
U = (eu.get("unidades") or [{}])[0].get("id") or 1

# 🔑 Suíte devolve o que encontrou: reserva da loja (o módulo ligado) e o Cardápio Vivo dela.
preservar_reserva(U)
# 🔑 Desde a 117, o Cardápio Vivo da loja são DUAS tabelas — a suíte devolve as duas.
from comum import gravar_cardapio, preservar_cardapio_vivo  # noqa: E402
preservar_cardapio_vivo(U)
with get_cursor() as cur:
    cur.execute("SELECT * FROM cardapio_config WHERE id_unidade = %s", (U,))
    _CFG_ANTES = cur.fetchone()
    _CFG_ANTES = dict(_CFG_ANTES) if _CFG_ANTES else None


def _devolver_config():
    with get_cursor() as cur:
        cur.execute("DELETE FROM cardapio_config WHERE id_unidade = %s", (U,))
        if _CFG_ANTES:
            cols = list(_CFG_ANTES)
            cur.execute(f"INSERT INTO cardapio_config ({', '.join(cols)}) "
                        f"VALUES ({', '.join(['%s'] * len(cols))})",
                        [_CFG_ANTES[c] for c in cols])
        cur.execute("DELETE FROM catalogos WHERE nome LIKE %s", (f"%{MARCA}%",))
        cur.execute("DELETE FROM produtos WHERE nome LIKE %s", (f"%{MARCA}%",))
        cur.execute("DELETE FROM saloes WHERE nome LIKE %s", (f"%{MARCA}%",))


atexit.register(_devolver_config)
_st, par = chamar("GET", f"/unidades/{U}/parametros", token=token)
chamar("PUT", f"/unidades/{U}/parametros", {**par, "reservas_ligado": True}, token)


def produto(nome, preco=None):
    _st, p = chamar("POST", "/produtos", {"nome": f"{nome} {MARCA}", "tipo": "INSUMO",
                                          "um_estoque": "UN", "controla_estoque": False}, token)
    _st, atual = chamar("GET", f"/produtos/{p['id']}", token=token)
    chamar("PUT", f"/produtos/{p['id']}", {**atual, "integrado_pdv": True,
                                            **({"preco_venda": preco} if preco is not None else {})},
           token)
    return p["id"]


print("0. cenário: um cardápio de produtos, um salão com duas mesas")
_st, cat = chamar("POST", "/catalogos", {"nome": f"Vivo {MARCA}", "origem": "PRODUTOS",
                                         "situacao": "ATIVO"}, token)
ID_CAT = cat.get("id")
_st, pdf = chamar("POST", "/catalogos", {"nome": f"Vivo PDF {MARCA}", "origem": "PDF"}, token)
_st, g1 = chamar("POST", f"/catalogos/{ID_CAT}/categorias", {"nome": "Pratos", "ordem": 1}, token)
_st, g2 = chamar("POST", f"/catalogos/{ID_CAT}/categorias", {"nome": "Sábado", "ordem": 2}, token)
_st, sub = chamar("POST", f"/catalogos/categorias/{g1['id']}/subcategorias",
                  {"nome": "Pra Dividir"}, token)
A, B, C, D = (produto("VIVO RISOTO", 58), produto("VIVO BATATA", 32), produto("VIVO FEIJOADA", 79),
              produto("VIVO SUCO", 12))
itens = {}
for nome, pid, sec, sub_id in (("A", A, g1, None), ("B", B, g1, sub["id"]),
                               ("C", C, g2, None), ("D", D, g1, None)):
    _st, it = chamar("POST", f"/catalogos/categorias/{sec['id']}/itens",
                     {"id_produto": pid, **({"id_subcategoria": sub_id} if sub_id else {})}, token)
    itens[nome] = it.get("id")
with get_cursor() as cur:
    cur.execute("INSERT INTO saloes (id_unidade, nome) VALUES (%s, %s) RETURNING id",
                (U, f"Varanda {MARCA}"))
    SALAO = cur.fetchone()["id"]
    mesas = []
    for n in ("1", "2"):
        cur.execute("""INSERT INTO mesas (id_unidade, id_salao, nome, lugares, capacidade_max)
                       VALUES (%s, %s, %s, 4, 4) RETURNING id, token""", (U, SALAO, n))
        mesas.append(dict(cur.fetchone()))
M1, M2 = mesas
checar("o cenário existe", ID_CAT and all(itens.values()) and M1["token"], (itens, M1))
checar("a mesa nova nasce com token (o padrão da migração não é só para as antigas)",
       bool(M1["token"]) and M1["token"] != M2["token"])

print("\n1. sem configuração, a mesa não tem cardápio")
with get_cursor() as cur:
    cur.execute("DELETE FROM cardapio_config WHERE id_unidade = %s", (U,))
    cur.execute("DELETE FROM cardapio_vivos WHERE id_unidade = %s", (U,))
st, r = chamar("GET", f"/publico/cardapio/mesa/{M1['token']}")
checar("404 enquanto a loja não aponta um catálogo", st == 404, (st, r))

print("\n2. a configuração da loja")
st, r = chamar("GET", "/cardapio-vivo/config", token=token)
checar("nasce sem Cardápio Vivo nenhum", st == 200 and r["vivos"] == []
       and r["config"]["id_catalogo"] is None, (st, r))
checar("oferece só os catálogos de PRODUTOS",
       ID_CAT in [c["id"] for c in r["catalogos"]] and pdf["id"] not in [c["id"] for c in r["catalogos"]])
CFG = {"id_catalogo": ID_CAT, "modo": "VITRINE", "cor_principal": "#3d5a3a",
       "cor_fundo": "#f5efe4", "fonte": "NEWSREADER", "retencao_meses": 13}
st, r = gravar_cardapio(chamar, token, {**CFG, "id_catalogo": pdf["id"]})
checar("apontar um PDF é recusado (409)", st == 409, (st, r))
st, r = gravar_cardapio(chamar, token, {**CFG, "modo": "PEDIDO"})
# Fase 2 (115): o PEDIDO foi liberado — a suíte dele é `smoke_cardapio_pedido.py`.
checar("o modo PEDIDO é aceito desde a fase 2", st == 200 and r["vivos"][0]["modo"] == "PEDIDO", (st, r))
gravar_cardapio(chamar, token, CFG)
st, r = gravar_cardapio(chamar, token, {**CFG, "cor_principal": "verde"})
checar("cor que não é #RRGGBB é recusada", st == 422, st)
st, r = gravar_cardapio(chamar, token, CFG)
checar("a configuração grava", st == 200 and r["config"]["id_catalogo"] == ID_CAT, (st, r))
checar("e devolve o link da loja (vitrine, balcão)", r["link_loja"].endswith(f"/c/{U}"), r.get("link_loja"))
checar("e avisa os itens publicados sem foto e sem vídeo",
       {i["id"] for i in r["sem_midia"]} >= set(itens.values()), r.get("sem_midia"))

print("\n3. o feed da mesa")
st, f = chamar("GET", f"/publico/cardapio/mesa/{M1['token']}")
checar("abre pela mesa (200)", st == 200, (st, f))
checar("diz a mesa e o salão", f.get("mesa") == {"nome": "1", "salao": f"Varanda {MARCA}"}, f.get("mesa"))
checar("em VITRINE", f.get("modo") == "VITRINE", f.get("modo"))
checar("com a marca da loja", f["marca"]["cor_principal"] == "#3d5a3a", f.get("marca"))
ordem = [i["id"] for i in f["itens"]]
checar("os itens na ordem do cardápio (soltos, depois a subcategoria, depois a outra seção)",
       ordem == [itens["A"], itens["D"], itens["B"], itens["C"]], ordem)
risoto = next(i for i in f["itens"] if i["id"] == itens["A"])
checar("o preço da loja", risoto["preco"] == 58.0, risoto)
checar("sem mídia nenhuma, diz NENHUMA", risoto["midia"]["tipo"] == "NENHUMA", risoto["midia"])
checar("nada de id de produto nem custo no público",
       not any(k in risoto for k in ("id_produto", "custo", "saldo")), list(risoto))
st, r = chamar("GET", "/publico/cardapio/mesa/naoexiste123")
checar("token inventado: 404", st == 404, st)
st, r = chamar("GET", f"/publico/cardapio/loja/{U}")
checar("a URL da loja (sem mesa) abre também", st == 200 and r.get("mesa") is None, (st, r))
# 🔑 **O site de reservas sabe qual catálogo é o Cardápio Vivo** (pedido do dono,
# 14/10/2026): é por este campo que ele leva ao feed `/c/{loja}` em vez da tela antiga.
st, lista = chamar("GET", f"/publico/{U}/catalogos")
vivo = next((c for c in (lista or []) if c.get("id") == ID_CAT), None)
checar("a lista pública do site marca o Cardápio Vivo",
       st == 200 and vivo is not None and vivo.get("cardapio_vivo") is True, (st, vivo))
checar("e só ele", all(c.get("cardapio_vivo") is False for c in (lista or []) if c.get("id") != ID_CAT),
       [(c.get("id"), c.get("cardapio_vivo")) for c in (lista or [])])

print("\n4. a mídia em cascata: vídeo → foto do item → subcategoria → categoria")
from base64 import b64decode  # noqa: E402
FOTO = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+wSzIAAAABlBMVEX///+/v7+jQ3Y5AAAA"
                 "DklEQVQI12P4AIX8EAgALgAD/aNpbtEAAAAASUVORK5CYII=")
enviar(f"/catalogos/secoes/categoria/{g1['id']}/foto", token, FOTO, "cat.png", "image/png")
enviar(f"/catalogos/secoes/subcategoria/{sub['id']}/foto", token, FOTO, "sub.png", "image/png")
enviar(f"/produtos/{D}/foto", token, FOTO, "suco.png", "image/png")
_st, f = chamar("GET", f"/publico/cardapio/mesa/{M1['token']}")
por_id = {i["id"]: i for i in f["itens"]}
checar("o item com foto própria mostra a dele", por_id[itens["D"]]["midia"]["tipo"] == "FOTO"
       and not por_id[itens["D"]]["midia"]["herdada"], por_id[itens["D"]]["midia"])
checar("o da subcategoria herda a foto dela", por_id[itens["B"]]["midia"]["herdada"]
       and "subcategoria" in por_id[itens["B"]]["midia"]["foto"], por_id[itens["B"]]["midia"])
checar("o solto na categoria herda a da categoria",
       "categoria" in (por_id[itens["A"]]["midia"]["foto"] or ""), por_id[itens["A"]]["midia"])

# Um vídeo de 3 s, gerado aqui mesmo — a suíte não depende de arquivo de fora.
import imageio_ffmpeg  # noqa: E402
with tempfile.TemporaryDirectory() as pasta:
    bruto = Path(pasta) / "teste.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc=duration=3:size=1080x1920:rate=30", "-pix_fmt", "yuv420p",
                    str(bruto)], check=True)
    VIDEO = bruto.read_bytes()
st, r = enviar(f"/produtos/{A}/video", token, b"nao sou video", "x.mp4", "video/mp4")
checar("arquivo que não é vídeo é recusado (400)", st == 400, (st, r))
st, r = enviar(f"/produtos/{A}/video", token, FOTO, "x.png", "image/png")
checar("imagem no lugar do vídeo é recusada pelo tipo", st == 400, (st, r))
st, r = enviar(f"/produtos/{A}/video", token, VIDEO, "risoto.mp4", "video/mp4")
checar("o vídeo é convertido e gravado", st == 200 and r["video"]["url"].endswith(".mp4"), (st, r))
checar("com a duração", 2.5 <= (r.get("video") or {}).get("segundos", 0) <= 3.5, r)
checar("e cabe nos ~2 MB", (r.get("video") or {}).get("bytes", 9e9) < 3 * 1024 * 1024, r)
_st, f = chamar("GET", f"/publico/cardapio/mesa/{M1['token']}")
m = next(i for i in f["itens"] if i["id"] == itens["A"])["midia"]
checar("o vídeo ganha da foto, com a capa (poster)", m["tipo"] == "VIDEO" and m["capa"], m)

print("\n4b. o arquivo do vídeo: em partes, como o iPhone pede")
req = urllib.request.Request(BASE + m["video"], headers={"Range": "bytes=0-1"})
with urllib.request.urlopen(req) as resp:
    checar("Range responde 206 com dois bytes", resp.status == 206 and len(resp.read()) == 2,
           resp.status)
    checar("e diz o total", resp.headers["Content-Range"].startswith("bytes 0-1/"),
           resp.headers.get("Content-Range"))
with urllib.request.urlopen(BASE + m["capa"]) as resp:
    checar("a capa sai em WebP", resp.headers["Content-Type"] == "image/webp")
with urllib.request.urlopen(BASE + por_id[itens["D"]]["midia"]["foto"] + "?w=480") as resp:
    checar("a foto pedida com ?w= sai redimensionada em WebP",
           resp.headers["Content-Type"] == "image/webp")

print("\n5. restrições, destaque e esgotado")
st, r = chamar("PUT", f"/produtos/{B}/restricoes", {"restricoes": ["VEGANO", "PICANTE"]}, token)
checar("restrição fora da lista fixa é recusada", st == 422, (st, r))
st, r = chamar("PUT", f"/produtos/{B}/restricoes", {"restricoes": ["SEM_GLUTEN", "VEGANO"]}, token)
checar("as da lista gravam, na ordem do vocabulário", r.get("restricoes") == ["VEGANO", "SEM_GLUTEN"], r)
st, r = chamar("PUT", f"/catalogos/itens/{itens['B']}/marcas", {"destaque": True}, token)
checar("destaque grava sem mexer no esgotado", r.get("destaque") is True and r.get("esgotado") is False, r)
st, r = chamar("PUT", f"/catalogos/itens/{itens['D']}/marcas", {"esgotado": True}, token)
_st, f = chamar("GET", f"/publico/cardapio/mesa/{M1['token']}")
por_id = {i["id"]: i for i in f["itens"]}
checar("o esgotado CONTINUA no feed, marcado", por_id.get(itens["D"], {}).get("esgotado") is True)
checar("as restrições e o destaque saem no feed",
       por_id[itens["B"]]["restricoes"] == ["VEGANO", "SEM_GLUTEN"] and por_id[itens["B"]]["destaque"])
gravar_cardapio(chamar, token, {**CFG, "esconder_esgotado": True})
_st, f = chamar("GET", f"/publico/cardapio/mesa/{M1['token']}")
checar("com a opção da loja, o esgotado some", itens["D"] not in [i["id"] for i in f["itens"]])
gravar_cardapio(chamar, token, CFG)
st, r = chamar("PUT", f"/catalogos/itens/999999/marcas", {"destaque": True}, token)
checar("item que não existe: 404", st == 404, st)

print("\n6. a seção por dia e horário")
from relogio import agora_da_casa  # noqa: E402
agora = agora_da_casa().replace(tzinfo=None)
hoje = agora.isoweekday()
outro = 1 if hoje != 1 else 2
st, r = chamar("PUT", f"/catalogos/secoes/categoria/{g2['id']}/exibicao", {"dias": [outro]}, token)
checar("a exibição grava", st == 200 and r.get("dias") == [outro], (st, r))
_st, f = chamar("GET", f"/publico/cardapio/mesa/{M1['token']}")
checar("fora do dia, a seção e os itens dela somem", itens["C"] not in [i["id"] for i in f["itens"]]
       and g2["id"] not in [c["id"] for c in f["categorias"]])
with get_cursor() as cur:
    cur.execute("""INSERT INTO reserva_dias_especiais (id_unidade, data, abre, fecha, ultima_reserva, motivo)
                   VALUES (%s, %s, '00:00', '23:59', '23:00', 'smoke') ON CONFLICT DO NOTHING""",
                (U, agora.date()))
chamar("PUT", f"/catalogos/secoes/categoria/{g2['id']}/exibicao",
       {"dias": [outro], "horario_especial": True}, token)
_st, f = chamar("GET", f"/publico/cardapio/mesa/{M1['token']}")
checar("'Sábados e Feriados': no dia especial ela aparece", itens["C"] in [i["id"] for i in f["itens"]])
with get_cursor() as cur:
    cur.execute("DELETE FROM reserva_dias_especiais WHERE id_unidade = %s AND motivo = 'smoke'", (U,))
de = (agora + timedelta(hours=2)).time().replace(second=0, microsecond=0)
ate = (agora + timedelta(hours=3)).time().replace(second=0, microsecond=0)
chamar("PUT", f"/catalogos/secoes/categoria/{g2['id']}/exibicao",
       {"hora_de": str(de), "hora_ate": str(ate)}, token)
_st, f = chamar("GET", f"/publico/cardapio/mesa/{M1['token']}")
checar("fora da faixa de horário, some", itens["C"] not in [i["id"] for i in f["itens"]])
st, prev = chamar("GET", f"/cardapio-vivo/previa?id_catalogo={ID_CAT}", token=token)
checar("mas a PRÉVIA do cadastro a mostra, marcada",
       st == 200 and any(c["id"] == g2["id"] and c["fora_do_horario"] for c in prev["categorias"]),
       (st, prev.get("categorias") if isinstance(prev, dict) else prev))
st, r = chamar("PUT", f"/catalogos/secoes/categoria/{g2['id']}/exibicao", {"hora_de": "10:00"}, token)
checar("só uma ponta do horário é recusada", st == 422, st)
st, r = chamar("PUT", f"/catalogos/secoes/categoria/{g2['id']}/exibicao", {"dias": [8]}, token)
checar("dia 8 é recusado", st == 422, st)
chamar("PUT", f"/catalogos/secoes/categoria/{g2['id']}/exibicao", {}, token)
from services import cardapio_vivo as sv  # noqa: E402
checar("a faixa que vira a meia-noite vale nos dois lados",
       sv._na_faixa(hora(23, 30), hora(22), hora(2)) and sv._na_faixa(hora(1), hora(22), hora(2))
       and not sv._na_faixa(hora(12), hora(22), hora(2)))

print("\n7. exceções: a mais específica vence")
with get_cursor() as cur:
    # Desde a 117 o modo é do Cardápio Vivo PRINCIPAL (o da mesa), não da loja.
    cur.execute("""UPDATE cardapio_vivos SET modo = 'PEDIDO', pedido_hora_de = '11:00',
                          pedido_hora_ate = '15:00'
                    WHERE id_unidade = %s AND id_catalogo = %s""", (U, ID_CAT))
    meio_dia = datetime(2026, 10, 14, 12, 0)
    checar("a loja em PEDIDO, dentro do horário", sv.modo_efetivo(cur, U, M1["id"], meio_dia)["modo"] == "PEDIDO")
    noite = sv.modo_efetivo(cur, U, M1["id"], datetime(2026, 10, 14, 20, 0))
    checar("fora do horário cai para VITRINE, com o aviso",
           noite["modo"] == "VITRINE" and noite["aviso"] == "Pedidos com o garçom.", noite)
    cur.execute("INSERT INTO cardapio_excecoes (id_unidade, id_salao, modo) VALUES (%s, %s, 'VITRINE')",
                (U, SALAO))
    checar("o salão em VITRINE vence a loja", sv.modo_efetivo(cur, U, M1["id"], meio_dia)["modo"] == "VITRINE")
    cur.execute("""INSERT INTO cardapio_excecoes (id_unidade, id_mesa, modo, pedido_hora_de, pedido_hora_ate)
                   VALUES (%s, %s, 'PEDIDO', '18:00', '23:00')""", (U, M2["id"]))
    checar("a mesa vence o salão", sv.modo_efetivo(cur, U, M2["id"], datetime(2026, 10, 14, 20, 0))["modo"] == "PEDIDO")
    checar("e com o horário DELA (meio-dia está fora)",
           sv.modo_efetivo(cur, U, M2["id"], meio_dia)["modo"] == "VITRINE")
    checar("a mesa 1 continua com o salão", sv.modo_efetivo(cur, U, M1["id"], meio_dia)["modo"] == "VITRINE")
    cur.execute("DELETE FROM cardapio_excecoes WHERE id_unidade = %s", (U,))
gravar_cardapio(chamar, token, CFG)
st, r = chamar("PUT", "/cardapio-vivo/excecoes", {"id_salao": SALAO, "id_mesa": M1["id"]}, token)
checar("exceção de salão E mesa ao mesmo tempo é recusada", st == 422, st)
st, r = chamar("PUT", "/cardapio-vivo/excecoes", {"id_mesa": M1["id"], "modo": "VITRINE"}, token)
checar("a exceção de mesa grava pela rota", st == 200, (st, r))
st, lista = chamar("GET", "/cardapio-vivo/excecoes", token=token)
checar("e aparece na lista com o nome do salão", any(e["mesa"] == "1" and e["salao"] == f"Varanda {MARCA}"
                                                     for e in lista), lista)
chamar("DELETE", f"/cardapio-vivo/excecoes/{r['id']}", token=token)

print("\n8. o acesso das mesas: link, QR e token novo")
st, r = chamar("GET", "/cardapio-vivo/mesas", token=token)
minha = next((m for m in r.get("mesas", []) if m["id"] == M1["id"]), {})
checar("cada mesa tem o link com o token", minha.get("link", "").endswith(f"/c/{U}/{M1['token']}"), minha)
st, png = chamar("GET", f"/cardapio-vivo/mesas/{M1['id']}/qr.png", token=token)
checar("o QR sai em PNG", st == 200 and png[:8] == b"\x89PNG\r\n\x1a\n", st)
st, pdf_qr = chamar("GET", f"/cardapio-vivo/mesas/qr.pdf?ids={M1['id']},{M2['id']}", token=token)
checar("e o PDF das mesas escolhidas", st == 200 and pdf_qr[:5] == b"%PDF-", st)
st, r = chamar("POST", f"/cardapio-vivo/mesas/{M1['id']}/token", token=token)
checar("gerar de novo devolve outro link", st == 200 and M1["token"] not in r["link"], (st, r))
st, _r = chamar("GET", f"/publico/cardapio/mesa/{M1['token']}")
checar("e o QR ANTIGO para de abrir", st == 404, st)
NOVO = r["link"].rsplit("/", 1)[1]

print("\n9. os eventos (sendBeacon, text/plain)")
SESSAO = str(uuid.uuid4())
lote = {"sessao": SESSAO, "loja": U, "mesa": NOVO, "modo": "VITRINE", "dispositivo": "CELULAR",
        "eventos": [{"tipo": "abriu_cardapio"},
                    {"tipo": "viu_item", "item": itens["A"], "midia": "VIDEO", "duracao_ms": 4200},
                    {"tipo": "adicionou", "item": itens["A"], "midia": "VIDEO"},
                    {"tipo": "removeu", "item": itens["A"], "midia": "VIDEO", "idade_ms": 1000},
                    {"tipo": "viu_item", "item": 999999, "midia": "FOTO", "duracao_ms": 100}]}
st, _r = chamar("POST", "/publico/cardapio/eventos", bruto=json.dumps(lote).encode(), tipo="text/plain")
checar("o lote grava (204)", st == 204, (st, _r))
with get_cursor() as cur:
    cur.execute("SELECT tipo, id_produto, id_mesa, id_item FROM cardapio_eventos WHERE id_sessao = %s "
                "ORDER BY id", (SESSAO,))
    ev = [dict(x) for x in cur.fetchall()]
checar("cinco eventos, na mesa certa", len(ev) == 5 and all(e["id_mesa"] == M1["id"] for e in ev), ev)
checar("o produto é descoberto pelo item", ev[1]["id_produto"] == A, ev[1])
checar("item que não é deste cardápio fica sem item e sem produto",
       ev[4]["id_item"] is None and ev[4]["id_produto"] is None, ev[4])
st, r = chamar("POST", "/publico/cardapio/eventos",
               bruto=json.dumps({**lote, "mesa": M1["token"]}).encode(), tipo="text/plain")
checar("com o token antigo, a mesa não existe (404)", st == 404, st)
with get_cursor() as cur:
    cur.execute("SELECT id FROM unidades WHERE id <> %s LIMIT 1", (U,))
    outra = cur.fetchone()
if outra:
    st, r = chamar("POST", "/publico/cardapio/eventos",
                   bruto=json.dumps({**lote, "loja": outra["id"]}).encode(), tipo="text/plain")
    checar("a sessão não troca de loja", st in (404, 409), st)
st, r = chamar("POST", "/publico/cardapio/eventos",
               bruto=json.dumps({**lote, "eventos": [{"tipo": "hackeou"}]}).encode(), tipo="text/plain")
checar("tipo de evento desconhecido: 422", st == 422, st)
st, r = chamar("POST", "/publico/cardapio/eventos", bruto=b"x" * 70000, tipo="text/plain")
checar("lote acima de 64 KB: 413", st == 413, st)

print("\n10. o resumo do dia e a retenção")
with get_cursor() as cur:
    cur.execute("UPDATE cardapio_eventos SET quando = quando - interval '400 days' WHERE id_sessao = %s",
                (SESSAO,))
    sv.reter(cur)
    cur.execute("SELECT count(*) AS n FROM cardapio_eventos WHERE id_sessao = %s", (SESSAO,))
    checar("o bruto além de 13 meses é apagado", cur.fetchone()["n"] == 0)
    cur.execute("""SELECT sum(visualizacoes) AS v, sum(adicoes) AS a, sum(remocoes) AS r,
                          sum(atencao_ms) AS ms
                     FROM cardapio_agregados_dia WHERE id_produto = %s""", (A,))
    ag = dict(cur.fetchone())
    checar("mas o agregado fica — feito ANTES de apagar",
           ag["v"] == 1 and ag["a"] == 1 and ag["r"] == 1 and ag["ms"] == 4200, ag)

print("\n11. adicionais do produto")
st, r = chamar("PUT", f"/produtos/{A}/adicionais",
               [{"nome": "Ponto", "minimo": 2, "maximo": 1, "opcoes": [{"nome": "Al dente"}]}], token)
checar("mínimo maior que o máximo é recusado", st == 422, st)
st, r = chamar("PUT", f"/produtos/{A}/adicionais",
               [{"nome": "Extras", "minimo": 0, "maximo": 2,
                 "opcoes": [{"nome": "Parmesão", "preco": 6},
                            {"nome": "Suco junto", "preco": 99, "id_produto_ref": D}]}], token)
checar("os adicionais gravam", st == 200 and len(r["adicionais"]) == 1, (st, r))
_st, f = chamar("GET", f"/publico/cardapio/mesa/{NOVO}")
ad = next(i for i in f["itens"] if i["id"] == itens["A"])["adicionais"]
precos = {o["nome"]: o["preco"] for o in ad[0]["opcoes"]} if ad else {}
checar("no feed, o preço do texto é o digitado", precos.get("Parmesão") == 6.0, precos)
checar("e o que aponta para produto usa o preço DELE (o 99 digitado é ignorado)",
       precos.get("Suco junto") == 12.0, precos)
st, r = chamar("PUT", f"/produtos/{A}/adicionais",
               [{"nome": "X", "opcoes": [{"nome": "Eu mesmo", "id_produto_ref": A}]}], token)
checar("apontar para o próprio produto é recusado", st == 422, st)

print("\n11b. o Hub: avaliação no Google e Wi-Fi (114)")
_st, lojas = chamar("GET", "/unidades", token=token)
ANTES_LOJA = next(u for u in lojas if u["id"] == U)
atexit.register(lambda: chamar("PUT", f"/unidades/{U}", {k: ANTES_LOJA.get(k) for k in
                                                         ("google_avaliacao_url", "wifi_rede", "wifi_senha")}, token))
chamar("PUT", f"/unidades/{U}", {"google_avaliacao_url": None, "wifi_rede": None, "wifi_senha": None}, token)
_st, f = chamar("GET", f"/publico/cardapio/mesa/{NOVO}")
checar("sem nada ligado, não há Hub (a tela cai direto no feed)", f.get("hub") is None, f.get("hub"))
st, r = chamar("PUT", f"/unidades/{U}", {"google_avaliacao_url": "http://g.page/x"}, token)
checar("link de avaliação sem https é recusado", st == 422, st)
chamar("PUT", f"/unidades/{U}", {"google_avaliacao_url": "https://g.page/r/botane/review",
                                 "wifi_rede": "Botane Clientes", "wifi_senha": "cafe2026"}, token)
_st, f = chamar("GET", f"/publico/cardapio/mesa/{NOVO}")
checar("com o dado na loja mas o botão desligado, continua sem Hub", f.get("hub") is None, f.get("hub"))
gravar_cardapio(chamar, token, {**CFG, "hub_wifi": True})
_st, f = chamar("GET", f"/publico/cardapio/mesa/{NOVO}")
checar("ligado o Wi-Fi, o Hub traz rede e senha (e não a avaliação, desligada)",
       f.get("hub") == {"avaliacao": None, "wifi": {"rede": "Botane Clientes", "senha": "cafe2026"}},
       f.get("hub"))
gravar_cardapio(chamar, token, {**CFG, "hub_wifi": True, "hub_avaliacao": True})
_st, f = chamar("GET", f"/publico/cardapio/mesa/{NOVO}")
checar("e com a avaliação também",
       (f.get("hub") or {}).get("avaliacao") == "https://g.page/r/botane/review", f.get("hub"))
gravar_cardapio(chamar, token, CFG)

print("\n11c. eventos novos, atenção estimada e sessão engajada")
S1, S2 = str(uuid.uuid4()), str(uuid.uuid4())
base = {"loja": U, "mesa": NOVO, "modo": "VITRINE", "dispositivo": "CELULAR"}
lote1 = {**base, "sessao": S1, "eventos": [
    {"tipo": "abriu_hub"}, {"tipo": "clicou_wifi"}, {"tipo": "clicou_avaliacao"},
    {"tipo": "viu_item", "item": itens["A"], "midia": "VIDEO", "duracao_ms": 300000},
    {"tipo": "deslizou_frente", "item": itens["D"]}, {"tipo": "deslizou_tras", "item": itens["A"]},
    {"tipo": "favoritou", "item": itens["A"]}, {"tipo": "abriu_personalizacao", "item": itens["A"]},
    {"tipo": "escolheu_opcao", "item": itens["A"]}, {"tipo": "desfavoritou", "item": itens["A"]}]}
lote2 = {**base, "sessao": S2, "eventos": [{"tipo": "abriu_cardapio"},
                                          {"tipo": "viu_item", "item": itens["D"], "duracao_ms": 2000}]}
for lote in (lote1, lote2):
    st, _r = chamar("POST", "/publico/cardapio/eventos", bruto=json.dumps(lote).encode(), tipo="text/plain")
    checar("o lote com os tipos novos grava", st == 204, (st, _r))
with get_cursor() as cur:
    cur.execute("SELECT current_date AS d")
    dia = cur.fetchone()["d"]
    sv.agregar_dia(cur, dia, U)
    cur.execute("""SELECT sum(atencao_ms) AS ms, sum(favoritos) AS fav, sum(deslizes_tras) AS tras,
                          sum(personalizacoes) AS pers
                     FROM cardapio_agregados_dia WHERE dia = %s AND id_produto = %s""", (dia, A))
    ag = dict(cur.fetchone())
    checar("a atenção estimada tem teto de 60 s por visualização (5 min viram 60 s)", ag["ms"] == 60000, ag)
    checar("favoritos, deslizes para trás e personalizações entram no resumo",
           ag["fav"] == 1 and ag["tras"] == 1 and ag["pers"] == 1, ag)
    cur.execute("""SELECT count(*) FILTER (WHERE s.id = %s) AS s1, count(*) FILTER (WHERE s.id = %s) AS s2
                     FROM (SELECT id_sessao AS id FROM cardapio_eventos WHERE id_sessao IN (%s, %s)
                            GROUP BY id_sessao HAVING """ + sv.SQL_SESSAO_ENGAJADA + """) s""",
                (S1, S2, S1, S2))
    eng = dict(cur.fetchone())
    checar("a sessão que favoritou é engajada; a que viu um item só, não", eng == {"s1": 1, "s2": 0}, eng)
    cur.execute("SELECT * FROM cardapio_resumo_dia WHERE dia = %s AND id_unidade = %s", (dia, U))
    rs = dict(cur.fetchone() or {})
    checar("o resumo do dia separa sessões abertas de engajadas",
           rs.get("sessoes", 0) >= 2 and 1 <= rs.get("engajadas", 0) < rs["sessoes"], rs)
    checar("e conta os cliques do Hub", rs.get("hubs", 0) >= 1 and rs.get("cliques_wifi", 0) >= 1
           and rs.get("cliques_avaliacao", 0) >= 1, rs)

print("\n11d. vários Cardápios Vivos na loja (117)")
# 🔑 Pedido do dono (15/10/2026): a cafeteria (o principal, da mesa) e o Catering, pelo link.
_st, cat2 = chamar("POST", "/catalogos", {"nome": f"Catering {MARCA}", "origem": "PRODUTOS",
                                          "situacao": "ATIVO"}, token)
_st, gc = chamar("POST", f"/catalogos/{cat2['id']}/categorias", {"nome": "Kits"}, token)
_st, itc = chamar("POST", f"/catalogos/categorias/{gc['id']}/itens", {"id_produto": A}, token)
st, r = chamar("PUT", f"/cardapio-vivo/vivos/{cat2['id']}", {"slug": "catering"}, token)
checar("ligar um segundo Cardápio Vivo grava", st == 200, (st, r))
v2 = next((v for v in r.get("vivos", []) if v["id_catalogo"] == cat2["id"]), {})
checar("e ele NÃO toma o lugar do principal", v2.get("principal") is False
       and next(v for v in r["vivos"] if v["id_catalogo"] == ID_CAT)["principal"] is True, r.get("vivos"))
SLUG1 = next(v for v in r["vivos"] if v["id_catalogo"] == ID_CAT)["slug"]
checar("o principal ganhou um nome de link tirado do nome do catálogo",
       SLUG1.startswith("vivo-"), SLUG1)
checar("e tem o link próprio, com ?cardapio=", v2.get("link", "").endswith(f"/c/{U}?cardapio=catering"), v2)
_st, f = chamar("GET", f"/publico/cardapio/loja/{U}?cardapio=catering")
checar("o link abre o catering", f.get("cardapio") == f"Catering {MARCA}"
       and f.get("vivo", {}).get("slug") == "catering" and [i["id"] for i in f["itens"]] == [itc["id"]], f.get("vivo"))
_st, f = chamar("GET", f"/publico/cardapio/mesa/{NOVO}")
checar("e a mesa continua abrindo o principal", f.get("vivo", {}).get("id_catalogo") == ID_CAT, f.get("vivo"))
_st, f = chamar("GET", f"/publico/cardapio/loja/{U}")
checar("sem ?cardapio=, o link da loja é o principal", f.get("vivo", {}).get("id_catalogo") == ID_CAT)
st, _r = chamar("GET", f"/publico/cardapio/loja/{U}?cardapio=nao-existe")
checar("nome de link que não existe é 404", st == 404, st)
st, r = chamar("PUT", f"/cardapio-vivo/vivos/{cat2['id']}", {"slug": SLUG1}, token)
checar("o mesmo nome de link de outro cardápio é recusado (409)", st == 409 and "já é do" in r.get("detail", ""), (st, r))
st, r = chamar("PUT", f"/cardapio-vivo/vivos/{cat2['id']}", {"slug": "Catering Ç"}, token)
checar("nome de link com espaço ou acento é recusado (422)", st == 422, st)
st, r = chamar("PUT", f"/cardapio-vivo/vivos/{pdf['id']}", {}, token)
checar("PDF não vira Cardápio Vivo (409)", st == 409, st)
# Eventos do catering contam o produto pelo catálogo DELE.
S3 = str(uuid.uuid4())
st, _r = chamar("POST", "/publico/cardapio/eventos", {"sessao": S3, "loja": U, "modo": "VITRINE",
                "catalogo": cat2["id"], "eventos": [{"tipo": "viu_item", "item": itc["id"], "duracao_ms": 900}]})
with get_cursor() as cur:
    cur.execute("SELECT id_produto FROM cardapio_eventos WHERE id_sessao = %s", (S3,))
    ev = cur.fetchone()
checar("o evento do catering é aceito e acha o produto pelo item dele", st == 204 and ev and ev["id_produto"] == A, (st, ev))
# Trocar o principal: a mesa passa a abrir o catering; e volta.
st, r = chamar("PUT", f"/cardapio-vivo/vivos/{cat2['id']}", {"slug": "catering", "principal": True}, token)
_st, f = chamar("GET", f"/publico/cardapio/mesa/{NOVO}")
checar("marcar outro como principal: a mesa passa a abrir ele, e o antigo deixa de ser",
       f.get("vivo", {}).get("id_catalogo") == cat2["id"]
       and [v["principal"] for v in r["vivos"]].count(True) == 1, r.get("vivos"))
chamar("PUT", f"/cardapio-vivo/vivos/{ID_CAT}", {"slug": "cardapio", "principal": True}, token)
st, r = chamar("DELETE", f"/cardapio-vivo/vivos/{cat2['id']}", token=token)
checar("deixar de ser Cardápio Vivo responde 200", st == 200, (st, r))
st, _r = chamar("GET", f"/publico/cardapio/loja/{U}?cardapio=catering")
checar("e o link dele deixa de abrir", st == 404, st)
_st, lista = chamar("GET", f"/publico/{U}/catalogos")
meu = next((c for c in lista if c.get("id") == ID_CAT), {})
checar("o site recebe qual é o Cardápio Vivo e se é o principal",
       meu.get("cardapio_vivo") is True and meu.get("vivo") == {"slug": "cardapio", "principal": True}, meu)

print("\n12. a porta: Portal desligado, cardápio fechado")
chamar("PUT", f"/unidades/{U}/parametros", {**par, "reservas_ligado": False}, token)
st, _r = chamar("GET", f"/publico/cardapio/mesa/{NOVO}")
checar("com o Portal desligado, a mesa não abre (404)", st == 404, st)
st, _r = chamar("GET", "/cardapio-vivo/config", token=token)
checar("e a configuração recusa com 409", st == 409, st)
chamar("PUT", f"/unidades/{U}/parametros", {**par, "reservas_ligado": True}, token)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
