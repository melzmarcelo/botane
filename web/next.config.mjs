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
