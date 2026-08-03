import json
import yaml
from pathlib import Path
from typing import List, Dict, Any


class ConfigError(Exception):
    pass


class Config:
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)

        if not self.config_path.exists():
            raise ConfigError(f"Config file not found: {config_path}")

        if self.config_path.suffix.lower() in ['.yaml', '.yml']:
            self._load_yaml()
        elif self.config_path.suffix.lower() == '.json':
            self._load_json()
        else:
            try:
                self._load_yaml()
            except Exception:
                try:
                    self._load_json()
                except Exception:
                    raise ConfigError(
                        f"Could not parse config file. "
                        f"Expected YAML (.yaml, .yml) or JSON (.json)"
                    )

        self._validate()

    def _load_yaml(self):
        try:
            with open(self.config_path, 'r') as f:
                self.data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"Error parsing YAML: {e}")
        except IOError as e:
            raise ConfigError(f"Error reading config file: {e}")

    def _load_json(self):
        try:
            with open(self.config_path, 'r') as f:
                self.data = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigError(f"Error parsing JSON: {e}")
        except IOError as e:
            raise ConfigError(f"Error reading config file: {e}")

    def _validate(self):
        if not isinstance(self.data, dict):
            raise ConfigError("Config must be a dictionary/object")

        if 'target_playlist' not in self.data:
            raise ConfigError("Config missing required field: target_playlist")

        if not isinstance(self.data['target_playlist'], str):
            raise ConfigError("target_playlist must be a string")

        if self.discover_pattern is not None and not isinstance(self.discover_pattern, str):
            raise ConfigError("discover_pattern must be a string")

        for field in ('source_playlists', 'extra_playlists'):
            value = self.data.get(field, [])
            if not isinstance(value, list):
                raise ConfigError(f"{field} must be a list")
            for i, item in enumerate(value):
                if not isinstance(item, str):
                    raise ConfigError(f"{field}[{i}] must be a string")

        if not self.discover_pattern and not self.source_playlists and not self.extra_playlists:
            raise ConfigError(
                "Config must define at least one of: discover_pattern, "
                "source_playlists, extra_playlists"
            )

    @property
    def target_playlist(self) -> str:
        return self.data['target_playlist']

    @property
    def discover_pattern(self) -> Any:
        return self.data.get('discover_pattern')

    @property
    def source_playlists(self) -> List[str]:
        return self.data.get('source_playlists', [])

    @property
    def extra_playlists(self) -> List[str]:
        return self.data.get('extra_playlists', [])

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)
