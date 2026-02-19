from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('servidores', '0012_merge_0010_merge_0009_host_instancia_0009_instancia_tipo_servicio_0011_instancia_estado_ultimo_check'),
    ]

    operations = [
        migrations.AddField(
            model_name='instancia',
            name='mensaje_error',
            field=models.TextField(blank=True, null=True),
        ),
    ]

