from pathlib import Path

from app.core.schemas import ChunkRecord
from app.core.utils import preprocess_query, select_primary_section_markers
from app.retrieval.filters import (
    authority_value,
    chunk_navigation_noise_score,
    chunk_quality_score,
    filter_chunk_records,
    infer_chunk_tax_year,
)
from app.retrieval.sparse import (
    apply_score_boosts,
    build_sparse_index,
    load_sparse_index,
    save_sparse_index,
    search_sparse_index,
)


def _chunk(
    *,
    chunk_id: str,
    doc_id: str,
    doc_title: str,
    authority_level: str,
    tax_year: str | None,
    page_no: int,
    section_id: str | None,
    subsection_id: str | None,
    chunk_type: str,
    heading_path: list[str],
    normalized_text: str,
) -> ChunkRecord:
    return ChunkRecord(
        chunk_id=chunk_id,
        doc_id=doc_id,
        doc_title=doc_title,
        doc_type="circular",
        authority_level=authority_level,
        tax_year=tax_year,
        effective_start=None,
        effective_end=None,
        page_no=page_no,
        section_id=section_id,
        subsection_id=subsection_id,
        appendix_id=None,
        sro_id=None,
        chunk_type=chunk_type,
        heading_path=heading_path,
        original_text=normalized_text,
        normalized_text=normalized_text,
        cross_refs=[],
    )


def _dataset() -> list[ChunkRecord]:
    return [
        _chunk(
            chunk_id="c1",
            doc_id="doc-2025",
            doc_title="Income Tax Circular 2025-2026",
            authority_level="national",
            tax_year="2025-2026",
            page_no=1,
            section_id="3",
            subsection_id="3.1",
            chunk_type="table",
            heading_path=["ধারা 3.1", "করহার"],
            normalized_text="ধারা 3.1 অনুযায়ী 2025-2026 করহার 10 শতাংশ",
        ),
        _chunk(
            chunk_id="c2",
            doc_id="doc-2024",
            doc_title="Income Tax Circular 2024-2025",
            authority_level="regional",
            tax_year="2024-2025",
            page_no=2,
            section_id="3",
            subsection_id="3.1",
            chunk_type="table",
            heading_path=["ধারা 3.1", "করহার"],
            normalized_text="ধারা 3.1 অনুযায়ী 2024-2025 করহার 12 শতাংশ",
        ),
        _chunk(
            chunk_id="c3",
            doc_id="doc-example",
            doc_title="Worked Example Note",
            authority_level="national",
            tax_year="2025-2026",
            page_no=3,
            section_id="8",
            subsection_id="8.1",
            chunk_type="example",
            heading_path=["উদাহরণ"],
            normalized_text="উদাহরণ সহ কর গণনার পদ্ধতি",
        ),
    ]


def test_query_normalization_and_signal_extraction() -> None:
    signals = preprocess_query("  ২০২৫-২০২৬ ধারা ৩.১ উদাহরণ  ")

    assert signals.normalized_query == "2025-2026 ধারা 3.1 উদাহরণ"
    assert signals.tax_year == "2025-2026"
    assert signals.section_reference == "3.1"
    assert signals.query_type == "example"


def test_query_without_section_does_not_treat_tax_year_as_section() -> None:
    signals = preprocess_query("২০২৫-২০২৬ করবর্ষে কোম্পানির করহার কী?")

    assert signals.tax_year == "2025-2026"
    assert signals.section_reference is None
    assert signals.section_id is None
    assert signals.subsection_id is None


def test_english_company_tax_question_is_rate_lookup() -> None:
    signals = preprocess_query("what tax i have to pay as a software company ?")

    assert signals.query_type == "rate_lookup"
    assert signals.query_intent == "rate_lookup"
    assert signals.rewritten_query is not None
    assert "tax rate" in signals.rewritten_query
    assert "software" in signals.rewritten_query


def test_banglish_tax_year_question_expands_to_definition_terms() -> None:
    signals = preprocess_query("kor ortho bochor ki?")

    assert signals.query_type == "definition"
    assert signals.query_intent == "definition"
    assert "করবর্ষ" in signals.normalized_query
    assert "অর্থ বছর" in signals.normalized_query
    assert "সংজ্ঞা" in signals.normalized_query


