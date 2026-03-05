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

            <Card className="w-full max-w-md shadow-lg border-primary/10 transition-all duration-300">
                <CardHeader className="space-y-1 text-center">
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
                <CardContent>
                    {error && (
                        <div className="mb-4 p-3 rounded-md bg-destructive/15 text-destructive text-sm font-medium text-center flex items-center justify-center gap-2">
                            <AlertCircle className="h-4 w-4" />
                            {error}
                        </div>
                    )}

                    {step === "username" && (
                        <div className="space-y-4">
                            <div className="rounded-lg border bg-card p-4 flex flex-col items-center justify-center text-center space-y-3">
                                <Camera className="h-10 w-10 text-muted-foreground" />
                                <p className="text-sm text-muted-foreground">
                                    Nuestro sistema utiliza reconocimiento facial con prueba activa de vida e inmutabilidad en blockchain.
                                </p>
                                <Button className="w-full mt-2" size="lg" onClick={startCamera}>
                                    Iniciar Escáner Activo
                                </Button>
                            </div>
                        </div>
                    )}

                    {step === "camera" && (
                        <div className="space-y-4 flex flex-col items-center">
                            <div className="relative overflow-hidden rounded-lg border-4 border-primary/20 bg-black w-full aspect-video flex items-center justify-center">
                                <video
                                    ref={videoRef}
                                    autoPlay
                                    playsInline
                                    muted
                                    className="h-full w-full object-cover transform scale-x-[-1]"
                                />

                                {/* Guía Visual */}
                                <div className="absolute inset-0 border-2 border-dashed border-primary/30 m-8 rounded-full pointer-events-none opacity-50" />

                                {/* Overlay de estado */}
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
                </CardContent>
            </Card>
        </div>
    )
}
