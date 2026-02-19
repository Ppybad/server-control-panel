from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from types import SimpleNamespace

from .models import Host, Instancia
from .forms import HostForm, InstanciaForm
from .services import scan_winrm_tomcat, scan_ssh_tomcat, verificar_estado_servidor, _verificar_estado, check_tcp_port, scan_winrm_node, scan_ssh_node
from .services_restart import reiniciar_servidor_tomcat, detener_servidor_tomcat, iniciar_servidor_tomcat

from .services_docker import listar_contenedores_docker
from .services_local import listar_contenedores_docker_local, listar_servicios_tomcat_locales, listar_servicios_node_locales, obtener_trusted_hosts, agregar_trusted_host, eliminar_trusted_host, establecer_comodin_trustedhosts
from .services_snmp import consultar_metricas_snmp
import platform
import json
import time
from django.conf import settings


def limpiar_mensaje_puerto(mensaje):
    if not mensaje:
        return mensaje
    if "Puerto" in mensaje and "OK" in mensaje:
        idx = mensaje.find("Puerto")
        return mensaje[:idx].strip()
    return mensaje


def detectar_puerto_http(ip):
    candidatos = [8080, 80, 8888, 8181, 8081, 8000, 3000, 5000]
    for p in candidatos:
        if check_tcp_port(ip, p):
            return p
    return 8080

def descubrir_tomcat_local(request):
    """API para autodescubrir servicios Tomcat locales."""
    servicios, error = listar_servicios_tomcat_locales()
    if error:
        return JsonResponse({'error': error}, status=500)
    return JsonResponse({'servicios': servicios})

def explorar_docker(request):
    if request.method == 'POST':
        if 'connect' in request.POST:
            mode = request.POST.get('connection_mode', 'ssh')
            
            if mode == 'local':
                contenedores, error = listar_contenedores_docker_local()
                ip = 'localhost'
                port = 0
                user = ''
                password = ''
            else:
                ip = request.POST.get('ip')
                port = int(request.POST.get('port') or 22)
                user = request.POST.get('user')
                password = request.POST.get('password')
                contenedores, error = listar_contenedores_docker(ip, port, user, password)
            
            if error:
                messages.error(request, error)
            else:
                request.session['docker_temp_creds'] = {
                    'ip': ip, 'port': port, 'user': user, 'password': password, 'mode': mode
                }
                return render(request, 'servidores/explorar_docker.html', {
                    'contenedores': contenedores,
                    'ip': ip,
                    'connected': True
                })
        
        elif 'add_container' in request.POST:
            creds = request.session.get('docker_temp_creds', {})
            if not creds:
                messages.error(request, "Sesión expirada. Por favor conecta nuevamente.")
                return redirect('explorar_docker')
                
            nombre_contenedor = request.POST.get('container_name')
            host_id = creds.get('host_id')
            ip = creds.get('ip')
            if not host_id:
                messages.error(request, "Para agregar un contenedor al panel, usa la exploración desde un Host en Navegación.")
                return redirect('navegacion')
            host = get_object_or_404(Host, pk=host_id)
            Instancia.objects.create(
                host=host,
                tipo_servicio='docker',
                tipo_instalacion='docker',
                nombre_servicio=nombre_contenedor,
                puerto_tomcat=8080,
                observaciones=f'Contenedor Docker detectado desde explorador ({ip})'
            )
            messages.success(request, f"Contenedor {nombre_contenedor} agregado al panel para el host {host.nombre}.")
            return redirect('navegacion')

    return render(request, 'servidores/explorar_docker.html', {'connected': False})

def explorar_docker_host(request, pk):
    h = get_object_or_404(Host, pk=pk)
    mode = h.tipo_conexion  # 'local' o 'ssh' (winrm no soportado para Docker aquí)
    ip = h.ip_host
    port = h.puerto_conexion or 22
    user = h.usuario
    password = h.password

    if mode == 'local':
        contenedores, error = listar_contenedores_docker_local()
    elif mode == 'ssh':
        contenedores, error = listar_contenedores_docker(ip, port, user, password)
    else:
        messages.error(request, 'Explorar Docker solo soporta hosts Local o SSH.')
        return redirect('navegacion')

    if error:
        messages.error(request, f"Error al conectar con {h.nombre}: {error}")
        return redirect('navegacion')

    request.session['docker_temp_creds'] = {
        'ip': ip, 'port': port if mode == 'ssh' else 0,
        'user': user if mode == 'ssh' else '',
        'password': password if mode == 'ssh' else '',
        'mode': mode,
        'host_id': h.id,
    }

    return render(request, 'servidores/explorar_docker.html', {
        'contenedores': contenedores,
        'ip': ip,
        'connected': True
    })

