"""
Provider registry and automatic platform loader for updater.
"""

from typing import Type
from updater.config import IS_LINUX, IS_MACOS, IS_WINDOWS
from updater.providers.base import BaseProvider
from updater.providers.eget import EgetProvider
from updater.providers.git_repos import GitProvider
from updater.providers.vencord import VencordProvider
from updater.providers.npm import NpmProvider
from updater.providers.bun import BunProvider
from updater.providers.cargo import CargoProvider
from updater.providers.pipx import PipxProvider
from updater.providers.uv import UvProvider
from updater.providers.gh_extensions import GhExtProvider
from updater.providers.standalone import StandaloneProvider

# Platform-specific provider imports
if IS_LINUX:
    from updater.providers.apt import AptProvider
    from updater.providers.deb import DebProvider
    from updater.providers.flatpak import FlatpakProvider
    from updater.providers.snap import SnapProvider
else:
    AptProvider = None  # type: ignore
    DebProvider = None  # type: ignore
    FlatpakProvider = None  # type: ignore
    SnapProvider = None  # type: ignore

if IS_MACOS:
    from updater.providers.brew import BrewProvider
    from updater.providers.mas import MasProvider
else:
    BrewProvider = None  # type: ignore
    MasProvider = None  # type: ignore

if IS_WINDOWS:
    from updater.providers.winget import WingetProvider
    from updater.providers.scoop import ScoopProvider
    from updater.providers.choco import ChocoProvider
else:
    WingetProvider = None  # type: ignore
    ScoopProvider = None  # type: ignore
    ChocoProvider = None  # type: ignore

def get_available_providers(git_repos: list[str] | None = None) -> list[BaseProvider]:
    """Instantiate and return all providers active on the current platform."""
    all_provider_classes: list[Type[BaseProvider]] = [
        EgetProvider,
        VencordProvider,
        NpmProvider,
        BunProvider,
        CargoProvider,
        PipxProvider,
        UvProvider,
        GhExtProvider,
        StandaloneProvider,
    ]

    if IS_LINUX:
        all_provider_classes.extend([
            AptProvider,  # type: ignore
            DebProvider,  # type: ignore
            FlatpakProvider,  # type: ignore
            SnapProvider,  # type: ignore
        ])

    if IS_MACOS:
        all_provider_classes.extend([
            BrewProvider,  # type: ignore
            MasProvider,  # type: ignore
        ])

    if IS_WINDOWS:
        all_provider_classes.extend([
            WingetProvider,  # type: ignore
            ScoopProvider,  # type: ignore
            ChocoProvider,  # type: ignore
        ])

    instances: list[BaseProvider] = []

    # Git provider needs optional custom repos passed in
    if GitProvider.is_available():
        instances.append(GitProvider(git_repos))

    for p_cls in all_provider_classes:
        if p_cls is not None and p_cls.is_available():
            instances.append(p_cls())

    # Sort providers by priority
    instances.sort(key=lambda p: p.priority)
    return instances
