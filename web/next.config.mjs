/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  agentRules: false,
  // Sem isto o dev server devolve 403 nos chunks quando a página é aberta por
  // 127.0.0.1 (ou pelo IP da máquina, no teste em celular) — a página renderiza
  // mas nunca hidrata, e todo formulário vira submit nativo.
  allowedDevOrigins: ["127.0.0.1", "localhost", "192.168.0.0/16"],
  // O selo do dev tapava o rodapé da barra lateral nas capturas.
  devIndicators: false,
  async headers() {
    return [
      {
        // 🔴 **Cabeçalhos de segurança em toda tela** (validação de 29/09/2026: no ar não
        // saía nenhum — dava para emoldurar o sistema noutro site e induzir clique).
        // ⚠️ Moldura só do PRÓPRIO site (`frame-ancestors 'self'`, `SAMEORIGIN`), não
        // nenhuma: a Ajuda mostra o `ajuda.html` dentro de um iframe.
        // ⚠️ A CSP NÃO restringe script de propósito: o Next injeta script inline, e
        // travá-lo pede nonce em cada página — uma CSP que quebra a tela é pior que
        // nenhuma. O que ela fecha aqui é moldura, `<base>`, plugin e destino de formulário.
        // ⚠️ Geolocalização só do próprio site: a configuração da fidelidade marca o ponto
        // da loja pelo GPS do aparelho.
        source: "/:caminho*",
        headers: [
          { key: "Strict-Transport-Security", value: "max-age=31536000" },
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), payment=(), geolocation=(self)" },
          {
            key: "Content-Security-Policy",
            value: "frame-ancestors 'self'; base-uri 'self'; object-src 'none'; form-action 'self'",
          },
        ],
      },
      {
        // O service worker NUNCA pode vir do cache do navegador: é ele que
        // decide o que fica guardado. Um sw.js velho em cache prenderia o
        // aparelho numa versão antiga sem nenhuma forma de sair.
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Service-Worker-Allowed", value: "/" },
        ],
      },
    ];
  },
};
export default nextConfig;
