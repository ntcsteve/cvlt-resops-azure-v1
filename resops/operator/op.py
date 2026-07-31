#!/usr/bin/env python3
"""
operator/ — the headless WRITE lane. Codifies the proven ResOps climb so a
workload goes DISCOVERED -> VALIDATED with no UI and no hand-crafted payloads.

    op preflight   <run_dir>  read-only gate: az · token · hypervisor · discovered · vCPU
    op protect     <run_dir>  create the VSA vmgroup (VM added by its Azure vmId)
    op backup      <run_dir>  trigger a backup and poll to completion
    op restore     <run_dir>  derive the restore payload (token-native) + run drill
    op threatscan  <run_dir>  trigger ThreatScan on the backup copy, poll, read verdict
    op incident    <run_dir>  plant a detectable compromise in the workload (workshop only)
    op climb       <run_dir>  preflight -> protect -> backup -> threatscan -> restore
    op status      <run_dir>  show the workload's rung on the ladder (via resops) — read-only
    op gate        <run_dir>  resops gate  -> PROMOTE / HOLD (exit 0 / 1)
    op teardown    <run_dir>  CV group + GXMD sweep + terraform destroy

op DRIVES the climb (write); `resops` (the read-only star) SHOWS the ladder + runs
the gate. status/climb-end/gate all hand the workload to resops.

<run_dir> is the terraform root (normally `infra/workloads`). Two inputs, no hardcodes:
  • the `workload` output      the CONTRACT (vm_name, vm_guid, rg, location,
                               vm_size, vnet_name, subnet_id, restore_storage_account)
  • config/workshop.yaml (platform: block)  the set-once ids (hypervisor{id,name,instance_id}, plan)
Runtime specifics (subclientId, disk, recovery time) are read from the live API.

NOT here: discovery — the one gated step (403 for this token). Trigger it once in
the UI (or a scheduled job in prod) between provision and protect.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time

import yaml

from ..reads import anomaly_verdict, default_copy_id, storage_pool_id
from ._azure import az_json, az_ok
from .commvault import poll_job
from . import preflight
from ._common import CFG, HOST, HYP, REPO, client, contract, find_vm, group_id, write
from .drills import run_restore


_VSA_APP_ID = 106    # Virtual Server Agent application type — fixed across Metallic tenants
_COMMCELL_ID = 2     # CommCell ID for this Metallic instance (m036)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def require_vm(vm_name: str) -> dict:
    """The VM's /VM record, or stop with the fix if discovery hasn't run."""
    vm = find_vm(vm_name)
    if vm is None:
        raise SystemExit(f"{vm_name} not in /VM — has discovery run? (the one manual step)")
    return vm


# --------------------------------------------------------------------------- #
# validate helpers
# --------------------------------------------------------------------------- #
def _find_placeholders(obj, path: str = "") -> list:
    """Recursively find unfilled <placeholder> values in the config dict."""
    if isinstance(obj, str) and obj.startswith("<") and obj.endswith(">"):
        return [path]
    if isinstance(obj, dict):
        out = []
        for k, v in obj.items():
            out += _find_placeholders(v, f"{path}.{k}" if path else k)
        return out
    if isinstance(obj, list):
        out = []
        for i, v in enumerate(obj):
            out += _find_placeholders(v, f"{path}[{i}]")
        return out
    return []


def _check_iam(sp: str) -> tuple:
    """Confirm the Commvault SP has both roles needed for backup and restore."""
    if not sp or sp.startswith("<"):
        return True, "IAM check skipped (commvault_sp_object_id not set)"
    roles = az_json("role", "assignment", "list",
                    "--assignee", sp,
                    "--scope", f"/subscriptions/{CFG['subscription_id']}",
                    "--query", "[].roleDefinitionName") or []
    needed = {"Contributor", "Storage Blob Data Contributor"}
    missing = needed - set(roles)
    if missing:
        return False, (f"SP {sp[:8]}… missing roles: {', '.join(sorted(missing))}"
                       f"  → fix: az role assignment create --assignee {sp}"
                       f" --role \"<role>\" --scope /subscriptions/{CFG['subscription_id']}")
    return True, f"SP {sp[:8]}… — Contributor + Storage Blob Data Contributor assigned"


def _check_rg_clean(rg: str) -> tuple:
    """Warn if a Recovery Services vault exists in the RG outside Terraform state.
    RSVs block RG deletion — teardown handles them, but knowing upfront prevents
    surprises."""
    vaults = az_json("resource", "list", "-g", rg,
                     "--resource-type", "Microsoft.RecoveryServices/vaults",
                     "--query", "[].name") or []
    if vaults:
        return False, (f"RG {rg} has RSV(s): {', '.join(vaults)}"
                       f"  → op teardown will remove them; or delete manually first")
    return True, f"RG {rg} — no foreign Recovery Services vaults"


# --------------------------------------------------------------------------- #
# protect — create the VSA vmgroup, VM added by its Azure vmId (== strGUID)
# --------------------------------------------------------------------------- #
def protect(run_dir: str) -> int:
    w = contract(run_dir)
    existing = group_id(w["vm_name"])         # idempotent — re-running never duplicates
    if existing:
        print(f"protect: group {existing} already exists — reusing")
        return existing
    body = {
        "name": f"resops-{w['vm_name']}-vg",
        "plan": {"id": CFG["plan_id"]},
        "Hypervisor": {"id": HYP["id"]},  # capital H — lowercase 400s
        "content": {"overwrite": True, "virtualMachines": [
            {"name": w["vm_name"], "GUID": w["vm_guid"], "type": "VM"}]},
    }
    r = write("POST", "v4/VMGroup", json=body)
    if r.status_code != 200:
        raise SystemExit(f"protect failed: HTTP {r.status_code} {r.text[:200]}")
    gid = r.json()["subclientId"]
    print(f"protected: group {gid}  ({w['vm_name']} by {w['vm_guid']}, IntelliSnap off)")
    return gid


# --------------------------------------------------------------------------- #
# backup — trigger a full backup on the workload's vmgroup, poll to terminal
# --------------------------------------------------------------------------- #
def backup(run_dir: str, gid: int | None = None) -> str:
    w = contract(run_dir)
    gid = gid or group_id(w["vm_name"])   # by group, not /VM (which lags after protect)
    if not gid:
        raise SystemExit(f"no vmgroup for {w['vm_name']} — run protect first")
    job = write("POST", f"v4/vmgroup/{gid}/backup", json={"backupLevel": "FULL"}).json()["jobIds"][0]
    print(f"backup job {job} on group {gid}…")
    status = poll_job(client, job)
    print(f"backup {status}")
    return status


# --------------------------------------------------------------------------- #
# restore — derive the /CreateTask payload token-native, then run the drill
# --------------------------------------------------------------------------- #
def _restore_payload(w: dict, subclient_id: int, disk_name: str,
                     disk_type: str, to_time: int) -> dict:
    """Build the /CreateTask body. The nested shape is captured verbatim from a
    proven Command Center restore — keep the structure as-is; only the values
    pulled from w / args vary. (applicationId 106 = VSA-Azure; commCellId 2 = this
    CommCell — both fixed for this tenant.)"""
    name = w["vm_name"]
    sa = w["restore_storage_account"]
    return {"taskInfo": {
        "task": {"taskFlags": {"disabled": False}, "policyType": "DATA_PROTECTION",
                 "taskType": "IMMEDIATE", "initiatedFrom": "GUI"},
        "associations": [{"subclientId": subclient_id, "client": {},
                          "applicationId": _VSA_APP_ID, "_type_": "CLIENT_ENTITY"}],
        "subTasks": [{"subTask": {"subTaskName": "", "subTaskType": "RESTORE",
                                  "operationType": "RESTORE"},
            "options": {"restoreOptions": {
                "browseOption": {"commCellId": _COMMCELL_ID,
                    "timeRange": {"fromTime": 0, "toTime": to_time},
                    "noImage": False, "useExactIndex": False,
                    "mediaOption": {"copyPrecedence": {"copyPrecedence": 0}},
                    "listMedia": False, "toTime": to_time, "fromTime": 0,
                    "showDeletedItems": False},
                "destination": {"destClient": {"clientId": HYP["id"],
                                               "clientName": HYP["name"]},
                                "inPlace": False, "isLegalHold": False},
                "restoreACLsType": "ACL_DATA",
                "volumeRstOption": {"volumeLeveRestore": False,
                    "volumeLevelRestoreType": "VIRTUAL_MACHINE",
                    "destinationVendor": "AZURE_V2"},
                "virtualServerRstOption": {"diskLevelVMRestoreOption": {
                    "powerOnVmAfterRestore": True, "passUnconditionalOverride": False,
                    "diskOption": "Auto", "advancedRestoreOptions": [{
                        "guid": w["vm_guid"], "name": name,
                        "newName": f"{name}-restore", "esxHost": w["resource_group"],
                        "Datastore": sa, "vmSize": w["vm_size"],
                        "disks": [{"name": disk_name,
                                   "newName": f"{name}-restore-osdisk",  # UNIQUE — avoids collision
                                   "Datastore": sa, "type": disk_type}],
                        "nics": [{"networkName": w["vnet_name"], "subnetId": w["subnet_id"]}],
                        "addToFailoverCluster": False, "securityGroups": [{}],
                        "datacenter": w["location"], "createPublicIP": False,
                        "restoreAsManagedVM": True, "encryptionOption": {},
                        "availabilityZones": "", "restoreVMTags": False,
                        "keyvaultId": "", "extensionRestorePolicy": "RESTORE"}],
                    "transportMode": "Auto", "useVcloudCredentials": True,
                    "restoreToDefaultHost": False, "generateNewGuid": False,
                    "reuseExistingVMClient": False},
                    "isDiskBrowse": True, "viewType": "DEFAULT",
                    "vCenterInstance": {"instanceId": HYP["instance_id"],
                                        "applicationId": _VSA_APP_ID, "clientId": HYP["id"]},
                    "securityScanOptions": {"runSecurityScan": False}},
                "fileOption": {"sourceItem": ["\\" + w["vm_guid"]]},
                "commonOptions": {"overwriteFiles": False, "detectRegularExpression": True,
                    "unconditionalOverwrite": False, "stripLevelType": "PRESERVE_LEVEL",
                    "preserveLevel": 1, "stripLevel": 0, "restoreACLs": True,
                    "isFromBrowseBackup": True, "clusterDBBackedup": False}},
                "adminOpts": {"updateOption": {"invokeLevel": "NONE"}},
                "commonOpts": {"notifyUserOnJobCompletion": False}}}]}}


def restore(run_dir: str) -> int:
    w = contract(run_dir)
    vm = require_vm(w["vm_name"])
    subclient_id = vm["vmSubClientEntity"]["subclientId"]            # the proven derivation
    disk = client.get(f"v2/vsa/vm/{w['vm_guid']}/disks").json()["disks"][0]
    to_time = int(time.time()) + 3600   # +1h clock-skew buffer: CommServ browse needs toTime > server time
    payload = _restore_payload(w, subclient_id, disk["name"], disk.get("type", "Standard_LRS"), to_time)
    run_restore.PAYLOAD_PATH.write_text(json.dumps(payload, indent=2))
    print(f"restore payload derived (subclient {subclient_id}, disk {disk['name']!r}) -> {run_restore.PAYLOAD_PATH}")
    return run_restore.main(["--cleanup"])


# --------------------------------------------------------------------------- #
# threatscan — trigger a ThreatScan job on the workload's backup copy,
# poll to completion, read the verdict. Explicit participant step (rung 3) so
# the team can see and act on the threat signal before cleanroom recovery.
# --------------------------------------------------------------------------- #
def _commcell_client_id(vm_name: str) -> int:
    """CommCell integer client ID for the VM. The plain Client API only lists
    physical/proxy clients, not VSA pseudo-clients — confirmed live. The VM's own
    /VM record carries its pseudo-client id at client.clientId (distinct from
    pseudoClient.clientId, which is the hypervisor)."""
    vm = require_vm(vm_name)
    return vm["client"]["clientId"]


def _storage_pool_id(pool_name: str) -> int:
    """The pool's id, or stop with the fix. Parsing lives in reads.storage_pool_id."""
    pool_id = storage_pool_id(client.get("StoragePool").json(), pool_name)
    if pool_id is None:
        raise SystemExit(f"storage pool {pool_name!r} not found in StoragePool list"
                         f"  → fix: config/workshop.yaml platform.storage_pool_name")
    return pool_id


