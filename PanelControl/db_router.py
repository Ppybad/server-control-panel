from pathlib import Path
from django.conf import settings
import os


class DynamicDBRouter:
    def _mode(self):
        try:
            p = Path(settings.BASE_DIR) / 'db_mode.txt'
            if p.exists():
                m = p.read_text(encoding='utf-8').strip().lower()
                if m in ('postgres', 'sqlite'):
                    return m
        except Exception:
            pass
        m = os.getenv('DB_MODE', '').strip().lower()
        if m in ('postgres', 'sqlite'):
            return m
        return 'sqlite'

    def db_for_read(self, model, **hints):
        m = self._mode()
        return 'postgres' if m == 'postgres' else 'sqlite'

    def db_for_write(self, model, **hints):
        m = self._mode()
        return 'postgres' if m == 'postgres' else 'sqlite'

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        m = self._mode()
        return db == ('postgres' if m == 'postgres' else 'sqlite')

