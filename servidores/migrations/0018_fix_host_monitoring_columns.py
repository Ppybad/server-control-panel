from django.db import migrations, connection


def ensure_host_monitoring_columns(apps, schema_editor):
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(servidores_host)")
        columns = [row[1] for row in cursor.fetchall()]

    if "last_cpu" not in columns:
        schema_editor.execute("ALTER TABLE servidores_host ADD COLUMN last_cpu REAL")
    if "last_ram" not in columns:
        schema_editor.execute("ALTER TABLE servidores_host ADD COLUMN last_ram REAL")
    if "is_online" not in columns:
        schema_editor.execute("ALTER TABLE servidores_host ADD COLUMN is_online BOOL DEFAULT 0")
    if "updated_at" not in columns:
        schema_editor.execute("ALTER TABLE servidores_host ADD COLUMN updated_at DATETIME")


class Migration(migrations.Migration):

    dependencies = [
        ("servidores", "0017_host_monitoring_fields"),
    ]

    operations = [
        migrations.RunPython(ensure_host_monitoring_columns, migrations.RunPython.noop),
    ]

