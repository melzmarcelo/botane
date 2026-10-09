"""As ferramentas que o Claude enxerga no conector MCP — e como cada uma vira um GET.

🔑 **Cada ferramenta é uma rota que JÁ EXISTE, chamada por dentro.** O `/mcp`
não lê banco nem decide permissão: ele repassa a pergunta à própria API, com a
credencial de quem perguntou (`chamar`). Por isso permissão, loja e setor são
os mesmos da tela, e uma regra nova no Botané vale aqui sem mudar esta tabela.

⚠️ **A maioria é GET, e a escrita é a exceção declarada.** Ferramenta com
`metodo` diferente de GET só aparece — e só funciona — para chave marcada como
"permite alterar" na tela de Usuários. Quem barra é o servidor, em
`contexto_da_credencial`: a lista escondida é conforto, não segurança.

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
# ⚠️ `destructiveHint` LIGADO em tudo que grava, inclusive no que "só corrige um
# campo": é o que faz o Claude perguntar antes de fazer. Nenhuma gravação daqui
# é idempotente — chamar duas vezes é gravar duas vezes.
ANOTACOES_ESCRITA = {"readOnlyHint": False, "destructiveHint": True,
                     "idempotentHint": False, "openWorldHint": False}


@dataclass
class Param:
    tipo: str                       # tipo JSON Schema: string, integer, boolean
    descricao: str = ""
    obrigatorio: bool = False
    padrao: Any = None
    enum: list[str] | None = None
    minimo: int | None = None
    maximo: int | None = None
    # Vai no CORPO em JSON, e não na query. Só nas ferramentas que gravam.
    no_corpo: bool = False
    # O esquema de cada item, quando `tipo` é "array" (os fornecedores do produto).
    itens: dict | None = None


@dataclass
class Ferramenta:
    nome: str
    titulo: str
    descricao: str
    caminho: str
    params: dict[str, Param] = field(default_factory=dict)
    # Vão sempre na query, sem o modelo escolher (ex.: `agrupar=true`).
    fixos: dict[str, Any] = field(default_factory=dict)
    metodo: str = "GET"

    @property
    def grava(self) -> bool:
        return self.metodo != "GET"

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
            if p.itens is not None:
                d["items"] = p.itens
            props[nome] = d
        obrig = [n for n, p in self.params.items() if p.obrigatorio]
        return {"type": "object", "properties": props, "required": obrig,
                "additionalProperties": False}

    def descritor(self) -> dict:
        anotacoes = ANOTACOES_ESCRITA if self.grava else ANOTACOES_LEITURA
        return {"name": self.nome, "title": self.titulo, "description": self.descricao,
                "inputSchema": self.esquema(),
                "annotations": {"title": self.titulo, **anotacoes}}


# 🔑 **Uma linha da receita**, com o mesmo contrato de `models.fichas.ItemFicha`.
# ⚠️ `id_insumo` OU `id_subficha`, nunca os dois — a rota recusa com 400.
_ITEM_DA_FICHA = {
    "type": "object",
    "properties": {
        "id_insumo": {"type": "integer",
                      "description": "O ingrediente (de `buscar_produtos`)."},
        "id_subficha": {"type": "integer",
                        "description": "Ou uma preparação com ficha própria "
                                       "(de `fichas_tecnicas`)."},
        "qtd_bruta": {"type": "number", "description": "Quantidade usada, maior que zero."},
        "qtd_liquida": {"type": "number",
                        "description": "Depois de limpar/descascar, se o arquivo disser. "
                                       "Com as duas, o fator de correção é calculado."},
        "um": {"type": "string", "description": "Unidade da quantidade (G, KG, ML, UN…)."},
        "fator_correcao": {"type": "number", "description": "Bruta ÷ líquida. Padrão 1."},
        "fator_coccao": {"type": "number", "description": "Perda no cozimento. Padrão 1."},
        "observacao": {"type": "string"}},
    "required": ["qtd_bruta"],
}


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
        "quem_sou", "Quem sou eu no sistema",
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
        "custos_de_referencia_suspeitos", "Custos de referência suspeitos",
        "Produtos custeados pela referência (a que veio do Omie) cujo número não bate com "
        "o custo registrado no estoque ou passa do preço de venda — com o custo sugerido.",
        "/ajustes/custo-referencia/previa", {}),
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
                         enum=["PENDENTE", "IMPORTADA", "CONCILIADA", "LANCADA", "CANCELADA"]),
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

    # ------------------------------------------------------------- produção
    Ferramenta(
        "agenda_producao", "Agenda de produção",
        "O que está planejado, em andamento e feito na produção, por período.",
        "/producao-agenda",
        {**_PERIODO, "status": Param("string", "Situação da linha da agenda.")}),
    Ferramenta(
        "item_da_agenda", "Uma linha da agenda",
        "Uma linha da agenda de produção, com a ficha e o que ela consome.",
        "/producao-agenda/{id_agenda}",
        {"id_agenda": Param("integer", "Id da linha.", obrigatorio=True)}),
    Ferramenta(
        "necessario_para_produzir", "O que falta para produzir",
        "Quanto de cada insumo uma produção consumiria, e o que falta em estoque.",
        "/producao-agenda/necessario",
        {"id_produto": Param("integer", "Produto a produzir.", obrigatorio=True),
         "quantidade": Param("number", "Quanto produzir.", obrigatorio=True),
         # ⚠️ O enum dizia `PORCOES`/`RENDIMENTO` e a rota só entendia
         # `PORCOES`/`RECEITAS`: `RENDIMENTO` caía calado no ramo de porções.
         "medida": Param("string", "A quantidade está em quê: PORCOES é a unidade de "
                                   "estoque do produto, RECEITAS são voltas inteiras da "
                                   "ficha, RENDIMENTO é a unidade em que a receita rende "
                                   "(5 KG de uma receita de 10 KG).", padrao="PORCOES",
                         enum=["PORCOES", "RECEITAS", "RENDIMENTO"]),
         "id_local": Param("integer", "Prateleira de onde sairiam os insumos."),
         "id_modo": Param("integer", "Modo de rendimento da ficha, se houver mais de um.")}),
    Ferramenta(
        "producoes_feitas", "Produções feitas",
        "As produções já lançadas, da mais recente — com o que saiu e o custo do produzido.",
        "/estoque/producoes",
        {"limite": _lim(50, 200), "offset": _OFFSET}),

    # ------------------------------------------------------------- inventário
    Ferramenta(
        "inventarios", "Inventários",
        "As contagens de estoque da loja, da mais recente.",
        "/inventarios",
        {"limite": _lim(25, 500), "offset": _OFFSET}),
    Ferramenta(
        "inventario", "Um inventário",
        "Uma contagem inteira: o que foi contado, o que divergiu e em que pé está.",
        "/inventarios/{id_inventario}",
        {"id_inventario": Param("integer", "Id da contagem.", obrigatorio=True)}),

    # ------------------------------------------------------------- remessas e ajustes
    Ferramenta(
        "transferencias", "Transferências entre lojas",
        "As remessas entre lojas, da mais recente.",
        "/transferencias",
        {"status": Param("string", "Situação da remessa."),
         "limite": _lim(25, 200), "offset": _OFFSET}),
    Ferramenta(
        "transferencia", "Uma transferência",
        "Uma remessa com os itens, quem enviou e quem recebeu.",
        "/transferencias/{id_transferencia}",
        {"id_transferencia": Param("integer", "Id da remessa.", obrigatorio=True)}),
    Ferramenta(
        "lotes_de_ajuste", "Ajustes em lote",
        "Os ajustes feitos em lote — de saldo (ESTOQUE) ou de custo (CUSTO).",
        "/ajustes/lotes",
        {"natureza": Param("string", "Tipo do lote.", enum=["ESTOQUE", "CUSTO"]),
         "limite": _lim(25, 200), "offset": _OFFSET}),

    # ------------------------------------------------------------- consumo
    Ferramenta(
        "consumo_periodos", "Períodos de consumo",
        "Os períodos de consumo da casa (o que a equipe consumiu e o que será cobrado).",
        "/consumo/periodos"),
    Ferramenta(
        "consumo_periodo", "Um período de consumo",
        "Um período de consumo aberto por pessoa, com o cheio, o desconto e o a cobrar.",
        "/consumo/periodos/{id_periodo}",
        {"id_periodo": Param("integer", "Id do período.", obrigatorio=True)}),
    Ferramenta(
        "meu_consumo", "O meu consumo",
        "O consumo da própria pessoa conectada no período aberto.",
        "/consumo/meu"),
    Ferramenta(
        "consumo_por_pessoa", "Consumo por pessoa",
        "O que cada pessoa consumiu no período: sintético (totais) ou analítico (item a item).",
        "/vendas/por-pessoa",
        {"id_periodo": Param("integer", "Período; sem ele, o aberto."),
         "id_pessoa": Param("integer", "Só esta pessoa."),
         "detalhe": Param("string", "Nível do detalhe.", padrao="sintetico",
                          enum=["sintetico", "analitico"])}),

    # ------------------------------------------------------------- pessoas
    Ferramenta(
        "buscar_pessoas", "Buscar pessoas e fornecedores",
        "Procura no cadastro de pessoas — quem fornece, quem trabalha e quem consome.",
        "/fornecedores",
        {"busca": Param("string", "Nome, apelido, CNPJ ou CPF."),
         "so_fornecedores": Param("boolean", "true = só fornecedores; false = só os demais."),
         "incluir_inativos": Param("boolean", "Trazer também os inativos.", padrao=False),
         "limite": _lim(25, 200), "offset": _OFFSET}),
    Ferramenta(
        "detalhe_pessoa", "Uma pessoa",
        "O cadastro completo de uma pessoa ou fornecedor.",
        "/fornecedores/{id_fornecedor}",
        {"id_fornecedor": Param("integer", "Id da pessoa.", obrigatorio=True)}),
    Ferramenta(
        "produtos_da_pessoa", "O que a pessoa fornece",
        "Os produtos ligados a esta pessoa, e por quanto da última vez.",
        "/fornecedores/{id_fornecedor}/produtos",
        {"id_fornecedor": Param("integer", "Id da pessoa.", obrigatorio=True)}),

    # ------------------------------------------------------------- tabelas de apoio
    Ferramenta(
        "setores", "Setores",
        "Os setores da casa (cozinha, bar, vitrine…) — o recorte de quem produz e conta.",
        "/setores",
        {"incluir_inativos": Param("boolean", "Trazer também os inativos.", padrao=False)}),
    Ferramenta(
        "locais", "Locais de estoque",
        "As prateleiras e câmaras onde o estoque mora.",
        "/locais",
        {"incluir_inativos": Param("boolean", "Trazer também os inativos.", padrao=False),
         "todas_lojas": Param("boolean", "De todas as lojas, não só da atual.", padrao=False)}),
    Ferramenta(
        "categorias", "Categorias",
        "A árvore de categorias dos produtos.",
        "/categorias",
        {"incluir_inativas": Param("boolean", "Trazer também as inativas.", padrao=False)}),
    Ferramenta(
        "unidades_medida", "Unidades de medida",
        "As unidades de medida cadastradas e como convertem entre si.",
        "/unidades-medida",
        {"incluir_inativas": Param("boolean", "Trazer também as inativas.", padrao=False)}),

    # ------------------------------------------------------------- estoque, segunda camada
    Ferramenta(
        "saldos_agrupados", "Saldos somados por produto",
        "O saldo de cada produto somando as prateleiras da loja — uma linha por produto.",
        "/estoque/saldos-agrupados",
        {"busca": Param("string", "Nome ou código do produto."),
         "id_produto": Param("integer", "Só este produto."),
         "id_setor": Param("integer", "Só os produtos deste setor."),
         "apenas_com_saldo": Param("boolean", "Só o que tem saldo.", padrao=False),
         "abaixo_do_minimo": Param("boolean", "Só o que está abaixo do mínimo.", padrao=False),
         "limite": _lim(50, 500), "offset": _OFFSET}),
    Ferramenta(
        "saldos_na_rede", "Saldos em todas as lojas",
        "O saldo de cada produto loja a loja — a visão da rede, não só da loja atual.",
        "/estoque/saldos-rede",
        {"busca": Param("string", "Nome ou código do produto."),
         "id_produto": Param("integer", "Só este produto."),
         "apenas_com_saldo": Param("boolean", "Só o que tem saldo.", padrao=False),
         "abaixo_do_minimo": Param("boolean", "Só o que está abaixo do mínimo.", padrao=False),
         "limite": _lim(50, 500), "offset": _OFFSET}),
    Ferramenta(
        "lotes_de_estoque", "Lotes",
        "Os lotes em estoque, com validade e quantidade.",
        "/estoque/lotes",
        {"id_produto": Param("integer", "Só este produto."),
         "incluir_zerados": Param("boolean", "Trazer os já consumidos.", padrao=False),
         "incluir_inativos": Param("boolean", "Trazer produtos inativos.", padrao=False)}),

    # ------------------------------------------------------------- CMV, segunda camada
    Ferramenta(
        "cmv_memoria", "Memória de cálculo do CMV",
        "Linha a linha, como o CMV do período foi formado — de onde veio cada valor.",
        "/cmv/memoria",
        {**_PERIODO, "limite": _lim(200, 2000, minimo=10)}),
    Ferramenta(
        "cmv_movimentacao", "Movimentação do período",
        "Por produto: o que tinha, o que entrou, o que saiu e o que sobrou. Diz se o "
        "período está congelado (fechado) ou calculado na hora (aberto).",
        "/cmv/movimentacao",
        _PERIODO),
    Ferramenta(
        "o_que_subiu_de_preco", "O que subiu de preço",
        "Os insumos que mudaram de preço no período, do que mais pesou para o que menos.",
        "/cmv/precos",
        {**_PERIODO, "limite": _lim(40, 200, minimo=5)}),
    Ferramenta(
        "preco_do_produto", "Histórico de preço de um produto",
        "Como o preço de compra de um produto andou ao longo do tempo.",
        "/cmv/precos/{id_produto}",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True)}),
    Ferramenta(
        "grupos_de_cmv", "Grupos de CMV",
        "Os grupos com que a casa lê o CMV (o recorte próprio dela).",
        "/cmv/grupos"),
    Ferramenta(
        "fechamentos_de_cmv", "Fechamentos",
        "Os períodos de CMV já fechados, com quem fechou e quando.",
        "/cmv/fechamentos"),

    # ------------------------------------------------------------- vendas e notas
    Ferramenta(
        "venda", "Uma venda",
        "Uma venda com os itens, o documento e o que cada item baixou do estoque.",
        "/vendas/{id_venda}",
        {"id_venda": Param("integer", "Id da venda.", obrigatorio=True)}),
    Ferramenta(
        "vendas_sem_vinculo", "Itens vendidos sem produto",
        "Itens que o PDV vendeu e que não estão ligados a nenhum produto — furo no CMV.",
        "/vendas/sem-vinculo",
        {"busca": Param("string", "Texto do item.")}),
    Ferramenta(
        "vinculos_de_notas", "De-para dos fornecedores",
        "Os vínculos entre o que o fornecedor chama e o produto da casa.",
        "/notas/vinculos"),

    # ------------------------------------------------------------- a casa
    Ferramenta(
        "empresa", "A empresa",
        "Os dados da empresa (razão social, CNPJ, endereço).",
        "/empresa"),
    Ferramenta(
        "lojas", "As lojas",
        "As lojas da casa, com apelido e qual é a matriz.",
        "/unidades",
        {"incluir_inativas": Param("boolean", "Trazer também as inativas.", padrao=False)}),
    Ferramenta(
        "parametros_da_loja", "Parâmetros de uma loja",
        "Como a loja trabalha: ciclo do CMV, alerta de validade, casas decimais e afins.",
        "/unidades/{id_unidade}/parametros",
        {"id_unidade": Param("integer", "Id da loja.", obrigatorio=True)}),
    Ferramenta(
        "auditoria", "Histórico de alterações",
        "Quem mudou o quê no sistema, do mais recente.",
        "/auditoria",
        {"entidade": Param("string", "Só desta entidade (ex.: produto, venda, usuario)."),
         "limite": _lim(50, 500), "offset": _OFFSET}),

    # ------------------------------------------------------------- reservas
    Ferramenta(
        "agenda_de_reservas", "Reservas do dia",
        "O dia inteiro de reservas, como a recepção olha.",
        "/reservas/agenda",
        {"data": Param("string", _DATA, obrigatorio=True)}),
    Ferramenta(
        "disponibilidade_de_reserva", "Horários livres",
        "Os horários com mesa livre num dia, para um número de pessoas.",
        "/reservas/disponibilidade",
        {"data": Param("string", _DATA, obrigatorio=True),
         "pessoas": Param("integer", "Quantas pessoas.", obrigatorio=True,
                          minimo=1, maximo=99)}),
    Ferramenta(
        "saloes_e_mesas", "Salões e mesas",
        "Os salões da casa e as mesas de cada um, com a lotação.",
        "/reservas/salao"),
    Ferramenta(
        "bloqueios_de_reserva", "Bloqueios",
        "Os dias e horários em que a casa não aceita reserva.",
        "/reservas/bloqueios"),

    Ferramenta(
        "produtos_duplicados", "Cadastros repetidos",
        "Cadastros ATIVOS com exatamente o mesmo nome — os candidatos a fusão. Isto "
        "DETECTA; quem decide é gente: o mesmo nome pode ser coisa diferente (três "
        "\"VALE-PRESENTE\" de valores diferentes), e nomes longos saem aparados do Omie. "
        "Para pares que o nome não pega (grafia diferente, abreviação), use "
        "`buscar_produtos` e compare.",
        "/produtos/duplicados",
        {"so_do_omie": Param("boolean", "Só os que vieram do Omie.", padrao=False),
         "limite": _lim(300, 1000)}),
    Ferramenta(
        "previa_de_fusao", "O que a fusão faria",
        "Mostra, ANTES de fundir: com que nome o produto fica, que campos são completados, "
        "quantos itens de venda mudam de dono e — quando não dá — o que exatamente trava. "
        "Chame sempre antes de `fundir_produtos`: fusão não tem desfazer.",
        "/produtos/{id_produto}/vincular/previa",
        {"id_produto": Param("integer", "O cadastro que FICA.", obrigatorio=True),
         "id_sai": Param("integer", "O cadastro que SAI (o sem história).",
                         obrigatorio=True)}),

    # ================================================================ GRAVAÇÃO
    # ⚠️ Daqui para baixo, tudo ALTERA o sistema. Só aparece para chave marcada
    # como "permite alterar", e cada uma passa pela mesma rota da tela: as regras
    # de negócio, as recusas e a auditoria são as mesmas.
    Ferramenta(
        "vincular_item_de_nota", "Ligar item de nota a um produto",
        "Diz de que produto é uma linha da nota — serve para ligar o pendente e para "
        "TROCAR o que está ligado errado. Com `aprender`, o fornecedor passa a cair "
        "sozinho nesse produto nas próximas notas.",
        "/notas/itens/{id_item}/vincular",
        {"id_item": Param("integer", "Id do item da nota (de `itens_sem_produto` ou "
                                     "`nota_entrada`).", obrigatorio=True),
         "id_produto": Param("integer", "Produto da casa.", obrigatorio=True, no_corpo=True),
         "fator": Param("number", "Quantos da unidade de estoque cabem em 1 da nota "
                                  "(ex.: caixa com 12 → 12).", no_corpo=True),
         "aprender": Param("boolean", "Gravar o de-para deste fornecedor.", padrao=True,
                           no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "ignorar_item_de_nota", "Marcar item como fora do estoque",
        "Item que a casa não controla em estoque (serviço, descartável avulso). Sai da "
        "fila de conciliação e não entra no razão.",
        "/notas/itens/{id_item}/ignorar",
        {"id_item": Param("integer", "Id do item da nota.", obrigatorio=True)},
        metodo="POST"),
    Ferramenta(
        "criar_produto_do_item", "Criar produto a partir do item da nota",
        "Cria o cadastro que falta usando o que a nota já diz, e liga o item a ele. "
        "⚠️ Confira antes se o produto não existe com outro nome: `buscar_produtos`.",
        "/notas/itens/{id_item}/criar-produto",
        {"id_item": Param("integer", "Id do item da nota.", obrigatorio=True),
         "nome": Param("string", "Nome do produto; sem ele, o da nota.", no_corpo=True),
         "tipo": Param("string", "Tipo do produto.", padrao="INSUMO", no_corpo=True,
                       enum=["INSUMO", "REVENDA", "PRODUZIDO", "KIT", "EMBALAGEM",
                             "MATERIAL_LIMPEZA", "UTENSILIO"]),
         "um_estoque": Param("string", "Unidade de estoque; sem ela, a da nota.",
                             no_corpo=True),
         "fator": Param("number", "Quantos da unidade de estoque cabem em 1 da nota.",
                        no_corpo=True),
         "substituir": Param("boolean", "Criar mesmo o item já estando ligado a outro "
                                        "produto (diga que é de propósito).",
                             padrao=False, no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "criar_produto", "Criar produto",
        "Cria um produto no cadastro. ⚠️ Procure antes (`buscar_produtos`): dois cadastros "
        "do mesmo insumo partem o custo médio em dois, e produto criado não se apaga — "
        "só se desativa.",
        "/produtos",
        {"nome": Param("string", "Nome do produto.", obrigatorio=True, no_corpo=True),
         "tipo": Param("string", "Tipo do produto.", padrao="INSUMO", no_corpo=True,
                       enum=["INSUMO", "REVENDA", "PRODUZIDO", "KIT", "EMBALAGEM",
                             "MATERIAL_LIMPEZA", "UTENSILIO"]),
         "um_estoque": Param("string", "Unidade de estoque (de `unidades_medida`).",
                             no_corpo=True),
         "id_categoria": Param("integer", "Categoria (de `categorias`).", no_corpo=True),
         "id_setor": Param("integer", "Setor (de `setores`).", no_corpo=True),
         "controla_estoque": Param("boolean", "Controla saldo.", padrao=True, no_corpo=True),
         "estoque_minimo": Param("number", "Mínimo para o alerta.", no_corpo=True),
         "estoque_maximo": Param("number", "Máximo de referência.", no_corpo=True),
         "codigo_barras": Param("string", "EAN.", no_corpo=True),
         "marca": Param("string", "Marca.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "atualizar_produto", "Corrigir o cadastro de um produto",
        # 🔑 **Todos os campos que a tela edita** (pedido do dono, 23/09/2026: *"permitir
        # a marcação de Controla Estoque. Pode liberar ajuste em todos os campos
        # editáveis do produto."*). A unidade de estoque e o fator de compra estavam
        # fora desde 20/09 porque convertem custo e saldo; entram agora porque a ROTA
        # já não deixa a conversão passar calada — o salto de custo volta 409 com os
        # dois números, e só um `confirmar_troca_de_unidade` explícito grava. É a mesma
        # porta da tela, que é o princípio das ferramentas de escrita.
        # ⚠️ A FOTO continua fora: é multipart, e o conector só fala JSON.
        "Altera só os campos informados — todos os que a tela de produto edita. Leia "
        "`detalhe_produto` antes. ⚠️ Trocar a UNIDADE de estoque (`um_estoque`) CONVERTE "
        "custo, mínimo, máximo e fatores: quando o custo dá um salto, o servidor recusa com "
        "os dois números — mostre-os à pessoa e só reenvie com `confirmar_troca_de_unidade` "
        "se ela disser sim. Quando ele não souber a relação entre as unidades, pede "
        "`fator_troca_unidade`. ⚠️ `fornecedores` SUBSTITUI a lista inteira. ⚠️ Desligar "
        "`controla_estoque` tira o produto do razão: as entradas e baixas seguintes deixam "
        "de mexer no saldo.",
        "/produtos/{id_produto}",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True),
         # --- identificação
         "codigo": Param("string", "Código interno (único).", no_corpo=True),
         "nome": Param("string", "Nome.", no_corpo=True),
         "nome_curto": Param("string", "Nome curto (cupom, etiqueta).", no_corpo=True),
         "tipo": Param("string", "Tipo do produto.", no_corpo=True,
                       enum=["INSUMO", "REVENDA", "PRODUZIDO", "KIT", "EMBALAGEM",
                             "MATERIAL_LIMPEZA", "UTENSILIO"]),
         "id_categoria": Param("integer", "Categoria (de `categorias`).", no_corpo=True),
         "id_setor": Param("integer", "Setor (de `setores`).", no_corpo=True),
         "status": Param("string", "Situação do cadastro.", no_corpo=True,
                         enum=["RASCUNHO", "ATIVO", "ARQUIVADO"]),
         "ativo": Param("boolean", "Ativo nas buscas e telas. Produto não se exclui: "
                                   "se desativa.", no_corpo=True),
         "confirmar_reativacao": Param("boolean", "Resposta ao 409 de reativar um cadastro "
                                                  "absorvido numa fusão. Só com o sim da "
                                                  "pessoa.", no_corpo=True),
         # --- estoque
         "controla_estoque": Param("boolean", "Controla saldo no estoque.", no_corpo=True),
         "um_estoque": Param("string", "Unidade de estoque (de `unidades_medida`). "
                                       "Converte custo e saldo — ver a descrição.",
                             no_corpo=True),
         "fator_troca_unidade": Param("number", "Quantos da unidade NOVA vale 1 da antiga, "
                                                "quando o servidor pedir.", no_corpo=True),
         "confirmar_troca_de_unidade": Param("boolean", "Resposta ao 409 do salto de custo "
                                                        "na troca de unidade. Só com o sim "
                                                        "da pessoa.", no_corpo=True),
         "um_compra": Param("string", "Unidade em que se compra.", no_corpo=True),
         "fator_compra": Param("number", "Quantos da unidade de estoque vêm em 1 da de "
                                         "compra.", no_corpo=True),
         "id_local_padrao": Param("integer", "Prateleira padrão (de `locais`).",
                                  no_corpo=True),
         "id_local_venda": Param("integer", "De onde a venda baixa (de `locais`).",
                                 no_corpo=True),
         "estoque_minimo": Param("number", "Mínimo para o alerta.", no_corpo=True),
         "estoque_maximo": Param("number", "Máximo de referência.", no_corpo=True),
         "perecivel": Param("boolean", "É perecível.", no_corpo=True),
         "validade_dias": Param("integer", "Validade em dias.", no_corpo=True,
                                minimo=0, maximo=3650),
         "controla_lote": Param("boolean", "Controla lote.", no_corpo=True),
         "controla_validade": Param("boolean", "Controla validade.", no_corpo=True),
         # --- produção
         "producao_propria": Param("boolean", "A casa produz este item.", no_corpo=True),
         "modo_producao": Param("string", "PARA_ESTOQUE produz e guarda; NA_HORA a venda "
                                          "produz e baixa junto.", no_corpo=True,
                                enum=["PARA_ESTOQUE", "NA_HORA"]),
         # --- venda e catálogo
         "preco_venda": Param("number", "Preço de venda da casa.", no_corpo=True),
         "nome_catalogo": Param("string", "Nome como o CLIENTE lê no cardápio do site.",
                                no_corpo=True),
         "informacao_adicional": Param("string", "Texto para o cliente no cardápio (não é "
                                                 "a observação interna).", no_corpo=True),
         # --- fiscal e integrações
         "codigo_barras": Param("string", "EAN.", no_corpo=True),
         "marca": Param("string", "Marca.", no_corpo=True),
         "ncm": Param("string", "NCM.", no_corpo=True),
         "cest": Param("string", "CEST.", no_corpo=True),
         "peso_liquido": Param("number", "Peso líquido.", no_corpo=True),
         "peso_bruto": Param("number", "Peso bruto.", no_corpo=True),
         "codigo_omie": Param("string", "Código no Omie.", no_corpo=True),
         "codigo_pdv": Param("string", "Código no PDV Legal.", no_corpo=True),
         "integrado_pdv": Param("boolean", "Integrado ao PDV Legal.", no_corpo=True),
         "observacao": Param("string", "Recado interno, para quem trabalha na casa.",
                             no_corpo=True),
         "fornecedores": Param(
             "array", "De quem se compra. SUBSTITUI a lista inteira: mande os que ficam "
                      "junto com o novo.", no_corpo=True,
             itens={"type": "object",
                    "properties": {
                        "id_fornecedor": {"type": "integer",
                                          "description": "Id (de `buscar_pessoas`)."},
                        "codigo_no_fornecedor": {"type": "string"},
                        "embalagem": {"type": "string"},
                        "fator": {"type": "number",
                                  "description": "Unidades de estoque por embalagem."},
                        "ultimo_preco": {"type": "number"},
                        "preferencial": {"type": "boolean"}},
                    "required": ["id_fornecedor"]})},
        metodo="PUT"),
    # -----------------------------------------------------------------------
    # As tabelas em volta do produto
    # -----------------------------------------------------------------------
    # 🔑 **Pedido do dono (26/09/2026):** *"liberar as opções do produto em tabelas
    # periféricas, como onde o produto está, para vincular mais de uma prateleira,
    # unidades de conversão quando há produtos vinculados, permitir desativar o
    # produto."* Cada uma é a MESMA rota que a tela de produto usa — regra, trava e
    # auditoria vêm junto.
    Ferramenta(
        "locais_do_produto", "Onde o produto está",
        "As prateleiras onde o produto mora NA LOJA, com o saldo de cada uma (e o custo, "
        "para quem pode ver). Um produto pode morar em várias.",
        "/produtos/{id_produto}/locais",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True)}),
    # 🔑 **Pedido do dono (05/10/2026):** *"adicionar reprocessar e transferência ao
    # conector"*. Depois da nota 6947 lançada com data retroativa, o acerto era
    # reprocessar quatro produtos e devolver 6 KG a uma prateleira — e o conector
    # só sabia LER as duas coisas.
    # ⚠️ **São as rotas da tela, com as travas dela**: permissão
    # (`estoque.transferencias`, `estoque.custo`), período fechado e o razão
    # append-only continuam sendo decididos pelo servidor.
    Ferramenta(
        "transferir_estoque", "Transferir entre prateleiras",
        "Move uma quantidade de um produto de uma prateleira para outra (de `locais`). "
        "Na MESMA loja entra na hora: dois movimentos no razão, saída e entrada pelo mesmo "
        "custo, sem mudar o valor do estoque. Entre LOJAS vira remessa, que o destino "
        "precisa receber. ⚠️ O razão não se apaga: desfazer é outra transferência no "
        "sentido contrário. Confira o saldo antes em `saldos_estoque`.",
        "/estoque/transferencias",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True, no_corpo=True),
         "quantidade": Param("number", "Quanto mover, na unidade de estoque do produto. "
                                       "Maior que zero.", obrigatorio=True, no_corpo=True),
         "id_local_origem": Param("integer", "De onde sai (de `locais`).",
                                  obrigatorio=True, no_corpo=True),
         "id_local_destino": Param("integer", "Para onde vai (de `locais`).",
                                   obrigatorio=True, no_corpo=True),
         "observacao": Param("string", "Por que está sendo movido.", no_corpo=True)},
        metodo="POST"),
    # ------------------------------------------- lote 3: vendas, preços e CMV
    # 🔑 Terceiro lote do pedido de 09/10/2026.
    Ferramenta(
        "lancar_vendas", "Lançar vendas",
        "Lança uma ou mais vendas (cupons): cada item baixa o estoque e congela o custo do "
        "dia; produto feito NA HORA é produzido junto. ⚠️ Venda que vem do PDV entra "
        "sozinha pela integração — lançar aqui a mesma venda duplica a baixa. O "
        "`documento` é o que impede a repetição: a mesma loja e origem não aceitam o "
        "mesmo documento duas vezes. Confirme os itens com a pessoa antes.",
        "/vendas/importar",
        {"vendas": Param(
            "array", "As vendas a lançar.", obrigatorio=True, no_corpo=True,
            itens={"type": "object",
                   "properties": {
                       "data": {"type": "string", "description": "Dia AAAA-MM-DD."},
                       "hora": {"type": "string", "description": "HH:MM:SS, se souber."},
                       "documento": {"type": "string",
                                     "description": "Número do cupom ou da comanda."},
                       "canal": {"type": "string",
                                 "description": "SALAO, BALCAO, DELIVERY ou EVENTO."},
                       "origem": {"type": "string", "description": "Use MANUAL."},
                       "desconto": {"type": "number", "description": "Desconto do cupom."},
                       "id_pessoa": {"type": "integer",
                                     "description": "Quem consumiu (de `buscar_pessoas`), "
                                                    "quando é consumo de pessoa da casa."},
                       "consumo_interno": {"type": "boolean",
                                           "description": "Consumo da casa, não venda."},
                       "itens": {"type": "array", "items": {
                           "type": "object",
                           "properties": {
                               "id_produto": {"type": "integer"},
                               "quantidade": {"type": "number"},
                               "valor_unitario": {"type": "number",
                                                  "description": "Preço cobrado."}},
                           "required": ["id_produto", "quantidade"]}}},
                   "required": ["data", "itens"]})},
        metodo="POST"),
    Ferramenta(
        "cancelar_venda", "Cancelar uma venda",
        "Cancela a venda: a baixa de estoque volta como estorno e, se ela produziu na hora, "
        "a produção é desfeita junto. A venda continua no histórico, marcada como "
        "cancelada. ⚠️ Não se desfaz.",
        "/vendas/{id_venda}",
        {"id_venda": Param("integer", "Id da venda (de `vendas`).", obrigatorio=True)},
        metodo="DELETE"),
    Ferramenta(
        "previa_vendas_sem_baixa", "Vendas que não saíram do estoque",
        "As vendas de produto que controla estoque e que nunca foram baixadas (o item "
        "entrou antes de o código estar vinculado), com o saldo que ficaria depois.",
        "/vendas/sem-baixa/previa"),
    Ferramenta(
        "baixar_vendas_sem_baixa", "Baixar do estoque as vendas atrasadas",
        "Lança a saída que ficou para trás, na data de cada venda. ⚠️ Mostre antes a "
        "`previa_vendas_sem_baixa`. Com `id_produto`, só as daquele produto.",
        "/vendas/sem-baixa/baixar",
        {"id_produto": Param("integer", "Só este produto.")},
        metodo="POST"),

    Ferramenta(
        "configuracao_de_precificacao", "Configuração da precificação",
        "Os impostos, taxas, custos por unidade e a margem que formam o preço sugerido "
        "nesta loja.",
        "/precificacao/config"),
    Ferramenta(
        "analise_de_precos", "Análise de preços",
        "Os produtos vendidos no período comparados com o menor preço que entrega a "
        "margem: custo, preço atual, sugerido, diferença e impacto no mês. O sugerido é o "
        "PISO — produto acima dele tem folga, e ninguém manda baixar.",
        "/precificacao/analise",
        {"dias": Param("integer", "Janela de vendas, em dias.", padrao=30, minimo=1,
                       maximo=365),
         "id_produto": Param("integer", "Só este produto (mesmo que venda pouco)."),
         "limite": _lim(200, 500)}),
    Ferramenta(
        "simular_preco", "Simular um preço",
        "A conta de UM produto num preço à escolha: para onde vai cada real (imposto, "
        "taxa, custo, margem). Não grava nada.",
        "/precificacao/simular",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True, no_corpo=True),
         "preco": Param("number", "Preço a testar, em reais.", obrigatorio=True,
                        no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "aplicar_precos", "Aplicar preços de venda",
        "Grava o preço de venda de um ou mais produtos. Vale NA HORA aqui; o PDV só recebe "
        "se o envio estiver ligado — a resposta diz. ⚠️ Mostre antes a lista com o preço "
        "atual e o novo (`analise_de_precos`) e espere o sim.",
        "/precificacao/aplicar",
        {"itens": Param(
            "array", "Um item por produto.", obrigatorio=True, no_corpo=True,
            itens={"type": "object",
                   "properties": {"id_produto": {"type": "integer"},
                                  "preco": {"type": "number",
                                            "description": "Preço novo, em reais."}},
                   "required": ["id_produto", "preco"]})},
        metodo="POST"),

    Ferramenta(
        "criar_grupo_de_cmv", "Criar grupo de CMV",
        "Cria um grupo da apuração do CMV (quais tipos de produto ele soma).",
        "/cmv/grupos",
        {"nome": Param("string", "Nome do grupo.", obrigatorio=True, no_corpo=True),
         "tipos": Param("array", "Tipos de produto do grupo.", no_corpo=True,
                        itens={"type": "string"}),
         "considerar_no_cmv": Param("boolean", "Entra na conta do CMV.", no_corpo=True),
         "ordem": Param("integer", "Posição na lista.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "atualizar_grupo_de_cmv", "Corrigir um grupo de CMV",
        "Regrava um grupo de CMV. ⚠️ Mande o grupo INTEIRO (nome e tipos): veja antes em "
        "`grupos_de_cmv`. Muda a apuração dos períodos ainda abertos.",
        "/cmv/grupos/{id_grupo}",
        {"id_grupo": Param("integer", "Id (de `grupos_de_cmv`).", obrigatorio=True),
         "nome": Param("string", "Nome do grupo.", obrigatorio=True, no_corpo=True),
         "tipos": Param("array", "Tipos de produto do grupo.", no_corpo=True,
                        itens={"type": "string"}),
         "considerar_no_cmv": Param("boolean", "Entra na conta do CMV.", no_corpo=True),
         "ativo": Param("boolean", "Em uso.", no_corpo=True),
         "ordem": Param("integer", "Posição na lista.", no_corpo=True)},
        metodo="PUT"),
    Ferramenta(
        "remover_grupo_de_cmv", "Remover um grupo de CMV",
        "Tira um grupo da apuração do CMV.",
        "/cmv/grupos/{id_grupo}",
        {"id_grupo": Param("integer", "Id (de `grupos_de_cmv`).", obrigatorio=True)},
        metodo="DELETE"),
    Ferramenta(
        "fechar_cmv", "Fechar um período do CMV",
        "Fecha a apuração de um período: congela os números e TRAVA o período para "
        "lançamento retroativo. ⚠️ Mostre antes a apuração (`cmv_apuracao`) e as "
        "pendências, e espere o sim — reabrir é outra decisão.",
        "/cmv/fechamentos",
        {"competencia": Param("string", "O período a fechar: a data de início dele, "
                                        "AAAA-MM-DD (de `cmv_periodos`).",
                              obrigatorio=True, no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "reabrir_cmv", "Reabrir um período fechado do CMV",
        "Reabre um fechamento: o período volta a aceitar lançamento e os números deixam de "
        "estar congelados. ⚠️ O que já foi mandado para a contabilidade deixa de valer.",
        "/cmv/fechamentos/{id_fechamento}/reabrir",
        {"id_fechamento": Param("integer", "Id (de `fechamentos_de_cmv`).",
                                obrigatorio=True)},
        metodo="POST"),
    Ferramenta(
        "abrir_periodo_de_consumo", "Abrir um período de consumo",
        "Abre um ciclo de consumo das pessoas da casa (o que cada um consumiu e vai pagar).",
        "/consumo/periodos",
        {"inicio": Param("string", "Primeiro dia, AAAA-MM-DD.", obrigatorio=True,
                         no_corpo=True),
         "fim": Param("string", "Último dia, AAAA-MM-DD.", obrigatorio=True, no_corpo=True),
         "nome": Param("string", "Nome do ciclo.", no_corpo=True),
         "observacao": Param("string", "Recado.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "fechar_periodo_de_consumo", "Fechar um período de consumo",
        "Fecha o ciclo de consumo: os valores de cada pessoa ficam congelados para a "
        "cobrança. ⚠️ Mostre antes o `consumo_periodo`.",
        "/consumo/periodos/{id_periodo}/fechar",
        {"id_periodo": Param("integer", "Id (de `consumo_periodos`).", obrigatorio=True),
         "observacao": Param("string", "Recado do fechamento.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "reabrir_periodo_de_consumo", "Reabrir um período de consumo",
        "Reabre um ciclo de consumo fechado.",
        "/consumo/periodos/{id_periodo}/reabrir",
        {"id_periodo": Param("integer", "Id (de `consumo_periodos`).", obrigatorio=True)},
        metodo="POST"),
    Ferramenta(
        "remover_periodo_de_consumo", "Remover um período de consumo",
        "Apaga um ciclo de consumo aberto por engano.",
        "/consumo/periodos/{id_periodo}",
        {"id_periodo": Param("integer", "Id (de `consumo_periodos`).", obrigatorio=True)},
        metodo="DELETE"),

    # ------------------------------------------- lote 4: portal de clientes
    # 🔑 Quarto lote. O que se OPERA no dia: reservas, pedidos do cardápio, selos e o
    # conteúdo do catálogo. ⚠️ Fora, de propósito: as CONFIGURAÇÕES (reserva,
    # fidelidade, pedidos), QR codes, arquivo e foto do catálogo, e a planta do salão.
    Ferramenta(
        "calendario_de_reservas", "Calendário de reservas",
        "O mês dia a dia: se a casa abre, o horário e quantas reservas há.",
        "/reservas/calendario",
        {"mes": Param("string", "O mês, AAAA-MM.", obrigatorio=True)}),
    Ferramenta(
        "clientes_das_reservas", "Clientes do site",
        "Quem se cadastrou pelo site ou já reservou, com telefone e histórico.",
        "/reservas/clientes",
        {"busca": Param("string", "Nome ou telefone."),
         "limite": _lim(50, 200), "offset": _OFFSET}),
    Ferramenta(
        "onde_um_grupo_sentaria", "Onde um grupo sentaria",
        "Simula a alocação: para tantas pessoas, em que mesa ou conjunto a casa sentaria.",
        "/reservas/salao/simular",
        {"pessoas": Param("integer", "Tamanho do grupo.", obrigatorio=True, minimo=1),
         "dia_semana": Param("integer", "Dia da semana (0 = segunda … 6 = domingo)."),
         "site": Param("boolean", "Como se fosse uma reserva do site.")}),
    Ferramenta(
        "criar_reserva", "Criar uma reserva",
        "Marca uma reserva de mesa. ⚠️ Confira antes o horário em "
        "`disponibilidade_de_reserva` e confirme nome, dia, hora e pessoas com quem pediu.",
        "/reservas",
        {"data": Param("string", "Dia AAAA-MM-DD.", obrigatorio=True, no_corpo=True),
         "hora": Param("string", "Hora HH:MM.", obrigatorio=True, no_corpo=True),
         "pessoas": Param("integer", "Quantas pessoas.", obrigatorio=True, no_corpo=True,
                          minimo=1),
         "nome": Param("string", "Em nome de quem.", obrigatorio=True, no_corpo=True),
         "telefone": Param("string", "Telefone de contato.", no_corpo=True),
         "objetivo": Param("string", "Ocasião (aniversário, reunião).", no_corpo=True),
         "observacao_cliente": Param("string", "Pedido do cliente.", no_corpo=True),
         "observacao_interna": Param("string", "Recado para a equipe.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "alterar_reserva", "Remarcar uma reserva",
        "Muda o dia, a hora ou o número de pessoas de uma reserva. Só o que for mandado "
        "muda.",
        "/reservas/{id_reserva}",
        {"id_reserva": Param("integer", "Id (de `agenda_de_reservas`).", obrigatorio=True),
         "data": Param("string", "Novo dia AAAA-MM-DD.", no_corpo=True),
         "hora": Param("string", "Nova hora HH:MM.", no_corpo=True),
         "pessoas": Param("integer", "Novo número de pessoas.", no_corpo=True, minimo=1)},
        metodo="PUT"),
    Ferramenta(
        "mudar_status_da_reserva", "Confirmar, encerrar ou cancelar uma reserva",
        "Muda a situação da reserva: confirmar, marcar que o cliente chegou, encerrar, "
        "cancelar ou registrar que não compareceu.",
        "/reservas/{id_reserva}/status",
        {"id_reserva": Param("integer", "Id (de `agenda_de_reservas`).", obrigatorio=True),
         "status": Param("string", "A nova situação.", obrigatorio=True, no_corpo=True,
                         enum=["CONFIRMADA", "CHEGOU", "ENCERRADA", "CANCELADA",
                               "NAO_COMPARECEU"])},
        metodo="PUT"),
    Ferramenta(
        "bloquear_reservas", "Bloquear dias para reservas",
        "Fecha um ou mais DIAS inteiros para novas reservas (evento, férias, manutenção). "
        "Para fechar só um horário, use `definir_dia_de_reserva` no modo ESPECIAL.",
        "/reservas/bloqueios",
        {"de": Param("string", "Primeiro dia, AAAA-MM-DD.", obrigatorio=True, no_corpo=True),
         "ate": Param("string", "Último dia, AAAA-MM-DD.", obrigatorio=True, no_corpo=True),
         "motivo": Param("string", "Por quê.", obrigatorio=True, no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "desbloquear_reservas", "Tirar um bloqueio de reservas",
        "Remove um bloqueio: os dias voltam a aceitar reservas.",
        "/reservas/bloqueios/{id_bloqueio}",
        {"id_bloqueio": Param("integer", "Id (de `bloqueios_de_reserva`).",
                              obrigatorio=True)},
        metodo="DELETE"),
    Ferramenta(
        "definir_dia_de_reserva", "Definir o horário de um dia",
        "Diz como a casa atende reservas num dia específico: PADRAO (o horário de sempre), "
        "ESPECIAL (outro horário) ou FECHADO (feriado, folga).",
        "/reservas/dias/{data}",
        {"data": Param("string", "O dia, AAAA-MM-DD.", obrigatorio=True),
         "modo": Param("string", "Como atende.", obrigatorio=True, no_corpo=True,
                       enum=["PADRAO", "ESPECIAL", "FECHADO"]),
         "abre": Param("string", "Abre às HH:MM (modo ESPECIAL).", no_corpo=True),
         "fecha": Param("string", "Fecha às HH:MM (modo ESPECIAL).", no_corpo=True),
         "ultima_reserva": Param("string", "Última reserva às HH:MM.", no_corpo=True),
         "motivo": Param("string", "Por quê.", no_corpo=True)},
        metodo="PUT"),
    Ferramenta(
        "criar_salao", "Criar um salão",
        "Cria um salão (ambiente) para as mesas.",
        "/reservas/saloes",
        {"nome": Param("string", "Nome do salão.", obrigatorio=True, no_corpo=True),
         "ordem": Param("integer", "Posição na lista.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "atualizar_salao", "Corrigir um salão",
        "Corrige um salão: nome, se atende, em que dias da semana e se aceita reserva pelo "
        "site. Só o que for mandado muda.",
        "/reservas/saloes/{id_salao}",
        {"id_salao": Param("integer", "Id (de `saloes_e_mesas`).", obrigatorio=True),
         "nome": Param("string", "Nome.", no_corpo=True),
         "ativo": Param("boolean", "Atende.", no_corpo=True),
         "dias_semana": Param("array", "Dias em que atende (0 = segunda … 6 = domingo).",
                              no_corpo=True, itens={"type": "integer"}),
         "aceita_site": Param("boolean", "Aceita reserva pelo site.", no_corpo=True),
         "ordem": Param("integer", "Posição na lista.", no_corpo=True)},
        metodo="PUT"),
    Ferramenta(
        "criar_mesa", "Criar uma mesa",
        "Cria uma mesa num salão.",
        "/reservas/mesas",
        {"id_salao": Param("integer", "Salão (de `saloes_e_mesas`).", obrigatorio=True,
                           no_corpo=True),
         "nome": Param("string", "Nome ou número da mesa.", obrigatorio=True, no_corpo=True),
         "lugares": Param("integer", "Lugares confortáveis.", no_corpo=True, minimo=1),
         "capacidade_max": Param("integer", "Máximo, com cadeira extra.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "criar_mesas_em_lote", "Criar várias mesas iguais",
        "Cria várias mesas iguais num salão, numeradas em sequência.",
        "/reservas/mesas/em-lote",
        {"id_salao": Param("integer", "Salão.", obrigatorio=True, no_corpo=True),
         "quantidade": Param("integer", "Quantas mesas.", obrigatorio=True, no_corpo=True,
                             minimo=1),
         "lugares": Param("integer", "Lugares confortáveis de cada uma.", no_corpo=True),
         "capacidade_max": Param("integer", "Máximo de cada uma.", no_corpo=True),
         "prefixo": Param("string", "Prefixo do nome (M → M01, M02…).", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "atualizar_mesa", "Corrigir uma mesa",
        "Corrige uma mesa: nome, lugares, salão ou se está em uso. Só o que for mandado "
        "muda.",
        "/reservas/mesas/{id_mesa}",
        {"id_mesa": Param("integer", "Id (de `saloes_e_mesas`).", obrigatorio=True),
         "nome": Param("string", "Nome.", no_corpo=True),
         "lugares": Param("integer", "Lugares confortáveis.", no_corpo=True),
         "capacidade_max": Param("integer", "Máximo, com cadeira extra.", no_corpo=True),
         "id_salao": Param("integer", "Mudar de salão.", no_corpo=True),
         "ativo": Param("boolean", "Em uso.", no_corpo=True)},
        metodo="PUT"),
    Ferramenta(
        "remover_mesa", "Remover uma mesa",
        "Tira uma mesa do salão.",
        "/reservas/mesas/{id_mesa}",
        {"id_mesa": Param("integer", "Id (de `saloes_e_mesas`).", obrigatorio=True)},
        metodo="DELETE"),

    Ferramenta(
        "painel_de_pedidos", "Painel dos pedidos do cardápio",
        "Quantos pedidos estão esperando resposta, confirmados e para hoje.",
        "/pedidos/painel"),
    Ferramenta(
        "pedidos", "Pedidos do cardápio",
        "Os pedidos feitos pelo cardápio do site.",
        "/pedidos",
        {"situacao": Param("string", "Situação do pedido."),
         "dia": Param("string", "Dia de entrega/retirada, AAAA-MM-DD."),
         "busca": Param("string", "Nome ou telefone do cliente."),
         "limite": _lim(50, 200), "offset": _OFFSET}),
    Ferramenta(
        "pedido", "Um pedido",
        "Um pedido inteiro: itens, cliente, entrega e pagamento.",
        "/pedidos/{id_pedido}",
        {"id_pedido": Param("integer", "Id do pedido.", obrigatorio=True)}),
    Ferramenta(
        "confirmar_pedido", "Confirmar um pedido",
        "Aceita o pedido do cliente. Ele é avisado.",
        "/pedidos/{id_pedido}/confirmar",
        {"id_pedido": Param("integer", "Id do pedido.", obrigatorio=True),
         "observacao": Param("string", "Recado para o cliente.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "recusar_pedido", "Recusar um pedido",
        "Recusa o pedido, com o motivo que o cliente vai ler.",
        "/pedidos/{id_pedido}/recusar",
        {"id_pedido": Param("integer", "Id do pedido.", obrigatorio=True),
         "motivo": Param("string", "Por quê.", obrigatorio=True, no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "cancelar_pedido", "Cancelar um pedido",
        "Cancela um pedido já confirmado, com o motivo.",
        "/pedidos/{id_pedido}/cancelar",
        {"id_pedido": Param("integer", "Id do pedido.", obrigatorio=True),
         "motivo": Param("string", "Por quê.", obrigatorio=True, no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "pedido_lancado_no_pdv", "Marcar o pedido como lançado no PDV",
        "Registra que o pedido foi digitado no caixa, com o número do cupom.",
        "/pedidos/{id_pedido}/lancado-pdv",
        {"id_pedido": Param("integer", "Id do pedido.", obrigatorio=True),
         "cupom": Param("string", "Número do cupom do PDV.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "pedido_pago", "Marcar o pedido como pago",
        "Registra o pagamento do pedido.",
        "/pedidos/{id_pedido}/pago",
        {"id_pedido": Param("integer", "Id do pedido.", obrigatorio=True),
         "como": Param("string", "Forma de pagamento.", obrigatorio=True, no_corpo=True,
                       enum=["DINHEIRO", "CARTAO", "PIX", "OUTRO"])},
        metodo="POST"),
    Ferramenta(
        "entregar_pedido", "Marcar o pedido como entregue",
        "Registra que o pedido foi entregue ou retirado.",
        "/pedidos/{id_pedido}/entregar",
        {"id_pedido": Param("integer", "Id do pedido.", obrigatorio=True)},
        metodo="POST"),

    Ferramenta(
        "painel_de_fidelidade", "Painel da fidelidade",
        "Quantos participantes, selos dados e prêmios ganhos e entregues.",
        "/fidelidade/painel/resumo"),
    Ferramenta(
        "participantes_da_fidelidade", "Participantes da fidelidade",
        "Quem tem cartão de fidelidade, com os selos de cada um.",
        "/fidelidade/participantes",
        {"busca": Param("string", "Nome ou telefone."),
         "limite": _lim(50, 200), "offset": _OFFSET}),
    Ferramenta(
        "participante_da_fidelidade", "Um participante da fidelidade",
        "O cartão de uma pessoa: selos, visitas e prêmios.",
        "/fidelidade/participantes/{id_cliente}",
        {"id_cliente": Param("integer", "Id do cliente.", obrigatorio=True)}),
    Ferramenta(
        "premios_da_fidelidade", "Prêmios da fidelidade",
        "Os prêmios ganhos: a entregar, entregues e vencidos.",
        "/fidelidade/premios",
        {"status": Param("string", "Situação do prêmio."),
         "busca": Param("string", "Nome, telefone ou código."),
         "limite": _lim(50, 200), "offset": _OFFSET}),
    Ferramenta(
        "dar_selos", "Dar ou tirar selos de um participante",
        "Acerta os selos do cartão de alguém à mão (positivo dá, negativo tira), com o "
        "motivo — fica registrado quem fez.",
        "/fidelidade/participantes/{id_cliente}/selos",
        {"id_cliente": Param("integer", "Id do cliente.", obrigatorio=True),
         "selos": Param("integer", "Quantos selos (negativo tira).", obrigatorio=True,
                        no_corpo=True),
         "motivo": Param("string", "Por quê.", obrigatorio=True, no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "entregar_premio", "Entregar um prêmio da fidelidade",
        "Dá baixa no prêmio pelo código que o cliente mostra.",
        "/fidelidade/premios/entregar",
        {"codigo": Param("string", "O código do prêmio.", obrigatorio=True, no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "prorrogar_premio", "Mudar o vencimento de um prêmio",
        "Altera a data até quando o prêmio pode ser retirado.",
        "/fidelidade/premios/{id_premio}/vencimento",
        {"id_premio": Param("integer", "Id (de `premios_da_fidelidade`).", obrigatorio=True),
         "vence_em": Param("string", "Nova data, AAAA-MM-DD.", obrigatorio=True,
                           no_corpo=True)},
        metodo="PUT"),

    Ferramenta(
        "catalogos", "Catálogos do site",
        "Os cardápios e catálogos que o site do cliente apresenta.",
        "/catalogos",
        {"situacao": Param("string", "RASCUNHO, ATIVO ou INATIVO.")}),
    Ferramenta(
        "catalogo", "Um catálogo",
        "O cadastro de um catálogo: nome, período de publicação e lojas.",
        "/catalogos/{id_catalogo}",
        {"id_catalogo": Param("integer", "Id (de `catalogos`).", obrigatorio=True)}),
    Ferramenta(
        "conteudo_do_catalogo", "O que um catálogo mostra",
        "As seções (categorias e subcategorias) de um catálogo e os produtos de cada uma.",
        "/catalogos/{id_catalogo}/conteudo",
        {"id_catalogo": Param("integer", "Id (de `catalogos`).", obrigatorio=True)}),
    Ferramenta(
        "produtos_para_o_catalogo", "Produtos que podem ir ao catálogo",
        "Os produtos que podem ser postos num catálogo.",
        "/catalogos/produtos-disponiveis",
        {"busca": Param("string", "Nome do produto.")}),
    Ferramenta(
        "criar_catalogo", "Criar um catálogo",
        "Cria um catálogo, em RASCUNHO. Ele só aparece no site quando a situação vira "
        "ATIVO (`atualizar_catalogo`).",
        "/catalogos",
        {"nome": Param("string", "Nome do catálogo.", obrigatorio=True, no_corpo=True),
         # ⚠️ OBRIGATÓRIO, e não "padrão PRODUTOS": o padrão do esquema é só um aviso
         # ao modelo, não vai no corpo — e a rota, sem o campo, cria o catálogo como
         # PDF, que não aceita seção nem produto. Pelo conector o arquivo nem sobe.
         "origem": Param("string", "PRODUTOS = montado aqui, com seções e produtos (é o "
                                   "que o conector consegue montar). PDF = um arquivo, "
                                   "que só se envia pela tela.", obrigatorio=True,
                         no_corpo=True, enum=["PRODUTOS", "PDF"]),
         "publica_de": Param("string", "Entra no ar em AAAA-MM-DD.", no_corpo=True),
         "publica_ate": Param("string", "Sai do ar em AAAA-MM-DD.", no_corpo=True),
         "observacao": Param("string", "Recado interno.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "atualizar_catalogo", "Corrigir ou publicar um catálogo",
        "Corrige um catálogo: nome, período e situação. ⚠️ `situacao: ATIVO` põe o "
        "catálogo NO SITE, à vista do cliente — confirme antes.",
        "/catalogos/{id_catalogo}",
        {"id_catalogo": Param("integer", "Id (de `catalogos`).", obrigatorio=True),
         "nome": Param("string", "Nome.", no_corpo=True),
         "situacao": Param("string", "Situação.", no_corpo=True,
                           enum=["RASCUNHO", "ATIVO", "INATIVO"]),
         "publica_de": Param("string", "Entra no ar em AAAA-MM-DD.", no_corpo=True),
         "publica_ate": Param("string", "Sai do ar em AAAA-MM-DD.", no_corpo=True),
         "observacao": Param("string", "Recado interno.", no_corpo=True)},
        metodo="PUT"),
    Ferramenta(
        "remover_catalogo", "Remover um catálogo",
        "Apaga um catálogo. Só rascunho sai; o que já foi ao ar se inativa.",
        "/catalogos/{id_catalogo}",
        {"id_catalogo": Param("integer", "Id (de `catalogos`).", obrigatorio=True)},
        metodo="DELETE"),
    Ferramenta(
        "criar_secao_do_catalogo", "Criar uma seção do catálogo",
        "Cria uma seção (categoria) dentro de um catálogo: Entradas, Bebidas.",
        "/catalogos/{id_catalogo}/categorias",
        {"id_catalogo": Param("integer", "Id do catálogo.", obrigatorio=True),
         "nome": Param("string", "Nome da seção.", obrigatorio=True, no_corpo=True),
         "descricao": Param("string", "Texto que aparece abaixo do nome.", no_corpo=True),
         "ordem": Param("integer", "Posição.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "atualizar_secao_do_catalogo", "Corrigir uma seção do catálogo",
        "Regrava o nome, o texto e a posição de uma seção.",
        "/catalogos/categorias/{id_categoria}",
        {"id_categoria": Param("integer", "Id da seção (de `conteudo_do_catalogo`).",
                               obrigatorio=True),
         "nome": Param("string", "Nome da seção.", obrigatorio=True, no_corpo=True),
         "descricao": Param("string", "Texto abaixo do nome.", no_corpo=True),
         "ordem": Param("integer", "Posição.", no_corpo=True)},
        metodo="PUT"),
    Ferramenta(
        "remover_secao_do_catalogo", "Remover uma seção do catálogo",
        "Tira uma seção do catálogo, com os itens dela.",
        "/catalogos/categorias/{id_categoria}",
        {"id_categoria": Param("integer", "Id da seção.", obrigatorio=True)},
        metodo="DELETE"),
    Ferramenta(
        "criar_subsecao_do_catalogo", "Criar uma subseção do catálogo",
        "Cria uma subseção dentro de uma seção do catálogo.",
        "/catalogos/categorias/{id_categoria}/subcategorias",
        {"id_categoria": Param("integer", "Id da seção.", obrigatorio=True),
         "nome": Param("string", "Nome da subseção.", obrigatorio=True, no_corpo=True),
         "descricao": Param("string", "Texto abaixo do nome.", no_corpo=True),
         "ordem": Param("integer", "Posição.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "por_produto_no_catalogo", "Pôr um produto no catálogo",
        "Põe um produto numa seção do catálogo (de `produtos_para_o_catalogo`).",
        "/catalogos/categorias/{id_categoria}/itens",
        {"id_categoria": Param("integer", "Id da seção.", obrigatorio=True),
         "id_produto": Param("integer", "Produto.", obrigatorio=True, no_corpo=True),
         "id_subcategoria": Param("integer", "Subseção, se houver.", no_corpo=True),
         "ordem": Param("integer", "Posição.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "tirar_produto_do_catalogo", "Tirar um produto do catálogo",
        "Tira um item do catálogo. O produto continua no cadastro.",
        "/catalogos/itens/{id_item}",
        {"id_item": Param("integer", "Id do item (de `conteudo_do_catalogo`).",
                          obrigatorio=True)},
        metodo="DELETE"),

    # ------------------------------------------- lote 2: cadastros de apoio
    # 🔑 Segundo lote do pedido de 09/10/2026. As tabelas que o produto usa — categoria,
    # setor, prateleira, fornecedor, unidade — e três campos do próprio produto que
    # tinham rota e não tinham ferramenta.
    # ⚠️ `integrado_pdv` fica FORA de categorias e setores: marcar ali cria pendência
    # de envio ao PDV, e o que vai ao caixa continua sendo decidido na tela.
    Ferramenta(
        "criar_categoria", "Criar categoria",
        "Cria uma categoria de produtos. ⚠️ Confira antes em `categorias` se ela já "
        "existe com outro nome.",
        "/categorias",
        {"nome": Param("string", "Nome da categoria.", obrigatorio=True, no_corpo=True),
         "tipo": Param("string", "De que tipo de produto ela é.", padrao="INSUMO",
                       no_corpo=True, enum=["INSUMO", "REVENDA", "PRODUZIDO", "EMBALAGEM", "MATERIAL_LIMPEZA", "UTENSILIO"]),
         "id_pai": Param("integer", "Categoria-mãe, para criar uma subcategoria.",
                         no_corpo=True),
         "ordem": Param("integer", "Posição na lista.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "atualizar_categoria", "Corrigir uma categoria",
        "Corrige uma categoria: só o que for mandado muda. `ativo: false` desativa.",
        "/categorias/{id_categoria}",
        {"id_categoria": Param("integer", "Id (de `categorias`).", obrigatorio=True),
         "nome": Param("string", "Nome.", no_corpo=True),
         "tipo": Param("string", "Tipo de produto.", no_corpo=True, enum=["INSUMO", "REVENDA", "PRODUZIDO", "EMBALAGEM", "MATERIAL_LIMPEZA", "UTENSILIO"]),
         "id_pai": Param("integer", "Categoria-mãe.", no_corpo=True),
         "ordem": Param("integer", "Posição na lista.", no_corpo=True),
         "ativo": Param("boolean", "Em uso.", no_corpo=True)},
        metodo="PUT"),
    Ferramenta(
        "remover_categoria", "Remover uma categoria",
        "Tira a categoria: a que tem produto é só DESATIVADA, a vazia é apagada. Recusa "
        "quando há subcategorias.",
        "/categorias/{id_categoria}",
        {"id_categoria": Param("integer", "Id (de `categorias`).", obrigatorio=True)},
        metodo="DELETE"),
    Ferramenta(
        "criar_setor", "Criar setor",
        "Cria um setor da casa (Cozinha, Bar, Confeitaria).",
        "/setores",
        {"nome": Param("string", "Nome do setor.", obrigatorio=True, no_corpo=True),
         "cor": Param("string", "Cor em hexadecimal (#2f6b4f).", no_corpo=True),
         "ordem": Param("integer", "Posição na lista.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "atualizar_setor", "Corrigir um setor",
        "Corrige um setor: só o que for mandado muda. `ativo: false` desativa.",
        "/setores/{id_setor}",
        {"id_setor": Param("integer", "Id (de `setores`).", obrigatorio=True),
         "nome": Param("string", "Nome.", no_corpo=True),
         "cor": Param("string", "Cor em hexadecimal.", no_corpo=True),
         "ordem": Param("integer", "Posição na lista.", no_corpo=True),
         "ativo": Param("boolean", "Em uso.", no_corpo=True)},
        metodo="PUT"),
    Ferramenta(
        "remover_setor", "Remover um setor",
        "Tira o setor: o que está em uso é só DESATIVADO, o vazio é apagado.",
        "/setores/{id_setor}",
        {"id_setor": Param("integer", "Id (de `setores`).", obrigatorio=True)},
        metodo="DELETE"),
    Ferramenta(
        "criar_local", "Criar prateleira de estoque",
        "Cria um local de estoque (prateleira, câmara, canto de um setor) na loja.",
        "/locais",
        {"nome": Param("string", "Nome do local.", obrigatorio=True, no_corpo=True),
         "tipo": Param("string", "Como conserva.", padrao="SECO", no_corpo=True,
                       enum=["SECO", "RESFRIADO", "CONGELADO", "BAR"]),
         "id_setor": Param("integer", "Setor a que pertence (de `setores`); sem ele, é "
                                      "estoque geral.", no_corpo=True),
         "principal": Param("boolean", "É o local padrão da loja.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "atualizar_local", "Corrigir uma prateleira",
        "Corrige um local de estoque: só o que for mandado muda. `ativo: false` desativa.",
        "/locais/{id_local}",
        {"id_local": Param("integer", "Id (de `locais`).", obrigatorio=True),
         "nome": Param("string", "Nome.", no_corpo=True),
         "tipo": Param("string", "Como conserva.", no_corpo=True,
                       enum=["SECO", "RESFRIADO", "CONGELADO", "BAR"]),
         "id_setor": Param("integer", "Setor a que pertence.", no_corpo=True),
         "principal": Param("boolean", "É o local padrão da loja.", no_corpo=True),
         "ativo": Param("boolean", "Em uso.", no_corpo=True)},
        metodo="PUT"),
    Ferramenta(
        "desativar_local", "Desativar uma prateleira",
        "Desativa um local de estoque. O saldo e o histórico dele continuam existindo.",
        "/locais/{id_local}",
        {"id_local": Param("integer", "Id (de `locais`).", obrigatorio=True)},
        metodo="DELETE"),
    Ferramenta(
        "criar_fornecedor", "Cadastrar fornecedor ou pessoa",
        "Cadastra um fornecedor (ou uma pessoa da casa, com `fornecedor: false`). "
        "⚠️ Procure antes em `buscar_pessoas`, pelo nome e pelo CNPJ.",
        "/fornecedores",
        {"nome": Param("string", "Razão social ou nome.", obrigatorio=True, no_corpo=True),
         "nome_fantasia": Param("string", "Nome fantasia.", no_corpo=True),
         "cnpj": Param("string", "CNPJ ou CPF.", no_corpo=True),
         "email": Param("string", "E-mail.", no_corpo=True),
         "telefone": Param("string", "Telefone.", no_corpo=True),
         "whatsapp": Param("string", "WhatsApp.", no_corpo=True),
         "contato": Param("string", "Com quem falar.", no_corpo=True),
         "cidade": Param("string", "Cidade.", no_corpo=True),
         "uf": Param("string", "UF, duas letras.", no_corpo=True),
         "prazo_entrega_dias": Param("integer", "Dias entre pedir e receber.", no_corpo=True),
         "dias_entrega": Param("string", "Dias em que entrega (seg,qui).", no_corpo=True),
         "pedido_minimo": Param("number", "Pedido mínimo, em reais.", no_corpo=True),
         "observacao": Param("string", "Recado interno.", no_corpo=True),
         "fornecedor": Param("boolean", "É fornecedor (true) ou só pessoa da casa.",
                             padrao=True, no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "atualizar_fornecedor", "Corrigir fornecedor ou pessoa",
        "Corrige o cadastro: só o que for mandado muda. `ativo: false` desativa.",
        "/fornecedores/{id_fornecedor}",
        {"id_fornecedor": Param("integer", "Id (de `buscar_pessoas`).", obrigatorio=True),
         "nome": Param("string", "Razão social ou nome.", no_corpo=True),
         "nome_fantasia": Param("string", "Nome fantasia.", no_corpo=True),
         "cnpj": Param("string", "CNPJ ou CPF.", no_corpo=True),
         "email": Param("string", "E-mail.", no_corpo=True),
         "telefone": Param("string", "Telefone.", no_corpo=True),
         "whatsapp": Param("string", "WhatsApp.", no_corpo=True),
         "contato": Param("string", "Com quem falar.", no_corpo=True),
         "cidade": Param("string", "Cidade.", no_corpo=True),
         "uf": Param("string", "UF, duas letras.", no_corpo=True),
         "prazo_entrega_dias": Param("integer", "Dias entre pedir e receber.", no_corpo=True),
         "dias_entrega": Param("string", "Dias em que entrega (seg,qui).", no_corpo=True),
         "pedido_minimo": Param("number", "Pedido mínimo, em reais.", no_corpo=True),
         "observacao": Param("string", "Recado interno.", no_corpo=True),
         "ativo": Param("boolean", "Em uso.", no_corpo=True)},
        metodo="PUT"),
    Ferramenta(
        "desativar_fornecedor", "Desativar fornecedor ou pessoa",
        "Desativa o cadastro. As notas e o histórico dele continuam existindo.",
        "/fornecedores/{id_fornecedor}",
        {"id_fornecedor": Param("integer", "Id (de `buscar_pessoas`).", obrigatorio=True)},
        metodo="DELETE"),
    Ferramenta(
        "criar_unidade_de_medida", "Criar unidade de medida",
        "Cria uma unidade (sigla e nome). ⚠️ `fator_base` é quanto ela vale na unidade-base "
        "da grandeza: G vale 0,001 (a base da massa é KG), ML vale 0,001 (a base do volume "
        "é L). Para embalagem (caixa, fardo) use grandeza UNIDADE com fator 1 — quantas "
        "cabem na caixa é do PRODUTO (`gravar_unidades_de_compra`), não da unidade.",
        "/unidades-medida",
        {"sigla": Param("string", "Sigla, até 6 letras.", obrigatorio=True, no_corpo=True),
         "nome": Param("string", "Nome por extenso.", obrigatorio=True, no_corpo=True),
         "grandeza": Param("string", "O que ela mede.", padrao="UNIDADE", no_corpo=True,
                           enum=["MASSA", "VOLUME", "UNIDADE"]),
         "fator_base": Param("number", "Quanto vale na unidade-base da grandeza.",
                             padrao=1, no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "atualizar_unidade_de_medida", "Corrigir uma unidade de medida",
        "Corrige uma unidade: só o que for mandado muda. ⚠️ Mudar `fator_base` ou "
        "`grandeza` muda a CONVERSÃO de toda ficha e nota que usa a sigla — confirme com a "
        "pessoa antes.",
        "/unidades-medida/{sigla}",
        {"sigla": Param("string", "A sigla (de `unidades_medida`).", obrigatorio=True),
         "nome": Param("string", "Nome por extenso.", no_corpo=True),
         "grandeza": Param("string", "O que ela mede.", no_corpo=True,
                           enum=["MASSA", "VOLUME", "UNIDADE"]),
         "fator_base": Param("number", "Quanto vale na unidade-base.", no_corpo=True),
         "ativo": Param("boolean", "Em uso.", no_corpo=True)},
        metodo="PUT"),
    Ferramenta(
        "apelidar_unidade_de_medida", "Dar apelido a uma unidade",
        "Ensina que uma sigla que vem de fora é uma unidade da casa: \"UND\" e \"UNID\" "
        "são UN, \"BJ\" é BANDEJA. É o que faz a nota do fornecedor casar sozinha.",
        "/unidades-medida/apelidos",
        {"apelido": Param("string", "A sigla como vem na nota.", obrigatorio=True,
                          no_corpo=True),
         "sigla": Param("string", "A unidade da casa a que ela corresponde.",
                        obrigatorio=True, no_corpo=True)},
        metodo="POST"),

    Ferramenta(
        "informar_custo_do_produto", "Informar o custo de um produto",
        "Grava o custo de UMA unidade de estoque digitado por quem conhece o produto. "
        "Serve para o que tem custo e não entra por nota (água encanada, gás). ⚠️ É o "
        "ÚLTIMO degrau: só vale quando não há custo médio no estoque nem preço de "
        "fornecedor — a resposta diz (`responde`). Para corrigir custo médio é "
        "`ajustar_custo`.",
        "/produtos/{id_produto}/custo-informado",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True),
         "custo": Param("number", "Custo de uma unidade de estoque, em reais. Maior que "
                                  "zero.", obrigatorio=True, no_corpo=True)},
        metodo="PUT"),
    Ferramenta(
        "definir_preco_da_loja", "Definir o preço de venda nesta loja",
        "Grava o preço de venda do produto NESTA loja, que sobrepõe o da casa. Sem valor "
        "(nulo), a loja volta a usar o preço da casa. ⚠️ Vale na hora aqui; o PDV só "
        "recebe se o envio estiver ligado. Para o preço da casa é `atualizar_produto`.",
        "/produtos/{id_produto}/preco-loja",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True),
         "preco_venda": Param("number", "Preço nesta loja, em reais.", no_corpo=True)},
        metodo="PUT"),
    Ferramenta(
        "kit_do_produto", "Composição de um combo",
        "Os componentes de um produto do tipo KIT e quanto ele custa hoje.",
        "/produtos/{id_produto}/kit",
        {"id_produto": Param("integer", "Id do produto (tipo KIT).", obrigatorio=True)}),
    Ferramenta(
        "gravar_kit", "Gravar a composição de um combo",
        "Define os componentes de um produto do tipo KIT. ⚠️ SUBSTITUI a composição "
        "inteira: mande todos os que ficam (veja antes em `kit_do_produto`).",
        "/produtos/{id_produto}/kit",
        {"id_produto": Param("integer", "Id do produto (tipo KIT).", obrigatorio=True),
         "itens": Param(
             "array", "Os componentes do combo.", obrigatorio=True, no_corpo=True,
             itens={"type": "object",
                    "properties": {
                        "id_componente": {"type": "integer",
                                          "description": "Produto que entra no combo."},
                        "quantidade": {"type": "number",
                                       "description": "Quantos, na unidade de estoque dele."},
                        "observacao": {"type": "string"}},
                    "required": ["id_componente"]})},
        metodo="PUT"),

    # ------------------------------------------- lote 1: estoque e produção
    # 🔑 **"Disponibilizar as maiores opções possíveis para o conector, pois o cliente
    # está utilizando muito por lá"** (pedido do dono, 09/10/2026). Cada ferramenta é
    # a MESMA rota da tela — a permissão, a trava de período fechado e o razão
    # append-only continuam sendo decididos pelo servidor. Ficaram de fora, de
    # propósito: usuários, papéis, credenciais de integração e envio ao PDV.
    Ferramenta(
        "motivos_de_perda", "Motivos de perda",
        "Os motivos cadastrados para lançar uma perda ou descartar uma etiqueta.",
        "/estoque/motivos-perda"),
    Ferramenta(
        "etiquetas", "Etiquetas de validade",
        "As etiquetas de validade da loja: ativas, a vencer, vencidas ou já baixadas.",
        "/etiquetas",
        {"situacao": Param("string", "Quais trazer.", padrao="ativas",
                           enum=["ativas", "vencendo", "vencidas", "baixadas"]),
         "busca": Param("string", "Nome do produto, código da etiqueta ou lote."),
         "id_local": Param("integer", "Só desta prateleira."),
         "limite": _lim(50, 200), "offset": _OFFSET}),
    Ferramenta(
        "painel_de_etiquetas", "Painel das etiquetas",
        "Quantas etiquetas estão ativas, vencendo e vencidas, e quanto foi descartado.",
        "/etiquetas/painel"),

    Ferramenta(
        "previa_ajuste_de_saldo", "Prévia do acerto de saldo",
        "O que o acerto de saldo faria, SEM fazer: o saldo de hoje, a diferença e o valor. "
        "Chame antes de `ajustar_saldo` e mostre à pessoa.",
        "/ajustes/estoque/previa",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True, no_corpo=True),
         "quantidade_certa": Param("number", "Quanto a prateleira TEM (a contagem), não a "
                                             "diferença.", obrigatorio=True, no_corpo=True),
         "id_local": Param("integer", "Prateleira (de `locais`). Sem ela, a padrão.",
                           no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "ajustar_saldo", "Acertar o saldo de um produto",
        "Acerta o saldo de UM produto numa prateleira para a quantidade contada: a diferença "
        "vira um movimento de ajuste no razão. ⚠️ O razão não se apaga — desfazer é outro "
        "ajuste. Mostre antes a `previa_ajuste_de_saldo` e espere o sim. Para contar vários "
        "produtos de uma vez, o caminho é o inventário (`abrir_inventario`).",
        "/ajustes/estoque",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True, no_corpo=True),
         "quantidade_certa": Param("number", "Quanto a prateleira TEM (a contagem), não a "
                                             "diferença.", obrigatorio=True, no_corpo=True),
         "id_local": Param("integer", "Prateleira (de `locais`). Sem ela, a padrão.",
                           no_corpo=True),
         "observacao": Param("string", "Por que está sendo acertado.", no_corpo=True),
         "documento": Param("string", "Documento de referência, se houver.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "previa_ajuste_de_custo", "Prévia do ajuste de custo",
        "O que o ajuste de custo médio faria, SEM fazer: o custo de hoje, o novo e quanto "
        "muda o valor do estoque. Chame antes de `ajustar_custo`.",
        "/ajustes/custo/previa",
        {"linhas": Param(
            "array", "Um item por produto.", obrigatorio=True, no_corpo=True,
            itens={"type": "object",
                   "properties": {
                       "id_produto": {"type": "integer"},
                       "custo_novo": {"type": "number",
                                      "description": "O custo CERTO por unidade de estoque, "
                                                     "não a diferença."},
                       "id_local": {"type": "integer",
                                    "description": "Só nesta prateleira; sem ela, em todas."}},
                   "required": ["id_produto", "custo_novo"]})},
        metodo="POST"),
    Ferramenta(
        "ajustar_custo", "Ajustar o custo médio",
        "Corrige o custo médio do estoque de um ou mais produtos. Não move mercadoria: muda "
        "o VALOR do estoque, e com ele o custo de toda ficha que usa o insumo. ⚠️ Mostre "
        "antes a `previa_ajuste_de_custo` e espere o sim. Produto SEM estoque não tem custo "
        "médio — para ele, o custo se informa no cadastro.",
        "/ajustes/custo",
        {"linhas": Param(
            "array", "Um item por produto.", obrigatorio=True, no_corpo=True,
            itens={"type": "object",
                   "properties": {
                       "id_produto": {"type": "integer"},
                       "custo_novo": {"type": "number",
                                      "description": "O custo CERTO por unidade de estoque."},
                       "id_local": {"type": "integer"},
                       "observacao": {"type": "string"}},
                   "required": ["id_produto", "custo_novo"]}),
         "observacao": Param("string", "Por que o custo está sendo corrigido.", no_corpo=True),
         "documento": Param("string", "Documento de referência, se houver.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "entrada_de_estoque", "Entrada avulsa no estoque",
        "Dá entrada de um produto SEM nota: bonificação, sobra, acerto de implantação. "
        "⚠️ Compra com nota NÃO é aqui — é `lancar_nota`, senão a mercadoria entra duas "
        "vezes. O custo informado entra no custo médio.",
        "/estoque/entradas",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True, no_corpo=True),
         "quantidade": Param("number", "Quanto entra, na unidade de estoque. Maior que zero.",
                             obrigatorio=True, no_corpo=True),
         "custo_unitario": Param("number", "Custo de UMA unidade de estoque, em reais.",
                                 obrigatorio=True, no_corpo=True),
         "id_local": Param("integer", "Prateleira (de `locais`). Sem ela, a do produto.",
                           no_corpo=True),
         "documento": Param("string", "Documento de referência.", no_corpo=True),
         "observacao": Param("string", "De onde veio.", no_corpo=True),
         "lote": Param("string", "Lote, para produto que controla lote.", no_corpo=True),
         "validade": Param("string", "Validade AAAA-MM-DD.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "saida_de_estoque", "Saída do estoque: perda ou consumo",
        "Baixa uma quantidade do estoque fora de venda e de produção: PERDA (quebra, "
        "vencimento — peça o motivo, de `motivos_de_perda`) ou CONSUMO INTERNO (uso da "
        "casa). ⚠️ Venda entra por Vendas e ingrediente de receita sai por `produzir`; "
        "lançar aqui também baixaria em dobro.",
        "/estoque/saidas",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True, no_corpo=True),
         "quantidade": Param("number", "Quanto sai, na unidade de estoque. Maior que zero.",
                             obrigatorio=True, no_corpo=True),
         "tipo": Param("string", "O que foi.", padrao="SAIDA_CONSUMO_INTERNO", no_corpo=True,
                       enum=["SAIDA_PERDA", "SAIDA_CONSUMO_INTERNO"]),
         "id_motivo_perda": Param("integer", "Motivo, quando é perda.", no_corpo=True),
         "id_local": Param("integer", "De que prateleira sai. Sem ela, a do produto.",
                           no_corpo=True),
         "observacao": Param("string", "O que aconteceu.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "estornar_movimento", "Estornar um movimento do estoque",
        "Desfaz UM movimento do razão criando o contrário dele (o original continua lá). "
        "O id vem de `movimentos_estoque`. ⚠️ Produção inteira é `estornar_producao`; nota "
        "lançada e venda têm o próprio cancelamento, que desfaz tudo junto.",
        "/estoque/movimentos/{id_movimento}/estornar",
        {"id_movimento": Param("integer", "Id do movimento.", obrigatorio=True),
         "motivo": Param("string", "Por que está sendo estornado.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "estornar_producao", "Estornar uma produção",
        "Desfaz uma produção inteira: o produzido sai da prateleira e os insumos voltam. O "
        "id vem de `producoes_feitas`. Recusa quando o produzido já foi usado ou vendido "
        "(acerte por `ajustar_saldo`) e quando a produção nasceu de uma venda ainda de pé.",
        "/estoque/producoes/{id_producao}/estornar",
        {"id_producao": Param("integer", "Id da produção.", obrigatorio=True),
         "motivo": Param("string", "Por que está sendo estornada.", no_corpo=True)},
        metodo="POST"),

    Ferramenta(
        "agendar_producao", "Agendar uma produção",
        "Põe uma produção na agenda de um dia. NÃO mexe no estoque — isso acontece quando "
        "a linha é cumprida (`produzir_da_agenda`). O mesmo produto no mesmo dia soma na "
        "mesma linha.",
        "/producao-agenda",
        {"id_produto": Param("integer", "Produto a produzir.", obrigatorio=True, no_corpo=True),
         "quantidade": Param("number", "Quanto, na `medida` escolhida.", obrigatorio=True,
                             no_corpo=True),
         "medida": Param("string", "PORCOES = unidade de estoque do produto; RECEITAS = "
                                   "voltas inteiras da ficha; RENDIMENTO = unidade em que a "
                                   "receita rende.", padrao="PORCOES", no_corpo=True,
                         enum=["PORCOES", "RECEITAS", "RENDIMENTO"]),
         "data_prevista": Param("string", "Dia AAAA-MM-DD. Sem ele, amanhã.", no_corpo=True),
         "id_local": Param("integer", "Prateleira de quem produz.", no_corpo=True),
         "id_modo": Param("integer", "Modo de rendimento da ficha.", no_corpo=True),
         "observacao": Param("string", "Recado para a cozinha.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "produzir_da_agenda", "Cumprir uma linha da agenda",
        "Produz o que estava agendado: baixa os insumos e dá entrada no produzido. O id vem "
        "de `agenda_producao`. ⚠️ Mexe no estoque — mostre `item_da_agenda` antes.",
        "/producao-agenda/{id_agenda}/produzir",
        {"id_agenda": Param("integer", "Id da linha da agenda.", obrigatorio=True),
         "quantidade": Param("number", "Quanto saiu de fato, na unidade de estoque. Sem "
                                       "ela, o planejado.", no_corpo=True),
         "id_local": Param("integer", "Prateleira de quem produziu.", no_corpo=True),
         "consumos": Param(
             "array", "Só quando o que SAIU foi diferente da receita.", no_corpo=True,
             itens={"type": "object",
                    "properties": {"id_item": {"type": "integer",
                                               "description": "A linha da receita."},
                                   "quantidade": {"type": "number"},
                                   "um": {"type": "string"}},
                    "required": ["id_item", "quantidade"]})},
        metodo="POST"),
    Ferramenta(
        "cancelar_agenda", "Tirar uma linha da agenda",
        "Cancela uma produção agendada que ainda não foi feita. Não mexe no estoque.",
        "/producao-agenda/{id_agenda}",
        {"id_agenda": Param("integer", "Id da linha da agenda.", obrigatorio=True)},
        metodo="DELETE"),
    # ⚠️ **Homologar NÃO entra, e a ausência é decisão antiga** (ver
    # `criar_ficha_tecnica`, mais abaixo): a ficha lida de arquivo nasce RASCUNHO, e
    # é na tela, com o custo do lado, que alguém confere antes de liberar a produção.
    # O lote de 09/10/2026 abriu quase tudo de estoque e produção; isto ficou de fora
    # até o dono dizer o contrário.
    Ferramenta(
        "duplicar_ficha", "Copiar uma ficha para outro produto",
        "Cria, em RASCUNHO, uma ficha para outro produto com a mesma receita desta.",
        "/fichas/{id_ficha}/duplicar",
        {"id_ficha": Param("integer", "A ficha a copiar.", obrigatorio=True),
         "id_produto": Param("integer", "O produto que recebe a cópia.", obrigatorio=True,
                             no_corpo=True)},
        metodo="POST"),

    Ferramenta(
        "abrir_inventario", "Abrir uma contagem de estoque",
        "Abre um inventário congelando o saldo de agora. Os filtros combinam com E, e vazio "
        "quer dizer todos. Nada muda no estoque até `fechar_inventario`.",
        "/inventarios",
        {"nome": Param("string", "Nome da contagem.", no_corpo=True),
         "cega": Param("boolean", "Contagem cega: quem conta não vê o saldo do sistema.",
                       padrao=False, no_corpo=True),
         "locais": Param("array", "Ids das prateleiras.", no_corpo=True,
                         itens={"type": "integer"}),
         "setores": Param("array", "Ids dos setores.", no_corpo=True,
                          itens={"type": "integer"}),
         "categorias": Param("array", "Ids das categorias.", no_corpo=True,
                             itens={"type": "integer"}),
         "produtos": Param("array", "Ids dos produtos, para contar só alguns.", no_corpo=True,
                           itens={"type": "integer"}),
         "observacao": Param("string", "Recado sobre esta contagem.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "contar_inventario", "Lançar a contagem",
        "Grava o que foi contado em um inventário aberto. Pode ser chamado várias vezes; "
        "ainda não mexe no razão.",
        "/inventarios/{id_inventario}/contagem",
        {"id_inventario": Param("integer", "Id da contagem.", obrigatorio=True),
         "itens": Param(
             "array", "O que foi contado.", obrigatorio=True, no_corpo=True,
             itens={"type": "object",
                    "properties": {
                        "id_produto": {"type": "integer"},
                        "id_local": {"type": "integer",
                                     "description": "Prateleira da linha (de `inventario`)."},
                        "qtd_contada": {"type": "number"},
                        "um": {"type": "string",
                               "description": "Unidade do que foi contado; sem ela, a de "
                                              "estoque."},
                        "observacao": {"type": "string"}},
                    "required": ["id_produto"]})},
        metodo="PUT"),
    Ferramenta(
        "incluir_no_inventario", "Incluir um produto na contagem",
        "Acrescenta à contagem um produto achado na prateleira que não estava na lista.",
        "/inventarios/{id_inventario}/incluir",
        {"id_inventario": Param("integer", "Id da contagem.", obrigatorio=True),
         "id_produto": Param("integer", "Produto achado.", obrigatorio=True, no_corpo=True),
         "id_local": Param("integer", "Em que prateleira.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "fechar_inventario", "Fechar a contagem",
        "Fecha o inventário e ACERTA O ESTOQUE: cada diferença vira um movimento de ajuste. "
        "⚠️ Não se desfaz. Mostre antes as divergências (`inventario`) e espere o sim.",
        "/inventarios/{id_inventario}/fechar",
        {"id_inventario": Param("integer", "Id da contagem.", obrigatorio=True)},
        metodo="POST"),
    Ferramenta(
        "cancelar_inventario", "Cancelar a contagem",
        "Cancela um inventário aberto, sem acertar nada no estoque.",
        "/inventarios/{id_inventario}",
        {"id_inventario": Param("integer", "Id da contagem.", obrigatorio=True)},
        metodo="DELETE"),

    Ferramenta(
        "emitir_etiquetas", "Emitir etiquetas de validade",
        "Gera etiquetas de validade: do que foi PRODUZIDO, do que foi ABERTO ou do que foi "
        "posto para DESCONGELAR. A validade sai da regra do produto. Reetiquetar um pote "
        "(abrir, descongelar, dividir) é passar `id_origem`.",
        "/etiquetas",
        {"evento": Param("string", "O que aconteceu com o produto.", obrigatorio=True,
                         no_corpo=True, enum=["PRODUCAO", "ABERTURA", "DESCONGELAMENTO"]),
         "id_produto": Param("integer", "Produto (dispensado com `id_origem`).", no_corpo=True),
         "id_origem": Param("integer", "Etiqueta que está sendo reetiquetada.", no_corpo=True),
         "id_producao": Param("integer", "Produção de onde saiu (de `producoes_feitas`).",
                              no_corpo=True),
         "copias": Param("integer", "Quantas etiquetas.", padrao=1, no_corpo=True, minimo=1),
         "quantidade": Param("number", "Quanto há em cada pote, na unidade de estoque.",
                             no_corpo=True),
         "conservacao": Param("string", "Como vai ser guardado (a regra do produto diz as "
                                        "que existem).", no_corpo=True),
         "id_local": Param("integer", "Onde fica guardado.", no_corpo=True),
         "validade_fabricante": Param("string", "Validade da embalagem, AAAA-MM-DD.",
                                      no_corpo=True),
         "observacao": Param("string", "Recado na etiqueta.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "usar_etiqueta", "Dar baixa em uma etiqueta: usei tudo",
        "Marca o pote como usado por inteiro. A etiqueta sai da lista das ativas.",
        "/etiquetas/{id_etiqueta}/usar",
        {"id_etiqueta": Param("integer", "Id da etiqueta (de `etiquetas`).", obrigatorio=True),
         "observacao": Param("string", "Recado.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "usar_parte_da_etiqueta", "Usar uma parte do pote",
        "Tira uma parte do pote: a etiqueta continua ativa com o que sobrou.",
        "/etiquetas/{id_etiqueta}/usar-parte",
        {"id_etiqueta": Param("integer", "Id da etiqueta.", obrigatorio=True),
         "quantidade": Param("number", "Quanto foi usado, na unidade da etiqueta.",
                             obrigatorio=True, no_corpo=True),
         "observacao": Param("string", "Recado.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "descartar_etiqueta", "Descartar um pote",
        "Descarta o que resta no pote. Com `lancar_perda`, a quantidade sai do estoque como "
        "perda, pelo motivo informado.",
        "/etiquetas/{id_etiqueta}/descartar",
        {"id_etiqueta": Param("integer", "Id da etiqueta.", obrigatorio=True),
         "lancar_perda": Param("boolean", "Baixar do estoque como perda.", no_corpo=True),
         "id_motivo_perda": Param("integer", "Motivo (de `motivos_de_perda`).", no_corpo=True),
         "motivo": Param("string", "O que aconteceu.", no_corpo=True),
         "quantidade": Param("number", "Quanto descartar; sem ela, o que resta no pote.",
                             no_corpo=True)},
        metodo="POST"),

    Ferramenta(
        "receber_transferencia", "Receber uma remessa de outra loja",
        "Confirma o recebimento de uma remessa: o estoque entra na loja de destino. Sem "
        "`itens`, recebe tudo como foi enviado.",
        "/transferencias/{id_transferencia}/receber",
        {"id_transferencia": Param("integer", "Id da remessa (de `transferencias`).",
                                   obrigatorio=True),
         "itens": Param(
             "array", "Só quando chegou diferente do enviado.", no_corpo=True,
             itens={"type": "object",
                    "properties": {
                        "id_item": {"type": "integer",
                                    "description": "A linha da remessa (de `transferencia`)."},
                        "qtd_recebida": {"type": "number"},
                        "id_motivo_perda": {"type": "integer"},
                        "observacao": {"type": "string"}},
                    "required": ["id_item"]}),
         "observacao": Param("string", "Recado sobre o recebimento.", no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "cancelar_transferencia", "Cancelar uma remessa",
        "Cancela uma remessa que ainda não foi recebida: a mercadoria volta para a origem.",
        "/transferencias/{id_transferencia}/cancelar",
        {"id_transferencia": Param("integer", "Id da remessa.", obrigatorio=True)},
        metodo="POST"),

    # 🔑 **Produzir pelo conector** (pedido do dono, 08/10/2026). É a mesma rota da
    # tela: exige ficha homologada e a permissão `estoque.saidas`.
    Ferramenta(
        "produzir", "Lançar uma produção",
        "Produz pela ficha técnica HOMOLOGADA do produto: baixa os insumos do estoque e dá "
        "entrada no produzido, pelo custo do que realmente saiu. ⚠️ **Mexe no estoque e o "
        "razão não se apaga** — desfazer é estornar movimento por movimento. Antes de "
        "chamar: mostre à pessoa a prévia de `necessario_para_produzir` (o que vai sair e o "
        "que falta) com a MESMA quantidade e medida, e só produza depois do sim.",
        "/estoque/producoes",
        {"id_produto": Param("integer", "Produto a produzir (precisa ter ficha homologada).",
                             obrigatorio=True, no_corpo=True),
         "quantidade": Param("number", "Quanto produzir, na `medida` escolhida. Maior que "
                                       "zero.", obrigatorio=True, no_corpo=True),
         "medida": Param("string", "A quantidade está em quê: PORCOES é a unidade de estoque "
                                   "do produto, RECEITAS são voltas inteiras da ficha, "
                                   "RENDIMENTO é a unidade em que a receita rende (5 KG de "
                                   "uma receita de 10 KG). ⚠️ Pergunte quando a pessoa não "
                                   "disser: \"2\" pode ser dois cookies ou duas receitas "
                                   "de 65.", padrao="PORCOES", no_corpo=True,
                         enum=["PORCOES", "RECEITAS", "RENDIMENTO"]),
         "id_local": Param("integer", "Prateleira de quem produz (de `locais`): os insumos "
                                      "saem dela primeiro. Sem ele, a padrão da loja.",
                           no_corpo=True),
         "id_modo": Param("integer", "Modo de rendimento da ficha, se houver mais de um.",
                          no_corpo=True),
         "observacao": Param("string", "Recado sobre esta produção.", no_corpo=True),
         "consumos": Param(
             "array", "Só quando o que SAIU foi diferente da receita (usou 6 ovos em vez "
                      "de 5). Uma linha por item corrigido; o resto segue a ficha.",
             no_corpo=True,
             itens={"type": "object",
                    "properties": {
                        "id_item": {"type": "integer",
                                    "description": "A LINHA da receita (`id_item` em "
                                                   "`necessario_para_produzir`), não o "
                                                   "produto."},
                        "quantidade": {"type": "number",
                                       "description": "Quanto realmente saiu. Zero = não "
                                                      "usei."},
                        "um": {"type": "string",
                               "description": "Unidade do que foi digitado; sem ela, a de "
                                              "estoque do insumo."}},
                    "required": ["id_item", "quantidade"]})},
        metodo="POST"),
    Ferramenta(
        "reprocessar_estoque", "Reprocessar o estoque de um produto",
        "Relê o razão de UM produto em ordem de data e refaz o que é derivado: saldo e "
        "custo médio de cada prateleira e o custo das saídas. É o acerto para lançamento "
        "retroativo (a nota do dia 9 que entrou depois da venda do dia 12). "
        "⚠️ **Sempre em dois passos**: chame primeiro SEM `aplicar` — é a prévia, não grava "
        "nada e mostra o que mudaria —, apresente à pessoa e só então chame com "
        "`aplicar: true`. Reescreve número que alguém já leu.",
        "/estoque/reprocessar",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True, no_corpo=True),
         "aplicar": Param("boolean", "false (padrão) = só a prévia. true = grava.",
                          padrao=False, no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "incluir_local_do_produto", "Pôr o produto em mais uma prateleira",
        "Diz que o produto também mora nesta prateleira (de `locais`), na loja. Não lança "
        "nada no estoque: a prateleira entra com saldo zero e passa a aparecer na contagem. "
        "Repetir não duplica. Para várias prateleiras, chame uma vez para cada.",
        "/produtos/{id_produto}/locais",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True),
         "id_local": Param("integer", "A prateleira (de `locais`).", obrigatorio=True,
                           no_corpo=True)},
        metodo="POST"),
    Ferramenta(
        "tirar_local_do_produto", "Tirar o produto de uma prateleira",
        "O produto deixa de morar nesta prateleira. ⚠️ Só com ela VAZIA: com saldo, o "
        "servidor recusa — transferir ou lançar a saída é na tela.",
        "/produtos/{id_produto}/locais/{id_local}",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True),
         "id_local": Param("integer", "A prateleira (de `locais_do_produto`).",
                           obrigatorio=True)},
        metodo="DELETE"),
    Ferramenta(
        "unidades_de_compra", "Unidades de compra do produto",
        "A tabela de conversão: em que unidades o produto é comprado (caixa, fardo, pacote) "
        "e quantas unidades de ESTOQUE vêm em cada.",
        "/produtos/{id_produto}/unidades",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True)}),
    Ferramenta(
        "gravar_unidades_de_compra", "Gravar as unidades de compra do produto",
        "⚠️ SUBSTITUI a tabela inteira: leia `unidades_de_compra` e mande todas as que "
        "ficam, junto com a nova. `fator` = quantas unidades de ESTOQUE vêm em 1 desta (a "
        "caixa com 12 → 12). A unidade de estoque, se entrar, tem fator 1. Só uma pode ser "
        "a padrão, e ela vira a unidade de compra do cadastro. Vale para as próximas notas.",
        "/produtos/{id_produto}/unidades",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True),
         "itens": Param("array", "TODAS as unidades de compra (substitui a lista).",
                        obrigatorio=True, no_corpo=True,
                        itens={"type": "object",
                               "properties": {
                                   "um": {"type": "string",
                                          "description": "Sigla (de `unidades_medida`)."},
                                   "fator": {"type": "number",
                                             "description": "Unidades de estoque em 1 desta."},
                                   "padrao": {"type": "boolean"},
                                   "observacao": {"type": "string"}},
                               "required": ["um", "fator"]})},
        metodo="PUT"),
    Ferramenta(
        "converter_codigo_vinculado", "Conversão do código de um produto vinculado",
        "Quando dois cadastros foram juntados (`fundir_produtos`), os códigos do que saiu "
        "viram apelidos do que ficou — e a nota daquele código passa a entrar como 1 "
        "unidade de estoque. Se o produto que saiu era outra embalagem (o pacote de 500 g "
        "de um produto em KG), diga quantas unidades de estoque vêm em 1 daquele código "
        "(0,5). Os códigos estão em `detalhe_produto` → `codigos_externos` (`sistema` e "
        "`codigo`). ⚠️ Vale da próxima nota em diante; não corrige nota já lançada.",
        "/produtos/{id_produto}/codigos/conversao",
        {"id_produto": Param("integer", "O produto que FICOU.", obrigatorio=True),
         "sistema": Param("string", "O espaço do código (ex.: FORNECEDOR, OMIE), como "
                                    "está em `codigos_externos`.", obrigatorio=True,
                          no_corpo=True),
         "codigo": Param("string", "O código, como está em `codigos_externos`.",
                         obrigatorio=True, no_corpo=True),
         "fator": Param("number", "Unidades de estoque em 1 unidade daquele código.",
                        obrigatorio=True, no_corpo=True)},
        metodo="PUT"),
    Ferramenta(
        "desativar_produto", "Desativar um produto",
        "Tira o produto das buscas e das telas. Produto não se exclui — o histórico dele "
        "(notas, estoque, fichas) continua. Para reativar, `atualizar_produto` com "
        "`ativo: true`. Confirme com a pessoa antes.",
        "/produtos/{id_produto}",
        {"id_produto": Param("integer", "Id do produto.", obrigatorio=True)},
        metodo="DELETE"),
    # -----------------------------------------------------------------------
    # Fichas técnicas pelo Claude
    # -----------------------------------------------------------------------
    # 🔑 **Pedido do dono (24/09/2026):** *"disponibilizar a criação de Fichas
    # Técnicas pelo Claude, pois ela tem muitas fichas em outros arquivos, e isto
    # facilitaria muito a importação/criação destas fichas."* O arquivo (planilha,
    # PDF, foto do caderno) é lido pelo Claude; aqui chega só a receita já
    # traduzida para os ids da casa, pela MESMA rota da tela.
    # ⚠️ **Nasce RASCUNHO, e a homologação fica na TELA.** Rascunho já custeia o
    # prato no CMV (é o degrau reserva da cascata), então a importação serve na
    # hora; mas é a homologação que libera PRODUZIR e congela a receita. Numa
    # leva de dezenas de fichas lidas de arquivo, um "10" que era "100" só
    # aparece quando alguém olha — e é na tela, com o custo do lado, que se olha.
    Ferramenta(
        "criar_ficha_tecnica", "Criar ficha técnica",
        "Cria a ficha técnica (receita) de um produto, como RASCUNHO. Roteiro: "
        "(1) `buscar_produtos` pelo prato — ele tem de ser tipo PRODUZIDO ou KIT; se não "
        "existir, `criar_produto` com tipo PRODUZIDO; (2) `fichas_tecnicas` com o "
        "`id_produto` — se já houver ficha, NÃO crie outra: corrija o rascunho "
        "(`atualizar_ficha_tecnica`) ou abra `nova_versao_da_ficha`; (3) cada ingrediente "
        "vira `id_insumo` via `buscar_produtos` (procure por partes do nome: o cadastro "
        "costuma estar em CAIXA ALTA e abreviado); o que não existir, `criar_produto` — "
        "pergunte à pessoa antes de criar insumo; uma preparação que já tem ficha entra "
        "como `id_subficha`; (4) `um` do item na unidade da receita (`unidades_medida`); "
        "(5) depois de criar, leia `ficha_tecnica` e avise os `itens_sem_custo`; "
        "(6) se o arquivo tem a foto do prato, `enviar_foto_da_ficha`. "
        "⚠️ Homologar é na tela do sistema.",
        "/fichas",
        {"id_produto": Param("integer", "O prato (produto PRODUZIDO ou KIT).",
                             obrigatorio=True, no_corpo=True),
         "rendimento_qtd": Param("number", "Quanto a receita rende.", padrao=1,
                                 no_corpo=True),
         "rendimento_um": Param("string", "Unidade do rendimento (KG, L, UN…).",
                                no_corpo=True),
         "porcoes": Param("number", "Em quantas porções o rendimento se divide.",
                          padrao=1, no_corpo=True),
         "porcao_qtd": Param("number", "Tamanho de UMA porção, na unidade do rendimento.",
                             no_corpo=True),
         "tempo_preparo_min": Param("integer", "Tempo de preparo, em minutos.",
                                    no_corpo=True, minimo=0, maximo=6000),
         "modo_preparo": Param("string", "Modo de preparo, como veio do arquivo.",
                               no_corpo=True),
         "alergenos": Param("string", "Alergênicos.", no_corpo=True),
         "observacao": Param("string", "Observação interna.", no_corpo=True),
         "itens": Param("array", "Os ingredientes, na ordem da receita.", no_corpo=True,
                        itens=_ITEM_DA_FICHA)},
        metodo="POST"),
    Ferramenta(
        "atualizar_ficha_tecnica", "Corrigir uma ficha técnica em rascunho",
        "Altera só os campos informados de uma ficha em RASCUNHO. ⚠️ `itens` SUBSTITUI a "
        "lista inteira: leia `ficha_tecnica` e mande todos os que ficam. Ficha "
        "homologada não se edita — use `nova_versao_da_ficha`.",
        "/fichas/{id_ficha}",
        {"id_ficha": Param("integer", "Id da ficha.", obrigatorio=True),
         "rendimento_qtd": Param("number", "Quanto a receita rende.", no_corpo=True),
         "rendimento_um": Param("string", "Unidade do rendimento.", no_corpo=True),
         "porcoes": Param("number", "Número de porções.", no_corpo=True),
         "porcao_qtd": Param("number", "Tamanho de UMA porção.", no_corpo=True),
         "tempo_preparo_min": Param("integer", "Tempo de preparo, em minutos.",
                                    no_corpo=True, minimo=0, maximo=6000),
         "modo_preparo": Param("string", "Modo de preparo.", no_corpo=True),
         "alergenos": Param("string", "Alergênicos.", no_corpo=True),
         "observacao": Param("string", "Observação interna.", no_corpo=True),
         "itens": Param("array", "TODOS os ingredientes (substitui a lista).",
                        no_corpo=True, itens=_ITEM_DA_FICHA)},
        metodo="PUT"),
    Ferramenta(
        "nova_versao_da_ficha", "Abrir nova versão de uma ficha",
        "Copia uma ficha (itens, modos e foto) para uma versão NOVA em rascunho, para "
        "mudar a receita de um prato que já tem ficha homologada. A vigente continua "
        "valendo até alguém homologar a nova, na tela. Depois, corrija a nova com "
        "`atualizar_ficha_tecnica`.",
        "/fichas/{id_ficha}/nova-versao",
        {"id_ficha": Param("integer", "A ficha de origem.", obrigatorio=True)},
        metodo="POST"),
    Ferramenta(
        "enviar_foto_da_ficha", "Gravar a foto do prato na ficha",
        # 🔑 **Pedido do dono (26/09/2026):** *"ao importar um PDF no Claude de uma ficha
        # técnica, e esta tem foto, permitir gravar esta imagem na ficha."*
        # ⚠️ O modelo NÃO consegue reescrever os bytes de uma imagem que só viu: ele
        # precisa da execução de código do claude.ai para recortá-la do arquivo. Sem
        # ela, a saída é a tela da ficha — e a descrição diz isso, para ele não
        # inventar um base64.
        "Grava a foto do prato pronto na ficha (substitui a que houver). Use quando o "
        "arquivo da ficha (PDF, foto) traz a imagem do prato. Como obter o `imagem_base64`: "
        "com a execução de código, extraia a imagem do arquivo (ex.: PyMuPDF "
        "`page.get_images()`/`extract_image`, ou recorte a página), reduza para no máximo "
        "800 px no lado maior e JPEG qualidade ~75 (fica em poucas dezenas de KB), e "
        "codifique em base64. ⚠️ NUNCA escreva um base64 de memória ou de uma imagem que "
        "você só viu — ele sai corrompido. Sem execução de código, diga à pessoa para "
        "anexar a foto na tela da ficha (Fichas técnicas → a ficha → Foto).",
        "/fichas/{id_ficha}/foto-base64",
        {"id_ficha": Param("integer", "A ficha (a que acabou de ser criada, por exemplo).",
                           obrigatorio=True),
         "imagem_base64": Param("string", "A imagem em base64 (PNG, JPG ou WEBP, até 2 MB). "
                                          "Aceita o prefixo data:image/...;base64,.",
                                obrigatorio=True, no_corpo=True)},
        metodo="PUT"),
    Ferramenta(
        "fundir_produtos", "Juntar dois cadastros do mesmo produto",
        "Funde dois cadastros: o que SAI é absorvido pelo que FICA, e o histórico, os "
        "códigos e os vínculos passam para ele. ⚠️ **Não tem desfazer** — rode "
        "`previa_de_fusao` antes e confirme com a pessoa. Quem sai tem de ser o cadastro "
        "SEM história (sem movimento, ficha, nota ou contagem); o servidor recusa e diz o "
        "que trava quando a direção está invertida.",
        "/produtos/{id_produto}/vincular",
        {"id_produto": Param("integer", "O cadastro que FICA.", obrigatorio=True),
         "id_sai": Param("integer", "O cadastro que SAI.", obrigatorio=True, no_corpo=True),
         "baixar_vendas": Param("boolean", "Baixar do estoque as vendas que o cadastro "
                                           "que sai já tinha feito sem baixar. Deixe "
                                           "ligado: senão a falta aparece depois, sem nome, "
                                           "na primeira contagem.",
                                padrao=True, no_corpo=True)},
        metodo="POST"),
    # 🔑 O "atualizar do Omie" pelo conector (09/10/2026): o da nota e o de todas.
    Ferramenta(
        "atualizar_nota_do_omie", "Atualizar uma nota do Omie",
        "Relê do Omie UMA nota ainda não lançada: traz valor corrigido, item trocado e "
        "nota cancelada lá. Os produtos já vinculados são mantidos.",
        "/notas/{id_nota}/atualizar-do-omie",
        {"id_nota": Param("integer", "Id da nota (de `notas_entrada`).", obrigatorio=True)},
        metodo="POST"),
    Ferramenta(
        "atualizar_notas_abertas_do_omie", "Atualizar do Omie as notas não lançadas",
        "Relê do Omie as notas que ainda NÃO foram lançadas, em LEVAS de até 50: valor "
        "corrigido, item trocado e nota cancelada lá. ⚠️ Cada nota é uma consulta ao Omie, "
        "com espera entre elas. A resposta traz `proximo`: chame de novo passando-o em "
        "`antes_de` até ele vir nulo. Se vier `parou_por_falhas`, PARE — o Omie está "
        "recusando, e insistir prolonga o bloqueio.",
        "/notas/atualizar-do-omie",
        {"antes_de": Param("integer", "O `proximo` da leva anterior. Sem ele, começa da "
                                      "nota mais recente.", no_corpo=True),
         "limite": Param("integer", "Quantas notas nesta leva.", padrao=30, no_corpo=True,
                         minimo=1, maximo=50)},
        metodo="POST"),
    Ferramenta(
        "lancar_nota", "Lançar a nota no estoque",
        "Dá entrada da nota no razão: cada item vira movimento, e o custo médio muda. "
        "⚠️ É o que MAIS pesa desta lista: o razão é append-only, então desfazer é "
        "estornar pela tela, não editar. Confira a conciliação (`nota_entrada`) antes.",
        "/notas/{id_nota}/lancar",
        {"id_nota": Param("integer", "Id da nota.", obrigatorio=True),
         "id_local": Param("integer", "Prateleira de entrada; sem ela, a padrão de cada "
                                      "produto.", no_corpo=True)},
        metodo="POST"),
]

POR_NOME = {f.nome: f for f in FERRAMENTAS}

# ⚠️ `{casa}` é preenchido em `routers/mcp.py` com o nome do cadastro da empresa.
INSTRUCOES = (
    "Sistema de gestão de {casa}: produtos, fichas técnicas, estoque, compras "
    "(notas do Omie), vendas e CMV. Com as permissões do usuário conectado: consulta "
    "sempre; grava (cadastros, fichas, notas, estoque, produção, inventário, etiquetas, "
    "vendas, preços, CMV, reservas, pedidos, fidelidade e catálogos) só "
    "com chave que permite alterar — e toda gravação deve ser confirmada com a pessoa antes. "
    "O que mexe no estoque não se apaga: desfazer é estornar. Onde houver ferramenta de "
    "prévia, mostre a prévia antes de gravar. Dinheiro em reais; quantidades na unidade de estoque do produto; datas "
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
        nome = m.group(1)
        valor = resto.pop(nome)
        # 🔑 **A SIGLA também é chave de caminho** (09/10/2026): a unidade de medida
        # não tem id, e `atualizar_unidade_de_medida` era recusada aqui antes de
        # chegar à rota. ⚠️ Só para parâmetro DECLARADO como texto, e só letra e
        # número: é a mesma guarda de baixo, por outro caminho — barra, ponto ou
        # espaço abririam `../` para outra rota.
        if f.params[nome].tipo == "string":
            # ⚠️ O hífen entra por causa da DATA (`/reservas/dias/2026-10-09`). Ele
            # não monta `../`: o que abre outra rota é barra e ponto, e esses ficam fora.
            if not isinstance(valor, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,20}", valor):
                raise ErroFerramenta(f"`{nome}` precisa ser só letras e números.")
            return valor
        # ⚠️ Só inteiro entra no caminho: string ali abriria `../` para outra rota.
        if not isinstance(valor, int) or isinstance(valor, bool):
            raise ErroFerramenta(f"`{nome}` precisa ser um número inteiro.")
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
    """Executa a ferramenta na própria API, com a credencial de quem pediu.

    🔑 **Por dentro, sem rede**: `httpx.ASGITransport` entrega o pedido ao app no
    mesmo processo. Passa pelos mesmos middlewares e dependências que um pedido
    da tela — `contexto_atual` confere a chave de novo, e é ali que a chave só de
    leitura leva 403 ao tentar gravar. Nenhuma regra de negócio é reescrita aqui.
    """
    f = POR_NOME.get(nome)
    if not f:
        raise ErroFerramenta(f"Ferramenta desconhecida: {nome}")
    caminho, resto = _caminho(f, args or {})
    id_loja = resto.pop("id_loja", None)
    cabecalhos = {"Authorization": f"Bearer {credencial}", "Accept": "application/json"}
    if id_loja is not None:
        cabecalhos["X-Unidade"] = str(id_loja)

    # ⚠️ **Só o que o modelo MANDOU vai no corpo.** O `PUT` de produto grava com
    # `exclude_unset`: mandar os não informados como nulo apagaria campo que
    # ninguém pediu para apagar.
    corpo = {k: resto.pop(k) for k in list(resto)
             if f.params.get(k) and f.params[k].no_corpo}
    corpo = {k: v for k, v in corpo.items() if v is not None}

    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://botane.interno",
                                 timeout=120) as cliente:
        r = await cliente.request(f.metodo, caminho, params=_query({**f.fixos, **resto}),
                                  headers=cabecalhos,
                                  json=corpo if f.grava else None)

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
