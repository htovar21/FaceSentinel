import { useState, useRef, useEffect, useCallback } from "react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Camera, CheckCircle2, UserCircle2, ArrowRight, ShieldCheck, AlertCircle } from "lucide-react"
import axios from "axios"

export default function Login() {
    const navigate = useNavigate()
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState("")
    const [step, setStep] = useState<"username" | "camera" | "success">("username")
    const [userName, setUserName] = useState("")
    const [livenessMessage, setLivenessMessage] = useState("Iniciando conexión segura...")
    const [livenessMetrics, setLivenessMetrics] = useState<any>(null)
    const [authDistance, setAuthDistance] = useState<number | null>(null)

    const videoRef = useRef<HTMLVideoElement>(null)
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const wsRef = useRef<WebSocket | null>(null)
    const streamRef = useRef<MediaStream | null>(null)
    const intervalRef = useRef<number | null>(null)

    const stopCameraAndSocket = useCallback(() => {
        if (intervalRef.current) {
            window.clearInterval(intervalRef.current)
            intervalRef.current = null
        }
        if (wsRef.current) {
            wsRef.current.close()
            wsRef.current = null
        }
        if (streamRef.current) {
            streamRef.current.getTracks().forEach(track => track.stop())
            streamRef.current = null
        }
    }, [])

    useEffect(() => {
        return () => {
            stopCameraAndSocket()
        }
    }, [stopCameraAndSocket])

    const startCamera = async () => {
        try {
            const mediaStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } })
            streamRef.current = mediaStream
            setStep("camera")
            setLivenessMetrics(null)
            setAuthDistance(null)
            setError("")
            setLivenessMessage("Conectando con motor Anti-Spoofing...")
        } catch (err) {
            setError("No se pudo acceder a la cámara. Revisa los permisos.")
        }
    }

    // Capture and send frame
    const sendFrame = useCallback(() => {
        if (!videoRef.current || !canvasRef.current || !wsRef.current) return
        if (wsRef.current.readyState !== WebSocket.OPEN) return

        const video = videoRef.current
        const canvas = canvasRef.current
        const ctx = canvas.getContext("2d")

        if (!ctx || video.videoWidth === 0) return

        canvas.width = video.videoWidth
        canvas.height = video.videoHeight
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height)

        // JPEG compression to save bandwidth
        const rawBase64Image = canvas.toDataURL("image/jpeg", 0.7)
        // Remove the data URL prefix so python can decode it directly
        const base64Image = rawBase64Image.replace(/^data:image\/[a-z]+;base64,/, "")

        wsRef.current.send(JSON.stringify({ image_base64: base64Image }))
    }, [])

    const handleAuthenticate = async (finalImageBase64: string) => {
        setLoading(true)
        setError("")
        setLivenessMessage("Identificando usuario en Blockchain...")

        try {
            const response = await axios.post("http://127.0.0.1:8000/api/v1/authenticate", {
                image_base64: finalImageBase64
            })

            if (response.data.success) {
                // Store session details
                setAuthDistance(response.data.match_score)
                localStorage.setItem("user_id", response.data.user_id || "")
                localStorage.setItem("user_name", response.data.user_name || "Usuario verificado")
                localStorage.setItem("role", response.data.role || "")

                setUserName(response.data.user_name || "Usuario verificado")
                stopCameraAndSocket()
                setStep("success")
                setTimeout(() => {
                    navigate("/dashboard")
                }, 2000)
            } else {
                setError(response.data.message || "Autenticación fallida")
                setLivenessMessage("Reintentando...")
                // Restart liveness tracking
                if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                    intervalRef.current = window.setInterval(sendFrame, 100)
                }
            }
        } catch (err: any) {
            setError(err.response?.data?.detail || "Error al conectar con el servidor")
            setLivenessMessage("Ocurrió un error. Reintentando...")
            // Restart liveness tracking after a short delay
            setTimeout(() => {
                setError("")
                if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                    setLivenessMessage("Analizando... Por favor, mira fijamente y parpadea.")
                    intervalRef.current = window.setInterval(sendFrame, 100)
                }
            }, 2500)
        } finally {
            setLoading(false)
        }
    }

    // Initialize WebRTC and WebSocket
    useEffect(() => {
        if (step === "camera" && videoRef.current && streamRef.current) {
            videoRef.current.srcObject = streamRef.current

            // Connect to WebSocket
            const wsUrl = "ws://127.0.0.1:8000/api/v1/ws/liveness"
            const ws = new WebSocket(wsUrl)
            wsRef.current = ws

            ws.onopen = () => {
                setLivenessMessage("Analizando... Por favor, mira fijamente y parpadea.")
                // Send frame 10 times per second
                intervalRef.current = window.setInterval(sendFrame, 100)
            }

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data)

                if (data.status === "passed") {
                    // Liveness passed! Stop streaming and capture HD frame for Auth
                    if (intervalRef.current) clearInterval(intervalRef.current)
                    setLivenessMessage(data.message)
                    setLivenessMetrics(data.metrics)

                    // Capture high quality frame
                    const canvas = canvasRef.current
                    if (canvas && videoRef.current) {
                        const ctx = canvas.getContext("2d")
                        canvas.width = videoRef.current.videoWidth
                        canvas.height = videoRef.current.videoHeight
                        ctx?.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height)
                        const capture = canvas.toDataURL("image/jpeg", 0.95)

                        handleAuthenticate(capture)
                    }
                } else if (data.status === "spoof_detected") {
                    // Stop tracking momentarily so user can read the warning
                    if (intervalRef.current) clearInterval(intervalRef.current)
                    setError(data.message)
                    setLivenessMessage("Bloqueo de seguridad activado.")
                    setLivenessMetrics(data.metrics)

                    // Resume tracking after 3 seconds
                    setTimeout(() => {
                        setError("")
                        setLivenessMessage("Analizando... Por favor, mira fijamente y parpadea.")
                        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                            intervalRef.current = window.setInterval(sendFrame, 100)
                        }
                    }, 3000)
                } else if (data.status === "tracking" || data.status === "no_face") {
                    setLivenessMessage(data.message)
                } else if (data.status === "error") {
                    setError("Error del servidor: " + data.message)
                }
            }

            ws.onerror = () => {
                setError("No se pudo conectar al motor de liveness.")
                setLivenessMessage("Error de conexión WS")
            }
        }
    }, [step, sendFrame])

    return (
        <div className="flex h-screen w-full items-center justify-center bg-muted/40 p-4">
            {/* Canvas en memoria usado para extraer los frames */}
            <canvas ref={canvasRef} style={{ display: "none" }} />

            <div className="absolute top-4 right-4">
                <Button variant="ghost" onClick={() => navigate("/signup")}>
                    Registrarse <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
            </div>

            <Card className={`w-full ${step !== "username" ? "max-w-4xl" : "max-w-md"} shadow-lg border-primary/10 transition-all duration-300`}>
                <CardHeader className="space-y-1 text-center md:col-span-full">
                    <div className="flex justify-center mb-4">
                        <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                            {step === "success" ? <ShieldCheck className="h-8 w-8" /> : <UserCircle2 className="h-8 w-8" />}
                        </div>
                    </div>
                    <CardTitle className="text-2xl font-bold tracking-tight">Acceso a FaceSentinel</CardTitle>
                    <CardDescription>
                        {step === "username" && "Inicia sesión con tu rostro para entrar"}
                        {step === "camera" && "Prueba de Vida Activa Requerida"}
                        {step === "success" && "¡Identidad verificada!"}
                    </CardDescription>
                </CardHeader>

                <CardContent className={`${step !== "username" ? "md:grid md:grid-cols-2 md:gap-6 items-start" : ""}`}>
                    {/* Mensaje global de error */}
                    {error && step === "username" && (
                        <div className="mb-4 p-3 rounded-md bg-destructive/15 text-destructive text-sm font-medium text-center flex items-center justify-center gap-2">
                            <AlertCircle className="h-4 w-4" />
                            {error}
                        </div>
                    )}

                    {/* Columna Izquierda: Input / Cámara */}
                    <div className="w-full flex flex-col space-y-4">
                        {error && step !== "username" && (
                            <div className="p-3 rounded-md bg-destructive/15 text-destructive text-sm font-medium text-center flex items-center justify-center gap-2">
                                <AlertCircle className="h-4 w-4" />
                                {error}
                            </div>
                        )}

                        {step === "username" && (
                            <div className="rounded-lg border bg-card p-4 flex flex-col items-center justify-center text-center space-y-3">
                                <Camera className="h-10 w-10 text-muted-foreground" />
                                <p className="text-sm text-muted-foreground">
                                    Nuestro sistema utiliza reconocimiento facial con prueba activa de vida e inmutabilidad en blockchain.
                                </p>
                                <Button className="w-full mt-2" size="lg" onClick={startCamera}>
                                    Iniciar Escáner Activo
                                </Button>
                            </div>
                        )}

                        {step === "camera" && (
                            <div className="space-y-4 flex flex-col items-center">
                                <div className="relative overflow-hidden rounded-lg border-4 border-primary/20 bg-black w-full aspect-video flex items-center justify-center shadow-inner">
                                    <video
                                        ref={videoRef}
                                        autoPlay
                                        playsInline
                                        muted
                                        className="h-full w-full object-cover transform scale-x-[-1]"
                                    />

                                    {/* Guía Visual */}
                                    <div className="absolute inset-0 border-2 border-dashed border-primary/30 m-8 rounded-full pointer-events-none opacity-50" />

                                    {/* Overlay de procesamiento */}
                                    {loading && (
                                        <div className="absolute inset-0 bg-background/80 flex items-center justify-center backdrop-blur-sm">
                                            <div className="flex flex-col items-center space-y-2">
                                                <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
                                                <p className="text-sm font-medium">Procesando Identidad...</p>
                                            </div>
                                        </div>
                                    )}
                                </div>

                                <div className="w-full text-center p-3 rounded-lg bg-secondary/50 border border-border">
                                    <p className="text-sm font-medium animate-pulse text-foreground">
                                        {livenessMessage}
                                    </p>
                                </div>

                                <div className="w-full">
                                    <Button
                                        variant="outline"
                                        className="w-full"
                                        onClick={() => { stopCameraAndSocket(); setStep("username"); setError(""); }}
                                        disabled={loading}
                                    >
                                        Cancelar
                                    </Button>
                                </div>
                            </div>
                        )}

                        {step === "success" && (
                            <div className="flex flex-col items-center justify-center py-6 space-y-4">
                                <div className="h-16 w-16 rounded-full bg-green-100 flex items-center justify-center">
                                    <CheckCircle2 className="h-10 w-10 text-green-600" />
                                </div>
                                <div className="text-center">
                                    <h3 className="text-xl font-semibold">¡Bienvenido!</h3>
                                    <p className="text-muted-foreground">{userName}</p>
                                </div>
                                <p className="text-sm text-center text-muted-foreground animate-pulse">
                                    Redirigiendo al panel seguro...
                                </p>
                            </div>
                        )}
                    </div>

                    {/* Columna Derecha: Métricas en Vivo */}
                    {(step === "camera" || step === "success") && (
                        <div className="w-full h-full flex flex-col justify-start mt-6 md:mt-0">
                            <div className="p-5 rounded-xl border border-border shadow-sm flex-1 flex flex-col items-center justify-center bg-card/50 relative overflow-hidden group">
                                <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-transparent opacity-50" />

                                {!livenessMetrics ? (
                                    <div className="text-center space-y-3 z-10 w-full opacity-60">
                                        <ShieldCheck className="h-12 w-12 mx-auto text-muted-foreground opacity-50" />
                                        <h4 className="text-sm font-medium uppercase tracking-wider text-muted-foreground">Monitor de Vida</h4>
                                        <p className="text-xs text-muted-foreground max-w-[200px] mx-auto">
                                            Esperando detección biométrica para generar métricas de Anti-Spoofing...
                                        </p>
                                    </div>
                                ) : (
                                    <div className="w-full space-y-4 z-10">
                                        <h4 className="text-sm font-semibold text-primary flex items-center gap-2 border-b border-border/50 pb-2">
                                            <ShieldCheck className="w-5 h-5" />
                                            Monitor de Liveness Activo
                                        </h4>
                                        <div className="space-y-3 text-xs w-full">
                                            <div className="grid grid-cols-4 gap-2 items-center px-2 py-1.5 rounded bg-muted/50 font-medium text-muted-foreground w-full">
                                                <span className="col-span-1">Filtro</span>
                                                <span className="col-span-1 text-center">Score</span>
                                                <span className="col-span-1 text-center">Umbral</span>
                                                <span className="col-span-1 text-right">Impacto</span>
                                            </div>

                                            <div className={`grid grid-cols-4 gap-2 items-center p-3 rounded-md transition-all ${livenessMetrics.blink ? 'bg-green-500/10 border-l-4 border-green-500 text-green-800 dark:text-green-300' : 'bg-destructive/10 border-l-4 border-destructive text-destructive'}`}>
                                                <span className="col-span-1 font-semibold flex items-center gap-1">EAR</span>
                                                <span className="col-span-1 text-center font-mono font-bold text-sm tracking-tight">{Number(livenessMetrics.blink?.value)?.toFixed(3)}</span>
                                                <span className="col-span-1 text-center font-mono opacity-80">{livenessMetrics.blink?.threshold}</span>
                                                <span className="col-span-1 text-right text-[10px] opacity-70 leading-tight">Pre-req<br />Biométrico</span>
                                            </div>

                                            <div className={`grid grid-cols-4 gap-2 items-center p-3 rounded-md transition-all ${livenessMetrics.texture?.value >= 4.75 ? 'bg-green-500/10 border-l-4 border-green-500 text-green-800 dark:text-green-300' : 'bg-destructive/10 border-l-4 border-destructive text-destructive'}`}>
                                                <span className="col-span-1 font-semibold flex items-center gap-1">LBP</span>
                                                <span className="col-span-1 text-center font-mono font-bold text-sm tracking-tight">{Number(livenessMetrics.texture?.value)?.toFixed(3)}</span>
                                                <span className="col-span-1 text-center font-mono opacity-80">{livenessMetrics.texture?.threshold}</span>
                                                <span className="col-span-1 text-right text-[10px] opacity-70 leading-tight">Densidad<br />Textura 3D</span>
                                            </div>

                                            <div className="grid grid-cols-4 gap-2 items-center p-3 rounded-md bg-muted/30 border-l-4 border-muted-foreground/30 opacity-60">
                                                <span className="col-span-1 font-semibold flex items-center gap-1">FFT</span>
                                                <span className="col-span-1 text-center font-mono text-sm tracking-tight">{livenessMetrics.frequency?.value ? Number(livenessMetrics.frequency?.value)?.toFixed(3) : 'N/A'}</span>
                                                <span className="col-span-1 text-center font-mono">{livenessMetrics.frequency?.threshold}</span>
                                                <span className="col-span-1 text-right text-[10px] leading-tight">Bypass<br />(OLEDs)</span>
                                            </div>

                                            {authDistance !== null && (
                                                <div className="grid grid-cols-4 gap-2 items-center p-3 rounded-md bg-primary/10 border-l-4 border-primary mt-4 pt-3 shadow-sm transform scale-105 origin-left transition-all">
                                                    <span className="col-span-1 font-bold text-primary">ArcFace</span>
                                                    <span className="col-span-1 text-center font-mono font-bold text-sm tracking-tight text-primary drop-shadow-[0_0_8px_rgba(var(--primary),0.5)]">{authDistance.toFixed(4)}</span>
                                                    <span className="col-span-1 text-center font-mono text-primary/80 font-medium">&lt; 0.68</span>
                                                    <span className="col-span-1 text-right text-[10px] font-bold text-primary/90 leading-tight">Match<br />Identidad</span>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
