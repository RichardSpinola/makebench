"""Task center functions. They run only when you test the application with F5."""

import sys


def simulate_installation(ctx, value):
    """Show progress and stderr without installing or changing packages."""
    ctx.log(f"Simulating installation: {value}")
    ctx.set_value("progress_task", 0)
    for progress in (20, 40, 60, 80, 100):
        ctx.run(sys.executable, ["-c", "import time; time.sleep(0.15)"])
        ctx.set_value("progress_task", progress)
        ctx.log(f"Progress: {progress}%")
    ctx.run_script('printf "Example warning; the task still succeeds.\\n" >&2')
    ctx.log("Simulation complete. No application was installed.")


def long_task(ctx, value):
    """Produce output for one minute; Stop run cancels this ordinary task."""
    ctx.run(
        sys.executable,
        [
            "-u",
            "-c",
            "import time\nfor i in range(60):\n print(f'Step {i+1}/60', flush=True)\n time.sleep(1)",
        ],
    )
