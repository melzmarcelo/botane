/**
 * Reduz a foto no navegador antes de enviar (24/11/2026, foto da nota no recebimento).
 *
 * 🔑 A foto do celular passa fácil dos 2 MB que o servidor aceita, e quem está na porta
 * recebendo mercadoria não vai procurar como diminuir. Aqui ela vira JPEG de até 1600 px no
 * lado maior — a nota continua legível e fica com uns 300 KB.
 * ⚠️ Se o navegador não conseguir desenhar (formato estranho, HEIC num desktop), devolve o
 * arquivo como veio e o servidor decide.
 */
export async function reduzirFoto(arquivo: File, ladoMaior = 1600, qualidade = 0.8): Promise<File> {
  if (!arquivo.type.startsWith("image/")) return arquivo;
  try {
    const bitmap = await createImageBitmap(arquivo);
    const escala = Math.min(1, ladoMaior / Math.max(bitmap.width, bitmap.height));
    const largura = Math.round(bitmap.width * escala);
    const altura = Math.round(bitmap.height * escala);
    const tela = document.createElement("canvas");
    tela.width = largura;
    tela.height = altura;
    const ctx = tela.getContext("2d");
    if (!ctx) return arquivo;
    ctx.drawImage(bitmap, 0, 0, largura, altura);
    bitmap.close?.();
    const blob = await new Promise<Blob | null>((ok) => tela.toBlob(ok, "image/jpeg", qualidade));
    if (!blob || (blob.size >= arquivo.size && arquivo.size < 2 * 1024 * 1024)) return arquivo;
    return new File([blob], arquivo.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" });
  } catch {
    return arquivo;
  }
}
