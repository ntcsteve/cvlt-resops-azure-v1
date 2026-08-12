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
    op remediate   <run_dir>  undo op incident in place and re-verify
    op climb       <run_dir>  preflight -> protect -> backup -> restore
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

from ..reads import threat_attestation
from ._azure import az_json, az_ok
from .commvault import poll_job, succeeded
from . import preflight
from ._common import CFG, HOST, HYP, REPO, client, contract, find_vm, group_id, write
from .drills import run_restore


_VSA_APP_ID = 106    # Virtual Server Agent application type — fixed across Metallic tenants

# The CommCell this tenant lives on. TENANT-SPECIFIC, unlike _VSA_APP_ID above.
# 2 is the common default for a single-CommCell Metallic instance and is what
# ours reports, but "common" is not "always" — and a wrong value here produces a
# restore request that is accepted and then browses the wrong CommCell, which
# reads as an empty backup rather than as an error. Override in workshop.yaml:
#
#   platform:
#     commcell_id: 3
#
# Find yours in Command Center, or from any job's commCellId in the API.
_DEFAULT_COMMCELL_ID = 2


def commcell_id() -> int:
    """This tenant's CommCell id, from config, defaulting to the common value."""
    return CFG.get("commcell_id", _DEFAULT_COMMCELL_ID)


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
    # STOP, do not return a status nobody checks. This used to hand the caller a
    # string and exit 0, so `climb` carried on to restore an OLDER recovery point
    # and attested THAT. The ladder still caught it at Detect, so it was never a
    # false promotion — but ten minutes were spent proving something about the
    # wrong point, and the output read as though the climb had worked.
    # Every other step in this lane completes or raises. Now this one does too.
    if not succeeded(status):
        raise SystemExit(
            f"backup job {job} ended {status!r} — NOTHING NEW WAS PROTECTED, so a"
            f" restore or a gate run now would be about an older recovery point"
            f"\n  → open job {job} in the console for the reason. A 'Waiting' job"
            f" that never starts is usually a media agent slot; 'collect file is"
            f" missing' means discovery moved agents and the backup will restart.")
    return status


