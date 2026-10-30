"""Os números de WhatsApp da loja (migração 143): vários, um principal.

🔑 **Pedido do dono (30/10/2026):** *"no cadastro de whatsapp nas lojas, poder configurar mais de
um, e tornar um o principal da loja."* Aqui mora a LISTA (rótulo, número, principal). A conexão
de cada número com a Meta (146) é gravada por `services/whatsapp.py`, na aba WhatsApp da loja;
gravar a lista por aqui não mexe nela.

🔑 **`unidades.whatsapp` é o espelho do principal**, mantido AQUI: tudo que já lia o campo (o
"Entre em contato" do site, o termo LGPD) recebe o principal sem mudar uma linha.
🔑 **O número do catálogo** (`catalogos.id_whatsapp`) é um desta lista, da loja DONA do
catálogo; nulo = o principal da loja onde o cliente está. `numero_do_catalogo` é a regra única
que o site, o feed e o pedido usam.
"""

import re

from fastapi import HTTPException


def so_digitos(v: str | None) -> str:
    """O que o `https://wa.me/<numero>` aceita: só dígitos.

    ⚠️ A mesma regra de `publico._so_digitos` (a casa digita com máscara, `(99) 99999-9999`),
    para o botão do catálogo e o "Entre em contato" darem o MESMO link.
    """
    return re.sub(r"\D", "", v or "")


def listar(cur, id_unidade: int) -> list[dict]:
    cur.execute(
        """SELECT id, rotulo, numero, principal FROM unidade_whatsapps
            WHERE id_unidade = %s ORDER BY principal DESC, ordem, id""",
        (id_unidade,),
    )
    return [dict(r) for r in cur.fetchall()]


def listar_varias(cur, ids: list[int]) -> dict[int, list[dict]]:
    if not ids:
        return {}
    cur.execute(
        """SELECT id, id_unidade, rotulo, numero, principal FROM unidade_whatsapps
            WHERE id_unidade = ANY(%s) ORDER BY principal DESC, ordem, id""",
        (ids,),
    )
    por: dict[int, list[dict]] = {i: [] for i in ids}
    for r in cur.fetchall():
        d = dict(r)
        por[d.pop("id_unidade")].append(d)
    return por


def gravar(cur, id_unidade: int, numeros: list[dict]) -> list[dict]:
    """Troca a lista da loja pela que veio, mantendo o id de quem já existia.

    ⚠️ O id importa: é ele que o catálogo (e o aviso, e a mensagem) guarda. Linha que sumiu da
    lista é apagada, e quem a usava volta ao principal (FK `ON DELETE SET NULL`).
    🔑 Lista com números e nenhum principal: o primeiro vira principal — loja com WhatsApp
    precisa de um que responda pelo "Entre em contato".
    """
    gravar_com_ids(cur, id_unidade, numeros)
    return listar(cur, id_unidade)


def gravar_com_ids(cur, id_unidade: int, numeros: list[dict]) -> list[int | None]:
    """Como `gravar`, devolvendo o id de cada linha recebida, NA ORDEM em que veio (None para a
    linha vazia, que é descartada)."""
    limpos = []
    posicoes: list[int | None] = []
    for n in numeros:
        numero = (n.get("numero") or "").strip()
        if not numero:
            if (n.get("phone_number_id") or "").strip():
                raise HTTPException(status_code=422,
                                    detail="Um número conectado à Meta está sem o número: informe-o.")
            posicoes.append(None)
            continue
        if len(re.sub(r"\D", "", numero)) < 10:
            raise HTTPException(status_code=422,
                                detail=f"O WhatsApp “{numero}” está incompleto: use DDD e número.")
        posicoes.append(len(limpos))
        limpos.append({"id": n.get("id"), "rotulo": (n.get("rotulo") or "").strip() or "WhatsApp",
                       "numero": numero, "principal": bool(n.get("principal")),
                       "ordem": len(limpos)})
    if sum(1 for n in limpos if n["principal"]) > 1:
        raise HTTPException(status_code=422, detail="Só um WhatsApp pode ser o principal da loja.")
    vistos = set()
    for n in limpos:
        d = so_digitos(n["numero"])
        if d in vistos:
            raise HTTPException(status_code=422, detail=f"O WhatsApp {n['numero']} está repetido.")
        vistos.add(d)
    if limpos and not any(n["principal"] for n in limpos):
        limpos[0]["principal"] = True

    existentes = {r["id"] for r in listar(cur, id_unidade)}
    ficam = {n["id"] for n in limpos if n["id"] in existentes}
    cur.execute("DELETE FROM unidade_whatsapps WHERE id_unidade = %s AND NOT (id = ANY(%s))",
                (id_unidade, list(ficam)))
    # ⚠️ Tira o principal antes de marcar o novo: o índice único não aceita dois nem por um
    # instante.
    cur.execute("UPDATE unidade_whatsapps SET principal = false WHERE id_unidade = %s", (id_unidade,))
    for n in limpos:
        if n["id"] in ficam:
            cur.execute(
                """UPDATE unidade_whatsapps SET rotulo = %s, numero = %s, principal = %s, ordem = %s
                    WHERE id = %s""",
                (n["rotulo"], n["numero"], n["principal"], n["ordem"], n["id"]),
            )
        else:
            cur.execute(
                """INSERT INTO unidade_whatsapps (id_unidade, rotulo, numero, principal, ordem)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (id_unidade, n["rotulo"], n["numero"], n["principal"], n["ordem"]),
            )
            n["id"] = cur.fetchone()["id"]
    principal = next((n["numero"] for n in limpos if n["principal"]), None)
    cur.execute("UPDATE unidades SET whatsapp = %s WHERE id = %s", (principal, id_unidade))
    return [None if p is None else limpos[p]["id"] for p in posicoes]


def do_catalogo_valido(cur, id_catalogo: int, id_whatsapp: int | None) -> None:
    """O número escolhido no catálogo precisa ser da loja DONA dele."""
    if id_whatsapp is None:
        return
    cur.execute(
        """SELECT 1 FROM unidade_whatsapps w JOIN catalogos c ON c.id_unidade = w.id_unidade
            WHERE w.id = %s AND c.id = %s""",
        (id_whatsapp, id_catalogo),
    )
    if not cur.fetchone():
        raise HTTPException(status_code=422,
                            detail="Esse WhatsApp não é da loja dona do catálogo.")


def numero_do_catalogo(cur, id_catalogo: int, id_unidade: int) -> str | None:
    """Os dígitos do WhatsApp que atende este catálogo NESTA loja.

    O escolhido no catálogo → o principal da loja onde o cliente está (o espelho em
    `unidades.whatsapp`) → o da empresa. Nulo quando ninguém cadastrou nada.
    """
    cur.execute(
        """SELECT w.numero AS do_catalogo, u.whatsapp AS da_loja,
                  (SELECT e.whatsapp FROM empresa e WHERE e.id = 1) AS da_empresa
             FROM unidades u
             LEFT JOIN catalogos c ON c.id = %s
             LEFT JOIN unidade_whatsapps w ON w.id = c.id_whatsapp
            WHERE u.id = %s""",
        (id_catalogo, id_unidade),
    )
    r = cur.fetchone()
    if not r:
        return None
    for v in (r["do_catalogo"], r["da_loja"], r["da_empresa"]):
        d = so_digitos(v)
        if d:
            return d
    return None
