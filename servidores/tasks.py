import re

import paramiko
from celery import shared_task
from django.utils import timezone

from .models import Host
from .services import _connect_ssh


def _parse_cpu_top(output):
    if not output:
        return None
    line = output.strip().splitlines()[0]
    match = re.search(r'(\d+[\.,]?\d*)\s*us', line)
    if match:
        try:
            return float(match.group(1).replace(',', '.'))
        except ValueError:
            return None
    return None


def _parse_ram_free(output):
    if not output:
        return None
    lines = [l for l in output.splitlines() if l.lower().startswith('mem:')]
    if not lines:
        return None
    parts = lines[0].split()
    if len(parts) < 3:
        return None
    try:
        total = float(parts[1])
        used = float(parts[2])
    except ValueError:
        return None
    return used, total


@shared_task
def monitor_host(host_id):
    host = Host.objects.filter(pk=host_id).first()
    if not host:
        return {'ok': False, 'reason': 'host_not_found'}
    if host.tipo_conexion != 'ssh':
        return {'ok': False, 'reason': 'not_ssh'}
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        port = host.puerto_conexion or 22
        _connect_ssh(client, host.ip_host, port, host.usuario, host.password)
    except Exception:
        return {'ok': False, 'reason': 'ssh_failed'}
    cpu_cmd = 'COLUMNS=512 top -bn1 | grep "Cpu(s)" || echo ""'
    ram_cmd = 'free -m || echo ""'
    node_cmd = 'pgrep -f node || true'
    tomcat_cmd = 'pgrep -f tomcat || true'
    stdin, stdout, stderr = client.exec_command(cpu_cmd)
    cpu_out = stdout.read().decode(errors='ignore')
    stdin, stdout, stderr = client.exec_command(ram_cmd)
    ram_out = stdout.read().decode(errors='ignore')
    stdin, stdout, stderr = client.exec_command(node_cmd)
    node_out = stdout.read().decode(errors='ignore').strip()
    stdin, stdout, stderr = client.exec_command(tomcat_cmd)
    tomcat_out = stdout.read().decode(errors='ignore').strip()
    cpu_val = _parse_cpu_top(cpu_out)
    ram_vals = _parse_ram_free(ram_out)
    last_cpu = cpu_val if cpu_val is not None else None
    last_ram = None
    if ram_vals is not None:
        used_mb, total_mb = ram_vals
        last_ram = used_mb
    online = True
    if not cpu_val and not ram_vals:
        online = False
    if online:
        if not node_out and not tomcat_out:
            online = False
    client.close()
    return {
        'ok': online,
        'cpu': last_cpu,
        'ram_used': last_ram,
        'ram_total': total_mb if ram_vals is not None else None,
        'node_pids': node_out,
        'tomcat_pids': tomcat_out,
    }
