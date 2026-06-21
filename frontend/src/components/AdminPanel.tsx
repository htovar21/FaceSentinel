import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ShieldCheck, Plus, CheckCircle2, Copy, AlertCircle, RefreshCw, Key, FileText, Check, Clock, XCircle } from "lucide-react"
import axios from "axios"

interface Client {
    client_id: string
    app_name: string
    redirect_uris: string[]
    created_at: string
}

interface AuditLog {
    user_id: string
    biometric_hash: string
    timestamp: number
    access_granted: boolean
    device_id: string
    match_score: number
    client_id: string
}

export default function AdminPanel() {
    const [clients, setClients] = useState<Client[]>([])
    const [loadingClients, setLoadingClients] = useState(true)
    const [error, setError] = useState("")
    
    // Register client form
    const [appName, setAppName] = useState("")
    const [redirectUriInput, setRedirectUriInput] = useState("")
    const [registering, setRegistering] = useState(false)
    const [newClientResult, setNewClientResult] = useState<{ client_id: string; client_secret: string } | null>(null)
    const [copiedId, setCopiedId] = useState(false)
    const [copiedSecret, setCopiedSecret] = useState(false)

    // Audit logs selector & view
    const [selectedClient, setSelectedClient] = useState<string>("")
    const [auditLogs, setAuditLogs] = useState<AuditLog[]>([])
    const [loadingLogs, setLoadingLogs] = useState(false)

    const token = localStorage.getItem("token") || ""
    const baseUrl = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"

    const fetchClients = async () => {
        setLoadingClients(true)
        setError("")
        try {
            const res = await axios.get(`${baseUrl}/api/v1/clients`, {
                headers: { Authorization: `Bearer ${token}` }
            })
            setClients(res.data)
        } catch (err: any) {
            setError(err.response?.data?.detail || "No se pudieron cargar las aplicaciones cliente.")
        } finally {
            setLoadingClients(false)
        }
    }

    const handleRegisterClient = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!appName || !redirectUriInput) {
            alert("Completa todos los campos.")
            return
        }

        setRegistering(true)
        setError("")
        setNewClientResult(null)

        const redirectUris = redirectUriInput.split(",").map(uri => uri.trim())

        try {
            const res = await axios.post(`${baseUrl}/api/v1/clients/register`, {
                app_name: appName,
                redirect_uris: redirectUris
            }, {
                headers: { Authorization: `Bearer ${token}` }
            })

            setNewClientResult({
                client_id: res.data.client_id,
                client_secret: res.data.client_secret
            })
            setAppName("")
            setRedirectUriInput("")
            fetchClients()
        } catch (err: any) {
            setError(err.response?.data?.detail || "Error al registrar la aplicación.")
        } finally {
            setRegistering(false)
        }
    }

    const fetchAuditLogs = async (clientId: string) => {
        if (!clientId) {
            setAuditLogs([])
            return
        }
        setLoadingLogs(true)
        try {
            const res = await axios.get(`${baseUrl}/api/v1/clients/${clientId}/logs?limit=50`, {
                headers: { Authorization: `Bearer ${token}` }
            })
            if (res.data.success && res.data.records) {
                setAuditLogs(res.data.records)
            } else {
                setAuditLogs([])
            }
        } catch (err) {
            console.error("Error al obtener los logs de auditoría", err)
            setAuditLogs([])
        } finally {
            setLoadingLogs(false)
        }
    }

    useEffect(() => {
        if (token) {
            fetchClients()
        }
    }, [token])

    const copyToClipboard = (text: string, type: "id" | "secret") => {
        navigator.clipboard.writeText(text)
        if (type === "id") {
            setCopiedId(true)
            setTimeout(() => setCopiedId(false), 2000)
        } else {
            setCopiedSecret(true)
            setTimeout(() => setCopiedSecret(false), 2000)
        }
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h3 className="text-xl font-bold tracking-tight flex items-center gap-2">
                        <ShieldCheck className="h-5 w-5 text-primary" /> Panel de Administración Multi-Tenant
                    </h3>
                    <p className="text-sm text-muted-foreground">
                        Gestiona clientes de SSO y visualiza registros de auditoría en Blockchain.
                    </p>
                </div>
                <Button variant="outline" size="sm" onClick={fetchClients} disabled={loadingClients}>
                    <RefreshCw className={`h-4 w-4 mr-2 ${loadingClients ? "animate-spin" : ""}`} /> Actualizar
                </Button>
            </div>

            {error && (
                <div className="p-3 rounded-md bg-destructive/15 text-destructive text-sm font-medium flex items-center gap-2">
                    <AlertCircle className="h-4 w-4" />
                    {error}
                </div>
            )}

            <div className="grid gap-6 md:grid-cols-3">
                {/* Registro de Clientes */}
                <Card className="md:col-span-1 border-primary/20">
                    <CardHeader>
                        <CardTitle className="text-md flex items-center gap-2">
                            <Plus className="w-5 h-5 text-primary" /> Registrar Nueva Aplicación
                        </CardTitle>
                        <CardDescription>
                            Genera credenciales de federación para un nuevo inquilino.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <form onSubmit={handleRegisterClient} className="space-y-4">
                            <div className="space-y-2">
                                <Label htmlFor="appName">Nombre de la Aplicación</Label>
                                <Input
                                    id="appName"
                                    placeholder="Mi Portal Educativo"
                                    value={appName}
                                    onChange={e => setAppName(e.target.value)}
                                    required
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="redirectUris">Redirect URIs (Separadas por coma)</Label>
                                <Input
                                    id="redirectUris"
                                    placeholder="http://localhost:3000/callback, https://jwt.io/"
                                    value={redirectUriInput}
                                    onChange={e => setRedirectUriInput(e.target.value)}
                                    required
                                />
                            </div>
                            <Button type="submit" className="w-full" disabled={registering}>
                                {registering ? "Registrando..." : "Registrar Aplicación"}
                            </Button>
                        </form>

                        {newClientResult && (
                            <div className="mt-4 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30 text-xs space-y-3">
                                <p className="font-semibold text-yellow-600 dark:text-yellow-400 flex items-center gap-1">
                                    <Key className="w-4 h-4" /> Guarda estas credenciales ahora.
                                </p>
                                <p className="text-muted-foreground">No podrás volver a ver el Client Secret.</p>
                                
                                <div className="space-y-1">
                                    <span className="font-medium">Client ID:</span>
                                    <div className="flex items-center gap-2 mt-1">
                                        <code className="p-1 rounded bg-muted w-full block truncate font-mono">{newClientResult.client_id}</code>
                                        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => copyToClipboard(newClientResult.client_id, "id")}>
                                            {copiedId ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
                                        </Button>
                                    </div>
                                </div>

                                <div className="space-y-1">
                                    <span className="font-medium">Client Secret:</span>
                                    <div className="flex items-center gap-2 mt-1">
                                        <code className="p-1 rounded bg-muted w-full block truncate font-mono">{newClientResult.client_secret}</code>
                                        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => copyToClipboard(newClientResult.client_secret, "secret")}>
                                            {copiedSecret ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Lista de Aplicaciones Clientes */}
                <Card className="md:col-span-2">
                    <CardHeader>
                        <CardTitle className="text-md flex items-center gap-2">
                            <FileText className="w-5 h-5 text-primary" /> Clientes Registrados (Tenants)
                        </CardTitle>
                        <CardDescription>
                            Listado completo de aplicaciones que pueden autenticar contra este IdP.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        {loadingClients ? (
                            <div className="text-center p-6 text-muted-foreground animate-pulse">Cargando aplicaciones...</div>
                        ) : clients.length > 0 ? (
                            <div className="overflow-x-auto">
                                <table className="w-full text-xs text-left">
                                    <thead className="text-muted-foreground uppercase bg-muted/50 font-semibold">
                                        <tr>
                                            <th className="px-3 py-2.5 rounded-tl-md">Aplicación</th>
                                            <th className="px-3 py-2.5">Client ID</th>
                                            <th className="px-3 py-2.5">Redirect URIs</th>
                                            <th className="px-3 py-2.5 rounded-tr-md">Fecha Registro</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {clients.map((client, i) => (
                                            <tr key={i} className="border-b last:border-0 hover:bg-muted/10 transition-colors">
                                                <td className="px-3 py-2.5 font-bold text-foreground">{client.app_name}</td>
                                                <td className="px-3 py-2.5 font-mono text-muted-foreground">{client.client_id}</td>
                                                <td className="px-3 py-2.5 truncate max-w-[200px]" title={client.redirect_uris.join(", ")}>
                                                    {client.redirect_uris.join(", ")}
                                                </td>
                                                <td className="px-3 py-2.5 text-muted-foreground">
                                                    {new Date(client.created_at).toLocaleDateString()}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        ) : (
                            <div className="text-center p-6 text-muted-foreground">No hay aplicaciones registradas todavía.</div>
                        )}
                    </CardContent>
                </Card>
            </div>

            {/* Auditoría Blockchain */}
            <Card className="w-full">
                <CardHeader>
                    <CardTitle className="text-md flex items-center justify-between">
                        <span className="flex items-center gap-2">
                            <Clock className="w-5 h-5 text-primary" /> Auditoría de Accesos por Aplicación (Blockchain)
                        </span>
                        <div className="flex items-center gap-2">
                            <select
                                className="flex h-9 rounded-md border border-input bg-background px-3 py-1 text-xs ring-offset-background disabled:cursor-not-allowed disabled:opacity-50"
                                value={selectedClient}
                                onChange={e => {
                                    setSelectedClient(e.target.value)
                                    fetchAuditLogs(e.target.value)
                                }}
                            >
                                <option value="">Selecciona una aplicación...</option>
                                {clients.map((client, i) => (
                                    <option key={i} value={client.client_id}>{client.app_name}</option>
                                ))}
                            </select>
                        </div>
                    </CardTitle>
                    <CardDescription>
                        Consulta los bloques y logs inmutables asociados a un inquilino específico en Ganache.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {!selectedClient ? (
                        <div className="text-center py-8 text-muted-foreground border border-dashed rounded-md bg-muted/10">
                            Por favor, selecciona una aplicación de la lista superior para cargar su historial Web3.
                        </div>
                    ) : loadingLogs ? (
                        <div className="text-center py-8 text-muted-foreground animate-pulse">Consultando el Smart Contract...</div>
                    ) : auditLogs.length > 0 ? (
                        <div className="overflow-x-auto">
                            <table className="w-full text-xs text-left">
                                <thead className="text-muted-foreground uppercase bg-muted/50 font-semibold">
                                    <tr>
                                        <th className="px-3 py-2.5 rounded-tl-md">Estado</th>
                                        <th className="px-3 py-2.5">Usuario</th>
                                        <th className="px-3 py-2.5">Dispositivo</th>
                                        <th className="px-3 py-2.5">Fecha y Hora</th>
                                        <th className="px-3 py-2.5">Score (ArcFace)</th>
                                        <th className="px-3 py-2.5 rounded-tr-md">Hash Biométrico (Blockchain)</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {auditLogs.map((log, i) => (
                                        <tr key={i} className="border-b last:border-0 hover:bg-muted/10 transition-colors">
                                            <td className="px-3 py-2.5">
                                                {log.access_granted ? (
                                                    <span className="flex items-center text-green-600 font-medium gap-1">
                                                        <CheckCircle2 className="w-4 h-4" /> Permitido
                                                    </span>
                                                ) : (
                                                    <span className="flex items-center text-red-600 font-medium gap-1">
                                                        <XCircle className="w-4 h-4" /> Denegado
                                                    </span>
                                                )}
                                            </td>
                                            <td className="px-3 py-2.5 font-semibold">{log.user_id}</td>
                                            <td className="px-3 py-2.5 text-muted-foreground">{log.device_id}</td>
                                            <td className="px-3 py-2.5 text-muted-foreground">
                                                {new Date((log.timestamp as any) * 1000).toLocaleString()}
                                            </td>
                                            <td className="px-3 py-2.5 font-mono">{log.match_score?.toFixed(4)}</td>
                                            <td className="px-3 py-2.5 font-mono text-muted-foreground truncate max-w-[200px]" title={log.biometric_hash}>
                                                {log.biometric_hash}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    ) : (
                        <div className="text-center py-8 text-muted-foreground border border-dashed rounded-md bg-muted/10">
                            No se encontraron logs de auditoría en la blockchain para esta aplicación.
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