def _backup_copy_id(plan_id: int) -> int:
    """The copy id that actually holds backed-up data, resolved via the PLAN's own
    storage policy. Parsing lives in reads.default_copy_id."""
    plan = client.get(f"V2/Plan/{plan_id}").json()["plan"]
    policy_id = plan["storage"]["storagePolicy"]["storagePolicyId"]
    copy_id = default_copy_id(client.get(f"StoragePolicy/{policy_id}").json())
    if copy_id is None:
        raise SystemExit(f"storage policy {policy_id} (plan {plan_id}) has no default copy")
    return copy_id


def _threatscan_verdict(commcell_client_id: int) -> dict:
    """Post-scan anomaly counts for this client. Parsing lives in reads.anomaly_verdict."""
    return anomaly_verdict(client.get("Client/Anomaly").json(), commcell_client_id)


def threatscan(run_dir: str) -> None:
    w = contract(run_dir)
    vm_name = w["vm_name"]
    pool_name = CFG.get("storage_pool_name")
    if not pool_name:
        raise SystemExit("platform.storage_pool_name missing from workshop.yaml"
                         "  → fix: add the managed storage pool's name, exactly as it"
                         " appears in the console (Manage > Storage)")
    cid = _commcell_client_id(vm_name)
    pool_id = _storage_pool_id(pool_name)
    copy_id = _backup_copy_id(CFG["plan_id"])
    payload = {
        "client": {"clientId": cid},
        "timeRange": {"fromTime": 0, "toTime": int(time.time()) + 3600},  # +1h clock-skew buffer
        "threatAnalysisFlags": 3,   # 1=malware 2=file-anomaly 3=both
        "backupDetails": [{"copyId": copy_id, "storagePoolId": pool_id}],
    }
    r = write("POST", "EDiscoveryClients/OnDemandAnalytics", json=payload)
    if r.status_code not in (200, 202):
        raise SystemExit(f"threatscan trigger failed: HTTP {r.status_code} {r.text[:200]}")
    body = r.json()
    # EDiscoveryClients returns jobId (singular); handle jobIds (plural list) defensively
    job_id = body.get("jobId") or (body.get("jobIds") or [None])[0]
    if not job_id:
        raise SystemExit(f"threatscan trigger succeeded but no job ID in response: {body}")
    print(f"threatscan job {job_id}  (client {cid}, pool {pool_id}, copy {copy_id})…")
    result = poll_job(client, job_id, timeout=900, every=20)
    print(f"threatscan {result}")
    if "Completed" not in result:
        # A failed scan is NOT a clean scan. Stop rather than let the climb continue
        # on a recovery point nobody actually checked.
        raise SystemExit(f"threatscan job {job_id} ended with {result!r} — no verdict, so"
                         f" the recovery point is UNVERIFIED (not clean)"
                         f"  → fix: open job {job_id} in the console for the reason;"
                         f" a scan-server slot or an unsupported agent are the usual ones")
    time.sleep(5)  # allow Metallic anomaly index to flush before reading verdict
    verdict = _threatscan_verdict(cid)
    label = "CLEAN" if verdict["clean"] else "THREATS FOUND"
    print(f"verdict: {label}  "
          f"(infected={verdict['infectedFilesCount']}, "
          f"fingerprint={verdict['fingerPrintFilesCount']})")
    if not verdict["clean"]:
        sys.exit(f"threatscan FAILED — threats detected on {vm_name}")


