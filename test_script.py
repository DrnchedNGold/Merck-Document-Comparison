import sys
import os

# Add current directory to path if needed
sys.path.append(os.getcwd())

from engine.docx_body_ingest import parse_docx_body_ir
from engine.paragraph_alignment import alignment_for_track_changes_emit
from engine.contracts import DEFAULT_WORD_LIKE_COMPARE_CONFIG

def get_text_from_block(block):
    if block.get('type') == 'paragraph':
        return "".join(run.get('text', '') for run in block.get('runs', []))
    elif block.get('type') == 'table':
        # Simple text representation of a table for search purposes
        texts = []
        for row in block.get('rows', []):
            for cell in row:
                for p in cell.get('paragraphs', []):
                    texts.append("".join(run.get('text', '') for run in p.get('runs', [])))
        return " ".join(texts)
    return ""

def main():
    path1 = "sample-docs/email1docs/diversity-plan-bladder-cancer-version1.docx"
    path2 = "sample-docs/email1docs/diversity-plan-bladder-cancer-version2.docx"

    if not os.path.exists(path1) or not os.path.exists(path2):
        print(f"Paths check failed. PWD: {os.getcwd()}")
        return

    ir1 = parse_docx_body_ir(path1)
    ir2 = parse_docx_body_ir(path2)

    keywords = ['1.2.1.1', '1.2.1.2', 'Environmental Factors', 'environmental factors', 'Coexisting Medical Conditions', 'coexisting medical conditions']

    hit_indices_orig = []
    hit_indices_revised = []

    print("--- Matches in Version 1 (Original) ---")
    blocks1 = ir1.get('blocks', [])
    for i, block in enumerate(blocks1):
        text = get_text_from_block(block)
        if any(kw in text for kw in keywords):
            print(f"Orig Index {i}: {text[:100]}")
            hit_indices_orig.append(i)

    print("\n--- Matches in Version 2 (Revised) ---")
    blocks2 = ir2.get('blocks', [])
    for i, block in enumerate(blocks2):
        text = get_text_from_block(block)
        if any(kw in text for kw in keywords):
            print(f"Revised Index {i}: {text[:100]}")
            hit_indices_revised.append(i)

    alignment = alignment_for_track_changes_emit(ir1, ir2, DEFAULT_WORD_LIKE_COMPARE_CONFIG)

    print("\n--- Alignment Rows near hits ---")
    for row in alignment:
        # alignment_for_track_changes_emit usually returns a list of EmitAlignmentRow
        # which has .orig_index, .revised_index, .revised_merge_end_exclusive attributes
        orig_idx = getattr(row, 'orig_index', None)
        revised_idx = getattr(row, 'revised_index', None)
        revised_merge_end = getattr(row, 'revised_merge_end_exclusive', None)
        
        near_orig = any(abs(orig_idx - h) <= 5 for h in hit_indices_orig if (orig_idx is not None and h is not None))
        near_revised = any(abs(revised_idx - h) <= 5 for h in hit_indices_revised if (revised_idx is not None and h is not None))
        
        if near_orig or near_revised:
             print(f"(orig_index: {orig_idx}, revised_index: {revised_idx}, revised_merge_end_exclusive: {revised_merge_end})")

if __name__ == "__main__":
    main()
