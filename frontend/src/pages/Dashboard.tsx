import { useEffect, useState, useRef } from "react"
import { useNavigate } from "react-router-dom"
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Activity, ShieldCheck, Lock, LogOut, User, Trash2, Clock, CheckCircle2, XCircle, Camera, RefreshCw, AlertCircle, X, Upload } from "lucide-react"
import axios from "axios"
import { API_BASE_URL } from "@/config/api"
import AdminPanel from "../components/AdminPanel"
import DeveloperPanel from "../components/DeveloperPanel"

interface AuthEvent {
    id?: number
    user_id: string
    access_granted: boolean
    match_score: number
    device_id: string
    tx_hash?: string
    biometric_hash?: string
    timestamp: number
}

export default function Dashboard() {
    const navigate = useNavigate()
    const [dbStatus, setDbStatus] = useState<any>(null)
    const [authHistory, setAuthHistory] = useState<AuthEvent[]>([])
    const [historyLoading, setHistoryLoading] = useState(true)
    const [deleteLoading, setDeleteLoading] = useState(false)

    // User Session
    const userId = localStorage.getItem("user_id") || ""
    const userName = localStorage.getItem("user_name") || "Usuario"
    const userRole = localStorage.getItem("role") || "Desconocido"

    const [activeTab, setActiveTab] = useState<"user" | "admin">(userRole.toLowerCase() === "admin" ? "admin" : "user")
    const baseUrl = API_BASE_URL

    // Self-re-enrollment state
    const [isReenrolling, setIsReenrolling] = useState(false)
    const [selfStream, setSelfStream] = useState<MediaStream | null>(null)
    const [reEnrollLoading, setReEnrollLoading] = useState(false)
    const [reEnrollSuccess, setReEnrollSuccess] = useState("")
    const [reEnrollError, setReEnrollError] = useState("")
    const selfVideoRef = useRef<HTMLVideoElement | null>(null)
    const selfStreamRef = useRef<MediaStream | null>(null)

    const startSelfCamera = async () => {
        setIsReenrolling(true)
        setReEnrollSuccess("")
        setReEnrollError("")
        try {
            let stream: MediaStream
            try {
                stream = await navigator.mediaDevices.getUserMedia({
                    video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" }
                })
            } catch {
                stream = await navigator.mediaDevices.getUserMedia({ video: true })
            }
            selfStreamRef.current = stream
            setSelfStream(stream)
            if (selfVideoRef.current) {
                selfVideoRef.current.srcObject = stream
                selfVideoRef.current.play().catch(() => {})
            }
        } catch (err: any) {
            if (err?.name === "NotAllowedError" || err?.name === "PermissionDeniedError") {
                setReEnrollError("Permiso denegado. Permite el acceso a la cámara en el navegador.")
            } else if (err?.name === "NotReadableError" || err?.name === "TrackStartError") {
                setReEnrollError("La cámara web está siendo ocupada por otra aplicación o pestaña.")
            } else {
                setReEnrollError("No se pudo acceder a la cámara web (" + (err?.message || "Error") + ").")
            }
        }
    }

    const stopSelfCamera = () => {
        if (selfStreamRef.current) {
            selfStreamRef.current.getTracks().forEach(track => track.stop())
            selfStreamRef.current = null
        }
        if (selfStream) {
            selfStream.getTracks().forEach(track => track.stop())
            setSelfStream(null)
        }
        if (selfVideoRef.current) {
            selfVideoRef.current.srcObject = null
        }
        setIsReenrolling(false)
    }

    useEffect(() => {
        if (isReenrolling && selfVideoRef.current && selfStream) {
            selfVideoRef.current.srcObject = selfStream
            selfVideoRef.current.play().catch(e => console.error("Error reproduciendo video:", e))
        }
    }, [isReenrolling, selfStream])

    const captureAndReEnrollSelf = async () => {
        if (!selfVideoRef.current) return
        setReEnrollLoading(true)
        setReEnrollError("")

        const video = selfVideoRef.current
        const width = video.videoWidth || 640
        const height = video.videoHeight || 480

        const canvas = document.createElement("canvas")
        canvas.width = width
        canvas.height = height
        const ctx = canvas.getContext("2d")
        if (!ctx) return
        ctx.drawImage(video, 0, 0, width, height)
        const base64Image = canvas.toDataURL("image/jpeg")

        const token = localStorage.getItem("token") || ""
        try {
            const res = await axios.put(`${baseUrl}/api/v1/users/me/biometrics`, {
                image_base64: base64Image
            }, {
                headers: { Authorization: `Bearer ${token}` }
            })
            setReEnrollSuccess(res.data?.message || "¡Tu biometría facial ha sido actualizada con éxito!")
            stopSelfCamera()
        } catch (err: any) {
            setReEnrollError(err.response?.data?.detail || "Error al actualizar tu biometría facial.")
        } finally {
            setReEnrollLoading(false)
        }
    }

    const handleSelfFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file) return
        setReEnrollLoading(true)
        setReEnrollError("")
        const reader = new FileReader()
        reader.onload = async (ev) => {
            const base64Image = ev.target?.result as string
            if (!base64Image) {
                setReEnrollLoading(false)
                return
            }
            const token = localStorage.getItem("token") || ""
            try {
                const res = await axios.put(`${baseUrl}/api/v1/users/me/biometrics`, {
                    image_base64: base64Image
                }, {
                    headers: { Authorization: `Bearer ${token}` }
                })
                setReEnrollSuccess(res.data?.message || "¡Tu biometría facial ha sido actualizada con éxito!")
                stopSelfCamera()
            } catch (err: any) {
                setReEnrollError(err.response?.data?.detail || "Error al actualizar tu biometría facial.")
            } finally {
                setReEnrollLoading(false)
            }
        }
        reader.readAsDataURL(file)
    }

    useEffect(() => {
        if (!userId) {
            navigate("/")
            return
        }

        // Verificamos conexión con el servidor y estado de la Blockchain
        axios.get(`${baseUrl}/api/v1/health`)
            .then(r => setDbStatus(r.data))
            .catch(() => setDbStatus({ status: "offline", blockchain: "disconnected" }))

        // Cargar historial de acceso (solo para admin)
        const roleLower = userRole.toLowerCase()
        if (roleLower === "admin") {
            const token = localStorage.getItem("token") || ""
            axios.get(`${baseUrl}/api/v1/auth-history/${userId}?limit=50`, {
                headers: { Authorization: `Bearer ${token}` }
            })
                .then(r => {
                    if (r.data.success && r.data.records && r.data.records.length > 0) {
                        setAuthHistory(r.data.records)
                    } else {
                        // Fallback para admin: cargar los eventos globales de acceso físico en Blockchain
                        axios.get(`${baseUrl}/api/v1/clients/PHYSICAL_ACCESS/logs?limit=50`, {
                            headers: { Authorization: `Bearer ${token}` }
                        }).then(cRes => {
                            if (cRes.data.success && cRes.data.records) {
                                setAuthHistory(cRes.data.records)
                            }
                        }).catch(() => {})
                    }
                })
                .catch(err => console.error("Error cargando historial", err))
                .finally(() => setHistoryLoading(false))
        } else {
            setHistoryLoading(false)
        }
    }, [userId, navigate])

    const handleLogout = () => {
        localStorage.clear()
        navigate("/")
    }

    const handleDeleteAccount = async () => {
        if (!window.confirm("¿Estás seguro de que deseas eliminar tu cuenta permanentemente? Tus datos biométricos serán borrados.")) {
            return
        }

        setDeleteLoading(true)
        try {
            await axios.delete(`${baseUrl}/api/v1/users/${userId}`)
            localStorage.clear()
            navigate("/")
        } catch (err) {
            alert("Hubo un error al intentar eliminar la cuenta.")
        } finally {
            setDeleteLoading(false)
        }
    }

    return (
        <div className="min-h-screen bg-muted/20 w-full flex flex-col">
            <header className="sticky top-0 z-10 w-full border-b bg-background/95 shadow-sm backdrop-blur">
                <div className="container mx-auto flex h-16 items-center justify-between px-4">
                    <div className="flex items-center gap-2">
                        <ShieldCheck className="h-6 w-6 text-primary" />
                        <span className="text-lg font-bold">FaceSentinel</span>
                    </div>
                    <Button variant="ghost" size="sm" onClick={handleLogout}>
                        <LogOut className="h-4 w-4 mr-2" /> Salir
                    </Button>
                </div>
            </header>

            <main className="flex-1 container mx-auto p-4 md:p-8 space-y-6">
                {reEnrollSuccess && (
                    <div className="p-3 rounded-md bg-green-500/15 text-green-700 dark:text-green-400 text-sm font-medium flex items-center justify-between border border-green-500/20">
                        <div className="flex items-center gap-2">
                            <CheckCircle2 className="h-4 w-4" />
                            {reEnrollSuccess}
                        </div>
                        <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => setReEnrollSuccess("")}>
                            <X className="h-4 w-4" />
                        </Button>
                    </div>
                )}
                {reEnrollError && (
                    <div className="p-3 rounded-md bg-destructive/15 text-destructive text-sm font-medium flex items-center justify-between border border-destructive/20">
                        <div className="flex items-center gap-2">
                            <AlertCircle className="h-4 w-4" />
                            {reEnrollError}
                        </div>
                        <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => setReEnrollError("")}>
                            <X className="h-4 w-4" />
                        </Button>
                    </div>
                )}

                {userRole.toLowerCase() === "developer" ? (
                    <DeveloperPanel />
                ) : userRole.toLowerCase() !== "admin" ? (
                    // Pantalla minimalista para usuario final (Student / Professor / User)
                    <div className="flex justify-center items-center py-12">
                        <Card className="w-full max-w-md border-primary/20 shadow-lg relative overflow-hidden">
                            <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-transparent opacity-50" />
                            <CardHeader className="text-center space-y-2 pb-4 z-10 relative">
                                <div className="h-14 w-14 rounded-full bg-green-500/10 flex items-center justify-center text-green-600 mx-auto shadow-inner border border-green-200">
                                    <ShieldCheck className="h-8 w-8" />
                                </div>
                                <CardTitle className="text-xl font-extrabold tracking-tight text-foreground">Identidad Activa</CardTitle>
                                <CardDescription className="text-xs">Sesión biométrica iniciada con FaceSentinel</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4 text-sm z-10 relative">
                                <div className="p-4 rounded-lg bg-muted/50 border border-border/50 space-y-3">
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">Nombre:</span>
                                        <span className="font-semibold text-foreground">{userName}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">ID de Usuario:</span>
                                        <span className="font-mono text-foreground font-semibold">{userId}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">Rol asignado:</span>
                                        <span className="font-semibold text-primary">{userRole}</span>
                                    </div>
                                </div>
                            </CardContent>
                            <CardFooter className="z-10 relative pt-2 flex flex-col gap-2">
                                <Button 
                                    className="w-full bg-primary/10 hover:bg-primary/20 text-primary border border-primary/30" 
                                    variant="outline"
                                    onClick={startSelfCamera}
                                >
                                    <Camera className="h-4 w-4 mr-2" />
                                    Actualizar Mi Rostro
                                </Button>
                                <Button 
                                    className="w-full" 
                                    variant="outline"
                                    onClick={handleLogout}
                                >
                                    <LogOut className="h-4 w-4 mr-2" />
                                    Cerrar Sesión
                                </Button>
                            </CardFooter>
                        </Card>
                    </div>
                ) : (
                    // Administrador
                    <>
                        <div className="flex items-center justify-between">
                            <div>
                                <h2 className="text-2xl font-bold tracking-tight">Panel Principal</h2>
                                <p className="text-muted-foreground">
                                    Has accedido a un área segura usando autenticación facial y registros inmutables.
                                </p>
                            </div>
                            <div className="flex bg-muted p-1 rounded-lg border border-border shadow-sm">
                                <Button 
                                    variant={activeTab === "user" ? "default" : "ghost"} 
                                    size="sm" 
                                    className="text-xs h-8"
                                    onClick={() => setActiveTab("user")}
                                >
                                    Mi Panel
                                </Button>
                                <Button 
                                    variant={activeTab === "admin" ? "default" : "ghost"} 
                                    size="sm" 
                                    className="text-xs h-8"
                                    onClick={() => setActiveTab("admin")}
                                >
                                    Consola Admin
                                </Button>
                            </div>
                        </div>

                        {activeTab === "admin" ? (
                            <AdminPanel />
                        ) : (
                            <>
                                <div className="grid gap-4 md:grid-cols-4">
                                    {/* Perfil del Usuario */}
                                    <Card className="md:col-span-1 border-primary/20">
                                        <CardHeader className="pb-2">
                                            <CardTitle className="text-sm font-medium flex items-center">
                                                <User className="h-4 w-4 mr-2 text-primary" /> Mi Perfil
                                            </CardTitle>
                                        </CardHeader>
                                        <CardContent>
                                            <div className="text-xl font-bold truncate">{userName}</div>
                                            <p className="text-xs text-muted-foreground mt-1">ID: {userId}</p>
                                            <p className="text-xs text-muted-foreground">Rol: {userRole}</p>
                                        </CardContent>
                                        <CardFooter className="pt-0 flex flex-col gap-2">
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                className="w-full mt-4 border-primary/30 hover:bg-primary/10 text-primary font-medium"
                                                onClick={startSelfCamera}
                                            >
                                                <Camera className="h-4 w-4 mr-2" />
                                                Actualizar Mi Rostro
                                            </Button>
                                            <Button
                                                variant="destructive"
                                                size="sm"
                                                className="w-full bg-red-500/10 text-red-600 hover:bg-red-500/20 shadow-none border border-red-200"
                                                onClick={handleDeleteAccount}
                                                disabled={deleteLoading}
                                            >
                                                <Trash2 className="h-4 w-4 mr-2" />
                                                {deleteLoading ? "Borrando..." : "Eliminar Cuenta"}
                                            </Button>
                                        </CardFooter>
                                    </Card>

                                    {/* Status Cards */}
                                    <Card className="md:col-span-1">
                                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                            <CardTitle className="text-sm font-medium">Estado Backend</CardTitle>
                                            <Activity className="h-4 w-4 text-muted-foreground" />
                                        </CardHeader>
                                        <CardContent>
                                            <div className="text-2xl font-bold">
                                                {dbStatus?.status === 'online' ? (
                                                    <span className="text-green-600">Online</span>
                                                ) : (
                                                    <span className="text-red-500">Offline</span>
                                                )}
                                            </div>
                                            <p className="text-xs text-muted-foreground mt-1">API Node</p>
                                        </CardContent>
                                    </Card>

                                    <Card className="md:col-span-1">
                                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                            <CardTitle className="text-sm font-medium">Blockchain</CardTitle>
                                            <Lock className="h-4 w-4 text-muted-foreground" />
                                        </CardHeader>
                                        <CardContent>
                                            <div className="text-2xl font-bold">
                                                {dbStatus?.blockchain === 'connected' ? (
                                                    <span className="text-primary">Conectada</span>
                                                ) : (
                                                    <span className="text-muted-foreground">Desconectada</span>
                                                )}
                                            </div>
                                            <p className="text-xs text-muted-foreground mt-1">Status Web3</p>
                                        </CardContent>
                                    </Card>

                                    <Card className="md:col-span-1">
                                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                            <CardTitle className="text-sm font-medium">Seguridad</CardTitle>
                                            <ShieldCheck className="h-4 w-4 text-muted-foreground" />
                                        </CardHeader>
                                        <CardContent>
                                            <div className="text-2xl font-bold text-green-600">Alta</div>
                                            <p className="text-xs text-muted-foreground mt-1">Anti-spoofing activo</p>
                                        </CardContent>
                                    </Card>
                                </div>

                                <Card className="mt-6">
                                    <CardHeader>
                                        <CardTitle className="flex items-center gap-2">
                                            <Clock className="h-5 w-5 text-primary" /> Historial de Acceso
                                        </CardTitle>
                                        <CardDescription>
                                            Registros inmutables en la red Web3 para este usuario.
                                        </CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        {historyLoading ? (
                                            <div className="flex justify-center p-8 text-muted-foreground animate-pulse">
                                                Cargando bloques...
                                            </div>
                                        ) : authHistory.length > 0 ? (
                                            <div className="overflow-x-auto">
                                                <table className="w-full text-sm text-left">
                                                    <thead className="text-xs text-muted-foreground uppercase bg-muted/50">
                                                        <tr>
                                                            <th className="px-4 py-3 rounded-tl-md">Estado</th>
                                                            <th className="px-4 py-3">Dispositivo</th>
                                                            <th className="px-4 py-3">Fecha y Hora</th>
                                                            <th className="px-4 py-3">Score (Distancia)</th>
                                                            <th className="px-4 py-3 rounded-tr-md">Hash Criptográfico (Web3)</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        {authHistory.map((log, i) => (
                                                            <tr key={i} className="border-b last:border-0 hover:bg-muted/20 transition-colors">
                                                                <td className="px-4 py-3">
                                                                    {log.access_granted ? (
                                                                        <span className="flex items-center text-green-600 font-medium">
                                                                            <CheckCircle2 className="w-4 h-4 mr-2" /> Permitido
                                                                        </span>
                                                                    ) : (
                                                                        <span className="flex items-center text-red-600 font-medium">
                                                                            <XCircle className="w-4 h-4 mr-2" /> Denegado
                                                                        </span>
                                                                    )}
                                                                </td>
                                                                <td className="px-4 py-3">
                                                                    <span className="font-mono text-xs px-2 py-0.5 rounded bg-muted text-foreground">
                                                                        {log.device_id || "GATEWAY"}
                                                                    </span>
                                                                </td>
                                                                <td className="px-4 py-3 text-xs">
                                                                    {new Date((log.timestamp as any) * 1000).toLocaleString()}
                                                                </td>
                                                                <td className="px-4 py-3 font-mono text-xs">
                                                                    {log.match_score !== null && log.match_score !== undefined
                                                                        ? log.match_score.toFixed(4)
                                                                        : "N/A"}
                                                                </td>
                                                                <td className="px-4 py-3">
                                                                    {(log.biometric_hash || log.tx_hash) ? (
                                                                        <span
                                                                            className="text-primary font-mono text-xs flex items-center gap-1.5"
                                                                            title={log.biometric_hash || log.tx_hash}
                                                                        >
                                                                            <Lock className="w-3.5 h-3.5 text-primary flex-shrink-0" />
                                                                            {((log.biometric_hash || log.tx_hash) as string).substring(0, 10)}...{((log.biometric_hash || log.tx_hash) as string).substring(((log.biometric_hash || log.tx_hash) as string).length - 8)}
                                                                        </span>
                                                                    ) : (
                                                                        <span className="text-muted-foreground text-xs">Local / Sin Hash</span>
                                                                    )}
                                                                </td>
                                                            </tr>
                                                        ))}
                                                    </tbody>
                                                </table>
                                            </div>
                                        ) : (
                                            <div className="rounded-md border border-dashed p-8 flex flex-col items-center justify-center text-muted-foreground bg-muted/20">
                                                <Clock className="h-8 w-8 mb-4 text-muted-foreground/50" />
                                                <p>No hay eventos registrados en la blockchain para este usuario.</p>
                                            </div>
                                        )}
                                    </CardContent>
                                </Card>
                            </>
                        )}
                    </>
                )}
                {/* Modal Flotante de Captura de Cámara para Auto-Re-Enrolamiento */}
                {isReenrolling && (
                    <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4 backdrop-blur-sm">
                        <Card className="w-full max-w-lg border-primary shadow-2xl bg-card">
                            <CardHeader className="flex flex-row items-center justify-between pb-3">
                                <div>
                                    <CardTitle className="flex items-center gap-2 text-primary text-lg">
                                        <Camera className="w-5 h-5" /> Actualizar Biometría Facial
                                    </CardTitle>
                                    <CardDescription>
                                        Ubica tu rostro dentro del óvalo guía con buena iluminación frontal.
                                    </CardDescription>
                                </div>
                                <Button variant="ghost" size="sm" className="h-8 w-8 p-0" onClick={stopSelfCamera} disabled={reEnrollLoading}>
                                    <X className="h-4 w-4" />
                                </Button>
                            </CardHeader>
                            <CardContent className="flex flex-col items-center space-y-4">
                                <div className="relative overflow-hidden rounded-xl aspect-video w-full flex items-center justify-center bg-black shadow-inner border border-primary/30">
                                    <video
                                        ref={(el) => {
                                            selfVideoRef.current = el
                                            if (el && selfStream && el.srcObject !== selfStream) {
                                                el.srcObject = selfStream
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
                                        <div className="w-1/2 h-3/4 border-2 border-primary/70 rounded-[45%] border-dashed shadow-[0_0_15px_rgba(0,255,200,0.3)] animate-pulse" />
                                    </div>
                                </div>
                                <div className="flex gap-3 w-full">
                                    <Button variant="outline" className="w-full" onClick={stopSelfCamera} disabled={reEnrollLoading}>
                                        Cancelar
                                    </Button>
                                    <Button 
                                        className="w-full bg-primary hover:bg-primary/90 text-primary-foreground font-semibold" 
                                        onClick={captureAndReEnrollSelf} 
                                        disabled={reEnrollLoading}
                                    >
                                        {reEnrollLoading ? (
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
                                <div className="relative flex py-1 items-center w-full">
                                    <div className="flex-grow border-t border-muted"></div>
                                    <span className="flex-shrink mx-3 text-[11px] text-muted-foreground uppercase font-medium">O si la cámara está ocupada</span>
                                    <div className="flex-grow border-t border-muted"></div>
                                </div>
                                <label className="w-full cursor-pointer">
                                    <input type="file" accept="image/*" className="hidden" onChange={handleSelfFileUpload} disabled={reEnrollLoading} />
                                    <div className="w-full inline-flex items-center justify-center rounded-md text-sm font-medium border border-input bg-muted/60 hover:bg-muted py-2 px-4 shadow-sm transition-colors text-foreground gap-2">
                                        <Upload className="w-4 h-4 text-primary" /> Subir Foto o Selfie desde Archivo
                                    </div>
                                </label>
                            </CardContent>
                        </Card>
                    </div>
                )}
            </main>
        </div>
    )
}
