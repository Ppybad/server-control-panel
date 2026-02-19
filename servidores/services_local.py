import subprocess
import platform

def ejecutar_comando_local(comando):
    """
    Ejecuta un comando en el sistema local y devuelve (output, error).
    """
    try:
        # Usar powershell en Windows para consistencia con WinRM
        if platform.system() == "Windows":
            cmd = ["powershell", "-Command", comando]
        else:
            cmd = comando.split()
            
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        return result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return None, str(e)

# --- SERVICIOS DEL SISTEMA (Tomcat Nativo) ---

def verificar_estado_local_sistema(nombre_servicio):
    """
    Verifica si un servicio de Windows local está corriendo.
    Soporta servicios tradicionales y procesos identificados por PID (PID:XXXX).
    """
    if not nombre_servicio:
        return "Desconocido", "Sin nombre de servicio"

    try:
        # Detectar si es un proceso PID
        if nombre_servicio.startswith("PID:"):
            pid = nombre_servicio.split(":")[1]
            if platform.system() == "Windows":
                # Verificar si el proceso existe
                cmd = f"Get-Process -Id {pid} | Select-Object Id"
                output, error = ejecutar_comando_local(cmd)
                if not error and output:
                    return "Activo", f"Proceso {pid} en ejecución."
                else:
                    return "Detenido", f"Proceso {pid} no encontrado (puede haber terminado)."
            else:
                 # Linux simple check
                 return "Desconocido", "Verificación PID no implementada en Linux"

        if platform.system() == "Windows":
            cmd = f"Get-Service -Name '{nombre_servicio}' | Select-Object -ExpandProperty Status"
            output, error = ejecutar_comando_local(cmd)
            
            if error and "Cannot find any service" in error:
                return "Error", f"Servicio '{nombre_servicio}' no encontrado."
            
            if output == "Running":
                return "Activo", "El servicio está en ejecución."
            elif output == "Stopped":
                return "Detenido", "El servicio está detenido."
            else:
                return "Desconocido", f"Estado: {output}"
        else:
            # Linux (systemctl)
            cmd = f"systemctl is-active {nombre_servicio}"
            output, error = ejecutar_comando_local(cmd)
            if output == "active":
                return "Activo", "Servicio activo"
            else:
                return "Detenido", f"Estado: {output}"

    except Exception as e:
        return "Error", f"Fallo verificación local: {str(e)}"

def controlar_servicio_local_sistema(nombre_servicio, accion):
    """
    Inicia, detiene o reinicia un servicio local.
    Soporta control básico de procesos PID (solo Detener).
    """
    if not nombre_servicio:
        return False, "Sin nombre de servicio"

    # Manejo de procesos PID
    if nombre_servicio.startswith("PID:"):
        pid = nombre_servicio.split(":")[1]
        if accion == 'stop':
            if platform.system() == "Windows":
                cmd = f"Stop-Process -Id {pid} -Force"
                output, error = ejecutar_comando_local(cmd)
                if error:
                    return False, f"Error al detener proceso {pid}: {error}"
                return True, f"Proceso {pid} terminado."
            else:
                return False, "No implementado en Linux"
        else:
            return False, "Para procesos detectados (IDEs), solo se permite la acción 'Detener'. Debes iniciarlos manualmente desde tu entorno."

    cmds = {
        'start': 'Start-Service',
        'stop': 'Stop-Service',
        'restart': 'Restart-Service'
    }
    
    verb = cmds.get(accion)
    if not verb:
        return False, "Acción no válida"

    try:
        if platform.system() == "Windows":
            # Requiere privilegios de administrador si el script no los tiene
            cmd = f"{verb} -Name '{nombre_servicio}'"
            output, error = ejecutar_comando_local(cmd)
            
            if error:
                return False, f"Error al {accion}: {error}"
            return True, f"Servicio {accion}do correctamente."
        else:
            # Linux
            cmd = f"sudo systemctl {accion} {nombre_servicio}"
            output, error = ejecutar_comando_local(cmd)
            if error:
                 return False, error
            return True, "OK"

    except Exception as e:
        return False, str(e)

