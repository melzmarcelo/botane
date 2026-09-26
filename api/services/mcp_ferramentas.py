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
         "medida": Param("string", "A quantidade está em quê.", padrao="PORCOES",
                         enum=["PORCOES", "RENDIMENTO"]),
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

INSTRUCOES = (
    "Sistema de gestão do Botané Deli & Café: produtos, fichas técnicas, estoque, compras "
    "(notas do Omie), vendas e CMV. Com as permissões do usuário conectado: consulta "
    "sempre; grava (cadastro, fichas, notas) só com chave que permite alterar — e toda "
    "gravação deve ser confirmada com a pessoa antes. Dinheiro em reais; quantidades na unidade de estoque do produto; datas "
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
