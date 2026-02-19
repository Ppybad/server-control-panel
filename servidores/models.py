from django.db import models


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


class Host(models.Model):
    nombre = models.CharField(max_length=100)
    ip_host = models.CharField(max_length=100)
    sistema_operativo = models.CharField(max_length=10, choices=OS_CHOICES, default='windows')
    tipo_conexion = models.CharField(max_length=10, choices=CONNECTION_CHOICES, default='winrm')
    puerto_conexion = models.IntegerField(blank=True, null=True)
    usuario = models.CharField(max_length=100, blank=True, null=True)
    password = models.CharField(max_length=100, blank=True, null=True)
    notas = models.TextField(blank=True, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    snmp_community = models.CharField(max_length=50, default='public', blank=True, help_text="Comunidad SNMP (ej. public)")
    snmp_port = models.IntegerField(default=161, blank=True, null=True, help_text="Puerto UDP SNMP")

    def __str__(self):
        return f"{self.nombre} ({self.ip_host})"


class Instancia(models.Model):
    SERVICE_CHOICES = [
        ('tomcat', 'Tomcat'),
        ('node', 'Node.js'),
        ('docker', 'Docker genérico'),
    ]

    host = models.ForeignKey(Host, on_delete=models.CASCADE, related_name='instancias')
    tipo_servicio = models.CharField(max_length=10, choices=SERVICE_CHOICES, default='tomcat')
    tipo_instalacion = models.CharField(max_length=10, choices=INSTALLATION_CHOICES, default='sistema')
    nombre_servicio = models.CharField(max_length=100)
    puerto_tomcat = models.IntegerField(default=8080)
    observaciones = models.TextField(blank=True, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=20, default='Desconocido')
    ultimo_check = models.DateTimeField(null=True, blank=True)
    mensaje_error = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.nombre_servicio} @ {self.host.ip_host}:{self.puerto_tomcat}"
