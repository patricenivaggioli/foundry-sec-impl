# Sandbox Patterns

**Audience:** a platform engineer choosing how to enforce [Principle IX](../../constitution.md#ix-sandbox-by-infrastructure-not-by-prompt) and [`spec.md` §9.1](../../spec.md#91-sandbox).

The principle is uncompromising: network egress and filesystem write boundaries are enforced by the runtime, not by the prompt. This page presents three reference topologies that satisfy it. None is a recommendation; pick whichever fits your existing infrastructure.

If a pattern below seems insufficient for your environment, the answer is to harden the pattern, not to relax the principle.

---

## Pattern A: single-host containers (gVisor / Kata)

```
        Host VM
        ┌──────────────────────────────────────────────┐
        │  Network egress filter (host-level firewall) │
        │  ↑                                            │
        │  │ allow: LLM provider, issue tracker,        │
        │  │        testbed, nothing else by default    │
        │  ↓                                            │
        │ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐  │
        │ │ Agent  │ │ Agent  │ │ Agent  │ │ Agent  │  │
        │ │ gVisor │ │ gVisor │ │ gVisor │ │ gVisor │  │
        │ │ ro mnt │ │ ro mnt │ │ ro mnt │ │ ro mnt │  │
        │ └────────┘ └────────┘ └────────┘ └────────┘  │
        └──────────────────────────────────────────────┘
```

**When:** dev environments, < ~16 agents, single-target evaluations.

**Boundary:**
- gVisor (or Kata Containers) provides the kernel-level isolation; an agent breaking out of its container does not gain host privileges.
- Host-level firewall (iptables, nftables, host security group) enforces the egress allowlist.

**Read-only mounts (FR-108):**
- Target source: `/target/source:ro`.
- Agent prompts and config: `/agent/config:ro`.
- The sandbox definition itself: `/sandbox/definition:ro`.

**Trade-offs:**
- Cheap to operate.
- The boundary is the gVisor sandbox + the host firewall together. Both must work.
- Single-host scaling limits.

**Verification ritual** (do NOT skip):
```
docker exec -it <agent-container> /bin/sh
# inside the container:
curl --connect-timeout 3 --max-time 10 https://attacker.example       # MUST be blocked
echo X >> /etc/hosts                                                  # MUST be denied
echo X >> /target/source/file.go                                      # MUST be denied (read-only)
curl --fail --connect-timeout 3 --max-time 10 https://allowlisted-llm.example   # MUST succeed
```

If any of the four behaves wrongly, the sandbox is misconfigured. Fix and re-verify.

---

## Pattern B: multi-host VMs

```
   Network policy plane
   ┌─────────────────────────────────────┐
   │ allowlist: LLM provider, tracker,    │
   │            testbed                   │
   └─────────────────────────────────────┘
              │ enforced at switch / router / cloud SG layer
              ▼
   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
   │  VM (agent role │  │  VM (agent role │  │  VM (agent role │
   │  Detector  x N) │  │  Triager   x N) │  │  Validator x N) │
   │  ───────────────│  │  ───────────────│  │  ───────────────│
   │  ro mnt source  │  │  ro mnt source  │  │  ro mnt source  │
   │  ro mnt prompts │  │  ro mnt prompts │  │  ro mnt prompts │
   └─────────────────┘  └─────────────────┘  └─────────────────┘
```

**When:** medium scale; one VM (or VM-set) per agent role.

**Boundary:**
- VM-level isolation; an agent inside one VM cannot reach into another VM's process space.
- Network policy enforced at the switch / router or cloud security-group layer; not at the OS layer of the VM.

**Read-only mounts (FR-108):**
- Same as Pattern A; mounts are per-VM.

**Trade-offs:**
- Stronger isolation than containers.
- Operationally heavier (more VMs to manage; per-role tuning).
- Cross-role coordination uses the substrate, not direct network calls.

**Verification ritual:** run the same four commands in each VM. Each VM must isolate independently.

---

## Pattern C: cloud-isolated workers (Firecracker / serverless)

```
   ┌──────────────────────────────────────────────────────┐
   │                  Cloud control plane                 │
   │  ────────────────────────────────────────────────────│
   │   Per-task Firecracker microVM                       │
   │   spawned by Orchestrator on demand                  │
   │   torn down on completion                            │
   │                                                      │
   │   ┌────────┐   ┌────────┐   ┌────────┐               │
   │   │ Agent  │   │ Agent  │   │ Agent  │               │
   │   │ μVM    │   │ μVM    │   │ μVM    │               │
   │   │ ro mnt │   │ ro mnt │   │ ro mnt │               │
   │   └────────┘   └────────┘   └────────┘               │
   │                                                      │
   │   Egress through cloud-managed proxy                 │
   │   (allowlist enforced at proxy layer)                │
   └──────────────────────────────────────────────────────┘
```

**When:** production scale; high concurrency; strong tenant isolation needed.

**Boundary:**
- Firecracker microVMs (or AWS Lambda equivalents) provide per-task isolation.
- A managed egress proxy enforces the allowlist; agent traffic cannot bypass it because the network namespace forces all egress through the proxy.

**Read-only mounts (FR-108):**
- Mounts are per-microVM, recreated on each spawn. Source code is fetched into the microVM at start, marked read-only, and discarded at teardown.

**Trade-offs:**
- Highest cost.
- Strongest Principle IX guarantees (per-task disposable VMs; per-task egress filter).
- Requires cloud-provider support for the chosen runtime.

**Verification ritual:** automate the four-command verification as part of microVM startup; fail-fast if any check passes when it should not.

---

## Cross-pattern requirements

Regardless of pattern, the following are non-negotiable:

### Egress allowlist (FR-107)

The default allowlist is:

- LLM provider endpoint(s).
- Issue tracker endpoint(s).
- Testbed endpoint(s) (if configured).
- Nothing else.

Add a destination only if the operator explicitly approves it; document why in the configuration.

### Read-only mounts (FR-108)

- Target source.
- Agent configuration.
- Agent prompts.
- The sandbox definition itself.

A read-write mount of any of these reproduces a failure mode Principle IX exists to prevent.

### Pivot-point disclosure (FR-109)

Inform the operator at setup time:

> Allowlisted destinations are pivot points. An agent that can reach the testbed can reach whatever the testbed can reach; an agent that can reach the issue tracker can post content humans will read. The sandbox bounds blast radius; it does not eliminate it.

Document this in your environment's runbook. Operators must not be surprised.

### Defense in depth (FR-110, FR-111)

Prompt-level hard rules are kept *as defense in depth*, not as the boundary. They state in plain language what the agent must never do. The default minimums apply when operating against any non-disposable testbed:

- No denial of service.
- No data deletion or modification outside the testbed.
- No credential changes.
- No actions affecting users other than designated test users.

## Failure modes and how to recognize them

| Failure mode | Symptom | Fix |
|---|---|---|
| Network policy not enforced at runtime | Egress to non-allowlisted host succeeds in verification ritual. | Re-check enforcement layer; ensure agent traffic actually traverses it. |
| Read-write mount mistakenly applied | Write to `/target/source/...` succeeds. | Recheck mount flags; recheck filesystem driver behavior. |
| Container escape | Agent process visible from host outside its namespace. | Switch from plain Docker to gVisor / Kata / Firecracker. |
| Sandbox definition writable | Agent can edit its own constraints. | Mount `/sandbox/definition:ro` and verify. |
| Allowlist drift | Hosts added "for testing" never removed. | Periodic audit. The allowlist is part of the spec configuration; treat it as such. |

## See also

- [`observability-checklist.md`](observability-checklist.md) — health checks for the sandbox (FR-125).
- [`../architecture/substrate-contracts.md`](../architecture/substrate-contracts.md) — the substrate contract that the sandboxed agents satisfy.
- [`../principles/anti-patterns.md#ix-sandbox-by-infrastructure-not-by-prompt`](../principles/anti-patterns.md#ix-sandbox-by-infrastructure-not-by-prompt) — failure modes the principle prevents.
- [`../../spec.md#91-sandbox`](../../spec.md#91-sandbox) — canonical requirements.
