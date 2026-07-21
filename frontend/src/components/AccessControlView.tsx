import React, { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Lock, Unlock, User, Users, Plus, Trash2, Shield, RefreshCw, AlertCircle, CheckCircle2 } from "lucide-react"
import axios from "axios"

interface IoTDevice {
    device_id: string
    device_name: string
    device_type: string
    location: string | null
}

interface UserRecord {
    user_id: string
    name: string
    role: string
}

interface ACLRule {
    id: number
    device_id: string
    user_id: string | null
    allowed_role: string | null
    created_at: string
}

export default function AccessControlView() {
    const [devices, setDevices] = useState<IoTDevice[]>([])
    const [users, setUsers] = useState<UserRecord[]>([])
    const [selectedDeviceId, setSelectedDeviceId] = useState("")
    const [aclRules, setAclRules] = useState<ACLRule[]>([])
    
    // UI Loading & Status
    const [loadingDevices, setLoadingDevices] = useState(true)
    const [loadingUsers, setLoadingUsers] = useState(true)
    const [loadingRules, setLoadingRules] = useState(false)
    const [submitting, setSubmitting] = useState(false)
    const [error, setError] = useState("")
    const [success, setSuccess] = useState("")

    // Form inputs
    const [grantType, setGrantType] = useState<"user" | "role">("user")
    const [selectedUserId, setSelectedUserId] = useState("")
    const [selectedRole, setSelectedRole] = useState("Student")

    const token = localStorage.getItem("token") || ""
    const baseUrl = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"

    const fetchDevices = async () => {
        setLoadingDevices(true)
        try {
            const res = await axios.get(`${baseUrl}/api/v1/devices`, {
                headers: { Authorization: `Bearer ${token}` }
            })
            setDevices(res.data)
            if (res.data.length > 0 && !selectedDeviceId) {
                setSelectedDeviceId(res.data[0].device_id)
            }
        } catch (err) {
            console.error("Error al obtener dispositivos", err)
            setError("No se pudieron cargar los dispositivos.")
        } finally {
            setLoadingDevices(false)
        }
    }

    const fetchUsers = async () => {
        setLoadingUsers(true)
        try {
            const res = await axios.get(`${baseUrl}/api/v1/users`, {
                headers: { Authorization: `Bearer ${token}` }
            })
            setUsers(res.data)
            if (res.data.length > 0) {
                setSelectedUserId(res.data[0].user_id)
            }
        } catch (err) {
            console.error("Error al obtener usuarios", err)
        } finally {
            setLoadingUsers(false)
        }
    }

    const fetchAclRules = async (deviceId: string) => {
        if (!deviceId) return
        setLoadingRules(true)
        try {
            const res = await axios.get(`${baseUrl}/api/v1/devices/${deviceId}/acl`, {
                headers: { Authorization: `Bearer ${token}` }
            })
            setAclRules(res.data)
        } catch (err) {
            console.error("Error al obtener reglas ACL", err)
            setAclRules([])
        } finally {
            setLoadingRules(false)
        }
    }

    const handleAddAclRule = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!selectedDeviceId) {
            alert("Selecciona un dispositivo primero.")
            return
        }

        setSubmitting(true)
        setError("")
        setSuccess("")

        const payload = {
            user_id: grantType === "user" ? selectedUserId : null,
            allowed_role: grantType === "role" ? selectedRole : null
        }

        try {
            await axios.post(`${baseUrl}/api/v1/devices/${selectedDeviceId}/acl`, payload, {
                headers: { Authorization: `Bearer ${token}` }
            })
            setSuccess("Permiso de acceso concedido con éxito.")
            fetchAclRules(selectedDeviceId)
            
            // Ocultar mensaje de éxito en 3s
            setTimeout(() => setSuccess(""), 3000)
        } catch (err: any) {
            setError(err.response?.data?.detail || "Error al registrar la regla de acceso.")
        } finally {
            setSubmitting(false)
        }
    }

    const handleDeleteAclRule = async (ruleId: number) => {
        if (!window.confirm("¿Deseas revocar esta regla de acceso?")) {
            return
        }

        try {
            await axios.delete(`${baseUrl}/api/v1/devices/acl/${ruleId}`, {
                headers: { Authorization: `Bearer ${token}` }
            })
            fetchAclRules(selectedDeviceId)
        } catch (err: any) {
            alert(err.response?.data?.detail || "Error al revocar la regla de acceso.")
        }
    }

    useEffect(() => {
        if (token) {
            fetchDevices()
            fetchUsers()
        }
    }, [token])

    useEffect(() => {
        if (selectedDeviceId) {
            fetchAclRules(selectedDeviceId)
        } else {
            setAclRules([])
        }
    }, [selectedDeviceId])

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-xl font-bold tracking-tight flex items-center gap-2">
                    <Lock className="h-5 w-5 text-primary" /> Control de Acceso Espacial (ACL / RBAC)
                </h3>
                <p className="text-sm text-muted-foreground">
                    Define qué usuarios o roles de FaceSentinel tienen permitido el acceso físico a cada zona.
                </p>
            </div>

            {error && (
                <div className="p-3 rounded-md bg-destructive/15 text-destructive text-sm font-medium flex items-center gap-2">
                    <AlertCircle className="h-4 w-4" />
                    {error}
                </div>
            )}

            {success && (
                <div className="p-3 rounded-md bg-green-500/15 text-green-600 text-sm font-medium flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4" />
                    {success}
                </div>
            )}

            <div className="grid gap-6 md:grid-cols-4">
                {/* Selector de Dispositivo & Formulario de ACL */}
                <Card className="md:col-span-2 border-primary/20">
                    <CardHeader>
                        <CardTitle className="text-md flex items-center gap-2">
                            <Shield className="w-5 h-5 text-primary" /> Otorgar Permiso de Acceso
                        </CardTitle>
                        <CardDescription>
                            Asocia una regla de entrada por Cédula de Identidad o Rol de usuario.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <form onSubmit={handleAddAclRule} className="space-y-4">
                            {/* Dispositivo Dropdown */}
                            <div className="space-y-2">
                                <Label htmlFor="deviceSelector">Seleccionar Punto de Acceso (Puerta/Cámara)</Label>
                                {loadingDevices ? (
                                    <div className="h-9 w-full rounded bg-muted animate-pulse border" />
                                ) : (
                                    <select
                                        id="deviceSelector"
                                        className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                        value={selectedDeviceId}
                                        onChange={e => setSelectedDeviceId(e.target.value)}
                                        required
                                    >
                                        <option value="" disabled>Selecciona una puerta...</option>
                                        {devices.map(d => (
                                            <option key={d.device_id} value={d.device_id}>
                                                {d.device_name} ({d.location || "Sin ubicación"})
                                            </option>
                                        ))}
                                    </select>
                                )}
                            </div>

                            {/* Tipo de asignación (ACL vs RBAC) */}
                            <div className="space-y-2">
                                <Label>Tipo de Permiso</Label>
                                <div className="grid grid-cols-2 gap-2 p-1 bg-muted rounded-lg border text-xs">
                                    <button
                                        type="button"
                                        className={`py-1.5 rounded-md font-medium transition-all flex items-center justify-center gap-1.5 ${grantType === "user" ? "bg-background shadow text-foreground" : "text-muted-foreground hover:text-foreground"}`}
                                        onClick={() => setGrantType("user")}
                                    >
                                        <User className="h-3.5 w-3.5" /> Por Usuario Único
                                    </button>
                                    <button
                                        type="button"
                                        className={`py-1.5 rounded-md font-medium transition-all flex items-center justify-center gap-1.5 ${grantType === "role" ? "bg-background shadow text-foreground" : "text-muted-foreground hover:text-foreground"}`}
                                        onClick={() => setGrantType("role")}
                                    >
                                        <Users className="h-3.5 w-3.5" /> Por Rol (RBAC)
                                    </button>
                                </div>
                            </div>

                            {/* Inputs dinámicos */}
                            {grantType === "user" ? (
                                <div className="space-y-2">
                                    <Label htmlFor="userSelector">Seleccionar Usuario Enrolado</Label>
                                    {loadingUsers ? (
                                        <div className="h-9 w-full rounded bg-muted animate-pulse border" />
                                    ) : (
                                        <select
                                            id="userSelector"
                                            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                            value={selectedUserId}
                                            onChange={e => setSelectedUserId(e.target.value)}
                                            required
                                        >
                                            {users.length > 0 ? (
                                                users.map(u => (
                                                    <option key={u.user_id} value={u.user_id}>
                                                        {u.name} (ID: {u.user_id} — {u.role})
                                                    </option>
                                                ))
                                            ) : (
                                                <option value="" disabled>No hay usuarios registrados</option>
                                            )}
                                        </select>
                                    )}
                                </div>
                            ) : (
                                <div className="space-y-2">
                                    <Label htmlFor="roleSelector">Seleccionar Rol Autorizado</Label>
                                    <select
                                        id="roleSelector"
                                        className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                        value={selectedRole}
                                        onChange={e => setSelectedRole(e.target.value)}
                                        required
                                    >
                                        <option value="Student">Student (Estudiantes)</option>
                                        <option value="Professor">Professor (Profesores/Docentes)</option>
                                        <option value="Developer">Developer (Desarrolladores)</option>
                                        <option value="Admin">Admin (Administradores)</option>
                                    </select>
                                </div>
                            )}

                            <Button type="submit" className="w-full flex items-center justify-center gap-1.5" disabled={submitting || !selectedDeviceId}>
                                <Plus className="h-4 w-4" /> Conceder Acceso
                            </Button>
                        </form>
                    </CardContent>
                </Card>

                {/* Tabla de Reglas ACL vigentes */}
                <Card className="md:col-span-2">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0">
                        <div>
                            <CardTitle className="text-md flex items-center gap-2">
                                <Unlock className="w-5 h-5 text-primary" /> Reglas de Acceso Habilitadas
                            </CardTitle>
                            <CardDescription>
                                Personas o roles autorizados a cruzar este punto.
                            </CardDescription>
                        </div>
                        {selectedDeviceId && (
                            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => fetchAclRules(selectedDeviceId)} disabled={loadingRules}>
                                <RefreshCw className={`h-4 w-4 ${loadingRules ? "animate-spin" : ""}`} />
                            </Button>
                        )}
                    </CardHeader>
                    <CardContent>
                        {!selectedDeviceId ? (
                            <div className="text-center py-10 text-muted-foreground border border-dashed rounded-md bg-muted/10">
                                Por favor, registre y seleccione un dispositivo a la izquierda.
                            </div>
                        ) : loadingRules ? (
                            <div className="text-center py-10 text-muted-foreground animate-pulse">Cargando reglas ACL...</div>
                        ) : aclRules.length > 0 ? (
                            <div className="overflow-x-auto">
                                <table className="w-full text-xs text-left">
                                    <thead className="text-muted-foreground uppercase bg-muted/50 font-semibold border-b">
                                        <tr>
                                            <th className="px-3 py-2.5 rounded-tl-md">Tipo Regla</th>
                                            <th className="px-3 py-2.5">Autorizado</th>
                                            <th className="px-3 py-2.5">Fecha Asignación</th>
                                            <th className="px-3 py-2.5 rounded-tr-md text-right">Revocar</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {aclRules.map((rule) => (
                                            <tr key={rule.id} className="border-b last:border-0 hover:bg-muted/10 transition-colors">
                                                <td className="px-3 py-2.5 font-semibold">
                                                    {rule.user_id ? (
                                                        <span className="flex items-center gap-1.5 text-blue-600">
                                                            <User className="h-3.5 w-3.5" /> Usuario Único
                                                        </span>
                                                    ) : (
                                                        <span className="flex items-center gap-1.5 text-indigo-600">
                                                            <Users className="h-3.5 w-3.5" /> Rol General
                                                        </span>
                                                    )}
                                                </td>
                                                <td className="px-3 py-2.5 font-mono">
                                                    {rule.user_id ? (
                                                        <span className="font-semibold text-foreground">{rule.user_id}</span>
                                                    ) : (
                                                        <span className="font-semibold text-primary px-2 py-0.5 rounded bg-primary/10 border border-primary/20">{rule.allowed_role}</span>
                                                    )}
                                                </td>
                                                <td className="px-3 py-2.5 text-muted-foreground">
                                                    {new Date(rule.created_at).toLocaleDateString()}
                                                </td>
                                                <td className="px-3 py-2.5 text-right">
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-7 w-7 text-destructive hover:bg-destructive/10"
                                                        onClick={() => handleDeleteAclRule(rule.id)}
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
                            <div className="text-center py-10 text-muted-foreground border border-dashed rounded-md bg-muted/10">
                                No hay ninguna regla de acceso configurada para este dispositivo. Está completamente **cerrado** por defecto (Zero-Trust).
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}