def test_banglish_rate_question_is_rate_lookup() -> None:
    signals = preprocess_query("2025-2026 korhar koto?")

    assert signals.tax_year == "2025-2026"
    assert signals.query_type == "rate_lookup"
    assert signals.query_intent == "rate_lookup"
    assert "করহার" in signals.normalized_query
    assert "tax rate" in (signals.rewritten_query or "")


def test_banglish_section_reference_and_withholding_terms() -> None:
    signals = preprocess_query("dhara 52 utse kor koto?")

    assert signals.section_reference == "52"
    assert signals.section_id == "52"
    assert "উৎসে কর" in signals.normalized_query
    assert "ধারা" in signals.normalized_query


def test_banglish_personal_tax_question_routes_to_rate_lookup() -> None:
    signals = preprocess_query("ami freelancer amar kor koto?")

    assert signals.query_type == "rate_lookup"
    assert signals.query_intent == "rate_lookup"
    assert "স্বাভাবিক ব্যক্তি" in signals.normalized_query
    assert "tax payable" in signals.normalized_query


def test_single_paripatra_year_maps_to_tax_year() -> None:
    signals = preprocess_query("সরকারি দপ্তর বুক-ট্রান্সফার করলে ২০১৬ পরিপত্রে কী বলা হয়েছে?")

    assert signals.tax_year == "2016-2017"


def test_multi_year_query_prefers_target_year_over_from_year() -> None:
    signals = preprocess_query(
        "২০১৯-২০২০ থেকে রিটার্ন বাধ্যতামূলক কিন্তু কিছুই দাখিল করেননি-২০২২-২০২৩ সালে কী করা যাবে?"
    )

    assert signals.tax_year == "2022-2023"
    assert signals.query_type == "general"


def test_multi_year_query_without_from_marker_prefers_first_year() -> None:
    signals = preprocess_query("২০২৪-২০২৫ ও ২০২৫-২০২৬ করবর্ষে ট্রাস্টের হার কখন ২৫% হবে?")

    assert signals.tax_year == "2024-2025"


def test_tax_year_range_before_paripatra_does_not_create_next_year() -> None:
    signals = preprocess_query("২০২৫-২০২৬ পরিপত্রে প্রতিবন্ধী কর্মচারী নিয়োগে কী কর রেয়াত আছে?")

    assert signals.tax_year == "2025-2026"


def test_bangla_penalty_amount_question_routes_to_amount_lookup() -> None:
    signals = preprocess_query("আন্তর্জাতিক লেনদেনের তথ্য না দিলে জরিমানার পরিমাণ কী হতে পারে?")

    assert signals.query_type == "amount_lookup"
    assert signals.query_intent == "amount_lookup"
    assert "international transactions" in (signals.rewritten_query or "")


def test_bangla_surcharge_question_is_rate_not_definition() -> None:
    signals = preprocess_query("২০২৪-২০২৫ করবর্ষের সারচার্জে তামাকজাত পণ্য প্রস্তুতকারকের জন্য অতিরিক্ত কী বলা হয়েছে?")

    assert signals.tax_year == "2024-2025"
    assert signals.query_type == "rate_lookup"
    assert signals.query_intent == "rate_lookup"
    assert "surcharge" in (signals.rewritten_query or "")


def test_bangla_exemption_yes_no_question_is_eligibility() -> None:
    signals = preprocess_query("রিটার্ন দাখিলে বাধ্য করদাতা রিটার্ন না দিলে কর অব্যাহতি বা হ্রাসকৃত করহার পাবে কি?")

    assert signals.query_type == "eligibility"
    assert signals.query_intent == "eligibility"


def test_tax_year_filter_uses_doc_title_when_chunk_tax_year_is_missing() -> None:
    chunk = _chunk(
        chunk_id="c-null-year",
        doc_id="doc-2015",
        doc_title="Income Tax Paripatra 2015-2016",
        authority_level="national",
        tax_year=None,
        page_no=48,
        section_id="107",
        subsection_id=None,
        chunk_type="text",
        heading_path=["ধারা 107"],
        normalized_text="আন্তর্জাতিক লেনদেনের অনধিক 2% পর্যন্ত জরিমানা আরোপ করতে পারবেন।",
    )

    assert infer_chunk_tax_year(chunk) == "2015-2016"
    assert filter_chunk_records([chunk], tax_year="2015-2016") == [chunk]


