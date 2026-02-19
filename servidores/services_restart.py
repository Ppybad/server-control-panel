import winrm
import paramiko

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

def reiniciar_servidor_tomcat(servidor):
    return controlar_servicio_tomcat(servidor, 'restart')

def detener_servidor_tomcat(servidor):
    return controlar_servicio_tomcat(servidor, 'stop')

def iniciar_servidor_tomcat(servidor):
    return controlar_servicio_tomcat(servidor, 'start')

from .services_docker import controlar_docker
from .services_local import controlar_servicio_local_sistema, controlar_servicio_local_docker

def controlar_servicio_tomcat(servidor, accion):
    """
    Controla el servicio Tomcat (start, stop, restart).
    """
    if servidor.tipo_conexion == 'local':
        if servidor.tipo_instalacion == 'docker':
            return controlar_servicio_local_docker(servidor.nombre_servicio, accion)
        else:
            return controlar_servicio_local_sistema(servidor.nombre_servicio, accion)
            
    if servidor.tipo_instalacion == 'docker':
        return controlar_docker(servidor, accion)
        
    if servidor.tipo_conexion == 'winrm':
        return controlar_winrm(servidor, accion)
    elif servidor.tipo_conexion == 'ssh':
        return controlar_ssh(servidor, accion)
    else:
        return False, "Tipo de conexión no soportado."

def controlar_winrm(servidor, accion):
    # Mapeo de acciones a cmdlets de PowerShell
    cmds = {
        'start': 'Start-Service',
        'stop': 'Stop-Service',
        'restart': 'Restart-Service'
    }
    cmdlet = cmds.get(accion)
    
    # Start-Service no soporta -Force, lo removemos para ese caso
    force_param = "-Force" if accion != 'start' else ""
    
    port = servidor.puerto_conexion if servidor.puerto_conexion else 5985
    url = f"http://{servidor.ip_host}:{port}/wsman"
    try:
        session = winrm.Session(url, auth=(servidor.usuario, servidor.password), transport='ntlm')
        
        service_name = servidor.nombre_servicio
        
        # Script mejorado para manejar Start-Service y autodescubrimiento si falla
        if service_name:
            ps_script = f"""
            $ErrorActionPreference = "Stop"
            try {{
                $service = Get-Service -Name '{service_name}'
                {cmdlet} -InputObject $service {force_param}
                Write-Output "SUCCESS: Acción {accion} completada sobre {service_name}."
            }} catch {{
                Write-Error $_.Exception.Message
            }}
            """
        else:
            # Si no tenemos nombre, buscamos *Tomcat*
            ps_script = f"""
            $ErrorActionPreference = "Stop"
            try {{
                $services = Get-Service | Where-Object {{$_.Name -like '*Tomcat*'}}
                if ($services) {{
                    foreach ($svc in $services) {{
                        {cmdlet} -InputObject $svc {force_param}
                        Write-Output "SUCCESS: Acción {accion} completada sobre $($svc.Name)."
                    }}
                }} else {{
                    throw "No se encontró ningún servicio que contenga 'Tomcat'."
                }}
            }} catch {{
                Write-Error $_.Exception.Message
            }}
            """
            
        result = session.run_ps(ps_script)
        
        output = decode_winrm_output(result.std_out)
        error = decode_winrm_output(result.std_err)

        if result.status_code == 0 and "SUCCESS:" in output:
            return True, output.replace("SUCCESS: ", "")
        else:
            if not error and result.status_code == 0:
                 return True, f"Comando {accion} enviado (sin confirmación explícita)."
            return False, f"Error: {error or output or 'Desconocido'}"
            
    except Exception as e:
        return False, f"Fallo conexión WinRM (Puerto {port}): {str(e)}"

def controlar_ssh(servidor, accion):
    # Mapeo de acciones a comandos systemctl
    cmds = {
        'start': 'start',
        'stop': 'stop',
        'restart': 'restart'
    }
    systemctl_action = cmds.get(accion)

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        port = servidor.puerto_conexion if servidor.puerto_conexion else 22
        client.connect(servidor.ip_host, port=port, username=servidor.usuario, password=servidor.password, timeout=10)
        service_name = getattr(servidor, 'nombre_servicio', None)
        if service_name:
            full_cmd = f"sudo systemctl {systemctl_action} {service_name}"
        else:
            services = ['tomcat', 'tomcat9', 'tomcat10']
            cmd_parts = []
            for svc in services:
                cmd_parts.append(f"sudo systemctl {systemctl_action} {svc}")
            full_cmd = " || ".join(cmd_parts)
        
        stdin, stdout, stderr = client.exec_command(full_cmd)
        error = stderr.read().decode()
        
        client.close()
        
        if not error or "Unit not found" in error: 
             return True, f"Comando {accion} enviado (SSH)."
        else:
             return False, f"Error SSH: {error}"
            
    except Exception as e:
        return False, f"Fallo conexión SSH (Puerto {port}): {str(e)}"
