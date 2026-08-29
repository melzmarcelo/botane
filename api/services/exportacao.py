"""Exportação: a MESMA declaração de relatório, em planilha ou em PDF.

Três detalhes decidem se o CSV abre certo no Excel ou vira uma coluna só de lixo:

1. **Separador `;`** — é o que o Excel em pt-BR espera; a vírgula ele usa como
   decimal.
2. **BOM no começo** — sem ele o Excel lê UTF-8 como Latin-1 e o "ç" vira "Ã§".
3. **Número com vírgula decimal** e sem separador de milhar, senão o Excel
   trata como texto e nenhuma soma funciona.

🔑 **`csv_de` e `pdf_de` têm a MESMA assinatura, e isso não é simetria por
estética.** Os nove relatórios da casa já se declaravam como
`(linhas, colunas, título, resumo)` — então o PDF não foi nove trabalhos, foi
um. Relatório novo nasce com os dois formatos sem que ninguém escreva nada a
mais; e enquanto os dois lerem a mesma declaração, é impossível a planilha e o
PDF discordarem sobre o que o relatório contém.
"""

import csv
import io
from datetime import date, datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

BOM = "﻿"

# ⚠️ Teto do PDF: o razão de uma base real tem centenas de milhares de
# movimentos, e o PDF disso é um arquivo de milhares de páginas que ninguém
# abre e que estoura o tempo da requisição no meio. Acima daqui a resposta é
# uma FRASE mandando usar a planilha — que não tem teto —, nunca um arquivo
# quebrado ou um pedaço do relatório calado.
MAXIMO_PDF = 5000


def _valor(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "sim" if v else "não"
    if isinstance(v, (Decimal, float, int)) and not isinstance(v, bool):
        # Vírgula decimal, sem milhar: é o que o Excel pt-BR soma.
        return f"{v}".replace(".", ",")
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    return str(v)


def csv_de(linhas: list[dict], colunas: list[tuple[str, str]],
           titulo: str | None = None, resumo: list[tuple[str, object]] | None = None,
           anexos: list[tuple] | None = None,
           notas: list[tuple[str, str]] | None = None) -> str:
    """`colunas` = [(chave_no_dict, "Cabeçalho na planilha"), ...].

    `anexos` = [(linhas, colunas, titulo, resumo), ...] — o segundo quadro do
    mesmo arquivo. ⚠️ Dois relatórios da casa são compostos de propósito: o do
    contador leva a apuração **e** a margem por prato; o da reunião com o
    fornecedor leva a evolução de preço **e** o peso por setor. São dois
    quadros que se leem juntos, e separá-los em dois arquivos faria quem
    recebe ter de juntar de novo.
    """
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n",
                          quoting=csv.QUOTE_MINIMAL)

    if titulo:
        escritor.writerow([titulo])
        escritor.writerow([f"Botané Deli e Café — gerado em "
                           f"{datetime.now().strftime('%d/%m/%Y %H:%M')}"])
        escritor.writerow([])
    if resumo:
        for rotulo, valor in resumo:
            escritor.writerow([rotulo, _valor(valor)])
        escritor.writerow([])

    escritor.writerow([cab for _chave, cab in colunas])
    for linha in linhas:
        escritor.writerow([_valor(linha.get(chave)) for chave, _cab in colunas])

    # ⚠️ Texto CORRIDO, não tabela: o modo de preparo de uma ficha técnica é
    # um parágrafo, e espremê-lo numa coluna o tornaria ilegível nos dois
    # formatos. Vem depois das linhas porque é o que se lê DEPOIS de saber os
    # ingredientes.
    for rotulo, corpo in (notas or []):
        if not (corpo or "").strip():
            continue
        escritor.writerow([])
        escritor.writerow([rotulo])
        escritor.writerow([corpo])

    texto = BOM + saida.getvalue()
    for a_linhas, a_colunas, a_titulo, a_resumo in (anexos or []):
        # ⚠️ O BOM do anexo SAI: ele só vale no começo do arquivo, e um BOM
        # solto no meio vira um caractere invisível numa célula do Excel.
        texto += "\r\n" + csv_de(a_linhas, a_colunas, a_titulo, a_resumo).lstrip(BOM)
    return texto


