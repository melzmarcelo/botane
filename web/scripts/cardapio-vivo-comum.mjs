// O que as verificações do Cardápio Vivo fazem igual: ligar o catálogo de teste como o
// Cardápio Vivo PRINCIPAL (o da mesa) e, no fim, devolver os da loja.
//
// 🔑 Desde a 117 são duas rotas: a casa em `/cardapio-vivo/config` (aparência, Hub) e cada
// cardápio em `/cardapio-vivo/vivos/{id}` (modo, garçom, horário, principal).
// ⚠️ Verificação devolve o que encontrou: os cardápios de antes voltam com o principal
// deles — senão a mesa da loja ficaria abrindo o cardápio de teste, já inativado.

/** Liga o catálogo de teste como principal. `casa` vai à configuração da casa. */
export async function ligarDeTeste(api, token, antes, idCatalogo, comportamento = {}, casa = {}) {
  if (Object.keys(casa).length) {
    const { id_unidade, logo_url, id_catalogo, ...cfg } = antes.config;
    await api("PUT", "/cardapio-vivo/config", { ...cfg, ...casa }, token);
  }
  return api("PUT", `/cardapio-vivo/vivos/${idCatalogo}`,
             { modo: "VITRINE", ...comportamento, principal: true }, token);
}

/** Devolve a configuração da casa e os Cardápios Vivos de antes, com o principal deles. */
export async function devolverVivos(api, token, antes, idCatalogoDeTeste) {
  const { id_unidade, logo_url, id_catalogo, ...cfg } = antes.config;
  await api("PUT", "/cardapio-vivo/config", cfg, token);
  await api("DELETE", `/cardapio-vivo/vivos/${idCatalogoDeTeste}`, undefined, token);
  // O principal por ÚLTIMO: gravá-lo desmarca qualquer outro.
  const ordem = [...(antes.vivos ?? [])].sort((a, b) => Number(a.principal) - Number(b.principal));
  for (const v of ordem) {
    await api("PUT", `/cardapio-vivo/vivos/${v.id_catalogo}`, {
      slug: v.slug, principal: v.principal, modo: v.modo, exige_confirmacao: v.exige_confirmacao,
      pedido_hora_de: v.pedido_hora_de, pedido_hora_ate: v.pedido_hora_ate, chamar_garcom: v.chamar_garcom,
      selecao: v.selecao ?? true, aberturas: v.aberturas ?? "AUTOMATICA",
    }, token);
  }
}
