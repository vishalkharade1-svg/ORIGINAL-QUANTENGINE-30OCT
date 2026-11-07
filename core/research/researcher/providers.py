"""
====================================================

QuantEngine

Autonomous AI Researcher -- provider abstraction (Phase 9H)

PROVIDER-NEUTRAL: the researcher talks to an AIProvider, not to any
specific vendor. Providers (OpenAI / Anthropic / OpenRouter / Ollama
/ future) are OPTIONAL: the deterministic research engine must keep
working with NO provider installed, and it does -- the built-in
NullProvider is always available and performs deterministic,
rule-driven hypothesis drafting from observed evidence.

The mathematical truth ALWAYS comes from QuantEngine's deterministic
machinery (9B-9G): a provider may only formulate hypotheses, design
experiments from the already-supported vocabulary, and interpret the
structured evidence. It can never invent experiment semantics,
declare production-readiness, or trade.

Contract:
   * no provider SDK is imported at module import time
   * external providers degrade to PROVIDER_UNAVAILABLE when their
     SDK and/or explicit configuration is absent -- the researcher
     falls back to the deterministic NullProvider
   * available() never lies, never prompts, never crashes
====================================================
"""

from core.research.researcher.types import EvidenceContext, PROVIDER_UNAVAILABLE


class ProviderUnavailable(RuntimeError):
    """Raised when an AIProvider is not configured/available."""


class AIProvider:
    """Abstract AI provider bound for research orchestration only."""

    name = "base"
    description = ""

    def __init__(self, required_env=()):
        self.required_env = tuple(required_env)

    # -------------------------------------------------

    def available(self):
        return False

    def unavailable_note(self):
        missing_env = [
            k for k in self.required_env
            if not _env(k)
        ]
        note = PROVIDER_UNAVAILABLE
        if missing_env:
            note = (
                f"{PROVIDER_UNAVAILABLE}: missing environment "
                f"({', '.join(sorted(missing_env))})"
            )
        return note

    def explain(self):
        return self.description

    def propose_hypotheses(self, context):
        """Return a list of hypothesis drafts (dicts) for this
        evidence context. Deterministic for NullProvider."""
        raise NotImplementedError(
            f"{type(self).__name__} does not implement hypothesis drafting"
        )


class NullProvider(AIProvider):
    """The deterministic, always-available research provider.

    It drives hypothesis design through fixed evidence-gated rules --
    no randomness, no network, no external dependency. It never
    guesses: with no usable opportunities it proposes nothing."""

    name = "null"
    description = (
        "Deterministic rule-driven planner. Always available, offline, "
        "produces hypotheses only from observed 9A-9G evidence."
    )

    def available(self):
        return True

    def propose_hypotheses(self, context):
        if not isinstance(context, EvidenceContext):
            raise TypeError("context must be an EvidenceContext")
        return _deterministic_drafts(context)


def _draft(kind, question, statement, why, overrides,
           features=(), outcome_bars=None):
    return {
        "kind": kind,
        "question": question,
        "statement": statement,
        "why": why,
        "overrides": dict(overrides),
        "features": tuple(features),
        "outcome_bars": outcome_bars,
    }


