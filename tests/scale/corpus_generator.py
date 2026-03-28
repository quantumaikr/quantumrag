"""Scale test corpus generator — uses REAL QA dataset sources as base.

Collects all sources from datasets/ds-001 ~ ds-NNN, then generates
confuser variants (date/entity/number perturbations) to amplify volume.
QA questions from all datasets become the test queries with known answers.

The result: real documents as "needles" in a sea of realistic confusers
that share the same domain, terms, and structure.

Usage:
    python tests/scale/corpus_generator.py --multiplier 10 --output /tmp/scale_corpus
    python tests/scale/corpus_generator.py --multiplier 50  # ~1,150 docs → ~7K chunks
"""

from __future__ import annotations

import re
import random
import shutil
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DATASETS_DIR = _PROJECT_ROOT / "datasets"


# ---------------------------------------------------------------------------
# Confuser generation — perturb real documents to create realistic noise
# ---------------------------------------------------------------------------


# Number perturbation: replace digits with nearby values
def _perturb_numbers(text: str, rng: random.Random) -> str:
    """Replace numbers with plausible but different values."""

    def _shift(match: re.Match) -> str:
        original = match.group(0)
        try:
            val = float(original.replace(",", ""))
            # Shift by ±10~40%
            factor = rng.uniform(0.6, 1.4)
            new_val = val * factor
            if "," in original:
                return f"{new_val:,.0f}"
            if "." in original:
                decimals = len(original.split(".")[-1])
                return f"{new_val:.{decimals}f}"
            return str(int(new_val))
        except (ValueError, OverflowError):
            return original

    return re.sub(r"\d[\d,]*\.?\d*", _shift, text)


# Year perturbation
def _perturb_years(text: str, rng: random.Random) -> str:
    """Shift years by ±1~3."""
    shift = rng.choice([-3, -2, -1, 1, 2, 3])

    def _shift_year(match: re.Match) -> str:
        year = int(match.group(0))
        if 2020 <= year <= 2030:
            return str(year + shift)
        return match.group(0)

    return re.sub(r"20[2-3]\d", _shift_year, text)


# Entity perturbation — swap known entities with alternates
_KO_ENTITY_SWAPS = {
    "삼성전자": ["LG전자", "현대모비스", "SK텔레콤", "KT"],
    "SK하이닉스": ["삼성전자", "마이크론", "키옥시아", "웨스턴디지털"],
    "현대자동차": ["기아", "BMW", "테슬라", "토요타"],
    "카카오": ["네이버", "라인", "쿠팡", "배달의민족"],
    "OpenAI": ["Anthropic", "Google DeepMind", "Meta AI", "Mistral"],
    "Google": ["Microsoft", "Apple", "Meta", "Amazon"],
    "Anthropic": ["OpenAI", "Cohere", "AI21 Labs", "Stability AI"],
}

_EN_ENTITY_SWAPS = {
    "GPT-5.2": ["Gemini 3.1", "Claude 4.7", "Llama 5", "Mixtral 9"],
    "Gemini": ["GPT", "Claude", "Llama", "Qwen"],
    "Claude": ["GPT", "Gemini", "Grok", "Command"],
    "Samsung": ["Intel", "TSMC", "Qualcomm", "Broadcom"],
    "NVIDIA": ["AMD", "Intel", "Qualcomm", "Broadcom"],
}


def _perturb_entities(text: str, rng: random.Random) -> str:
    """Swap known entities with plausible alternatives."""
    all_swaps = {**_KO_ENTITY_SWAPS, **_EN_ENTITY_SWAPS}
    for original, alternatives in all_swaps.items():
        if original in text:
            replacement = rng.choice(alternatives)
            text = text.replace(original, replacement)
    return text


# Quarter/period perturbation
_QUARTER_SWAPS = {
    "1분기": "3분기",
    "2분기": "4분기",
    "3분기": "1분기",
    "4분기": "2분기",
    "Q1": "Q3",
    "Q2": "Q4",
    "Q3": "Q1",
    "Q4": "Q2",
    "상반기": "하반기",
    "하반기": "상반기",
}


def _perturb_quarters(text: str, rng: random.Random) -> str:
    """Swap quarter references."""
    if rng.random() < 0.5:
        for orig, swap in _QUARTER_SWAPS.items():
            text = text.replace(orig, swap)
    return text


def _generate_confuser(original_content: str, variant_idx: int, seed: int) -> str:
    """Generate a single confuser variant from an original document."""
    rng = random.Random(seed + variant_idx * 7919)  # prime offset for diversity

    content = original_content

    # Apply perturbations in random order
    perturbations = [
        _perturb_numbers,
        _perturb_years,
        _perturb_entities,
        _perturb_quarters,
    ]
    rng.shuffle(perturbations)

    # Apply 2-3 perturbations per variant (not all — keep some similarity)
    n_perturbs = rng.randint(2, min(3, len(perturbations)))
    for fn in perturbations[:n_perturbs]:
        content = fn(content, rng)

    # Add a variant marker in metadata (won't affect search but aids debugging)
    header = f"<!-- variant:{variant_idx} seed:{seed} -->\n"
    return header + content


# ---------------------------------------------------------------------------
# Corpus assembly
# ---------------------------------------------------------------------------


