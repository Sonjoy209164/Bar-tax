from app.core.schemas import GenerationOptions, QuerySignals, RetrievalHit
from app.core.utils import preprocess_query
from app.generation.generator import generate_answer, parse_model_output


def _hit(
    *,
    chunk_id: str,
    score: float = 2.5,
    authority_level: str = "national",
    tax_year: str | None = "2025-2026",
    section_id: str | None = "3",
    subsection_id: str | None = "3.1",
    chunk_type: str = "table",
    text: str = "ধারা 3.1 অনুযায়ী 2025-2026 করহার 10 শতাংশ।",
) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk_id,
        doc_id="doc-1",
        doc_title="Income Tax Circular 2025-2026",
        page_no=10,
        section_id=section_id,
        subsection_id=subsection_id,
        chunk_type=chunk_type,
        authority_level=authority_level,
        tax_year=tax_year,
        original_text=text,
        normalized_text=text,
        heading_path=["ধারা 3.1", "করহার"],
        content=text,
        score=score,
        intermediate_scores={},
    )


def _options() -> GenerationOptions:
    return GenerationOptions(
        provider="mock",
        model_name="mock-grounded-generator",
        max_generation_tokens=256,
        temperature=0.0,
        abstention_score_threshold=0.75,
        verification_enabled=True,
    )


def _query() -> QuerySignals:
    return QuerySignals(
        original_query="২০২৫-২০২৬ করবর্ষে ধারা ৩.১ অনুযায়ী করহার কী?",
        normalized_query="2025-2026 করবর্ষে ধারা 3.1 অনুযায়ী করহার কী?",
        tax_year="2025-2026",
        section_reference="3.1",
        section_id="3",
        subsection_id="3.1",
        query_type="rate_lookup",
        query_intent="rate_lookup",
    )


def test_abstention_on_empty_evidence() -> None:
    result = generate_answer("করহার কী?", [], _query(), _options())

    assert result.abstained is True
    assert result.abstention_reason == "No evidence hits available."


def test_abstention_on_conflicting_evidence() -> None:
    hits = [
        _hit(chunk_id="c1", authority_level="national", tax_year="2025-2026"),
        _hit(chunk_id="c2", authority_level="national", tax_year="2024-2025"),
    ]
    result = generate_answer(
        "করহার কী?",
        hits,
        _query(),
        _options(),
        conflict_notes=["Potential tax-year conflict between c1 and c2."],
    )

    assert result.abstained is True


def test_verification_failure_for_unsupported_sentence() -> None:
    hits = [_hit(chunk_id="c1")]
    mocked_response = '{"answer_sentences":[{"sentence":"এই উত্তর সম্পূর্ণ নতুন দাবি করে।","citations":["[C9]"]}]}'

    result = generate_answer("করহার কী?", hits, _query(), _options(), mocked_response=mocked_response)

    assert result.abstained is True
    assert "Invalid citation marker" in (result.abstention_reason or "")


def test_generation_flow_using_mocked_model_response() -> None:
    hits = [_hit(chunk_id="c1"), _hit(chunk_id="c2", text="এটি কোম্পানির জন্য প্রযোজ্য।")]
    mocked_response = (
        '{"answer_sentences":['
        '{"sentence":"২০২৫-২০২৬ করবর্ষে ধারা ৩.১ অনুযায়ী করহার ১০ শতাংশ।","citations":["[C1]"]},'
        '{"sentence":"এটি কোম্পানির জন্য প্রযোজ্য।","citations":["[C2]"]}'
        '],"conflict_notes":[]}'
    )

    result = generate_answer("করহার কী?", hits, _query(), _options(), mocked_response=mocked_response)

    assert result.abstained is False
    assert result.verification_passed is True
    assert result.citations[0].marker == "[C1]"
    assert "[C1]" in result.answer_text
    assert result.used_chunk_ids == ["c1", "c2"]
    assert [citation.marker for citation in result.citations] == ["[C1]", "[C2]"]