def health(request):
    return JsonResponse({'status': 'ok'})

def estado_sistema(request):
    return render(request, 'servidores/estado_sistema.html')

def estado_diagnostico(request):
    t0 = time.perf_counter()
    server = {'status': 'ok', 'http': 200}
    t1 = time.perf_counter()
    db_start = time.perf_counter()
    try:
        c = Host.objects.count()
        db_status = {'status': 'ok', 'detail': f'Conectado ({c} hosts)'}
    except Exception as e:
        db_status = {'status': 'error', 'detail': str(e)[:120]}
    db_end = time.perf_counter()
    apis_start = time.perf_counter()
    apis_status = {'status': 'warn', 'detail': 'No configuradas'}
    apis_end = time.perf_counter()
    return JsonResponse({
        'ok': db_status.get('status') == 'ok' and server.get('status') == 'ok',
        'server': {'status': server['status'], 'http': server.get('http', '-'), 'time_ms': int((t1 - t0) * 1000)},
        'db': {'status': db_status['status'], 'detail': db_status.get('detail', ''), 'time_ms': int((db_end - db_start) * 1000)},
        'apis': {'status': apis_status['status'], 'detail': apis_status.get('detail', ''), 'time_ms': int((apis_end - apis_start) * 1000)},
    })

def documentacion(request):
    return render(request, 'servidores/documentacion.html')

def herramientas(request):
    return render(request, 'servidores/herramientas.html')

def navegacion(request):
    host_form = HostForm()
    instancia_form = InstanciaForm()
    hosts = list(Host.objects.prefetch_related('instancias').order_by('ip_host'))

    def normalizar_clave(valor):
        if not valor:
            return ''
        v = valor.strip().lower()
        if v in ('localhost', '127.0.0.1', '::1'):
            return 'localhost'
        return v

    if request.method == 'POST':
        if 'submit_host' in request.POST:
            host_form = HostForm(request.POST)
            if host_form.is_valid():
                host_form.save()
                messages.success(request, 'Host guardado correctamente.')
                return redirect('navegacion')
        elif 'submit_instancia' in request.POST:
            instancia_form = InstanciaForm(request.POST)
            if instancia_form.is_valid():
                instancia = instancia_form.save()
                host = instancia.host
                objeto = SimpleNamespace(
                    ip_host=host.ip_host,
                    puerto_conexion=host.puerto_conexion,
                    sistema_operativo=host.sistema_operativo,
                    tipo_conexion=host.tipo_conexion,
                    tipo_instalacion=instancia.tipo_instalacion,
                    usuario=host.usuario,
                    password=host.password,
                    nombre_servicio=instancia.nombre_servicio,
                    puerto_tomcat=instancia.puerto_tomcat,
                )
                estado, mensaje = _verificar_estado(objeto)
                mensaje_visible = mensaje
                if estado == 'Alerta' and mensaje and mensaje.startswith('Servicio activo, pero puerto'):
                    estado = 'Activo'
                    mensaje_visible = 'Servicio activo (puerto no accesible desde este panel).'
                if objeto.puerto_tomcat and objeto.puerto_tomcat != instancia.puerto_tomcat:
                    instancia.puerto_tomcat = objeto.puerto_tomcat
                instancia.estado = estado
                instancia.mensaje_error = '' if estado == 'Activo' else mensaje_visible
                instancia.ultimo_check = timezone.now()
                instancia.save()
                if estado == 'Activo':
                    messages.success(request, f'Instancia guardada. Estado actual: {limpiar_mensaje_puerto(mensaje_visible)}')
                else:
                    messages.warning(request, f'Instancia guardada, pero se detectó: {mensaje_visible}')
                return redirect('navegacion')
    prompt_ms = getattr(settings, 'NAV_SCAN_PROMPT_MS', 30000)
    request_ms = getattr(settings, 'NAV_SCAN_REQUEST_MS', 180000)
    prompt_sec = int(prompt_ms / 1000) if prompt_ms else 30
    return render(request, 'servidores/navegacion.html', {
        'host_form': host_form,
        'instancia_form': instancia_form,
        'hosts': hosts,
        'nav_scan_prompt_ms': prompt_ms,
        'nav_scan_request_ms': request_ms,
        'nav_scan_prompt_sec': prompt_sec,
    })


