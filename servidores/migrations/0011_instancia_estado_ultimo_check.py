from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('servidores', '0010_merge_0009_host_instancia_0009_instancia_tipo_servicio'),
    ]

    operations = [
        migrations.AddField(
            model_name='instancia',
            name='estado',
            field=models.CharField(default='Desconocido', max_length=20),
        ),
        migrations.AddField(
            model_name='instancia',
            name='ultimo_check',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