# --------------------------------------------------------------------------- #
# incident — make the workload untrusted ON PURPOSE, so the threat signal is
# real instead of narrated. A clean climb proves recoverability; it proves
# nothing about TRUST. This is the step that lets `op threatscan` say no.
# --------------------------------------------------------------------------- #
# Assembled from fragments at runtime, never stored whole. EICAR is the industry
# standard harmless test pattern every scanner is built to detect — but a file
# containing it verbatim is exactly what endpoint AV quarantines, and that file
# would be THIS SOURCE FILE sitting in the repo. Splitting it keeps the checkout
# scannable. The string is inert: it is not code, it does nothing, it exists only
# to be recognised.
_EICAR = ("X5O!P%@AP[4\\PZX54(P^)7CC)7}$"
          "EICAR-STANDARD-ANTIVIRUS-TEST-FILE!"
          "$H+H*")

# Runs inside the guest via the Azure agent. Two distinct signals, because
# ThreatScan looks for both and we want the demo to survive either one missing:
#   malware      — the EICAR pattern, matched by signature
#   file anomaly — a burst of high-entropy files with a changed extension, which
#                  is what mass encryption actually looks like on disk
_INCIDENT_SCRIPT = r"""
set -eu
DATA=/var/lib/app/data
mkdir -p "$DATA"

# 1. the signature-detectable artifact
printf '%s' '{eicar}' > "$DATA/invoice_overdue.doc"
printf '%s' '{eicar}' > "$DATA/.hidden_payload"

# 2. what mass encryption looks like: high-entropy files, extension changed,
#    originals removed. customers.csv is the one participants will miss.
for f in customers.csv orders.ndjson; do
  if [ -f "$DATA/$f" ]; then
    head -c 4096 /dev/urandom > "$DATA/$f.locked"
    rm -f "$DATA/$f"
  fi
done
for i in $(seq 1 12); do
  head -c 2048 /dev/urandom > "$DATA/record_$i.dat.locked"
done

# 3. the note. Operators find this first in a real event.
cat > "$DATA/README_RECOVER.txt" <<'NOTE'
Your files have been encrypted.
(Workshop simulation. No encryption was performed; these are random bytes.)
NOTE

echo "planted: 2 EICAR files, $(ls "$DATA" | grep -c '\.locked$') .locked files, 1 note"
echo "BASELINE marker still present: $([ -f "$DATA/BASELINE" ] && echo yes || echo NO)"
ls -la "$DATA"
"""


