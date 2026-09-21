from lumia_briefing_room.config import Config, PlayerConfig, load_config, save_config
from lumia_briefing_room.pipeline.nickname import learn_nickname


def test_learn_nickname_saves_first_reading_when_unset(tmp_path):
    path = tmp_path / "config.json"
    save_config(Config(), path)

    assert learn_nickname(path, "내테스트닉") is True
    assert load_config(path).player.nickname == "내테스트닉"


def test_learn_nickname_keeps_existing_nickname(tmp_path):
    path = tmp_path / "config.json"
    save_config(Config(player=PlayerConfig(nickname="직접입력")), path)

    assert learn_nickname(path, "다른이름") is False
    assert load_config(path).player.nickname == "직접입력"


def test_learn_nickname_ignores_empty_reading(tmp_path):
    path = tmp_path / "config.json"

    assert learn_nickname(path, None) is False
    assert learn_nickname(path, "  ") is False
    assert not path.exists()