def nome_arquivo(base: str, inicio: date | None = None, fim: date | None = None,
                 ext: str = "csv") -> str:
    pedaco = ""
    if inicio and fim:
        pedaco = f"-{inicio.strftime('%Y%m%d')}-a-{fim.strftime('%Y%m%d')}"
    elif inicio:
        pedaco = f"-{inicio.strftime('%Y%m%d')}"
    return f"botane-{base}{pedaco}-{date.today().strftime('%Y%m%d')}.{ext}"


# ---------------------------------------------------------------------------
# PDF — o mesmo relatório, feito para LER
# ---------------------------------------------------------------------------

# A identidade da casa, a mesma de `web/app/globals.css`.
_TINTA = colors.HexColor("#14201a")
_SUAVE = colors.HexColor("#5d6c61")
_LINHA = colors.HexColor("#d8ded0")
_FUNDO = colors.HexColor("#edf0e7")
_ERVA = colors.HexColor("#2c6a4a")


def quantidade_br(v, um: str | None = None) -> str:
    """1.0000 → "1"; 0.1200 → "0,12"; 12.5 → "12,5". Com `um`, junta a unidade.

    ⚠️ Existe porque texto MONTADO à mão escapa da formatação. A ficha técnica
    dizia `Rendimento;1.0000 UN` — ponto decimal e quatro zeros, no meio de um
    CSV que usa vírgula em todo o resto. O valor tinha virado string antes de
    passar por `_valor`, e nenhuma das duas formatações o alcançava.
    ⚠️ Os zeros à direita SAEM: "1,0000 UN" de rendimento não informa mais que
    "1 UN" — só ocupa a linha e sugere uma precisão que não existe ali.
    """
    if v is None:
        return ""
    d = Decimal(str(v)).normalize()
    if d == d.to_integral_value():
        d = d.quantize(Decimal(1))
    texto = f"{d:f}".replace(".", ",")
    return f"{texto} {um}".strip() if um else texto


def milhar(inteiro: str) -> str:
    grupos: list[str] = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    return ".".join(grupos)


def _numero_br(v) -> str:
    """1284532.1 → "1.284.532,10"; 2 → "2".

    ⚠️ O número sai formatado DIFERENTE do CSV, e isso parece incoerência sem
    ser: a planilha precisa de vírgula decimal **sem** separador de milhar (com
    ponto de milhar o Excel lê como texto e nenhuma soma funciona). O PDF é
    para o olho, e "1.284.532,10" se lê enquanto "1284532,1" não.

    ⚠️ **`int` é CONTAGEM e não leva casa decimal.** O resumo dizia
    "Linhas 2,00", que é a mesma régua de dinheiro aplicada a uma coisa que se
    conta. O tipo já separa os dois na origem: contagem chega de um `len()`,
    dinheiro chega do banco como `Decimal`.
    """
    if isinstance(v, int) and not isinstance(v, bool):
        return ("-" if v < 0 else "") + milhar(str(abs(v)))
    d = Decimal(str(v))
    # Dinheiro tem duas casas; quantidade pode ter três (0,125 KG de fermento).
    casas = 2 if d == d.quantize(Decimal("0.01")) else 3
    inteiro, _, frac = f"{abs(d):.{casas}f}".partition(".")
    return ("-" if d < 0 else "") + milhar(inteiro) + "," + frac