def listar_servicios_tomcat_locales():
    """
    Lista servicios locales que parecen ser Tomcat (contienen 'Tomcat' en el nombre).
    También intenta detectar procesos Java que parezcan ser Tomcat (lanzados por IDEs).
    """
    try:
        servicios_encontrados = []
        errores = []

        if platform.system() == "Windows":
            # 1. Buscar Servicios de Windows (Services.msc)
            cmd_services = "Get-Service | Where-Object {$_.Name -like '*Tomcat*' -or $_.DisplayName -like '*Tomcat*'} | Select-Object Name, DisplayName, Status | ConvertTo-Json"
            output_svc, error_svc = ejecutar_comando_local(cmd_services)
            
            if not error_svc and output_svc:
                import json
                try:
                    data = json.loads(output_svc)
                    if isinstance(data, dict):
                        data = [data]
                    
                    for svc in data:
                        servicios_encontrados.append({
                            'nombre': svc.get('Name'),
                            'display': f"[Servicio] {svc.get('DisplayName')}",
                            'estado': 'Activo' if svc.get('Status') == 4 else 'Detenido',
                            'tipo': 'servicio'
                        })
                except json.JSONDecodeError:
                    errores.append("Error decodificando servicios JSON")

            # 2. Buscar Procesos Java (IDEs / Manuales)
            # Buscamos procesos java.exe o javaw.exe cuya línea de comando contenga 'catalina'
            cmd_proc = (
                "Get-CimInstance Win32_Process "
                "| Where-Object { ($_.Name -eq 'java.exe' -or $_.Name -eq 'javaw.exe') "
                "-and $_.CommandLine -like '*catalina*' } "
                "| Select-Object ProcessId, CommandLine | ConvertTo-Json"
            )
            output_proc, error_proc = ejecutar_comando_local(cmd_proc)

            if not error_proc and output_proc:
                import json
                try:
                    data_proc = json.loads(output_proc)
                    if isinstance(data_proc, dict):
                        data_proc = [data_proc]
                    
                    for proc in data_proc:
                        # Extraer ruta base para identificar (ej. C:\Users\...\apache-tomcat-9.0.X)
                        cmd_line = proc.get('CommandLine', '')
                        pid = proc.get('ProcessId')
                        
                        # Intento simple de extraer nombre legible de la ruta
                        import re
                        match = re.search(r'-Dcatalina.base=["\']?([^"\']+)["\']?', cmd_line)
                        nombre_base = "Tomcat Process"
                        if match:
                            path_base = match.group(1)
                            # Tomar el nombre de la carpeta final
                            nombre_base = path_base.split('\\')[-1]
                        
                        servicios_encontrados.append({
                            'nombre': f"PID:{pid}", # Usamos PID como identificador temporal
                            'display': f"[Proceso] {nombre_base} (PID: {pid})",
                            'estado': 'Activo', # Si está en procesos, está activo
                            'tipo': 'proceso'
                        })
                except json.JSONDecodeError:
                    errores.append("Error decodificando procesos JSON")

            if not servicios_encontrados:
                msg = "No se encontraron servicios ni procesos Tomcat."
                if errores:
                    msg += f" (Errores: {', '.join(errores)})"
                return [], None # Retornamos vacío sin error crítico para que muestre la lista vacía en UI

            return servicios_encontrados, None

        else:
            # Linux (systemctl)
            cmd = "systemctl list-units --type=service --all | grep -i tomcat"
            output, error = ejecutar_comando_local(cmd)
            # Implementación simplificada para Linux
            return [], "Autodescubrimiento no implementado completamente para Linux Local"

    except Exception as e:
        return [], str(e)

# --- DOCKER LOCAL ---

def verificar_estado_local_docker(nombre_contenedor):
    """
    Verifica estado de contenedor Docker local.
    """
    if not nombre_contenedor:
        return "Desconocido", "Sin nombre de contenedor"

    try:
        # Usamos -a para buscar también contenedores detenidos y evitar falsos negativos "No such container"
        cmd = f"docker ps -a --filter 'name={nombre_contenedor}' --format '{{{{.Status}}}}'"
        # En Windows local, docker puede invocarse directamente si está en PATH
        if platform.system() == "Windows":
             output, error = ejecutar_comando_local(cmd)
        else:
             output, error = ejecutar_comando_local(cmd)

        if error:
            # Si el error es "No such container", es que no existe
            if "No such container" in error:
                return "Error", "El contenedor no existe"
            return "Error", f"Error Docker Local: {error}"
            
        if output and "Up" in output:
            return "Activo", f"Contenedor en ejecución ({output})"
        elif output:
            # Si hay output pero no dice "Up", es que existe pero está detenido (ej. "Exited (0)...")
            return "Detenido", f"Contenedor detenido ({output})"
        else:
            # Si no hay output con filter, es que no encontró coincidencia
            return "Error", "Contenedor no encontrado (puede haber sido eliminado)"
            
    except Exception as e:
        return "Error", str(e)

