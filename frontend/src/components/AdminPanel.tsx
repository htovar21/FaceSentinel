import { useState, useEffect, useRef } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ShieldCheck, Plus, CheckCircle2, Copy, AlertCircle, RefreshCw, Key, FileText, Check, Clock, XCircle, Users, Camera, Upload } from "lucide-react"
import axios from "axios"
import { API_BASE_URL } from "@/config/api"
import IoTDevicesView from "./IoTDevicesView"
import AccessControlView from "./AccessControlView"

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

interface SystemUser {
    user_id: string
    name: string
    role: string
    username?: string
    created_at?: string
}

export default function AdminPanel() {
    const [adminSubTab, setAdminSubTab] = useState<"sso" | "users" | "devices" | "acl">("sso")
    const [clients, setClients] = useState<Client[]>([])
    const [loadingClients, setLoadingClients] = useState(true)
    const [error, setError] = useState("")

    // Users and Biometrics Enrollment state
    const [usersList, setUsersList] = useState<SystemUser[]>([])
    const [loadingUsers, setLoadingUsers] = useState(false)
    const [enrollingUser, setEnrollingUser] = useState<SystemUser | null>(null)
    const [cameraStream, setCameraStream] = useState<MediaStream | null>(null)
    const [enrollSuccess, setEnrollSuccess] = useState("")
    const [cameraLoading, setCameraLoading] = useState(false)
    const videoRef = useRef<HTMLVideoElement | null>(null)
    const mediaStreamRef = useRef<MediaStream | null>(null)
    
    // Register client form
    const [appName, setAppName] = useState("")
    const [redirectUriInput, setRedirectUriInput] = useState("")
    const [devCedula, setDevCedula] = useState("")
    const [devUsername, setDevUsername] = useState("")
    const [devPassword, setDevPassword] = useState("")
    const [registering, setRegistering] = useState(false)
    const [newClientResult, setNewClientResult] = useState<{ client_id: string; client_secret: string } | null>(null)
    const [copiedId, setCopiedId] = useState(false)
    const [copiedSecret, setCopiedSecret] = useState(false)

    // Audit logs selector & view
    const [selectedClient, setSelectedClient] = useState<string>("")
    const [auditLogs, setAuditLogs] = useState<AuditLog[]>([])
    const [loadingLogs, setLoadingLogs] = useState(false)

    const token = localStorage.getItem("token") || ""
    const baseUrl = API_BASE_URL

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
        if (!appName || !redirectUriInput || !devCedula || !devUsername || !devPassword) {
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
                redirect_uris: redirectUris,
                developer_user_id: devCedula,
                developer_username: devUsername,
                developer_password: devPassword
            }, {
                headers: { Authorization: `Bearer ${token}` }
            })

            setNewClientResult({
                client_id: res.data.client_id,
                client_secret: res.data.client_secret
            })
            setAppName("")
            setRedirectUriInput("")
            setDevCedula("")
            setDevUsername("")
            setDevPassword("")
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

    const fetchUsers = async () => {
        setLoadingUsers(true)
        setError("")
        try {
            const res = await axios.get(`${baseUrl}/api/v1/users`, {
                headers: { Authorization: `Bearer ${token}` }
            })
            setUsersList(res.data)
        } catch (err: any) {
            setError(err.response?.data?.detail || "No se pudieron cargar los usuarios.")
        } finally {
            setLoadingUsers(false)
        }
    }

    const startUserCamera = async (u: SystemUser) => {
        setEnrollingUser(u)
        setEnrollSuccess("")
        setError("")
        try {
            let stream: MediaStream
            try {
                stream = await navigator.mediaDevices.getUserMedia({
                    video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" }
                })
            } catch {
                stream = await navigator.mediaDevices.getUserMedia({ video: true })
            }
            mediaStreamRef.current = stream
            setCameraStream(stream)
            if (videoRef.current) {
                videoRef.current.srcObject = stream
                videoRef.current.play().catch(() => {})
            }
        } catch (err: any) {
            if (err?.name === "NotAllowedError" || err?.name === "PermissionDeniedError") {
                setError("Permiso denegado. Permite el acceso a la cámara en el navegador.")
            } else if (err?.name === "NotReadableError" || err?.name === "TrackStartError") {
                setError("La cámara web está siendo ocupada por otra aplicación o pestaña.")
            } else {
                setError("No se pudo acceder a la cámara web (" + (err?.message || "Error") + ").")
            }
        }
    }

    const stopUserCamera = () => {
        if (mediaStreamRef.current) {
            mediaStreamRef.current.getTracks().forEach(track => track.stop())
            mediaStreamRef.current = null
        }
        if (cameraStream) {
            cameraStream.getTracks().forEach(track => track.stop())
            setCameraStream(null)
        }
        if (videoRef.current) {
            videoRef.current.srcObject = null
        }
        setEnrollingUser(null)
    }

    useEffect(() => {
        if (enrollingUser && videoRef.current && cameraStream) {
            videoRef.current.srcObject = cameraStream
            videoRef.current.play().catch(e => console.error("Error reproduciendo video:", e))
        }
    }, [enrollingUser, cameraStream])

    const captureAndEnrollUser = async () => {
        if (!videoRef.current || !enrollingUser) return
        setCameraLoading(true)
        setError("")
        
        const video = videoRef.current
        const width = video.videoWidth || 640
        const height = video.videoHeight || 480

        const canvas = document.createElement("canvas")
        canvas.width = width
        canvas.height = height
        const ctx = canvas.getContext("2d")
        if (!ctx) return
        ctx.drawImage(video, 0, 0, width, height)
        const base64Image = canvas.toDataURL("image/jpeg")

        try {
            const res = await axios.put(`${baseUrl}/api/v1/users/${enrollingUser.user_id}/biometrics`, {
                image_base64: base64Image
            }, {
                headers: { Authorization: `Bearer ${token}` }
            })
            setEnrollSuccess(res.data?.message || `¡Biometría facial de ${enrollingUser.name} actualizada con éxito!`)
            stopUserCamera()
            fetchUsers()
        } catch (err: any) {
            setError(err.response?.data?.detail || "Error al actualizar la biometría facial.")
        } finally {
            setCameraLoading(false)
        }
    }

    const handleAdminUserFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file || !enrollingUser) return
        setCameraLoading(true)
        setError("")
        const reader = new FileReader()
        reader.onload = async (ev) => {
            const base64Image = ev.target?.result as string
            if (!base64Image) {
                setCameraLoading(false)
                return
            }
            try {
                const res = await axios.put(`${baseUrl}/api/v1/users/${enrollingUser.user_id}/biometrics`, {
                    image_base64: base64Image
                }, {
                    headers: { Authorization: `Bearer ${token}` }
                })
                setEnrollSuccess(res.data?.message || `¡Biometría facial de ${enrollingUser.name} actualizada con éxito!`)
                stopUserCamera()
                fetchUsers()
            } catch (err: any) {
                setError(err.response?.data?.detail || "Error al actualizar la biometría facial.")
            } finally {
                setCameraLoading(false)
            }
        }
        reader.readAsDataURL(file)
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
                        Gestiona clientes de SSO, enrolamiento facial y auditoría en Blockchain.
                    </p>
                </div>
                <Button variant="outline" size="sm" onClick={() => { fetchClients(); if (adminSubTab === "users") fetchUsers(); }} disabled={loadingClients || loadingUsers}>
                    <RefreshCw className={`h-4 w-4 mr-2 ${loadingClients || loadingUsers ? "animate-spin" : ""}`} /> Actualizar
                </Button>
            </div>

            {/* Botones de Navegación de Sub-Páneles */}
            <div className="flex bg-muted/80 p-1 rounded-lg border w-fit text-xs gap-1 shadow-sm">
                <Button 
                    variant={adminSubTab === "sso" ? "default" : "ghost"} 
                    size="sm" 
                    className="h-8 text-xs font-semibold px-4"
                    onClick={() => setAdminSubTab("sso")}
                >
                    Multi-Tenant SSO
                </Button>
                <Button 
                    variant={adminSubTab === "users" ? "default" : "ghost"} 
                    size="sm" 
                    className="h-8 text-xs font-semibold px-4"
                    onClick={() => {
                        setAdminSubTab("users")
                        fetchUsers()
                    }}
                >
                    <Users className="w-3.5 h-3.5 mr-1.5" />
                    Usuarios y Biometría
                </Button>
                <Button 
                    variant={adminSubTab === "devices" ? "default" : "ghost"} 
                    size="sm" 
                    className="h-8 text-xs font-semibold px-4"
                    onClick={() => setAdminSubTab("devices")}
                >
                    Dispositivos IoT
                </Button>
                <Button 
                    variant={adminSubTab === "acl" ? "default" : "ghost"} 
                    size="sm" 
                    className="h-8 text-xs font-semibold px-4"
                    onClick={() => setAdminSubTab("acl")}
                >
                    Control de Acceso (ACL)
                </Button>
            </div>

            {adminSubTab === "sso" && (
                <>
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
                                    <div className="space-y-2">
                                        <Label htmlFor="devCedula">Cédula del Desarrollador</Label>
                                        <Input
                                            id="devCedula"
                                            placeholder="12345678"
                                            value={devCedula}
                                            onChange={e => setDevCedula(e.target.value)}
                                            required
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="devUsername">Username del Desarrollador</Label>
                                        <Input
                                            id="devUsername"
                                            placeholder="dev_user"
                                            value={devUsername}
                                            onChange={e => setDevUsername(e.target.value)}
                                            required
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="devPassword">Contraseña del Desarrollador</Label>
                                        <Input
                                            id="devPassword"
                                            type="password"
                                            placeholder="••••••••"
                                            value={devPassword}
                                            onChange={e => setDevPassword(e.target.value)}
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
                </>
            )}

            {adminSubTab === "users" && (
                <div className="space-y-6">
                    {enrollSuccess && (
                        <div className="p-3 rounded-md bg-green-500/15 text-green-700 dark:text-green-400 text-sm font-medium flex items-center gap-2 border border-green-500/20">
                            <CheckCircle2 className="h-4 w-4" />
                            {enrollSuccess}
                        </div>
                    )}

                    {error && (
                        <div className="p-3 rounded-md bg-destructive/15 text-destructive text-sm font-medium flex items-center gap-2">
                            <AlertCircle className="h-4 w-4" />
                            {error}
                        </div>
                    )}

                    {/* Modal / Escáner de Enrolamiento de Cámara */}
                    {enrollingUser && (
                        <Card className="border-primary shadow-lg bg-card/95 backdrop-blur">
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2 text-primary">
                                    <Camera className="w-5 h-5" /> Enrolando Rostro: {enrollingUser.name} ({enrollingUser.user_id})
                                </CardTitle>
                                <CardDescription>
                                    Ubica el rostro dentro del recuadro con buena iluminación frontal y presiona Capturar. El nuevo vector ArcFace reemplazará la plantilla anterior en ChromaDB.
                                </CardDescription>
                            </CardHeader>
                            <CardContent className="flex flex-col items-center space-y-4">
                                <div className="relative overflow-hidden rounded-xl aspect-video w-full max-w-md flex items-center justify-center bg-black shadow-inner border border-primary/30">
                                    <video
                                        ref={(el) => {
                                            videoRef.current = el
                                            if (el && cameraStream && el.srcObject !== cameraStream) {
                                                el.srcObject = cameraStream
                                                el.play().catch(() => {})
                                            }
                                        }}
                                        autoPlay
                                        playsInline
                                        muted
                                        onLoadedMetadata={(e) => {
                                            (e.target as HTMLVideoElement).play().catch(() => {})
                                        }}
                                        className="h-full w-full object-cover transform scale-x-[-1]"
                                    />
                                    <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                                        <div className="w-1/2 h-3/4 border-2 border-primary/70 rounded-[45%] border-dashed shadow-[0_0_15px_rgba(0,255,200,0.3)] animate-pulse"></div>
                                    </div>
                                </div>
                                <div className="flex gap-3 w-full max-w-md">
                                    <Button variant="outline" className="w-full" onClick={stopUserCamera} disabled={cameraLoading}>
                                        Cancelar
                                    </Button>
                                    <Button className="w-full bg-primary hover:bg-primary/90 text-primary-foreground font-semibold" onClick={captureAndEnrollUser} disabled={cameraLoading}>
                                        {cameraLoading ? (
                                            <span className="flex items-center gap-2">
                                                <RefreshCw className="w-4 h-4 animate-spin" /> Procesando Vector...
                                            </span>
                                        ) : (
                                            <span className="flex items-center gap-2">
                                                <Camera className="w-4 h-4" /> Capturar y Guardar
                                            </span>
                                        )}
                                    </Button>
                                </div>
                                <div className="relative flex py-1 items-center w-full max-w-md">
                                    <div className="flex-grow border-t border-muted"></div>
                                    <span className="flex-shrink mx-3 text-[11px] text-muted-foreground uppercase font-medium">O si la cámara está ocupada</span>
                                    <div className="flex-grow border-t border-muted"></div>
                                </div>
                                <label className="w-full max-w-md cursor-pointer">
                                    <input type="file" accept="image/*" className="hidden" onChange={handleAdminUserFileUpload} disabled={cameraLoading} />
                                    <div className="w-full inline-flex items-center justify-center rounded-md text-sm font-medium border border-input bg-muted/60 hover:bg-muted py-2 px-4 shadow-sm transition-colors text-foreground gap-2">
                                        <Upload className="w-4 h-4 text-primary" /> Subir Foto de {enrollingUser.name} desde Archivo
                                    </div>
                                </label>
                            </CardContent>
                        </Card>
                    )}

                    {/* Tabla de Usuarios Registrados */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between pb-3">
                            <div>
                                <CardTitle className="text-lg flex items-center gap-2">
                                    <Users className="w-5 h-5 text-primary" /> Directorio de Usuarios y Biometría
                                </CardTitle>
                                <CardDescription>
                                    Usuarios registrados en el IdP. Puedes re-enrolar la biometría facial de cualquier persona directamente con la cámara web.
                                </CardDescription>
                            </div>
                            <Button variant="outline" size="sm" onClick={fetchUsers} disabled={loadingUsers}>
                                <RefreshCw className={`h-4 w-4 mr-1.5 ${loadingUsers ? "animate-spin" : ""}`} /> Recargar
                            </Button>
                        </CardHeader>
                        <CardContent>
                            {loadingUsers ? (
                                <div className="text-center py-8 text-muted-foreground animate-pulse">
                                    Cargando directorio de usuarios...
                                </div>
                            ) : usersList.length > 0 ? (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-sm text-left">
                                        <thead className="text-xs text-muted-foreground uppercase bg-muted/50 border-b">
                                            <tr>
                                                <th className="px-4 py-3 rounded-tl-md">ID / Cédula</th>
                                                <th className="px-4 py-3">Nombre</th>
                                                <th className="px-4 py-3">Rol</th>
                                                <th className="px-4 py-3">Usuario SSO</th>
                                                <th className="px-4 py-3 text-right rounded-tr-md">Acción Biometría</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {usersList.map((u, i) => (
                                                <tr key={u.user_id || i} className="border-b last:border-0 hover:bg-muted/10 transition-colors">
                                                    <td className="px-4 py-3 font-mono font-bold text-foreground">
                                                        {u.user_id}
                                                    </td>
                                                    <td className="px-4 py-3 font-medium">
                                                        {u.name}
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <span className="px-2 py-0.5 rounded text-xs font-semibold bg-primary/10 text-primary border border-primary/20">
                                                            {u.role}
                                                        </span>
                                                    </td>
                                                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                                                        {u.username || "—"}
                                                    </td>
                                                    <td className="px-4 py-3 text-right">
                                                        <Button
                                                            size="sm"
                                                            variant="outline"
                                                            className="text-xs font-medium border-primary/30 text-primary hover:bg-primary/10"
                                                            onClick={() => startUserCamera(u)}
                                                            disabled={cameraLoading}
                                                        >
                                                            <Camera className="w-3.5 h-3.5 mr-1.5" />
                                                            Re-enrolar Rostro
                                                        </Button>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            ) : (
                                <div className="text-center py-8 text-muted-foreground border border-dashed rounded-md bg-muted/10">
                                    No se encontraron usuarios registrados en la base de datos.
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>
            )}

            {adminSubTab === "devices" && <IoTDevicesView />}
            {adminSubTab === "acl" && <AccessControlView />}
        </div>
    )
}
