"""render_vmgroups – the `resops list` table. Pure, no tenant."""
import re

from resops.render import render_vmgroups

ANSI = re.compile(r"\033\[[0-9]+m")


def _plain(lines):
    return "\n".join(ANSI.sub("", ln) for ln in lines)


def test_table_shows_id_name_coverage():
    out = _plain(render_vmgroups([
        {"vmGroup": {"id": 35311, "name": "Steve-VM-Group"},
         "vmBackupInfo": {"vmProtectedCount": 1, "vmTotalCount": 1}},
        {"vmGroup": {"id": 123, "name": "example-group"},
         "vmBackupInfo": {"vmProtectedCount": 1, "vmTotalCount": 4}},
    ]))
    assert "35311" in out and "Steve-VM-Group" in out and "1/1" in out
    assert "123" in out and "1/4" in out
    assert "vm_group_id" in out             # the onboarding hint


def test_empty_list_is_a_clear_message():
    out = _plain(render_vmgroups([]))
    assert "no VM groups found" in out


def test_missing_fields_dont_crash():
    out = _plain(render_vmgroups([{}]))      # no vmGroup, no info
    assert "?" in out                        # id/name fall back to '?'
