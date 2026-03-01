// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title AccessRegistry
 * @author FaceSentinel
 * @notice Contrato inteligente para el registro inmutable de eventos de
 *         autenticación biométrica facial. Diseñado para Ganache (desarrollo)
 *         con estructura lista para redes Ethereum/Polygon reales.
 */
contract AccessRegistry {

    // =========================================================================
    //                              ESTRUCTURAS
    // =========================================================================

    /// @notice Estructura que representa un evento de autenticación
    struct AuthRecord {
        string userId;           // Identificador del usuario (ej. "V-12345")
        bytes32 biometricHash;   // Hash SHA-256 del embedding facial (no se guarda el vector real)
        uint256 timestamp;       // Marca de tiempo UNIX del momento de autenticación
        bool accessGranted;      // true = acceso concedido, false = denegado
        string deviceId;         // Identificador del punto de acceso / dispositivo
        uint256 matchScore;      // Distancia coseno x10000 (4 decimales de precisión)
    }

    // =========================================================================
    //                           VARIABLES DE ESTADO
    // =========================================================================

    /// @notice Dirección del administrador del contrato
    address public owner;

    /// @notice Contador global de registros (también sirve como ID incremental)
    uint256 public totalRecords;

    /// @notice Mapeo de dispositivos autorizados para registrar eventos
    mapping(address => bool) public authorizedDevices;

    /// @notice Todos los registros de autenticación, indexados por ID
    mapping(uint256 => AuthRecord) public authRecords;

    /// @notice Índice: userId => lista de IDs de registros para ese usuario
    mapping(string => uint256[]) private userRecordIds;

    // =========================================================================
    //                               EVENTOS
    // =========================================================================

    /// @notice Se emite cada vez que se registra un intento de autenticación
    event AuthenticationLogged(
        uint256 indexed recordId,
        string userId,
        bool accessGranted,
        uint256 timestamp,
        address indexed device
    );

    /// @notice Se emite cuando se autoriza o revoca un dispositivo
    event DeviceAuthorizationChanged(
        address indexed device,
        bool authorized
    );

    // =========================================================================
    //                             MODIFICADORES
    // =========================================================================

    /// @notice Solo el dueño del contrato puede ejecutar esta función
    modifier onlyOwner() {
        require(msg.sender == owner, "Solo el administrador puede ejecutar esta accion");
        _;
    }

    /// @notice Solo dispositivos autorizados o el owner pueden registrar eventos
    modifier onlyAuthorized() {
        require(
            authorizedDevices[msg.sender] || msg.sender == owner,
            "Dispositivo no autorizado para registrar eventos"
        );
        _;
    }

    // =========================================================================
    //                            CONSTRUCTOR
    // =========================================================================

    /// @notice Inicializa el contrato, el deployer se convierte en owner
    constructor() {
        owner = msg.sender;
        authorizedDevices[msg.sender] = true;
        totalRecords = 0;
    }

    // =========================================================================
    //                       FUNCIONES DE ADMINISTRACIÓN
    // =========================================================================

    /**
     * @notice Autoriza un nuevo dispositivo para registrar eventos
     * @param _device Dirección Ethereum del dispositivo a autorizar
     */
    function authorizeDevice(address _device) external onlyOwner {
        require(_device != address(0), "Direccion invalida");
        authorizedDevices[_device] = true;
        emit DeviceAuthorizationChanged(_device, true);
    }

    /**
     * @notice Revoca la autorización de un dispositivo
     * @param _device Dirección Ethereum del dispositivo a revocar
     */
    function revokeDevice(address _device) external onlyOwner {
        authorizedDevices[_device] = false;
        emit DeviceAuthorizationChanged(_device, false);
    }

    // =========================================================================
    //                     FUNCIONES PRINCIPALES (CORE)
    // =========================================================================

    /**
     * @notice Registra un evento de autenticación biométrica en la blockchain
     * @param _userId Identificador del usuario
     * @param _biometricHash Hash SHA-256 del vector biométrico
     * @param _accessGranted Si el acceso fue concedido o denegado
     * @param _deviceId Identificador del punto de acceso
     * @param _matchScore Distancia coseno x10000
     * @return recordId El ID asignado al registro
     */
    function logAuthentication(
        string calldata _userId,
        bytes32 _biometricHash,
        bool _accessGranted,
        string calldata _deviceId,
        uint256 _matchScore
    ) external onlyAuthorized returns (uint256 recordId) {
        recordId = totalRecords;

        authRecords[recordId] = AuthRecord({
            userId: _userId,
            biometricHash: _biometricHash,
            timestamp: block.timestamp,
            accessGranted: _accessGranted,
            deviceId: _deviceId,
            matchScore: _matchScore
        });

        userRecordIds[_userId].push(recordId);
        totalRecords++;

        emit AuthenticationLogged(
            recordId,
            _userId,
            _accessGranted,
            block.timestamp,
            msg.sender
        );

        return recordId;
    }

    // =========================================================================
    //                       FUNCIONES DE CONSULTA (VIEW)
    // =========================================================================

    /**
     * @notice Obtiene un registro de autenticación por su ID
     * @param _recordId ID del registro a consultar
     * @return El struct AuthRecord completo
     */
    function getRecord(uint256 _recordId) external view returns (AuthRecord memory) {
        require(_recordId < totalRecords, "Registro no existe");
        return authRecords[_recordId];
    }

    /**
     * @notice Obtiene todos los IDs de registros para un usuario
     * @param _userId Identificador del usuario
     * @return Array con los IDs de todos los registros de ese usuario
     */
    function getRecordIdsByUser(string calldata _userId) external view returns (uint256[] memory) {
        return userRecordIds[_userId];
    }

    /**
     * @notice Obtiene los últimos N registros de un usuario
     * @param _userId Identificador del usuario
     * @param _count Cantidad de registros a retornar (máximo)
     * @return Array de AuthRecord con los registros más recientes
     */
    function getRecentRecordsByUser(
        string calldata _userId,
        uint256 _count
    ) external view returns (AuthRecord[] memory) {
        uint256[] storage ids = userRecordIds[_userId];
        uint256 total = ids.length;
        uint256 resultCount = _count < total ? _count : total;

        AuthRecord[] memory results = new AuthRecord[](resultCount);

        for (uint256 i = 0; i < resultCount; i++) {
            // Empezamos desde el final para obtener los más recientes
            results[i] = authRecords[ids[total - 1 - i]];
        }

        return results;
    }

    /**
     * @notice Verifica si un dispositivo está autorizado
     * @param _device Dirección del dispositivo
     * @return true si está autorizado
     */
    function isDeviceAuthorized(address _device) external view returns (bool) {
        return authorizedDevices[_device] || _device == owner;
    }

    /**
     * @notice Obtiene el número total de autenticaciones de un usuario
     * @param _userId Identificador del usuario
     * @return Cantidad de registros
     */
    function getUserRecordCount(string calldata _userId) external view returns (uint256) {
        return userRecordIds[_userId].length;
    }
}