def incident(run_dir: str) -> None:
    """Plant a detectable incident inside the running workload.

    Deliberately makes the workload untrusted so the next backup carries a
    compromised recovery point and `op threatscan` returns THREATS FOUND. The
    known-good BASELINE marker is left in place so "what did we still trust?"
    has an answer.

    Reversible: `op teardown` then a fresh climb restores a clean workload.
    Targeted: the VM comes from the terraform contract, so it cannot hit
    anything other than this run_dir's own workload."""
    w = contract(run_dir)
    vm_name, rg = w["vm_name"], w["resource_group"]
    print(f"incident: planting a detectable compromise in {vm_name} ({rg})")
    print("  EICAR test pattern + high-entropy .locked files — inert, no real encryption")
    result = az_json("vm", "run-command", "invoke",
                     "-g", rg, "-n", vm_name,
                     "--command-id", "RunShellScript",
                     "--scripts", _INCIDENT_SCRIPT.replace("{eicar}", _EICAR),
                     timeout=300)
    if not result:
        raise SystemExit(f"incident failed — could not run the command on {vm_name}"
                         f"  → fix: is the VM running? az vm get-instance-view -g {rg} -n {vm_name}")
    for msg in result.get("value", []):
        print(msg.get("message", "").strip())
    print(f"\n{vm_name} is now UNTRUSTED. Next: op backup, then op threatscan.")