def test_paripatra_doc_title_overrides_example_year_metadata() -> None:
    chunk = _chunk(
        chunk_id="c-example-year",
        doc_id="doc-2022",
        doc_title="Income Tax Paripatra 2022-2023",
        authority_level="national",
        tax_year="2019-2020",
        page_no=47,
        section_id=None,
        subsection_id=None,
        chunk_type="example",
        heading_path=["উদাহরণ"],
        normalized_text="2019-2020 আয়বর্ষে পরিচালক ছিলেন। 2022-2023 অর্থবর্ষে কোম্পানির করদায় পরিশোধে ব্যর্থ হয়েছে।",
    )

    assert infer_chunk_tax_year(chunk) == "2022-2023"
    assert filter_chunk_records([chunk], tax_year="2022-2023") == [chunk]
    assert filter_chunk_records([chunk], tax_year="2019-2020") == []


def test_explicit_future_tax_year_heading_overrides_paripatra_doc_title() -> None:
    chunk = _chunk(
        chunk_id="c-future-year-heading",
        doc_id="doc-2025",
        doc_title="Income Tax Paripatra 2025-2026",
        authority_level="national",
        tax_year="2026-2027",
        page_no=12,
        section_id=None,
        subsection_id=None,
        chunk_type="table",
        heading_path=["১.৪ ২০২৬-২০২৭ এবং ২০২৭-২০২৮ করবর্ষের সারচার্জের হার"],
        normalized_text="নীট পরিসম্পদের পরিমাণ চার কোটি টাকা পর্যন্ত শূন্য।",
    )

    assert infer_chunk_tax_year(chunk) == "2026-2027"
    assert filter_chunk_records([chunk], tax_year="2026-2027") == [chunk]
    assert filter_chunk_records([chunk], tax_year="2025-2026") == []


def test_navigation_noise_penalizes_early_outline_not_real_rate_table() -> None:
    outline_chunk = _chunk(
        chunk_id="outline",
        doc_id="doc-2019",
        doc_title="Income Tax Paripatra 2019-2020",
        authority_level="national",
        tax_year="2019-2020",
        page_no=3,
        section_id=None,
        subsection_id=None,
        chunk_type="section",
        heading_path=["২০১৯-২০২০ কর বছরের জন্য প্রযোজ্য আয়কর হার"],
        normalized_text="(ক) ব্যক্তি করদাতার জন্য সাধারণ করহার\n(খ) কোম্পানি ব্যতীত করহার\n(গ) কোম্পানির করহার",
    )
    table_chunk = _chunk(
        chunk_id="rate-table",
        doc_id="doc-2019",
        doc_title="Income Tax Paripatra 2019-2020",
        authority_level="national",
        tax_year=None,
        page_no=10,
        section_id=None,
        subsection_id=None,
        chunk_type="table",
        heading_path=["২০১৯-২০ কর বছরের জন্য প্রযোজ্য আয়কর হার"],
        normalized_text="মোট আয়\nহার\nপ্রথম 250,000 টাকা পর্যন্ত শূন্য\nপরবর্তী 4,00,000 টাকা 10%",
    )

    assert chunk_navigation_noise_score(outline_chunk) > 0.5
    assert chunk_navigation_noise_score(table_chunk) == 0.0


def test_personal_labour_tax_question_is_eligibility() -> None:
    signals = preprocess_query("I am a labour, what will be my tax?")

    assert signals.query_type == "eligibility"
    assert signals.query_intent == "eligibility"
    assert "day labourer" in (signals.rewritten_query or "")


def test_threshold_question_is_amount_lookup() -> None:
    signals = preprocess_query(
        "What is the threshold amount in the charitable purpose clause for services in exchange for consideration?"
    )

    assert signals.query_type == "amount_lookup"
    assert signals.query_intent == "amount_lookup"
    assert "threshold" in (signals.rewritten_query or "")


def test_section_marker_selection_prefers_heading_for_list_continuations_with_footnotes() -> None:
    section_id, subsection_id = select_primary_section_markers(
        "(k) Deputy Commissioners of Taxes;\n1 The words ... by section 16(a) of the Finance Act, 2024.",
        heading_path=["TAX ADMINISTRATION", "4. Income tax authorities.—For the purposes of this Act"],
        page_section_markers=["4", "16"],
    )

    assert section_id == "4"
    assert subsection_id is None


