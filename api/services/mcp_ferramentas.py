"""As ferramentas que o Claude enxerga no conector MCP — e como cada uma vira um GET.

🔑 **Cada ferramenta é uma rota que JÁ EXISTE, chamada por dentro.** O `/mcp`
não lê banco nem decide permissão: ele repassa a pergunta à própria API, com a
credencial de quem perguntou (`chamar`). Por isso permissão, loja e setor são
os mesmos da tela, e uma regra nova no Botané vale aqui sem mudar esta tabela.

⚠️ **Só GET, e isso é estrutural, não convenção**: `chamar` só sabe fazer GET,
e a chave do Claude é só de leitura — o servidor recusaria o resto.

Para acrescentar uma ferramenta: uma entrada em `FERRAMENTAS`. O nome dos
parâmetros é o da ROTA (vão direto para a query string), exceto os que aparecem
entre chaves no caminho.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

# ⚠️ Resposta grande demais enche o contexto do Claude e empurra a conversa
# para fora. O corte é aqui, com aviso: o modelo sabe que faltou e pede com
# filtro, em vez de concluir sobre metade da lista achando que é tudo.
LIMITE_CARACTERES = 60_000

ANOTACOES_LEITURA = {"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False}


@dataclass
class Param:
    tipo: str                       # tipo JSON Schema: string, integer, boolean
    descricao: str = ""
    obrigatorio: bool = False
    padrao: Any = None
    enum: list[str] | None = None
    minimo: int | None = None
    maximo: int | None = None


@dataclass
class Ferramenta:
    nome: str
    titulo: str
    descricao: str
    caminho: str
    params: dict[str, Param] = field(default_factory=dict)
    # Vão sempre na query, sem o modelo escolher (ex.: `agrupar=true`).
    fixos: dict[str, Any] = field(default_factory=dict)

    def esquema(self) -> dict:
        props: dict[str, dict] = {}
        for nome, p in {**self.params, "id_loja": _ID_LOJA}.items():
            d: dict[str, Any] = {"type": p.tipo}
            if p.descricao:
                d["description"] = p.descricao
            if p.padrao is not None:
                d["default"] = p.padrao
            if p.enum:
                d["enum"] = p.enum
            if p.minimo is not None:
                d["minimum"] = p.minimo
            if p.maximo is not None:
                d["maximum"] = p.maximo
            props[nome] = d
        obrig = [n for n, p in self.params.items() if p.obrigatorio]
        return {"type": "object", "properties": props, "required": obrig,
                "additionalProperties": False}

    def descritor(self) -> dict:
        return {"name": self.nome, "title": self.titulo, "description": self.descricao,
                "inputSchema": self.esquema(),
                "annotations": {"title": self.titulo, **ANOTACOES_LEITURA}}


_ID_LOJA = Param("integer", "Loja a consultar (id, de `quem_sou`). Sem ele, a loja "
                            "padrão do usuário.")
_DATA = "Data AAAA-MM-DD."


def _lim(padrao: int, maximo: int, minimo: int = 1) -> Param:
    return Param("integer", "Quantos itens trazer.", padrao=padrao, minimo=minimo, maximo=maximo)


_OFFSET = Param("integer", "Quantos pular (paginação).", padrao=0, minimo=0)
_PERIODO = {"inicio": Param("string", _DATA + " Sem ele, o início do período atual da casa."),
            "fim": Param("string", _DATA + " Sem ele, hoje.")}
_ESCOPO = Param("string", "`loja` (a atual) ou `empresa` (todas as lojas).",
                padrao="loja", enum=["loja", "empresa"])

FERRAMENTAS: list[Ferramenta] = [
    Ferramenta(
        "quem_sou", "Quem sou eu no Botané",
        "Quem é o usuário conectado: nome, papéis, permissões e as LOJAS que ele enxerga. "
        "Chame primeiro: as lojas daqui são os valores aceitos em `id_loja`.",
        "/auth/me"),
    Ferramenta(
        "painel_inicio", "Painel inicial",
        "O painel da tela inicial: indicadores do período atual da casa (vendas, CMV, "
        "compras) e o que está pendente.",
        "/inicio"),
    Ferramenta(
        "alertas", "Alertas",
        "O que está pedindo atenção agora (estoque negativo ou abaixo do mínimo, notas "
        "não lançadas, fichas faltando, CMV). Já vem filtrado pelas permissões.",
        "/alertas"),
    Ferramenta(
        "buscar_produtos", "Buscar produtos",
        "Procura produtos por nome, código ou EAN. Devolve o resumo e o total.",
        "/produtos",
        {"busca": Param("string", "Texto: nome, código ou EAN."),
         "tipo": Param("string", "Tipo do produto.",
                       enum=["INSUMO", "REVENDA", "PRODUZIDO", "KIT", "EMBALAGEM",
                             "MATERIAL_LIMPEZA", "UTENSILIO"]),
         "ativo": Param("boolean", "true = só ativos, false = só inativos; omita para todos.",
                        padrao=True),
         "limite": _lim(25, 200), "offset": _OFFSET}),
    Ferramenta(
        "detalhe_produto", "Cadastro de um produto",
        "O cadastro completo de um produto: unidades, conversões, setor, categoria, "
        "fornecedores, códigos.",
        "/produtos/{id_produto}",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True)}),
    Ferramenta(
        "custo_produto", "Custo de um produto",
        "Quanto um produto custa hoje e o que formou esse custo (última compra, média, "
        "ficha, referência).",
        "/produtos/{id_produto}/custo",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True)}),
    Ferramenta(
        "fichas_tecnicas", "Fichas técnicas",
        "Lista as fichas técnicas — uma linha por produto, a versão que vale.",
        "/fichas",
        {"busca": Param("string", "Nome ou código do produto."),
         "id_produto": Param("integer", "Só a ficha deste produto."),
         "limite": _lim(25, 200), "offset": _OFFSET},
        fixos={"agrupar": "true"}),
    Ferramenta(
        "ficha_tecnica", "Uma ficha técnica",
        "Uma ficha técnica inteira: insumos, quantidades, rendimento e custo. O custo só "
        "vem se o usuário puder ver custos de ficha.",
        "/fichas/{id_ficha}",
        {"id_ficha": Param("integer", "Id da ficha (de `fichas_tecnicas`).", obrigatorio=True)}),
    Ferramenta(
        "saldos_estoque", "Saldos de estoque",
        "Saldo em estoque por produto e local, com custo médio.",
        "/estoque/saldos",
        {"busca": Param("string", "Nome ou código do produto."),
         "id_produto": Param("integer", "Só este produto."),
         "apenas_com_saldo": Param("boolean", "Só o que tem saldo.", padrao=False),
         "abaixo_do_minimo": Param("boolean", "Só o que está abaixo do mínimo.", padrao=False),
         "limite": _lim(50, 500), "offset": _OFFSET}),
    Ferramenta(
        "movimentos_estoque", "Movimentos de estoque",
        "O razão do estoque — entradas, saídas, ajustes, produções —, do mais recente. "
        "O razão nunca é editado: correção aparece como estorno.",
        "/estoque/movimentos",
        {"id_produto": Param("integer", "Só este produto."),
         "busca": Param("string", "Nome ou código do produto."),
         "tipo": Param("string", "Tipo do movimento."),
         **_PERIODO, "limite": _lim(50, 500), "offset": _OFFSET}),
    Ferramenta(
        "vencimentos", "Lotes vencendo",
        "Lotes que vencem nos próximos `dias` (sem `dias`, a janela dos parâmetros da loja).",
        "/alertas/vencimentos",
        {"dias": Param("integer", "Janela em dias.", minimo=0, maximo=365)}),
    Ferramenta(
        "notas_entrada", "Notas de compra",
        "Notas de compra (vindas do Omie), da mais recente. Busca por número ou fornecedor.",
        "/notas",
        {"busca": Param("string", "Número da NF ou nome do fornecedor."),
         "status": Param("string", "Situação da nota.",
                         enum=["PENDENTE", "IMPORTADA", "CONCILIADA", "LANCADA"]),
         **_PERIODO, "limite": _lim(25, 200), "offset": _OFFSET}),
    Ferramenta(
        "nota_entrada", "Uma nota de compra",
        "Uma nota de compra com os itens e o produto a que cada item foi ligado.",
        "/notas/{id_nota}",
        {"id_nota": Param("integer", "Id da nota.", obrigatorio=True)}),
    Ferramenta(
        "itens_sem_produto", "Itens de nota sem produto",
        "Itens de nota que ainda não acharam produto — a fila da conciliação.",
        "/notas/pendencias"),
    Ferramenta(
        "vendas", "Vendas",
        "Vendas da loja, da mais recente.",
        "/vendas",
        {**_PERIODO, "busca": Param("string", "Documento ou texto da venda."),
         "limite": _lim(50, 500), "offset": _OFFSET}),
    Ferramenta(
        "cmv_periodos", "Períodos de CMV",
        "Os últimos períodos de CMV da casa (no ritmo dela: semana ou mês) e quais já "
        "estão fechados. Use as datas daqui nas outras ferramentas de CMV.",
        "/cmv/periodos",
        {"quantos": Param("integer", "Quantos períodos.", padrao=12, minimo=1, maximo=60)}),
    Ferramenta(
        "cmv_apuracao", "Apuração do CMV",
        "A apuração do CMV: estoque inicial + compras − estoque final, receita e food "
        "cost. Sem datas, o período atual da casa.",
        "/cmv/apuracao",
        {**_PERIODO, "escopo": _ESCOPO}),
    Ferramenta(
        "cmv_por_grupo", "CMV por grupo",
        "O CMV aberto por setor, categoria, grupo, local, produto ou loja.",
        "/cmv/por-grupo",
        {"agrupar": Param("string", "Como abrir o CMV.", padrao="setor",
                          enum=["setor", "categoria", "grupo", "local", "produto", "loja"]),
         **_PERIODO, "escopo": _ESCOPO}),
    Ferramenta(
        "curva_abc", "Curva ABC",
        "Curva ABC do consumo no período: os insumos que mais pesam no custo.",
        "/cmv/abc",
        {**_PERIODO, "limite": _lim(50, 200, minimo=5)}),
    Ferramenta(
        "margem_pratos", "Margem dos pratos",
        "Margem dos itens vendidos no período: receita, custo e margem por prato.",
        "/cmv/margem",
        {**_PERIODO, "limite": _lim(50, 200, minimo=5)}),
]

POR_NOME = {f.nome: f for f in FERRAMENTAS}

INSTRUCOES = (
    "Sistema de gestão do Botané Deli & Café: produtos, fichas técnicas, estoque, compras "
    "(notas do Omie), vendas e CMV. Acesso SÓ DE LEITURA, com as permissões do usuário "
    "conectado. Dinheiro em reais; quantidades na unidade de estoque do produto; datas "
    "AAAA-MM-DD. Comece por `quem_sou` para saber lojas e permissões. Um erro 403 quer "
    "dizer que o usuário não tem aquela permissão, não que o dado não existe. O CMV "
    "trabalha no PERÍODO da casa: use `cmv_periodos` antes de escolher datas."
)


class ErroFerramenta(Exception):
    """Vira `isError: true` no resultado — o modelo lê a frase e se corrige."""


def _caminho(f: Ferramenta, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    resto = dict(args)
    faltando = [n for n, p in f.params.items() if p.obrigatorio and resto.get(n) is None]
    if faltando:
        raise ErroFerramenta(f"Falta o argumento obrigatório: {', '.join(faltando)}.")
    desconhecidos = set(resto) - set(f.params) - {"id_loja"}
    if desconhecidos:
        raise ErroFerramenta(f"Argumento desconhecido: {', '.join(sorted(desconhecidos))}.")

    def trocar(m: re.Match) -> str:
        valor = resto.pop(m.group(1))
        # ⚠️ Só inteiro entra no caminho: string ali abriria `../` para outra rota.
        if not isinstance(valor, int) or isinstance(valor, bool):
            raise ErroFerramenta(f"`{m.group(1)}` precisa ser um número inteiro.")
        return str(valor)

    caminho = re.sub(r"\{(\w+)\}", trocar, f.caminho)
    return caminho, resto


def _query(valores: dict[str, Any]) -> dict[str, str]:
    q: dict[str, str] = {}
    for k, v in valores.items():
        if v is None or v == "":
            continue
        q[k] = ("true" if v else "false") if isinstance(v, bool) else str(v)
    return q


async def chamar(app, credencial: str, nome: str, args: dict[str, Any] | None) -> str:
    """Executa a ferramenta como um GET na própria API, com a credencial de quem pediu.

    🔑 **Por dentro, sem rede**: `httpx.ASGITransport` entrega o pedido ao app no
    mesmo processo. Passa pelos mesmos middlewares e dependências que um pedido
    da tela — `contexto_atual` confere a chave de novo, e a trava de só leitura
    vale porque é GET.
    """
    f = POR_NOME.get(nome)
    if not f:
        raise ErroFerramenta(f"Ferramenta desconhecida: {nome}")
    caminho, resto = _caminho(f, args or {})
    id_loja = resto.pop("id_loja", None)
    cabecalhos = {"Authorization": f"Bearer {credencial}", "Accept": "application/json"}
    if id_loja is not None:
        cabecalhos["X-Unidade"] = str(id_loja)

    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://botane.interno",
                                 timeout=120) as cliente:
        r = await cliente.get(caminho, params=_query({**f.fixos, **resto}), headers=cabecalhos)

    try:
        dados = r.json()
    except ValueError:
        raise ErroFerramenta(f"A API respondeu {r.status_code} sem JSON.")
    if r.status_code >= 400:
        detalhe = dados.get("detail") if isinstance(dados, dict) else dados
        if isinstance(detalhe, list):   # 422 do FastAPI: diga QUAL argumento
            detalhe = "; ".join(f"{'.'.join(map(str, d.get('loc', [])[1:]))}: {d.get('msg')}"
                                for d in detalhe)
        raise ErroFerramenta(f"{r.status_code}: {detalhe}")

    total = r.headers.get("X-Total")
    if total is not None and isinstance(dados, list):
        dados = {"total": int(total), "nesta_pagina": len(dados), "itens": dados}

    texto = json.dumps(dados, ensure_ascii=False, default=str, separators=(",", ":"))
    if len(texto) > LIMITE_CARACTERES:
        texto = (texto[:LIMITE_CARACTERES] + f"\n…[CORTADO: a resposta tinha {len(texto)} "
                 "caracteres. Refaça com filtro, período menor ou limite menor.]")
    return texto