def climb(run_dir: str) -> None:
    preflight.run(run_dir)        # gate first — never act on a shaky environment
    gid = protect(run_dir)        # thread the group id → backup needn't wait on /VM
    backup(run_dir, gid)
    threatscan(run_dir)           # Scan sits below Validate: never prove a restore
                                  # from a point you haven't checked. Exits non-zero
                                  # on a threat, so the climb stops here rather than
                                  # rehearsing recovery from a compromised copy.
    restore(run_dir)              # /VM has caught up by now (backup took minutes)
    print()
    status(run_dir)               # hand to resops — watch the rung land at VALIDATED


# --------------------------------------------------------------------------- #
# verify bridge — op DRIVES the climb, then hands the workload to `resops` (the
# read-only star) to render the ladder / run the gate. resops SHOWS + decides.
# --------------------------------------------------------------------------- #
def _gate_config_path(run_dir: str) -> str:
    """A resops config for THIS workload — inherits config/workshop.yaml's `gate`
    block (frameworks + freshness) and injects the live workload name from the
    terraform contract. resops resolves the vm group by name (resops-<name>-vg),
    so there's no hand-copied id to drift. (JSON is valid YAML, so resops reads it.)"""
    w = contract(run_dir)
    base = REPO / "config" / "workshop.yaml"
    wcfg = yaml.safe_load(base.read_text()) if base.exists() else {}
    wcfg_workload = wcfg.get("workload") or {}
    cfg = {
        "gate": wcfg.get("gate", {}),
        "workload": {"name": w["vm_name"], "tier": wcfg_workload.get("tier")},
        "target": HOST,
    }
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        json.dump(cfg, f)
        return f.name


