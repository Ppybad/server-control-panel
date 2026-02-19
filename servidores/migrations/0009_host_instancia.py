from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('servidores', '0008_servidor_snmp_community_servidor_snmp_port'),
    ]

    operations = [
        migrations.CreateModel(
            name='Host',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100)),
                ('ip_host', models.CharField(max_length=100)),
                ('sistema_operativo', models.CharField(choices=[('windows', 'Windows'), ('linux', 'Linux')], default='windows', max_length=10)),
                ('tipo_conexion', models.CharField(choices=[('winrm', 'WinRM (Windows Remoto)'), ('ssh', 'SSH (Linux / Windows OpenSSH)'), ('local', 'Local (Este Equipo)')], default='winrm', max_length=10)),
                ('puerto_conexion', models.IntegerField(blank=True, null=True)),
                ('usuario', models.CharField(blank=True, max_length=100, null=True)),
                ('password', models.CharField(blank=True, max_length=100, null=True)),
                ('notas', models.TextField(blank=True, null=True)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='Instancia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo_instalacion', models.CharField(choices=[('sistema', 'Servicio del Sistema (Systemd/Services)'), ('docker', 'Contenedor Docker')], default='sistema', max_length=10)),
                ('nombre_servicio', models.CharField(max_length=100)),
                ('puerto_tomcat', models.IntegerField(default=8080)),
                ('observaciones', models.TextField(blank=True, null=True)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('host', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='instancias', to='servidores.host')),
            ],
        ),
    ]

