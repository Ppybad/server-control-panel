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

- Debes ejecutar el servidor de desarrollo **como Administrador**.
- Abre tu terminal (PowerShell/CMD) con **"Ejecutar como administrador"** antes de correr `python manage.py runserver`.

---

## 🐳 Despliegue con Docker (Entorno Servidor)

Esta opcion levanta el panel en contenedores usando Django + Redis + un worker Celery. La conexion a base de datos se toma desde `.env` y puede apuntar a SQLite o PostgreSQL segun `DB_MODE`.

### Prerrequisitos

- Docker Desktop instalado y en ejecución.
- Puerto `8000` libre en tu máquina (para acceder al panel).

### Levantar el stack

Desde la raíz del proyecto:

```bash
docker-compose up --build
```

Esto levanta:

- **web**: contenedor con Django, ejecuta `python manage.py migrate && python manage.py runserver 0.0.0.0:8000`
- **worker**: proceso Celery para monitoreo SSH/Celery
- **redis**: broker y result backend para Celery

Notas importantes:

- El archivo `docker-compose.yml` actual **no** incluye un contenedor `db`.
- La base real usada por Django sale de las variables `DB_MODE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` y opcionalmente `DB_SCHEMA`.
- Si `DB_MODE=postgres`, el panel usa el alias `postgres`; si no, usa `db.sqlite3`.

Acceso al panel:

- Navegador: `http://localhost:8000`

### Comandos de gestion dentro del contenedor

1. Ver el nombre de los contenedores:

```bash
docker ps
```

2. Ejecutar comandos Django dentro del contenedor `web`:

```bash
docker exec -it <nombre-del-contenedor-web> python manage.py createsuperuser
docker exec -it <nombre-del-contenedor-web> python manage.py migrate
docker exec -it <nombre-del-contenedor-web> python test_ssh.py <IP> <PUERTO> <USUARIO> <PASSWORD>
```

3. Ver logs de arranque y diagnostico:

```bash
docker-compose logs -f web
docker-compose logs -f worker
docker-compose up --build
```

### Parar y limpiar

- Detener contenedores (sin borrar datos de Postgres):

```bash
docker-compose down
```

- Detener y borrar datos (reiniciar base desde cero):

```bash
docker-compose down -v
```

### Limitaciones en modo Docker

Cuando el panel corre dentro de Docker:

- El panel esta pensado como **gestor remoto**:
  - Linux por SSH
  - Windows por WinRM
  - Docker remoto vía SSH
- Cuando el host configurado es `localhost` o `127.0.0.1`, el codigo intenta resolverlo como `host.docker.internal` dentro del contenedor para SSH.
- Las opciones “Local (Este Equipo)” pueden estar limitadas, ya que el contenedor no tiene acceso directo a los servicios del host ni al binario `docker` del host salvo configuracion extra.

---

## 📚 Documentación Técnica de Comandos

El panel utiliza distintos protocolos y comandos segun el tipo de conexion, el tipo de servicio y el flujo de navegacion activa.

### 1. Windows Remoto (WinRM)
Usa `pywinrm` con transporte NTLM sobre `http://<ip>:5985/wsman`.

- **Tomcat remoto**
  - Escaneo: `Get-WmiObject Win32_Service | Where-Object { $_.Name -like '*Tomcat*' -or $_.DisplayName -like '*Tomcat*' }`
  - Puertos por PID: `Get-NetTCPConnection -State Listen | Where-Object { $_.OwningProcess -eq $pid }`
  - Verificacion: `Get-Service -Name '<servicio>' | Select-Object -ExpandProperty Status`
  - Control: `Start-Service`, `Stop-Service -Force`, `Restart-Service -Force`
- **Node remoto**
  - Escaneo de servicios: `Get-WmiObject Win32_Service | Where-Object { $_.PathName -like '*node.exe*' ... }`
  - Escaneo de procesos: `Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' }`
  - Puertos por PID: `Get-NetTCPConnection -State Listen`
  - El flujo marca si el hallazgo es servicio Windows o proceso `PID:`.

### 2. Linux / SSH
Usa `paramiko` por SSH, normalmente en puerto `22`.

- **Tomcat remoto**
  - Verificacion: `systemctl is-active tomcat || systemctl is-active tomcat9 || systemctl is-active tomcat10`
  - Fallback por proceso: `ps aux | grep [t]omcat`
  - Puertos: `ss -ltnp | grep java || netstat -ltnp | grep java`
  - Control: `sudo systemctl start|stop|restart <servicio>`
- **Node remoto**
  - PM2: `pm2 jlist 2>/dev/null || true`
  - systemd: `systemctl list-units --type=service --all | grep -i node || true`
  - procesos: `ps aux | grep [n]ode`
  - puertos: `ss -ltnp | grep <pid> || netstat -ltnp | grep <pid>`
  - El flujo clasifica origen como `pm2`, `systemd_service` o `proceso_pid`.

### 3. Docker por SSH
Se conecta al host remoto por SSH y ejecuta Docker con `sudo -S`.

