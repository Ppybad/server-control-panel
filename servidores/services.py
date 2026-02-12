import winrm
import paramiko
from django.utils import timezone
import socket

def decode_winrm_output(bytes_data):
    """
    Intenta decodificar la salida de WinRM con múltiples codificaciones
    para evitar errores con caracteres especiales (tildes, ñ, etc).
    """
    if not bytes_data:
        return ""
    
    encodings = ['utf-8', 'cp850', 'cp1252', 'latin-1']
    
    for enc in encodings:
        try:
            return bytes_data.decode(enc).strip()
        except UnicodeDecodeError:
            continue
            
    # Si todo falla, usar utf-8 con replace
    return bytes_data.decode('utf-8', errors='replace').strip()

def check_tcp_port(ip, port):
    """
    Verifica si un puerto TCP está abierto y aceptando conexiones.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2) # 2 segundos de timeout
        result = sock.connect_ex((ip, int(port)))
        sock.close()
        return result == 0
    except Exception:
        return False

from .services_docker import verificar_estado_docker
from .services_local import verificar_estado_local_sistema, verificar_estado_local_docker

def verificar_estado_servidor(servidor):
    """
    Verifica el estado del servidor según su configuración.
    Actualiza el objeto servidor y lo guarda.
    """
    estado = "Error"
    mensaje = ""

    try:
        # 1. Verificar servicio (Local, WinRM, SSH o Docker Remoto)
        if servidor.tipo_conexion == 'local':
            if servidor.tipo_instalacion == 'docker':
                estado, mensaje = verificar_estado_local_docker(servidor.nombre_servicio)
            else:
                estado, mensaje = verificar_estado_local_sistema(servidor.nombre_servicio)
                
        elif servidor.tipo_instalacion == 'docker':
            estado, mensaje = verificar_estado_docker(servidor)
        elif servidor.tipo_conexion == 'winrm':
            estado, mensaje = check_winrm(servidor)
        elif servidor.tipo_conexion == 'ssh':
            estado, mensaje = check_ssh(servidor)
        else:
            mensaje = "Tipo de conexión no soportado."
            
        # 2. Si el servicio está activo, verificar también el puerto TCP
        if estado == "Activo":
            if not check_tcp_port(servidor.ip_host, servidor.puerto_tomcat):
                # El servicio corre pero el puerto no responde
                estado = "Alerta"
                mensaje = f"Servicio activo, pero puerto {servidor.puerto_tomcat} inalcanzable (cerrado o bloqueado)."
            else:
                mensaje += f" Puerto {servidor.puerto_tomcat} OK."
            
    except Exception as e:
        mensaje = str(e)

    servidor.estado = estado
    servidor.mensaje_error = mensaje if estado != 'Activo' else ""
    servidor.ultimo_check = timezone.now()
    servidor.save()
    
    return estado, mensaje

def check_winrm(servidor):
    port = servidor.puerto_conexion if servidor.puerto_conexion else 5985
    url = f"http://{servidor.ip_host}:{port}/wsman"
    
    try:
        if not servidor.usuario or not servidor.password:
            return "Error", "Faltan credenciales (usuario/password)"

        session = winrm.Session(url, auth=(servidor.usuario, servidor.password), transport='ntlm')
        
        # Estrategia mejorada: 
        # 1. Si tenemos nombre de servicio guardado, usarlo directamente.
        # 2. Si no, intentar descubrirlo por puerto (si el puerto está activo).
        # 3. Si no se puede por puerto, buscar genéricamente "*Tomcat*".

        service_name = servidor.nombre_servicio
        
        # Intentar autodescubrimiento si no tenemos nombre o si queremos revalidar
        # Solo si el puerto está respondiendo, podemos intentar mapear Puerto -> PID -> Servicio
        port_open = check_tcp_port(servidor.ip_host, servidor.puerto_tomcat)
        
        if not service_name and port_open:
            # Script para descubrir el servicio que escucha en el puerto
            discovery_script = f"""
            $conn = Get-NetTCPConnection -LocalPort {servidor.puerto_tomcat} -State Listen -ErrorAction SilentlyContinue
            if ($conn) {{
                $pid_val = $conn.OwningProcess
                $svc = Get-WmiObject Win32_Service | Where-Object {{ $_.ProcessId -eq $pid_val }}
                if ($svc) {{
                    Write-Output "FOUND_SVC:$($svc.Name)"
                }}
            }}
            """
            res_disc = session.run_ps(discovery_script)
            out_disc = decode_winrm_output(res_disc.std_out)
            
            if "FOUND_SVC:" in out_disc:
                parts = out_disc.split("FOUND_SVC:")
                if len(parts) > 1:
                    found_name = parts[1].strip()
                    servidor.nombre_servicio = found_name
                    service_name = found_name
                    # No guardamos todavía, se guardará al final de verificar_estado_servidor
        
        # Ahora verificamos el estado del servicio
        if service_name:
            # Verificar servicio específico
            ps_script = f"Get-Service -Name '{service_name}' | Select-Object -ExpandProperty Status"
        else:
            # Fallback genérico (cuidado, puede afectar a múltiples servicios si se usa para control)
            ps_script = "Get-Service | Where-Object {$_.Name -like '*Tomcat*'} | Select-Object -ExpandProperty Status"
            
        result = session.run_ps(ps_script)
        
        if result.status_code == 0:
            output = decode_winrm_output(result.std_out)
            # Get-Service puede devolver múltiples líneas si el wildcard matchea varios
            # Si usamos service_name específico, debería ser una sola.
            
            if "Running" in output:
                return "Activo", f"Servicio {service_name or 'Tomcat'} ejecutándose."
            elif "Stopped" in output:
                return "Detenido", f"Servicio {service_name or 'Tomcat'} detenido."
            elif not output:
                 return "Error", f"No se encontró servicio: {service_name or '*Tomcat*'}"
            else:
                return "Desconocido", f"Estado: {output}"
        else:
            err = decode_winrm_output(result.std_err)
            if "Cannot find any service with service name" in err:
                 return "Error", f"Servicio '{service_name}' no encontrado."
            return "Error", f"Error WinRM: {err}"
            
    except Exception as e:
        return "Error", f"Fallo conexión WinRM (Puerto {port}): {str(e)}"

def check_ssh(servidor):
    try:
        if not servidor.usuario or not servidor.password:
            return "Error", "Faltan credenciales"

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        port = servidor.puerto_conexion if servidor.puerto_conexion else 22
        client.connect(servidor.ip_host, port=port, username=servidor.usuario, password=servidor.password, timeout=5)
        
        # Intento 1: Systemctl (común en linux modernos)
        # Buscamos tomcat, tomcat9, tomcat10...
        cmd = "systemctl is-active tomcat || systemctl is-active tomcat9 || systemctl is-active tomcat10"
        stdin, stdout, stderr = client.exec_command(cmd)
        status = stdout.read().decode().strip()
        
        if status == "active":
            client.close()
            return "Activo", "Servicio Tomcat activo (systemctl)."
        elif status == "inactive":
            client.close()
            return "Detenido", "Servicio Tomcat detenido (systemctl)."
        
        # Intento 2: Buscar proceso java corriendo tomcat
        stdin, stdout, stderr = client.exec_command("ps aux | grep [t]omcat")
        output = stdout.read().decode()
        client.close()
        
        if output:
            return "Activo", "Proceso Tomcat detectado en ejecución."
        
        return "Error", "No se detectó servicio ni proceso Tomcat."

    except Exception as e:
        return "Error", f"Fallo conexión SSH (Puerto {port}): {str(e)}"