def test_parse_model_output_accepts_fenced_json() -> None:
    answer_sentences, conflict_notes = parse_model_output(
        """```json
        {"answer_sentences":[{"sentence":"The income tax authorities include the National Board of Revenue.","citations":["[C1]"]}],"conflict_notes":[]}
        ```"""
    )

    assert conflict_notes == []
    assert len(answer_sentences) == 1
    assert answer_sentences[0].sentence_text == "The income tax authorities include the National Board of Revenue."
    assert answer_sentences[0].citation_markers == ["[C1]"]


def test_parse_model_output_accepts_wrapped_json() -> None:
    answer_sentences, conflict_notes = parse_model_output(
        'Here is the grounded answer JSON:\n{"answer_sentences":[{"sentence":"The income tax authorities include the National Board of Revenue.","citations":["[C1]"]}],"conflict_notes":["none"]}\nUse it carefully.'
    )

    assert conflict_notes == ["none"]
    assert len(answer_sentences) == 1
    assert answer_sentences[0].sentence_text == "The income tax authorities include the National Board of Revenue."
    assert answer_sentences[0].citation_markers == ["[C1]"]


def test_default_mock_generation_is_extractive_and_supported() -> None:
    hits = [_hit(chunk_id="c1", text="ধারা 3.1 অনুযায়ী 2025-2026 করহার 10 শতাংশ।")]

    result = generate_answer("২০২৫-২০২৬ করবর্ষে ধারা ৩.১ অনুযায়ী করহার কী?", hits, _query(), _options())

    assert result.abstained is False
    assert result.verification_passed is True
    assert "10 শতাংশ" in result.answer_text
    assert "[C1]" in result.answer_text


def test_llm_output_missing_citations_falls_back_to_extractive_answer() -> None:
    hits = [_hit(chunk_id="c1", text="ধারা 3.1 অনুযায়ী 2025-2026 করহার 10 শতাংশ।")]
    options = GenerationOptions(
        provider="openai_compatible",
        model_name="deepseek-r1:7b",
        base_url="http://127.0.0.1:11434/v1",
        api_key=None,
        max_generation_tokens=256,
        temperature=0.0,
        abstention_score_threshold=0.75,
        verification_enabled=True,
        fallback_to_mock=True,
    )

    result = generate_answer(
        "২০২৫-২০২৬ করবর্ষে ধারা ৩.১ অনুযায়ী করহার কী?",
        hits,
        _query(),
        options,
        mocked_response='{"answer_sentences":[{"sentence":"২০২৫-২০২৬ করবর্ষে করহার ১০ শতাংশ।","citations":[]}]}',
    )

    assert result.abstained is False
    assert result.verification_passed is True
    assert "[C1]" in result.answer_text


def test_mock_generation_cleans_bangla_ocr_noise_before_answering() -> None:
    noisy_text = (
        "আয়কর পররপত্র ২০২৫- ২০২৬ | 17\n"
        "ক্রমিক নং\n"
        "ধারা 3.1 অনুযায়ী\n"
        "করহার 10 শতাংশ।"
    )
    hits = [_hit(chunk_id="c1", text=noisy_text)]

    result = generate_answer("২০২৫-২০২৬ করবর্ষে ধারা ৩.১ অনুযায়ী করহার কী?", hits, _query(), _options())

    assert result.abstained is False
    assert "আয়কর পররপত্র" not in result.answer_text
    assert "ক্রমিক নং" not in result.answer_text
    assert "10 শতাংশ" in result.answer_text


def test_section_query_returns_used_citations_only() -> None:
    hits = [
        _hit(chunk_id="c1", text="3.1 ধারা অনুযায়ী কর অবকাশের সংজ্ঞা পরিবর্তন করা হয়েছে।"),
        _hit(chunk_id="c2", text="অন্য একটি অপ্রাসঙ্গিক সহায়ক অনুচ্ছেদ।", subsection_id="3.2"),
    ]
    query = QuerySignals(
        original_query="ধারা ৩.১ এ কী বলা হয়েছে?",
        normalized_query="ধারা 3.1 এ কী বলা হয়েছে?",
        section_reference="3.1",
        section_id="3",
        subsection_id="3.1",
        query_type="definition",
        query_intent="definition",
    )

    result = generate_answer("ধারা ৩.১ এ কী বলা হয়েছে?", hits, query, _options())

    assert result.abstained is False
    assert result.citations == [result.citations[0]]
    assert result.citations[0].marker == "[C1]"
    assert result.used_chunk_ids == ["c1"]