def eliminar_host(request, pk):
    host = get_object_or_404(Host, pk=pk)
    nombre = host.nombre
    host.delete()
    messages.success(request, f'Host "{nombre}" eliminado correctamente junto con sus instancias.')
    return redirect('navegacion')

def editar_host(request, pk):
    h = get_object_or_404(Host, pk=pk)
    if request.method == 'POST':
        form = HostForm(request.POST, instance=h)
        if form.is_valid():
            form.save()
            messages.success(request, 'Host actualizado correctamente.')
        else:
            messages.error(request, 'Error al actualizar el Host.')
        return redirect('navegacion')
    return redirect('navegacion')

def editar_instancia(request, pk):
    inst = get_object_or_404(Instancia, pk=pk)
    if request.method == 'POST':
        form = InstanciaForm(request.POST, instance=inst)
        if form.is_valid():
            form.save()
            messages.success(request, 'Instancia actualizada correctamente.')
        else:
            messages.error(request, 'Error al actualizar la Instancia.')
        return redirect('navegacion')
    return redirect('navegacion')


def controlar_instancia(request, pk, accion):
    instancia = get_object_or_404(Instancia, pk=pk)
    host = instancia.host
    es_pid = isinstance(instancia.nombre_servicio, str) and instancia.nombre_servicio.startswith('PID:')
    servidor_like = SimpleNamespace(
        ip_host=host.ip_host,
        puerto_conexion=host.puerto_conexion,
        sistema_operativo=host.sistema_operativo,
        tipo_conexion=host.tipo_conexion,
        tipo_instalacion=instancia.tipo_instalacion,
        usuario=host.usuario,
        password=host.password,
        nombre_servicio=instancia.nombre_servicio,
        puerto_tomcat=instancia.puerto_tomcat,
    )
    if accion in ['start', 'iniciar']:
        exito, mensaje = iniciar_servidor_tomcat(servidor_like)
    elif accion in ['stop', 'detener']:
        exito, mensaje = detener_servidor_tomcat(servidor_like)
    elif accion in ['restart', 'reiniciar']:
        exito, mensaje = reiniciar_servidor_tomcat(servidor_like)
    elif accion in ['delete', 'eliminar']:
        nombre = instancia.nombre_servicio
        instancia.delete()
        messages.success(request, f'Instancia "{nombre}" eliminada correctamente.')
        return redirect('navegacion')
    else:
        messages.error(request, f'Acción no soportada: {accion}')
        return redirect('navegacion')
    if exito:
        if es_pid and accion in ['stop', 'detener']:
            nombre = instancia.nombre_servicio
            instancia.delete()
            messages.success(request, f'{mensaje} Proceso basado en PID "{nombre}" eliminado del resumen de instancias.')
            return redirect('navegacion')
        estado, mensaje_estado = _verificar_estado(servidor_like)
        mensaje_visible = mensaje_estado
        if estado == 'Alerta' and mensaje_estado and mensaje_estado.startswith('Servicio activo, pero puerto'):
            estado = 'Activo'
            mensaje_visible = 'Servicio activo (puerto no accesible desde este panel).'
        if getattr(servidor_like, 'puerto_tomcat', None) and servidor_like.puerto_tomcat != instancia.puerto_tomcat:
            instancia.puerto_tomcat = servidor_like.puerto_tomcat
        instancia.estado = estado
        instancia.mensaje_error = '' if estado == 'Activo' else mensaje_visible
        instancia.ultimo_check = timezone.now()
        instancia.save()
        if mensaje_visible:
            messages.success(request, mensaje_visible)
        else:
            messages.success(request, mensaje)
    else:
        messages.error(request, mensaje)
    return redirect('navegacion')


