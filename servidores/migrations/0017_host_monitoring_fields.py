from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('servidores', '0016_alter_host_snmp_community_alter_host_snmp_port'),
    ]

    operations = [
        migrations.AddField(
            model_name='host',
            name='last_cpu',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='host',
            name='last_ram',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='host',
            name='is_online',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='host',
            name='updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