def test_preprocess_query_detects_mention_lookup() -> None:
    signals = preprocess_query("Is software service mentioned in the Act?")

    assert signals.query_type == "mention_lookup"
    assert signals.query_intent == "mention_lookup"
    assert "software service" in (signals.rewritten_query or "")


def test_preprocess_query_treats_say_about_as_mention_lookup() -> None:
    signals = preprocess_query("What does the Act say about software test lab service?")

    assert signals.query_type == "mention_lookup"
    assert signals.query_intent == "mention_lookup"


def test_preprocess_query_detects_amount_lookup() -> None:
    signals = preprocess_query(
        "What is the threshold amount in the charitable purpose clause for services in exchange for consideration?"
    )

    assert signals.query_type == "amount_lookup"
    assert signals.query_intent == "amount_lookup"


def test_preprocess_query_detects_date_lookup() -> None:
    signals = preprocess_query("What is the Tax Day for a company?")

    assert signals.query_type == "date_lookup"
    assert signals.query_intent == "date_lookup"


def test_preprocess_query_detects_count_lookup() -> None:
    signals = preprocess_query("How many classes of income tax authorities are listed under section 4?")

    assert signals.query_type == "count_lookup"
    assert signals.query_intent == "count_lookup"


def test_preprocess_query_detects_eligibility_lookup() -> None:
    signals = preprocess_query("I am a labour, what will be my tax?")

    assert signals.query_type == "eligibility"
    assert signals.query_intent == "eligibility"


def test_mention_lookup_uses_deterministic_grounded_answer() -> None:
    hits = [
        _hit(
            chunk_id="c1",
            score=3.4,
            tax_year=None,
            section_id="107",
            subsection_id=None,
            chunk_type="section",
            text=(
                "software test lab service;\n"
                "website development and service;\n"
                "IT assistance and software maintenance service;"
            ),
        ),
        _hit(
            chunk_id="c2",
            score=3.1,
            tax_year=None,
            section_id="5",
            subsection_id=None,
            chunk_type="section",
            text="Amortization of computer software and applications shall be allowed as follows.",
        ),
    ]
    query = preprocess_query("Is software service mentioned in the Act?")
    options = GenerationOptions(
        provider="openai_compatible",
        model_name="deepseek-r1:7b",
        base_url="http://127.0.0.1:11434/v1",
        api_key=None,
        max_generation_tokens=256,
        temperature=0.0,
        abstention_score_threshold=0.75,
        verification_enabled=True,
        fallback_to_mock=True,
    )

    result = generate_answer("Is software service mentioned in the Act?", hits, query, options)

    assert result.abstained is False
    assert result.verification_passed is True
    assert result.answer_text.startswith("Yes, the Act mentions")
    assert "[C1]" in result.answer_text
    assert result.used_chunk_ids == ["c1"]


def test_say_about_query_returns_focused_mention_answer() -> None:
    hits = [
        _hit(
            chunk_id="c1",
            score=3.8,
            tax_year=None,
            section_id="107",
            subsection_id=None,
            chunk_type="section",
            text="software test lab service; website development and service; IT assistance and software maintenance service;",
        ),
    ]
    query = preprocess_query("What does the Act say about software test lab service?")

    result = generate_answer("What does the Act say about software test lab service?", hits, query, _options())

    assert result.abstained is False
    assert result.verification_passed is True
    assert 'software test lab service' in result.answer_text.lower()
    assert "[C1]" in result.answer_text


def test_definition_query_prefers_exact_definition_sentence() -> None:
    hits = [
        _hit(
            chunk_id="c1",
            score=3.1,
            tax_year=None,
            section_id="2",
            subsection_id=None,
            chunk_type="section",
            text="(2) “Additional Commissioner of Taxes (Appeals)” means the Additional Commissioner of Taxes (Appeals) as referred to in section 4;",
        ),
        _hit(
            chunk_id="c2",
            score=3.0,
            tax_year=None,
            section_id="2",
            subsection_id=None,
            chunk_type="section",
            text="(19) “Commissioner” means Commissioner of Taxes or Commissioner of Taxes (Large Taxpayer Unit) as referred to in section 4;",
        ),
    ]
    query = preprocess_query("What is the definition of Commissioner?")

    result = generate_answer("What is the definition of Commissioner?", hits, query, _options())

    assert result.abstained is False
    assert result.verification_passed is True
    assert "commissioner" in result.answer_text.lower()
    assert "additional commissioner" not in result.answer_text.lower()
    assert result.used_chunk_ids == ["c2"]


