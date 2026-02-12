from django import forms
from .models import Servidor

class ServidorForm(forms.ModelForm):
    class Meta:
        model = Servidor
        fields = ['nombre', 'ip_host', 'puerto_tomcat', 'puerto_conexion', 'sistema_operativo', 'tipo_conexion', 'tipo_instalacion', 'usuario', 'password', 'nombre_servicio']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Servidor Producción'}),
            'ip_host': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '192.168.1.100'}),
            'puerto_tomcat': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '8080'}),
            'puerto_conexion': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Vacío = Default (22/5985)'}),
            'sistema_operativo': forms.Select(attrs={'class': 'form-select'}),
            'tipo_conexion': forms.Select(attrs={'class': 'form-select'}),
            'tipo_instalacion': forms.Select(attrs={'class': 'form-select'}),
            'usuario': forms.TextInput(attrs={'class': 'form-control'}),
            'password': forms.PasswordInput(attrs={'class': 'form-control'}),
            'nombre_servicio': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre exacto del servicio o contenedor'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        tipo_conexion = cleaned_data.get('tipo_conexion')
        usuario = cleaned_data.get('usuario')
        password = cleaned_data.get('password')
        
        # Si es conexión remota, requerir usuario y password (para nuevos registros)
        if tipo_conexion in ['winrm', 'ssh']:
            if not usuario:
                self.add_error('usuario', 'El usuario es obligatorio para conexiones remotas.')
            if not password and not self.instance.pk: # Solo obligatorio si es nuevo
                self.add_error('password', 'La contraseña es obligatoria para nuevas conexiones remotas.')
        
        return cleaned_data
