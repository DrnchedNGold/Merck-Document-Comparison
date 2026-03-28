import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}

pytestmark = pytest.mark.golden_corpus


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sample_doc(relative_path: str) -> Path:
    return _repo_root() / "sample-docs" / relative_path


def _tracked_change_counts(docx_path: Path) -> tuple[int, int]:
    with zipfile.ZipFile(docx_path, "r") as zf:
        document_xml = zf.read("word/document.xml")
    root = ET.fromstring(document_xml)
    ins_count = len(root.findall(".//w:ins", NS))
    del_count = len(root.findall(".//w:del", NS))
    return ins_count, del_count


@pytest.mark.parametrize(
    "relative_path",
    [
        "email1docs/diversity-plan-bladder-cancer-version1.docx",
        "email1docs/diversity-plan-bladder-cancer-version2.docx",
        "email1docs/diversity-plan-cervical-cancer-version1.docx",
        "email1docs/diversity-plan-cervical-cancer-version2.docx",
        "email2docs/ind-general-investigation-plan-3475-v2.docx",
        "email2docs/ind-general-investigation-plan-V940-v1.docx",
        "email2docs/ind-general-investigation-plan-V940-v4.docx",
        "email3docs/1026-010-02.docx",
        "email3docs/1026-010-04.docx",
        "email3docs/7902-010-04.docx",
        "email3docs/7902-010-05.docx",
        "email3docs/ib-edition-6.docx",
        "email3docs/ib-edition-8.docx",
        "email3docs/ib-edition-10.docx",
        "email3docs/ib-edition-11.docx",
    ],
)
def test_source_docs_have_no_preexisting_tracked_changes(relative_path: str) -> None:
    docx_path = _sample_doc(relative_path)
    if not docx_path.is_file():
        pytest.skip(f"Sample doc not in workspace: {relative_path}")
    assert zipfile.is_zipfile(docx_path)
    ins_count, del_count = _tracked_change_counts(docx_path)
    assert ins_count == 0
    assert del_count == 0


@pytest.mark.parametrize(
    "relative_path",
    [
        "email1docs/diversity-plan-bladder-cancer-version2_compare_against-version1.docx",
        "email1docs/diversity-plan-cervical-cancer-version2_compare_against-version1.docx",
        "email2docs/ind-general-investigation-plan-3475-V2 compare to V1.docx",
        "email2docs/ind-general-investigation-plan-V940-V4 compare to V1.docx",
        "email3docs/1026-010-04_version_compare_against-02.docx",
        "email3docs/7902-010-05_version_compare_against-04.docx",
        "email3docs/ib-compare-edition-6-8.docx",
        "email3docs/ib-compare-edition-10-11.docx",
    ],
)
def test_reference_compare_outputs_include_tracked_changes(relative_path: str) -> None:
    docx_path = _sample_doc(relative_path)
    if not docx_path.is_file():
        pytest.skip(f"Reference compare output not in workspace: {relative_path}")
    assert zipfile.is_zipfile(docx_path)
    ins_count, del_count = _tracked_change_counts(docx_path)
    assert ins_count + del_count > 0