def test_amount_lookup_returns_threshold_phrase() -> None:
    hits = [
        _hit(
            chunk_id="c1",
            score=3.5,
            tax_year=None,
            section_id="2",
            subsection_id=None,
            chunk_type="section",
            text=(
                "the aggregate value of such consideration in any income year exceeds "
                "Taka 1(one) crore;"
            ),
        ),
    ]
    query = preprocess_query(
        "What is the threshold amount in the charitable purpose clause for services in exchange for consideration?"
    )

    result = generate_answer(
        "What is the threshold amount in the charitable purpose clause for services in exchange for consideration?",
        hits,
        query,
        _options(),
    )

    assert result.abstained is False
    assert "Taka 1(one) crore" in result.answer_text
    assert result.used_chunk_ids == ["c1"]


def test_amount_lookup_handles_footnote_wrapped_amount_phrase() -> None:
    hits = [
        _hit(
            chunk_id="c1",
            score=3.5,
            tax_year=None,
            section_id="2",
            subsection_id=None,
            chunk_type="section",
            text="the aggregate value of such consideration in any income year exceeds Taka 2[1(one) crore];",
        ),
    ]
    query = preprocess_query(
        "What is the threshold amount in the charitable purpose clause for services in exchange for consideration?"
    )

    result = generate_answer(
        "What is the threshold amount in the charitable purpose clause for services in exchange for consideration?",
        hits,
        query,
        _options(),
    )

    assert result.abstained is False
    assert "Taka 1(one) crore" in result.answer_text


def test_duration_lookup_returns_successive_years_phrase() -> None:
    hits = [
        _hit(
            chunk_id="c1",
            score=3.6,
            tax_year=None,
            section_id="2",
            subsection_id=None,
            chunk_type="section",
            text="the amount of loss shall be carried forward and set off to the next 9 (nine) successive assessment years.",
        ),
    ]
    query = preprocess_query("For how many successive assessment years can startup losses be carried forward?")

    result = generate_answer(
        "For how many successive assessment years can startup losses be carried forward?",
        hits,
        query,
        _options(),
    )

    assert result.abstained is False
    assert "9 (nine) successive assessment years" in result.answer_text
    assert result.used_chunk_ids == ["c1"]


def test_count_lookup_counts_enumerated_items() -> None:
    hits = [
        _hit(
            chunk_id="c1",
            score=3.7,
            tax_year=None,
            section_id="4",
            subsection_id=None,
            chunk_type="section",
            text="(a) The National Board of Revenue; (b) Chief Commissioner of Taxes; (c) Director General (Inspection);",
        ),
    ]
    query = preprocess_query("How many classes of income tax authorities are listed under section 4?")

    result = generate_answer(
        "How many classes of income tax authorities are listed under section 4?",
        hits,
        query,
        _options(),
    )

    assert result.abstained is False
    assert "3 classes of income tax authorities" in result.answer_text
    assert result.used_chunk_ids == ["c1"]


def test_count_lookup_counts_across_multiple_authority_chunks() -> None:
    hits = [
        _hit(
            chunk_id="c1",
            score=3.7,
            tax_year=None,
            section_id="4",
            subsection_id=None,
            chunk_type="section",
            text="(a) The National Board of Revenue; (b) Chief Commissioner of Taxes; (c) Director General (Inspection);",
        ),
        _hit(
            chunk_id="c2",
            score=3.6,
            tax_year=None,
            section_id="16",
            subsection_id=None,
            chunk_type="section",
            text="(l) Tax Recovery Officers nominated by the Commissioner of Taxes within his jurisdiction;",
        ),
        _hit(
            chunk_id="c3",
            score=3.5,
            tax_year=None,
            section_id="4",
            subsection_id=None,
            chunk_type="section",
            text="(m) Assistant Commissioners of Taxes; (n) Extra Assistant Commissioners of Taxes; and (o) Inspectors of Taxes.",
        ),
    ]
    for hit in hits:
        hit.heading_path = ["TAX ADMINISTRATION", "4. Income tax authorities.—For the purposes of this Act, there shall be the"]
    query = preprocess_query("How many classes of income tax authorities are listed under section 4?")

    result = generate_answer(
        "How many classes of income tax authorities are listed under section 4?",
        hits,
        query,
        _options(),
    )

    assert result.abstained is False
    assert "7 classes of income tax authorities" in result.answer_text


