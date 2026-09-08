"""Launches the orchestrator as a subprocess for the web panel.

The orchestrator always runs as a separate process, never in-process
with the web server, for isolation: a crash or hang in Playwright/the
adapters can't take down the web panel, and each run gets its own
clean interpreter state. Commands are built as argv lists and passed
to asyncio.create_subprocess_exec — never shell=True — so supplier
names and other run parameters can't be used for shell injection.
Skip names are validated against ALLOWED_SUPPLIERS before the
subprocess is even built.
"""

import asyncio

from loguru import logger

from web.sse import create_bus, remove_bus, get_bus
from web.db import insert_run, update_run
from settings import settings

ALLOWED_SUPPLIERS: set[str] = set()

_procs: dict[str, asyncio.subprocess.Process] = {}


async def launch_run(
    run_id: str,
    parts_total: int,
    suppliers: list[str],
    skip: list[str],
    parallel: bool = False,
) -> None:
    for name in skip:
        if name not in ALLOWED_SUPPLIERS:
            raise ValueError(f"unknown supplier in skip list: {name}")

    await insert_run(run_id, parts_total, suppliers)
    bus = create_bus(run_id)

    cmd = [
        settings.hawkeye_python,
        "-u",
        "main.py",
        "run",
        "--input",
        settings.parts_file,
        "--tiers",
        settings.pricing_tiers_file,
        "--output",
        settings.output_dir,
    ]
    for name in skip:
        cmd += ["--skip", name]
    if parallel:
        cmd += ["--parallel"]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=settings.hawkeye_dir,
    )
    _procs[run_id] = proc

    try:
        if proc.stdout is None:
            logger.error(f"[{run_id}] subprocess stdout is None")
            return

        async for line in proc.stdout:
            decoded = line.decode(errors="replace").rstrip()
            await bus.publish(decoded)
            logger.info(f"[{run_id}] {decoded}")

        await proc.wait()

        status = "done" if proc.returncode == 0 else "error"
        # TODO: parse parts_found/errors/duration_sec from the orchestrator's
        # log output instead of hardcoding zeros.
        await update_run(run_id, status, parts_found=0, errors=0, duration_sec=0.0)
        logger.info(f"run {run_id} finished with status {status}")
    finally:
        _procs.pop(run_id, None)
        remove_bus(run_id)


async def stop_run(run_id: str) -> bool:
    bus = get_bus(run_id)
    if bus is None:
        return False

    proc = _procs.pop(run_id, None)
    if proc is not None and proc.returncode is None:
        proc.terminate()
        await proc.wait()

    remove_bus(run_id)
    await update_run(run_id, "stopped", parts_found=0, errors=0, duration_sec=0.0)
    return True