def controlar_servicio_local_docker(nombre_contenedor, accion):
    """
    Controla contenedor Docker local.
    """
    if not nombre_contenedor:
        return False, "Sin nombre de contenedor"

    valid_actions = ['start', 'stop', 'restart']
    if accion not in valid_actions:
        return False, "Acción inválida"

    try:
        cmd = f"docker {accion} {nombre_contenedor}"
        output, error = ejecutar_comando_local(cmd)
        
        if error:
            return False, f"Error Docker: {error}"
        return True, f"Contenedor {accion}do."
    except Exception as e:
        return False, str(e)

def listar_contenedores_docker_local():
    """
    Lista contenedores Docker locales.
    """
    try:
        cmd = "docker ps -a --format '{{.ID}}|{{.Names}}|{{.Status}}|{{.Image}}'"
        output, error = ejecutar_comando_local(cmd)
        
        if error and not output:
            msg = error or ""
            if "dockerDesktopLinuxEngine" in msg or "The system cannot find the file specified" in msg:
                msg = "No se pudo conectar al motor Docker local. Asegúrate de que Docker esté instalado y corriendo en esta máquina."
            return None, f"Error Docker Local: {msg}"
        
        contenedores = []
        for line in output.strip().split('\n'):
            if line:
                parts = line.split('|')
                if len(parts) >= 4:
                    contenedores.append({
                        'id': parts[0],
                        'nombre': parts[1],
                        'estado': parts[2],
                        'imagen': parts[3]
                    })
        
        return contenedores, None
    except Exception as e:
        return None, f"Excepción local: {str(e)}"

