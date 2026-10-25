# Disposable real-Polkit test

Do not run `smoke.py` or `cancel_agent.py` directly on the host. These files
belong only in the test container: they create a local rule and an agent that
always cancels, limited to the disposable `tester` user and the `/usr/bin/id`
program.

```bash
podman build -t localhost/makebench-polkit-test:local -f checks/polkit/Containerfile checks/polkit
podman run --rm --network none --pids-limit 256 localhost/makebench-polkit-test:local
podman image rm localhost/makebench-polkit-test:local
```

Use rootless Podman, without `--privileged` and without mounting host
directories. The build installs dependencies only in the image. The test uses no
password and does not change the host's rules, packages or services; `id -u`
proves privilege only inside the container's namespace. Expected results:
authorised 0/uid 0; refused 127; agent cancels 126. The user's real graphical
agent is not part of this test.

Tests of the Qt supervisor, without elevation, are in `tests/test_runtime.py`.
