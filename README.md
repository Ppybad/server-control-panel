# Panel de Control Tomcat

Sistema de gestión centralizada para servidores Tomcat y contenedores Docker, diseñado para facilitar la administración remota (Windows/Linux) y local.

## 🚀 Instalación para Desarrolladores

Sigue estos pasos para configurar el entorno de desarrollo en tu máquina local.

### Prerrequisitos
*   **Python 3.10+** instalado.
*   **Git** instalado.
*   Acceso a una terminal (PowerShell recomendado en Windows).

### Pasos de Configuración

1.  **Clonar el Repositorio**
    ```bash
    git clone <url-del-repositorio>
    cd PanelControlTomcat // o la carpeta donde se haya bajado el proyecto server-control-panel
    ```

2.  **Crear Entorno Virtual**
    Es recomendable usar un entorno virtual para aislar las dependencias.
    ```bash
    python -m venv venv
    ```

3.  **Activar Entorno Virtual**
    *   **Windows:**
        ```powershell
        .\venv\Scripts\Activate
        ```
    *   **Linux/Mac:**
        ```bash
        source venv/bin/activate
        ```

4.  **Instalar Dependencias**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Configurar Base de Datos**
    Aplica las migraciones iniciales para crear la base de datos SQLite (por defecto).
    ```bash
    python manage.py migrate
    ```

6.  **Crear Superusuario (Opcional)**
    Para acceder al admin de Django.
    ```bash
    python manage.py createsuperuser
    ```

7.  **Ejecutar el Servidor**
    ```bash
    python manage.py runserver
    ```
    Accede a `http://127.0.0.1:8000` en tu navegador.

### ⚠️ Nota Importante sobre Servicios Locales
Si deseas utilizar la funcionalidad de **"Local (Este Equipo)"** para gestionar servicios de Windows o detener procesos en tu propia máquina de desarrollo:

*   Debes ejecutar el servidor de desarrollo **como Administrador**.
*   Abre tu terminal (PowerShell/CMD) con **"Ejecutar como administrador"** antes de correr `python manage.py runserver`.

---

## 📚 Documentación Técnica de Comandos

El panel utiliza diferentes protocolos y comandos según el tipo de conexión y servidor.

### 1. Windows Remoto (WinRM)
Utiliza la librería `pywinrm` para ejecutar comandos de PowerShell.
*   **Puerto por defecto:** 5985 (HTTP).
*   **Verificar Estado:** `Get-Service -Name 'NombreServicio' | Select-Object Status`
*   **Iniciar:** `Start-Service -Name 'NombreServicio'`
*   **Detener:** `Stop-Service -Name 'NombreServicio' -Force`
*   **Reiniciar:** `Restart-Service -Name 'NombreServicio' -Force`

### 2. Linux / SSH
Utiliza la librería `paramiko` para conectar vía SSH.
*   **Puerto por defecto:** 22.
*   **Verificar Estado:** `systemctl is-active 'nombre_servicio'`
*   **Iniciar:** `sudo systemctl start 'nombre_servicio'`
*   **Detener:** `sudo systemctl stop 'nombre_servicio'`
*   **Reiniciar:** `sudo systemctl restart 'nombre_servicio'`

### 3. Docker (Vía SSH)
Se conecta al servidor anfitrión vía SSH y ejecuta comandos `docker`. Requiere que el usuario tenga permisos `sudo`.
*   **Listar Contenedores:** `echo 'password' | sudo -S docker ps --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}'`
*   **Iniciar:** `echo 'password' | sudo -S docker start 'contenedor'`
*   **Detener:** `echo 'password' | sudo -S docker stop 'contenedor'`
*   **Reiniciar:** `echo 'password' | sudo -S docker restart 'contenedor'`
*   **Nota:** Se utiliza `sudo -S` para pasar la contraseña vía entrada estándar (stdin) y evitar errores de terminal interactiva.

### 4. Local (Este Equipo)
Ejecuta comandos directamente en el sistema operativo donde corre el panel.

#### Windows Local
*   **Descubrir Servicios:** `Get-Service | Where-Object {$_.Name -like '*Tomcat*'} ...`
*   **Descubrir Procesos (IDEs):** `Get-CimInstance Win32_Process -Filter "Name = 'java.exe'" ...` (Busca procesos Java con 'catalina' en la línea de comandos).
*   **Controlar Servicios:** `Start-Service`, `Stop-Service`, `Restart-Service`.
*   **Controlar Procesos:** `Stop-Process -Id <PID> -Force` (Solo detener).

#### Linux Local
*   **Controlar Servicios:** `sudo systemctl [start|stop|restart] [servicio]`
