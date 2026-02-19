from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('servidores', '0009_host_instancia'),
    ]

    operations = [
        migrations.AddField(
            model_name='instancia',
            name='tipo_servicio',
            field=models.CharField(
                choices=[
                    ('tomcat', 'Tomcat'),
                    ('node', 'Node.js'),
                    ('docker', 'Docker genérico'),
                ],
                default='tomcat',
                max_length=10,
            ),
        ),
    ]