def test_tax_day_question_is_date_lookup() -> None:
    signals = preprocess_query("What is the Tax Day for a company?")

    assert signals.query_type == "date_lookup"
    assert signals.query_intent == "date_lookup"


def test_how_many_items_question_is_count_lookup() -> None:
    signals = preprocess_query("How many classes of income tax authorities are listed under section 4?")

    assert signals.query_type == "count_lookup"
    assert signals.query_intent == "count_lookup"


def test_how_many_years_question_prefers_duration_lookup() -> None:
    signals = preprocess_query("For how many successive assessment years can startup losses be carried forward?")

    assert signals.query_type == "duration_lookup"
    assert signals.query_intent == "duration_lookup"


def test_compare_question_is_detected_as_comparison() -> None:
    signals = preprocess_query("Compare the Tax Day for a company and for an assessee other than a company.")

    assert signals.query_type == "comparison"
    assert signals.query_intent == "comparison"


def test_filtering_by_tax_year() -> None:
    filtered = filter_chunk_records(_dataset(), tax_year="2025-2026")

    assert {chunk.chunk_id for chunk in filtered} == {"c1", "c3"}


def test_chunk_quality_score_treats_english_legal_text_as_substantive() -> None:
    text = (
        "4. Income tax authorities.—For the purposes of this Act, there shall be the following classes "
        "of income tax authorities, namely: (a) The National Board of Revenue; (b) Chief Commissioner of Taxes."
    )

    assert chunk_quality_score(text) >= 0.3


def test_section_match_boost_and_authority_boost() -> None:
    query_signals = preprocess_query("ধারা 3.1 করহার")
    high_authority_score = apply_score_boosts(_dataset()[0], query_signals, 1.0)
    lower_authority_score = apply_score_boosts(_dataset()[1], query_signals, 1.0)

    assert high_authority_score > lower_authority_score
    assert authority_value("national") > authority_value("regional")


def test_sparse_retrieval_on_synthetic_dataset(tmp_path: Path) -> None:
    sparse_index = build_sparse_index(_dataset())
    save_sparse_index(sparse_index, tmp_path / "sparse")
    loaded_index = load_sparse_index(tmp_path / "sparse")

    response = search_sparse_index(
        query="২০২৫-২০২৬ ধারা ৩.১ করহার",
        index=loaded_index,
        top_k=2,
    )

    assert response.hits
    assert response.hits[0].chunk_id == "c1"
    assert response.hits[0].tax_year == "2025-2026"


def test_graceful_empty_results_after_filtering() -> None:
    response = search_sparse_index(
        query="করহার",
        index=build_sparse_index(_dataset()),
        top_k=3,
        tax_year="2030-2031",
    )

    assert response.hits == []


def test_sparse_retrieval_drops_lexically_unrelated_hits_for_company_tax_query() -> None:
    dataset = [
        _chunk(
            chunk_id="company-rate",
            doc_id="doc-1",
            doc_title="Company Tax Rates",
            authority_level="national",
            tax_year="2025-2026",
            page_no=5,
            section_id="2",
            subsection_id="2.3",
            chunk_type="table",
            heading_path=["Company tax rate"],
            normalized_text="Company tax rate for resident company is 20 percent.",
        ),
        _chunk(
            chunk_id="irrelevant",
            doc_id="doc-2",
            doc_title="Appeal Procedure",
            authority_level="national",
            tax_year="2025-2026",
            page_no=99,
            section_id="15",
            subsection_id=None,
            chunk_type="text",
            heading_path=["Appeal procedure"],
            normalized_text="Executor administrator successor and other legal representative of the assessee.",
        ),
    ]

    response = search_sparse_index(
        query="what tax i have to pay as a software company ?",
        index=build_sparse_index(dataset),
        top_k=2,
        tax_year="2025-2026",
    )

    assert response.hits
    assert response.hits[0].chunk_id == "company-rate"
    assert all(hit.chunk_id != "irrelevant" for hit in response.hits)


