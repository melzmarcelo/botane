"use client";

/**
 * "Gerar acesso" das mesas: o link de cada uma (o QR e a etiqueta NFC gravam este link),
 * o QR em PNG, o PDF de todas, e o segredo novo quando um impresso vaza.
 *
 * 🔑 **NFC**: a etiqueta NTAG213/215 grava um registro de URL — qualquer app de gravação
 * (NFC Tools, por exemplo) aceita o link copiado daqui. A NTAG213 guarda 144 bytes; o link
 * da mesa tem menos de 60.
 */

import { useEffect, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando, Cartao } from "@/components/ui";
import { baixarQrPdf, baixarQrPng, CardapioVivoService, type MesaAcesso } from "@/lib/cardapio-vivo";

export default function AcessoMesas() {
  const aviso = useAviso();
  const [mesas, setMesas] = useState<MesaAcesso[] | null>(null);
  const [linkLoja, setLinkLoja] = useState("");
  const [erro, setErro] = useState("");
  const [tamanho, setTamanho] = useState<"P" | "M" | "G">("M");

  const carregar = () => CardapioVivoService.mesas()
    .then((r) => { setMesas(r.mesas); setLinkLoja(r.link_loja); })
    .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar as mesas"));
  useEffect(() => { void carregar(); }, []);

  async function copiar(texto: string) {
    try {
      await navigator.clipboard.writeText(texto);
      aviso.sucesso("Link copiado — cole no app de gravação da etiqueta NFC.");
    } catch {
      aviso.erro("Não deu para copiar. Selecione o link e copie à mão.");
    }
  }

  async function novoToken(m: MesaAcesso) {
    if (!confirm(`Gerar outro acesso para a mesa ${m.nome}? O QR e a etiqueta NFC atuais param de abrir.`)) return;
    try {
      const r = await CardapioVivoService.novoToken(m.id);
      aviso.sucesso(r.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gerar outro acesso.");
    }
  }

  const baixar = (p: Promise<void>) => p.catch((e) => aviso.erro(e instanceof Error ? e.message : "Falha ao baixar."));

  if (erro) return <Cartao titulo="Acesso das mesas"><Aviso tipo="info">{erro}</Aviso></Cartao>;
  if (!mesas) return <Cartao titulo="Acesso das mesas"><Carregando /></Cartao>;

  const ativas = mesas.filter((m) => m.ativo);
  return (
    <Cartao titulo="Acesso das mesas"
            descricao="Cada mesa tem o próprio link, com um segredo — o número da mesa sozinho não abre nada."
            acao={ativas.length ? (
              <div className="flex items-center gap-2">
                <select className="campo !w-auto" value={tamanho} onChange={(e) => setTamanho(e.target.value as "P" | "M" | "G")}
                        aria-label="Tamanho do cartão">
                  <option value="G">1 por folha</option><option value="M">4 por folha</option><option value="P">12 por folha</option>
                </select>
                <button className="btn btn-primario" onClick={() => void baixar(baixarQrPdf(undefined, tamanho))}>
                  PDF de todas
                </button>
              </div>
            ) : undefined}>
      <p className="mb-3 text-[13px]">
        Sem mesa (vitrine, balcão): <span className="break-all font-mono text-[12px]">{linkLoja}</span>{" "}
        <button className="link-acao text-[13px]" onClick={() => void copiar(linkLoja)}>copiar</button>
      </p>
      {ativas.length === 0 ? (
        <Aviso tipo="info">Nenhuma mesa cadastrada. As mesas vêm do Salão.</Aviso>
      ) : (
        <div className="overflow-x-auto">
          <table className="tabela w-full">
            <thead><tr><th>Mesa</th><th>Link (QR e NFC)</th><th className="text-right">Ações</th></tr></thead>
            <tbody>
              {ativas.map((m) => (
                <tr key={m.id}>
                  <td className="whitespace-nowrap"><span className="font-medium">{m.nome}</span>
                    <span className="block text-[12px] text-suave">{m.salao}</span></td>
                  <td className="max-w-[22rem] break-all font-mono text-[12px]">{m.link}</td>
                  <td className="whitespace-nowrap text-right text-[13px]">
                    <button className="link-acao" onClick={() => void copiar(m.link)}>copiar</button>
                    {" · "}
                    <button className="link-acao" onClick={() => void baixar(baixarQrPng(m.id))}>QR</button>
                    {" · "}
                    <button className="link-acao" onClick={() => void baixar(baixarQrPdf([m.id], tamanho))}>PDF</button>
                    {" · "}
                    <button className="link-acao" onClick={() => void novoToken(m)}>gerar outro</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Cartao>
  );
}
