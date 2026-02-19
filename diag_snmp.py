import asyncio
import sys
from pysnmp.hlapi.v3arch.asyncio import *

async def check_snmp(ip, community, port=161):
    print(f"--- Diagnóstico SNMP ---")
    print(f"Target: {ip}:{port}")
    print(f"Community: {community}")
    print("Enviando solicitud GET para sysDescr (1.3.6.1.2.1.1.1.0)...", flush=True)
    
    try:
        print("Creando transporte UDP...", flush=True)
        transport_target = await UdpTransportTarget.create((ip, port), timeout=5, retries=3)
        print("Transporte creado. Ejecutando get_cmd...", flush=True)
        result = await get_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            transport_target,
            ContextData(),
            ObjectType(ObjectIdentity('1.3.6.1.2.1.1.1.0'))
        )
        print(f"Resultado obtenido: {type(result)}", flush=True)
        
        errorIndication, errorStatus, errorIndex, varBinds = result


        if errorIndication:
            print(f"❌ FALLO: {errorIndication}")
            print("Posibles causas:")
            print("1. La IP es incorrecta o inalcanzable.")
            print("2. El puerto 161 (UDP) está bloqueado por firewall.")
            print("3. El servicio SNMP no está corriendo en el destino.")
            print("4. La 'Comunidad' es incorrecta (si es v2c).")
        elif errorStatus:
            print(f"❌ ERROR SNMP: {errorStatus.prettyPrint()}")
        else:
            print("✅ ÉXITO: Respuesta recibida.")
            for varBind in varBinds:
                print(f"Dato: {varBind[1]}")
                
    except Exception as e:
        print(f"❌ EXCEPCIÓN CRÍTICA: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python diag_snmp.py <IP_SERVIDOR> [COMUNIDAD]")
        print("Ejemplo: python diag_snmp.py 192.168.1.50 public")
        sys.exit(1)
        
    ip = sys.argv[1]
    community = sys.argv[2] if len(sys.argv) > 2 else 'public'
    
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(check_snmp(ip, community))
