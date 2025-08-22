import pytest

from aurora.config import (
    AbstractDataclass,
    BaseConfig,
    ChannelConfig,
    GlobalConfig,
    GuildConfig,
)


def test_abstract_dataclass_cannot_be_instantiated():
    with pytest.raises(TypeError):
        AbstractDataclass()  # type: ignore


def test_direct_subclass_of_abstract_cannot_be_instantiated():
    class Direct(AbstractDataclass):
        pass

    with pytest.raises(TypeError):
        Direct()  # type: ignore


def test_indirect_subclass_can_be_instantiated():
    class Direct2(AbstractDataclass):
        pass

    class Indirect(Direct2):
        pass

    obj = Indirect()
    assert isinstance(obj, Indirect)


def test_base_config_cannot_be_instantiated():
    with pytest.raises(TypeError):
        BaseConfig()  # type: ignore


def test_base_config_from_dict_raises():
    with pytest.raises(TypeError):
        BaseConfig.from_dict({})  # type: ignore


@pytest.mark.parametrize(
    "input_url,expected",
    [
        ("https://api.letta.ai", "https://api.letta.ai/"),
        ("https://api.letta.ai/", "https://api.letta.ai/"),
        ("https://localhost:8234", "https://localhost:8234/"),
        ("https://localhost:8234/", "https://localhost:8234/"),
    ],
)
def test_global_config_trailing_slash_added(input_url, expected):
    cfg = GlobalConfig(letta_base_url=input_url)
    assert cfg.letta_base_url == expected


def test_global_config_invalid_url_raises():
    with pytest.raises(ValueError):
        GlobalConfig(letta_base_url="example.com")
    with pytest.raises(ValueError):
        GlobalConfig(letta_base_url="not a url")


def test_global_config_from_dict_roundtrip():
    orig = GlobalConfig(letta_base_url="https://api.letta.ai/v1")
    d = orig.to_dict()
    rebuilt = GlobalConfig.from_dict(d)
    assert rebuilt == orig
    assert rebuilt.letta_base_url.endswith("/")


@pytest.mark.parametrize(
    "config_class",
    [GlobalConfig, GuildConfig, ChannelConfig],
)
def test_config_to_dict_roundtrip(config_class):
    orig = config_class()
    d = orig.to_dict()
    rebuilt = config_class.from_dict(d)
    assert rebuilt == orig


def test_guild_config_defaults():
    g = GuildConfig()
    assert g.enabled is False
    assert g.channels == []
    assert g.agent_id is None
    assert g.respond_to_generic is False
    assert g.respond_to_mentions is True
    assert g.respond_to_replies is True
    assert g.enable_timer is True
    assert g.min_timer_interval_minutes == 5
    assert g.max_timer_interval_minutes == 15
    assert g.firing_probability == 0.1


def test_channel_config_excludes_agent_id_and_channels():
    c = ChannelConfig()
    assert hasattr(c, "enabled")
    assert not hasattr(c, "agent_id")
    assert not hasattr(c, "channels")


def test_channel_config_field_defaults_match_guild_config_subset():
    g = GuildConfig()
    c = ChannelConfig()
    shared = [
        "enabled",
        "respond_to_generic",
        "respond_to_mentions",
        "respond_to_replies",
        "enable_timer",
        "min_timer_interval_minutes",
        "max_timer_interval_minutes",
        "firing_probability",
    ]
    for name in shared:
        assert getattr(c, name) == getattr(g, name)


def test_modifying_channel_config_does_not_affect_guild_config():
    g = GuildConfig()
    c = ChannelConfig()
    c.enabled = True
    assert g.enabled is False
    assert c.enabled is True


def test_global_config_mutation_independent_instances():
    a = GlobalConfig()
    b = GlobalConfig()
    a.surface_errors = True
    assert b.surface_errors is False