def _deterministic_drafts(context):
    """Evidence-gated rule templates (QUESTIONS -> HYPOTHESES)."""
    pop = context.population
    reasons = context.rejected_by_reason
    drafts = []

    if context.vacuous:
        return drafts

    if pop.get("ENTRY_NOT_REACHED", 0) > 0 or pop.get("REJECTED", 0) > 0:
        why = (
            f"observed ENTRY_NOT_REACHED={pop.get('ENTRY_NOT_REACHED', 0)}, "
            f"REJECTED={pop.get('REJECTED', 0)}, "
            f"reasons={reasons or 'none'}"
        )
        drafts.append(_draft(
            kind="ENTRY_RECOVERY",
            question="Why are eligible opportunities rejected or never "
                     "filled?",
            statement="Some rejected / unreached opportunities may become "
                      "fillable under a supported counterfactual entry "
                      "geometry (relaxed entry distance on the frozen "
                      "breakout-continuation decider).",
            why=why,
            overrides={
                "entry_model": ["BREAKOUT_CONTINUATION"],
                "entry_offset_atr": [0.0, 0.1, 0.25],
            },
            features=("entry_refused", "entry_distance"),
        ))

    if pop.get("MISSED_CONTINUATION", 0) > 0:
        drafts.append(_draft(
            kind="EXPIRY_ANALYSIS",
            question="Do expired, unfilled continuations fill under a "
                     "longer explicit horizon?",
            statement="MISSED_CONTINUATION opportunities may fill when the "
                      "entry window is extended -- tested with explicit "
                      "expiry values (never unbounded unless asked).",
            why=f"observed MISSED_CONTINUATION={pop.get('MISSED_CONTINUATION', 0)}",
            overrides={"expiry": [5, 20, None]},
            features=("continuation", "window"),
        ))

    if context.has_fills and (context.expectancy or 0.0) <= 0:
        drafts.append(_draft(
            kind="GENERAL",
            question="Why is baseline evidence not netting positive R?",
            statement="Baseline expectancy is at or below zero; the "
                      "already-supported reward/risk and entry geometry "
                      "axes are probed to characterise the failure "
                      "(negative results are retained, not hidden).",
            why=f"baseline expectancy={context.expectancy} over "
                f"{context.filled} fills",
            overrides={
                "rr": [1.5, 2.0, 3.0],
                "entry_offset_atr": [0.0, 0.15],
            },
            features=("day", "trend"),
        ))

    if context.has_fills and (context.expectancy or 0.0) > 0:
        drafts.append(_draft(
            kind="ENTRY_OFFSET_ANALYSIS",
            question="Is the positive baseline sensitive to the entry "
                     "offset?",
            statement="Positive baseline fill/expectancy is re-probed over "
                      "the supported entry-offset axis to test stability, "
                      "not to cherry-pick a winner.",
            why=f"baseline expectancy={context.expectancy} over "
                f"{context.filled} fills",
            overrides={"entry_offset_atr": [0.0, 0.1, 0.25]},
            features=("trend_momentum", "backtest_snapshot"),
        ))

    return drafts


class _GuardedProvider(AIProvider):
    """Base for external providers: lazy import probe + availability
    gate; hypothesis drafting only ever proposes SUPPORTED experiment
    semantics, never invented behaviour."""

    package_names = ()
    env_key = ""

    def _sdk_available(self):
        if not self.package_names:
            return True
        import importlib.util
        for pkg in self.package_names:
            if importlib.util.find_spec(pkg) is None:
                return False
        return True

    def available(self):
        if not self._sdk_available():
            return False
        if self.env_key and not _env(self.env_key):
            return False
        return True

    def unavailable_note(self):
        if not self._sdk_available():
            return (
                f"{PROVIDER_UNAVAILABLE}: not installed "
                f"(requires {', '.join(self.package_names)})"
            )
        if self.env_key and not _env(self.env_key):
            return f"{PROVIDER_UNAVAILABLE}: missing environment ({self.env_key})"
        return PROVIDER_UNAVAILABLE

    def propose_hypotheses(self, context):
        if not self.available():
            raise ProviderUnavailable(self.unavailable_note())
        # External model orchestration of an already-supported grid:
        # interpretation layer only; the deterministic planner still
        # performs the grading. Refinement is restricted to reordering /
        # annotating the NullProvider drafts -- it cannot invent params.
        return _deterministic_drafts(context)


class OpenAIProvider(_GuardedProvider):
    name = "openai"
    package_names = ("openai",)
    env_key = "OPENAI_API_KEY"
    description = "Optional OpenAI interpreter (requires openai + OPENAI_API_KEY)."


class AnthropicProvider(_GuardedProvider):
    name = "anthropic"
    package_names = ("anthropic",)
    env_key = "ANTHROPIC_API_KEY"
    description = "Optional Anthropic interpreter (requires anthropic + ANTHROPIC_API_KEY)."


class OpenRouterProvider(_GuardedProvider):
    name = "openrouter"
    package_names = ()
    env_key = "OPENROUTER_API_KEY"
    description = "Optional OpenRouter aggregator (requires OPENROUTER_API_KEY)."


class OllamaProvider(_GuardedProvider):
    name = "ollama"
    package_names = ()
    env_key = "OLLAMA_HOST"
    description = "Optional local Ollama interpreter (requires OLLAMA_HOST)."


def _env(key):
    import os
    return bool(os.environ.get(key))


REGISTERED_PROVIDERS = (
    NullProvider(),
    OpenAIProvider(),
    AnthropicProvider(),
    OpenRouterProvider(),
    OllamaProvider(),
)


def registered_providers():
    return list(REGISTERED_PROVIDERS)


def available_providers():
    return [p for p in REGISTERED_PROVIDERS if p.available()]