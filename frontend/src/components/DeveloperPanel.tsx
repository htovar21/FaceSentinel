import { useState, useEffect, useRef } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ShieldCheck, Copy, AlertCircle, RefreshCw, Key, FileText, Check, Clock, XCircle, CheckCircle2, Lock, Camera } from "lucide-react"
import axios from "axios"

interface Client {
    client_id: string
    app_name: string
    redirect_uris: string[]
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

export default function DeveloperPanel() {
    const [client, setClient] = useState<Client | null>(null)
    const [loadingClient, setLoadingClient] = useState(true)
    const [error, setError] = useState("")
    const [successMessage, setSuccessMessage] = useState("")

    // Password change
    const [currentPassword, setCurrentPassword] = useState("")
    const [newPassword, setNewPassword] = useState("")
    const [updatingPassword, setUpdatingPassword] = useState(false)

    // Biometrics Enrollment
    const [showCamera, setShowCamera] = useState(false)
    const [cameraLoading, setCameraLoading] = useState(false)
    const videoRef = useRef<HTMLVideoElement>(null)
    const [stream, setStream] = useState<MediaStream | null>(null)

    // Audit logs
    const [auditLogs, setAuditLogs] = useState<AuditLog[]>([])
    const [loadingLogs, setLoadingLogs] = useState(false)
    const [activeSubTab, setActiveSubTab] = useState<"credentials" | "logs" | "security">("credentials")

    const token = localStorage.getItem("token") || ""
    const baseUrl = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"

    const [copiedId, setCopiedId] = useState(false)

    const fetchClientInfo = async () => {
        setLoadingClient(true)
        setError("")
        try {
            const res = await axios.get(`${baseUrl}/api/v1/clients/my`, {
                headers: { Authorization: `Bearer ${token}` }
            })
            setClient(res.data)
            fetchAuditLogs(res.data.client_id)
        } catch (err: any) {
            setError(err.response?.data?.detail || "No se pudo obtener la información de tu aplicación inquilina.")
        } finally {
            setLoadingClient(false)
        }
    }

    const fetchAuditLogs = async (clientId: string) => {
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

    const handleChangePassword = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!currentPassword || !newPassword) return

        setUpdatingPassword(true)
        setError("")
        setSuccessMessage("")

        try {
            await axios.put(`${baseUrl}/api/v1/users/me/password`, {
                current_password: currentPassword,
                new_password: newPassword
            }, {
                headers: { Authorization: `Bearer ${token}` }
            })
            setSuccessMessage("¡Contraseña actualizada con éxito!")
            setCurrentPassword("")
            setNewPassword("")
        } catch (err: any) {
            setError(err.response?.data?.detail || "Error al actualizar la contraseña.")
        } finally {
            setUpdatingPassword(false)
        }
    }

    const startBiometricEnrollment = async () => {
        setError("")
        setSuccessMessage("")
        try {
            const mediaStream = await navigator.mediaDevices.getUserMedia({ video: true })
            setStream(mediaStream)
            setShowCamera(true)
        } catch (err) {
            setError("No se pudo acceder a la cámara. Revisa los permisos de tu navegador.")
        }
    }

    const stopCamera = () => {
        if (stream) {
            stream.getTracks().forEach(track => track.stop())
            setStream(null)
        }
        setShowCamera(false)
    }

