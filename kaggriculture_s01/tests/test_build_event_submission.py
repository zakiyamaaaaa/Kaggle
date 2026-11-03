from scripts.build_event_cnn_ppo_submission import selected_source


def test_selected_source_extracts_assignments_and_functions(tmp_path):
    path = tmp_path / "sample.py"
    path.write_text("A = 1\nB = 2\ndef wanted():\n    return A\ndef ignored():\n    return B\n")
    source = selected_source(path, {"A", "wanted"})
    assert "A = 1" in source
    assert "def wanted" in source
    assert "B = 2" not in source
    assert "def ignored" not in source