def _resops(*args: str) -> int:
    """Run the read-only resops engine (the star) as a subcommand, from the repo."""
    return subprocess.run([sys.executable, "-m", "resops", *args], cwd=str(REPO)).returncode


def status(run_dir: str) -> None:
    """Show the workload's rung on the ladder + the DevOps lens — anytime, read-only."""
    _resops("--detail", _gate_config_path(run_dir))


def gate(run_dir: str) -> None:
    """The promotion gate — PROMOTE/HOLD + the compliance crosswalk. exit 0/1."""
    sys.exit(_resops("gate", _gate_config_path(run_dir)))


# --------------------------------------------------------------------------- #
# teardown helpers
# --------------------------------------------------------------------------- #
def _sweep_recovery_vaults(rg: str) -> None:
    """Remove any Recovery Services vaults from the RG before terraform destroy.
    Azure blocks RG deletion when an RSV exists — even after everything else is gone.
    Vaults outside Terraform state (e.g. created manually) cause `terraform destroy`
    to stall for 10+ minutes. This sweeps them first, cleanly."""
    vaults = az_json("resource", "list", "-g", rg,
                     "--resource-type", "Microsoft.RecoveryServices/vaults",
                     "--query", "[].name") or []
    if not vaults:
        return
    for name in vaults:
        print(f"  RSV {name!r} not in Terraform state — clearing before destroy")
        az_ok("backup", "vault", "backup-properties", "set",
              "-g", rg, "--vault-name", name, "--soft-delete-state", "Disable")
        containers = az_json("backup", "container", "list",
                             "-g", rg, "--vault-name", name,
                             "--backup-management-type", "AzureIaasVM") or []
        for c in containers:
            cname = c.get("name", "")
            for item in (az_json("backup", "item", "list", "-g", rg,
                                 "--vault-name", name,
                                 "--backup-management-type", "AzureIaasVM",
                                 "--container-name", cname) or []):
                az_ok("backup", "protection", "disable",
                      "-g", rg, "--vault-name", name,
                      "--container-name", cname, "--item-name", item.get("name", ""),
                      "--backup-management-type", "AzureIaasVM",
                      "--workload-type", "VM", "--delete-backup-data", "true", "--yes")
        az_ok("backup", "vault", "delete", "-g", rg, "--name", name, "--yes")


# --------------------------------------------------------------------------- #
# teardown — retire the workload cleanly: CV group + GXMD sweep + terraform destroy
# --------------------------------------------------------------------------- #
def teardown(run_dir: str) -> None:
    w = contract(run_dir)
    gid = group_id(w["vm_name"])
    if gid:
        r = write("DELETE", f"v4/VMGroup/{gid}")
        note = " (pending admin approval)" if r.status_code == 202 else ""
        print(f"CV group {gid} delete → HTTP {r.status_code}{note}")
    # Sweep Commvault GXMD snapshots — even streaming backups leave one, and it
    # blocks the RG delete (it's a snapshot, so `az disk list` won't show it).
    for res in (az_json("resource", "list", "-g", w["resource_group"],
                        "--query", "[?contains(name,'GXMD')]") or []):
        az_json("resource", "delete", "--ids", res["id"])
        print(f"swept GXMD snapshot: {res['name']}")
    _sweep_recovery_vaults(w["resource_group"])
    subprocess.run(["terraform", f"-chdir={run_dir}", "destroy", "-auto-approve"])
    # Azure auto-creates a region-level NetworkWatcher (in NetworkWatcherRG) the first
    # time a VNet is made in a region — it's not in our Terraform, so destroy leaves it.
    # Remove just this region's watcher so the workshop leaves zero residue. Best-effort,
    # and surgical: we never touch NetworkWatcherRG itself (it's shared across regions).
    # It's free and Azure recreates it on the next climb, so this only matters for the
    # single-workload workshop flow.
    for wid in (az_json("network", "watcher", "list",
                        "--query", f"[?location=='{w['location']}'].id") or []):
        az_json("resource", "delete", "--ids", wid)
        print(f"removed auto-created NetworkWatcher in {w['location']}")


