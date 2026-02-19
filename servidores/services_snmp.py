import asyncio
from pysnmp.hlapi.v3arch.asyncio import *

async def _snmp_get_async(ip, community, oid, port=161):
    """
    Versión asíncrona interna de SNMP GET.
    """
    print(f"DEBUG: _snmp_get_async start for {oid}", flush=True)
    try:
        # Timeout aumentado a 5s y 3 retries para mayor robustez (igual que diag_snmp.py)
        transport_target = await UdpTransportTarget.create((ip, port), timeout=5, retries=3)
        print("DEBUG: Transport created", flush=True)
        result = await get_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1), # SNMPv2c
            transport_target,
            ContextData(),
            ObjectType(ObjectIdentity(oid))
        )
        print("DEBUG: get_cmd finished", flush=True)
        
        errorIndication, errorStatus, errorIndex, varBinds = result

        if errorIndication:
            return None, str(errorIndication)
        elif errorStatus:
            return None, errorStatus.prettyPrint()
        else:
            for varBind in varBinds:
                # Devuelve el valor casteado a string o entero según corresponda
                val = varBind[1]
                try:
                    return int(val), None
                except (ValueError, TypeError):
                    return str(val), None
        return None, "No data"
    except Exception as e:
        return None, str(e)

async def _snmp_walk_async(ip, community, oid, port=161):
    """
    Versión asíncrona interna de SNMP WALK.
    """
    try:
        valores = []
        # Timeout aumentado a 5s y 3 retries
        transport_target = await UdpTransportTarget.create((ip, port), timeout=5, retries=3)
        async for errorIndication, errorStatus, errorIndex, varBinds in walk_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            transport_target,
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
            lexicographicMode=False
        ):
            if errorIndication:
                break
            elif errorStatus:
                break
            else:
                for varBind in varBinds:
                    val = varBind[1]
                    try:
                        valores.append(int(val))
                    except (ValueError, TypeError):
                        valores.append(str(val))
        return valores, None
    except Exception as e:
        return None, str(e)

async def _consultar_metricas_async(servidor):
    """
    Obtiene todas las métricas en paralelo.
    """
    ip = servidor.ip_host
    community = servidor.snmp_community
    port = servidor.snmp_port
    
    datos = {
        'cpu_load': 0,
        'ram_total': 0,
        'ram_used': 0,
        'uptime': '',
        'sys_descr': '',
        'error': None
    }

    # 1. System Description (Check de conectividad inicial)
    # Hacemos este primero y solo, para fallar rápido si no hay conexión
    try:
        desc, err = await _snmp_get_async(ip, community, '1.3.6.1.2.1.1.1.0', port)
        if err:
            # Si hay error explícito de SNMP, lanzamos excepción
            raise Exception(err)
        datos['sys_descr'] = desc
    except Exception as e:
        # Si falla el GET inicial, relanzamos para activar DEMO
        # PERO, si el error es de timeout (que es lo que pasa cuando no hay servicio),
        # queremos que se note.
        raise Exception(f"Fallo conexión inicial ({ip}:{port}): {str(e)}")

    # 2. Consultas paralelas para el resto
    # OIDs: Uptime, CPU Load, RAM Total, RAM Avail (Linux)
    task_uptime = _snmp_get_async(ip, community, '1.3.6.1.2.1.1.3.0', port)
    task_cpu = _snmp_walk_async(ip, community, '1.3.6.1.2.1.25.3.3.1.2', port)
    task_ram_total = _snmp_get_async(ip, community, '1.3.6.1.2.1.25.2.2.0', port)
    task_ram_avail = _snmp_get_async(ip, community, '1.3.6.1.4.1.2021.4.6.0', port)

    results = await asyncio.gather(task_uptime, task_cpu, task_ram_total, task_ram_avail)
    
    # Procesar Uptime
    uptime_val, _ = results[0]
    if isinstance(uptime_val, int):
        seconds = uptime_val / 100
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        datos['uptime'] = f"{days}d {hours}h {minutes}m"

    # Procesar CPU
    cpu_vals, _ = results[1]
    if cpu_vals:
        loads_int = [x for x in cpu_vals if isinstance(x, int)]
        if loads_int:
            datos['cpu_load'] = sum(loads_int) / len(loads_int)

    # Procesar RAM
    ram_total_kb, _ = results[2]
    ram_avail_kb, _ = results[3]

    if isinstance(ram_total_kb, int):
        datos['ram_total'] = ram_total_kb / 1024 # MB
        
        if isinstance(ram_avail_kb, int):
            datos['ram_used'] = (ram_total_kb - ram_avail_kb) / 1024

    return datos

def consultar_metricas_snmp(servidor):
    """
    Wrapper que invoca un script externo para evitar conflictos Asyncio/Django en Windows.
    """
    import subprocess
    import json
    import sys
    import os
    
    script_path = os.path.join(os.path.dirname(__file__), 'snmp_worker.py')
    cmd = [sys.executable, script_path, servidor.ip_host, servidor.snmp_community, str(servidor.snmp_port)]
    
    print(f"\n--- INICIANDO CONSULTA SNMP A {servidor.ip_host}:{servidor.snmp_port} via WORKER ---")
    
    try:
        # Ejecutamos el script externo con timeout de 10s
        output = subprocess.check_output(cmd, timeout=10, stderr=subprocess.STDOUT)
        resultado_real = json.loads(output)
        
        # Verificar errores retornados por el worker
        if resultado_real.get('error'):
             raise Exception(resultado_real.get('error'))
             
        # Si la lógica interna devolvió sys_descr válido, es un éxito.
        if not resultado_real.get('sys_descr') or 'Error' in str(resultado_real.get('sys_descr', '')):
             raise Exception("Datos vacíos o error en descripción")
             
        print(f"--- ÉXITO CONSULTA SNMP WORKER: {resultado_real} ---")
        return resultado_real

    except Exception as e:
        # FALLBACK: Si falla la conexión, devolvemos datos DEMO
        print(f"--- EXCEPCIÓN SNMP WORKER ({e}). Activando modo DEMO. ---")
        import random
        return {
            'cpu_load': random.randint(10, 90), 
            'ram_total': 16384, 
            'ram_used': random.randint(4096, 12000), 
            'uptime': '0d 0h 0m (Simulado)', 
            'sys_descr': 'Servidor de Prueba (Simulación)', 
            'error': None, 
            'error_real': str(e),
            'is_demo': True
        }

# Helpers antiguos exportados para compatibilidad si fuera necesario, 
# pero idealmente usar consultar_metricas_snmp
def snmp_get(ip, community, oid, port=161):
    return asyncio.run(_snmp_get_async(ip, community, oid, port))

def snmp_walk(ip, community, oid, port=161):
    return asyncio.run(_snmp_walk_async(ip, community, oid, port))
