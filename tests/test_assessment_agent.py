"""Tests for the AssessmentAgent: comparative multi-pass self-consistency + flagging."""

from agents.assessment_agent import AssessmentAgent


class _MockLLM:
    """Returns a scripted {hyp_id: mark} dict per pass; counts calls."""

    def __init__(self, scripted_passes):
        self._passes = scripted_passes
        self.calls = 0

    def evaluate_hypotheses(self, article_content, hypotheses, evidence_marks, temperature=None):
        result = self._passes[self.calls % len(self._passes)]
        self.calls += 1
        return dict(result)


# --------------------------------------------------------------------------- #
# measure_self_consistency
# --------------------------------------------------------------------------- #
def test_self_consistency_full_agreement(config, hypotheses):
    agent = AssessmentAgent(config, hypotheses, _MockLLM([{}]))
    assert agent.measure_self_consistency(["++", "++", "++"]) == 1.0


def test_self_consistency_split(config, hypotheses):
    agent = AssessmentAgent(config, hypotheses, _MockLLM([{}]))
    assert agent.measure_self_consistency(["+", "+", "N/A"]) == 2 / 3


def test_self_consistency_empty(config, hypotheses):
    agent = AssessmentAgent(config, hypotheses, _MockLLM([{}]))
    assert agent.measure_self_consistency([]) == 0.0


# --------------------------------------------------------------------------- #
# assess_article
# --------------------------------------------------------------------------- #
def test_one_call_per_pass_not_per_hypothesis(config, hypotheses, article):
    config.llm_num_passes = 5
    llm = _MockLLM([{"h1": "++", "h2": "N/A", "h3": "-"}])
    AssessmentAgent(config, hypotheses, llm).assess_article(article)
    assert llm.calls == 5  # comparative: 5 passes, NOT 5 * 3 hypotheses


def test_unanimous_marks_high_confidence_not_flagged(config, hypotheses, article):
    config.llm_num_passes = 4
    llm = _MockLLM([{"h1": "++", "h2": "N/A", "h3": "-"}])  # same every pass
    result = AssessmentAgent(config, hypotheses, llm).assess_article(article)

    by_id = {hs.hypothesis_id: hs for hs in result.hypothesis_scores}
    assert by_id["h1"].evidence_mark == "++" and by_id["h1"].confidence == 1.0
    assert by_id["h2"].evidence_mark == "N/A"
    assert by_id["h3"].evidence_mark == "-"
    assert result.overall_confidence == 1.0
    assert result.flagged_for_human_review is False


def test_split_marks_lower_confidence_and_flagged(config, hypotheses, article):
    config.llm_num_passes = 4
    config.confidence_threshold = 0.6
    # h1 splits 2/2 -> confidence 0.5 (< threshold) -> flagged
    passes = [
        {"h1": "++", "h2": "N/A", "h3": "-"},
        {"h1": "+", "h2": "N/A", "h3": "-"},
        {"h1": "++", "h2": "N/A", "h3": "-"},
        {"h1": "+", "h2": "N/A", "h3": "-"},
    ]
    result = AssessmentAgent(config, hypotheses, _MockLLM(passes)).assess_article(article)
    by_id = {hs.hypothesis_id: hs for hs in result.hypothesis_scores}
    assert by_id["h1"].confidence == 0.5
    assert result.flagged_for_human_review is True


def test_majority_mark_wins(config, hypotheses, article):
    config.llm_num_passes = 5
    passes = [
        {"h1": "N/A", "h2": "N/A", "h3": "N/A"},
        {"h1": "N/A", "h2": "N/A", "h3": "N/A"},
        {"h1": "N/A", "h2": "N/A", "h3": "N/A"},
        {"h1": "+", "h2": "N/A", "h3": "N/A"},
        {"h1": "+", "h2": "N/A", "h3": "N/A"},
    ]
    result = AssessmentAgent(config, hypotheses, _MockLLM(passes)).assess_article(article)
    h1 = next(hs for hs in result.hypothesis_scores if hs.hypothesis_id == "h1")
    assert h1.evidence_mark == "N/A"        # 3/5 majority
    assert h1.confidence == 3 / 5


def test_execute_processes_all_articles(config, hypotheses, article):
    config.llm_num_passes = 2
    llm = _MockLLM([{"h1": "N/A", "h2": "N/A", "h3": "N/A"}])
    results = AssessmentAgent(config, hypotheses, llm).execute([article, article])
    assert len(results) == 2
