import os
from dataclasses import asdict, dataclass, field
from typing import List


@dataclass
class AppSettings:
    api_base_url: str = os.getenv("PRO_API_BASE_URL", "http://127.0.0.1:8000")
    theme: str = "nova"
    selected_model: str = "yolov8"
    custom_model_path: str = ""
    model_options: List[str] = field(default_factory=lambda: ["yolov5", "yolov8", "custom model"])
    update_check_on_start: bool = True
    user_email: str = ""
    user_token: str = ""
    user_display_name: str = ""
    user_avatar_url: str = ""
    user_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
