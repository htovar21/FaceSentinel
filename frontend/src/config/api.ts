/**
 * api.ts — Configuración centralizada de comunicación cliente-servidor para FaceSentinel.
 * 
 * Portabilidad universal:
 * - En Docker / Producción (detrás de Nginx):
 *   Las rutas relativas ("") permiten que el navegador use el mismo host y puerto (ej. http://localhost:5173 o http://192.168.1.50:5173),
 *   evitando errores de CORS y problemas de resolución de 127.0.0.1.
 * - En Desarrollo local con Vite:
 *   El proxy de Vite redirige /api a http://127.0.0.1:8000.
 */

export const API_BASE_URL: string = (import.meta.env.VITE_API_URL ?? "").trim();

/**
 * Obtiene la URL completa del WebSocket de forma dinámica.
 * Respeta HTTPS (usando wss://) y extrae el hostname y puerto actuales del navegador.
 */
export function getWebSocketUrl(path: string = "/api/v1/ws/liveness"): string {
    const customWs = (import.meta.env.VITE_WS_URL ?? "").trim();
    if (customWs) {
        return `${customWs.replace(/\/+$/, "")}${path.startsWith("/") ? path : `/${path}`}`;
    }

    if (API_BASE_URL && API_BASE_URL.startsWith("http")) {
        const wsBase = API_BASE_URL.replace(/^http/, "ws").replace(/\/+$/, "");
        return `${wsBase}${path.startsWith("/") ? path : `/${path}`}`;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const cleanPath = path.startsWith("/") ? path : `/${path}`;
    return `${protocol}//${host}${cleanPath}`;
}
