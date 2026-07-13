from types import SimpleNamespace

from app.services.ai_config import get_ai_scene_config


class FakeSession:
    def __init__(self, item):
        self.item = item

    def get(self, _model, _scene):
        return self.item


def test_scene_can_override_model_while_reusing_global_provider():
    saved_scene = SimpleNamespace(
        provider="legacy-provider",
        model="legacy-scene-model",
        system_prompt="scene-specific prompt",
    )

    config = get_ai_scene_config(
        FakeSession(saved_scene),
        "ai_analysis",
        "global-model",
        "default prompt",
        "global-provider",
    )

    assert config["provider"] == "global-provider"
    assert config["model"] == "legacy-scene-model"
    assert config["system_prompt"] == "scene-specific prompt"