def test_sparse_retrieval_prefers_amount_threshold_chunk() -> None:
    dataset = [
        _chunk(
            chunk_id="threshold",
            doc_id="act-2023",
            doc_title="Income Tax Act 2023",
            authority_level="national",
            tax_year=None,
            page_no=12,
            section_id="2",
            subsection_id=None,
            chunk_type="section",
            heading_path=["2. Definitions"],
            normalized_text="the aggregate value of such consideration in any income year exceeds Taka 1(one) crore;",
        ),
        _chunk(
            chunk_id="irrelevant-rate",
            doc_id="act-2023",
            doc_title="Income Tax Act 2023",
            authority_level="national",
            tax_year=None,
            page_no=234,
            section_id="3",
            subsection_id=None,
            chunk_type="table",
            heading_path=["4. Tax rate table"],
            normalized_text="the tax rate mentioned in column (3) shall be 100% higher",
        ),
    ]

    response = search_sparse_index(
        query="What is the threshold amount in the charitable purpose clause for services in exchange for consideration?",
        index=build_sparse_index(dataset),
        top_k=2,
    )

    assert response.hits
    assert response.hits[0].chunk_id == "threshold"


def test_field_aware_sparse_index_prefers_exact_section_chunk_over_incidental_reference() -> None:
    dataset = [
        _chunk(
            chunk_id="exact-section",
            doc_id="act-2023",
            doc_title="Income Tax Act 2023",
            authority_level="national",
            tax_year=None,
            page_no=24,
            section_id="4",
            subsection_id=None,
            chunk_type="section",
            heading_path=["4. Income tax authorities"],
            normalized_text="There shall be the following classes of income tax authorities, namely.",
        ),
        _chunk(
            chunk_id="incidental-reference",
            doc_id="act-2023",
            doc_title="Income Tax Act 2023",
            authority_level="national",
            tax_year=None,
            page_no=207,
            section_id="295",
            subsection_id=None,
            chunk_type="section",
            heading_path=["295. Appeal to the Appellate Division"],
            normalized_text="A Commissioner of Taxes from among the income tax authorities under section 4 may represent in the Alternative Dispute Resolution process.",
        ),
    ]

    response = search_sparse_index(
        query="What are the income tax authorities under section 4?",
        index=build_sparse_index(dataset),
        top_k=2,
    )

    assert response.hits
    assert response.hits[0].chunk_id == "exact-section"
    assert response.hits[0].intermediate_scores["field_heading_score"] >= 0
    assert "field_structure_score" in response.hits[0].intermediate_scores


def test_sparse_retrieval_prefers_labour_status_chunk_for_personal_tax_question() -> None:
    dataset = [
        _chunk(
            chunk_id="labour-status",
            doc_id="act-2023",
            doc_title="Income Tax Act 2023",
            authority_level="national",
            tax_year=None,
            page_no=8,
            section_id="2",
            subsection_id=None,
            chunk_type="section",
            heading_path=["2. Definitions"],
            normalized_text=(
                "employee means any employee and also includes all other persons who receive income from employment "
                "under section 32: Provided that it shall not include any worker of a tea garden and day labourer."
            ),
        ),
        _chunk(
            chunk_id="chargeable-income",
            doc_id="act-2023",
            doc_title="Income Tax Act 2023",
            authority_level="national",
            tax_year=None,
            page_no=4,
            section_id="2",
            subsection_id=None,
            chunk_type="section",
            heading_path=["2. Definitions"],
            normalized_text="income includes any income which is chargeable to tax under any provision of this Act.",
        ),
        _chunk(
            chunk_id="irrelevant-company-rate",
            doc_id="act-2023",
            doc_title="Income Tax Act 2023",
            authority_level="national",
            tax_year=None,
            page_no=230,
            section_id="163",
            subsection_id=None,
            chunk_type="table",
            heading_path=["163. Rates of tax for company"],
            normalized_text="the rate of tax for a company shall be 20 percent.",
        ),
    ]

    response = search_sparse_index(
        query="I am a labour, what will be my tax?",
        index=build_sparse_index(dataset),
        top_k=3,
    )

    assert response.signals.query_intent == "eligibility"
    assert response.hits
    assert response.hits[0].chunk_id == "labour-status"
    assert "chargeable-income" in {hit.chunk_id for hit in response.hits[:2]}