def test_date_lookup_returns_tax_day_sentence() -> None:
    hits = [
        _hit(
            chunk_id="c1",
            score=3.3,
            tax_year=None,
            section_id="2",
            subsection_id=None,
            chunk_type="section",
            text=(
                "Tax Day means in the case of a company, the 15th (fifteenth) day of the seventh month "
                "following the end of the income year."
            ),
        ),
    ]
    query = preprocess_query("What is the Tax Day for a company?")

    result = generate_answer("What is the Tax Day for a company?", hits, query, _options())

    assert result.abstained is False
    assert "15th (fifteenth) day of the seventh month" in result.answer_text
    assert result.used_chunk_ids == ["c1"]


def test_date_lookup_extracts_company_tax_day_clause_from_definition_chunk() -> None:
    hits = [
        _hit(
            chunk_id="c1",
            score=3.3,
            tax_year=None,
            section_id="2",
            subsection_id=None,
            chunk_type="section",
            text=(
                "(23) “Tax Day” means— "
                "(a) in the case of an assesse other than a company, the 30th (thirtieth) day of November following the end of the income year; "
                "(b) in the case of a company, the 15th (fifteenth) day of the seventh month following the end of the income year or the fifteenth day of September following the end of the income year where the said fifteenth day falls before the fifteenth day of September; "
                "(c) in the case of an assessee, who is an individual and has not submitted return before, the 30th (thirtieth) day of June following the end of the income year."
            ),
        ),
    ]
    query = preprocess_query("What is the Tax Day for a company?")

    result = generate_answer("What is the Tax Day for a company?", hits, query, _options())

    assert result.abstained is False
    assert "Tax Day is the 15th (fifteenth) day of the seventh month" in result.answer_text


def test_section_query_can_answer_from_heading_path_when_heading_is_best_signal() -> None:
    hits = [
        _hit(
            chunk_id="c1",
            score=3.5,
            tax_year=None,
            section_id="4",
            subsection_id=None,
            chunk_type="section",
            text="There shall be the following classes, namely: (a) The National Board of Revenue;",
        )
    ]
    hits[0].heading_path = ["4. Income tax authorities.—For the purposes of this Act, there shall be the following classes of income tax authorities."]
    query = preprocess_query("What are the income tax authorities under section 4?")

    result = generate_answer("What are the income tax authorities under section 4?", hits, query, _options())

    assert result.abstained is False
    assert result.verification_passed is True
    assert "income tax authorities" in result.answer_text.lower()
    assert "[C1]" in result.answer_text


def test_eligibility_query_returns_cautious_grounded_answer() -> None:
    hits = [
        _hit(
            chunk_id="c1",
            score=3.6,
            tax_year=None,
            section_id="2",
            subsection_id=None,
            chunk_type="section",
            text=(
                "employee means any employee and also includes all other persons who receive income from employment "
                "under section 32: Provided that it shall not include any worker of a tea garden and day labourer."
            ),
        ),
        _hit(
            chunk_id="c2",
            score=3.4,
            tax_year=None,
            section_id="2",
            subsection_id=None,
            chunk_type="section",
            text="income includes any income, receipts, profits or gains which is chargeable to tax under any provision of this Act.",
        ),
    ]
    query = preprocess_query("I am a labour, what will be my tax?")

    result = generate_answer("I am a labour, what will be my tax?", hits, query, _options())

    assert result.abstained is False
    assert result.verification_passed is True
    assert "day labourer" in result.answer_text.lower()
    assert "chargeable to tax" in result.answer_text.lower()
    assert "exact tax" in result.answer_text.lower()
    assert result.used_chunk_ids == ["c1", "c2"]
