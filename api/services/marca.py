"""O nome que aparece: o da CASA, lido do cadastro — nunca escrito no código.

🔑 **Pedido do dono (05/10/2026):** o sistema nasceu para uma casa e passou a ser
levado a outras do mesmo ramo. Até aqui o nome dela estava escrito em dezenas de
lugares (login, e-mail, página do conector, rodapé de relatório), e cada um
deles mostraria a marca de OUTRA empresa para o cliente novo.

Duas palavras, e só duas:

* **a casa** — `nome_da_casa(cur)`: nome fantasia, senão razão social, do
  cadastro em Administração ▸ Empresa;
* **o sistema** — `SISTEMA`: como o produto se chama quando o assunto é ele
  mesmo ("entre no sistema", "o sistema só lê do Omie"). ⚠️ É genérico de
  propósito: o produto ainda não tem nome próprio, e quando tiver ele troca
  AQUI (e em `web/lib/marca.ts`), não em quarenta arquivos.
"""
from __future__ import annotations

from database import get_cursor

SISTEMA = "Sistema de gestão"


def nome_da_casa(cur, padrao: str = SISTEMA) -> str:
    """O nome da casa, ou `padrao` enquanto o cadastro estiver em branco.

    ⚠️ O `padrao` existe porque quem fala com o CLIENTE da casa (site, WhatsApp,
    cartão de fidelidade) não pode dizer "Sistema de gestão" — ali o chamador
    passa uma frase que faça sentido para quem está do lado de fora.
    """
    cur.execute("SELECT nome_fantasia, razao_social FROM empresa WHERE id = 1")
    e = cur.fetchone() or {}
    return (e.get("nome_fantasia") or "").strip() or (e.get("razao_social") or "").strip() or padrao


def casa(padrao: str = SISTEMA) -> str:
    """`nome_da_casa` para quem não tem cursor na mão (página HTML, e-mail de teste)."""
    with get_cursor() as cur:
        return nome_da_casa(cur, padrao)


def publica(cur) -> dict:
    """O que a tela de ENTRADA pode mostrar antes de alguém se identificar.

    ⚠️ **Só nome e logo.** É rota pública: nada de CNPJ, endereço ou contato —
    quem ainda não entrou só precisa saber de quem é a porta.
    """
    cur.execute("SELECT nome_fantasia, razao_social, logo_url FROM empresa WHERE id = 1")
    e = cur.fetchone() or {}
    nome = (e.get("nome_fantasia") or "").strip() or (e.get("razao_social") or "").strip()
    return {"nome": nome or None, "logo_url": e.get("logo_url"), "sistema": SISTEMA}
