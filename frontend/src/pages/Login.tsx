import { useState, useRef, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Camera, CheckCircle2, UserCircle2, ArrowRight } from "lucide-react"
import axios from "axios"

export default function Login() {
    const navigate = useNavigate()
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState("")
    const [step, setStep] = useState<"username" | "camera" | "success">("username")
    const [userName, setUserName] = useState("")

    const videoRef = useRef<HTMLVideoElement>(null)
    const [stream, setStream] = useState<MediaStream | null>(null)

    const startCamera = async () => {
        try {
            const mediaStream = await navigator.mediaDevices.getUserMedia({ video: true })
            setStream(mediaStream)
            setStep("camera")
        } catch (err) {
            setError("No se pudo acceder a la cámara. Revisa los permisos.")
        }
    }

    const stopCamera = () => {
        if (stream) {
            stream.getTracks().forEach(track => track.stop())
            setStream(null)
        }
    }

    // Assign stream to video element when it becomes available
    useEffect(() => {
        if (step === "camera" && videoRef.current && stream) {
            videoRef.current.srcObject = stream
        }
    }, [step, stream])

    const handleAuthenticate = async () => {
        if (!videoRef.current) return

        setLoading(true)
        setError("")

        // Capture image
        const video = videoRef.current
        const width = video.videoWidth || video.clientWidth || 640
        const height = video.videoHeight || video.clientHeight || 480

        const canvas = document.createElement("canvas")
        canvas.width = width
        canvas.height = height
        const ctx = canvas.getContext("2d")
        if (!ctx) return

        ctx.drawImage(video, 0, 0, width, height)
        const base64Image = canvas.toDataURL("image/jpeg")

        try {
            const response = await axios.post("http://127.0.0.1:8000/api/v1/authenticate", {
                image_base64: base64Image
            })

            if (response.data.success) {
                // Store session details
                localStorage.setItem("user_id", response.data.user_id || "")
                localStorage.setItem("user_name", response.data.user_name || "Usuario verificado")
                localStorage.setItem("role", response.data.role || "")

                setUserName(response.data.user_name || "Usuario verificado")
                stopCamera()
                setStep("success")
                setTimeout(() => {
                    navigate("/dashboard")
                }, 2000)
            } else {
                setError(response.data.message || "Autenticación fallida")
            }
        } catch (err: any) {
            setError(err.response?.data?.detail || "Error al conectar con el servidor")
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="flex h-screen w-full items-center justify-center bg-muted/40 p-4">
            <div className="absolute top-4 right-4">
                <Button variant="ghost" onClick={() => navigate("/signup")}>
                    Registrarse <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
            </div>

            <Card className="w-full max-w-md shadow-lg border-primary/10">
                <CardHeader className="space-y-1 text-center">
                    <div className="flex justify-center mb-4">
                        <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                            <UserCircle2 className="h-8 w-8" />
                        </div>
                    </div>
                    <CardTitle className="text-2xl font-bold tracking-tight">Acceso a FaceSentinel</CardTitle>
                    <CardDescription>
                        {step === "username" && "Inicia sesión con tu rostro para entrar"}
                        {step === "camera" && "Mira a la cámara para autenticarte"}
                        {step === "success" && "¡Identidad verificada!"}
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {error && (
                        <div className="mb-4 p-3 rounded-md bg-destructive/15 text-destructive text-sm font-medium text-center">
                            {error}
                        </div>
                    )}

                    {step === "username" && (
                        <div className="space-y-4">
                            <div className="rounded-lg border bg-card p-4 flex flex-col items-center justify-center text-center space-y-3">
                                <Camera className="h-10 w-10 text-muted-foreground" />
                                <p className="text-sm text-muted-foreground">
                                    Nuestro sistema utiliza reconocimiento facial de grado industrial con inmutabilidad en blockchain.
                                </p>
                                <Button className="w-full mt-2" size="lg" onClick={startCamera}>
                                    Iniciar Escáner Facial
                                </Button>
                            </div>
                        </div>
                    )}

                    {step === "camera" && (
                        <div className="space-y-4 flex flex-col items-center">
                            <div className="relative overflow-hidden rounded-lg border-4 border-primary/20 bg-black aspect-video w-full flex items-center justify-center">
                                <video
                                    ref={videoRef}
                                    autoPlay
                                    playsInline
                                    muted
                                    className="h-full w-full object-cover"
                                />

                                {/* Animación de escaneo simulada */}
                                <div className="absolute top-0 w-full h-1 bg-primary/80 shadow-[0_0_10px_2px_rgba(59,130,246,0.6)] animate-[scan_2s_ease-in-out_infinite]" />
                            </div>

                            <div className="w-full flex gap-2">
                                <Button
                                    variant="outline"
                                    className="w-full"
                                    onClick={() => { stopCamera(); setStep("username"); setError(""); }}
                                    disabled={loading}
                                >
                                    Cancelar
                                </Button>
                                <Button
                                    className="w-full"
                                    onClick={handleAuthenticate}
                                    disabled={loading}
                                >
                                    {loading ? "Verificando..." : "Autenticar"}
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

            <style>{`
        @keyframes scan {
          0% { top: 0; }
          50% { top: 100%; }
          100% { top: 0; }
        }
      `}</style>
        </div>
    )
}
