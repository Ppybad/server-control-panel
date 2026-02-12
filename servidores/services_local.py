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
            # Buscamos procesos java.exe cuya línea de comando contenga 'org.apache.catalina.startup.Bootstrap'
            cmd_proc = "Get-CimInstance Win32_Process -Filter \"Name = 'java.exe'\" | Where-Object {$_.CommandLine -like '*org.apache.catalina.startup.Bootstrap*'} | Select-Object ProcessId, CommandLine | ConvertTo-Json"
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
        cmd = f"docker ps --filter 'name={nombre_contenedor}' --format '{{{{.Status}}}}'"
        # En Windows local, docker puede invocarse directamente si está en PATH
        if platform.system() == "Windows":
             output, error = ejecutar_comando_local(cmd)
        else:
             output, error = ejecutar_comando_local(cmd)

        if error:
            return "Error", f"Error Docker Local: {error}"
            
        if output and "Up" in output:
            return "Activo", f"Contenedor en ejecución ({output})"
        else:
            return "Detenido", "Contenedor no está corriendo"
            
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
             return None, f"Error Docker Local: {error}"
        
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
