from django import forms
from .models import Host, Instancia

class HostForm(forms.ModelForm):
    class Meta:
        model = Host
        fields = ['nombre', 'ip_host', 'sistema_operativo', 'tipo_conexion', 'puerto_conexion', 'usuario', 'password', 'snmp_community', 'snmp_port', 'notas']
        labels = {
            'nombre': 'Nombre del Host',
            'ip_host': 'Host / IP',
            'sistema_operativo': 'Sistema Operativo',
            'tipo_conexion': 'Tipo de Conexión',
            'puerto_conexion': 'Puerto Conexión (Opcional)',
            'usuario': 'Usuario (Opcional)',
            'password': 'Contraseña (Opcional)',
            'snmp_community': 'Comunidad SNMP',
            'snmp_port': 'Puerto SNMP',
            'notas': 'Notas (Opcional)',
        }
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Servidor Producción'}),
            'ip_host': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '192.168.1.100'}),
            'sistema_operativo': forms.Select(attrs={'class': 'form-select'}),
            'tipo_conexion': forms.Select(attrs={'class': 'form-select'}),
            'puerto_conexion': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Vacío = Default (22/5985)'}),
            'usuario': forms.TextInput(attrs={'class': 'form-control'}),
            'password': forms.PasswordInput(attrs={'class': 'form-control'}),
            'snmp_community': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: public'}),
            'snmp_port': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Por defecto 161'}),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get('tipo_conexion')
        usuario = cleaned.get('usuario')
        password = cleaned.get('password')
        # Requerir credenciales para conexiones remotas
        if tipo in ['winrm', 'ssh']:
            if not usuario:
                self.add_error('usuario', 'El usuario es obligatorio para conexiones remotas.')
            if not password:
                self.add_error('password', 'La contraseña es obligatoria para conexiones remotas.')
        return cleaned

class InstanciaForm(forms.ModelForm):
    class Meta:
        model = Instancia
        fields = ['host', 'tipo_servicio', 'tipo_instalacion', 'nombre_servicio', 'puerto_tomcat', 'observaciones']
        labels = {
            'host': 'Host',
            'tipo_servicio': 'Servicio a detectar',
            'tipo_instalacion': 'Tipo de despliegue',
            'nombre_servicio': 'Nombre del Servicio/Contenedor',
            'puerto_tomcat': 'Puerto del servicio',
            'observaciones': 'Observaciones (Opcional)',
        }
        widgets = {
            'host': forms.Select(attrs={'class': 'form-select'}),
            'tipo_instalacion': forms.Select(attrs={'class': 'form-select'}),
            'nombre_servicio': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Tomcat9 o mi-contenedor'}),
            'puerto_tomcat': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: 8080 (auto-detectado para Tomcat, editable)',
            }),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
