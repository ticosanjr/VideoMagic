from videoflow.application.dubbing import translate_text


class Client:
    def __init__(self) -> None:
        self.prompt = ""

    def complete_json(self, prompt: str, schema_name: str) -> dict:
        self.prompt = prompt
        assert schema_name == "videoflow.translation"
        return {"text": "Olá, mundo"}


def test_translation_uses_target_language_and_returns_text() -> None:
    client = Client()
    result = translate_text(client, "Hello, world", "pt")
    assert result == "Olá, mundo"
    assert "pt" in client.prompt
    assert "Hello, world" in client.prompt