def verificar_instancia(request, pk):
    instancia = get_object_or_404(Instancia, pk=pk)
    host = instancia.host
    objeto = SimpleNamespace(
        ip_host=host.ip_host,
        puerto_conexion=host.puerto_conexion,
        sistema_operativo=host.sistema_operativo,
        tipo_conexion=host.tipo_conexion,
        tipo_instalacion=instancia.tipo_instalacion,
        usuario=host.usuario,
        password=host.password,
        nombre_servicio=instancia.nombre_servicio,
        puerto_tomcat=instancia.puerto_tomcat,
    )
    estado, mensaje = _verificar_estado(objeto)
    if objeto.puerto_tomcat and objeto.puerto_tomcat != instancia.puerto_tomcat:
        instancia.puerto_tomcat = objeto.puerto_tomcat
    mensaje_visible = mensaje
    if estado == 'Alerta' and mensaje and mensaje.startswith('Servicio activo, pero puerto'):
        estado = 'Activo'
        mensaje_visible = 'Servicio activo (puerto no accesible desde este panel).'
    instancia.estado = estado
    instancia.mensaje_error = '' if estado == 'Activo' else mensaje_visible
    instancia.ultimo_check = timezone.now()
    instancia.save()
    if estado == 'Activo':
        messages.success(request, f'Instancia activa: {limpiar_mensaje_puerto(mensaje_visible)}')
    else:
        messages.error(request, f'Problema detectado: {mensaje_visible}')
    return redirect('navegacion')


def eliminar_instancia(request, pk):
    instancia = get_object_or_404(Instancia, pk=pk)
    nombre = instancia.nombre_servicio
    instancia.delete()
    messages.success(request, f'Instancia "{nombre}" eliminada correctamente.')
    return redirect('navegacion')


