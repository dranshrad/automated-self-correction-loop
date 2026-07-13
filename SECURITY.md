# Security Policy

## What this tool does

ASCL writes LLM-generated Python to disk and executes it via `subprocess` under a hard timeout. That is inherently risky.

## Threat model (v1)

**In scope / mitigated (best effort):**

- Infinite loops → process-group `SIGKILL` after `--timeout`
- Log bombs → stdout/stderr byte caps
- Fork bombs / runaway allocs → Unix `RLIMIT_NPROC`, `RLIMIT_AS`, `RLIMIT_CPU` via `preexec_fn`
- Accidental reuse of host API keys in child processes → runner strips `*_API_KEY` / provider keys from the child environment
- Cheap rejection of broken syntax / obvious lint errors before spawning behavioral tests

**Out of scope for v1 (not a sandbox):**

- Containerization, seccomp, network namespaces, or filesystem jails
- Malicious exfiltration via non-env channels
- Multi-tenant untrusted workloads

**Recommendation:** run ASCL only on trusted prompts and machines. For untrusted tasks, wrap executions in an external sandbox (Docker, Firejail, gVisor, etc.).

## Reporting a vulnerability

Please open a private security advisory on GitHub (or email the maintainer listed in the repository) with:

- A clear description of the issue
- Steps to reproduce
- Impact assessment

Do not file public issues for exploitable sandbox escapes until a fix or mitigation is available.
