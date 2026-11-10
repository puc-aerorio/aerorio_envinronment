# Coding standards

Judgement calls for review. Mechanical rules are enforced by the static test layer (`tests/static/`: shellcheck, hadolint, ruff check and format, a reason on every suppression, compose validity), so they are not repeated here.

## Language

The team reads Portuguese; tooling and agent-facing docs are English.

- **Portuguese:** comments and messages in shell scripts, compose files and the `Dockerfile`; `README.md`; anything a team member reads at the terminal (`run.sh`, `start_simulation.sh` output).
- **English:** test code and its comments, `GLOSSARY.md`, ADRs, `docs/`.

Match the file you're in; a Portuguese script gets Portuguese comments, including the reason on a suppression.

## Domain words

Name things with the terms in `GLOSSARY.md` (Host, Container, Image, Simulation, Photo, Ground Station, …), in code, tests, comments and issues alike.

## Tests

A test asserts only what a team member or maintainer could observe from outside: a command's output or exit code, a file in the Workspace, an HTTP response from uav-api, or the Container config the launcher resolves. It does not inspect script internals or file contents directly.

## Ports

A change that moves, adds or removes a port updates `docs/network.md` in the same PR. Host networking stays on (ADR-0003).
