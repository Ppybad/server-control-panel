import winrm
import paramiko
from django.utils import timezone
import socket
import logging
import os
import traceback

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
from .services_local import verificar_estado_local_sistema, verificar_estado_local_docker, obtener_puerto_publico_local
import json
import re


def _verificar_estado(servidor):
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
            port_ok = check_tcp_port(servidor.ip_host, servidor.puerto_tomcat)
            
            if not port_ok:
                corregido = False
                if servidor.tipo_conexion == 'local' and servidor.tipo_instalacion == 'docker':
                    nuevo_puerto, err_p = obtener_puerto_publico_local(servidor.nombre_servicio)
                    if nuevo_puerto and nuevo_puerto != servidor.puerto_tomcat:
                        if check_tcp_port(servidor.ip_host, nuevo_puerto):
                            mensaje += f" [Puerto actualizado de {servidor.puerto_tomcat} a {nuevo_puerto}]"
                            servidor.puerto_tomcat = nuevo_puerto
                            port_ok = True
                            corregido = True
                if not port_ok and servidor.tipo_conexion == 'winrm' and servidor.nombre_servicio:
                    p = discover_port_by_service_winrm(servidor.ip_host, servidor.puerto_conexion or 5985, servidor.usuario, servidor.password, servidor.nombre_servicio)
                    if p and p != servidor.puerto_tomcat and check_tcp_port(servidor.ip_host, p):
                        servidor.puerto_tomcat = p
                        port_ok = True
                        corregido = True
                if not port_ok and servidor.tipo_conexion == 'ssh' and servidor.nombre_servicio:
                    p = discover_port_by_service_ssh(servidor.ip_host, servidor.puerto_conexion or 22, servidor.usuario, servidor.password, servidor.nombre_servicio)
                    if p and p != servidor.puerto_tomcat and check_tcp_port(servidor.ip_host, p):
                        servidor.puerto_tomcat = p
                        port_ok = True
                        corregido = True
                
                if not port_ok:
                    estado = "Alerta"
                    mensaje = f"Servicio activo, pero puerto {servidor.puerto_tomcat} inalcanzable (cerrado o bloqueado)."
                else:
                    mensaje += f" Puerto {servidor.puerto_tomcat} OK."
            else:
                mensaje += f" Puerto {servidor.puerto_tomcat} OK."
            
    except Exception as e:
            mensaje = str(e)

    return estado, mensaje


def verificar_estado_servidor(servidor):
    estado, mensaje = _verificar_estado(servidor)
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
        _connect_ssh(client, servidor.ip_host, port, servidor.usuario, servidor.password)
        
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
        if not IN_DOCKER:
            traceback.print_exc()
        return "Error", f"Fallo conexión SSH (Puerto {port}): {str(e)}"


