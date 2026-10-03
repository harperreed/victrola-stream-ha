# ABOUTME: Tests for the media source: browsing turntables and resolving live streams.
# ABOUTME: Resolve must read the stream URL fresh from the device, never the snapshot.
import pytest
from homeassistant.components.media_source import (
    Unresolvable,
    async_browse_media,
    async_resolve_media,
    generate_media_source_id,
)
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.victrola_stream.const import DOMAIN, URL_PATHS
from tests.conftest import setup_entry
from tests.fake_device import FakeVictrola

# The documented URL shapes (victrola-stream-go docs/live-stream-discovery.md).
# The recorded device sat in network standby, so its own fixture URLs read "".
_HLS_URL = "http://192.0.2.10:8143/pl.m3u8"
_FLAC_URL = "http://192.0.2.10:44323/stream.flac"


def _string_value(text: str) -> list[dict[str, str]]:
    return [{"type": "string_", "string_": text}]


async def _setup(hass: HomeAssistant, fake: FakeVictrola) -> MockConfigEntry:
    await async_setup_component(hass, "media_source", {})
    return await setup_entry(hass, fake)


async def test_browse_root_lists_turntable(hass, fake):
    entry = await _setup(hass, fake)

    root = await async_browse_media(hass, generate_media_source_id(DOMAIN, ""))

    assert len(root.children) == 1
    turntable = root.children[0]
    assert turntable.identifier == entry.entry_id
    assert turntable.title == "Record Player"  # fixture settings:/deviceName
    assert turntable.can_expand is True
    assert turntable.can_play is False

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_browse_turntable_lists_three_formats(hass, fake):
    entry = await _setup(hass, fake)

    turntable = await async_browse_media(
        hass, generate_media_source_id(DOMAIN, entry.entry_id)
    )

    assert [child.identifier for child in turntable.children] == [
        f"{entry.entry_id}/hls",
        f"{entry.entry_id}/mp3",
        f"{entry.entry_id}/flac",
    ]
    assert all(child.can_play for child in turntable.children)
    assert not any(child.can_expand for child in turntable.children)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_resolve_reads_url_fresh(hass, fake):
    # The fixture itself reads "" (recorded in standby); set the real URL only
    # after setup so a resolve built from the setup-time snapshot would still
    # see "" and wrongly raise, while a fresh read sees the new value.
    entry = await _setup(hass, fake)
    fake.values[URL_PATHS["flac"]] = _string_value(_FLAC_URL)

    played = await async_resolve_media(
        hass, generate_media_source_id(DOMAIN, f"{entry.entry_id}/flac"), None
    )

    assert played.url == _FLAC_URL
    assert played.mime_type == "audio/ogg"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_resolve_offline_raises_unresolvable(hass, fake):
    entry = await _setup(hass, fake)
    fake.values[URL_PATHS["hls"]] = _string_value(_HLS_URL)
    fake.offline = True

    with pytest.raises(Unresolvable):
        await async_resolve_media(
            hass, generate_media_source_id(DOMAIN, f"{entry.entry_id}/hls"), None
        )

    fake.offline = False  # let unload's push-loop teardown reach the device
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_resolve_empty_url_raises_unresolvable(hass, fake):
    # R8: the recorded fixture sat in network standby, so every URL_PATHS
    # node already reads "" with no extra setup.
    entry = await _setup(hass, fake)
    assert fake.values[URL_PATHS["mp3"]] == _string_value("")

    with pytest.raises(Unresolvable):
        await async_resolve_media(
            hass, generate_media_source_id(DOMAIN, f"{entry.entry_id}/mp3"), None
        )

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