def _valor_pdf(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "sim" if v else "não"
    if isinstance(v, (Decimal, float, int)):
        return _numero_br(v)
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    return str(v)


def _escapar(texto: str) -> str:
    """O texto vai dentro de um `Paragraph`, que interpreta marcação."""
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _e_numerica(linhas: list[dict], chave: str) -> bool:
    """Coluna de número alinha à DIREITA — é assim que uma coluna se confere."""
    viu = False
    for linha in linhas:
        v = linha.get(chave)
        if v is None or v == "":
            continue
        if isinstance(v, bool) or not isinstance(v, (Decimal, float, int)):
            return False
        viu = True
    return viu


def _larguras(linhas: list[dict], colunas: list[tuple[str, str]],
              disponivel: float) -> list[float]:
    """Cada coluna pesa o que o conteúdo dela ocupa, com piso e TETO.

    ⚠️ Sem teto, um campo de observação de 300 caracteres come a página inteira
    e as colunas de número ficam com 4 mm de largura — o relatório ilegível que
    a lição do `<th>` de largura fixa já tinha ensinado a evitar na tela.
    ⚠️ A medida sai de uma AMOSTRA: percorrer 400.000 linhas só para medir texto
    custaria mais que desenhar o documento.
    """
    pesos = []
    for chave, cabecalho in colunas:
        maior = len(cabecalho)
        for linha in linhas[:400]:
            maior = max(maior, len(_valor_pdf(linha.get(chave))))
        pesos.append(min(max(maior, 6), 34))
    total = sum(pesos)
    return [disponivel * p / total for p in pesos]


def _junta_rodape(emitido_por: str | None) -> str:
    """"emitido por Fulano em 29/08/2026 11:52" — ou só a data, sem o nome."""
    quando = datetime.now().strftime("%d/%m/%Y %H:%M")
    return f"emitido por {emitido_por} em {quando}" if emitido_por else f"emitido em {quando}"


class _CanvasNumerado(rl_canvas.Canvas):
    """"Página 3" sozinha não diz se o relatório acabou.

    O total de páginas só existe depois de o documento inteiro ser desenhado —
    por isso as páginas ficam guardadas e o rodapé é escrito no fim, quando o
    número total já é conhecido.
    """

    def __init__(self, *args, **kwargs):
        self._rodape = kwargs.pop("rodape")
        super().__init__(*args, **kwargs)
        self._paginas: list[dict] = []

    def showPage(self):
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._paginas)
        for estado in self._paginas:
            self.__dict__.update(estado)
            self._rodape(self, self._pageNumber, total)
            super().showPage()
        super().save()