def scan_winrm_tomcat(ip, port, user, password):
    url = f"http://{ip}:{port or 5985}/wsman"
    try:
        session = winrm.Session(url, auth=(user, password), transport='ntlm')
        # Un solo script que devuelve servicios Tomcat con PID y puertos en JSON
        ps = r"""
        $services = Get-WmiObject Win32_Service | Where-Object { $_.Name -like '*Tomcat*' -or $_.DisplayName -like '*Tomcat*' }
        $results = @()
        foreach ($svc in $services) {
            $pid = $svc.ProcessId
            $ports = @()
            if ($pid -ne 0) {
                try {
                    $ports = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -eq $pid } | Select-Object -ExpandProperty LocalPort
                } catch {}
            }
            $results += [PSCustomObject]@{
                Name = $svc.Name
                DisplayName = $svc.DisplayName
                Status = $svc.State
                Pid = $pid
                Ports = $ports | Sort-Object -Unique
            }
        }
        $results | ConvertTo-Json
        """
        res = session.run_ps(ps)
        if res.status_code != 0:
            err = decode_winrm_output(res.std_err)
            return [], f"WinRM error: {err}"
        txt = decode_winrm_output(res.std_out)
        items = []
        if not txt:
            return items, None
        try:
            data = json.loads(txt)
            if isinstance(data, dict):
                data = [data]
            prefer = [8080, 8181, 8081, 80, 8888, 8000, 3000, 5000]
            for svc in data:
                ports = []
                try:
                    ports = svc.get('Ports') or []
                    if isinstance(ports, str):
                        # a veces viene como string "8080 8009"
                        ports = [int(p) for p in ports.split() if p.isdigit()]
                except Exception:
                    ports = []
                chosen = None
                for cand in prefer:
                    if cand in ports:
                        chosen = cand
                        break
                if not chosen and ports:
                    try:
                        chosen = int(ports[0])
                    except Exception:
                        chosen = None
                items.append({
                    'nombre': svc.get('Name'),
                    'display': svc.get('DisplayName') or svc.get('Name'),
                    'estado': 'Activo' if str(svc.get('Status', '')).lower() in ['running', '4', 'running '] else 'Detenido',
                    'tipo': 'servicio',
                    'puerto': chosen or 8080,
                    'tipo_instalacion': 'sistema',
                })
        except Exception:
            pass
        return items, None
    except Exception as e:
        return [], str(e)


def scan_ssh_tomcat(ip, port, user, password):
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        _connect_ssh(client, ip, port or 22, user, password)
        names = ['tomcat', 'tomcat9', 'tomcat10']
        items = []
        for name in names:
            cmd = f"systemctl is-active {name}"
            stdin, stdout, stderr = client.exec_command(cmd)
            status = stdout.read().decode().strip()
            if status in ['active', 'inactive', 'failed', 'activating', 'deactivating']:
                # Intentar detectar puertos abiertos por procesos java para priorizar
                stdin2, stdout2, stderr2 = client.exec_command("ss -ltnp | grep java || netstat -ltnp | grep java")
                out2 = stdout2.read().decode()
                ports = [int(p) for p in re.findall(r':(\d+)\s', out2)]
                prefer = [8080, 8181, 8081, 80, 8888, 8000, 3000, 5000]
                chosen = None
                for cand in prefer:
                    if cand in ports:
                        chosen = cand
                        break
                if not chosen and ports:
                    chosen = ports[0]
                items.append({
                    'nombre': name,
                    'display': name,
                    'estado': 'Activo' if status == 'active' else 'Detenido',
                    'tipo': 'servicio',
                    'puerto': chosen or 8080,
                    'tipo_instalacion': 'sistema',
                })
        if not items:
            stdin, stdout, stderr = client.exec_command("ps aux | grep [t]omcat")
            output = stdout.read().decode()
            if output:
                stdin2, stdout2, stderr2 = client.exec_command("ss -ltnp | grep java || netstat -ltnp | grep java")
                out2 = stdout2.read().decode()
                ports = [int(p) for p in re.findall(r':(\d+)\s', out2)]
                prefer = [8080, 8181, 8081, 80, 8888, 8000, 3000, 5000]
                chosen = None
                for cand in prefer:
                    if cand in ports:
                        chosen = cand
                        break
                if not chosen and ports:
                    chosen = ports[0]
                items.append({
                    'nombre': 'tomcat-proceso',
                    'display': 'Proceso Tomcat',
                    'estado': 'Activo',
                    'tipo': 'proceso',
                    'puerto': chosen or 8080,
                    'tipo_instalacion': 'sistema',
                })
        client.close()
        return items, None
    except Exception as e:
        if not IN_DOCKER:
            traceback.print_exc()
        return [], str(e)


