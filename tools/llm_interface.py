"""LLM interface for local open-source models."""

import logging

import requests


logger = logging.getLogger(__name__)


class LLMInterface:
    """Interface for interacting with local LLM services (Ollama/vLLM)."""
    
    def __init__(self, config):
        """Initialize the LLM interface.
        
        Args:
            config: Settings object with LLM configuration
        """
        self.config = config
        self.base_url = config.llm_endpoint
        self.model = config.llm_model
        self._verify_connection()

    def _verify_connection(self) -> bool:
        """Verify that the LLM service is accessible.
        
        Returns:
            True if service is reachable
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            logger.info(f"LLM service connected at {self.base_url}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to LLM service at {self.base_url}: {e}")
            raise RuntimeError(f"LLM service unavailable at {self.base_url}")

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> str:
        """Generate text from the local LLM via Ollama's /api/generate endpoint.

        Args:
            prompt: Input prompt
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum output length (Ollama's num_predict)

        Returns:
            Generated text (stripped)

        Raises:
            RuntimeError: If the request fails or returns a non-OK status.
        """
        logger.debug(f"Generating with model {self.model}, temperature={temperature}")
        options = {"temperature": temperature, "num_predict": max_tokens}
        # num_ctx lets a long-context model ingest the full article rather than
        # have Ollama silently truncate the prompt to the default window.
        ctx = getattr(self.config, "llm_context_window", 0)
        if ctx and ctx > 0:
            options["num_ctx"] = ctx
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.config.agent_timeout_seconds,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM generation request failed: {e}")
            raise RuntimeError(f"LLM generation failed: {e}") from e

        return response.json().get("response", "").strip()

    @staticmethod
    def _extract_mark(segment: str, ordered_marks: list[str]):
        """Return the first evidence mark found in a text segment, or None.

        Longer marks are checked first so "++"/"--"/"N/A" are not shadowed by
        "+"/"-": first a leading mark, then a mark appearing as a standalone
        token. ``ordered_marks`` must already be sorted longest-first.
        """
        for mark in ordered_marks:
            if segment.startswith(mark):
                return mark
        tokens = set(segment.replace(":", " ").split())
        for mark in ordered_marks:
            if mark in tokens:
                return mark
        return None

    @staticmethod
    def _parse_comparative(
        text: str, hypotheses: list[dict], evidence_marks: list[str]
    ) -> dict[str, str]:
        """Parse a per-hypothesis mark from a comparative response.

        Expects one line per hypothesis like ``h1: ++``. For each hypothesis id,
        finds its line and extracts the mark (preferring the text after a colon,
        which avoids confusing a "-" separator with a "-" mark). Hypotheses with
        no parseable mark default to "N/A".
        """
        ordered = sorted(evidence_marks, key=len, reverse=True)
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        result: dict[str, str] = {}
        for h in hypotheses:
            hid = h["id"]
            mark = None
            for line in lines:
                if line.lower().startswith(hid.lower()):
                    after = line.split(":", 1)[1].strip() if ":" in line else line[len(hid):].strip()
                    mark = LLMInterface._extract_mark(after, ordered)
                    if mark:
                        break
            result[hid] = mark or "N/A"
        return result

    def evaluate_hypotheses(
        self,
        article_content: str,
        hypotheses: list[dict],
        evidence_marks: list[str],
        temperature: float = None,
    ) -> dict[str, str]:
        """Comparatively score an article against all competing hypotheses at once.

        ACH evidence is diagnostic only insofar as it distinguishes between
        competing hypotheses, so all hypotheses are presented together in one
        prompt and the model assigns a mark to each. This improves discrimination
        (the model can weigh the alternatives) and cuts LLM calls to one per pass
        instead of one per hypothesis.

        Args:
            article_content: Full article text to evaluate
            hypotheses: Hypothesis dicts (id, name, description)
            evidence_marks: Valid evidence marks (++, +, N/A, -, --)
            temperature: Sampling temperature (uses config default if None)

        Returns:
            Dict mapping each hypothesis id -> evidence mark. On LLM failure,
            every hypothesis maps to "N/A" so one bad pass doesn't abort the run.
        """
        if temperature is None:
            temperature = self.config.llm_temperature

        hyp_block = "\n".join(
            f"{h['id']}: {h['name']} -- {h.get('description', '').strip()}"
            for h in hypotheses
        )
        answer_template = "\n".join(f"{h['id']}: <mark>" for h in hypotheses)

        prompt = f"""You are an intelligence analyst applying Analysis of Competing \
Hypotheses (ACH). You are given a NEWS ARTICLE and a set of COMPETING, mutually \
exclusive hypotheses. Assess the diagnostic value of the article for EACH \
hypothesis.

NEWS ARTICLE:
{article_content}

COMPETING HYPOTHESES:
{hyp_block}

For EACH hypothesis assign exactly one mark:
  ++  = the article gives STRONG evidence the hypothesis is TRUE
  +   = the article gives WEAK evidence the hypothesis is true
  N/A = the article presents NO evidence about this hypothesis (not relevant)
  -   = the article gives WEAK evidence the hypothesis is FALSE
  --  = the article gives STRONG evidence the hypothesis is false

Rules:
- If the article does not discuss the actors and stances the hypotheses are \
about, mark EVERY hypothesis N/A. The mere absence of contradiction is NOT support.
- The hypotheses are mutually exclusive: evidence supporting one is usually \
evidence against the others, so do not assign the same positive mark to several \
hypotheses -- favour the best-supported one.

Respond in EXACTLY this format, one line per hypothesis, nothing else:
{answer_template}"""

        logger.debug(
            f"Comparative evaluation of {len(hypotheses)} hypotheses, temp={temperature}"
        )
        try:
            raw = self.generate(
                prompt, temperature=temperature, max_tokens=self.config.llm_max_tokens
            )
        except RuntimeError as e:
            logger.warning(f"Comparative evaluation failed, defaulting all to N/A: {e}")
            return {h["id"]: "N/A" for h in hypotheses}

        return self._parse_comparative(raw, hypotheses, evidence_marks)

    def list_available_models(self) -> list[str]:
        """List available models on the LLM service.
        
        Returns:
            List of model names
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            data = response.json()
            models = [m["name"] for m in data.get("models", [])]
            return models
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to list models: {e}")
            return []
