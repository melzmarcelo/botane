"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import ExplicaTela from "@/components/explica-tela";
import { Aviso, Campo, Carregando, Cartao, Etiqueta } from "@/components/ui";
import {
  gravarEnderecoDoSite,
  listarQrCodes,
  type QrCodes,
  type QrDaCasa,
} from "@/lib/qrcodes";

import ImpressaoDoQr from "./impressao";

/**
 * Portal de Clientes → QR codes: todos os QR da casa num lugar só.
 *
 * 🔑 **Pedido do dono (27/09/2026):** *"implementar também a opção de mais QR codes: o da
 * pontuação, o do cardápio que pode ir na mesa, o da própria reserva. Criar uma tela em
 * reservas específica para organizar estes QR codes."*
 *
 * ⚠️ **Todos abrem o MESMO site**, com a loja dentro; o que muda é a tela em que ele abre.
 * Por isso o endereço do site fica aqui, no topo: mudar depois de imprimir invalida todos.
 */
const ICONE: Record<QrDaCasa["tipo"], string> = {
  site: "Página inicial",
  reserva: "Reserva",
  cardapio: "Cardápio",
  fidelidade: "Fidelidade",
};

export default function PaginaQrCodes() {
  const aviso = useAviso();
  const [dados, setDados] = useState<QrCodes | null>(null);
  const [erro, setErro] = useState("");
  const [site, setSite] = useState("");
  const [imprimindo, setImprimindo] = useState<QrDaCasa | null>(null);
  const [gravando, setGravando] = useState(false);

  useEffect(() => {
    listarQrCodes()
      .then((d) => {
        setDados(d);
        setSite(d.site_url);
      })
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar os QR codes"));
  }, []);

  async function gravarSite() {
    setGravando(true);
    try {
      const r = await gravarEnderecoDoSite(site);
      setDados(r);
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar o endereço");
    } finally {
      setGravando(false);
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados) return <Carregando />;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Portal de Clientes</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">QR codes</h1>
        <ExplicaTela>
          Os QR codes que a casa espalha: o do site, o da reserva, o de cada cardápio (para as
          mesas) e o da fidelidade. Cada um abre o site do cliente direto na tela certa, nesta
          loja.
        </ExplicaTela>
      </header>

      <Cartao titulo="Endereço do site" descricao="Todos os QR codes abrem este endereço.">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <Campo rotulo="Endereço" className="min-w-0 flex-1">
            <input className="campo mono" value={site} onChange={(e) => setSite(e.target.value)} />
          </Campo>
          <button className="btn btn-secundario" onClick={() => void gravarSite()}
                  disabled={gravando || site === dados.site_url} aria-busy={gravando}>
            {gravando ? "…" : "Gravar"}
          </button>
        </div>
        <p className="mt-2 text-[13px] text-suave">
          ⚠️ Mudar o endereço depois de imprimir faz os QR já impressos apontarem para o lugar
          antigo.
        </p>
      </Cartao>

      <div className="grid gap-4 md:grid-cols-2">
        {dados.tipos.map((qr) => (
          <Cartao key={qr.tipo + (qr.id_catalogo ?? "")}>
            <div className="flex h-full flex-col gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <Etiqueta cor={qr.tipo === "fidelidade" ? "alerta" : "erva"}>{ICONE[qr.tipo]}</Etiqueta>
                <h2 className="text-[16px] font-bold">{qr.nome}</h2>
              </div>
              <p className="text-[13px] text-suave">Fica bem {qr.onde}.</p>
              {qr.tipo === "fidelidade" && (
                <p className="text-[13px]">
                  {qr.metodo === "CODIGO_CAIXA"
                    ? "Método: código de confirmação — o cliente lê no caixa e o atendente passa o código (Fidelidade → Códigos)."
                    : "Método: QR na mesa — a visita conta na hora da leitura."}{" "}
                  <Link href="/fidelidade/configuracao" className="link-acao">mudar</Link>
                </p>
              )}
              <p className="break-all rounded-[8px] bg-[var(--color-superficie2)] px-2.5 py-1.5 font-mono text-[12px]">
                {qr.link}
              </p>
              {qr.disponivel === false ? (
                <Aviso tipo="info">{qr.motivo}</Aviso>
              ) : (
                <div className="mt-auto flex justify-end">
                  <button className="btn btn-primario" onClick={() => setImprimindo(qr)}>
                    Imprimir
                  </button>
                </div>
              )}
            </div>
          </Cartao>
        ))}
      </div>

      {!dados.tipos.some((t) => t.tipo === "cardapio") && (
        <p className="text-[13px] text-suave">
          Nenhum cardápio ativo nesta loja — o QR de cada cardápio aparece aqui quando houver
          um em <Link href="/catalogos" className="link-acao">Catálogos</Link>.
        </p>
      )}

      {imprimindo && <ImpressaoDoQr qr={imprimindo} aoFechar={() => setImprimindo(null)} />}
    </div>
  );
}