def scan_winrm_node(ip, port, user, password):
    url = f"http://{ip}:{port or 5985}/wsman"
    try:
        session = winrm.Session(url, auth=(user, password), transport='ntlm')
        # 1) Servicios Windows cuyo ejecutable apunte a node.exe
        # 2) Procesos node.exe con sus puertos asociados y datos de proceso
        ps = r"""
$svcNode = Get-WmiObject Win32_Service | Where-Object { $_.PathName -like '*node.exe*' -or $_.Name -like '*node*' -or $_.DisplayName -like '*node*' -or $_.Name -like '*ISSET*' -or $_.DisplayName -like '*ISSET*' -or $_.Name -like '*SIPEM*' -or $_.DisplayName -like '*SIPEM*' }
$procNode = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' }
$svcAll = Get-WmiObject Win32_Service
$svcIndexByPid = @{}
foreach ($svc in $svcAll) {
    if ($svc.ProcessId -ne 0) { $svcIndexByPid[$svc.ProcessId] = $svc }
}
$listens = @{}
try {
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        $pid = $_.OwningProcess
        if ($pid -ne 0) {
            if (-not $listens.ContainsKey($pid)) { $listens[$pid] = @() }
            $listens[$pid] += $_.LocalPort
        }
    }
} catch {}
$results = @()
$procIndex = @{}
foreach ($p in $procNode) { $procIndex[$p.ProcessId] = $p }
foreach ($svc in $svcNode) {
    $pid = $svc.ProcessId
    $ports = @()
    if ($pid -ne 0 -and $listens.ContainsKey($pid)) {
        $ports = $listens[$pid] | Sort-Object -Unique
    }
    $cmd = $null
    $ppid = 0
    if ($pid -ne 0 -and $procIndex.ContainsKey($pid)) {
        $cmd = $procIndex[$pid].CommandLine
        $ppid = $procIndex[$pid].ParentProcessId
    }
    $results += [PSCustomObject]@{
        Kind = 'windows_service'
        Name = $svc.Name
        Display = $svc.DisplayName
        Status = $svc.State
        Pid = $pid
        Ports = $ports
        Cmd = $cmd
        Path = $svc.PathName
        ParentPid = $ppid
    }
}
foreach ($p in $procNode) {
    $pid = $p.ProcessId
    $ports = @()
    if ($listens.ContainsKey($pid)) { $ports = $listens[$pid] | Sort-Object -Unique }
    $parentSvcName = $null
    $parentSvcDisplay = $null
    if ($svcIndexByPid.ContainsKey($p.ParentProcessId)) {
        $parentSvcName = $svcIndexByPid[$p.ParentProcessId].Name
        $parentSvcDisplay = $svcIndexByPid[$p.ParentProcessId].DisplayName
    }
    $results += [PSCustomObject]@{
        Kind = 'raw_process'
        Name = "PID:$pid"
        Display = $p.Name
        Status = 'Running'
        Pid = $pid
        Ports = $ports
        Cmd = $p.CommandLine
        Path = $null
        ParentPid = $p.ParentProcessId
        ParentServiceName = $parentSvcName
        ParentServiceDisplay = $parentSvcDisplay
    }
}
$results | ConvertTo-Json
        """
        res = session.run_ps(ps)
        if res.status_code != 0:
            err = decode_winrm_output(res.std_err)
            return [], f"WinRM error: {err}"
        txt = decode_winrm_output(res.std_out)
        if not txt:
            return [], None
        items = []
        try:
            data = json.loads(txt)
            if isinstance(data, dict):
                data = [data]
            prefer = [4000, 9005, 9007, 3000, 8080, 8000, 5000, 80, 8888]
            # Indexamos por PID para deduplicar y poder analizar padre/hijo
            by_pid = {}
            others = []
            for row in data:
                pid = 0
                try:
                    pid = int(row.get('Pid') or row.get('PID') or 0)
                except Exception:
                    pid = 0
                ports = []
                try:
                    ports = row.get('Ports') or []
                    if isinstance(ports, str):
                        ports = [int(p) for p in ports.split() if str(p).isdigit()]
                except Exception:
                    ports = []
                kind = (row.get('Kind') or '').lower()
                cmd = (row.get('Cmd') or '') if isinstance(row.get('Cmd'), str) else ''
                path = (row.get('Path') or '') if isinstance(row.get('Path'), str) else ''
                status = row.get('Status') or ''
                name = row.get('Name')
                display_raw = row.get('Display') or name or 'Node'
                parent_service_name = row.get('ParentServiceName')
                parent_service_display = row.get('ParentServiceDisplay')
                parent_pid = None
                try:
                    parent_pid = int(row.get('ParentPid')) if row.get('ParentPid') is not None else None
                except Exception:
                    parent_pid = None
                if pid <= 0:
                    others.append((row, ports, kind, cmd, path, status, display_raw))
                    continue
                info = by_pid.get(pid)
                if not info:
                    info = {
                        'pid': pid,
                        'ports': set(),
                        'cmd': '',
                        'path': '',
                        'status': status,
                        'service_names': set(),
                        'kinds': set(),
                        'displays': [],
                        'parent_pid': parent_pid,
                        'name': name,
                    }
                    by_pid[pid] = info
                info['ports'].update(int(p) for p in ports if isinstance(p, int))
                if cmd:
                    info['cmd'] = cmd
                if path:
                    info['path'] = path
                if status:
                    info['status'] = status
                if parent_pid is not None:
                    info['parent_pid'] = parent_pid
                if kind:
                    info['kinds'].add(kind)
                if name:
                    info['name'] = name
                if display_raw:
                    info['displays'].append(display_raw)
                if parent_service_name:
                    info['service_names'].add(parent_service_name)
                    if parent_service_display:
                        info['displays'].append(parent_service_display)
                if kind == 'windows_service' and name:
                    info['service_names'].add(name)

            hidden_pids = set()
            for pid, info in by_pid.items():
                parent_pid = info.get('parent_pid')
                if parent_pid and parent_pid in by_pid:
                    has_ports = bool(info['ports'])
                    parent_has_ports = bool(by_pid[parent_pid]['ports'])
                    if not has_ports and parent_has_ports:
                        hidden_pids.add(pid)
                    elif has_ports and not parent_has_ports:
                        hidden_pids.add(parent_pid)

            for pid, info in list(by_pid.items()):
                try:
                    low_cmd = ((info.get('cmd') or '') + ' ' + (info.get('path') or '')).lower()
                except Exception:
                    low_cmd = ''
                if ('npm ' in low_cmd or ' npx ' in low_cmd or 'npm-cli.js' in low_cmd) and not info['ports']:
                    hidden_pids.add(pid)

            def clasificar_rol(cmd_text, path_text, has_ports):
                base = (cmd_text or '') + ' ' + (path_text or '')
                low = base.lower()
                if has_ports:
                    if 'next-server' in low or 'nuxt' in low or 'dist/main.js' in low:
                        return 'web'
                    return 'api'
                return 'worker'

            for pid, info in by_pid.items():
                if pid in hidden_pids:
                    continue
                try:
                    debug_cmd = (info.get('cmd') or '')
                    script_match = re.search(r'([^\\\/]+\.(js|ts|mjs))', debug_cmd)
                    script_name = script_match.group(1) if script_match else ''
                    debug_cmd_short = debug_cmd[:160]
                    debug_ports = sorted(info['ports'])
                    print(f"[NODE_WINRM_SCAN] PID={pid} PORTS={debug_ports} SCRIPT={script_name} CMD={debug_cmd_short}")
                except Exception:
                    pass
                ports = sorted(info['ports'])
                chosen = None
                for cand in prefer:
                    if cand in ports:
                        chosen = cand
                        break
                if not chosen and ports:
                    chosen = ports[0]
                kinds = info['kinds']
                service_names = info.get('service_names') or set()
                if 'windows_service' in kinds or service_names:
                    origen = 'servicio_windows'
                    tipo = 'servicio'
                    controlable = True
                else:
                    origen = 'proceso_pid'
                    tipo = 'proceso'
                    controlable = False
                display = info['displays'][0] if info['displays'] else (info['name'] or 'Node')
                try:
                    m = re.search(r'([\\\/])([^\\\/]+\.(js|ts|mjs))', info['cmd'] or info['path'] or '')
                    if m:
                        display = f"{display} ({m.group(2)})"
                except Exception:
                    pass
                targets = []
                if origen == 'servicio_windows' and service_names:
                    for svc_name in sorted(service_names):
                        targets.append(svc_name)
                else:
                    targets.append(info['name'] or f"PID:{pid}")
                rol = clasificar_rol(info['cmd'], info['path'], bool(ports))
                for nombre_val in targets:
                    items.append({
                        'nombre': nombre_val,
                        'display': f"[Node] {display}",
                        'estado': 'Activo' if str(info['status']).lower() in ['running','4','active'] else 'Detenido',
                        'tipo': tipo,
                        'puerto': chosen if origen == 'proceso_pid' else (chosen or 3000),
                        'tipo_instalacion': 'sistema',
                        'origen_node': origen,
                        'controlable_node': controlable,
                        'detalle_node': info['cmd'] or info['path'],
                        'rol_node': rol,
                    })

            # Entradas sin PID válido (caso raro), se procesan individualmente
            for row, ports, kind, cmd, path, status, display_raw in others:
                chosen = None
                for cand in prefer:
                    if cand in ports:
                        chosen = cand
                        break
                if not chosen and ports:
                    chosen = ports[0] if ports else None
                origen = 'desconocido'
                tipo = 'proceso'
                controlable = False
                if kind == 'windows_service':
                    origen = 'servicio_windows'
                    tipo = 'servicio'
                    controlable = True
                elif kind == 'raw_process':
                    origen = 'proceso_pid'
                    tipo = 'proceso'
                display = display_raw or 'Node'
                try:
                    m = re.search(r'([\\\/])([^\\\/]+\.(js|ts|mjs))', cmd or path or '')
                    if m:
                        display = f"{display} ({m.group(2)})"
                except Exception:
                    pass
                rol = clasificar_rol(cmd, path, bool(ports))
                items.append({
                    'nombre': row.get('Name'),
                    'display': f"[Node] {display}",
                    'estado': 'Activo' if str(status).lower() in ['running','4','active'] else 'Detenido',
                    'tipo': tipo,
                    'puerto': chosen if origen == 'proceso_pid' else (chosen or 3000),
                    'tipo_instalacion': 'sistema',
                    'origen_node': origen,
                    'controlable_node': controlable,
                    'detalle_node': cmd or path,
                    'rol_node': rol,
                })
        except Exception:
            pass
        return items, None
    except Exception as e:
        return [], str(e)


