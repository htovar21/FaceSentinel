import { useState, useRef, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { CheckCircle2, UserPlus, ArrowLeft, ArrowRight } from "lucide-react"
import axios from "axios"

export default function Signup() {
    const navigate = useNavigate()
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState("")
    const [step, setStep] = useState<"form" | "camera" | "success">("form")

    // Data State
    const [formData, setFormData] = useState({ id: "", name: "", role: "Student" })

    const videoRef = useRef<HTMLVideoElement>(null)
    const [stream, setStream] = useState<MediaStream | null>(null)

    const handleNext = (e: React.FormEvent) => {
        e.preventDefault()
        if (!formData.id || !formData.name || !formData.role) {
            setError("Por favor completa todos los campos.")
            return
        }
        setError("")
        startCamera()
    }

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

    const handleRegister = async () => {
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
            const response = await axios.post("http://127.0.0.1:8000/api/v1/register", {
                user_id: formData.id,
                name: formData.name,
                role: formData.role,
                image_base64: base64Image
            })

            if (response.data.success) {
                stopCamera()
                setStep("success")
                setTimeout(() => {
                    navigate("/")
                }, 3000)
            } else {
                setError(response.data.message || "Registro fallido")
            }
        } catch (err: any) {
            setError(err.response?.data?.detail || "Error al conectar con el servidor")
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="flex min-h-screen w-full items-center justify-center bg-muted/40 p-4">
            <div className="absolute top-4 left-4">
                <Button variant="ghost" onClick={() => navigate("/")}>
                    <ArrowLeft className="mr-2 h-4 w-4" /> Volver
                </Button>
            </div>

            <Card className="w-full max-w-md shadow-lg border-primary/10">
                <CardHeader className="space-y-1 text-center">
                    <div className="flex justify-center mb-4">
                        <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                            <UserPlus className="h-8 w-8" />
                        </div>
                    </div>
                    <CardTitle className="text-2xl font-bold tracking-tight">Registro de Usuario</CardTitle>
                    <CardDescription>
                        {step === "form" && "Ingresa tus datos para registrar tu perfil."}
                        {step === "camera" && "Captura tu rostro para el acceso biométrico."}
                        {step === "success" && "¡Registro completado exitosamente!"}
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {error && (
                        <div className="mb-4 p-3 rounded-md bg-destructive/15 text-destructive text-sm font-medium text-center">
                            {error}
                        </div>
                    )}

                    {step === "form" && (
                        <form onSubmit={handleNext} className="space-y-4">
                            <div className="space-y-2">
                                <Label htmlFor="id">ID de Usuario (ej. V-1234567)</Label>
                                <Input
                                    id="id"
                                    placeholder="V-1234567"
                                    value={formData.id}
                                    onChange={e => setFormData({ ...formData, id: e.target.value })}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="name">Nombre Completo</Label>
                                <Input
                                    id="name"
                                    placeholder="Juan Pérez"
                                    value={formData.name}
                                    onChange={e => setFormData({ ...formData, name: e.target.value })}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="role">Rol</Label>
                                <select
                                    id="role"
                                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background disabled:cursor-not-allowed disabled:opacity-50"
                                    value={formData.role}
                                    onChange={e => setFormData({ ...formData, role: e.target.value })}
                                >
                                    <option value="Student">Estudiante</option>
                                    <option value="Professor">Profesor</option>
                                    <option value="Admin">Administrador</option>
                                </select>
                            </div>
                            <Button type="submit" className="w-full mt-4">
                                Continuar a Escaneo Facial <ArrowRight className="ml-2 h-4 w-4" />
                            </Button>
                        </form>
                    )}

                    {step === "camera" && (
                        <div className="space-y-4 flex flex-col items-center">
                            <div className="relative overflow-hidden rounded-lg border border-input aspect-video w-full flex items-center justify-center bg-black">
                                <video
                                    ref={videoRef}
                                    autoPlay
                                    playsInline
                                    muted
                                    className="h-full w-full object-cover"
                                />

                                {/* Guía facial */}
                                <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                                    <div className="w-1/2 h-2/3 border-2 border-white/50 rounded-[40%] border-dashed"></div>
                                </div>
                            </div>

                            <p className="text-sm text-muted-foreground text-center">
                                Mira fijamente a la cámara y asegúrate de tener buena iluminación.
                            </p>

                            <div className="w-full flex gap-2 pt-2">
                                <Button
                                    variant="outline"
                                    className="w-full"
                                    onClick={() => { stopCamera(); setStep("form"); setError(""); }}
                                    disabled={loading}
                                >
                                    Atrás
                                </Button>
                                <Button
                                    className="w-full"
                                    onClick={handleRegister}
                                    disabled={loading}
                                >
                                    {loading ? "Registrando..." : "Capturar y Finalizar"}
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
                                <h3 className="text-xl font-semibold">¡Todo listo!</h3>
                                <p className="text-muted-foreground">Tu perfil ha sido registrado con seguridad blockchain.</p>
                            </div>
                            <Button className="w-full mt-4" onClick={() => navigate("/")}>
                                Ir al Inicio de Sesión
                            </Button>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
