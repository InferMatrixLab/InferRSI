from inferrsi.apps.views.dashboard import _write_view_document, render_dashboard


def test_service_reuse_page_can_be_rewritten_by_the_dashboard_writer(tmp_path):
    # write_dashboard renders this page and replaces only pages it recognizes as its own.
    snapshot = {"data": {"evaluation_mode": "service_reuse"}, "chart": "<svg></svg>"}
    page = render_dashboard(snapshot)
    output = tmp_path / "dashboard.html"
    assert _write_view_document(output, page, generator="InferRSI dashboard") == output
    assert _write_view_document(output, page, generator="InferRSI dashboard") == output
    assert output.read_text(encoding="utf-8") == page
