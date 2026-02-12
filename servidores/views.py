from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Servidor
from .forms import ServidorForm
from .services import verificar_estado_servidor
from .services_restart import reiniciar_servidor_tomcat, detener_servidor_tomcat, iniciar_servidor_tomcat

from .services_docker import listar_contenedores_docker
from .services_local import listar_contenedores_docker_local, listar_servicios_tomcat_locales
import platform
from django.http import JsonResponse

def descubrir_tomcat_local(request):
    """API para autodescubrir servicios Tomcat locales."""
    servicios, error = listar_servicios_tomcat_locales()
    if error:
        return JsonResponse({'error': error}, status=500)
    return JsonResponse({'servicios': servicios})

def explorar_docker(request, pk=None):
    # Si se pasa un ID, intentar conectar automáticamente usando las credenciales del servidor
    if pk and request.method == 'GET':
        servidor = get_object_or_404(Servidor, pk=pk)
        
        mode = servidor.tipo_conexion # 'local' o 'ssh'
        ip = servidor.ip_host
        port = servidor.puerto_conexion or 22
        user = servidor.usuario
        password = servidor.password

        if mode == 'local':
            contenedores, error = listar_contenedores_docker_local()
        else:
            # Asumimos SSH para remoto
            contenedores, error = listar_contenedores_docker(ip, port, user, password)
        
        if error:
            messages.error(request, f"Error al conectar con {servidor.nombre}: {error}")
            return redirect('lista_servidores')
        
        # Guardar en sesión para futuras acciones
        request.session['docker_temp_creds'] = {
            'ip': ip, 'port': port, 'user': user, 'password': password, 'mode': mode
        }
        
        return render(request, 'servidores/explorar_docker.html', {
            'contenedores': contenedores,
            'ip': ip,
            'connected': True
        })

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
            mode = creds.get('mode', 'ssh')
            
            Servidor.objects.create(
                nombre=f"Docker {'Local' if mode == 'local' else ''} - {nombre_contenedor}",
                ip_host=creds['ip'],
                puerto_conexion=creds['port'] if mode == 'ssh' else None,
                usuario=creds['user'] if mode == 'ssh' else None,
                password=creds['password'] if mode == 'ssh' else None,
                sistema_operativo='linux' if mode == 'ssh' else ('windows' if platform.system() == 'Windows' else 'linux'),
                tipo_conexion='local' if mode == 'local' else 'ssh',
                tipo_instalacion='docker',
                nombre_servicio=nombre_contenedor,
                puerto_tomcat=8080
            )
            messages.success(request, f"Contenedor {nombre_contenedor} agregado al panel.")
            return redirect('lista_servidores')

    return render(request, 'servidores/explorar_docker.html', {'connected': False})

def documentacion(request):
    return render(request, 'servidores/documentacion.html')

def lista_servidores(request):
    if request.method == 'POST':
        form = ServidorForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, '¡Servidor agregado correctamente!')
            return redirect('lista_servidores')
        else:
            messages.error(request, 'Error al agregar el servidor. Por favor verifica los datos.')
    else:
        form = ServidorForm()

    servidores = Servidor.objects.all().order_by('-fecha_creacion')
    return render(request, 'servidores/lista_servidores.html', {
        'servidores': servidores,
        'form': form
    })

def verificar_servidor(request, pk):
    servidor = get_object_or_404(Servidor, pk=pk)
    estado, mensaje = verificar_estado_servidor(servidor)
    
    if estado == 'Activo':
        messages.success(request, f'Conexión Exitosa: {mensaje}')
    else:
        messages.error(request, f'Problema detectado: {mensaje}')
        
    return redirect('lista_servidores')

def editar_servidor(request, pk):
    servidor = get_object_or_404(Servidor, pk=pk)
    if request.method == 'POST':
        form = ServidorForm(request.POST, instance=servidor)
        if form.is_valid():
            form.save()
            messages.success(request, 'Servidor actualizado correctamente.')
            return redirect('lista_servidores')
        else:
            print(f"Errores formulario: {form.errors}") # Debug
    else:
        form = ServidorForm(instance=servidor)
    
    return render(request, 'servidores/editar_servidor.html', {'form': form, 'servidor': servidor})

def eliminar_servidor(request, pk):
    servidor = get_object_or_404(Servidor, pk=pk)
    nombre = servidor.nombre
    servidor.delete()
    messages.success(request, f'Servidor "{nombre}" eliminado correctamente.')
    return redirect('lista_servidores')

def reiniciar_servidor(request, pk):
    servidor = get_object_or_404(Servidor, pk=pk)
    exito, mensaje = reiniciar_servidor_tomcat(servidor)
    
    if exito:
        messages.success(request, f'Reinicio Exitoso: {mensaje}')
        # Actualizamos estado inmediatamente
        verificar_estado_servidor(servidor)
    else:
        messages.error(request, f'Error al reiniciar: {mensaje}')
        
    return redirect('lista_servidores')

def detener_servidor(request, pk):
    servidor = get_object_or_404(Servidor, pk=pk)
    exito, mensaje = detener_servidor_tomcat(servidor)
    
    if exito:
        messages.success(request, f'Detención Exitosa: {mensaje}')
        verificar_estado_servidor(servidor)
    else:
        messages.error(request, f'Error al detener: {mensaje}')
        
    return redirect('lista_servidores')

def iniciar_servidor(request, pk):
    servidor = get_object_or_404(Servidor, pk=pk)
    exito, mensaje = iniciar_servidor_tomcat(servidor)
    
    if exito:
        messages.success(request, f'Inicio Exitoso: {mensaje}')
        verificar_estado_servidor(servidor)
    else:
        messages.error(request, f'Error al iniciar: {mensaje}')
        
    return redirect('lista_servidores')

def controlar_servidor(request, pk, accion):
    servidor = get_object_or_404(Servidor, pk=pk)
    
    if accion == 'start':
        exito, mensaje = iniciar_servidor_tomcat(servidor)
        verb = "Inicio"
    elif accion == 'stop':
        exito, mensaje = detener_servidor_tomcat(servidor)
        verb = "Detención"
    elif accion == 'restart':
        exito, mensaje = reiniciar_servidor_tomcat(servidor)
        verb = "Reinicio"
    else:
        messages.error(request, "Acción no válida")
        return redirect('lista_servidores')

    if exito:
        messages.success(request, f'{verb} Exitoso: {mensaje}')
        verificar_estado_servidor(servidor)
    else:
        messages.error(request, f'Error en {verb.lower()}: {mensaje}')
        
    return redirect('lista_servidores')