def test_sparse_retrieval_prefers_startup_loss_duration_chunk() -> None:
    dataset = [
        _chunk(
            chunk_id="startup-loss",
            doc_id="act-2023",
            doc_title="Income Tax Act 2023",
            authority_level="national",
            tax_year=None,
            page_no=286,
            section_id="2",
            subsection_id=None,
            chunk_type="section",
            heading_path=["STARTUP SANDBOX"],
            normalized_text="the amount of loss shall be carried forward and set off to the next 9 (nine) successive assessment years.",
        ),
        _chunk(
            chunk_id="generic-assessment-year",
            doc_id="act-2023",
            doc_title="Income Tax Act 2023",
            authority_level="national",
            tax_year=None,
            page_no=234,
            section_id="3",
            subsection_id=None,
            chunk_type="table",
            heading_path=["4. Wealth tax table"],
            normalized_text="assets and liabilities or balance sheet furnished with the return filed for the assessment year 2024-25.",
        ),
    ]

    response = search_sparse_index(
        query="For how many successive assessment years can startup losses be carried forward?",
        index=build_sparse_index(dataset),
        top_k=2,
    )

    assert response.hits
    assert response.hits[0].chunk_id == "startup-loss"


def test_exact_section_heading_is_preferred_over_incidental_section_reference() -> None:
    dataset = [
        _chunk(
            chunk_id="exact-section",
            doc_id="act-2023",
            doc_title="Income Tax Act 2023",
            authority_level="national",
            tax_year=None,
            page_no=24,
            section_id="4",
            subsection_id=None,
            chunk_type="section",
            heading_path=["4. Income tax authorities.—For the purposes of this Act"],
            normalized_text="4. Income tax authorities.—For the purposes of this Act, there shall be the following classes of income tax authorities.",
        ),
        _chunk(
            chunk_id="incidental-reference",
            doc_id="act-2023",
            doc_title="Income Tax Act 2023",
            authority_level="national",
            tax_year=None,
            page_no=207,
            section_id="4",
            subsection_id=None,
            chunk_type="section",
            heading_path=["295. Appeal to the Appellate Division.—(1)"],
            normalized_text="Commissioner of Taxes from among the income tax authorities under section 4 to represent in the Alternative Dispute Resolution process.",
        ),
    ]

    response = search_sparse_index(
        query="What are the income tax authorities under section 4?",
        index=build_sparse_index(dataset),
        top_k=2,
    )

    assert response.hits
    assert response.hits[0].chunk_id == "exact-section"


def test_definition_query_prefers_definition_clause_for_commissioner() -> None:
    dataset = [
        _chunk(
            chunk_id="broader-definition-clause",
            doc_id="act-2023",
            doc_title="Income Tax Act 2023",
            authority_level="national",
            tax_year=None,
            page_no=3,
            section_id="2",
            subsection_id=None,
            chunk_type="section",
            heading_path=["2. Definitions.— In this Act"],
            normalized_text="(2) “Additional Commissioner of Taxes (Appeals)” means the Additional Commissioner of Taxes (Appeals) and Joint Commissioner of Taxes (Appeals) as referred to in section 4.",
        ),
        _chunk(
            chunk_id="definition-clause",
            doc_id="act-2023",
            doc_title="Income Tax Act 2023",
            authority_level="national",
            tax_year=None,
            page_no=6,
            section_id="2",
            subsection_id=None,
            chunk_type="section",
            heading_path=["2. Definitions.— In this Act"],
            normalized_text="(19) “Commissioner” means Commissioner of Taxes or Commissioner of Taxes (Large Taxpayer Unit) as referred to in section 4.",
        ),
        _chunk(
            chunk_id="incidental-commissioner",
            doc_id="act-2023",
            doc_title="Income Tax Act 2023",
            authority_level="national",
            tax_year=None,
            page_no=237,
            section_id="3",
            subsection_id=None,
            chunk_type="section",
            heading_path=["3. Withdrawal of approval.—(1)"],
            normalized_text="If the Commissioner is satisfied that the conditions mentioned in paragraphs 2 and 3 have been violated.",
        ),
    ]

    response = search_sparse_index(
        query="What is the definition of Commissioner?",
        index=build_sparse_index(dataset),
        top_k=3,
    )

    assert response.hits
    assert response.hits[0].chunk_id == "definition-clause"
