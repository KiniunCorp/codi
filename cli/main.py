"""Entry point for the CODI command line interface."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import typer
import uvicorn
from core.analyzer import build_analysis_payload, perform_analysis
from core.build import BuildRunner, BuildRunnerError, CmdRunSummary
from core.config import CodiEnvironment
from core.dashboard import collect_dashboard_data
from core.llm import (
    AssistCandidate,
    AssistContext,
    AssistDetection,
    ImageMetricsSnapshot,
    LLMRankingService,
    LocalLLMError,
)
from core.parse import DockerfileParseError
from core.perf import CPUPerfThresholds, run_cpu_sanity_suite, write_cpu_perf_report
from core.render import RenderContext, render_for_stack
from core.report import ReportGenerationError, generate_report
from core.security import SecurityPolicyError, enforce_airgap_guard, validate_or_raise
from core.store import create_run_store
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

console = Console()
app = typer.Typer(
    help="Rules-first Dockerfile optimizer for the CODI project.",
    no_args_is_help=True,
    add_completion=False,
)


@dataclass
class CLIContext:
    """Shared state propagated to subcommands."""

    out_dir: Path
    verbose: bool
    config: CodiEnvironment


def _configure_logging(verbose: bool) -> None:
    """Initialise application logging using Rich for pretty output."""

    level = logging.DEBUG if verbose else logging.INFO
    handler = RichHandler(
        console=console,
        rich_tracebacks=True,
        show_time=False,
        show_path=False,
    )
    logging.basicConfig(level=level, format="%(message)s", handlers=[handler])


@app.callback()
def _cli(  # pragma: no cover - exercised indirectly via commands
    ctx: typer.Context,
    out: Path | None = typer.Option(
        None,
        "--out",
        "-o",
        help="Directory where CODI writes run artefacts.",
        exists=False,
        file_okay=False,
        dir_okay=True,
        writable=True,
        resolve_path=True,
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Increase logging verbosity."),
) -> None:
    """Configure shared CLI context before executing any command."""

    config = CodiEnvironment.from_env()
    _configure_logging(verbose)
    enforce_airgap_guard()
    selected_out = out or config.output_root
    out_path = selected_out.expanduser().resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    config = config.with_output_root(out_path)

    logger = logging.getLogger("codi.cli")
    logger.debug("Output root set to %s", out_path)
    logger.debug("LLM enabled: %s (endpoint=%s)", config.llm.enabled, config.llm.endpoint or "n/a")
    logger.debug("AIRGAP enabled: %s", config.airgap_enabled)

    ctx.obj = CLIContext(out_dir=out_path, verbose=verbose, config=config)


def _acknowledge_stub(command_name: str) -> None:
    """Display a notice for commands that are scaffolded but not yet fully implemented."""

    console.print(
        Panel.fit(
            f"[bold yellow]The `{command_name}` command is scaffolded and will be fully implemented in an upcoming release.[/]\n"
            "Use this CLI to explore available verbs; functional behaviour follows once dependent modules land.",
            title="CODI",
            border_style="yellow",
        )
    )


def _get_context(ctx: typer.Context) -> CLIContext:
    if ctx.obj is None:
        raise typer.Exit(code=1)
    return cast(CLIContext, ctx.obj)


def _locate_dockerfile(project_root: Path) -> Path:
    candidates = [project_root / "Dockerfile"]
    for relative in ("docker/Dockerfile", "Dockerfile.dev", "Dockerfile.release"):
        candidates.append(project_root / relative)

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    console.print(
        Panel(
            f"Unable to locate a Dockerfile under {project_root}.",
            title="Analysis failed",
            border_style="red",
        )
    )
    raise typer.Exit(code=1)


def _display_cmd_summary(summary: CmdRunSummary | None) -> None:
    if summary is None:
        return

    analysis = summary.analysis or {}
    runtime = summary.runtime or {}

    if not analysis and not runtime:
        return

    if analysis:
        table = Table(title="CMD Instruction (original)", show_lines=False)
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Value")
        table.add_row("Instruction", str(analysis.get("original") or "—"))
        table.add_row("Form", str(analysis.get("form") or "—"))
        stage = analysis.get("stage") if isinstance(analysis.get("stage"), dict) else {}
        stage_label = stage.get("name") or (f"#{stage.get('index')}" if stage else "runtime")
        table.add_row("Stage", str(stage_label))
        parsed = analysis.get("parsed") if isinstance(analysis.get("parsed"), dict) else {}
        executable = parsed.get("executable")
        if executable:
            table.add_row("Executable", str(executable))
        argv = parsed.get("argv")
        if isinstance(argv, list) and argv:
            joined = ", ".join(str(token) for token in argv)
            table.add_row("argv", f"[{joined}]")
        console.print(table)

        flags = analysis.get("flags") if isinstance(analysis.get("flags"), dict) else {}
        if flags:
            flag_table = Table(title="CMD Flags", show_lines=False)
            flag_table.add_column("Flag", style="cyan")
            flag_table.add_column("State", justify="center")
            for key, value in sorted(flags.items()):
                flag_table.add_row(key, "yes" if value else "no")
            console.print(flag_table)

    if runtime:
        runtime_table = Table(title="CMD Rewrite", show_lines=False)
        runtime_table.add_column("Field", style="cyan", no_wrap=True)
        runtime_table.add_column("Value")
        runtime_table.add_row("Applied", "yes" if runtime.get("applied") else "no")
        rewrite_id = runtime.get("rewrite_id")
        if rewrite_id:
            runtime_table.add_row("Rewrite ID", str(rewrite_id))
        preferred_form = runtime.get("preferred_form")
        if preferred_form:
            runtime_table.add_row("Preferred form", str(preferred_form))
        runtime_instruction = runtime.get("runtime_instruction")
        if runtime_instruction:
            runtime_table.add_row("Runtime instruction", str(runtime_instruction))
        original_instruction = runtime.get("original_instruction")
        if original_instruction and original_instruction != runtime_instruction:
            runtime_table.add_row("Original instruction", str(original_instruction))
        rationale = runtime.get("rationale_comment")
        if rationale:
            runtime_table.add_row("Rationale", str(rationale))
        console.print(runtime_table)

        builder_promotions = runtime.get("builder_promotions")
        if isinstance(builder_promotions, list) and builder_promotions:
            promotions_table = Table(title="Builder promotions", show_lines=False)
            promotions_table.add_column("Action")
            for item in builder_promotions:
                promotions_table.add_row(str(item))
            console.print(promotions_table)

        post_copy_steps = runtime.get("post_copy_steps")
        if isinstance(post_copy_steps, list) and post_copy_steps:
            post_table = Table(title="Post-copy steps", show_lines=False)
            post_table.add_column("Action")
            for item in post_copy_steps:
                post_table.add_row(str(item))
            console.print(post_table)

        runtime_flags = runtime.get("flags") if isinstance(runtime.get("flags"), dict) else {}
        if runtime_flags:
            runtime_flag_table = Table(title="Runtime flags", show_lines=False)
            runtime_flag_table.add_column("Flag", style="cyan")
            runtime_flag_table.add_column("State", justify="center")
            for key, value in sorted(runtime_flags.items()):
                runtime_flag_table.add_row(key, "yes" if value else "no")
            console.print(runtime_flag_table)

        benefits = _derive_cli_cmd_benefits(analysis, runtime)
        if benefits:
            benefit_panel = Panel.fit(
                "\n".join(f"- {item}" for item in benefits),
                title="CMD Benefits",
                border_style="cyan",
            )
            console.print(benefit_panel)


def _derive_cli_cmd_benefits(analysis: dict[str, Any], runtime: dict[str, Any]) -> list[str]:
    benefits: list[str] = []
    flags = analysis.get("flags") if isinstance(analysis.get("flags"), dict) else {}
    builder_promotions = (
        runtime.get("builder_promotions")
        if isinstance(runtime.get("builder_promotions"), list)
        else []
    )
    preferred_form = runtime.get("preferred_form")

    if flags.get("uses_shell_form") and runtime.get("applied") and preferred_form == "exec":
        benefits.append("Converted shell-form runtime command to exec-form entrypoint.")

    if flags.get("installs_packages") and builder_promotions:
        benefits.append("Relocated package installation steps into the builder stage.")

    if flags.get("runs_migrations") and builder_promotions:
        benefits.append("Flagged migration commands for build-time execution.")

    script_flags = (
        runtime.get("script_flags") if isinstance(runtime.get("script_flags"), dict) else {}
    )
    if flags.get("missing_script") and not script_flags.get("missing_script", False):
        benefits.append("Surfaced missing script references for remediation.")

    return benefits


@app.command()
def analyze(
    ctx: typer.Context,
    target: Path = typer.Argument(
        Path("."),
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to the project root containing a Dockerfile to analyze.",
    ),
) -> None:
    """Inspect a project directory and prepare optimisation insights."""

    context = _get_context(ctx)
    logger = logging.getLogger("codi.cli")
    logger.info("Analyzing project at %s", target)
    project_root = target
    dockerfile_path = _locate_dockerfile(project_root)

    try:
        analysis = perform_analysis(project_root, dockerfile_path=dockerfile_path)
        validate_or_raise(analysis.document)
    except DockerfileParseError as exc:
        console.print(Panel(str(exc), title="Analysis failed", border_style="red"))
        raise typer.Exit(code=1) from exc
    except SecurityPolicyError as exc:
        console.print(Panel(str(exc), title="Security policy violation", border_style="red"))
        raise typer.Exit(code=1) from exc

    detection = analysis.detection
    stack_label = detection.stack if detection.stack in {"node", "python", "java"} else None
    store = create_run_store(
        context.out_dir,
        stack=stack_label,
        label=f"{project_root.name}-analysis",
    )
    logger.debug("Analysis artefacts will be written to %s", store.paths.root)

    store.snapshot_file(dockerfile_path, destination_name="Dockerfile")

    analysis_payload = build_analysis_payload(analysis)
    analysis_payload["project_root"] = str(project_root)
    analysis_payload["dockerfile_path"] = str(dockerfile_path)
    analysis_payload["mode"] = "analyze"
    store.write_json("metadata/analysis.json", analysis_payload)
    store.write_json("metadata/detect.json", asdict(detection))
    store.write_json("metadata/environment.json", context.config.to_metadata())

    summary_table = Table(title="Dockerfile Summary", show_lines=False)
    summary_table.add_column("Metric", style="cyan", no_wrap=True)
    summary_table.add_column("Value")
    summary_table.add_row("Stages", str(analysis.summary.get("stage_count", 0)))
    summary_table.add_row("Base images", ", ".join(analysis.summary.get("bases", [])))
    summary_table.add_row(
        "Package manager", "yes" if analysis.summary.get("uses_pkg_manager") else "no"
    )
    summary_table.add_row("Runs as root", "yes" if analysis.summary.get("runs_as_root") else "no")
    summary_table.add_row(
        "Cache mounts", "yes" if analysis.summary.get("has_cache_mount") else "no"
    )
    summary_table.add_row(
        "Exposed ports", ", ".join(analysis.summary.get("exposed_ports", []) or ["—"])
    )

    console.print(
        Panel.fit(
            "Analysis completed successfully.\n"
            f"Stack: {detection.stack} (confidence {detection.confidence:.2f})\n"
            f"Artefacts: {store.paths.root}",
            title="CODI",
            border_style="green",
        )
    )
    console.print(summary_table)

    if analysis.cmd and analysis.cmd.dominant:
        cmd_details = analysis.cmd.dominant
        cmd_table = Table(title=f"{cmd_details.instruction} Analysis", show_lines=False)
        cmd_table.add_column("Field", style="cyan", no_wrap=True)
        cmd_table.add_column("Value")
        cmd_table.add_row("Form", cmd_details.form)
        cmd_table.add_row("Original", cmd_details.original)
        parsed_summary = []
        if "argv" in cmd_details.parsed:
            parsed_summary.append(f"argv={cmd_details.parsed['argv']}")
        if "command" in cmd_details.parsed:
            parsed_summary.append(f"command={cmd_details.parsed['command']}")
        if "shell" in cmd_details.parsed:
            parsed_summary.append(f"shell={cmd_details.parsed['shell']}")
        cmd_table.add_row("Parsed", "; ".join(parsed_summary) or "—")
        console.print(cmd_table)

        flags_table = Table(title="CMD Flags", show_lines=False)
        flags_table.add_column("Flag", style="cyan")
        flags_table.add_column("State", justify="center")
        for key, value in sorted(cmd_details.flags.items()):
            flags_table.add_row(key, "yes" if value else "no")
        console.print(flags_table)

        if cmd_details.scripts:
            scripts_table = Table(title="Referenced Scripts", show_lines=False)
            scripts_table.add_column("Path", style="cyan")
            scripts_table.add_column("Exists", justify="center")
            scripts_table.add_column("Flags")
            scripts_table.add_column("Warnings")
            for script in cmd_details.scripts:
                scripts_table.add_row(
                    script.path,
                    "yes" if script.exists else "no",
                    ", ".join(key for key, state in sorted(script.flags.items()) if state) or "—",
                    "; ".join(script.warnings) or "—",
                )
            console.print(scripts_table)

        if cmd_details.warnings:
            console.print(
                Panel(
                    "\n".join(cmd_details.warnings),
                    title="CMD Warnings",
                    border_style="yellow",
                )
            )
        if cmd_details.recommendations:
            console.print(
                Panel(
                    "\n".join(cmd_details.recommendations),
                    title="Recommendations",
                    border_style="cyan",
                )
            )


@app.command()
def rewrite(
    ctx: typer.Context,
    target: Path = typer.Argument(
        Path("."),
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to the project root to rewrite Dockerfiles for.",
    ),
) -> None:
    """Generate candidate Dockerfile rewrites for the supplied project."""

    context = _get_context(ctx)
    logging.getLogger("codi.cli").info("Rewriting Dockerfiles under %s", target)
    logging.getLogger("codi.cli").debug("Outputs will be staged in %s", context.out_dir)
    _acknowledge_stub("rewrite")


@app.command()
def run(
    ctx: typer.Context,
    target: Path = typer.Argument(
        Path("."),
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to the project root to build and benchmark.",
    ),
    real: bool = typer.Option(
        False,
        "--real",
        help="Execute real container builds instead of dry-run analysis.",
    ),
) -> None:
    """Execute the full build pipeline for original and candidate Dockerfiles."""

    context = _get_context(ctx)
    logger = logging.getLogger("codi.cli")
    logger.info("Running builds for %s", target)
    logger.debug("Real build toggle: %s", real)
    logger.debug("Outputs will be staged in %s", context.out_dir)

    try:
        runner = BuildRunner(target, context.out_dir, real_builds=real, environment=context.config)
        result = runner.run()
    except BuildRunnerError as exc:
        console.print(Panel(str(exc), title="Build failed", border_style="red"))
        raise typer.Exit(code=1) from exc

    table = Table(title="Build metrics", show_lines=False)
    table.add_column("Variant", style="cyan", no_wrap=True)
    table.add_column("Layers", justify="right")
    table.add_column("Size (MB)", justify="right")
    table.add_column("Seconds", justify="right")

    original_metrics = result.original.metrics
    table.add_row(
        "original",
        str(original_metrics.layers),
        f"{original_metrics.size_bytes / (1024 * 1024):.1f}",
        f"{original_metrics.build_seconds:.2f}",
    )

    for candidate in result.candidates:
        metrics = candidate.metrics
        label = f"{candidate.rule_id}"
        if candidate.name:
            label = f"{label}\n{candidate.name}"
        table.add_row(
            label,
            str(metrics.layers),
            f"{metrics.size_bytes / (1024 * 1024):.1f}",
            f"{metrics.build_seconds:.2f}",
        )

    console.print(
        Panel.fit(
            f"Run completed (ID: [bold]{result.run_id}[/])\n"
            f"Stack: {result.stack}\n"
            f"Artefacts: {result.run_dir}",
            title="CODI",
            border_style="green",
        )
    )
    console.print(table)

    _display_cmd_summary(result.cmd)

    if result.assist:
        lines = ["LLM Assist", result.assist.summary]
        if result.assist.recommendation:
            rec = result.assist.recommendation
            confidence_text = (
                f" (confidence {rec.confidence:.2f})" if rec.confidence is not None else ""
            )
            source_text = f" [{rec.source}]" if rec.source else ""
            lines.append(
                f"Recommendation: {rec.rule_id} — {rec.reason}{confidence_text}{source_text}"
            )
        console.print(Panel.fit("\n".join(lines), title="Assist", border_style="cyan"))


@app.command()
def perf(
    ctx: typer.Context,
    demo_root: Path = typer.Option(
        Path("demo"),
        "--demo-root",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Root directory containing demo stacks (node/python/java).",
    ),
    stack: list[str] = typer.Option(
        None,
        "--stack",
        "-s",
        help="Stack identifier to include (node, python, java). Repeat to specify multiple.",
    ),
    analysis_budget: float = typer.Option(
        3.0,
        "--analysis-budget",
        min=0.1,
        help="Maximum allowed analysis duration in seconds.",
    ),
    total_budget: float = typer.Option(
        300.0,
        "--total-budget",
        min=1.0,
        help="Maximum allowed end-to-end runtime in seconds (default 5 minutes).",
    ),
    export_json: Path | None = typer.Option(
        None,
        "--export-json",
        help="Optional path to write the performance report JSON (defaults to <out>/perf/cpu_perf_report.json).",
        resolve_path=True,
    ),
) -> None:
    """Run CPU-only performance sanity checks across demo stacks."""

    context = _get_context(ctx)
    selected_stacks = list(stack) if stack else ["node", "python", "java"]

    available_projects = {
        "node": demo_root / "node",
        "python": demo_root / "python",
        "java": demo_root / "java",
    }

    project_roots: list[Path] = []
    for item in selected_stacks:
        lowered = item.lower()
        if lowered not in available_projects:
            raise typer.BadParameter(f"Unsupported stack '{item}'. Choose from node, python, java.")
        project_path = available_projects[lowered]
        if not project_path.exists():
            raise typer.BadParameter(
                f"Demo project missing for stack '{lowered}' at {project_path}"
            )
        project_roots.append(project_path)

    thresholds = CPUPerfThresholds(
        analysis_seconds=analysis_budget,
        total_seconds=total_budget,
    )

    perf_output_root = context.out_dir / "perf"
    report = run_cpu_sanity_suite(
        project_roots,
        perf_output_root,
        thresholds=thresholds,
        environment=context.config,
    )

    table = Table(title="CPU Sanity Results", show_lines=False)
    table.add_column("Stack", style="cyan", no_wrap=True)
    table.add_column("Project")
    table.add_column("Analysis (s)", justify="right")
    table.add_column("Render (s)", justify="right")
    table.add_column("Total (s)", justify="right")
    table.add_column("Status", style="magenta")

    for result in report.results:
        message = f" ({result.message})" if result.message else ""
        table.add_row(
            result.stack,
            result.project,
            f"{result.analysis_seconds:.2f}",
            f"{result.render_seconds:.2f}",
            f"{result.total_seconds:.2f}",
            f"{result.status}{message}",
        )

    export_path = export_json or (perf_output_root / "cpu_perf_report.json")
    write_cpu_perf_report(report, export_path)

    status_style = "green" if report.passed else "red"
    console.print(
        Panel.fit(
            "CPU sanity suite completed.\n"
            f"Runs output: {perf_output_root}\n"
            f"Report: {export_path}\n"
            f"Thresholds — analysis: {thresholds.analysis_seconds:.2f}s, total: {thresholds.total_seconds:.2f}s\n"
            f"Overall status: [bold]{'PASSED' if report.passed else 'FAILED'}[/]",
            title="CODI",
            border_style=status_style,
        )
    )
    console.print(table)


@app.command()
def dashboard(
    ctx: typer.Context,
    runs: Path = typer.Option(
        None,
        "--runs",
        help="Root directory containing CODI run artefacts (defaults to the CLI --out path).",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
    ),
    export_json: Path = typer.Option(
        None,
        "--export-json",
        help="Path to write the aggregated dashboard data (defaults to <out>/dashboard/dashboard.json).",
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
    relative_to: Path = typer.Option(
        None,
        "--relative-to",
        help="Rewrite artefact paths relative to this directory (e.g. docs/dashboard).",
        resolve_path=True,
    ),
) -> None:
    """Aggregate run artefacts into a dashboard-friendly data set."""

    context = _get_context(ctx)
    runs_root = runs or context.out_dir
    output_path = export_json or (context.out_dir / "dashboard" / "dashboard.json")

    try:
        data = collect_dashboard_data(runs_root, relative_to=relative_to)
    except FileNotFoundError as exc:
        console.print(Panel(str(exc), title="Dashboard failed", border_style="red"))
        raise typer.Exit(code=1) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    table = Table(title="Dashboard summary", show_lines=False)
    table.add_column("Stack", style="cyan")
    table.add_column("Runs", justify="right")
    table.add_column("Avg Δ Size (%)", justify="right")
    table.add_column("Avg Δ Build (s)", justify="right")
    table.add_column("Best Run", overflow="fold")

    for entry in data.get("stacks", []):
        table.add_row(
            entry.get("stack", "?"),
            str(entry.get("run_count", 0)),
            f"{entry.get('avg_size_delta_pct', 0.0):.2f}",
            f"{entry.get('avg_build_delta_seconds', 0.0):.2f}",
            entry.get("best_run_id") or "—",
        )

    console.print(
        Panel.fit(
            "Dashboard data generated.\n"
            f"Runs scanned: {data.get('run_count', 0)}\n"
            f"Runs root: {data.get('runs_root')}\n"
            f"Output JSON: {output_path}",
            title="CODI",
            border_style="green",
        )
    )
    console.print(table)


@app.command()
def report(
    ctx: typer.Context,
    run_dir: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to a CODI run directory produced by `codi run`.",
    ),
) -> None:
    """Render human-friendly artefacts summarising a CODI optimisation run."""

    _get_context(ctx)
    logger = logging.getLogger("codi.cli")
    logger.info("Generating report for run at %s", run_dir)

    try:
        artefacts = generate_report(run_dir)
    except ReportGenerationError as exc:
        console.print(Panel(str(exc), title="Report failed", border_style="red"))
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            "Report generated successfully.\n"
            f"Markdown: {artefacts.markdown_path}\n"
            f"HTML: {artefacts.html_path}",
            title="CODI",
            border_style="green",
        )
    )


@app.command()
def serve(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host", help="Address to bind the FastAPI server to."),
    port: int = typer.Option(8000, "--port", "-p", help="Port for the FastAPI server."),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (development only)."),
    workers: int = typer.Option(1, "--workers", help="Number of worker processes."),
) -> None:
    """Launch the CODI FastAPI service."""

    _get_context(ctx)
    if reload and workers != 1:
        console.print(
            Panel(
                "[bold yellow]Reload mode forces a single worker. Adjusting `--workers` to 1 for stability.[/]",
                title="CODI",
                border_style="yellow",
            )
        )
        workers = 1

    console.print(
        Panel.fit(
            "Starting CODI API server...\n" f"Host: {host}\n" f"Port: {port}\n" f"Reload: {reload}",
            title="CODI",
            border_style="green",
        )
    )

    uvicorn.run(
        "api.server:app", host=host, port=port, reload=reload, workers=workers, log_level="info"
    )


@app.command()
def all(
    ctx: typer.Context,
    target: Path = typer.Argument(
        Path("."),
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to the project root for the end-to-end workflow.",
    ),
) -> None:
    """Run analyze → rewrite → run → report sequentially for the given project."""

    context = _get_context(ctx)
    logging.getLogger("codi.cli").info("Executing full CODI pipeline for %s", target)
    logging.getLogger("codi.cli").debug("Outputs will be staged in %s", context.out_dir)
    try:
        runner = BuildRunner(target, context.out_dir, environment=context.config)
        result = runner.run()
        artefacts = generate_report(result.run_dir)
    except (BuildRunnerError, ReportGenerationError) as exc:
        console.print(Panel(str(exc), title="Pipeline failed", border_style="red"))
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            "Pipeline completed successfully.\n"
            f"Run ID: {result.run_id}\n"
            f"Markdown report: {artefacts.markdown_path}\n"
            f"HTML report: {artefacts.html_path}",
            title="CODI",
            border_style="green",
        )
    )
    _display_cmd_summary(result.cmd)
    if result.assist:
        lines = ["LLM Assist", result.assist.summary]
        if result.assist.recommendation:
            rec = result.assist.recommendation
            confidence_text = (
                f" (confidence {rec.confidence:.2f})" if rec.confidence is not None else ""
            )
            source_text = f" [{rec.source}]" if rec.source else ""
            lines.append(
                f"Recommendation: {rec.rule_id} — {rec.reason}{confidence_text}{source_text}"
            )
        console.print(Panel.fit("\n".join(lines), title="Assist", border_style="cyan"))


# ----------------------------------------------------------------------
# LLM command group
# ----------------------------------------------------------------------

llm_app = typer.Typer(
    help="LLM-assisted ranking and explanation commands.",
    no_args_is_help=True,
)
app.add_typer(llm_app, name="llm")


@llm_app.command("rank")
def llm_rank(
    ctx: typer.Context,
    target: Path = typer.Argument(
        Path("."),
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to the project root to rank candidates for.",
    ),
    limit: int = typer.Option(
        2,
        "--limit",
        "-n",
        min=1,
        max=5,
        help="Maximum number of candidates to rank.",
    ),
    model: str = typer.Option(
        None,
        "--model",
        help="Override model ID (defaults to environment setting).",
    ),
    adapter: Path = typer.Option(
        None,
        "--adapter",
        help="Override adapter path (defaults to environment setting).",
        resolve_path=True,
    ),
) -> None:
    """Rank optimization candidates using LLM assistance."""
    context = _get_context(ctx)
    logger = logging.getLogger("codi.cli")

    if not context.config.llm.enabled:
        console.print(
            Panel(
                "LLM ranking is disabled. Set LLM_ENABLED=true to enable.",
                title="LLM Disabled",
                border_style="yellow",
            )
        )
        raise typer.Exit(code=1)

    logger.info("Ranking candidates for %s", target)
    project_root = target
    dockerfile_path = _locate_dockerfile(project_root)

    try:
        analysis = perform_analysis(project_root, dockerfile_path=dockerfile_path)
        validate_or_raise(analysis.document)
    except (DockerfileParseError, SecurityPolicyError) as exc:
        console.print(Panel(str(exc), title="Analysis failed", border_style="red"))
        raise typer.Exit(code=1) from exc

    detection = analysis.detection
    stack = detection.stack if detection.stack in {"node", "python", "java"} else "node"

    # Build render context to get candidates
    render_context = RenderContext(stack=stack)
    for path_str in _collect_files_cli(project_root):
        render_context.add_file(path_str)
    for path_str in _collect_lockfiles_cli(project_root):
        render_context.add_lockfile(path_str)
    for feature in _collect_features_cli(stack, project_root):
        render_context.add_feature(feature)

    try:
        candidates = render_for_stack(render_context, limit=limit)
    except Exception as exc:
        console.print(Panel(str(exc), title="Rendering failed", border_style="red"))
        raise typer.Exit(code=1) from exc

    # Build assist context
    assist_context = _build_assist_context_cli(
        project_root=project_root,
        detection=detection,
        analysis=analysis,
        candidates=candidates,
    )

    # Create ranking service
    ranking_service = LLMRankingService.from_settings(context.config)

    try:
        result = ranking_service.rank_candidates(assist_context)
    except LocalLLMError as exc:
        console.print(Panel(str(exc), title="LLM ranking failed", border_style="red"))
        raise typer.Exit(code=1) from exc

    # Display results
    table = Table(title="LLM Ranking", show_lines=False)
    table.add_column("Rank", style="cyan", no_wrap=True, justify="center")
    table.add_column("Rule ID")
    table.add_column("Candidate ID")
    table.add_column("Score", justify="right")

    for ranked in result.ranking:
        table.add_row(
            str(ranked.rank),
            ranked.rule_id,
            ranked.candidate_id,
            f"{ranked.score:.3f}",
        )

    console.print(
        Panel.fit(
            f"LLM ranking completed.\n"
            f"Adapter: {result.adapter_version}\n"
            f"Mode: {result.llm_metrics.get('mode', 'unknown')}",
            title="CODI LLM",
            border_style="green",
        )
    )
    console.print(table)
    console.print(Panel(result.rationale, title="Rationale", border_style="cyan"))

    # Output JSON if verbose
    if context.verbose:
        output_data = {
            "ranking": [
                {
                    "rank": r.rank,
                    "candidate_id": r.candidate_id,
                    "rule_id": r.rule_id,
                    "score": r.score,
                }
                for r in result.ranking
            ],
            "rationale": result.rationale,
            "adapter_version": result.adapter_version,
            "llm_metrics": result.llm_metrics,
        }
        console.print("\n[dim]JSON output:[/]")
        console.print(json.dumps(output_data, indent=2))


@llm_app.command("explain")
def llm_explain(
    ctx: typer.Context,
    target: Path = typer.Argument(
        Path("."),
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to the project root to explain.",
    ),
) -> None:
    """Generate explanation for Dockerfile analysis using LLM."""
    context = _get_context(ctx)
    logger = logging.getLogger("codi.cli")

    if not context.config.llm.enabled:
        console.print(
            Panel(
                "LLM explanation is disabled. Set LLM_ENABLED=true to enable.",
                title="LLM Disabled",
                border_style="yellow",
            )
        )
        raise typer.Exit(code=1)

    logger.info("Generating explanation for %s", target)
    project_root = target
    dockerfile_path = _locate_dockerfile(project_root)

    try:
        analysis = perform_analysis(project_root, dockerfile_path=dockerfile_path)
        validate_or_raise(analysis.document)
    except (DockerfileParseError, SecurityPolicyError) as exc:
        console.print(Panel(str(exc), title="Analysis failed", border_style="red"))
        raise typer.Exit(code=1) from exc

    detection = analysis.detection
    stack = detection.stack if detection.stack in {"node", "python", "java"} else "node"

    # Build render context to get candidates
    render_context = RenderContext(stack=stack)
    for path_str in _collect_files_cli(project_root):
        render_context.add_file(path_str)
    for path_str in _collect_lockfiles_cli(project_root):
        render_context.add_lockfile(path_str)
    for feature in _collect_features_cli(stack, project_root):
        render_context.add_feature(feature)

    try:
        candidates = render_for_stack(render_context, limit=2)
    except Exception as exc:
        console.print(Panel(str(exc), title="Rendering failed", border_style="red"))
        raise typer.Exit(code=1) from exc

    # Build assist context
    assist_context = _build_assist_context_cli(
        project_root=project_root,
        detection=detection,
        analysis=analysis,
        candidates=candidates,
    )

    # Create ranking service
    ranking_service = LLMRankingService.from_settings(context.config)

    try:
        result = ranking_service.explain_analysis(assist_context)
    except LocalLLMError as exc:
        console.print(Panel(str(exc), title="LLM explanation failed", border_style="red"))
        raise typer.Exit(code=1) from exc

    # Display results
    console.print(
        Panel.fit(
            f"LLM explanation completed.\n" f"Adapter: {result.adapter_version}",
            title="CODI LLM",
            border_style="green",
        )
    )
    console.print(Panel(result.summary, title="Summary", border_style="cyan"))
    console.print(Panel(result.rationale, title="Rationale", border_style="cyan"))

    # Output JSON if verbose
    if context.verbose:
        output_data = {
            "summary": result.summary,
            "rationale": result.rationale,
            "adapter_version": result.adapter_version,
        }
        console.print("\n[dim]JSON output:[/]")
        console.print(json.dumps(output_data, indent=2))


def _collect_files_cli(root: Path) -> list[str]:
    """Collect relevant project files."""
    wanted = ["package.json", "requirements.txt", "pyproject.toml", "pom.xml", "Dockerfile"]
    files = []
    for name in wanted:
        path = root / name
        if path.exists():
            files.append(path.relative_to(root).as_posix())
    return files


def _collect_lockfiles_cli(root: Path) -> list[str]:
    """Collect lockfiles from project."""
    lockfiles_names = [
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "requirements.txt",
        "poetry.lock",
        "Pipfile.lock",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
    ]
    lockfiles = []
    for name in lockfiles_names:
        path = root / name
        if path.exists():
            lockfiles.append(path.relative_to(root).as_posix())
    return lockfiles


def _collect_features_cli(stack: str, root: Path) -> list[str]:
    """Collect features from project."""
    features = []
    if stack == "node":
        package_json = root / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
                dependencies: dict[str, Any] = {}
                dependencies.update(data.get("dependencies") or {})
                dependencies.update(data.get("devDependencies") or {})
                if any("next" in key.lower() for key in dependencies):
                    features.append("nextjs")
            except json.JSONDecodeError:
                pass
    elif stack == "python":
        requirements = root / "requirements.txt"
        if requirements.exists():
            content = requirements.read_text(encoding="utf-8").lower()
            if "fastapi" in content:
                features.append("fastapi")
    elif stack == "java":
        pom = root / "pom.xml"
        if pom.exists():
            content = pom.read_text(encoding="utf-8").lower()
            if "spring-boot" in content:
                features.append("spring-boot")
    return features


def _build_assist_context_cli(
    *,
    project_root: Path,
    detection: Any,
    analysis: Any,
    candidates: Sequence[Any],
) -> AssistContext:
    """Build AssistContext from CLI analysis and candidates."""
    from core.build import heuristic_metrics

    # Create original metrics snapshot
    original_metrics_dict = heuristic_metrics(
        stage_count=len(analysis.document.stages),
        features=[],
    )
    original = ImageMetricsSnapshot(
        size_bytes=original_metrics_dict["size_bytes"],
        layers=original_metrics_dict["layers"],
        build_seconds=original_metrics_dict["build_seconds"],
    )

    # Convert candidates
    assist_candidates: list[AssistCandidate] = []
    for candidate in candidates:
        candidate_metrics_dict = heuristic_metrics(stage_count=2, features=[])
        metrics = ImageMetricsSnapshot(
            size_bytes=candidate_metrics_dict["size_bytes"],
            layers=candidate_metrics_dict["layers"],
            build_seconds=candidate_metrics_dict["build_seconds"],
        )

        assist_candidates.append(
            AssistCandidate(
                rule_id=candidate.rule_id,
                name=candidate.name,
                description=candidate.description,
                rationale=list(candidate.rationale),
                policy_notes=list(candidate.policy_notes),
                metrics=metrics,
            )
        )

    # Build detection snapshot
    assist_detection = AssistDetection(
        stack=detection.stack,
        confidence=detection.confidence,
        evidence=detection.evidence,
    )

    # Collect context data
    features = _collect_features_cli(detection.stack, project_root)
    files = _collect_files_cli(project_root)
    lockfiles = _collect_lockfiles_cli(project_root)

    return AssistContext(
        project_name=project_root.name,
        detection=assist_detection,
        features=features,
        files=files,
        lockfiles=lockfiles,
        original=original,
        candidates=assist_candidates,
        rag_matches=(),
    )


def main() -> None:
    """Console script entry point for Typer."""

    app()


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    main()