def pdf_de(linhas: list[dict], colunas: list[tuple[str, str]],
           titulo: str | None = None, resumo: list[tuple[str, object]] | None = None,
           subtitulo: str | None = None, anexos: list[tuple] | None = None,
           notas: list[tuple[str, str]] | None = None,
           orientacao: str = "auto", empresa: dict | None = None,
           emitido_por: str | None = None) -> bytes:
    """`colunas` = [(chave_no_dict, "Cabeçalho"), ...] — igual ao `csv_de`.

    `anexos` = [(linhas, colunas, titulo, resumo), ...], como no `csv_de`.

    `empresa` = {"nome", "linhas", "logo"} de `exportacao_catalogo.papel_timbrado`.
    `emitido_por` = o nome de quem pediu o arquivo.

    ⚠️ **O PDF sai da tela e circula** — vira anexo de e-mail, papel na mesa do
    contador, foto no grupo. Sem o timbre ele não diz de que casa é; sem o
    rodapé não diz quem o emitiu nem quando, e um relatório sem essas duas
    coisas não se confere contra nada.
    """
    # ⚠️ Paisagem por CONTAGEM DE COLUNAS, não por gosto: a movimentação do
    # estoque tem 14 colunas, e em retrato cada uma ficaria com 13 mm.
    # ⚠️ Vale o quadro MAIS LARGO do arquivo, anexo incluído: a orientação é do
    # documento inteiro, e decidir pelo primeiro quadro espremeria o segundo.
    mais_colunas = max([len(colunas)] + [len(c) for _l, c, _t, _r in (anexos or [])])
    # ⚠️ `orientacao` existe para o documento que tem FORMA por convenção: a
    # ficha técnica é um cartão de receita, e sai em retrato mesmo com uma
    # coluna a mais que o corte automático. Relatório de tabela continua no
    # "auto" — quem decide lá é a largura, não o costume.
    paisagem = (mais_colunas > 7 if orientacao == "auto" else orientacao == "paisagem")
    pagina = landscape(A4) if paisagem else A4
    margem = 12 * mm

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=pagina,
        leftMargin=margem, rightMargin=margem, topMargin=margem, bottomMargin=16 * mm,
        title=titulo or "Botané", author="Botané Deli e Café",
    )

    normal = ParagraphStyle("corpo", fontName="Helvetica", fontSize=7.5, leading=9.5,
                            textColor=_TINTA)
    direita = ParagraphStyle("corpoDir", parent=normal, alignment=2)
    cab_esq = ParagraphStyle("cab", fontName="Helvetica-Bold", fontSize=7, leading=8.5,
                             textColor=_SUAVE)
    cab_dir = ParagraphStyle("cabDir", parent=cab_esq, alignment=2)

    largura = pagina[0] - 2 * margem
    historia: list = []

    def timbre() -> None:
        """Logo à esquerda, dados da casa à direita, e um fio fechando."""
        if not empresa or not empresa.get("nome"):
            return
        texto = [Paragraph(_escapar(empresa["nome"]), ParagraphStyle(
            "casa", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=_TINTA))]
        for l in empresa.get("linhas") or []:
            texto.append(Paragraph(_escapar(l), ParagraphStyle(
                "casaLinha", fontName="Helvetica", fontSize=7.5, leading=10,
                textColor=_SUAVE)))

        celula_logo = ""
        caminho = empresa.get("logo")
        if caminho:
            # ⚠️ Altura fixa e largura pela PROPORÇÃO: logo esticada é pior que
            # logo nenhuma, e cada casa manda a sua no formato que tiver.
            try:
                largura_img, altura_img = ImageReader(str(caminho)).getSize()
                alta = 14 * mm
                celula_logo = Image(str(caminho), width=alta * largura_img / altura_img,
                                    height=alta)
            except Exception:
                # ⚠️ Arquivo ilegível não derruba o relatório: o cabeçalho sai
                # sem a logo. No App Platform a pasta é efêmera e some a cada
                # deploy — é um estado normal, não um erro.
                celula_logo = ""

        cabecalho = Table([[celula_logo, texto]],
                          colWidths=[22 * mm if celula_logo else 0, largura -
                                     (22 * mm if celula_logo else 0)],
                          hAlign="LEFT")
        cabecalho.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, 0), 0),
            ("LEFTPADDING", (1, 0), (1, 0), 4 if celula_logo else 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, _LINHA),
        ]))
        historia.append(cabecalho)
        historia.append(Spacer(1, 5 * mm))

    def bloco(b_linhas, b_colunas, b_titulo, b_resumo, principal: bool) -> None:
        if b_titulo:
            historia.append(Paragraph(_escapar(b_titulo), ParagraphStyle(
                "titulo", fontName="Helvetica-Bold", fontSize=14 if principal else 11,
                leading=17 if principal else 14, textColor=_TINTA)))
        if principal:
            # ⚠️ Com o timbre em cima, o subtítulo padrão diria de novo o nome
            # da casa e a data — e a data agora mora no rodapé, ao lado de quem
            # emitiu. Repetido em dois lugares, o dado envelhece num deles.
            padrao = None if empresa else (
                f"Botané Deli e Café — gerado em "
                f"{datetime.now().strftime('%d/%m/%Y às %H:%M')}")
            if subtitulo or padrao:
                historia.append(Paragraph(_escapar(subtitulo or padrao), ParagraphStyle(
                    "sub", fontName="Helvetica", fontSize=8, leading=11,
                    textColor=_SUAVE)))
        historia.append(Spacer(1, 6 * mm))

        if b_resumo:
            # O resumo é o que se lê primeiro — e em vários relatórios é a
            # única coisa que se lê. Fica em caixa, antes da tabela.
            celulas = [[Paragraph(_escapar(str(rot)), cab_esq),
                        Paragraph(_escapar(_valor_pdf(val)), normal)] for rot, val in b_resumo]
            caixa = Table(celulas, colWidths=[48 * mm, 58 * mm], hAlign="LEFT")
            caixa.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), _FUNDO),
                ("BOX", (0, 0), (-1, -1), 0.5, _LINHA),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            historia.append(KeepTogether(caixa))
            historia.append(Spacer(1, 6 * mm))

        if not b_linhas:
            # ⚠️ Página vazia não explica nada, e quem baixou vai achar que o
            # sistema falhou em vez de que o filtro não achou ninguém.
            historia.append(Paragraph("Nenhuma linha para o filtro escolhido.", normal))
            return

        numericas = {chave: _e_numerica(b_linhas, chave) for chave, _ in b_colunas}
        dados = [[Paragraph(_escapar(cab), cab_dir if numericas[chave] else cab_esq)
                  for chave, cab in b_colunas]]
        for linha in b_linhas:
            dados.append([
                Paragraph(_escapar(_valor_pdf(linha.get(chave))),
                          direita if numericas[chave] else normal)
                for chave, _cab in b_colunas
            ])
        tabela = Table(dados, colWidths=_larguras(b_linhas, b_colunas, largura),
                       repeatRows=1, hAlign="LEFT")
        tabela.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _FUNDO),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, _ERVA),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, _LINHA),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        historia.append(tabela)

    timbre()
    bloco(linhas, colunas, titulo, resumo, principal=True)
    for a_linhas, a_colunas, a_titulo, a_resumo in (anexos or []):
        historia.append(Spacer(1, 10 * mm))
        bloco(a_linhas, a_colunas, a_titulo, a_resumo, principal=False)

    # As notas fecham o documento. ATENCAO: a quebra de linha do texto tem de
    # virar `<br/>` — o `Paragraph` do reportlab ignora a quebra crua e junta
    # tudo num paragrafo so; um modo de preparo numerado sairia em bloco
    # corrido.
    for rotulo, corpo in (notas or []):
        if not (corpo or "").strip():
            continue
        historia.append(Spacer(1, 8 * mm))
        historia.append(Paragraph(_escapar(rotulo), ParagraphStyle(
            "nota", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=_TINTA)))
        historia.append(Spacer(1, 2 * mm))
        quebrado = _escapar(corpo).replace(chr(13) + chr(10), chr(10)).replace(chr(10), "<br/>")
        historia.append(Paragraph(
            quebrado,
            ParagraphStyle("notaCorpo", fontName="Helvetica", fontSize=9, leading=13,
                           textColor=_TINTA)))

    # ⚠️ O carimbo é calculado UMA vez, fora do rodapé: `_CanvasNumerado`
    # redesenha o rodapé de cada página no fim, e chamar `now()` ali daria
    # horários diferentes entre a página 1 e a 40 do mesmo arquivo.
    emissao = _junta_rodape(emitido_por)

    def rodape(canvas, numero: int, total: int) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(_SUAVE)
        # À esquerda o título: uma página solta na mesa precisa dizer de que
        # relatório ela é. Ao centro quem emitiu e quando. À direita, onde está.
        canvas.drawString(margem, 9 * mm, titulo or "Botané Deli e Café")
        if emissao:
            canvas.drawCentredString(pagina[0] / 2, 9 * mm, emissao)
        canvas.drawRightString(pagina[0] - margem, 9 * mm, f"Página {numero} de {total}")
        canvas.restoreState()

    doc.build(historia, canvasmaker=lambda *a, **k: _CanvasNumerado(*a, rodape=rodape, **k))
    return buffer.getvalue()
