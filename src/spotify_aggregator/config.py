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

        if 'source_playlists' not in self.data:
            raise ConfigError("Config missing required field: source_playlists")

        if not isinstance(self.data['target_playlist'], str):
            raise ConfigError("target_playlist must be a string")

        if not isinstance(self.data['source_playlists'], list):
            raise ConfigError("source_playlists must be a list")

        if len(self.data['source_playlists']) == 0:
            raise ConfigError("source_playlists cannot be empty")

        for i, item in enumerate(self.data['source_playlists']):
            if not isinstance(item, str):
                raise ConfigError(f"source_playlists[{i}] must be a string")

    @property
    def target_playlist(self) -> str:
        return self.data['target_playlist']

    @property
    def source_playlists(self) -> List[str]:
        return self.data['source_playlists']

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)
