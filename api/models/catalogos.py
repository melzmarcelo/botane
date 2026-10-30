"""O que entra e o que sai do cadastro de catálogos.

⚠️ **Nada de `body: dict`** — é regra da casa, e aqui ela vale dobrado: os
campos deste cadastro vão parar no site do cliente, e um campo com nome errado
que o servidor ignora em silêncio é uma promessa que a tela faz e o site não
cumpre.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

# 🔑 **Uma origem só, por enquanto** (pedido do dono, 21/09/2026: *"neste
# momento somente vamos ter PDF"*). A tupla existe para o dia da segunda: quem
# acrescentar aqui ganha a validação e a tela junto, sem caçar `== "PDF"`
# espalhado pelo código.
#
# ⚠️ **PDF é ARQUIVO, não `PDV`.** A origem é um PDF importado e mostrado no
# site de reservas; o PDV é o caixa e vive em `services/pdv/`. As três letras
# parecidas já custaram uma primeira versão inteira deste módulo.
# 🔑 **A segunda origem chegou** (pedido do dono, 22/09/2026: *"vamos adicionar
# a Origem Produtos"*), e a tupla fez o trabalho para o qual foi escrita: quem
# acrescenta aqui ganha a validação e a tela junto, sem caçar `== "PDF"` pelo
# código. `PRODUTOS` é o cardápio montado aqui dentro — categorias,
# subcategorias e os produtos de cada uma.
ORIGENS = ("PDF", "PRODUTOS")

# 🔑 **A origem que monta o cardápio aqui dentro.** Vale a constante em vez do
# literal: é ela que decide se a tela abre a página de configuração ou o envio
# de PDF, e um `== "PRODUTOS"` solto em cinco lugares envelhece mal.
ORIGEM_PRODUTOS = "PRODUTOS"

# RASCUNHO nasce; ATIVO publica; INATIVO guarda sem apagar.
SITUACOES = ("RASCUNHO", "ATIVO", "INATIVO")


class CatalogoBase(BaseModel):
    """O cabeçalho do catálogo — a capa do que a casa publica."""

    # ⚠️ **`min_length=2`**: "A" não identifica catálogo nenhum numa lista, e
    # este nome é o que o cliente lê no site.
    nome: str = Field(min_length=2, max_length=120)
    origem: str = "PDF"
    publica_de: date | None = None
    publica_ate: date | None = None
    situacao: str = "RASCUNHO"
    observacao: str | None = None
    # 🔑 **O cliente se identifica antes de abrir** (migração 086, pedido do dono
    # 24/09/2026). Quem garante é o servidor: a lista pública não entrega o
    # conteúdo deste catálogo, e sim um pedido de identificação.
    exige_cadastro: bool = False
    # 🔑 **Visível nas lojas** (migração 087, pedido do dono 24/09/2026). Nulo na
    # criação = só a loja dona, que é o que o site sempre fez.
    lojas: list[int] | None = None

    @model_validator(mode="after")
    def _coerente(self):
        if self.origem not in ORIGENS:
            raise ValueError(
                f"Origem desconhecida: {self.origem}. "
                f"Por enquanto só existe {', '.join(ORIGENS)}.")
        if self.situacao not in SITUACOES:
            raise ValueError(
                f"Situação desconhecida: {self.situacao}. "
                f"As que existem: {', '.join(SITUACOES)}.")
        # ⚠️ **Só compara com as DUAS pontas preenchidas.** Uma nula quer dizer
        # "sem começo" ou "sem prazo", e recusar isso obrigaria a inventar um
        # "até 2099" para o cardápio permanente da casa.
        if (self.publica_de and self.publica_ate
                and self.publica_ate < self.publica_de):
            raise ValueError(
                "O fim da publicação não pode ser antes do começo — o catálogo "
                "sairia do ar antes de entrar.")
        return self


class CatalogoCreate(CatalogoBase):
    pass


class CatalogoUpdate(BaseModel):
    """A alteração: tudo opcional, porque a tela salva o que mudou.

    ⚠️ **Não herda de `CatalogoBase`.** Herdando, os campos obrigatórios dela
    continuariam obrigatórios aqui, e mudar só a situação exigiria reenviar o
    nome — que é como um PUT acaba apagando o que ninguém tocou.
    """

    nome: str | None = Field(default=None, min_length=2, max_length=120)
    origem: str | None = None
    publica_de: date | None = None
    publica_ate: date | None = None
    situacao: str | None = None
    observacao: str | None = None
    exige_cadastro: bool | None = None
    lojas: list[int] | None = None
    # 🔑 O WhatsApp que atende este catálogo (143), um da loja dona; nulo = o principal.
    id_whatsapp: int | None = None
    # O botão "entre em contato" no cabeçalho do catálogo (site e Cardápio Vivo).
    permite_contato: bool | None = None


class CatalogoResponse(BaseModel):
    id: int
    nome: str
    origem: str
    publica_de: date | None = None
    publica_ate: date | None = None
    situacao: str
    observacao: str | None = None
    exige_cadastro: bool = False
    # As lojas em que o CLIENTE vê este catálogo no site.
    lojas: list[int] = []
    # 🔑 **Se ele está no ar HOJE**, que é a pergunta que a lista responde de
    # relance. Não é `situacao == 'ATIVO'`: um catálogo ativo cujo período já
    # passou não está publicado, e mostrar os dois como iguais faria a casa
    # procurar no site um cardápio que saiu do ar sozinho.
    publicado_hoje: bool = False
    criado_por: str | None = None
    # 🔑 **O PDF que o site exibe** (migração 080). `arquivo_url` é o endereço
    # público; os bytes moram em `arquivos`, e quem lê daqui não sabe disso.
    arquivo_url: str | None = None
    # ⚠️ O nome ORIGINAL, porque a URL leva sufixo aleatório e não diz mais qual
    # PDF é aquele.
    arquivo_nome: str | None = None
    arquivo_bytes: int | None = None
    arquivo_em: datetime | None = None
    # O resumo do cardápio montado: pratos, sem foto, sem descrição, inativos.
    resumo: dict | None = None
    # É o Cardápio Vivo (o feed da mesa) de alguma loja.
    cardapio_vivo: bool = False
    # 143: o WhatsApp do catálogo (nulo = o principal da loja) e o botão de contato.
    id_whatsapp: int | None = None
    permite_contato: bool = False


# ---------------------------------------------------------------------------
# O catálogo montado por PRODUTOS
# ---------------------------------------------------------------------------
#
# 🔑 **Pedido do dono (22/09/2026):** *"podemos criar Categorias (exemplo: Menu
# Principal) e suas SubCategorias (exemplo: Pra Dividir), cada item terá o Nome,
# Descrição e uma foto. Após isto, podemos vincular os produtos disponíveis no
# PDV para a subcategoria. Somente produtos ativos."*


class SecaoBase(BaseModel):
    """O que categoria e subcategoria têm em comum: nome, descrição e ordem.

    ⚠️ **A FOTO não está aqui.** Ela sobe por rota própria, multipart, como a do
    produto e a do catálogo — um campo de arquivo dentro do formulário faria
    cada renomeação carregar a imagem inteira de novo.
    """

    nome: str = Field(min_length=2, max_length=120)
    descricao: str | None = Field(default=None, max_length=500)
    # ⚠️ **A ordem é do CARDÁPIO, não alfabética**: "Entradas" antes de
    # "Sobremesas" é a sequência da refeição, e só a casa sabe qual é.
    ordem: int = Field(default=0, ge=0, le=999)
    # 121: a seção abre com tela própria no Cardápio Vivo. ⚠️ Nulo = NÃO MUDA: a janela
    # antiga (e a do conector) que não manda o campo não religa a abertura que a casa desligou.
    abertura: bool | None = None


class CategoriaCreate(SecaoBase):
    pass


class SubcategoriaCreate(SecaoBase):
    pass


class ItemCreate(BaseModel):
    """Um produto pendurado na categoria ou na subcategoria.

    🔑 **`id_subcategoria` é opcional** (decisão do dono): categoria pode ter
    produto direto. Cardápio de verdade tem os dois casos — "Menu Principal" se
    divide em "Pra Dividir" e "Pratos", mas "Bebidas" costuma ser uma lista só.
    ⚠️ **Quem garante que a subcategoria é DESTA categoria é o banco**, pela
    chave composta da migração 084 — não esta validação.
    """

    id_produto: int
    id_subcategoria: int | None = None
    ordem: int = Field(default=0, ge=0, le=999)


class OpcaoDaEscolha(BaseModel):
    """Uma opção do item de escolha (142): um PRODUTO, com rótulo curto opcional."""

    id_produto: int
    rotulo: str | None = Field(default=None, max_length=60)


class EscolhaCreate(BaseModel):
    """Item de ESCOLHA (142): não é produto — o cliente escolhe UMA das opções.

    🔑 Pedido do dono (29/10/2026): "Chocolate Quente → Preto ou Branco"; "Monte sua
    cesta → Pequena, Média, Grande". A lista vai INTEIRA a cada gravação, na ordem.
    """

    nome: str = Field(min_length=1, max_length=120)
    descricao: str | None = Field(default=None, max_length=2000)
    id_subcategoria: int | None = None
    opcoes: list[OpcaoDaEscolha] = Field(min_length=2, max_length=30)


class ItemLugar(BaseModel):
    """Para onde o prato vai: outra seção do MESMO catálogo.

    🔑 Mover não é tirar e pôr: o item leva junto destaque, esgotado, objetivo e
    margem (15/10/2026). Nulo em `id_subcategoria` = direto na categoria.
    """

    id_categoria: int
    id_subcategoria: int | None = None


class ItemOrdem(BaseModel):
    """Reordenar sem recriar: só o que mudou de lugar."""

    id: int
    ordem: int = Field(ge=0, le=999)
