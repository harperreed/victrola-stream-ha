# ABOUTME: Select platform: output mode, default speaker and enum settings.
# ABOUTME: Each option maps to a typed device write, confirmed by read-back.
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    NODE_RCA_MODE,
    NODE_SET_DEFAULT_OUTPUT,
    NODE_SONOS_DELAY,
    NODE_STREAMING_QUALITY,
    OUTPUT_TOGGLES,
    SPEAKERS_PATH,
)
from .coordinator import VictrolaConfigEntry, VictrolaState
from .entity import VictrolaEntity, VictrolaEntityDescriptionMixin
from .nsdk import NsdkValue


def _sonos_with_speakers(state: VictrolaState) -> bool:
    """Default speaker only has choices while the device streams to Sonos."""
    return state.output == "sonos" and bool(state.speakers)


@dataclass(frozen=True, kw_only=True)
class VictrolaSelectEntityDescription(
    SelectEntityDescription, VictrolaEntityDescriptionMixin
):
    """Extra fields for the enum settings; Output and Default speaker ignore them.

    options_map: option key -> device value, e.g. "sound_quality" -> "soundQuality".
    device_type: the NSDK typed value's type, e.g. "forceLowBitrate".
    """

    options_map: dict[str, str] | None = None
    device_type: str | None = None


def _enum_description(
    key: str, node: str, options_map: dict[str, str], device_type: str
) -> VictrolaSelectEntityDescription:
    """An enum setting: one node, one device type, option key -> device value."""
    return VictrolaSelectEntityDescription(
        key=key,
        translation_key=key,
        node=node,
        entity_category=EntityCategory.CONFIG,
        options=list(options_map),
        options_map=options_map,
        device_type=device_type,
    )


_OUTPUT_DESCRIPTION = VictrolaSelectEntityDescription(
    key="output",
    translation_key="output",
    options=list(OUTPUT_TOGGLES),
)

_DEFAULT_SPEAKER_DESCRIPTION = VictrolaSelectEntityDescription(
    key="default_speaker",
    translation_key="default_speaker",
    node=SPEAKERS_PATH,
    available_fn=_sonos_with_speakers,
)


class VictrolaOutputSelect(VictrolaEntity, SelectEntity):
    """Which output the turntable streams to; selecting clears the others."""

    entity_description: VictrolaSelectEntityDescription

    @property
    def current_option(self) -> str | None:
        return self.coordinator.data.output

    async def async_select_option(self, option: str) -> None:
        await self._async_write(OUTPUT_TOGGLES[option], NsdkValue.of_bool(True))


class VictrolaDefaultSpeakerSelect(VictrolaEntity, SelectEntity):
    """The Sonos speaker the turntable defaults to; empty outside Sonos mode."""

    entity_description: VictrolaSelectEntityDescription

    @property
    def options(self) -> list[str]:
        return [speaker.title for speaker in self.coordinator.data.speakers]

    @property
    def current_option(self) -> str | None:
        return next(
            (s.title for s in self.coordinator.data.speakers if s.preferred), None
        )

    async def async_select_option(self, option: str) -> None:
        # The first match if titles repeat, matching how `options` lists them.
        speaker = next(s for s in self.coordinator.data.speakers if s.title == option)
        await self._async_activate(
            NODE_SET_DEFAULT_OUTPUT,
            {"type": speaker.type, "id": speaker.id},
            reread_speakers=True,
        )


class VictrolaEnumSelect(VictrolaEntity, SelectEntity):
    """A device setting whose typed value is a fixed enum of strings."""

    entity_description: VictrolaSelectEntityDescription

    @property
    def current_option(self) -> str | None:
        description = self.entity_description
        device_value = self.coordinator.data.value(description.node).payload
        reverse_map = {v: k for k, v in description.options_map.items()}
        return reverse_map.get(device_value)

    async def async_select_option(self, option: str) -> None:
        description = self.entity_description
        device_value = description.options_map[option]
        await self._async_write(
            description.node, NsdkValue(description.device_type, device_value)
        )


SELECT_ENTITIES: tuple[
    tuple[VictrolaSelectEntityDescription, type[VictrolaEntity]], ...
] = (
    (_OUTPUT_DESCRIPTION, VictrolaOutputSelect),
    (_DEFAULT_SPEAKER_DESCRIPTION, VictrolaDefaultSpeakerSelect),
    (
        _enum_description(
            "streaming_quality",
            NODE_STREAMING_QUALITY,
            {
                "connection_quality": "connectionQuality",
                "sound_quality": "soundQuality",
                "lossless_quality": "losslessQuality",
            },
            "forceLowBitrate",
        ),
        VictrolaEnumSelect,
    ),
    (
        _enum_description(
            "sonos_audio_delay",
            NODE_SONOS_DELAY,
            {"min": "min", "med": "med", "high": "high", "max": "max"},
            "adchlsLatency",
        ),
        VictrolaEnumSelect,
    ),
    (
        _enum_description(
            "rca_mode",
            NODE_RCA_MODE,
            {"switching": "switching", "simultaneous": "simultaneous"},
            "adchlsDACMode",
        ),
        VictrolaEnumSelect,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VictrolaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one select per description whose node exists on this device."""
    coordinator = entry.runtime_data
    async_add_entities(
        entity_cls(coordinator, description)
        for description, entity_cls in SELECT_ENTITIES
        if description.exists(coordinator.data)
    )
