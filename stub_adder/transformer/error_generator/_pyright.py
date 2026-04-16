import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from stub_adder.transformer.error_generator._base import ErrorGeneratorBase

DiagnosticRule = Literal["error", "warning", "information", "none"]


class PyrightConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    # Mirrors typeshed's pyrightconfig.json defaults
    typeshed_path: str | None = None
    type_checking_mode: Literal["off", "basic", "standard", "strict"] = (
        "strict"
    )
    report_incomplete_stub: DiagnosticRule = "none"
    report_missing_parameter_type: DiagnosticRule = "none"
    report_unknown_member_type: DiagnosticRule = "none"
    report_unknown_parameter_type: DiagnosticRule = "none"
    report_unknown_variable_type: DiagnosticRule = "none"
    report_call_in_default_initializer: DiagnosticRule = "error"
    report_unnecessary_type_ignore_comment: DiagnosticRule = "error"
    enable_type_ignore_comments: bool = False
    report_missing_super_call: DiagnosticRule = "none"
    report_uninitialized_instance_variable: DiagnosticRule = "none"
    report_private_usage: DiagnosticRule = "none"
    report_missing_module_source: DiagnosticRule = "none"
    report_incompatible_method_override: DiagnosticRule = "none"
    report_incompatible_variable_override: DiagnosticRule = "none"
    report_property_type_mismatch: DiagnosticRule = "none"
    report_overlapping_overload: DiagnosticRule = "none"
    report_self_cls_parameter_name: DiagnosticRule = "none"
    report_deprecated: DiagnosticRule = "none"


class Pyright(ErrorGeneratorBase):
    type: Literal["pyright"] = "pyright"
    config: PyrightConfig = PyrightConfig()

    def _build_config(self) -> dict:
        return self.config.model_dump(by_alias=True, exclude_none=True)

    def generate(
        self, pyi_paths: list[Path], stubs_dir: Path
    ) -> dict[Path, list[str]]:
        """Run pyright and return per-file error lines for files with errors."""
        pyi_paths = [p.resolve() for p in pyi_paths]
        stubs_dir = stubs_dir.resolve()
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            str(stubs_dir)
            if not existing
            else f"{stubs_dir}{os.pathsep}{existing}"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as cfg_file:
            json.dump(self._build_config(), cfg_file)
            cfg_path = cfg_file.name
        try:
            result = subprocess.run(
                ["pyright", "--outputjson", "--project", cfg_path]
                + list(map(str, pyi_paths)),
                capture_output=True,
                text=True,
                env=env,
            )
        finally:
            Path(cfg_path).unlink(missing_ok=True)
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {}
        diagnostics = data.get("generalDiagnostics", [])
        errors: dict[Path, list[str]] = {}
        for diag in diagnostics:
            if diag.get("severity") == "error":
                file_path = Path(diag["file"])
                if file_path in pyi_paths:
                    line = (
                        diag.get("range", {}).get("start", {}).get("line", 0)
                        + 1
                    )
                    message = diag.get("message", "")
                    errors.setdefault(file_path, []).append(
                        f"{file_path}:{line}: error: {message}"
                    )
        return errors