def scan_ssh_node(ip, port, user, password):
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        _connect_ssh(client, ip, port or 22, user, password)
        prefer = [4000, 9005, 9007, 3000, 8080, 8000, 5000, 80, 8888]
        rows = []
        # 1) pm2 (si existe)
        stdin, stdout, stderr = client.exec_command("pm2 jlist 2>/dev/null || true")
        j = stdout.read().decode().strip()
        if j:
            try:
                data = json.loads(j)
                if isinstance(data, dict):
                    data = [data]
                for p in data:
                    pm2_name = p.get('name') or 'pm2-app'
                    pid = int(p.get('pid') or 0)
                    ports = []
                    if pid > 0:
                        stdin2, stdout2, stderr2 = client.exec_command(f"ss -ltnp | grep 'pid {pid}' || ss -ltnp | grep {pid} || netstat -ltnp | grep {pid}")
                        out2 = stdout2.read().decode()
                        ports = [int(x) for x in re.findall(r':(\d+)\s', out2)]
                    chosen = None
                    for cand in prefer:
                        if cand in ports:
                            chosen = cand
                            break
                    if not chosen and ports:
                        chosen = ports[0]
                    try:
                        low_name = str(pm2_name).lower()
                        low_name = low_name or ''
                    except Exception:
                        low_name = ''
                    detalle = ''
                    try:
                        detalle = str(p.get('pm2_env', {}).get('pm_exec_path') or '')
                    except Exception:
                        detalle = ''
                    rows.append({
                        'kind': 'pm2',
                        'name': f'pm2:{pm2_name}',
                        'display': f'PM2 {pm2_name}',
                        'status': 'online' if p.get('pm2_env',{}).get('status') == 'online' else 'offline',
                        'pid': pid,
                        'ports': ports,
                        'cmd': detalle,
                        'path': '',
                        'parent_pid': None,
                        'origen_hint': 'pm2',
                    })
            except Exception:
                pass
        # 2) systemd services que parezcan node
        stdin, stdout, stderr = client.exec_command("systemctl list-units --type=service --all | grep -i node || true")
        out = stdout.read().decode()
        service_names = []
        for line in out.splitlines():
            tok = line.strip().split()
            if tok:
                name = tok[0] if tok[0].endswith('.service') else None
                if name:
                    service_names.append(name)
        for name in service_names[:10]:
            stdin, stdout, stderr = client.exec_command(f"systemctl is-active {name} || true")
            status = stdout.read().decode().strip()
            stdin, stdout, stderr = client.exec_command(f"systemctl show {name} -p MainPID --value || echo 0")
            pid_txt = stdout.read().decode().strip()
            pid = int(pid_txt) if pid_txt.isdigit() else 0
            cmd = ''
            try:
                stdin2, stdout2, stderr2 = client.exec_command(f"systemctl show {name} -p ExecStart --value || echo ''")
                cmd = stdout2.read().decode().strip()
            except Exception:
                cmd = ''
            ports = []
            if pid > 0:
                stdin2, stdout2, stderr2 = client.exec_command(f"ss -ltnp | grep 'pid {pid}' || ss -ltnp | grep {pid} || netstat -ltnp | grep {pid}")
                out2 = stdout2.read().decode()
                ports = [int(x) for x in re.findall(r':(\d+)\s', out2)]
            chosen = None
            for cand in prefer:
                if cand in ports:
                    chosen = cand
                    break
            if not chosen and ports:
                chosen = ports[0]
            rows.append({
                'kind': 'systemd_service',
                'name': name,
                'display': name,
                'status': status,
                'pid': pid,
                'ports': ports,
                'cmd': cmd,
                'path': '',
                'parent_pid': None,
                'origen_hint': 'systemd_service',
            })
        # 3) procesos node genéricos
        stdin, stdout, stderr = client.exec_command("ps aux | grep [n]ode")
        proc_out = stdout.read().decode()
        for line in proc_out.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                pid = int(parts[1])
            except Exception:
                continue
            cmd = ""
            if len(parts) > 10:
                cmd = " ".join(parts[10:])
            else:
                cmd = line
            stdin2, stdout2, stderr2 = client.exec_command(f"ss -ltnp | grep 'pid {pid}' || ss -ltnp | grep {pid} || netstat -ltnp | grep {pid}")
            out2 = stdout2.read().decode()
            ports = [int(x) for x in re.findall(r':(\d+)\s', out2)]
            rows.append({
                'kind': 'raw_process',
                'name': f'PID:{pid}',
                'display': f'Proceso Node (PID: {pid})',
                'status': 'Running',
                'pid': pid,
                'ports': ports,
                'cmd': cmd,
                'path': '',
                'parent_pid': None,
                'origen_hint': 'proceso_pid',
            })
        # Enriquecer con PPID para todos los PIDs conocidos
        pid_list = sorted({r['pid'] for r in rows if r.get('pid')})
        if pid_list:
            pid_arg = ",".join(str(p) for p in pid_list)
            stdin, stdout, stderr = client.exec_command(f"ps -o pid=,ppid= -p {pid_arg} || true")
            out_pp = stdout.read().decode()
            ppid_map = {}
            for line in out_pp.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                    ppid_map[int(parts[0])] = int(parts[1])
            for r in rows:
                pid = r.get('pid') or 0
                if pid in ppid_map:
                    r['parent_pid'] = ppid_map[pid]
        client.close()

        # Consolidación por PID (deduplicación, clasificación, padre/hijo)
        by_pid = {}
        others = []
        for r in rows:
            pid = int(r.get('pid') or 0)
            ports = r.get('ports') or []
            kind = (r.get('kind') or '').lower()
            cmd = r.get('cmd') or ''
            path = r.get('path') or ''
            status = r.get('status') or ''
            name = r.get('name')
            display_raw = r.get('display') or name or 'Node'
            parent_pid = r.get('parent_pid')
            origen_hint = r.get('origen_hint')
            if pid <= 0:
                others.append((r, ports, kind, cmd, path, status, display_raw, origen_hint))
                continue
            info = by_pid.get(pid)
            if not info:
                info = {
                    'pid': pid,
                    'ports': set(),
                    'cmd': '',
                    'path': '',
                    'status': status,
                    'service_names': set(),
                    'kinds': set(),
                    'displays': [],
                    'parent_pid': parent_pid,
                    'name': name,
                    'origen_hints': set(),
                }
                by_pid[pid] = info
            info['ports'].update(int(p) for p in ports if isinstance(p, int))
            if cmd:
                info['cmd'] = cmd
            if path:
                info['path'] = path
            if status:
                info['status'] = status
            if parent_pid is not None:
                info['parent_pid'] = parent_pid
            if kind:
                info['kinds'].add(kind)
            if name:
                info['name'] = name
            if display_raw:
                info['displays'].append(display_raw)
            if origen_hint:
                info['origen_hints'].add(origen_hint)
            if kind == 'systemd_service' and name:
                info['service_names'].add(name)

        hidden_pids = set()
        for pid, info in by_pid.items():
            parent_pid = info.get('parent_pid')
            if parent_pid and parent_pid in by_pid:
                has_ports = bool(info['ports'])
                parent_has_ports = bool(by_pid[parent_pid]['ports'])
                if not has_ports and parent_has_ports:
                    hidden_pids.add(pid)
                elif has_ports and not parent_has_ports:
                    hidden_pids.add(parent_pid)

        def clasificar_rol(cmd_text, path_text, has_ports):
            base = (cmd_text or '') + ' ' + (path_text or '')
            low = base.lower()
            if has_ports:
                if 'next-server' in low or 'nuxt' in low or 'dist/main.js' in low:
                    return 'web'
                return 'api'
            return 'worker'

        items = []
        for pid, info in by_pid.items():
            if pid in hidden_pids:
                continue
            ports = sorted(info['ports'])
            chosen = None
            for cand in prefer:
                if cand in ports:
                    chosen = cand
                    break
            if not chosen and ports:
                chosen = ports[0]
            kinds = info['kinds']
            origen_hints = info.get('origen_hints') or set()
            if 'systemd_service' in kinds or 'systemd_service' in origen_hints:
                origen = 'systemd_service'
                tipo = 'servicio'
                controlable = True
            elif 'pm2' in kinds or 'pm2' in origen_hints:
                origen = 'pm2'
                tipo = 'servicio'
                controlable = False
            else:
                origen = 'proceso_pid'
                tipo = 'proceso'
                controlable = False
            display = info['displays'][0] if info['displays'] else (info['name'] or 'Node')
            try:
                m = re.search(r'([\\\/])([^\\\/]+\.(js|ts|mjs))', info['cmd'] or info['path'] or '')
                if m:
                    display = f"{display} ({m.group(2)})"
            except Exception:
                pass
            rol = clasificar_rol(info['cmd'], info['path'], bool(ports))
            items.append({
                'nombre': info['name'] or f"PID:{pid}",
                'display': f"[Node] {display}",
                'estado': 'Activo' if str(info['status']).lower() in ['running','4','active'] else 'Detenido',
                'tipo': tipo,
                'puerto': chosen if origen == 'proceso_pid' else (chosen or 3000),
                'tipo_instalacion': 'sistema',
                'origen_node': origen,
                'controlable_node': controlable,
                'detalle_node': info['cmd'] or info['path'],
                'rol_node': rol,
            })

        for r, ports, kind, cmd, path, status, display_raw, origen_hint in others:
            chosen = None
            for cand in prefer:
                if cand in ports:
                    chosen = cand
                    break
            if not chosen and ports:
                chosen = ports[0] if ports else None
            origen = 'desconocido'
            tipo = 'proceso'
            controlable = False
            if kind == 'systemd_service':
                origen = 'systemd_service'
                tipo = 'servicio'
                controlable = True
            elif kind == 'pm2':
                origen = 'pm2'
                tipo = 'servicio'
            elif kind == 'raw_process':
                origen = 'proceso_pid'
                tipo = 'proceso'
            display = display_raw or 'Node'
            try:
                m = re.search(r'([\\\/])([^\\\/]+\.(js|ts|mjs))', cmd or path or '')
                if m:
                    display = f"{display} ({m.group(2)})"
            except Exception:
                pass
            rol = clasificar_rol(cmd, path, bool(ports))
            items.append({
                'nombre': r.get('name'),
                'display': f"[Node] {display}",
                'estado': 'Activo' if str(status).lower() in ['running','4','active'] else 'Detenido',
                'tipo': tipo,
                'puerto': chosen if origen == 'proceso_pid' else (chosen or 3000),
                'tipo_instalacion': 'sistema',
                'origen_node': origen,
                'controlable_node': controlable,
                'detalle_node': cmd or path,
                'rol_node': rol,
            })
        return items, None
    except Exception as e:
        if not IN_DOCKER:
            traceback.print_exc()
        return [], str(e)

