# ABOUTME: Lists each turntable's live stream in Home Assistant's media browser.
# ABOUTME: Resolve always re-reads the stream URL from the device, never the snapshot.
from __future__ import annotations

from homeassistant.components.media_player import MediaClass, MediaType
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .const import DOMAIN, NODE_DEVICE_NAME, URL_PATHS
from .coordinator import VictrolaConfigEntry
from .nsdk import NsdkConnectionError, NsdkError

# URL_PATHS keys to this stream's resolved mime type.
_MIME_TYPES: dict[str, str] = {
    "hls": "application/vnd.apple.mpegurl",
    "mp3": "audio/mpeg",
    "flac": "audio/ogg",
}

# URL_PATHS keys to this stream's browse title, in display order.
_FORMAT_TITLES: dict[str, str] = {
    "hls": "Live (HLS)",
    "mp3": "Live (MP3)",
    "flac": "Live (FLAC, Ogg)",
}


async def async_get_media_source(hass: HomeAssistant) -> VictrolaMediaSource:
    """Set up the Victrola Stream media source."""
    return VictrolaMediaSource(hass)


class VictrolaMediaSource(MediaSource):
    """Offers each turntable's live stream as playable media.

    Browsing walks a snapshot (root -> turntable -> formats); resolving a
    format always reads the device fresh, since a stream URL's port can
    change on every reconnect and must never be handed out stale.
    """

    name = "Victrola Stream"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        """Browse the root (turntables) or one turntable (its stream formats)."""
        if not item.identifier:
            return self._browse_root()
        return self._browse_turntable(self._loaded_entry(item.identifier))

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve one stream format to a playable URL, read fresh from the device."""
        entry_id, _, fmt = (item.identifier or "").partition("/")
        if fmt not in URL_PATHS:
            raise Unresolvable(f"Not a Victrola stream format: {item.identifier!r}")
        entry = self._loaded_entry(entry_id)
        try:
            value = await entry.runtime_data.client.get_value(URL_PATHS[fmt])
        except (NsdkError, NsdkConnectionError) as err:
            raise Unresolvable(f"Could not read the {fmt} stream URL: {err}") from err
        url = value.as_str()
        if not url:
            raise Unresolvable(f"No {fmt} stream is available right now")
        return PlayMedia(url=url, mime_type=_MIME_TYPES[fmt])

    def _browse_root(self) -> BrowseMediaSource:
        """One child per loaded config entry, titled with its device name."""
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier="",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title=self.name,
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.DIRECTORY,
            children=[
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=entry.entry_id,
                    media_class=MediaClass.DIRECTORY,
                    media_content_type=MediaType.MUSIC,
                    title=self._device_name(entry),
                    can_play=False,
                    can_expand=True,
                )
                for entry in self.hass.config_entries.async_loaded_entries(DOMAIN)
            ],
        )

    def _browse_turntable(self, entry: VictrolaConfigEntry) -> BrowseMediaSource:
        """Three children, one per URL_PATHS format, each directly playable."""
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=entry.entry_id,
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title=self._device_name(entry),
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.MUSIC,
            children=[
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{entry.entry_id}/{fmt}",
                    media_class=MediaClass.MUSIC,
                    media_content_type=_MIME_TYPES[fmt],
                    title=title,
                    can_play=True,
                    can_expand=False,
                )
                for fmt, title in _FORMAT_TITLES.items()
            ],
        )

    @staticmethod
    def _device_name(entry: VictrolaConfigEntry) -> str | None:
        return entry.runtime_data.data.value(NODE_DEVICE_NAME).as_str()

    def _loaded_entry(self, entry_id: str) -> VictrolaConfigEntry:
        """The loaded config entry for entry_id; never a stale/unloaded one."""
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.state is not ConfigEntryState.LOADED:
            raise Unresolvable(f"Unknown turntable: {entry_id!r}")
        return entry
