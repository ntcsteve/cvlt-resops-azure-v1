# The observability stack

One VM. Three containers. Nothing installed on any protected workload.

```
 resops gate     judge once   ──▶  evidence/
 resops metrics  publish many ──▶  curl ──▶ pushgateway ──▶ prometheus ──▶ grafana
```

It **scrapes nothing**. There is no agent, no node_exporter, no service discovery
and no network path from this stack to a workload. The numbers come from evidence
a run already wrote, so a dashboard can never disagree with the bundle beside it.

## Deploy

```bash
terraform -chdir=infra/observability init
terraform -chdir=infra/observability apply

# lock it to your own IP for a private run
terraform -chdir=infra/observability apply -var allowed_source=203.0.113.7
```

Then:

```bash
terraform -chdir=infra/observability output grafana_url
terraform -chdir=infra/observability output -raw grafana_password   # user: admin
```

## Publish a run

```bash
python3 -m resops gate    config/estate.yaml    # judge
python3 -m resops metrics config/estate.yaml \
  | curl --data-binary @- "$(terraform -chdir=infra/observability output -raw pushgateway_url)/metrics/job/resops"
```

`terraform output -raw publish_command` prints that second line with the IP filled in.

Put it after the gate step in CI and the wall stays current with no extra plumbing.

## Destroy — always

```bash
terraform -chdir=infra/observability destroy
```

**This stack is cattle.** No volumes, no persistence, nothing worth keeping. Losing
it loses nothing: rebuild is one apply and the numbers return the next time
anything runs `resops metrics`.

## Test it without spending anything

```bash
./infra/observability/test-stack.sh          # ~1 min, needs docker running
KEEP=1 ./infra/observability/test-stack.sh   # leave it up to poke at
```

Nothing in this stack is Azure-specific — it is three containers and four config
files, and Azure only supplies a VM to run Docker on. So the part that can break
is testable on a laptop. The script runs **the real files in `stack/`**, the same
ones cloud-init embeds; a test against a copy would prove nothing about what
deploys.

```
 1  containers reach healthy
 2  pushgateway accepts a real `resops metrics` payload
 3  prometheus has the series
 4  grafana's datasource is healthy
 5  grafana LOADED the dashboard      provisioning failures are otherwise SILENT
 6  every panel query returns data    ◀ catches an empty panel before a room does
```

Check 6 is the one worth having. Static validation cannot catch a query that
parses correctly and matches nothing.

**Only these need a real Azure apply**, and only once: cloud-init running on
Azure's image, the NSG letting 3000/9091 through, the public IP being reachable,
and B2s being big enough. Everything else is proven locally, for free, repeatedly.

## The panels

```
 Provably recoverable      % of workloads the gate would PROMOTE, with 90d trend
 Where the estate is stuck workloads by blocking stage — the stage IS the fix
 Attestation age           days since anything opened the recovery point and read it
 Control coverage          workloads with PASS evidence per control, per framework
 Every workload            rung · blocker · verdict, one row each
```

Dashboards are **code**: provisioned from `dashboard.json` at boot with
`allowUiUpdates: false`. Edit the file and re-apply; do not click.

## Two things to know before you screenshot it

**Control coverage will be mostly red, and that is correct.** It measures whether
recovery was *proven* — a real restore, opened and read — not whether a policy
exists. Most compliance dashboards are green because they measure the latter. If
this one ever goes green without work, something is wrong with it.

**The crosswalk is indicative.** It supports a resilience programme; it is not a
compliance attestation. That warning is on the dashboard itself, not just here,
because a Grafana panel makes a mapping look more official than a markdown file
does.

## Trade-offs taken knowingly

| Choice | Why | Cost |
|---|---|---|
| Ports 3000 + 9091 open by default | the room reaches Grafana, CI reaches the pushgateway | mitigate with `allowed_source`; destroy the same day |
| No volumes | rebuild is trivial, nothing to back up | history resets on redeploy |
| `Standard_B2s` | BS quota family, never starves a workload VM | still takes 2 of the 10 shared regional vCPUs, leaving 8 |
| VNet `10.250.0.0/16` | workloads are all `10.123.0.0/16` and overlap | none — push needs no peering |
