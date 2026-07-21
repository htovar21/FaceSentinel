import React, { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Cpu, Plus, Trash2, Copy, Check, MapPin, Activity, AlertCircle, RefreshCw, Key } from "lucide-react"
import axios from "axios"

interface IoTDevice {
    device_id: string
    device_name: string
    device_type: string
    location: string | null
    is_active: boolean
    created_at: string
}

export default function IoTDevicesView() {
    const [devices, setDevices] = useState<IoTDevice[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState("")

    // Form fields
    const [deviceId, setDeviceId] = useState("")
    const [deviceName, setDeviceName] = useState("")
    const [deviceType, setDeviceType] = useState("door")
    const [location, setLocation] = useState("")
    const [registering, setRegistering] = useState(false)

    // Registration Result (contains the plain token)
    const [newDeviceSecret, setNewDeviceSecret] = useState<string | null>(null)
    const [copiedSecret, setCopiedSecret] = useState(false)

    const token = localStorage.getItem("token") || ""
    const baseUrl = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"

    const fetchDevices = async () => {
        setLoading(true)
        setError("")
        try {
            const res = await axios.get(`${baseUrl}/api/v1/devices`, {
                headers: { Authorization: `Bearer ${token}` }
            })
            setDevices(res.data)
        } catch (err: any) {
            setError(err.response?.data?.detail || "No se pudieron cargar los dispositivos de hardware.")
        } finally {
            setLoading(false)
        }
    }

    const handleRegisterDevice = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!deviceId || !deviceName) {
            alert("El ID y el Nombre del dispositivo son obligatorios.")
            return
        }

        setRegistering(true)
        setError("")
        setNewDeviceSecret(null)

        try {
            const res = await axios.post(`${baseUrl}/api/v1/devices`, {
                device_id: deviceId,
                device_name: deviceName,
                device_type: deviceType,
                location: location || null
            }, {
                headers: { Authorization: `Bearer ${token}` }
            })

            // El backend retorna el secreto físico plano para ser copiado una única vez
            setNewDeviceSecret(res.data.client_secret)
            
            // Limpiar formulario
            setDeviceId("")
            setDeviceName("")
            setDeviceType("door")
            setLocation("")
            fetchDevices()
        } catch (err: any) {
            setError(err.response?.data?.detail || "Error al registrar el dispositivo físico.")
        } finally {
            setRegistering(false)
        }
    }

    const handleDeleteDevice = async (id: string) => {
        if (!window.confirm("¿Estás seguro de que deseas eliminar este dispositivo? Se perderán todas sus reglas ACL.")) {
            return
        }

        try {
            await axios.delete(`${baseUrl}/api/v1/devices/${id}`, {
                headers: { Authorization: `Bearer ${token}` }
            })
            fetchDevices()
        } catch (err: any) {
            alert(err.response?.data?.detail || "Error al eliminar el dispositivo.")
        }
    }

    const copyToClipboard = (text: string) => {
        navigator.clipboard.writeText(text)
        setCopiedSecret(true)
        setTimeout(() => setCopiedSecret(false), 2000)
    }

    useEffect(() => {
        if (token) {
            fetchDevices()
        }
    }, [token])

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h3 className="text-xl font-bold tracking-tight flex items-center gap-2">
                        <Cpu className="h-5 w-5 text-primary" /> Gestión de Hardware & Dispositivos IoT
                    </h3>
                    <p className="text-sm text-muted-foreground">
                        Registra puntos de acceso físicos y administra sus tokens de conexión M2M.
                    </p>
                </div>
                <Button variant="outline" size="sm" onClick={fetchDevices} disabled={loading}>
                    <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} /> Actualizar
                </Button>
            </div>

            {error && (
                <div className="p-3 rounded-md bg-destructive/15 text-destructive text-sm font-medium flex items-center gap-2">
                    <AlertCircle className="h-4 w-4" />
                    {error}
                </div>
            )}

            <div className="grid gap-6 md:grid-cols-3">
                {/* Formulario de Registro */}
                <Card className="md:col-span-1 border-primary/20">
                    <CardHeader>
                        <CardTitle className="text-md flex items-center gap-2">
                            <Plus className="w-5 h-5 text-primary" /> Registrar Dispositivo
                        </CardTitle>
                        <CardDescription>
                            Añade una puerta, cámara o relé biométrico al sistema.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <form onSubmit={handleRegisterDevice} className="space-y-4">
                            <div className="space-y-2">
                                <Label htmlFor="deviceId">ID del Dispositivo (Único)</Label>
                                <Input
                                    id="deviceId"
                                    placeholder="door_main_floor"
                                    value={deviceId}
                                    onChange={e => setDeviceId(e.target.value)}
                                    required
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="deviceName">Nombre Descriptivo</Label>
                                <Input
                                    id="deviceName"
                                    placeholder="Puerta Principal Acceso A"
                                    value={deviceName}
                                    onChange={e => setDeviceName(e.target.value)}
                                    required
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="deviceType">Tipo de Dispositivo</Label>
                                <select
                                    id="deviceType"
                                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                    value={deviceType}
                                    onChange={e => setDeviceType(e.target.value)}
                                >
                                    <option value="door">Cerradura / Puerta</option>
                                    <option value="camera">Cámara RTSP / Videovigilancia</option>
                                    <option value="turnstile">Torniquete / Molinete</option>
                                    <option value="gateway">Edge Gateway</option>
                                </select>
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="location">Ubicación física</Label>
                                <Input
                                    id="location"
                                    placeholder="Edificio B, Planta Baja"
                                    value={location}
                                    onChange={e => setLocation(e.target.value)}
                                />
                            </div>
                            <Button type="submit" className="w-full" disabled={registering}>
                                {registering ? "Registrando..." : "Registrar Dispositivo"}
                            </Button>
                        </form>

                        {/* Alerta de Secret Token */}
                        {newDeviceSecret && (
                            <div className="mt-4 p-4 rounded-lg bg-yellow-500/10 border border-yellow-500/30 text-xs space-y-3 relative overflow-hidden">
                                <div className="absolute top-0 left-0 h-full w-1 bg-yellow-500" />
                                <p className="font-semibold text-yellow-700 dark:text-yellow-400 flex items-center gap-1.5">
                                    <Key className="w-4 h-4" /> ¡GUARDE ESTE TOKEN AHORA!
                                </p>
                                <p className="text-muted-foreground leading-normal">
                                    Este es el **Hardware Token** (`client_secret`) del dispositivo. Copie este valor y péguelo en su script `edge_gateway.py`. **No se volverá a mostrar por seguridad.**
                                </p>
                                <div className="flex items-center gap-2 mt-2">
                                    <code className="p-2 rounded bg-muted w-full block font-mono text-[10px] break-all select-all font-semibold border text-foreground">
                                        {newDeviceSecret}
                                    </code>
                                    <Button size="icon" variant="outline" className="h-8 w-8 shrink-0 bg-background" onClick={() => copyToClipboard(newDeviceSecret)}>
                                        {copiedSecret ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
                                    </Button>
                                </div>
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Tabla de Dispositivos */}
                <Card className="md:col-span-2">
                    <CardHeader>
                        <CardTitle className="text-md flex items-center gap-2">
                            <Activity className="w-5 h-5 text-primary" /> Dispositivos Registrados
                        </CardTitle>
                        <CardDescription>
                            Hardware activo y conectado reportando biometría local.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        {loading ? (
                            <div className="text-center p-8 text-muted-foreground animate-pulse">Cargando dispositivos...</div>
                        ) : devices.length > 0 ? (
                            <div className="overflow-x-auto">
                                <table className="w-full text-xs text-left">
                                    <thead className="text-muted-foreground uppercase bg-muted/50 font-semibold border-b">
                                        <tr>
                                            <th className="px-4 py-3 rounded-tl-md">Nombre / ID</th>
                                            <th className="px-4 py-3">Tipo</th>
                                            <th className="px-4 py-3">Ubicación</th>
                                            <th className="px-4 py-3">Estado</th>
                                            <th className="px-4 py-3 rounded-tr-md text-right">Acciones</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {devices.map((device) => (
                                            <tr key={device.device_id} className="border-b last:border-0 hover:bg-muted/10 transition-colors">
                                                <td className="px-4 py-3">
                                                    <div className="font-bold text-foreground">{device.device_name}</div>
                                                    <div className="text-[10px] font-mono text-muted-foreground">{device.device_id}</div>
                                                </td>
                                                <td className="px-4 py-3 capitalize text-muted-foreground">{device.device_type}</td>
                                                <td className="px-4 py-3 text-muted-foreground">
                                                    {device.location ? (
                                                        <span className="flex items-center gap-1">
                                                            <MapPin className="h-3 w-3 text-primary shrink-0" />
                                                            {device.location}
                                                        </span>
                                                    ) : (
                                                        <span className="italic text-muted-foreground/60">Sin ubicación</span>
                                                    )}
                                                </td>
                                                <td className="px-4 py-3">
                                                    {device.is_active ? (
                                                        <span className="px-2 py-0.5 rounded-full bg-green-500/10 text-green-600 font-semibold border border-green-200">
                                                            Activo
                                                        </span>
                                                    ) : (
                                                        <span className="px-2 py-0.5 rounded-full bg-destructive/10 text-destructive font-semibold border border-destructive/20">
                                                            Inactivo
                                                        </span>
                                                    )}
                                                </td>
                                                <td className="px-4 py-3 text-right">
                                                    <Button 
                                                        variant="ghost" 
                                                        size="icon" 
                                                        className="h-8 w-8 text-destructive hover:bg-destructive/10" 
                                                        onClick={() => handleDeleteDevice(device.device_id)}
                                                    >
                                                        <Trash2 className="h-4 w-4" />
                                                    </Button>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        ) : (
                            <div className="text-center p-8 text-muted-foreground border border-dashed rounded-md bg-muted/10">
                                No se encontraron dispositivos físicos de hardware registrados.
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}