def discover_port_by_service_winrm(ip, port, user, password, service_name):
    try:
        url = f"http://{ip}:{port or 5985}/wsman"
        session = winrm.Session(url, auth=(user, password), transport='ntlm')
        ps = f"""
        $svc = Get-WmiObject Win32_Service -Filter "Name='{service_name}'"
        if ($svc) {{
            $pid = $svc.ProcessId
            if ($pid -ne 0) {{
                Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object {{ $_.OwningProcess -eq $pid }} | Select-Object -ExpandProperty LocalPort
            }}
        }}
        """
        res = session.run_ps(ps)
        out = decode_winrm_output(res.std_out)
        ports = []
        for token in out.replace('\r','\n').split('\n'):
            token = token.strip()
            if token.isdigit():
                ports.append(int(token))
        prefer = [8080, 8181, 8081, 80, 8888, 8000, 3000, 5000]
        for cand in prefer:
            if cand in ports:
                return cand
        if ports:
            return ports[0]
        return None
    except Exception:
        return None


def discover_port_by_service_ssh(ip, port, user, password, service_name):
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        _connect_ssh(client, ip, port or 22, user, password)
        cmd = f"systemctl show {service_name} -p MainPID --value || echo 0"
        stdin, stdout, stderr = client.exec_command(cmd)
        pid_txt = stdout.read().decode().strip()
        pid = int(pid_txt) if pid_txt.isdigit() else 0
        ports = []
        if pid > 0:
            stdin2, stdout2, stderr2 = client.exec_command(f"ss -ltnp | grep 'pid {pid}' || ss -ltnp | grep {pid} || netstat -ltnp | grep {pid}")
            out2 = stdout2.read().decode()
            ports = [int(p) for p in re.findall(r':(\d+)\s', out2)]
        client.close()
        prefer = [8080, 8181, 8081, 80, 8888, 8000, 3000, 5000]
        for cand in prefer:
            if cand in ports:
                return cand
        if ports:
            return ports[0]
        return None
    except Exception:
        return None