- **Listar contenedores:** `sudo -S docker ps -a --format '{{.ID}}|{{.Names}}|{{.Status}}|{{.Image}}'`
- **Verificar estado:** `sudo -S docker ps -a --filter 'name=<contenedor>' --format '{{.Status}}'`
- **Iniciar:** `sudo -S docker start <contenedor>`
- **Detener:** `sudo -S docker stop <contenedor>`
- **Reiniciar:** `sudo -S docker restart <contenedor>`

El password se manda por `stdin`, por eso no aparece literal en el comando final.

### 4. Local (Este Equipo)
Ejecuta comandos en la maquina donde corre el panel.

#### Windows Local
- **Tomcat servicios:** `Get-Service | Where-Object { $_.Name -like '*Tomcat*' -or $_.DisplayName -like '*Tomcat*' }`
- **Tomcat procesos manuales:** `Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'java.exe' -or $_.Name -eq 'javaw.exe' }`
- **Node servicios:** `Get-WmiObject Win32_Service | Where-Object { $_.PathName -like '*node.exe*' ... }`
- **Node procesos:** `Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' }`
- **Puertos:** `Get-NetTCPConnection -State Listen`
- **Control servicios:** `Start-Service`, `Stop-Service`, `Restart-Service`
- **Control procesos PID:** `Stop-Process -Id <PID> -Force`

#### Linux Local
- **Tomcat local:** exploracion aun no esta implementada completamente
- **Node local:** `ps aux | grep [n]ode`
- **Puertos Node:** `ss -ltnp | grep <pid> || netstat -ltnp | grep <pid>`
- **Control servicios:** `sudo systemctl start|stop|restart <servicio>`

### 5. Flujo de autodescubrimiento
El endpoint `/navegacion/scan-host/` soporta `tomcat`, `docker` y `node`.

- Si el host es `winrm`, el escaneo remoto disponible es `tomcat` y `node`.
- Si el host es `ssh`, el escaneo remoto disponible es `tomcat`, `node` y `docker`.
- Si el host es `local`, el flujo usa funciones locales para `tomcat`, `node` y `docker`.
- Los items devueltos incluyen `nombre`, `display`, `estado`, `puerto`, `tipo_instalacion` y, para Node, metadatos extra como `origen_node`, `controlable_node` y `rol_node`.

### 6. SNMP y monitoreo Celery/SSH
El panel soporta dos modos de monitoreo visual: **SNMP** y **Celery/SSH**.

**Diagnostico SNMP desde CLI**
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

**Arquitectura SNMP**
- El panel invoca un worker aislado para SNMP: [snmp_worker.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/snmp_worker.py).
- La vista usa un wrapper sincronico [services_snmp.py](file:///d:/proyectosPython/PanelControlTomcat/servidores/services_snmp.py) que lanza el worker via `subprocess`.
- Si SNMP falla, la UI entra en modo simulacion y muestra ayuda contextual.

**Arquitectura Celery/SSH**
- La vista `monitor_host_celery` lanza la tarea [monitor_host](file:///d:/proyectosPython/PanelControlTomcat/servidores/tasks.py).
- La tarea usa SSH y ejecuta:
  - `top -bn1 | grep "Cpu(s)"`
  - `free -m`
  - `pgrep -f node`
  - `pgrep -f tomcat`
- El resultado se devuelve a la UI para graficar CPU y RAM sin depender de persistencia de metricas.

**Ejecución Manual del Worker**
```bash
python servidores/snmp_worker.py <IP> <COMUNIDAD> [PUERTO]
# Ejemplo:
python servidores/snmp_worker.py 10.63.17.147 public 161
```

**Tiempos de espera y fallback**
- El wrapper SNMP usa timeout del worker y fallback a modo simulacion si no hay respuesta.
- La ventana de monitoreo refresca cada 2 segundos y pausa cuando la pestana deja de estar visible.

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

## 📊 Monitoreo (Resumen)

- **SNMP**: CPU, RAM, uptime y descripcion del sistema por OID.
- **Celery/SSH**: CPU y RAM por comandos Linux, mas validacion basica de procesos Node/Tomcat.
- **Configuracion del host**:
  - `snmp_community` y `snmp_port` para monitoreo SNMP
  - `usuario`, `password` y `puerto_conexion` para monitoreo Celery/SSH
- **Acceso UI**:
  - `monitoreo/host/<id>/` para SNMP
  - `monitoreo/host/<id>/celery/` para Celery/SSH

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
  - Host: equipo gestionado; credenciales, tipo de conexión y parámetros SNMP. Relación 1:N con Instancia.
  - Instancia: servicio o contenedor asociado a un Host. Campos clave: `tipo_servicio` (tomcat/node/docker), `tipo_instalacion` (sistema/docker), `nombre_servicio` (o `PID:xxxx` para procesos detectados), `puerto_tomcat`.
- Migraciones crean tablas SQLite por defecto; ver carpeta [migrations](file:///d:/proyectosPython/PanelControlTomcat/servidores/migrations/). El estado final solo incluye Host e Instancia para la sección Navegación.
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
