import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Activity, ShieldCheck, Lock, LogOut, User, Trash2, Clock, CheckCircle2, XCircle } from "lucide-react"
import axios from "axios"

interface AuthEvent {
    id: number
    user_id: string
    access_granted: boolean
    match_score: number
    device_id: string
    tx_hash: string
    timestamp: string
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

    useEffect(() => {
        if (!userId) {
            navigate("/")
            return
        }

        // Verificamos conexión con el servidor
        axios.get("http://127.0.0.1:8000/")
            .then(r => setDbStatus(r.data))
            .catch(() => setDbStatus({ status: "offline", blockchain: "disconnected" }))

        // Cargar historial de acceso
        axios.get(`http://127.0.0.1:8000/api/v1/auth-history/${userId}`)
            .then(r => {
                if (r.data.success) setAuthHistory(r.data.history)
            })
            .catch(err => console.error("Error cargando historial", err))
            .finally(() => setHistoryLoading(false))
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
            await axios.delete(`http://127.0.0.1:8000/api/v1/users/${userId}`)
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
                        <span className="text-lg font-bold">BioAuth-Web3</span>
                    </div>
                    <Button variant="ghost" size="sm" onClick={handleLogout}>
                        <LogOut className="h-4 w-4 mr-2" /> Salir
                    </Button>
                </div>
            </header>

            <main className="flex-1 container mx-auto p-4 md:p-8 space-y-6">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">Panel Principal</h2>
                    <p className="text-muted-foreground">
                        Has accedido a un área segura usando autenticación facial y registros inmutables.
                    </p>
                </div>

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
                        <CardFooter className="pt-0">
                            <Button
                                variant="destructive"
                                size="sm"
                                className="w-full mt-4 bg-red-500/10 text-red-600 hover:bg-red-500/20 shadow-none border border-red-200"
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
                                            <th className="px-4 py-3">Fecha y Hora</th>
                                            <th className="px-4 py-3">Score (Distancia)</th>
                                            <th className="px-4 py-3 rounded-tr-md">Transacción (TxHash)</th>
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
                                                    {new Date(log.timestamp).toLocaleString()}
                                                </td>
                                                <td className="px-4 py-3 font-mono">
                                                    {log.match_score.toFixed(4)}
                                                </td>
                                                <td className="px-4 py-3">
                                                    {log.tx_hash !== "N/A" ? (
                                                        <a
                                                            href={`#`}
                                                            className="text-primary hover:underline font-mono text-xs flex items-center"
                                                            title="Ver en explorador de bloques"
                                                        >
                                                            {log.tx_hash.substring(0, 10)}...{log.tx_hash.substring(log.tx_hash.length - 8)}
                                                        </a>
                                                    ) : (
                                                        <span className="text-muted-foreground">Local / Error Web3</span>
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
            </main>
        </div>
    )
}
