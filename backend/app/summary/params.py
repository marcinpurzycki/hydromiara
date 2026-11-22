"""Settings of the Report summary: provider configuration names, limits, word lists.

All limits are engineering values without a scientific source; none of them
decides a verdict, a cause or a recommendation.
"""

# --- Provider configuration (environment variables) --------------------------

API_KEY_ENV = "AI_API_KEY"
MODEL_ENV = "OPENAI_MODEL"
BASE_URL_ENV = "AI_BASE_URL"
TIMEOUT_ENV = "AI_TIMEOUT_S"
REASONING_EFFORT_ENV = "AI_REASONING_EFFORT"

# Interface compatible with the OpenAI Chat Completions API. The model name has
# no default on purpose: without a key or a model the template is used.
DEFAULT_BASE_URL = "https://api.openai.com/v1"
COMPLETIONS_PATH = "/chat/completions"
USER_AGENT = "hydro-analysis/0.1"
# Values of the optional `reasoning_effort` request field. It is sent only when
# the operator sets it: not every model accepts it or each of its values.
REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
# Hosts that may be reached without TLS (a model served on the same machine).
PLAIN_HTTP_HOSTS = ("localhost", "127.0.0.1", "::1")

# --- Time ---------------------------------------------------------------------

# PROVISIONAL: longest wait for the provider. Two live calls took 7.5 s and more
# than 8 s; the time left in the analysis budget shortens this limit when needed.
DEFAULT_TIMEOUT_S = 12.0
# With less time left in the analysis budget the provider is not called at all.
MIN_CALL_TIME_S = 1.0

# --- Length ---------------------------------------------------------------------

# Upper bound of generated tokens; it also covers the reasoning tokens of models
# that reason before answering, so it is far above the length of the answer.
# PROVISIONAL: engineering value.
MAX_COMPLETION_TOKENS = 2000
# PROVISIONAL: accepted length of the answer in characters (a few sentences).
MIN_ANSWER_CHARS = 60
MAX_ANSWER_CHARS = 900
# Limitations of the Report passed to the model, the most important first.
MAX_LIMITATIONS = 3

# --- Wording checks -------------------------------------------------------------

# Characters of markup or structured output; the answer is plain prose.
FORMAT_CHARS = "*#`{}[]<>|_"

# Stems of words the project glossary tells to avoid. One of them is accepted
# only when the Report text given to the model contains it as well.
AVOIDED_STEMS = (
    r"parcel", r"gospodarstw", r"ug[oó]r", r"wegetacyjn", r"wilgotno", r"płodozmian",
    r"zmianowan", r"ryzyk", r"porad", r"zalec", r"wskazówk", r"diagnoz", r"walidac",
    r"fallback", r"awaryjn", r"ostrzeże", r"prawdopodob", r"dokładnoś", r"teryt",
    r"punktow",
)
# "susza" names an official state the Report does not establish. The stem may
# appear only inside these fixed phrases taken from the Report.
DROUGHT_STEM = r"susz"
DROUGHT_PHRASES = (
    r"stwierdzeni\w+ suszy(?: rolniczej)?",
    r"wskaźnik\w* suszy",
    r"obserwatori\w+ suszy",
)

# Phrases that state a result or an action. Each may appear in the answer only
# when the Report text given to the model contains it: degrees of the deficit
# scale, recommendation groups, results of the consistency check, advice words.
GUARDED_TERMS = (
    r"\bw normie\b", r"\blekk\w+ niedob\w+", r"\bwyraźn\w+ niedob\w+", r"\bsiln\w+ niedob\w+",
    r"\bretencj\w+ krajobrazow\w+", r"\bretencj\w+ glebow\w+", r"\bagrotechni\w+",
    r"\bzgodne\b", r"\brozbieżn\w+",
    r"\bwarto\b", r"\bnależy\b", r"\bpowin\w+", r"\brozważ\w*", r"\bzastos\w+",
    r"\bmusisz\b", r"\btrzeba\b", r"\bkoniecznie\b",
)

# A confidence level next to the word "pewność"; the level must be one the
# Report gives to a verdict.
CONFIDENCE_PATTERNS = (
    r"\b(wysok|średni|nisk)\w*\s+pewno",
    r"pewno\w*(?:\s+\w+){0,3}?[\s:—–-]+(wysok|średni|nisk)",
)

# What an answer about verdicts without a deficit level has to say.
NOT_ASSESSED_PATTERN = r"nie\s+(?:\w+\s+)?(?:ocenion|wyznacz)\w*"

MONTH_PATTERNS = (
    r"\bstycz\w+", r"\blut(?:y|ego|ym)\b", r"\bmar(?:zec|ca|cu|cem|cow\w+)\b", r"\bkwie\w+",
    r"\bmaj(?:a|u|em|ow\w+)?\b", r"\bczerw(?:iec|ca|cu|cem|cow\w+)\b",
    r"\blip(?:iec|ca|cu|cem|cow\w+)\b", r"\bsierp\w+", r"\bwrze\w+", r"\bpaździer\w+",
    r"\blistopad\w*", r"\bgrud\w+",
)

# Unit words read after a number, grouped into classes.
UNIT_PATTERNS = (
    ("percent", r"(?:%|procent\w*)"),
    ("m3", r"(?:m³|m3)"),
    ("mm", r"mm\b"),
    ("days", r"(?:dni|dnia|dzień|dniu)\b"),
    ("years", r"(?:lat|lata|latach|roku|rok)\b"),
)
