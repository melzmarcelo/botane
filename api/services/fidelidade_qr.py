"""O PDF dos QR codes de check-in, para imprimir e pôr nas mesas.

🔑 **Pedido do dono (24/09/2026):** *"na configuração também teremos a impressão do
QR code, onde podemos escolher a quantidade que vamos imprimir e o tamanho e se tem
mais alguma informação, para ocupar bem o espaço do PDF."*

⚠️ **Todos os QR de uma loja são o MESMO link** (loja + segredo do programa): a
mesa não identifica ninguém, só prova que a pessoa esteve na casa. Por isso a
numeração ("Mesa 7") é só impressa — não vai no link.

🔑 Três tamanhos que enchem a folha A4 sem sobra: grande (1 por folha, para o
caixa ou a porta), médio (4, display de mesa) e pequeno (12, adesivo).
"""

from io import BytesIO

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# colunas x linhas por folha
LAYOUTS = {"G": (1, 1), "M": (2, 2), "P": (3, 4)}

_TINTA = HexColor("#1B211C")
_SUAVE = HexColor("#5E6659")
_LINHA = HexColor("#C9C0AC")


def _quebrar(c: canvas.Canvas, texto: str, fonte: str, tamanho: float, largura: float) -> list[str]:
    """Quebra o texto em linhas que cabem na largura — o reportlab não faz sozinho."""
    linhas, atual = [], ""
    for palavra in texto.split():
        tentativa = f"{atual} {palavra}".strip()
        if c.stringWidth(tentativa, fonte, tamanho) <= largura or not atual:
            atual = tentativa
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def _cartao(c: canvas.Canvas, x: float, y: float, w: float, h: float, link: str,
            titulo: str, chamada: str, extra: str, casa: str, mesa: str | None) -> None:
    """Um cartão de check-in no retângulo (x, y, w, h) — y é a base."""
    # A linha de corte, tracejada: o cartão é recortado da folha.
    c.setStrokeColor(_LINHA)
    c.setDash(3, 3)
    c.roundRect(x, y, w, h, 3 * mm)
    c.setDash()

    escala = min(w, h) / (180 * mm)  # 1.0 no grande
    margem = max(5 * mm, 12 * mm * escala)
    largura = w - 2 * margem
    topo = y + h - margem

    # Título
    t_tam = max(11, 30 * escala)
    c.setFillColor(_TINTA)
    for linha in _quebrar(c, titulo, "Helvetica-Bold", t_tam, largura)[:2]:
        topo -= t_tam
        c.setFont("Helvetica-Bold", t_tam)
        c.drawCentredString(x + w / 2, topo, linha)
        topo -= t_tam * 0.25

    # Rodapé (de baixo para cima): casa e mesa.
    base = y + margem
    r_tam = max(7, 14 * escala)
    c.setFont("Helvetica", r_tam)
    c.setFillColor(_SUAVE)
    c.drawCentredString(x + w / 2, base, casa)
    base += r_tam * 1.5
    if mesa:
        m_tam = max(9, 22 * escala)
        c.setFont("Helvetica-Bold", m_tam)
        c.setFillColor(_TINTA)
        c.drawCentredString(x + w / 2, base, mesa)
        base += m_tam * 1.4

    # Chamada e texto extra, logo acima do rodapé.
    s_tam = max(8, 17 * escala)
    blocos = []
    for texto, fonte in ((chamada, "Helvetica-Bold"), (extra, "Helvetica")):
        if texto:
            blocos.append((_quebrar(c, texto, fonte, s_tam, largura)[:3], fonte))
    for linhas, fonte in reversed(blocos):
        c.setFont(fonte, s_tam)
        c.setFillColor(_TINTA if fonte.endswith("Bold") else _SUAVE)
        for linha in reversed(linhas):
            c.drawCentredString(x + w / 2, base, linha)
            base += s_tam * 1.3
        base += s_tam * 0.4

    # O QR ocupa o que sobrou no meio — quadrado, centralizado.
    espaco = topo - base - s_tam * 0.6
    lado = max(min(espaco, largura), 20 * mm)
    qr = QrCodeWidget(link, barLevel="M")
    x0, y0, x1, y1 = qr.getBounds()
    d = Drawing(lado, lado, transform=[lado / (x1 - x0), 0, 0, lado / (y1 - y0), 0, 0])
    d.add(qr)
    renderPDF.draw(d, c, x + (w - lado) / 2, base + (espaco - lado) / 2 + s_tam * 0.3)


def gerar(link: str, quantidade: int, tamanho: str, titulo: str, chamada: str,
          extra: str, casa: str, numerar: bool, primeira_mesa: int = 1) -> bytes:
    colunas, linhas = LAYOUTS[tamanho]
    pagina_w, pagina_h = A4
    margem = 10 * mm
    folga = 6 * mm
    w = (pagina_w - 2 * margem - (colunas - 1) * folga) / colunas
    h = (pagina_h - 2 * margem - (linhas - 1) * folga) / linhas

    saida = BytesIO()
    c = canvas.Canvas(saida, pagesize=A4)
    c.setTitle(f"QR codes de check-in — {casa}")
    por_folha = colunas * linhas
    for i in range(quantidade):
        if i and i % por_folha == 0:
            c.showPage()
        pos = i % por_folha
        col, lin = pos % colunas, pos // colunas
        x = margem + col * (w + folga)
        y = pagina_h - margem - (lin + 1) * h - lin * folga
        mesa = f"Mesa {primeira_mesa + i}" if numerar else None
        _cartao(c, x, y, w, h, link, titulo, chamada, extra, casa, mesa)
    c.save()
    return saida.getvalue()
