import unittest
from pathlib import Path

from app.core.config import Settings
from app.core.email_config import EmailSettings
from app.core.paths import BACKEND_ENV_FILE, ENV_FILE, PROJECT_ROOT, ROOT_ENV_FILE
from app.core.storage_config import StorageSettings


class ConfigPathTest(unittest.TestCase):
    def test_project_root_is_resolved_from_source_location(self) -> None:
        expected_project_root = Path(__file__).resolve().parents[2]

        self.assertEqual(PROJECT_ROOT, expected_project_root)
        self.assertEqual(ROOT_ENV_FILE, expected_project_root / ".env")
        self.assertEqual(BACKEND_ENV_FILE, expected_project_root / "backend" / ".env")
        expected_env_file = ROOT_ENV_FILE if ROOT_ENV_FILE.exists() else BACKEND_ENV_FILE
        self.assertEqual(ENV_FILE, expected_env_file)

    def test_all_backend_settings_use_the_same_selected_env_file(self) -> None:
        settings_classes = (Settings, EmailSettings, StorageSettings)

        for settings_class in settings_classes:
            with self.subTest(settings_class=settings_class.__name__):
                self.assertEqual(
                    Path(settings_class.model_config["env_file"]),
                    ENV_FILE,
                )


if __name__ == "__main__":
    unittest.main()
