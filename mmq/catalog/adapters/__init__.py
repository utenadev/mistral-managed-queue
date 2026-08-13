"""Provider plugins for catalog fetching.

Each provider (OpenRouter, NVIDIA NIM, Mistral) has its own plugin
that implements the ProviderPlugin protocol.
"""

from mmq.catalog.adapters.base import ProviderPlugin
from mmq.catalog.adapters.openrouter import OpenRouterPlugin
from mmq.catalog.adapters.nvidia_nim import NvidiaNimPlugin
from mmq.catalog.adapters.mistral import MistralPlugin

__all__ = [
    "ProviderPlugin",
    "OpenRouterPlugin",
    "NvidiaNimPlugin",
    "MistralPlugin",
]