    const handleEnrollBiometrics = async () => {
        if (!videoRef.current) return

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
            await axios.put(`${baseUrl}/api/v1/users/me/biometrics`, {
                image_base64: base64Image
            }, {
                headers: { Authorization: `Bearer ${token}` }
            })
            setSuccessMessage("¡Biometría facial enrolada correctamente! Ya puedes iniciar sesión con tu rostro.")
            stopCamera()
        } catch (err: any) {
            setError(err.response?.data?.detail || "Error al registrar la biometría facial.")
        } finally {
            setCameraLoading(false)
        }
    }

    useEffect(() => {
        if (token) {
            fetchClientInfo()
        }
        return () => {
            if (stream) {
                stream.getTracks().forEach(track => track.stop())
            }
        }
    }, [token])

    // Bind stream to video element
    useEffect(() => {
        if (showCamera && videoRef.current && stream) {
            videoRef.current.srcObject = stream
        }
    }, [showCamera, stream])

    const copyToClipboard = (text: string) => {
        navigator.clipboard.writeText(text)
        setCopiedId(true)
        setTimeout(() => setCopiedId(false), 2000)
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h3 className="text-xl font-bold tracking-tight flex items-center gap-2">
                        <ShieldCheck className="h-5 w-5 text-primary" /> Panel de Desarrollador (Tenant Dashboard)
                    </h3>
                    <p className="text-sm text-muted-foreground">
                        Aprovisionamiento aislado de tu aplicación cliente y auditoría inmutable en Blockchain.
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant={activeSubTab === "credentials" ? "default" : "outline"}
                        size="sm"
                        onClick={() => setActiveSubTab("credentials")}
                    >
                        Mis Credenciales
                    </Button>
                    <Button
                        variant={activeSubTab === "logs" ? "default" : "outline"}
                        size="sm"
                        onClick={() => setActiveSubTab("logs")}
                    >
                        Auditoría Web3
                    </Button>
                    <Button
                        variant={activeSubTab === "security" ? "default" : "outline"}
                        size="sm"
                        onClick={() => setActiveSubTab("security")}
                    >
                        Seguridad
                    </Button>
                </div>
            </div>

            {error && (
                <div className="p-3 rounded-md bg-destructive/15 text-destructive text-sm font-medium flex items-center gap-2">
                    <AlertCircle className="h-4 w-4" />
                    {error}
                </div>
            )}

            {successMessage && (
                <div className="p-3 rounded-md bg-green-500/10 text-green-600 dark:text-green-400 text-sm font-medium flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4" />
                    {successMessage}
                </div>
            )}

            {loadingClient ? (
                <div className="text-center p-8 text-muted-foreground animate-pulse">Cargando credenciales de Tenant...</div>
            ) : (
                <>
                    {activeSubTab === "credentials" && client && (
                        <div className="grid gap-6 md:grid-cols-3">
                            <Card className="md:col-span-1 border-primary/20">
                                <CardHeader>
                                    <CardTitle className="text-md flex items-center gap-2">
                                        <Key className="w-5 h-5 text-primary" /> Credenciales SSO
                                    </CardTitle>
                                    <CardDescription>
                                        Parámetros necesarios para integrar tu aplicación cliente.
                                    </CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div className="space-y-1">
                                        <Label className="text-xs text-muted-foreground">Nombre de Aplicación</Label>
                                        <div className="font-bold text-foreground text-sm">{client.app_name}</div>
                                    </div>
                                    <div className="space-y-1">
                                        <Label className="text-xs text-muted-foreground">Client ID</Label>
                                        <div className="flex items-center gap-2 mt-1">
                                            <code className="p-1 rounded bg-muted w-full block truncate font-mono text-xs">{client.client_id}</code>
                                            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => copyToClipboard(client.client_id)}>
                                                {copiedId ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
                                            </Button>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>

                            <Card className="md:col-span-2">
                                <CardHeader>
                                    <CardTitle className="text-md flex items-center gap-2">
                                        <FileText className="w-5 h-5 text-primary" /> URIs de Redirección Autorizadas
                                    </CardTitle>
                                    <CardDescription>
                                        Ubicaciones seguras a donde FaceSentinel enviará el token JWT de vuelta.
                                    </CardDescription>
                                </CardHeader>
                                <CardContent>
                                    <ul className="space-y-2">
                                        {client.redirect_uris.map((uri, index) => (
                                            <li key={index} className="p-2.5 rounded bg-muted/50 border border-border/50 text-xs font-mono">
                                                {uri}
                                            </li>
                                        ))}
                                    </ul>
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeSubTab === "logs" && client && (
                        <Card className="w-full">
                            <CardHeader className="flex flex-row items-center justify-between space-y-0">
                                <div>
                                    <CardTitle className="text-md flex items-center gap-2">
                                        <Clock className="w-5 h-5 text-primary" /> Historial de Autenticaciones (Blockchain)
                                    </CardTitle>
                                    <CardDescription>
                                        Registros inmutables en la red Web3 asociados a tu aplicación ({client.app_name}).
                                    </CardDescription>
                                </div>
                                <Button size="sm" variant="outline" onClick={() => fetchAuditLogs(client.client_id)} disabled={loadingLogs}>
                                    <RefreshCw className={`w-4 h-4 ${loadingLogs ? "animate-spin" : ""}`} />
                                </Button>
                            </CardHeader>
                            <CardContent>
                                {loadingLogs ? (
                                    <div className="text-center py-8 text-muted-foreground animate-pulse">Consultando el Smart Contract...</div>
                                ) : auditLogs.length > 0 ? (
                                    <div className="overflow-x-auto">
                                        <table className="w-full text-xs text-left">
                                            <thead className="text-muted-foreground uppercase bg-muted/50 font-semibold">
                                                <tr>
                                                    <th className="px-3 py-2.5 rounded-tl-md">Estado</th>
                                                    <th className="px-3 py-2.5">Usuario (ID)</th>
                                                    <th className="px-3 py-2.5">Dispositivo</th>
                                                    <th className="px-3 py-2.5">Fecha y Hora</th>
                                                    <th className="px-3 py-2.5">Score (ArcFace)</th>
                                                    <th className="px-3 py-2.5 rounded-tr-md">Hash Criptográfico (Blockchain)</th>
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
                                        No se encontraron registros de auditoría en la blockchain para esta aplicación.
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    )}

                    {activeSubTab === "security" && (
                        <div className="grid gap-6 md:grid-cols-2">
                            {/* Cambiar Contraseña */}
                            <Card className="border-primary/10">
                                <CardHeader>
                                    <CardTitle className="text-md flex items-center gap-2">
                                        <Lock className="w-5 h-5 text-primary" /> Cambiar Contraseña
                                    </CardTitle>
                                    <CardDescription>
                                        Actualiza la contraseña temporal que te asignó el administrador.
                                    </CardDescription>
                                </CardHeader>
                                <CardContent>
                                    <form onSubmit={handleChangePassword} className="space-y-4">
                                        <div className="space-y-2">
                                            <Label htmlFor="currPass">Contraseña Actual</Label>
                                            <Input
                                                id="currPass"
                                                type="password"
                                                value={currentPassword}
                                                onChange={e => setCurrentPassword(e.target.value)}
                                                required
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <Label htmlFor="newPass">Nueva Contraseña</Label>
                                            <Input
                                                id="newPass"
                                                type="password"
                                                value={newPassword}
                                                onChange={e => setNewPassword(e.target.value)}
                                                required
                                            />
                                        </div>
                                        <Button type="submit" className="w-full" disabled={updatingPassword}>
                                            {updatingPassword ? "Actualizando..." : "Actualizar Contraseña"}
                                        </Button>
                                    </form>
                                </CardContent>
                            </Card>

                            {/* Enrolamiento Biométrico */}
                            <Card className="border-primary/10">
                                <CardHeader>
                                    <CardTitle className="text-md flex items-center gap-2">
                                        <Camera className="w-5 h-5 text-primary" /> Enrolamiento Facial
                                    </CardTitle>
                                    <CardDescription>
                                        Registra tu rostro para poder iniciar sesión biométricamente en el futuro.
                                    </CardDescription>
                                </CardHeader>
                                <CardContent className="flex flex-col items-center justify-center space-y-4">
                                    {!showCamera ? (
                                        <div className="text-center py-6 space-y-4">
                                            <p className="text-xs text-muted-foreground">
                                                Enrolar tu rostro asocia tu vector facial (ArcFace) con tu cuenta. Podrás ingresar sin usar contraseña.
                                            </p>
                                            <Button variant="outline" onClick={startBiometricEnrollment}>
                                                Iniciar Escáner Facial
                                            </Button>
                                        </div>
                                    ) : (
                                        <div className="w-full flex flex-col items-center space-y-4">
                                            <div className="relative overflow-hidden rounded-lg aspect-video w-full max-w-sm flex items-center justify-center bg-black">
                                                <video
                                                    ref={videoRef}
                                                    autoPlay
                                                    playsInline
                                                    muted
                                                    className="h-full w-full object-cover transform scale-x-[-1]"
                                                />
                                                <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                                                    <div className="w-1/2 h-2/3 border-2 border-white/50 rounded-[40%] border-dashed"></div>
                                                </div>
                                            </div>
                                            <div className="flex gap-2 w-full max-w-sm">
                                                <Button variant="outline" className="w-full" onClick={stopCamera} disabled={cameraLoading}>
                                                    Cancelar
                                                </Button>
                                                <Button className="w-full" onClick={handleEnrollBiometrics} disabled={cameraLoading}>
                                                    {cameraLoading ? "Enrolando..." : "Capturar Rostro"}
                                                </Button>
                                            </div>
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </div>
                    )}
                </>
            )}
        </div>
    )
}
