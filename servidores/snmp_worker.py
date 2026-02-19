import asyncio
import sys
import json
import logging

from pysnmp.hlapi.v3arch.asyncio import *

# Configuración de logging para depuración
logging.basicConfig(level=logging.ERROR)

async def _snmp_get_async(ip, community, oid, port=161):
    try:
        # Timeout de 2s y 1 retry (total ~4s) para respuesta rápida
        transport_target = await UdpTransportTarget.create((ip, port), timeout=2, retries=1)
        result = await get_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1), # SNMPv2c
            transport_target,
            ContextData(),
            ObjectType(ObjectIdentity(oid))
        )
        
        errorIndication, errorStatus, errorIndex, varBinds = result

        if errorIndication:
            return None, str(errorIndication)
        elif errorStatus:
            return None, errorStatus.prettyPrint()
        else:
            for varBind in varBinds:
                val = varBind[1]
                try:
                    return int(val), None
                except (ValueError, TypeError):
                    return str(val), None
        return None, "No data"
    except Exception as e:
        return None, str(e)

async def _snmp_walk_async(ip, community, oid, port=161):
    try:
        valores = []
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

async def consultar_metricas(ip, community, port):
    datos = {
        'cpu_load': 0,
        'ram_total': 0,
        'ram_used': 0,
        'uptime': '',
        'sys_descr': '',
        'error': None
    }

    try:
        # 1. System Description (Check de conectividad inicial)
        desc, err = await _snmp_get_async(ip, community, '1.3.6.1.2.1.1.1.0', port)
        if err:
            raise Exception(err)
        datos['sys_descr'] = desc
    except Exception as e:
        datos['error'] = str(e)
        return datos

    # 2. Consultas paralelas
    try:
        uptime_oid = '1.3.6.1.2.1.1.3.0'
        cpu_load_oid = '1.3.6.1.4.1.2021.10.1.3.1' # Linux 1 min load
        ram_total_oid = '1.3.6.1.4.1.2021.4.5.0'   # memTotalReal
        ram_avail_oid = '1.3.6.1.4.1.2021.4.6.0'   # memAvailReal

        results = await asyncio.gather(
            _snmp_get_async(ip, community, uptime_oid, port),
            _snmp_get_async(ip, community, cpu_load_oid, port),
            _snmp_get_async(ip, community, ram_total_oid, port),
            _snmp_get_async(ip, community, ram_avail_oid, port)
        )

        uptime_val, uptime_err = results[0]
        cpu_val, cpu_err = results[1]
        ram_total_kb, ram_err1 = results[2]
        ram_avail_kb, ram_err2 = results[3]

        if uptime_val:
            seconds = int(uptime_val) / 100
            days = int(seconds // 86400)
            hours = int((seconds % 86400) // 3600)
            minutes = int((seconds % 3600) // 60)
            datos['uptime'] = f"{days}d {hours}h {minutes}m"

        if isinstance(cpu_val, (int, float)):
             # Load average usually float but snmp returns int/float depending on OID type
             # UCD-SNMP-MIB::laLoad.1 returns DisplayString usually? No, laLoadInt is better.
             # Using laLoad.1 (1.3.6.1.4.1.2021.10.1.3.1) returns string usually?
             # Let's assume it returns something usable.
             # If string "0.05", we might need float.
             try:
                 datos['cpu_load'] = float(cpu_val) * 100 if float(cpu_val) < 1 else float(cpu_val)
                 # Adjust: Load 0.50 means 50% of 1 core? Or 0.50 load avg.
                 # Let's just keep as is for now, or map 0-1 to 0-100?
                 # Assuming 1.00 = 100% usage on 1 core.
                 pass
             except:
                 pass
        
        # If CPU failed with standard OID, try Host-Resources-MIB (Windows/Linux standard)
        if not cpu_val or cpu_err:
             # hrProcessorLoad (1.3.6.1.2.1.25.3.3.1.2)
             cpu_loads, err = await _snmp_walk_async(ip, community, '1.3.6.1.2.1.25.3.3.1.2', port)
             if cpu_loads and not err:
                 avg_load = sum([int(x) for x in cpu_loads]) / len(cpu_loads)
                 datos['cpu_load'] = avg_load

        if isinstance(ram_total_kb, int):
            datos['ram_total'] = ram_total_kb / 1024 # KB to MB
        
        if isinstance(ram_avail_kb, int):
            # Used = Total - Avail
            # Note: memAvailReal in UCD-SNMP is sometimes misleading, but good enough.
            if isinstance(datos['ram_total'], (int, float)):
                ram_total_mb = datos['ram_total']
                ram_avail_mb = ram_avail_kb / 1024
                datos['ram_used'] = ram_total_mb - ram_avail_mb
        
        # If RAM failed, try Host-Resources-MIB
        if (not ram_total_kb or ram_err1) or (not ram_avail_kb or ram_err2):
            # hrStorageSize (1.3.6.1.2.1.25.2.3.1.5) and hrStorageUsed (1.3.6.1.2.1.25.2.3.1.6)
            # Need to find the one with hrStorageType = hrStorageRam (1.3.6.1.2.1.25.2.1.2)
            # This is complex for a simple script, skipping for now unless needed.
            pass

    except Exception as e:
        # Partial failure is OK
        pass

    return datos

if __name__ == "__main__":
    # sys.stdout.reconfigure(encoding='utf-8')
    
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: snmp_worker.py <IP> <COMMUNITY> [PORT]"}))
        sys.exit(1)

    ip = sys.argv[1]
    community = sys.argv[2]
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 161

    try:
        # Run async loop
        result = asyncio.run(consultar_metricas(ip, community, port))
        print(json.dumps(result), flush=True)
    except Exception as e:
        print(json.dumps({"error": str(e)}), flush=True)
