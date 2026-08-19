"""The read layer – gather() over a fake client. No live tenant.

classify()'s truth table (test_state.py) assumes well-formed Reads; these tests
cover the I/O path that BUILDS a Reads: the right GETs, parsing the VM out of the
list, looking up the drill's own restore job for proof, and turning every failed
read into an error string (never an exception) so classify() can block on the
right rung.
"""
import json

from resops import client, reads
from resops.reads import _recovery_proof, list_vmgroups
from resops.state import gather

WL = {"vm_group_id": 35311, "vm_name": "vm-rwk-ws-0610a-vm01"}


class FakeResponse:
    """Models the bits of requests.Response the read layer actually touches.

    `headers` and `text` are here because _get inspects them: a 200 carrying an
    HTML body is a maintenance page, not a result, and status alone cannot tell.
    """
    def __init__(self, status_code, payload, content_type="application/json", text=""):
        self.status_code, self._payload = status_code, payload
        self.headers = {"content-type": content_type}
        self.text = text or ""

    def json(self):
        return self._payload


class FakeClient:
    """Maps request paths to canned (status, payload) responses."""
    def __init__(self, routes):
        self.routes = routes

    def get(self, path):
        return FakeResponse(*self.routes.get(path, (404, {})))


def _vm(name="vm-rwk-ws-0610a-vm01"):
    return {"name": name, "slaCategoryDescription": "Protected",
            "isRestoreActivityEnabled": True, "lastSuccessfulBackupTime": 1781299030,
            # the pseudo-client id _attest() needs before it will reach the
            # restore-verify fallback
            "client": {"clientId": 17394}}


def _routes(**over):
    routes = {
        "V4/VMGroup/35311": (200, {"name": "Steve-VM-Group"}),
        # the by-name resolver lists groups, then fetches the matched id
        "v4/vmgroups": (200, {"vmGroups": [{"vmGroup": {"id": 35311, "name": "resops-resolveme-vg"}}]}),
        "VM": (200, {"vmStatusInfoList": [_vm()]}),
        "Client/Anomaly": (200, {}),          # nothing recorded: attests nothing
        # proof is now a LOOKUP of the job the attestation names, not a search
        "Job/7540314": (200, {"jobs": [{"jobSummary": {"jobId": 7540314,
                                                       "status": "Completed"}}]}),
    }
    routes.update(over)
    return routes


def _attestation_file(tmp_path, restore_job="7540314", **over):
    """A restore-verify attestation on disk, as the drill writes it."""
    data = {"source": "restore-verify", "clean": True, "detail": "ok",
            "at": 1781299999, "restore_job": restore_job, "script": "/opt/app/verify.sh"}
    data.update(over)
    p = tmp_path / "attestation.json"
    p.write_text(json.dumps(data))
    return str(p)


def test_gather_collects_all_three_lanes(tmp_path):
    wl = dict(WL, attestation_file=_attestation_file(tmp_path))
    reads = gather(FakeClient(_routes()), wl)
    assert reads.vm_name == "vm-rwk-ws-0610a-vm01"
    assert reads.vmgroup["name"] == "Steve-VM-Group" and reads.vmgroup_error == ""
    assert reads.vm["name"] == "vm-rwk-ws-0610a-vm01" and reads.vm_error == ""
    assert reads.attestation["restore_job"] == "7540314"
    assert reads.proof["jobId"] == 7540314 and reads.proof_error == ""


def test_resolves_group_id_by_name_when_id_omitted():
    # no vm_group_id → resolve resops-resolveme-vg → id 35311 → fetch the group
    reads = gather(FakeClient(_routes()), {"vm_name": "resolveme"})
    assert reads.vmgroup["name"] == "Steve-VM-Group" and reads.vmgroup_error == ""


def test_unprotected_workload_resolves_to_a_clear_error():
    reads = gather(FakeClient(_routes()), {"vm_name": "ghost"})  # no matching group
    assert "no VM group" in reads.vmgroup_error and "resops-ghost-vg" in reads.vmgroup_error


def test_group_403_becomes_an_error_string_not_an_exception():
    reads = gather(FakeClient(_routes(**{"V4/VMGroup/35311": (403, {})})), WL)
    assert reads.vmgroup_error == "HTTP 403"


def test_vm_absent_from_list_is_none_without_error():
    reads = gather(FakeClient(_routes(VM=(200, {"vmStatusInfoList": [_vm("other")]}))), WL)
    assert reads.vm is None and reads.vm_error == ""


# --------------------------------------------------------------------------- #
# _recovery_proof – the Validate rung's evidence.
#
# THE BUG THESE EXIST TO PREVENT, observed live 2026-08-12. This used to ask for
# the last ten restore jobs and take the newest whose detail JSON mentioned the VM
# name. A Command Center FILE DOWNLOAD (job 8162459: two files, 194 bytes, sent to
# a Commvault-operated host) matched both conditions, because jobFilter=Restore
# includes downloads and the VM name is in their detail. The ladder reported
# ●●●●●● VALIDATED "recovery proven" and the gate PROMOTED, exit 0, on a workload
# nothing had restored.
#
# The rule is now a LOOKUP of the job the drill itself recorded, so the shape of
# the vendor's job list cannot decide our verdict. These tests pin that, using the
# real job ids from that night.
# --------------------------------------------------------------------------- #
def test_a_file_download_is_not_proof_of_recovery():
    """THE REGRESSION. Job 8162459 is the real download that promoted a workload.
    Even though it is newer than the drill, nothing may consult it: proof comes
    from the attestation, and the attestation names 8162077."""
    routes = _routes(**{
        "Job/8162077": (200, {"jobs": [{"jobSummary": {"jobId": 8162077,
                                                       "status": "Completed"}}]}),
        # present, newer, and irrelevant – a lookup never sees it
        "Job/8162459": (200, {"jobs": [{"jobSummary": {"jobId": 8162459,
                                                       "status": "Completed"}}]}),
        # the vendor list the old code consumed, with the download newest. Its
        # presence must not influence the verdict: that is the whole point.
        "Job?jobFilter=Restore": (200, {"jobs": [
            {"jobSummary": {"jobId": 8162459, "status": "Completed"}},
            {"jobSummary": {"jobId": 8162077, "status": "Completed"}}]}),
    })
    proof, err = _recovery_proof(FakeClient(routes), {"restore_job": "8162077"})
    assert err == ""
    assert proof["jobId"] == 8162077, "the drill's own job must be the proof"


