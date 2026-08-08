"""boxlab — the Box driver for the protocol benchmark.

A lean, Claude-only adaptation of box-wheel's control layer (see ../README.md for
what was carried over and why). Nothing here ships with the `hypergraph-protocol`
distribution; it is research tooling for this repo alone.

Layering mirrors box-wheel's, minus everything the benchmark does not need:

    config    -> credentials, env-gated, with explicit provenance (no I/O on Box)
    box_ctl   -> box lifecycle + the ssh-on-stdin primitive (the only mutations)
    provision -> the arm-aware bash script that turns a bare box into an agent host
    runner    -> detached `claude -p` launch, status probe, stop, log tail

The pure script builders (`provision.build_script`, `runner.build_launch_script`)
do no I/O so they can be asserted as strings in tests — box-wheel's convention,
kept because a provisioning bug costs a whole run to discover otherwise.
"""
