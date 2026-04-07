def test_streamlit_app_imports() -> None:
    import app.ui.streamlit_app as streamlit_app

    assert hasattr(streamlit_app, "main")
