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

### 5. SNMP (Diagnóstico y Configuración)
Soporte de lectura vía **SNMPv2c** para CPU/RAM/Uptime.

**Diagnóstico desde el panel (CLI local)**
*   Ejecuta una prueba rápida:
    ```bash
    python diag_snmp.py <IP_SERVIDOR> <COMUNIDAD>
    # Ejemplo:
    python diag_snmp.py 10.63.17.147 public
    ```
    - Si ves “No SNMP response received before timeout”, verifica firewall/servicio.

**Windows (Servidor Remoto)**
*   Instalar cliente SNMP (opcional, según edición):
    ```powershell
    Add-WindowsCapability -Online -Name 'SNMP.Client~~~~0.0.1.0'
    ```
*   Abrir firewall (UDP 161):
    ```powershell
    New-NetFirewallRule -DisplayName "SNMP (UDP 161)" -Direction Inbound -Protocol UDP -LocalPort 161 -Action Allow
    ```
*   Configurar comunidad y hosts permitidos:
    - `services.msc` → Servicio SNMP → Propiedades → Seguridad
    - Agregar comunidad (p. ej. `public`) como **solo lectura**
    - Permitir desde tu IP o “aceptar paquetes SNMP de cualquier host”

**Linux (Servidor Remoto)**
*   Debian/Ubuntu:
    ```bash
    sudo apt update
    sudo apt install snmpd
    # Editar /etc/snmp/snmpd.conf y configurar, por ejemplo:
    # rocommunity public
    sudo systemctl restart snmpd
    sudo ufw allow 161/udp
    ```

**Arquitectura en el Panel**
- El panel invoca un worker aislado para SNMP: [snmp_worker.py](servidores/snmp_worker.py). Esto evita conflictos de `asyncio` en Windows.
- La vista usa un wrapper síncrono [services_snmp.py](servidores/services_snmp.py) que lanza el worker vía `subprocess` con timeout controlado.
- Endpoint de API/UI: `monitor_snmp` ([urls.py](servidores/urls.py), [views.py](servidores/views.py)).

**Ejecución Manual del Worker**
```bash
python servidores/snmp_worker.py <IP> <COMUNIDAD> [PUERTO]
# Ejemplo:
python servidores/snmp_worker.py 10.63.17.147 public 161
```

**Tiempos de Espera y Fallback**
- Timeout efectivo ~4 segundos (2s x 1 retry).  
- Si no hay respuesta, la UI entra en **Modo Simulación**, muestra un aviso desplegable con pasos de configuración y grafica datos de ejemplo.

**Notas Windows**
- El proyecto aplica automáticamente `WindowsSelectorEventLoopPolicy` en [manage.py](manage.py) para compatibilidad UDP/asyncio.
- No se requiere configuración adicional para ejecutar el servidor en Windows.

**OIDs consultados por el panel**
*   Descripción del sistema: `1.3.6.1.2.1.1.1.0` (sysDescr)
*   Uptime: `1.3.6.1.2.1.1.3.0` (sysUpTime)
*   CPU por núcleo: Walk `1.3.6.1.2.1.25.3.3.1.2` (hrProcessorLoad)
*   Memoria total: `1.3.6.1.2.1.25.2.2.0` (hrMemorySize)
*   Memoria disponible (UCD): `1.3.6.1.4.1.2021.4.6.0` (memAvailReal)

> Si SNMP falla, la UI muestra modo **Simulación** y un panel de ayuda con estos pasos.

---

## 📊 Monitoreo SNMP (Opcional)

Permite visualizar métricas básicas (CPU, RAM y Uptime) vía SNMPv2c.

### Requisitos en el Servidor Remoto (Windows)
1. Habilitar el servicio SNMP desde Características de Windows.
2. Abrir el puerto `161/UDP` en el Firewall de Windows (regla de entrada).
3. En `services.msc` → Servicio SNMP → Propiedades → Seguridad:
   - Agregar la comunidad configurada en el panel (por defecto `public`) con permisos de solo lectura.
   - En “Aceptar paquetes SNMP de estos hosts”, agregar la IP del panel o marcar “Aceptar paquetes SNMP de cualquier host”.

### Configuración en el Panel
- En “Agregar/Editar Servidor”, completar:
  - Comunidad SNMP.
  - Puerto UDP (por defecto 161).
- Accede al monitoreo desde la acción “Monitoreo SNMP” del servidor.

### Nota
Si el servidor no responde a SNMP, el panel mostrará las gráficas en modo demostración y un aviso con instrucciones para habilitar SNMP en el destino.

---

## 🧱 Arquitectura y Guía de Desarrollo

Esta sección resume cómo está organizado el proyecto (front/back), los modelos de datos, las funciones reutilizables y cómo extender la UI (por ejemplo, agregar un botón nuevo).

### Visión General
- Framework: Django.
- App principal: `servidores` (rutas, vistas, modelos, servicios y templates).
- Patrón general:
  - Vistas ligeras que orquestan la lógica.
  - Módulos `services_*.py` encapsulan integraciones (WinRM, SSH, Docker local, SNMP).
  - Templates Bootstrap 5 con un modal de confirmación reutilizable.