def _discover_datasets() -> list[Path]:
    """Find all ds-NNN directories."""
    if not _DATASETS_DIR.exists():
        return []
    return sorted(d for d in _DATASETS_DIR.iterdir() if d.is_dir() and d.name.startswith("ds-"))


def _load_sources(ds_dir: Path) -> list[dict]:
    """Load source files and QA questions from a dataset."""
    sources_dir = ds_dir / "sources"
    qa_file = ds_dir / "qa.yaml"
    manifest_file = ds_dir / "manifest.yaml"

    if not sources_dir.exists():
        return []

    sources = []
    for f in sorted(sources_dir.glob("*.md")):
        content = f.read_text(encoding="utf-8")
        sources.append(
            {
                "dataset": ds_dir.name,
                "filename": f.name,
                "content": content,
                "path": f,
            }
        )
    return sources


def _load_all_qa_queries() -> list[dict]:
    """Load QA questions from all datasets as test queries."""
    queries = []
    for ds_dir in _discover_datasets():
        qa_file = ds_dir / "qa.yaml"
        if not qa_file.exists():
            continue
        with open(qa_file) as f:
            data = yaml.safe_load(f)
        for q in data.get("questions", []):
            queries.append(
                {
                    "dataset": ds_dir.name,
                    "qid": q["id"],
                    "query": q["query"],
                    "expected_keywords": q.get("expected_keywords", []),
                    "match_mode": q.get("match_mode", "any"),
                    "difficulty": q.get("difficulty", "medium"),
                    "type": q.get("type", "factual"),
                    "expect_insufficient": q.get("expect_insufficient", False),
                }
            )
    return queries


def generate_corpus(
    multiplier: int = 10,
    output_dir: str | Path = "/tmp/scale_corpus",
    seed: int = 42,
) -> dict:
    """Generate a scale test corpus from all QA dataset sources.

    Args:
        multiplier: How many confuser variants per original source.
                    10 = ~230 docs, 50 = ~1,150 docs, 200 = ~4,600 docs
        output_dir: Where to write the corpus.
        seed: Random seed for reproducibility.

    Returns:
        Metadata dict with corpus statistics.
    """
    output = Path(output_dir)
    sources_dir = output / "sources"
    if output.exists():
        shutil.rmtree(output)
    sources_dir.mkdir(parents=True, exist_ok=True)

    # 1) Collect all real sources
    datasets = _discover_datasets()
    all_sources: list[dict] = []
    for ds_dir in datasets:
        all_sources.extend(_load_sources(ds_dir))

    if not all_sources:
        raise RuntimeError(f"No sources found in {_DATASETS_DIR}")

    # 2) Copy originals (these are the "needles")
    original_count = 0
    for src in all_sources:
        dst_name = f"orig_{src['dataset']}_{src['filename']}"
        (sources_dir / dst_name).write_text(src["content"], encoding="utf-8")
        original_count += 1

    # 3) Generate confuser variants
    confuser_count = 0
    rng = random.Random(seed)
    for src in all_sources:
        n_variants = multiplier
        for vi in range(n_variants):
            variant_content = _generate_confuser(
                src["content"], vi, seed=seed + hash(src["filename"])
            )
            dst_name = f"var_{src['dataset']}_{src['filename'].replace('.md', '')}_{vi:03d}.md"
            (sources_dir / dst_name).write_text(variant_content, encoding="utf-8")
            confuser_count += 1

    # 4) Collect all QA queries
    queries = _load_all_qa_queries()
    with open(output / "queries.yaml", "w") as f:
        yaml.dump({"queries": queries}, f, allow_unicode=True, default_flow_style=False)

    # 5) Write corpus manifest
    total_docs = original_count + confuser_count
    manifest = {
        "seed": seed,
        "multiplier": multiplier,
        "datasets_used": [d.name for d in datasets],
        "original_sources": original_count,
        "confuser_variants": confuser_count,
        "total_docs": total_docs,
        "total_queries": len(queries),
        "queries_by_difficulty": {},
        "queries_by_dataset": {},
    }

    for q in queries:
        diff = q["difficulty"]
        manifest["queries_by_difficulty"][diff] = manifest["queries_by_difficulty"].get(diff, 0) + 1
        ds = q["dataset"]
        manifest["queries_by_dataset"][ds] = manifest["queries_by_dataset"].get(ds, 0) + 1

    with open(output / "corpus_manifest.yaml", "w") as f:
        yaml.dump(manifest, f, allow_unicode=True, default_flow_style=False)

    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Generate scale test corpus from QA datasets")
    parser.add_argument(
        "--multiplier",
        type=int,
        default=10,
        help="Confuser variants per source (10=~230 docs, 50=~1150, 200=~4600)",
    )
    parser.add_argument("--output", type=str, default="/tmp/scale_corpus")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    result = generate_corpus(
        multiplier=args.multiplier,
        output_dir=args.output,
        seed=args.seed,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nCorpus generated at: {args.output}")
    print(f"  Datasets used:     {result['datasets_used']}")
    print(f"  Original sources:  {result['original_sources']}")
    print(f"  Confuser variants: {result['confuser_variants']}")
    print(f"  Total docs:        {result['total_docs']}")
    print(f"  Test queries:      {result['total_queries']}")
    print(f"  By difficulty:     {result['queries_by_difficulty']}")
