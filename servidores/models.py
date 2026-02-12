from django.db import models

class Servidor(models.Model):
    OS_CHOICES = [
        ('windows', 'Windows'),
        ('linux', 'Linux'),
    ]
    
    CONNECTION_CHOICES = [
        ('winrm', 'WinRM (Windows Remoto)'),
        ('ssh', 'SSH (Linux / Windows OpenSSH)'),
        ('local', 'Local (Este Equipo)'),
    ]

    INSTALLATION_CHOICES = [
        ('sistema', 'Servicio del Sistema (Systemd/Services)'),
        ('docker', 'Contenedor Docker'),
    ]

    nombre = models.CharField(max_length=100, help_text="Nombre identificativo del servidor")
    ip_host = models.CharField(max_length=100, help_text="Dirección IP o Hostname")
    puerto_tomcat = models.IntegerField(default=8080, help_text="Puerto donde corre Tomcat")
    puerto_conexion = models.IntegerField(blank=True, null=True, help_text="Puerto de conexión remota (SSH: 22, WinRM: 5985). Dejar vacío para default.")
    sistema_operativo = models.CharField(max_length=10, choices=OS_CHOICES, default='windows')
    tipo_conexion = models.CharField(max_length=10, choices=CONNECTION_CHOICES, default='winrm', help_text="Protocolo de conexión remota")
    tipo_instalacion = models.CharField(max_length=10, choices=INSTALLATION_CHOICES, default='sistema', help_text="Tipo de despliegue: Servicio nativo o Docker")
    
    # Credenciales (Para conectar y ejecutar comandos)
    usuario = models.CharField(max_length=100, blank=True, null=True)
    password = models.CharField(max_length=100, blank=True, null=True)

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    ultimo_check = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=20, default='Desconocido')
    nombre_servicio = models.CharField(max_length=100, blank=True, null=True, help_text="Nombre real del servicio en el SO (Autodetectado)")
    mensaje_error = models.TextField(blank=True, null=True, help_text="Último mensaje de error si falló la conexión")

    def __str__(self):
        return f"{self.nombre} ({self.ip_host})"