### Modelado de Datos
- Modelos en [models.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/models.py):
  - Host: equipo gestionado; credenciales y tipo de conexión. Relación 1:N con Instancia.
  - Instancia: servicio o contenedor asociado a un Host. Campos clave: `tipo_servicio` (tomcat/node/docker), `tipo_instalacion` (sistema/docker), `nombre_servicio` (o `PID:xxxx` para procesos detectados), `puerto_tomcat`.
  - Servidor: modelo histórico/legacy para vistas clásicas; conserva soporte SNMP y control.
- Migraciones crean tablas SQLite por defecto; ver carpeta [migrations](file:///d:/proyectosPython/PanelControlTomcat/servidores/migrations/).
- Integridad:
  - `Instancia.host` tiene `on_delete=CASCADE`, por lo que al eliminar un Host se eliminan sus Instancias.

### Rutas y Vistas
- URLs en [servidores/urls.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/urls.py):
  - Navegación avanzada: `/navegacion/` → [navegacion](file:///d:/proyectosPython/PanelControlTomcat/servidores/views.py#L170-L193)
  - Control de instancias: `/navegacion/instancia/<id>/<accion>/` → [controlar_instancia](file:///d:/proyectosPython/PanelControlTomcat/servidores/views.py#L227-L266)
  - Verificación: `/navegacion/instancia/<id>/verificar/` → [verificar_instancia](file:///d:/proyectosPython/PanelControlTomcat/servidores/views.py#L268-L304)
  - CRUD Host/Instancia: editar/eliminar endpoints dedicados.
  - Exploración/escaneo: `/navegacion/scan-host/` → [scan_host](file:///d:/proyectosPython/PanelControlTomcat/servidores/views.py#L306-L347)
  - TrustedHosts (Windows local): `/trusted-hosts...` → [trusted_hosts*](file:///d:/proyectosPython/PanelControlTomcat/servidores/views.py#L515-L592)

#### Flujo Navegación (alta/carga)
- Form Host e Instancia en plantilla; `POST` al mismo endpoint guardan con [HostForm / InstanciaForm](file:///d:/proyectosPython/PanelControlTomcat/servidores/forms.py).
- La sección “Resumen de Hosts e Instancias” muestra las instancias por host y botones de acción.
- Al completar acciones, se redirige de nuevo a `navegacion` y la tabla se repinta con mensajes flash.

### Frontend (Templates y UI)
- Base UI: [base.html](file:///d:/proyectosPython/PanelControlTomcat/servidores/templates/servidores/base.html)
  - Bootstrap 5 + Font Awesome.
  - Modal de confirmación reutilizable:
    - Cualquier enlace/botón con `data-confirm="true"` abre el modal.
    - Soporta `data-confirm-title`, `data-confirm-message`, `data-confirm-variant` (danger/warning/info).
- Vista principal: [navegacion.html](file:///d:/proyectosPython/PanelControlTomcat/servidores/templates/servidores/navegacion.html)
  - Formulario de Host e Instancia con validación y mensajes.
  - Resultados de escaneo y resumen de instancias con acciones:
    - Iniciar/Detener/Reiniciar/Eliminar
    - Verificar estado
  - Comportamiento especial PID:
    - Si `nombre_servicio` empieza por `PID:`, el botón Iniciar está deshabilitado.
    - Al “Detener” y confirmarse con éxito, la instancia se elimina de la tabla automáticamente.

#### Cómo agregar un botón nuevo en la UI
1. Agrega el botón en la plantilla correspondiente (p. ej., en la lista de acciones de [navegacion.html](file:///d:/proyectosPython/PanelControlTomcat/servidores/templates/servidores/navegacion.html#L317-L328)):
   - Usa un enlace `<a href="{% url 'nombre_de_ruta' args %}" ...>` o un `<button>` con `data-href`.
   - Si requiere confirmación, añade:
     - `data-confirm="true"`
     - `data-confirm-title="Título"`
     - `data-confirm-message="Mensaje descriptivo"`
     - `data-confirm-variant="danger|warning|info"`
2. Declara la ruta en [urls.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/urls.py).
3. Implementa la vista en [views.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/views.py), usa `messages.success/error` y redirige a la pantalla adecuada.
4. Si necesita lógica de sistema/remote, encapsúlala en un módulo `services_*.py`.

### Backend (Servicios y Utilidades)
- Verificación/Control de estado en [services.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/services.py) y [services_restart.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/services_restart.py):
  - Conexiones:
    - WinRM (Windows): `check_winrm`, `controlar_winrm`
    - SSH (Linux): `check_ssh`, `controlar_ssh`
    - Docker (SSH remoto): [services_docker.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/services_docker.py)
    - Local (Windows/Linux): [services_local.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/services_local.py)
  - Utilidades clave:
    - `check_tcp_port(ip, port)` — abre socket TCP con timeout para validar puertos.
    - `decode_winrm_output(bytes)` — decodificación robusta de salida PowerShell.
    - `ejecutar_comando_local(cmd)` — ejecución local consistente (PowerShell en Windows).
  - Reglas:
    - Si el estado es “Activo” pero el puerto HTTP no responde, se marca “Alerta” o corrige puerto (docker local) cuando es posible.

#### Control de acciones (start/stop/restart/delete)
- Vista [controlar_instancia](file:///d:/proyectosPython/PanelControlTomcat/servidores/views.py#L227-L266) construye un objeto “servidor_like” con datos del Host/Instancia y delega en funciones de control.
- Comportamiento especial para procesos `PID:`:
  - Al detener y confirmar éxito, la instancia se elimina de la base de datos (no queda “Detenida” en la UI).
- Acciones se reflejan con mensajes flash (Bootstrap alerts).

### Autodescubrimiento / Exploración
- Endpoint: [scan_host](file:///d:/proyectosPython/PanelControlTomcat/servidores/views.py#L306-L347)
  - Entrada: `host_id` y `tipo_servicio` (`tomcat` o `docker`).
  - Lógica:
    - `local`:
      - Tomcat: [listar_servicios_tomcat_locales](file:///d:/proyectosPython/PanelControlTomcat/servidores/services_local.py#L129-L207)
      - Docker: [listar_contenedores_docker_local](file:///d:/proyectosPython/PanelControlTomcat/servidores/services_local.py#L275-L303) con mensaje genérico si Docker no está disponible.
    - `ssh`:
      - Docker remoto: [listar_contenedores_docker](file:///d:/proyectosPython/PanelControlTomcat/servidores/services_docker.py#L4-L53)
    - `winrm`:
      - Solo Tomcat nativo (explorar Docker no aplica).
  - Respuesta: `{"items":[{nombre, display, estado, tipo_instalacion, puerto}], "error": null|str}`
  - Puerto HTTP se auto-detecta con `detectar_puerto_http` cuando es posible.

### Inserción y Edición de Datos
- Formularios:
  - [HostForm](file:///d:/proyectosPython/PanelControlTomcat/servidores/forms.py#L35-L60) y [InstanciaForm](file:///d:/proyectosPython/PanelControlTomcat/servidores/forms.py#L74-L96) usan `ModelForm`, por lo que `form.save()` inserta/actualiza registros.
- Vistas:
  - [navegacion](file:///d:/proyectosPython/PanelControlTomcat/servidores/views.py#L170-L193) gestiona creación de Host/Instancia por `POST`.
  - Editar y eliminar tienen endpoints específicos; al eliminar Host, sus instancias se borran en cascada.

### Comandos de Gestión Remota (Resumen)
- Windows/WinRM: `Get-Service`, `Start-Service`, `Stop-Service`, `Restart-Service`.
- Linux/SSH: `systemctl start/stop/restart`.
- Docker remoto (SSH): `sudo docker ps/start/stop/restart`.
- Local Windows: `Get-Service`, `Stop-Process -Id <PID>` para procesos detectados.

### Dónde buscar qué
- Modelos y relaciones: [models.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/models.py)
- Formularios: [forms.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/forms.py)
- Vistas y flujos: [views.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/views.py)
- Lógica de conexión/control:
  - WinRM/SSH/puertos: [services.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/services.py)
  - Control start/stop/restart: [services_restart.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/services_restart.py)
  - Docker (SSH): [services_docker.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/services_docker.py)
  - Local + TrustedHosts: [services_local.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/services_local.py)
- Templates y componentes UI:
  - Layout base + modal de confirmación: [base.html](file:///d:/proyectosPython/PanelControlTomcat/servidores/templates/servidores/base.html)
  - Navegación/Resumen y acciones: [navegacion.html](file:///d:/proyectosPython/PanelControlTomcat/servidores/templates/servidores/navegacion.html)
- Entradas SNMP:
  - Wrapper/worker: [services_snmp.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/services_snmp.py), [snmp_worker.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/snmp_worker.py)

### Ejemplo práctico: agregar una acción “Suspender”
1. Ruta en `urls.py`:
   - `path('navegacion/instancia/<int:pk>/suspender/', views.suspender_instancia, name='suspender_instancia')`
2. Vista en `views.py`:
   - Obtener instancia y decidir si aplica (p. ej., solo docker).
   - Llamar a una función en `services_*.py` que implemente la operación.
   - Registrar `messages.success/error` y `redirect('navegacion')`.
3. Botón en `navegacion.html`:
   - `<a href="{% url 'suspender_instancia' inst.id %}" class="btn btn-outline-secondary" data-confirm="true" data-confirm-title="Suspender instancia" data-confirm-message="¿Suspender la instancia {{ inst.nombre_servicio }}?" data-confirm-variant="warning"><i class="fas fa-pause"></i></a>`
4. Probar el flujo:
   - Ejecutar servidor, realizar la acción y verificar que la tabla y mensajes se actualicen.

Con este mapa podrás localizar rápidamente las piezas del código y extender el panel sin romper los flujos existentes.