def listar_servicios_node_locales():
    """
    Lista servicios y procesos Node locales, intentando extraer puertos
    y nombres legibles cuando sea posible.
    """
    try:
        encontrados = []
        if platform.system() == "Windows":
            # Servicios que ejecutan node.exe
            cmd_svc = (
                "Get-WmiObject Win32_Service | "
                "Where-Object { $_.PathName -like '*node.exe*' -or $_.Name -like '*node*' -or $_.DisplayName -like '*node*' } "
                "| Select-Object Name, DisplayName, State, ProcessId | ConvertTo-Json"
            )
            out_svc, err_svc = ejecutar_comando_local(cmd_svc)
            import json
            if out_svc:
                try:
                    data = json.loads(out_svc)
                    if isinstance(data, dict):
                        data = [data]
                    # Pre-index de puertos por PID
                    out_ports, _ = ejecutar_comando_local("Get-NetTCPConnection -State Listen | Select-Object OwningProcess, LocalPort | ConvertTo-Json")
                    pid_ports = {}
                    if out_ports:
                        try:
                            pjs = json.loads(out_ports)
                            if isinstance(pjs, dict):
                                pjs = [pjs]
                            for r in pjs:
                                pid_ports.setdefault(int(r.get('OwningProcess') or 0), set()).add(int(r.get('LocalPort') or 0))
                        except Exception:
                            pass
                    for s in data:
                        pid = int(s.get('ProcessId') or 0)
                        ports = sorted(list(pid_ports.get(pid, [])))
                        prefer = [4000, 9005, 9007, 3000, 8080, 8000, 5000, 80, 8888]
                        chosen = None
                        for cand in prefer:
                            if cand in ports:
                                chosen = cand
                                break
                        if not chosen and ports:
                            chosen = ports[0]
                        encontrados.append({
                            'nombre': s.get('Name'),
                            'display': f"[Servicio] {s.get('DisplayName')}",
                            'estado': 'Activo' if str(s.get('State','')).lower() in ['running','4'] else 'Detenido',
                            'tipo': 'servicio',
                            'puerto': chosen or 3000,
                            'origen_node': 'servicio_windows',
                            'controlable_node': True,
                            'detalle_node': None,
                        })
                except json.JSONDecodeError:
                    pass
            # Procesos node.exe
            cmd_proc = "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' } | Select-Object ProcessId, CommandLine | ConvertTo-Json"
            out_p, err_p = ejecutar_comando_local(cmd_proc)
            if out_p:
                try:
                    data = json.loads(out_p)
                    if isinstance(data, dict):
                        data = [data]
                    # Pre-index de puertos por PID
                    out_ports, _ = ejecutar_comando_local("Get-NetTCPConnection -State Listen | Select-Object OwningProcess, LocalPort | ConvertTo-Json")
                    pid_ports = {}
                    if out_ports:
                        try:
                            pjs = json.loads(out_ports)
                            if isinstance(pjs, dict):
                                pjs = [pjs]
                            for r in pjs:
                                pid_ports.setdefault(int(r.get('OwningProcess') or 0), set()).add(int(r.get('LocalPort') or 0))
                        except Exception:
                            pass
                    import re as _re
                    for p in data:
                        pid = int(p.get('ProcessId') or 0)
                        cmdline = p.get('CommandLine') or ''
                        name_disp = "Proceso Node"
                        m = _re.search(r'([\\\/])([^\\\/]+\.(js|ts|mjs))', cmdline)
                        if m:
                            name_disp = f"{name_disp} ({m.group(2)})"
                        ports = sorted(list(pid_ports.get(pid, [])))
                        prefer = [4000, 9005, 9007, 3000, 8080, 8000, 5000, 80, 8888]
                        chosen = None
                        for cand in prefer:
                            if cand in ports:
                                chosen = cand
                                break
                        if not chosen and ports:
                            chosen = ports[0]
                        rol = None
                        try:
                            low_cmd = cmdline.lower()
                            if any(x in low_cmd for x in ['worker', 'daemon', 'queue', 'consumer']):
                                rol = 'worker'
                            elif any(x in low_cmd for x in ['api', 'server', 'index.js', 'app.js', 'main.js']):
                                rol = 'api'
                        except Exception:
                            pass
                        encontrados.append({
                            'nombre': f"PID:{pid}",
                            'display': f"[Proceso] {name_disp}",
                            'estado': 'Activo',
                            'tipo': 'proceso',
                            'puerto': chosen,
                            'origen_node': 'proceso_pid',
                            'controlable_node': False,
                            'detalle_node': cmdline,
                            'rol_node': rol,
                        })
                except Exception:
                    pass
            return encontrados, None
        else:
            # Linux local
            out, err = ejecutar_comando_local("ps aux | grep [n]ode")
            pids = []
            for line in (out or "").splitlines():
                parts = line.split()
                if len(parts) > 1 and parts[1].isdigit():
                    pids.append(int(parts[1]))
            encontrados = []
            for pid in pids[:50]:
                outp, errp = ejecutar_comando_local(f"ss -ltnp | grep 'pid {pid}' || ss -ltnp | grep {pid} || netstat -ltnp | grep {pid}")
                import re as _re
                ports = [int(x) for x in _re.findall(r':(\d+)\s', outp or "")]
                prefer = [4000, 9005, 9007, 3000, 8080, 8000, 5000, 80, 8888]
                chosen = None
                for cand in prefer:
                    if cand in ports:
                        chosen = cand
                        break
                if not chosen and ports:
                    chosen = ports[0]
                rol = None
                cmdline = ""
                try:
                    cmdline, _ = ejecutar_comando_local(f"ps -p {pid} -o command=")
                    low_cmd = (cmdline or "").lower()
                    if any(x in low_cmd for x in ['worker', 'daemon', 'queue', 'consumer']):
                        rol = 'worker'
                    elif any(x in low_cmd for x in ['api', 'server', 'index.js', 'app.js', 'main.js']):
                        rol = 'api'
                except Exception:
                    pass
                encontrados.append({
                    'nombre': f"PID:{pid}",
                    'display': f"[Proceso] Node (PID: {pid})",
                    'estado': 'Activo',
                    'tipo': 'proceso',
                    'puerto': chosen,
                    'origen_node': 'proceso_pid',
                    'controlable_node': False,
                    'detalle_node': cmdline,
                    'rol_node': rol,
                })
            return encontrados, None
    except Exception as e:
        return [], str(e)