# --------------------------------------------------------------------------- #
# restore — derive the /CreateTask payload token-native, then run the drill
# --------------------------------------------------------------------------- #
def _restore_payload(w: dict, subclient_id: int, disk_name: str,
                     disk_type: str, to_time: int) -> dict:
    """Build the /CreateTask body. The nested shape is captured verbatim from a
    proven Command Center restore — keep the structure as-is; only the values
    pulled from w / args vary. applicationId 106 is VSA-Azure and is fixed across
    Metallic; commCellId comes from config because it is NOT (see commcell_id())."""
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
                "browseOption": {"commCellId": commcell_id(),
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


def _os_disk(vm_guid: str) -> dict:
    """The VM's OS disk, chosen by the API's OWN isOSDisk flag.

    NEVER take disks[0]. For an Azure VSA backup the first entry is the VM's
    config blob — name "<vm>.json", isOSDisk false, type "" — and sending that as
    the restore disk makes Commvault reject the job with "No OS disk found.
    Please check if OS disk was filtered as part of backup", which reads like a
    BACKUP problem and is not one. Proven live on aug12-narwhal 2026-08-12;
    cherry-turtles has the identical two-entry shape, so disks[0] was always
    wrong and only ever worked by luck of ordering.
    """
    disks = client.get(f"v2/vsa/vm/{vm_guid}/disks").json().get("disks") or []
    for d in disks:
        if d.get("isOSDisk"):
            return d
    raise SystemExit(f"no disk with isOSDisk=true for {vm_guid} — cannot build a restore"
                     f" payload  → disks returned: {[d.get('name') for d in disks]}")


def restore(run_dir: str) -> int:
    w = contract(run_dir)
    vm = require_vm(w["vm_name"])
    subclient_id = vm["vmSubClientEntity"]["subclientId"]            # the proven derivation
    disk = _os_disk(w["vm_guid"])
    to_time = int(time.time()) + 3600   # +1h clock-skew buffer: CommServ browse needs toTime > server time
    # `or` not a dict default: the config-blob entry carries type "", which is
    # present-but-empty, so .get("type", fallback) would hand Commvault an empty string.
    payload = _restore_payload(w, subclient_id, disk["name"], disk.get("type") or "Standard_LRS", to_time)
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


def _threatscan_verdict(commcell_client_id: int) -> dict | None:
    """The scan's attestation for this client, or None if it attests nothing.
    Parsing lives in reads.threat_attestation."""
    return threat_attestation(client.get("Client/Anomaly").json(), commcell_client_id)


def threatscan(run_dir: str) -> dict | None:
    """Trigger a threat scan for THIS workload and return what the tenant recorded.

    Two calls, both proven live 2026-08-12 and NEITHER DOCUMENTED by the vendor —
    absent from a 6,798-URL API reference and from Commvault's own Python SDK. That
    is stated here because it is a maintenance liability, not a footnote. If either
    route changes, this command breaks, the Scan rung reports nothing, and nothing
    silently passes. See HANDOVER.prev.md section 0b.

      WRITE  POST ThreatIndicator/OnDemandScan   one VM, one job id returned
      READ   GET  Client/Anomaly                 keyed on the VM's client.clientId

    THE JOB IS POLLED ONLY TO KNOW THE ATTEMPT FINISHED. It is never the verdict.
    A re-scan of a poisoned recovery point with no new backup data completes with
    no error code and no findings — observed three times on one workload. Job
    success and cleanliness are unrelated facts here.

    The verdict is the persistent per-client record, and threat_attestation treats
    a zero count as attesting NOTHING rather than as clean, because the client
    stays in that list with 0 after remediation.

    Returns the recorded negative, or None. None is not a pass. It never was.
    """
    w = contract(run_dir)
    vm_name = w["vm_name"]
    scan_plan = CFG.get("scan_plan_id")
    if not scan_plan:
        raise SystemExit(
            "platform.scan_plan_id missing from workshop.yaml"
            "  -> fix: add the THREAT SCAN plan's id, from Secure > Threat scan >"
            " Plans. NOT the protection plan id: they are different objects, and the"
            " protection plan will be accepted and scan nothing.")
    cid = _commcell_client_id(vm_name)

    # The VM does NOT need to appear in the Resources tab first. This was fired
    # against a clientId with no row there and it bound correctly. That tab is a
    # materialised view on a slow cycle, and waiting for it would make this command
    # unusable on a workload built the same morning.
    payload = {"clients": [{"tdPlan": {"planId": scan_plan},
                            "client": {"entityType": 3, "_type_": 3,
                                       "clientId": cid,
                                       "applicationId": _VSA_APP_ID}}],
               "type": 0, "levelType": 1}
    r = write("POST", "ThreatIndicator/OnDemandScan", json=payload)
    body = r.json()
    if body.get("errorCode"):
        raise SystemExit(f"threatscan trigger refused: {body.get('errorString')!r} "
                         f"(errorCode {body.get('errorCode')}) {body.get('jobErrorList')}")
    job_id = (body.get("jobIds") or [None])[0]
    if not job_id:
        raise SystemExit(f"threatscan trigger returned no job id: {body}")
    print(f"threatscan job {job_id}  (client {cid}, scan plan {scan_plan})...")

    status = poll_job(client, job_id, timeout=900, every=20)
    print(f"threatscan attempt {status}")
    if not succeeded(status):
        # No fresh look at the data. The persistent record may still hold an OLDER
        # verdict, and reporting that as though this scan produced it would be the
        # same lie in a new place.
        raise SystemExit(
            f"threatscan job {job_id} ended {status!r} - this recovery point was NOT"
            f" examined, so it is UNVERIFIED and not clean"
            f"\n  -> open job {job_id} in the console. A group whose VM has been"
            f" deleted fails every time with [14:313]; suspect a stale group before"
            f" you suspect the product.")

    verdict = _threatscan_verdict(cid)
    if verdict is None:
        print("verdict: no threat recorded for this workload - which is NOT the same"
              " as clean, and does not clear the Scan rung on its own")
        return None
    print(f"verdict: THREATS FOUND - {verdict.get('detail')}")
    return verdict
def _cli_threatscan(run_dir: str) -> None:
    """`op threatscan` as a standalone command: exit 1 when threats are found, so
    it can gate a pipeline.

    The wording matters. A scan that could not run and a scan that ran and found
    threats are opposite situations, and "threatscan FAILED" (what this used to
    print) reads at 2am as "the scan broke, re-run it" — the precise opposite of
    "the scan worked and your recovery point is poisoned". The failed-job path
    above says UNVERIFIED; this one says compromised."""
    if threatscan(run_dir) is not None:
        sys.exit("THREATS DETECTED — the scan ran and this recovery point is NOT safe "
                 "to restore from. The scan did its job; the backup is the problem.")


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
STASH=/var/lib/app/.incident-stash
mkdir -p "$DATA"

# 1. the signature-detectable artifact
printf '%s' '{eicar}' > "$DATA/invoice_overdue.doc"
printf '%s' '{eicar}' > "$DATA/.hidden_payload"

# 2. what mass encryption looks like: high-entropy files, extension changed,
#    originals removed. customers.csv is the one participants will miss.
#
#    The original is STASHED first, outside $DATA so verify.sh and the drill never
#    see it, purely so `op remediate` can put back EXACTLY what was taken. The
#    alternative was to hardcode the known-good rows in a second place and keep
#    them in step with cloud-init by hand — and verify.sh only checks the header
#    and a row count, so that drift would have been invisible. Stashing makes the
#    inverse exact instead of approximate.
mkdir -p "$STASH"
for f in customers.csv orders.ndjson; do
  if [ -f "$DATA/$f" ]; then
    cp -p "$DATA/$f" "$STASH/$f"
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


# --------------------------------------------------------------------------- #
# remediate — the exact inverse of incident, so the lab is a LOOP and not a
# one-way trip. Until this existed the dirty->clean transition was done by hand,
# four times in one session, differently each time.
# --------------------------------------------------------------------------- #
_REMEDIATE_SCRIPT = r"""
set -u
DATA=/var/lib/app/data
STASH=/var/lib/app/.incident-stash

# 1. remove exactly what `op incident` planted. Nothing else is touched.
rm -f "$DATA"/*.locked "$DATA/README_RECOVER.txt" \
      "$DATA/invoice_overdue.doc" "$DATA/.hidden_payload"

# 2. put back exactly what it took. cp, not mv: re-running must be safe, and a
#    half-finished remediation that consumed the stash would be unrecoverable.
restored=0
if [ -d "$STASH" ]; then
  for f in "$STASH"/*; do
    [ -e "$f" ] || continue
    cp -p "$f" "$DATA/$(basename "$f")" && restored=$((restored + 1))
  done
fi

echo "removed the planted artefacts; restored $restored file(s) from the stash"
echo "locked_remaining=$(find "$DATA" -name '*.locked' | wc -l)"
echo "stash_present=$([ -d "$STASH" ] && echo yes || echo NO)"

# 3. the workload's own check decides whether this worked. Same contract as the
#    drill: the OK:/FAIL: line is the verdict, not the exit code.
if [ -x /opt/app/verify.sh ]; then /opt/app/verify.sh; else echo 'NO VERIFY SCRIPT'; fi
"""


def remediate(run_dir: str) -> None:
    """Undo `op incident` and prove the workload is good again.

    Not a restore. This repairs the LIVE workload in place so the next backup
    produces a clean recovery point — which is what closes the loop
    incident -> backup -> scan -> HOLD -> remediate -> backup -> scan -> PROMOTE.
    Recovering from a backup instead is `op restore`, and it answers a different
    question.

    Targeted the same way as `op incident`: the VM comes from the terraform
    contract for this run_dir, so it cannot reach anything else. Idempotent — safe
    on a workload that is already clean.

    RAISES if verify.sh does not report OK afterwards, because a remediation that
    did not achieve its purpose must not read as success. That is the same
    convention every other step in this lane follows.
    """
    w = contract(run_dir)
    vm_name, rg = w["vm_name"], w["resource_group"]
    print(f"remediate: repairing {vm_name} ({rg}) in place")
    result = az_json("vm", "run-command", "invoke",
                     "-g", rg, "-n", vm_name,
                     "--command-id", "RunShellScript",
                     "--scripts", _REMEDIATE_SCRIPT, timeout=300)
    if not result:
        raise SystemExit(f"remediate failed — could not run the command on {vm_name}"
                         f"  → fix: is the VM running? "
                         f"az vm get-instance-view -g {rg} -n {vm_name}")
    output = "\n".join(m.get("message", "") for m in result.get("value", []))
    for line in output.splitlines():
        if line.strip():
            print("   ", line.strip()[:160])

    verdict = next((l.strip() for l in output.splitlines()
                    if l.strip().startswith(("OK:", "FAIL:", "NO VERIFY"))), "")
    if not verdict.startswith("OK:"):
        raise SystemExit(
            f"\nremediate did NOT restore {vm_name} to a good state: {verdict or 'no verdict'}"
            f"\n  → if stash_present=NO above, `op incident` ran before stashing existed"
            f" (or never ran), so the originals it deleted cannot be put back."
            f"\n  → recover from a backup instead: op restore {run_dir}")
    print(f"\n{vm_name} is clean again. Next: op backup, then op gate.")


def climb(run_dir: str) -> None:
    preflight.run(run_dir)        # gate first — never act on a shaky environment
    gid = protect(run_dir)        # thread the group id → backup needn't wait on /VM
    backup(run_dir, gid)
    # NO threatscan here, deliberately. It used to sit between backup and restore,
    # and every exit from it is a SystemExit three frames down — so one bad
    # response from a lane we do not own took the whole climb with it and
    # `restore` never ran. A climb must not be that fragile.
    #
    # The Scan rung is NOT weakened. It reads the attestation `restore` writes,
    # so an unattested or dirty recovery point still blocks below VALIDATED, and
    # restore-verify was always the primary attester. `op threatscan` stays a
    # standalone command.
    restore(run_dir)              # /VM has caught up, and this writes the attestation
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
    # Carry through every declared key the read lane understands. Listing them
    # explicitly (rather than copying the whole block) keeps the live workload
    # name from the terraform contract authoritative — but a key omitted here is
    # a key silently dropped, which cost us a confusing UNATTESTED verdict when
    # attestation_file was added and this wasn't.
    passthrough = ("tier", "criticality", "env", "owner",
                   "vm_group_id", "attestation_file", "promote_policy")
    workload = {"name": w["vm_name"]}
    workload.update({k: wcfg_workload[k] for k in passthrough if k in wcfg_workload})
    cfg = {
        "gate": wcfg.get("gate", {}),
        "workload": workload,
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
        "backup": backup, "restore": restore, "threatscan": _cli_threatscan,
        "incident": incident, "remediate": remediate, "climb": climb, "status": status,
        "gate": gate, "teardown": teardown}

_USAGE = """op — the ResOps write lane

  op validate    <run_dir>   config + IAM + preflight + RG cleanliness (run first, and before teardown)
  op preflight   <run_dir>   read-only gate: az · token · hypervisor · discovered · vCPU
  op protect     <run_dir>   create the Commvault VM group for the workload
  op backup      <run_dir>   trigger a full backup and poll to completion
  op restore     <run_dir>   derive the restore payload + run the drill
  op threatscan  <run_dir>   trigger ThreatScan on the backup copy, poll to clean/threat verdict
  op incident    <run_dir>   plant a detectable compromise in the workload (workshop only)
  op remediate   <run_dir>   undo op incident in place, and prove it with verify.sh
  op climb       <run_dir>   preflight → protect → backup → restore (one step)
  op status      <run_dir>   show the workload's rung on the readiness ladder (read-only)
  op gate        <run_dir>   promotion gate → PROMOTE / HOLD  (exit 0 / 1)
  op teardown    <run_dir>   CV group delete + GXMD sweep + RSV sweep + terraform destroy

<run_dir> is the terraform root (normally infra/workloads).
Always run `op validate` first — it catches config, IAM, and environment blockers up front.

The workshop's trusted-recovery story, once the workload is VALIDATED:
  op incident → op backup → op restore → op gate
  clean workload, PROMOTE  ⇒  compromised recovery point, HOLD."""


# Commands that never call Commvault, so they must not demand a live token.
# validate/preflight are diagnostics — they have to work on a cold session, which
# is exactly when you reach for them. incident is pure Azure (terraform contract +
# az run-command); making it fail on a stale token would block the one command whose
# whole job is to break things locally.
_NO_TOKEN_NEEDED = ("validate", "preflight", "incident", "remediate")


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