def validate(run_dir: str) -> None:
    """Extended preflight — config completeness + IAM roles + all preflight checks
    + RG cleanliness. Run before climbing (catches config and auth blockers) and
    before teardown (confirms the RG is safe to destroy)."""
    base = REPO / "config" / "workshop.yaml"
    raw_cfg = yaml.safe_load(base.read_text()) if base.exists() else {}
    sp = (raw_cfg.get("platform") or {}).get("commvault_sp_object_id", "")

    placeholders = _find_placeholders(raw_cfg)
    checks: list = [
        ((False, f"config has unfilled placeholders: {', '.join(placeholders[:3])}"
                 f"  → fix: fill config/workshop.yaml")
         if placeholders else (True, "config/workshop.yaml — no placeholder values")),
        _check_iam(sp),
        preflight.check_az(), preflight.check_token(), preflight.check_hypervisor(),
    ]

    try:
        w = contract(run_dir)
        checks += [
            preflight.check_discovered(w["vm_name"]),
            preflight.check_vcpu(w["location"], w["vm_size"]),
            _check_rg_clean(w["resource_group"]),
        ]
    except SystemExit:
        checks.append((True, f"terraform not yet applied in {run_dir} — workload checks skipped"))

    all_ok = True
    for ok, msg in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {msg}")
        all_ok = all_ok and ok
    if not all_ok:
        sys.exit("validate FAILED — fix the above before climbing")
    print("validate PASS — safe to climb and teardown")


CMDS = {"validate": validate, "preflight": preflight.run, "protect": protect,
        "backup": backup, "restore": restore, "threatscan": threatscan,
        "incident": incident, "climb": climb, "status": status,
        "gate": gate, "teardown": teardown}

_USAGE = """op — the ResOps write lane

  op validate    <run_dir>   config + IAM + preflight + RG cleanliness (run first, and before teardown)
  op preflight   <run_dir>   read-only gate: az · token · hypervisor · discovered · vCPU
  op protect     <run_dir>   create the Commvault VM group for the workload
  op backup      <run_dir>   trigger a full backup and poll to completion
  op restore     <run_dir>   derive the restore payload + run the drill
  op threatscan  <run_dir>   trigger ThreatScan on the backup copy, poll to clean/threat verdict
  op incident    <run_dir>   plant a detectable compromise in the workload (workshop only)
  op climb       <run_dir>   preflight → protect → backup → threatscan → restore (one step)
  op status      <run_dir>   show the workload's rung on the readiness ladder (read-only)
  op gate        <run_dir>   promotion gate → PROMOTE / HOLD  (exit 0 / 1)
  op teardown    <run_dir>   CV group delete + GXMD sweep + RSV sweep + terraform destroy

<run_dir> is the terraform root (normally infra/workloads).
Always run `op validate` first — it catches config, IAM, and environment blockers up front.

The workshop's trusted-recovery story, once the workload is VALIDATED:
  op incident → op backup → op threatscan → op gate
  clean workload, PROMOTE  ⇒  compromised backup, THREATS FOUND, HOLD."""


# Commands that never call Commvault, so they must not demand a live token.
# validate/preflight are diagnostics — they have to work on a cold session, which
# is exactly when you reach for them. incident is pure Azure (terraform contract +
# az run-command); making it fail on a stale token would block the one command whose
# whole job is to break things locally.
_NO_TOKEN_NEEDED = ("validate", "preflight", "incident")


def main() -> None:
    """Console entry point (`op <cmd> <run_dir>`)."""
    if len(sys.argv) < 2 or sys.argv[1] in ("help", "-h", "--help"):
        print(_USAGE)
        sys.exit(0)
    if len(sys.argv) != 3 or sys.argv[1] not in CMDS:
        sys.exit(f"usage: op {{{'|'.join(CMDS)}}} <run_dir>\n\nRun `op help` for details.")
    if sys.argv[1] not in _NO_TOKEN_NEEDED:
        client.ensure_fresh_token()
    CMDS[sys.argv[1]](sys.argv[2])


if __name__ == "__main__":
    main()
