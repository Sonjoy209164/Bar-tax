import streamlit as st


def main() -> None:
    st.set_page_config(page_title="Bangla Tax RAG", layout="wide")
    st.title("Bangla Tax RAG")
    st.write("Starter interface for ingestion, retrieval, and evaluation experiments.")

    query_text = st.text_input("Enter a research query", placeholder="e.g. What is the current tax-free income threshold?")
    retrieval_mode = st.selectbox("Retrieval mode", options=["sparse", "dense", "hybrid"], index=2)
    run_button = st.button("Run placeholder query")

    if run_button:
        st.success(f"Placeholder query submitted with mode '{retrieval_mode}'.")
        st.json({"query": query_text, "mode": retrieval_mode, "status": "not_implemented"})


if __name__ == "__main__":
    main()
