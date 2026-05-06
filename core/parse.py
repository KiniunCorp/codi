"""Tolerant Dockerfile parser used across the CODI toolchain."""

from __future__ import annotations

import shlex
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "DockerInstruction",
    "DockerStage",
    "DockerfileDocument",
    "DockerfileParseError",
    "parse_dockerfile",
]


class DockerfileParseError(RuntimeError):
    """Raised when the parser cannot interpret the provided Dockerfile."""


@dataclass(slots=True)
class DockerInstruction:
    """Represents a single Dockerfile instruction."""

    keyword: str
    arguments: str
    original: str

    def to_dict(self) -> dict[str, str]:  # pragma: no cover - trivial serialization
        return {"keyword": self.keyword, "arguments": self.arguments, "original": self.original}


@dataclass(slots=True)
class DockerStage:
    """Container build stage extracted from a Dockerfile."""

    base_image: str
    name: str | None
    instructions: list[DockerInstruction] = field(default_factory=list)
    args: dict[str, str | None] = field(default_factory=dict)
    env: dict[str, str | None] = field(default_factory=dict)
    copied_sources: list[str] = field(default_factory=list)
    exposes: list[str] = field(default_factory=list)
    workdirs: list[str] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)
    cmds: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - trivial serialization
        return {
            "base_image": self.base_image,
            "name": self.name,
            "instructions": [instruction.to_dict() for instruction in self.instructions],
            "args": self.args,
            "env": self.env,
            "copied_sources": self.copied_sources,
            "exposes": self.exposes,
            "workdirs": self.workdirs,
            "entrypoints": self.entrypoints,
            "cmds": self.cmds,
        }


@dataclass(slots=True)
class DockerfileDocument:
    """Top-level representation of a Dockerfile."""

    args: dict[str, str | None]
    env: dict[str, str | None]
    stages: list[DockerStage]

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - trivial serialization
        return {
            "args": self.args,
            "env": self.env,
            "stages": [stage.to_dict() for stage in self.stages],
        }


def parse_dockerfile(source: str | Path) -> DockerfileDocument:
    """Parse a Dockerfile from a string or path into a structured representation."""

    text = _load_source(source)
    logical_lines = list(_coalesce_lines(text.splitlines()))

    global_args: dict[str, str | None] = {}
    global_env: dict[str, str | None] = {}
    stages: list[DockerStage] = []
    current_stage: DockerStage | None = None

    for logical_line in logical_lines:
        stripped = logical_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        keyword, _, tail = stripped.partition(" ")
        keyword_upper = keyword.upper()
        arguments = _collapse_whitespace_outside_quotes(tail.strip())
        instruction = DockerInstruction(
            keyword=keyword_upper, arguments=arguments, original=stripped
        )

        if keyword_upper == "FROM":
            current_stage = _start_new_stage(arguments)
            stages.append(current_stage)
            continue

        if current_stage is None and keyword_upper not in {"ARG", "ENV"}:
            raise DockerfileParseError(
                "Dockerfile must start with a FROM, ARG, or ENV instruction; found "
                f"{keyword_upper!r} instead."
            )

        target_stage = current_stage

        if keyword_upper == "ARG":
            name, value = _parse_name_value(arguments)
            if target_stage is None:
                global_args[name] = value
            else:
                target_stage.args[name] = value
                target_stage.instructions.append(instruction)
            global_args.setdefault(name, value)
            continue

        if keyword_upper == "ENV":
            assignments = _parse_env(arguments)
            if target_stage is None:
                global_env.update(assignments)
            else:
                target_stage.env.update(assignments)
                target_stage.instructions.append(instruction)
            for key, value in assignments.items():
                if key not in global_env:
                    global_env[key] = value
            continue

        if target_stage is None:
            # This can happen when ENV/ARG are the only globals and no FROM has been processed yet.
            raise DockerfileParseError("Encountered instruction before any stage was defined.")

        target_stage.instructions.append(instruction)
        _enrich_stage_metadata(target_stage, keyword_upper, arguments)

    if not stages:
        raise DockerfileParseError("Dockerfile does not declare any build stages.")

    return DockerfileDocument(args=global_args, env=global_env, stages=stages)


def _load_source(source: str | Path) -> str:
    if isinstance(source, Path):
        return source.read_text()
    if "\n" in source or "FROM" in source.upper():
        return source
    potential_path = Path(source)
    if potential_path.exists():
        return potential_path.read_text()
    raise DockerfileParseError("Unable to load Dockerfile source; provide text or a valid path.")


def _coalesce_lines(lines: Iterable[str]) -> Iterator[str]:
    buffer = ""
    for raw_line in lines:
        line = raw_line.rstrip()
        if not line:
            if buffer:
                yield buffer
                buffer = ""
            continue

        if buffer:
            buffer += " " + line.lstrip()
        else:
            buffer = line

        if buffer.endswith("\\"):
            buffer = buffer[:-1].rstrip()
            continue

        yield buffer
        buffer = ""

    if buffer:
        yield buffer


def _start_new_stage(arguments: str) -> DockerStage:
    tokens = arguments.split()
    if not tokens:
        raise DockerfileParseError("FROM instruction is missing a base image.")

    base_image = tokens[0]
    name = None

    if len(tokens) >= 3 and tokens[1].upper() == "AS":
        name = tokens[2]

    return DockerStage(base_image=base_image, name=name)


def _parse_name_value(argument: str) -> tuple[str, str | None]:
    if "=" not in argument:
        return argument, None
    name, _, value = argument.partition("=")
    return name.strip(), value.strip() or None


def _parse_env(argument: str) -> dict[str, str | None]:
    assignments: dict[str, str | None] = {}
    if not argument:
        return assignments

    for chunk in shlex.split(argument, posix=True):
        if "=" not in chunk:
            assignments[chunk] = None
            continue
        name, _, value = chunk.partition("=")
        assignments[name] = value or None

    return assignments


def _enrich_stage_metadata(stage: DockerStage, keyword: str, arguments: str) -> None:
    upper_keyword = keyword.upper()
    if upper_keyword in {"COPY", "ADD"}:
        if "--from=" in arguments:
            for part in arguments.split():
                if part.startswith("--from="):
                    stage.copied_sources.append(part.split("=", maxsplit=1)[1])
    elif upper_keyword == "EXPOSE":
        stage.exposes.extend(arg.strip() for arg in arguments.split() if arg.strip())
    elif upper_keyword == "WORKDIR":
        stage.workdirs.append(arguments)
    elif upper_keyword == "ENTRYPOINT":
        stage.entrypoints.append(arguments)
    elif upper_keyword == "CMD":
        stage.cmds.append(arguments)


def _collapse_whitespace_outside_quotes(value: str) -> str:
    if not value:
        return value

    result: list[str] = []
    in_single = False
    in_double = False
    escape = False
    saw_space = False

    for char in value:
        if escape:
            result.append(char)
            escape = False
            saw_space = False
            continue

        if char == "\\":
            result.append(char)
            escape = True
            continue

        if char == "'" and not in_double:
            in_single = not in_single
            result.append(char)
            saw_space = False
            continue

        if char == '"' and not in_single:
            in_double = not in_double
            result.append(char)
            saw_space = False
            continue

        if char in {" ", "\t"} and not in_single and not in_double:
            if saw_space:
                continue
            result.append(" ")
            saw_space = True
            continue

        result.append(char)
        saw_space = False

    return "".join(result)
