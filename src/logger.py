import json
import os
from typing import List, Optional
from src.models import EpisodeLog


class EpisodeLogger:
    """Logs episode execution records into structured JSON and JSONL format."""
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.jsonl_path = os.path.join(self.log_dir, "episodes.jsonl")

    def log_episode(self, episode: EpisodeLog) -> str:
        """Append an episode record to JSONL log file and write individual JSON log."""
        data = episode.model_dump()
        
        # 1. Append to JSONL
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data) + "\n")

        # 2. Write individual JSON log
        single_json_path = os.path.join(self.log_dir, f"episode_{episode.scenario_id}.json")
        with open(single_json_path, "w", encoding="utf-8") as f:
            json.dumps(data, indent=2)

        return single_json_path

    def load_all_episodes(self) -> List[dict]:
        """Read all logged episodes from JSONL log file."""
        if not os.path.exists(self.jsonl_path):
            return []
        episodes = []
        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    episodes.append(json.loads(line))
        return episodes