@csrf_exempt
def scan_host(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        data = {}
        if request.body:
            import json as _json
            data = _json.loads(request.body.decode('utf-8'))
        host_id = data.get('host_id') or request.POST.get('host_id')
        tipo_servicio = data.get('tipo_servicio') or request.POST.get('tipo_servicio') or 'tomcat'
        h = get_object_or_404(Host, pk=host_id)
        if h.tipo_conexion in ['winrm', 'ssh']:
            if not h.usuario or not h.password:
                return JsonResponse({'error': 'Faltan credenciales en el Host seleccionado (usuario/contraseña). Edita o registra el Host con credenciales válidas.'}, status=400)
        results = []
        error = None
        puerto_detectado = detectar_puerto_http(h.ip_host)
        existentes_qs = Instancia.objects.filter(host=h, tipo_servicio=tipo_servicio)
        existentes_por_nombre = {inst.nombre_servicio: inst.id for inst in existentes_qs}
        # Selección por tipo de servicio
        if tipo_servicio == 'docker':
            # Escaneo de contenedores Docker
            if h.tipo_conexion == 'local':
                conts, err = listar_contenedores_docker_local()
                error = err
            elif h.tipo_conexion == 'ssh':
                conts, err = listar_contenedores_docker(h.ip_host, h.puerto_conexion or 22, h.usuario, h.password)
                error = err
            else:
                conts = []
                error = 'Exploración Docker no soportada con WinRM; usa Local o SSH.'
            # Normalizar a estructura común
            results = []
            for c in conts or []:
                estado = 'Activo' if ('Up' in (c.get('estado') or '')) else 'Detenido'
                nombre = c.get('nombre') or c.get('id') or 'contenedor'
                display = f"[Docker] {nombre}"
                if c.get('imagen'):
                    display = f"[Docker] {nombre} ({c.get('imagen')})"
                results.append({
                    'nombre': nombre,
                    'display': display,
                    'estado': estado,
                    'tipo': 'docker'
                })
        elif tipo_servicio == 'tomcat':
            # Escaneo de Tomcat
            if h.tipo_conexion == 'winrm':
                results, error = scan_winrm_tomcat(h.ip_host, h.puerto_conexion or 5985, h.usuario, h.password)
            elif h.tipo_conexion == 'ssh':
                results, error = scan_ssh_tomcat(h.ip_host, h.puerto_conexion or 22, h.usuario, h.password)
            elif h.tipo_conexion == 'local':
                from .services_local import listar_servicios_tomcat_locales
                items, err = listar_servicios_tomcat_locales()
                error = err
                results = [{'nombre': i['nombre'], 'display': i['display'], 'estado': i['estado'], 'tipo': i['tipo']} for i in items] if items else []
        elif tipo_servicio == 'node':
            # Escaneo de Node.js
            if h.tipo_conexion == 'winrm':
                results, error = scan_winrm_node(h.ip_host, h.puerto_conexion or 5985, h.usuario, h.password)
            elif h.tipo_conexion == 'ssh':
                results, error = scan_ssh_node(h.ip_host, h.puerto_conexion or 22, h.usuario, h.password)
            elif h.tipo_conexion == 'local':
                items, err = listar_servicios_node_locales()
                error = err
                results = [{
                    'nombre': i['nombre'],
                    'display': i['display'],
                    'estado': i['estado'],
                    'tipo': i['tipo'],
                    'puerto': i.get('puerto'),
                    'origen_node': i.get('origen_node'),
                    'controlable_node': i.get('controlable_node'),
                    'rol_node': i.get('rol_node'),
                    'detalle_node': i.get('detalle_node'),
                } for i in items] if items else []
        else:
            # Otros tipos aún no implementados
            results = []
            error = error or 'Tipo de servicio no soportado para autodescubrimiento.'
        items_final = []
        for i in results or []:
            item = dict(i)
            if tipo_servicio == 'tomcat':
                item.setdefault('tipo_instalacion', 'sistema')
            elif tipo_servicio == 'docker':
                item.setdefault('tipo_instalacion', 'docker')
            else:
                item.setdefault('tipo_instalacion', 'sistema')
            # Si el escaneo ya detectó un puerto específico para ese servicio, lo respetamos.
            # Solo usamos puerto_detectado como fallback cuando no hay puerto en el item.
            if not item.get('puerto'):
                item['puerto'] = puerto_detectado
            nombre_item = item.get('nombre') or ''
            inst_id = existentes_por_nombre.get(nombre_item)
            if inst_id:
                item['ya_registrado'] = True
                item['instancia_id'] = inst_id
            else:
                item['ya_registrado'] = False
            items_final.append(item)
        if tipo_servicio not in ['tomcat', 'docker', 'node']:
            error = error or 'Tipo de servicio no soportado para autodescubrimiento.'
        return JsonResponse({'items': items_final, 'error': error})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def monitor_snmp_host(request, pk):
    host = get_object_or_404(Host, pk=pk)
    community = host.snmp_community or 'public'
    port = host.snmp_port or 161
    host_like = SimpleNamespace(
        ip_host=host.ip_host,
        snmp_community=community,
        snmp_port=port,
        nombre=getattr(host, 'nombre', host.ip_host)
    )
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'json' in request.GET:
        data = consultar_metricas_snmp(host_like)
        return JsonResponse(data)
    return render(request, 'servidores/monitoreo.html', {
        'servidor': host_like,
        'host_id': host.id,
    })

def trusted_hosts(request):
    """
    Devuelve la lista de TrustedHosts del cliente local (Windows).
    Siempre responde JSON.
    """
    hosts, error = obtener_trusted_hosts()
    return JsonResponse({
        'trusted_hosts': hosts,
        'wildcard': '*' in hosts if hosts else False,
        'error': error
    })
@csrf_exempt
def trusted_hosts_add(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        data = {}
        if request.body:
            try:
                data = json.loads(request.body.decode('utf-8'))
            except Exception:
                data = {}
        host = data.get('host') or request.POST.get('host')
        hosts, error, cmd = agregar_trusted_host(host)
        return JsonResponse({
            'trusted_hosts': hosts,
            'wildcard': '*' in hosts if hosts else False,
            'error': error,
            'ps': cmd
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
@csrf_exempt
def trusted_hosts_remove(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        data = {}
        if request.body:
            try:
                data = json.loads(request.body.decode('utf-8'))
            except Exception:
                data = {}
        host = data.get('host') or request.POST.get('host')
        hosts, error, cmd = eliminar_trusted_host(host)
        return JsonResponse({
            'trusted_hosts': hosts,
            'wildcard': '*' in hosts if hosts else False,
            'error': error,
            'ps': cmd
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
@csrf_exempt
def trusted_hosts_wildcard(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        data = {}
        if request.body:
            try:
                data = json.loads(request.body.decode('utf-8'))
            except Exception:
                data = {}
        activar = data.get('activar')
        if activar in [True, False]:
            pass
        else:
            activar = str(activar).lower() in ['1', 'true', 'yes', 'on']
        hosts, error, cmd = establecer_comodin_trustedhosts(activar)
        return JsonResponse({
            'trusted_hosts': hosts,
            'wildcard': '*' in hosts if hosts else False,
            'error': error,
            'ps': cmd
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