def obtener_puerto_publico_local(nombre_contenedor):
    """
    Intenta obtener el primer puerto público mapeado de un contenedor local.
    Devuelve (puerto, error).
    """
    try:
        # Obtenemos los puertos en formato raw
        cmd = f"docker ps --filter 'name={nombre_contenedor}' --format '{{{{.Ports}}}}'"
        output, error = ejecutar_comando_local(cmd)
        
        if error:
            return None, error
        
        if not output:
            return None, "Contenedor no encontrado o sin puertos"
            
        # Ejemplo output: "0.0.0.0:8080->8080/tcp, :::8080->8080/tcp"
        # O simplemente: "8080/tcp" (si no está mapeado)
        
        import re
        # Buscamos patrón 0.0.0.0:PORT-> o :::PORT->
        match = re.search(r':(\d+)->', output)
        if match:
            return int(match.group(1)), None
            
        return None, "No se detectó mapeo de puertos público"
        
    except Exception as e:
        return None, str(e)

# --- WINRM TRUSTEDHOSTS (Cliente local) ---

def obtener_trusted_hosts():
    import platform
    if platform.system() != "Windows":
        return [], "TrustedHosts solo aplica para cliente Windows"
    try:
        cmd = "(Get-Item WSMan:\\localhost\\Client\\TrustedHosts).Value"
        output, error = ejecutar_comando_local(cmd)
        if error and not output:
            return [], error
        value = (output or "").strip()
        if not value:
            return [], None
        # Separar por comas, limpiar espacios
        hosts = [h.strip() for h in value.split(",") if h.strip()]
        return hosts, None
    except Exception as e:
        return [], str(e)
def establecer_trusted_hosts(hosts):
    import platform
    if platform.system() != "Windows":
        return False, "Solo disponible en Windows", None
    try:
        value = ",".join([h.strip() for h in hosts if h and h.strip()])
        cmd = f'Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value "{value}" -Force'
        output, error = ejecutar_comando_local(cmd)
        if error:
            return False, error, cmd
        return True, None, cmd
    except Exception as e:
        return False, str(e), None
def agregar_trusted_host(host):
    import platform
    if platform.system() != "Windows":
        return [], "Solo disponible en Windows", None
    h = (host or "").strip()
    if not h:
        return [], "Host vacío", None
    hosts, error = obtener_trusted_hosts()
    if error and hosts is None:
        return [], error, None
    hosts = hosts or []
    if h in hosts:
        return hosts, None, None
    if h == "*":
        ok, err, cmd = establecer_trusted_hosts(["*"])
        if not ok:
            return [], err, cmd
        return ["*"], None, cmd
    if "*" in hosts:
        hosts = [x for x in hosts if x != "*"]
    new_list = hosts + [h]
    ok, err, cmd = establecer_trusted_hosts(new_list)
    if not ok:
        return [], err, cmd
    return new_list, None, cmd
def eliminar_trusted_host(host):
    import platform
    if platform.system() != "Windows":
        return [], "Solo disponible en Windows", None
    h = (host or "").strip()
    if not h:
        return [], "Host vacío", None
    hosts, error = obtener_trusted_hosts()
    if error and hosts is None:
        return [], error, None
    hosts = hosts or []
    if h not in hosts:
        return hosts, None, None
    new_list = [x for x in hosts if x != h]
    ok, err, cmd = establecer_trusted_hosts(new_list)
    if not ok:
        return [], err, cmd
    return new_list, None, cmd
def establecer_comodin_trustedhosts(activar):
    import platform
    if platform.system() != "Windows":
        return [], "Solo disponible en Windows", None
    if activar:
        ok, err, cmd = establecer_trusted_hosts(["*"])
        if not ok:
            return [], err, cmd
        return ["*"], None, cmd
    hosts, error = obtener_trusted_hosts()
    if error and hosts is None:
        return [], error, None
    hosts = hosts or []
    new_list = [x for x in hosts if x != "*"]
    ok, err, cmd = establecer_trusted_hosts(new_list)
    if not ok:
        return [], err, cmd
    return new_list, None, cmd
