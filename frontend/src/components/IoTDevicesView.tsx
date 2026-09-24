import React, { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Cpu, Plus, Trash2, Copy, Check, MapPin, Activity, AlertCircle, RefreshCw, Key, Video, Sliders, Edit2, X, Download, Target, Play, Sparkles } from "lucide-react"
import axios from "axios"
import { API_BASE_URL } from "@/config/api"

interface IoTDevice {
    device_id: string
    device_name: string
    device_type: string
    location: string | null
    stream_url?: string | null
    lbp_threshold?: number
    is_active: boolean
    created_at: string
}

export default function IoTDevicesView() {
    const [devices, setDevices] = useState<IoTDevice[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState("")

    // Form fields para registro
    const [deviceId, setDeviceId] = useState("")
    const [deviceName, setDeviceName] = useState("")
    const [deviceType, setDeviceType] = useState("camera")
    const [location, setLocation] = useState("")
    const [streamUrl, setStreamUrl] = useState("")
    const [lbpThreshold, setLbpThreshold] = useState("3.670")
    const [registering, setRegistering] = useState(false)

    // Modal de edición / calibración
    const [editingDevice, setEditingDevice] = useState<IoTDevice | null>(null)
    const [editThreshold, setEditThreshold] = useState("3.670")
    const [editStreamUrl, setEditStreamUrl] = useState("")
    const [editLocation, setEditLocation] = useState("")
    const [savingEdit, setSavingEdit] = useState(false)

    // Auto-calibración sensorial en vivo desde la plataforma web
    const [autoCalibrating, setAutoCalibrating] = useState(false)
    const [calibResult, setCalibResult] = useState<any>(null)
    const [calibError, setCalibError] = useState("")

    // Token generado en registro
    const [newDeviceSecret, setNewDeviceSecret] = useState<string | null>(null)
    const [copiedSecret, setCopiedSecret] = useState(false)

    // Modal de exportación de configuración Edge Gateway (cameras.json)
    const [exportModalOpen, setExportModalOpen] = useState(false)
    const [copiedExport, setCopiedExport] = useState(false)

    // Known tokens persistentes para facilitar la exportación automática
    const KNOWN_TOKENS: Record<string, string> = {
        "PASILLO62": "hw_zaEy9rg43tK6QZa0e9O_oDE_spala6yRm71hA74ayV8",
        "TLFHECTOR": "hw_tlfhector_secret_key_8832a74ayV8"
    }

    const generateCamerasExport = () => {
        return devices.map(d => ({
            device_id: d.device_id,
            name: d.device_name,
            token: KNOWN_TOKENS[d.device_id] || (newDeviceSecret && d.device_id === deviceId ? newDeviceSecret : `hw_${d.device_id.toLowerCase()}_token_aqui`),
            source: d.stream_url || "0",
            location: d.location || "Punto de Acceso",
            enabled: Boolean(d.stream_url && d.stream_url.trim() !== "" && d.is_active)
        }))
    }

    const handleDownloadJson = () => {
        const jsonStr = JSON.stringify(generateCamerasExport(), null, 4)
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(jsonStr)
        const downloadAnchor = document.createElement("a")
        downloadAnchor.setAttribute("href", dataStr)
        downloadAnchor.setAttribute("download", "cameras.json")
        document.body.appendChild(downloadAnchor)
        downloadAnchor.click()
        downloadAnchor.remove()
    }

    const token = localStorage.getItem("token") || ""
    const baseUrl = API_BASE_URL

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
                device_id: deviceId.trim().toUpperCase(),
                device_name: deviceName.trim(),
                device_type: deviceType,
                location: location.trim() || null,
                stream_url: streamUrl.trim() || null,
                lbp_threshold: parseFloat(lbpThreshold) || 3.670
            }, {
                headers: { Authorization: `Bearer ${token}` }
            })

            setNewDeviceSecret(res.data.client_secret)
            setDeviceId("")
            setDeviceName("")
            setDeviceType("camera")
            setLocation("")
            setStreamUrl("")
            setLbpThreshold("3.670")
            fetchDevices()
        } catch (err: any) {
            setError(err.response?.data?.detail || "Error al registrar el dispositivo físico.")
        } finally {
            setRegistering(false)
        }
    }

    const openEditModal = (device: IoTDevice) => {
        setEditingDevice(device)
        setEditThreshold(String(device.lbp_threshold || 3.670))
        setEditStreamUrl(device.stream_url || "")
        setEditLocation(device.location || "")
        setCalibResult(null)
        setCalibError("")
    }

    const handleAutoCalibrate = async () => {
        if (!editingDevice) return
        setAutoCalibrating(true)
        setCalibError("")
        setCalibResult(null)

        try {
            const res = await axios.post(
                `${baseUrl}/api/v1/devices/${editingDevice.device_id}/auto-calibrate?target_samples=25`,
                {},
                { headers: { Authorization: `Bearer ${token}` } }
            )
            setCalibResult(res.data.calibration)
            setEditThreshold(String(res.data.calibration.optimal_threshold))
            fetchDevices()
        } catch (err: any) {
            setCalibError(err.response?.data?.detail || "Error al auto-calibrar el dispositivo.")
        } finally {
            setAutoCalibrating(false)
        }
    }

    const handleSaveCalibration = async () => {
        if (!editingDevice) return
        setSavingEdit(true)
        try {
            await axios.patch(`${baseUrl}/api/v1/devices/${editingDevice.device_id}`, {
                lbp_threshold: parseFloat(editThreshold) || 3.670,
                stream_url: editStreamUrl.trim() || null,
                location: editLocation.trim() || null
            }, {
                headers: { Authorization: `Bearer ${token}` }
            })
            setEditingDevice(null)
            fetchDevices()
        } catch (err: any) {
            alert(err.response?.data?.detail || "Error al actualizar la calibración del dispositivo.")
        } finally {
            setSavingEdit(false)
        }
    }

    const handleDeleteDevice = async (id: string) => {
        if (!window.confirm(`¿Estás seguro de que deseas eliminar el dispositivo '${id}'? Se perderán sus reglas ACL.`)) {
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
                        <Cpu className="h-5 w-5 text-primary" /> Gestión de Hardware & Puntos de Acceso
                    </h3>
                    <p className="text-sm text-muted-foreground">
                        Administra cámaras RTSP, umbrales de calibración óptica individual y tokens de borde M2M.
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Button 
                        variant="outline" 
                        size="sm" 
                        onClick={() => setExportModalOpen(true)}
                        className="border-primary/40 text-primary hover:bg-primary/10 shadow-sm"
                        title="Exportar configuración cameras.json para el Edge Gateway"
                    >
                        <Download className="h-4 w-4 mr-1.5" /> Exportar cameras.json
                    </Button>
                    <Button variant="outline" size="sm" onClick={fetchDevices} disabled={loading}>
                        <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} /> Actualizar
                    </Button>
                </div>
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
                            <Plus className="w-5 h-5 text-primary" /> Registrar Punto de Acceso
                        </CardTitle>
                        <CardDescription>
                            Añade una cámara IP de vigilancia, webcam o torniquete.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <form onSubmit={handleRegisterDevice} className="space-y-3">
                            <div className="space-y-1.5">
                                <Label htmlFor="deviceId">ID del Dispositivo (Código)</Label>
                                <Input
                                    id="deviceId"
                                    placeholder="PASILLO_6_4 o ENTRADA_B"
                                    value={deviceId}
                                    onChange={e => setDeviceId(e.target.value)}
                                    required
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label htmlFor="deviceName">Nombre Descriptivo</Label>
                                <Input
                                    id="deviceName"
                                    placeholder="Cámara Pasillo 6-4"
                                    value={deviceName}
                                    onChange={e => setDeviceName(e.target.value)}
                                    required
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-2">
                                <div className="space-y-1.5">
                                    <Label htmlFor="deviceType">Tipo</Label>
                                    <select
                                        id="deviceType"
                                        className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-xs"
                                        value={deviceType}
                                        onChange={e => setDeviceType(e.target.value)}
                                    >
                                        <option value="camera">Cámara RTSP / IP</option>
                                        <option value="door">Cerradura / Puerta</option>
                                        <option value="turnstile">Molinete / Torniquete</option>
                                        <option value="gateway">Servidor Edge</option>
                                    </select>
                                </div>
                                <div className="space-y-1.5">
                                    <Label htmlFor="lbpThreshold">Umbral LBP</Label>
                                    <Input
                                        id="lbpThreshold"
                                        type="number"
                                        step="0.01"
                                        placeholder="3.670"
                                        value={lbpThreshold}
                                        onChange={e => setLbpThreshold(e.target.value)}
                                    />
                                </div>
                            </div>
                            <div className="space-y-1.5">
                                <Label htmlFor="streamUrl">URL de Stream (RTSP / HTTP)</Label>
                                <Input
                                    id="streamUrl"
                                    placeholder="rtsp://admin:pass@192.168.1.10:554/... o http://..."
                                    value={streamUrl}
                                    onChange={e => setStreamUrl(e.target.value)}
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label htmlFor="location">Ubicación Física</Label>
                                <Input
                                    id="location"
                                    placeholder="Edificio B, Pasillo 6"
                                    value={location}
                                    onChange={e => setLocation(e.target.value)}
                                />
                            </div>
                            <Button type="submit" className="w-full mt-2" disabled={registering}>
                                {registering ? "Registrando..." : "Registrar Dispositivo"}
                            </Button>
                        </form>

                        {/* Alerta con el Secret Token de Hardware */}
                        {newDeviceSecret && (
                            <div className="mt-4 p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs space-y-2 relative overflow-hidden">
                                <div className="absolute top-0 left-0 h-full w-1 bg-amber-500" />
                                <p className="font-semibold text-amber-700 dark:text-amber-400 flex items-center gap-1.5">
                                    <Key className="w-4 h-4" /> ¡GUARDA ESTE TOKEN DE HARDWARE!
                                </p>
                                <p className="text-muted-foreground text-[11px] leading-tight">
                                    Este es el `client_secret` de M2M. Cópialo para agregarlo al archivo `cameras.json` del Edge Gateway.
                                </p>
                                <div className="flex items-center gap-2 mt-1">
                                    <code className="p-1.5 rounded bg-muted w-full block font-mono text-[10px] break-all select-all font-semibold border text-foreground">
                                        {newDeviceSecret}
                                    </code>
                                    <Button size="icon" variant="outline" className="h-7 w-7 shrink-0" onClick={() => copyToClipboard(newDeviceSecret)}>
                                        {copiedSecret ? <Check className="w-3.5 h-3.5 text-green-600" /> : <Copy className="w-3.5 h-3.5" />}
                                    </Button>
                                </div>
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Tabla de Dispositivos & Calibraciones */}
                <Card className="md:col-span-2">
                    <CardHeader>
                        <CardTitle className="text-md flex items-center gap-2">
                            <Activity className="w-5 h-5 text-primary" /> Puntos de Acceso & Calibración
                        </CardTitle>
                        <CardDescription>
                            Configuración óptica individual, flujos RTSP y umbrales de textura por cámara.
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
                                            <th className="px-3 py-2.5 rounded-tl-md">Punto / ID</th>
                                            <th className="px-3 py-2.5">Stream / Tipo</th>
                                            <th className="px-3 py-2.5">Calibración LBP</th>
                                            <th className="px-3 py-2.5">Ubicación</th>
                                            <th className="px-3 py-2.5 rounded-tr-md text-right">Acciones</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {devices.map((device) => (
                                            <tr key={device.device_id} className="border-b last:border-0 hover:bg-muted/10 transition-colors">
                                                <td className="px-3 py-2.5">
                                                    <div className="font-bold text-foreground">{device.device_name}</div>
                                                    <div className="text-[10px] font-mono text-muted-foreground">{device.device_id}</div>
                                                </td>
                                                <td className="px-3 py-2.5">
                                                    <div className="capitalize font-medium text-foreground">{device.device_type}</div>
                                                    {device.stream_url ? (
                                                        <div className="text-[10px] font-mono text-primary flex items-center gap-1 max-w-[150px] truncate" title={device.stream_url}>
                                                            <Video className="w-3 h-3 shrink-0" /> {device.stream_url}
                                                        </div>
                                                    ) : (
                                                        <div className="text-[10px] text-muted-foreground italic">Sin RTSP</div>
                                                    )}
                                                </td>
                                                <td className="px-3 py-2.5">
                                                    <span className="px-2 py-0.5 rounded-md font-mono text-[11px] font-bold bg-primary/10 text-primary border border-primary/20">
                                                        θ = {device.lbp_threshold?.toFixed(3) || "3.670"}
                                                    </span>
                                                </td>
                                                <td className="px-3 py-2.5 text-muted-foreground">
                                                    {device.location ? (
                                                        <span className="flex items-center gap-1">
                                                            <MapPin className="h-3 w-3 text-primary shrink-0" />
                                                            {device.location}
                                                        </span>
                                                    ) : (
                                                        <span className="italic text-muted-foreground/60">—</span>
                                                    )}
                                                </td>
                                                <td className="px-3 py-2.5 text-right space-x-1">
                                                    <Button 
                                                        variant="ghost" 
                                                        size="icon" 
                                                        className="h-7 w-7 text-primary hover:bg-primary/10" 
                                                        title="Editar Calibración y Stream"
                                                        onClick={() => openEditModal(device)}
                                                    >
                                                        <Edit2 className="h-3.5 w-3.5" />
                                                    </Button>
                                                    <Button 
                                                        variant="ghost" 
                                                        size="icon" 
                                                        className="h-7 w-7 text-destructive hover:bg-destructive/10" 
                                                        title="Eliminar Dispositivo"
                                                        onClick={() => handleDeleteDevice(device.device_id)}
                                                    >
                                                        <Trash2 className="h-3.5 w-3.5" />
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

            {/* Modal de Calibración & Edición Rápida */}
            {editingDevice && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
                    <Card className="w-full max-w-md border-primary/30 shadow-2xl">
                        <CardHeader className="flex flex-row items-center justify-between pb-2">
                            <div>
                                <CardTitle className="text-md flex items-center gap-2">
                                    <Sliders className="w-4 h-4 text-primary" /> Calibrar {editingDevice.device_name}
                                </CardTitle>
                                <CardDescription className="text-xs">
                                    Ajuste fino de umbrales ópticos y flujo RTSP del dispositivo `{editingDevice.device_id}`.
                                </CardDescription>
                            </div>
                            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => setEditingDevice(null)}>
                                <X className="w-4 h-4" />
                            </Button>
                        </CardHeader>
                        <CardContent className="space-y-3 pt-2">
                            <div className="space-y-1">
                                <Label htmlFor="editLbp" className="text-xs">Umbral de Calibración LBP (Textura)</Label>
                                <div className="flex items-center gap-3">
                                    <Input
                                        id="editLbp"
                                        type="number"
                                        step="0.005"
                                        min="3.0"
                                        max="4.3"
                                        value={editThreshold}
                                        onChange={e => setEditThreshold(e.target.value)}
                                        className="font-mono text-sm"
                                    />
                                    <span className="text-[11px] text-muted-foreground shrink-0">
                                        Recomendado: 3.65 - 3.70
                                    </span>
                                </div>
                            </div>
                            <div className="space-y-1">
                                <Label htmlFor="editStream" className="text-xs">Flujo de Video RTSP / HTTP</Label>
                                <Input
                                    id="editStream"
                                    placeholder="rtsp://... o http://..."
                                    value={editStreamUrl}
                                    onChange={e => setEditStreamUrl(e.target.value)}
                                    className="font-mono text-xs"
                                />
                            </div>
                            <div className="space-y-1">
                                <Label htmlFor="editLoc" className="text-xs">Ubicación Física</Label>
                                <Input
                                    id="editLoc"
                                    placeholder="Patio B, Pasillo 6"
                                    value={editLocation}
                                    onChange={e => setEditLocation(e.target.value)}
                                />
                            </div>
                            {/* Asistente de Auto-Calibración Sensorial en Vivo */}
                            <div className="p-3 rounded-lg border border-primary/20 bg-primary/5 space-y-2.5 mt-2">
                                <div className="flex items-center justify-between gap-2">
                                    <div>
                                        <h4 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                                            <Target className="w-3.5 h-3.5 text-primary" /> Auto-Calibración Óptica (Captura Facial)
                                        </h4>
                                        <p className="text-[11px] text-muted-foreground">
                                            Analiza 25 fotogramas en vivo desde la cámara para calcular empíricamente el umbral LBP óptimo.
                                        </p>
                                    </div>
                                    <Button 
                                        type="button" 
                                        size="sm" 
                                        onClick={handleAutoCalibrate} 
                                        disabled={autoCalibrating || !editStreamUrl}
                                        className="bg-primary hover:bg-primary/90 text-primary-foreground text-xs h-8 px-3 gap-1.5 shrink-0 shadow-sm"
                                    >
                                        {autoCalibrating ? (
                                            <>
                                                <RefreshCw className="w-3 h-3 animate-spin" /> Calibrando...
                                            </>
                                        ) : (
                                            <>
                                                <Play className="w-3 h-3 fill-current" /> Calibrar en Vivo
                                            </>
                                        )}
                                    </Button>
                                </div>

                                {autoCalibrating && (
                                    <div className="p-2.5 rounded-md bg-background/90 border border-primary/30 text-[11px] text-primary flex items-center gap-2 animate-pulse font-medium shadow-sm">
                                        <RefreshCw className="w-4 h-4 animate-spin shrink-0" /> Conectando al stream de video y muestreando piel... Por favor, mira fijamente a la cámara.
                                    </div>
                                )}

                                {calibError && (
                                    <div className="p-2.5 rounded-md bg-destructive/15 text-destructive text-[11px] font-medium flex items-center gap-2">
                                        <AlertCircle className="w-4 h-4 shrink-0" /> {calibError}
                                    </div>
                                )}

                                {calibResult && (
                                    <div className="p-3 rounded-md bg-emerald-500/10 border border-emerald-500/30 text-xs space-y-2 text-foreground">
                                        <div className="flex items-center justify-between font-bold text-emerald-700 dark:text-emerald-400">
                                            <span className="flex items-center gap-1.5">
                                                <Sparkles className="w-3.5 h-3.5" /> ¡Calibración Óptica Exitosa!
                                            </span>
                                            <span className="font-mono bg-emerald-500/20 border border-emerald-500/30 px-2 py-0.5 rounded text-[11px]">
                                                θ Óptimo = {calibResult.optimal_threshold}
                                            </span>
                                        </div>
                                        <div className="grid grid-cols-3 gap-2 text-[10px] font-mono text-muted-foreground pt-1.5 border-t border-emerald-500/20">
                                            <div>Resolución: <b className="text-foreground">{calibResult.resolution}</b></div>
                                            <div>Entropía: <b className="text-foreground">{calibResult.mean_entropy} ± {calibResult.std_entropy}</b></div>
                                            <div>Varianza: <b className="text-foreground">{calibResult.variance_mean}</b></div>
                                        </div>
                                        <p className="text-[10px] text-emerald-600 dark:text-emerald-400">
                                            El nuevo umbral fue aplicado al formulario y guardado para este dispositivo.
                                        </p>
                                    </div>
                                )}
                            </div>

                            <div className="flex justify-end gap-2 pt-2 border-t">
                                <Button variant="outline" size="sm" onClick={() => setEditingDevice(null)}>
                                    Cancelar
                                </Button>
                                <Button size="sm" onClick={handleSaveCalibration} disabled={savingEdit}>
                                    {savingEdit ? "Guardando..." : "Guardar Calibración"}
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            )}

            {/* Modal de Exportación cameras.json para Edge Gateway */}
            {exportModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
                    <Card className="w-full max-w-xl border-primary/30 shadow-2xl">
                        <CardHeader className="flex flex-row items-center justify-between pb-2">
                            <div>
                                <CardTitle className="text-md flex items-center gap-2">
                                    <Download className="w-4 h-4 text-primary" /> Configuración Edge Gateway (cameras.json)
                                </CardTitle>
                                <CardDescription className="text-xs">
                                    Generado automáticamente a partir de los {devices.length} dispositivos registrados en FaceSentinel.
                                </CardDescription>
                            </div>
                            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => setExportModalOpen(false)}>
                                <X className="w-4 h-4" />
                            </Button>
                        </CardHeader>
                        <CardContent className="space-y-3 pt-2">
                            <p className="text-xs text-muted-foreground leading-relaxed">
                                Este archivo contiene las fuentes de video (RTSP/HTTP), nombres y tokens M2M para que <code className="text-primary font-mono bg-primary/10 px-1 py-0.5 rounded">edge_gateway_multi.py</code> las procese concurrentemente.
                            </p>
                            <pre className="p-3 rounded-md bg-muted/90 font-mono text-[11px] max-h-60 overflow-y-auto border text-foreground select-all">
                                {JSON.stringify(generateCamerasExport(), null, 4)}
                            </pre>
                            <div className="flex justify-between items-center pt-2 border-t">
                                <Button 
                                    variant="outline" 
                                    size="sm" 
                                    onClick={() => {
                                        navigator.clipboard.writeText(JSON.stringify(generateCamerasExport(), null, 4))
                                        setCopiedExport(true)
                                        setTimeout(() => setCopiedExport(false), 2000)
                                    }}
                                    className="text-xs"
                                >
                                    {copiedExport ? <Check className="w-3.5 h-3.5 mr-1.5 text-green-600" /> : <Copy className="w-3.5 h-3.5 mr-1.5" />}
                                    {copiedExport ? "¡Copiado!" : "Copiar JSON"}
                                </Button>
                                <div className="space-x-2">
                                    <Button variant="outline" size="sm" onClick={() => setExportModalOpen(false)}>
                                        Cerrar
                                    </Button>
                                    <Button size="sm" onClick={handleDownloadJson} className="bg-primary text-primary-foreground hover:bg-primary/90">
                                        <Download className="w-3.5 h-3.5 mr-1.5" /> Descargar cameras.json
                                    </Button>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            )}
        </div>
    )
}
