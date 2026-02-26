from django.db import migrations, connection


def ensure_host_monitoring_columns_v2(apps, schema_editor):
    vendor = connection.vendor
    with connection.cursor() as cursor:
        if vendor == "sqlite":
            cursor.execute("PRAGMA table_info(servidores_host)")
            columns = [row[1] for row in cursor.fetchall()]
            if "last_cpu" not in columns:
                cursor.execute("ALTER TABLE servidores_host ADD COLUMN last_cpu REAL")
            if "last_ram" not in columns:
                cursor.execute("ALTER TABLE servidores_host ADD COLUMN last_ram REAL")
            if "is_online" not in columns:
                cursor.execute("ALTER TABLE servidores_host ADD COLUMN is_online BOOL DEFAULT 0")
            if "updated_at" not in columns:
                cursor.execute("ALTER TABLE servidores_host ADD COLUMN updated_at DATETIME")
        elif vendor == "postgresql":
            cursor.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'servidores_host'"
            )
            columns = {row[0] for row in cursor.fetchall()}
            if "last_cpu" not in columns:
                cursor.execute("ALTER TABLE servidores_host ADD COLUMN last_cpu DOUBLE PRECISION")
            if "last_ram" not in columns:
                cursor.execute("ALTER TABLE servidores_host ADD COLUMN last_ram DOUBLE PRECISION")
            if "is_online" not in columns:
                cursor.execute("ALTER TABLE servidores_host ADD COLUMN is_online BOOLEAN DEFAULT FALSE")
            if "updated_at" not in columns:
                cursor.execute("ALTER TABLE servidores_host ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE")


class Migration(migrations.Migration):

    dependencies = [
        ("servidores", "0018_fix_host_monitoring_columns"),
    ]

    operations = [
        migrations.RunPython(ensure_host_monitoring_columns_v2, migrations.RunPython.noop),
    ]