def test_an_attestation_with_no_job_id_proves_nothing():
    """Absence of evidence is not evidence of absence. An attester that did not
    record WHICH job it ran has not identified anything, so this is a gap."""
    proof, err = _recovery_proof(FakeClient(_routes()), {"source": "restore-verify",
                                                         "clean": True})
    assert proof is None and err == ""


def test_no_attestation_at_all_proves_nothing():
    proof, err = _recovery_proof(FakeClient(_routes()), None)
    assert proof is None and err == ""


def test_a_job_the_commcell_cannot_confirm_fails_closed():
    """The attestation is our own artefact. If the vendor has no record of the job
    it names, we have a claim and no confirmation, which must never read as proof."""
    routes = _routes(**{"Job/9999999": (200, {"jobs": []})})
    proof, err = _recovery_proof(FakeClient(routes), {"restore_job": "9999999"})
    assert proof is None
    assert "9999999" in err and "no record" in err


def test_proof_read_error_propagates(tmp_path):
    wl = dict(WL, attestation_file=_attestation_file(tmp_path))
    reads = gather(FakeClient(_routes(**{"Job/7540314": (401, {})})), wl)
    assert reads.proof is None and reads.proof_error == "HTTP 401"


# --- list_vmgroups (the onboarding lookup) ---------------------------------- #
def test_list_vmgroups_returns_the_array():
    payload = {"vmGroups": [{"vmGroup": {"id": 35311, "name": "Steve-VM-Group"}}]}
    groups, err = list_vmgroups(FakeClient({"v4/vmgroups": (200, payload)}))
    assert err == "" and groups[0]["vmGroup"]["id"] == 35311


def test_list_vmgroups_uses_lowercase_plural_path():
    # The singular V4/VMGroup 404s for the list – the endpoint must be v4/vmgroups.
    groups, err = list_vmgroups(FakeClient({"V4/VMGroup": (200, {"vmGroups": [1]})}))
    assert groups == [] and err == "HTTP 404"


def test_list_vmgroups_propagates_error():
    groups, err = list_vmgroups(FakeClient({"v4/vmgroups": (403, {})}))
    assert groups == [] and err == "HTTP 403"

# --------------------------------------------------------------------------- #
# is_html_response – the guard that exists because STATUS CODE IS NOT ENOUGH.
#
# It lives in client.py because it is a transport question, not a workload one.
# It is tested here, next to the read path that depends on it, so the unit answer
# and the rung-level consequence stay in one place – and so FakeResponse is not
# duplicated into a second file for four assertions.
#
# On 2026-08-12 the tenant went into maintenance mid-session and answered GETs
# with HTTP 200 + an HTML page, and some POSTs with 405 + an HTML page. preflight
# reported "Commvault token valid" straight through it, and every write call site
# sailed past its `status_code != 200` check and died on .json().
# --------------------------------------------------------------------------- #
def test_html_content_type_is_not_an_api_response():
    assert client.is_html_response(FakeResponse(200, {}, content_type="text/html; charset=UTF-8")) is True


def test_an_html_body_is_caught_even_with_no_content_type():
    assert client.is_html_response(FakeResponse(200, {}, content_type="", text="<!DOCTYPE html><html>...")) is True
    assert client.is_html_response(FakeResponse(200, {}, content_type=None, text="\r\n  <html>")) is True


def test_real_json_is_not_mistaken_for_html():
    assert client.is_html_response(FakeResponse(200, {}, text='{"vmGroups": []}')) is False
    assert client.is_html_response(FakeResponse(200, {}, content_type="application/json;charset=utf-8", text="[]")) is False


def test_an_empty_body_is_not_html():
    # Not HTML, so not diagnosed as maintenance. Callers that need JSON still fail,
    # with the generic "body is not JSON" message, which is the honest distinction.
    assert client.is_html_response(FakeResponse(200, {}, content_type="", text="")) is False
    assert client.is_html_response(FakeResponse(200, {}, content_type=None, text=None)) is False


def test_a_maintenance_page_blocks_the_read_instead_of_passing_as_success():
    """A 200 carrying HTML must become a rung-level error, never an empty result
    that reads as 'nothing configured'. This is the live failure, reproduced."""
    client = FakeClient({"VM": (200, {})})
    client.routes["VM"] = (200, {})
    resp = FakeResponse(200, {}, content_type="text/html", text="<!DOCTYPE html>")
    client.get = lambda path: resp
    body, err = reads._get(client, "VM")
    assert body == {}
    assert "HTML page" in err and "maintenance" in err
