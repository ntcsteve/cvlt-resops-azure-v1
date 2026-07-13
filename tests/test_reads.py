"""The read layer — gather() over a fake client. No live tenant.

classify()'s truth table (test_state.py) assumes well-formed Reads; these tests
cover the I/O path that BUILDS a Reads: the right GETs, parsing the VM out of the
list, scanning restore jobs for proof, and turning every failed read into an
error string (never an exception) so classify() can block on the right rung.
"""
from resops.reads import list_vmgroups
from resops.state import gather

WL = {"vm_group_id": 35311, "vm_name": "vm-rwk-ws-0610a-vm01"}


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code, self._payload = status_code, payload

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
            "isRestoreActivityEnabled": True, "lastSuccessfulBackupTime": 1781299030}


def _routes(**over):
    routes = {
        "V4/VMGroup/35311": (200, {"name": "Steve-VM-Group"}),
        # the by-name resolver lists groups, then fetches the matched id
        "v4/vmgroups": (200, {"vmGroups": [{"vmGroup": {"id": 35311, "name": "resops-resolveme-vg"}}]}),
        "VM": (200, {"vmStatusInfoList": [_vm()]}),
        "Job?jobFilter=Restore": (200, {"jobs": [{"jobSummary": {"jobId": 7540314, "status": "Completed"}}]}),
        "Job/7540314": (200, {"src": "vm-rwk-ws-0610a-vm01"}),
    }
    routes.update(over)
    return routes


def test_gather_collects_all_three_lanes():
    reads = gather(FakeClient(_routes()), WL)
    assert reads.vm_name == "vm-rwk-ws-0610a-vm01"
    assert reads.vmgroup["name"] == "Steve-VM-Group" and reads.vmgroup_error == ""
    assert reads.vm["name"] == "vm-rwk-ws-0610a-vm01" and reads.vm_error == ""
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


def test_proof_requires_the_job_detail_to_reference_our_vm():
    # restore job exists, but its detail names a different VM → no proof
    routes = _routes(**{"Job/7540314": (200, {"src": "some-other-vm"})})
    assert gather(FakeClient(routes), WL).proof is None


def test_proof_read_error_propagates():
    reads = gather(FakeClient(_routes(**{"Job?jobFilter=Restore": (401, {})})), WL)
    assert reads.proof is None and reads.proof_error == "HTTP 401"


# --- list_vmgroups (the onboarding lookup) ---------------------------------- #
def test_list_vmgroups_returns_the_array():
    payload = {"vmGroups": [{"vmGroup": {"id": 35311, "name": "Steve-VM-Group"}}]}
    groups, err = list_vmgroups(FakeClient({"v4/vmgroups": (200, payload)}))
    assert err == "" and groups[0]["vmGroup"]["id"] == 35311


def test_list_vmgroups_uses_lowercase_plural_path():
    # The singular V4/VMGroup 404s for the list — the endpoint must be v4/vmgroups.
    groups, err = list_vmgroups(FakeClient({"V4/VMGroup": (200, {"vmGroups": [1]})}))
    assert groups == [] and err == "HTTP 404"


def test_list_vmgroups_propagates_error():
    groups, err = list_vmgroups(FakeClient({"v4/vmgroups": (403, {})}))
    assert groups == [] and err == "HTTP 403"
