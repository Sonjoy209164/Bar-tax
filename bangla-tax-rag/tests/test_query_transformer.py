from app.domain import QueryExecutionPath, QueryType
from app.retrieval import QueryTransformer, build_query_plan


def test_definition_query_plan_expands_exact_definition_patterns() -> None:
    plan = build_query_plan("What is the definition of Commissioner?")

    assert plan.query_type is QueryType.DEFINITION
    assert 3 <= len(plan.steps) <= 5
    sub_queries = [step.sub_query.lower() for step in plan.steps]
    assert any("definition of commissioner" in sub_query for sub_query in sub_queries)
    assert any('"commissioner" means' in sub_query for sub_query in sub_queries)
    assert "commissioner of taxes" in " ".join(plan.legal_expansions).lower()


def test_section_query_plan_adds_section_disambiguation_filters() -> None:
    plan = build_query_plan("How many classes of income tax authorities are listed under section 4?")

    assert plan.query_type is QueryType.COUNT_LOOKUP
    assert plan.section_references == ["4"]
    assert any(step.metadata_filters.get("section_number") == "4" for step in plan.steps)
    assert any("section 4" in step.sub_query.lower() for step in plan.steps)


def test_scenario_query_plan_decomposes_role_rule_and_table_queries() -> None:
    plan = build_query_plan("What is the car benefit for a director?")

    assert plan.query_type is QueryType.SCENARIO_REASONING
    assert plan.execution_path is QueryExecutionPath.AGENTIC
    sub_queries = [step.sub_query.lower() for step in plan.steps]
    assert any("definition of director" in sub_query for sub_query in sub_queries)
    assert any("perquisite director motor vehicle" in sub_query for sub_query in sub_queries)
    assert any("motor vehicle valuation table" in sub_query for sub_query in sub_queries)


def test_comparison_query_plan_splits_both_sides() -> None:
    transformer = QueryTransformer()
    plan = transformer.transform("Compare the Tax Day for a company and for an assessee other than a company.")

    assert plan.query_type is QueryType.COMPARISON
    assert plan.execution_path is QueryExecutionPath.AGENTIC
    goals = [step.goal for step in plan.steps]
    assert "first comparison side" in goals
    assert "second comparison side" in goals
