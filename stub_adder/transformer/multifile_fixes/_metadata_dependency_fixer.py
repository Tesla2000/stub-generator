import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar
from typing import Literal

import tomlkit

from stub_adder._stub_tuple import _StubTuple
from stub_adder.transformer.multifile_fixes._base import MultiFileFix


class MetadataDependencyFixer(MultiFileFix):
    type: Literal["metadata_dependency"] = "metadata_dependency"
    max_attempts: int = 3

    _IMPORT_FAIL_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"error: (?P<failing>[\w.]+) failed to import.*"
        r"(?:ModuleNotFoundError: No module named '(?P<module>[^']+)'"
        r"|ImportError: (?:The (?P<lib>\w+) library is not installed|Error: No module named '(?P<mod2>[^']+)'))",
        re.DOTALL,
    )

    @staticmethod
    def _is_external(failing: str, missing: str) -> bool:
        """Return True when the missing module is an external dependency.

        Internal failures look like:
            failing = "google.auth.aio.transport.mtls"
            missing = "google.auth.aio.transport.mtls"
        Both share the top-level package "google" → internal, not a dep to add.

        External failures look like:
            failing = "google.auth.aio.transport.aiohttp"
            missing = "aiohttp"
        Different top-level packages → missing is a real external dependency.
        """
        return failing.split(".")[0] != missing.split(".")[0]

    def _external_missing(self, errors: Iterable[str]) -> set[str]:
        result: set[str] = set()
        for e in errors:
            m = self._IMPORT_FAIL_RE.search(e)
            if not m:
                continue
            failing = m.group("failing") or ""
            mod = m.group("module") or m.group("lib") or m.group("mod2")
            if mod and self._is_external(failing, mod):
                result.add(mod.split(".")[0])
        return result

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return bool(self._external_missing(errors))

    def __call__(
        self,
        affected_stubs: list[_StubTuple],
        errors_by_file: dict[Path, list[str]],
        completed: dict[Path, str],
        layer_deps: dict[Path, set[Path]],
        stubs_dir: Path,
    ) -> None:
        missing_modules: set[str] = set()
        for errors in errors_by_file.values():
            missing_modules |= self._external_missing(errors)

        if not missing_modules:
            return

        metadata_path = stubs_dir / "METADATA.toml"
        if not metadata_path.exists():
            return

        doc = tomlkit.parse(metadata_path.read_text())
        existing_deps: list[str] = list(doc.get("dependencies", []))
        existing_names = {
            re.split(r"[<>=!;\[]", d)[0].strip().lower() for d in existing_deps
        }

        for mod in sorted(missing_modules):
            pkg = mod.replace("_", "-")
            if pkg.lower() not in existing_names:
                existing_deps.append(pkg)

        if existing_deps:
            doc["dependencies"] = existing_deps

        metadata_path.write_text(tomlkit.dumps(doc))
