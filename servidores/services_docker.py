import paramiko
import logging
import os
import traceback

IN_DOCKER = os.path.exists('/.dockerenv')


def _resolve_ssh_host(ip):
    if IN_DOCKER and ip in ['127.0.0.1', 'localhost']:
        return 'host.docker.internal'
    return ip


def _connect_ssh(client, ip, port, user, password):
    target_ip = _resolve_ssh_host(ip)
    logging.getLogger("paramiko").setLevel(logging.DEBUG)
    kwargs = {
        'hostname': target_ip,
        'port': port or 22,
        'username': user,
        'password': password,
        'timeout': 10,
        'banner_timeout': 20,
    }
    if IN_DOCKER:
        kwargs['allow_agent'] = False
        kwargs['look_for_keys'] = False
    client.connect(**kwargs)


def listar_contenedores_docker(ip, port, user, password):
    """
    Conecta por SSH y ejecuta 'docker ps' para obtener la lista de contenedores.
    Retorna una lista de diccionarios con info de cada contenedor.
    """
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        real_port = port if port else 22
        _connect_ssh(client, ip, real_port, user, password)
        
        # Opción 1: Pasar password a sudo vía stdin de forma segura
        # Usamos -a para listar TODOS los contenedores (incluidos los detenidos)
        cmd = "sudo -S docker ps -a --format '{{.ID}}|{{.Names}}|{{.Status}}|{{.Image}}'"
        
        stdin, stdout, stderr = client.exec_command(cmd)
        stdin.write(password + '\n')
        stdin.flush()
        
        # Sudo -S puede escribir el prompt de password en stderr, así que filtramos eso
        output = stdout.read().decode()
        error = stderr.read().decode()
        
        # Limpiar mensaje de sudo del error
        if "[sudo] password for" in error:
            error = error.replace(f"[sudo] password for {user}:", "").strip()

        client.close()
        
        if error and not output:
             # Si aún hay error real (no solo el prompt)
            return None, f"Error Docker: {error}"
            
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
        if not IN_DOCKER:
            traceback.print_exc()
        return None, f"Error conexión SSH: {str(e)}"

def controlar_docker(servidor, accion):
    """
    Controla un contenedor Docker (start/stop/restart).
    Usa el campo 'nombre_servicio' del servidor como el ID o nombre del contenedor.
    """
    # Mapeo de acciones
    cmds = {
        'start': 'start',
        'stop': 'stop',
        'restart': 'restart'
    }
    docker_action = cmds.get(accion)
    
    container_name = servidor.nombre_servicio
    if not container_name:
        return False, "Error: No se ha especificado el nombre del contenedor (nombre_servicio)."

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        port = servidor.puerto_conexion if servidor.puerto_conexion else 22
        _connect_ssh(client, servidor.ip_host, port, servidor.usuario, servidor.password)
        
        # Usar sudo -S para pasar password
        full_cmd = f"sudo -S docker {docker_action} {container_name}"
        
        stdin, stdout, stderr = client.exec_command(full_cmd)
        stdin.write(servidor.password + '\n')
        stdin.flush()
        
        # Leer salida y error
        error = stderr.read().decode()
        
        # Limpiar mensaje de sudo del error
        if "[sudo] password for" in error:
            error = error.replace(f"[sudo] password for {servidor.usuario}:", "").strip()
        
        client.close()
        
        if not error:
             return True, f"Contenedor {container_name} {docker_action}do correctamente."
        else:
             return False, f"Error Docker: {error}"
            
    except Exception as e:
        if not IN_DOCKER:
            traceback.print_exc()
        return False, f"Fallo conexión SSH (Puerto {port}): {str(e)}"

def verificar_estado_docker(servidor):
    """
    Verifica si un contenedor está corriendo.
    """
    container_name = servidor.nombre_servicio
    if not container_name:
        return "Desconocido", "Sin nombre de contenedor"

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        port = servidor.puerto_conexion if servidor.puerto_conexion else 22
        _connect_ssh(client, servidor.ip_host, port, servidor.usuario, servidor.password)
        
        # Check if running con sudo -S
        # Usamos -a para detectar si existe pero está detenido
        cmd = f"sudo -S docker ps -a --filter 'name={container_name}' --format '{{{{.Status}}}}'"
        
        stdin, stdout, stderr = client.exec_command(cmd)
        stdin.write(servidor.password + '\n')
        stdin.flush()
        
        output = stdout.read().decode().strip()
        client.close()
        
        if output and "Up" in output:
            return "Activo", f"Contenedor {container_name} en ejecución ({output})"
        elif output:
            return "Detenido", f"Contenedor detenido ({output})"
        else:
            return "Error", "Contenedor no encontrado"
            
    except Exception as e:
        if not IN_DOCKER:
            traceback.print_exc()
        return "Error", f"Fallo verificación: {str(e)}"
