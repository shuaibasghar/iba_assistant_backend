# ============================================================
# Multi-Agent RAG Study Assistant
# ANLP Project - Sukkur IBA University
# Proposal: Multi-Agent RAG System for Intelligent Study Assistance
#
# ARCHITECTURE:
#   Retriever Agent  →  Generator Agent  →  Moderator Agent
#
# USAGE:
#   1. pip install -r requirements.txt
#   2. Create .env file with: OPENAI_API_KEY=your_key_here
#   3. python main.py
# ============================================================

import os
import json
import time
import warnings
from pathlib import Path

import nltk
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

warnings.filterwarnings("ignore")
load_dotenv()

# ── Check API Key ──────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found! Create a .env file with your key.")

# ── LangChain ──────────────────────────────────────────────
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain.schema import Document

# ── CrewAI ─────────────────────────────────────────────────
from crewai import Agent, Task, Crew, Process
from crewai_tools import BaseTool

# ── Evaluation ────────────────────────────────────────────
from rouge_score import rouge_scorer
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
from sklearn.metrics import f1_score

nltk.download("punkt", quiet=True)
nltk.download("punkt_tab", quiet=True)

# ── Dataset ───────────────────────────────────────────────
from datasets import load_dataset

# =============================================================
# SECTION 1: CONFIGURATION
# =============================================================

CONFIG = {
    "openai_model"    : "gpt-4o-mini",       # cheap & fast for experiments
    "embedding_model" : "text-embedding-3-small",
    "top_k"           : 3,                   # number of chunks to retrieve
    "chunk_size"      : 500,
    "chunk_overlap"   : 50,
    "squad_samples"   : 50,                  # how many SQuAD samples to evaluate
    "chroma_dir"      : "./chroma_db",
    "temperature"     : 0.0,
}

print("=" * 60)
print("  Multi-Agent RAG Study Assistant")
print("  ANLP Project | Sukkur IBA University")
print("=" * 60)

# =============================================================
# SECTION 2: VECTOR DATABASE SETUP (LangChain)
# =============================================================

def build_vector_store(documents: list[Document], persist_dir: str) -> Chroma:
    """
    Chunk documents, embed them with OpenAI, store in ChromaDB.
    LangChain handles all of this with a few lines.
    """
    print("\n[1/5] Building vector store ...")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size    = CONFIG["chunk_size"],
        chunk_overlap = CONFIG["chunk_overlap"],
    )
    chunks = splitter.split_documents(documents)
    print(f"      {len(documents)} docs → {len(chunks)} chunks")

    embeddings = OpenAIEmbeddings(
        model   = CONFIG["embedding_model"],
        api_key = OPENAI_API_KEY,
    )

    vectorstore = Chroma.from_documents(
        documents         = chunks,
        embedding         = embeddings,
        persist_directory = persist_dir,
    )
    print(f"      Vector store saved to: {persist_dir}")
    return vectorstore


def load_vector_store(persist_dir: str) -> Chroma:
    embeddings = OpenAIEmbeddings(
        model   = CONFIG["embedding_model"],
        api_key = OPENAI_API_KEY,
    )
    return Chroma(
        persist_directory = persist_dir,
        embedding_function = embeddings,
    )

# =============================================================
# SECTION 3: CrewAI CUSTOM TOOL — wraps the ChromaDB retriever
# =============================================================

class RAGRetrieverTool(BaseTool):
    """
    CrewAI tool that retrieves top-k relevant chunks from ChromaDB
    given a user query.
    """
    name        : str = "RAG Retriever Tool"
    description : str = (
        "Retrieves the most relevant document chunks from the study material "
        "vector database based on a user's question."
    )
    vectorstore : object   # Chroma instance injected at runtime
    top_k       : int = 3

    class Config:
        arbitrary_types_allowed = True

    def _run(self, query: str) -> str:
        results = self.vectorstore.similarity_search(query, k=self.top_k)
        if not results:
            return "No relevant context found."
        context_parts = []
        for i, doc in enumerate(results, 1):
            context_parts.append(f"[Chunk {i}]\n{doc.page_content.strip()}")
        return "\n\n".join(context_parts)

# =============================================================
# SECTION 4: CrewAI AGENTS
# =============================================================

def create_agents(retriever_tool: RAGRetrieverTool) -> dict:
    """
    Create the 3 agents from the project proposal:
      1. Retriever Agent
      2. Generator Agent
      3. Moderator Agent
    """
    llm = ChatOpenAI(
        model       = CONFIG["openai_model"],
        temperature = CONFIG["temperature"],
        api_key     = OPENAI_API_KEY,
    )

    retriever_agent = Agent(
        role  = "Document Retrieval Specialist",
        goal  = "Find and return the most relevant context chunks for the given question.",
        backstory = (
            "You are an expert at semantic search. Given a question, you use the "
            "RAG Retriever Tool to fetch the most relevant passages from the knowledge base."
        ),
        tools    = [retriever_tool],
        llm      = llm,
        verbose  = False,
        allow_delegation = False,
    )

    generator_agent = Agent(
        role  = "Answer Generator",
        goal  = "Generate an initial answer to the question based on provided context.",
        backstory = (
            "You are a knowledgeable study assistant. Using the retrieved context, "
            "you write a clear and factual initial answer to the student's question. "
            "You do NOT self-evaluate or refine — just generate the answer."
        ),
        llm      = llm,
        verbose  = False,
        allow_delegation = False,
    )

    moderator_agent = Agent(
        role  = "Answer Moderator",
        goal  = "Review and refine the generated answer for accuracy, clarity, and completeness.",
        backstory = (
            "You are a quality-assurance expert for educational content. "
            "You review answers and: (1) remove unsupported claims, "
            "(2) improve structure and clarity, (3) ensure the answer is complete. "
            "Output only the refined final answer."
        ),
        llm      = llm,
        verbose  = False,
        allow_delegation = False,
    )

    return {
        "retriever" : retriever_agent,
        "generator" : generator_agent,
        "moderator" : moderator_agent,
    }

# =============================================================
# SECTION 5: CrewAI TASKS & CREW EXECUTION
# =============================================================

def run_baseline(agents: dict, question: str, context: str) -> str:
    """
    Baseline: Retriever → Generator (no Moderator)
    """
    retrieve_task = Task(
        description = f"Find relevant context for this question: {question}",
        expected_output = "Relevant document chunks as plain text.",
        agent = agents["retriever"],
    )

    generate_task = Task(
        description = (
            f"Using the retrieved context below, answer this question:\n\n"
            f"Question: {question}\n\n"
            f"Context:\n{context}"
        ),
        expected_output = "A clear, factual answer to the question.",
        agent = agents["generator"],
    )

    crew = Crew(
        agents  = [agents["retriever"], agents["generator"]],
        tasks   = [retrieve_task, generate_task],
        process = Process.sequential,
        verbose = False,
    )
    result = crew.kickoff()
    return str(result).strip()


def run_proposed(agents: dict, question: str, context: str) -> str:
    """
    Proposed: Retriever → Generator → Moderator
    """
    retrieve_task = Task(
        description = f"Find relevant context for this question: {question}",
        expected_output = "Relevant document chunks as plain text.",
        agent = agents["retriever"],
    )

    generate_task = Task(
        description = (
            f"Using the retrieved context below, write an initial answer:\n\n"
            f"Question: {question}\n\n"
            f"Context:\n{context}"
        ),
        expected_output = "An initial answer to the question.",
        agent = agents["generator"],
    )

    moderate_task = Task(
        description = (
            "Review the initial answer provided by the Generator Agent. "
            "Fix any inaccuracies, improve structure and clarity, remove unsupported claims. "
            f"Original question was: {question}\n"
            f"Retrieved context was:\n{context}"
        ),
        expected_output = "A refined, high-quality final answer.",
        agent = agents["moderator"],
    )

    crew = Crew(
        agents  = [agents["retriever"], agents["generator"], agents["moderator"]],
        tasks   = [retrieve_task, generate_task, moderate_task],
        process = Process.sequential,
        verbose = False,
    )
    result = crew.kickoff()
    return str(result).strip()

# =============================================================
# SECTION 6: EVALUATION METRICS
# =============================================================

def compute_token_f1(prediction: str, ground_truth: str) -> float:
    """Token-level F1 — same as SQuAD official metric."""
    pred_tokens = prediction.lower().split()
    gt_tokens   = ground_truth.lower().split()

    if not pred_tokens or not gt_tokens:
        return 0.0

    common = set(pred_tokens) & set(gt_tokens)
    if not common:
        return 0.0

    precision = len(common) / len(pred_tokens)
    recall    = len(common) / len(gt_tokens)
    f1 = 2 * precision * recall / (precision + recall)
    return round(f1, 4)


def compute_bleu(prediction: str, ground_truth: str) -> float:
    """Sentence BLEU with smoothing."""
    smooth = SmoothingFunction().method1
    ref    = [ground_truth.lower().split()]
    hyp    = prediction.lower().split()
    return round(sentence_bleu(ref, hyp, smoothing_function=smooth), 4)


def compute_rouge(prediction: str, ground_truth: str) -> dict:
    """ROUGE-1, ROUGE-2, ROUGE-L F1."""
    scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)
    scores = scorer.score(ground_truth, prediction)
    return {
        "rouge1": round(scores["rouge1"].fmeasure, 4),
        "rouge2": round(scores["rouge2"].fmeasure, 4),
        "rougeL": round(scores["rougeL"].fmeasure, 4),
    }


def evaluate_answer(prediction: str, ground_truth: str) -> dict:
    rouge = compute_rouge(prediction, ground_truth)
    return {
        "f1"    : compute_token_f1(prediction, ground_truth),
        "bleu"  : compute_bleu(prediction, ground_truth),
        "rouge1": rouge["rouge1"],
        "rouge2": rouge["rouge2"],
        "rougeL": rouge["rougeL"],
    }

# =============================================================
# SECTION 7: DATASET — SQuAD
# =============================================================

def load_squad_samples(n: int = 50) -> list[dict]:
    """Load n samples from SQuAD validation set."""
    print(f"\n[2/5] Loading {n} SQuAD samples ...")
    dataset = load_dataset("rajpurkar/squad", split="validation")
    samples = []
    seen_contexts = set()

    for item in dataset:
        ctx = item["context"]
        if ctx in seen_contexts:
            continue
        seen_contexts.add(ctx)
        samples.append({
            "context" : ctx,
            "question": item["question"],
            "answer"  : item["answers"]["text"][0],
        })
        if len(samples) >= n:
            break

    print(f"      Loaded {len(samples)} unique context samples")
    return samples


def prepare_documents(samples: list[dict]) -> list[Document]:
    """Convert SQuAD contexts into LangChain Document objects."""
    docs = []
    for i, s in enumerate(samples):
        docs.append(Document(
            page_content = s["context"],
            metadata     = {"source": f"squad_{i}"},
        ))
    return docs

# =============================================================
# SECTION 8: MAIN PIPELINE
# =============================================================

def main():

    # ── Load Dataset ──────────────────────────────────────
    samples = load_squad_samples(n=CONFIG["squad_samples"])
    documents = prepare_documents(samples)

    # ── Build / Load Vector Store ─────────────────────────
    chroma_path = CONFIG["chroma_dir"]
    if Path(chroma_path).exists():
        print(f"\n[1/5] Loading existing vector store from {chroma_path} ...")
        vectorstore = load_vector_store(chroma_path)
    else:
        vectorstore = build_vector_store(documents, chroma_path)

    # ── Create CrewAI Tool & Agents ───────────────────────
    print("\n[3/5] Initializing CrewAI agents ...")
    retriever_tool = RAGRetrieverTool(
        vectorstore = vectorstore,
        top_k       = CONFIG["top_k"],
    )
    agents = create_agents(retriever_tool)
    print("      Retriever Agent ✓")
    print("      Generator Agent ✓")
    print("      Moderator Agent ✓")

    # ── Run Evaluation ────────────────────────────────────
    print(f"\n[4/5] Running evaluation on {len(samples)} samples ...")
    print("      (Baseline: Retriever → Generator)")
    print("      (Proposed: Retriever → Generator → Moderator)\n")

    results = []

    for i, sample in enumerate(tqdm(samples, desc="Evaluating")):
        question     = sample["question"]
        ground_truth = sample["answer"]

        # Retrieve context once (shared by both systems — fair comparison)
        retrieved_docs = vectorstore.similarity_search(question, k=CONFIG["top_k"])
        context = "\n\n".join([d.page_content for d in retrieved_docs])

        try:
            baseline_answer = run_baseline(agents, question, context)
            time.sleep(0.5)  # avoid rate-limit
        except Exception as e:
            baseline_answer = ""
            print(f"      [WARN] Baseline failed for sample {i}: {e}")

        try:
            proposed_answer = run_proposed(agents, question, context)
            time.sleep(0.5)
        except Exception as e:
            proposed_answer = ""
            print(f"      [WARN] Proposed failed for sample {i}: {e}")

        baseline_metrics = evaluate_answer(baseline_answer, ground_truth)
        proposed_metrics = evaluate_answer(proposed_answer, ground_truth)

        results.append({
            "question"        : question,
            "ground_truth"    : ground_truth,
            "baseline_answer" : baseline_answer,
            "proposed_answer" : proposed_answer,
            **{f"baseline_{k}": v for k, v in baseline_metrics.items()},
            **{f"proposed_{k}": v for k, v in proposed_metrics.items()},
        })

    # ── Aggregate Results ─────────────────────────────────
    print("\n[5/5] Computing aggregate metrics ...")
    df = pd.DataFrame(results)
    df.to_csv("evaluation_results.csv", index=False)
    print("      Results saved to: evaluation_results.csv")

    metrics = ["f1", "bleu", "rouge1", "rouge2", "rougeL"]

    print("\n" + "=" * 60)
    print("  EVALUATION RESULTS")
    print("=" * 60)
    print(f"{'Metric':<12} {'Baseline':>12} {'Proposed':>12} {'Delta':>10}")
    print("-" * 50)

    for m in metrics:
        b = df[f"baseline_{m}"].mean()
        p = df[f"proposed_{m}"].mean()
        delta = p - b
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        print(f"{m.upper():<12} {b:>12.4f} {p:>12.4f} {arrow} {delta:+.4f}")

    print("=" * 60)

    # ── Summary Table ─────────────────────────────────────
    summary = {
        "Metric"   : [m.upper() for m in metrics],
        "Baseline" : [round(df[f"baseline_{m}"].mean(), 4) for m in metrics],
        "Proposed" : [round(df[f"proposed_{m}"].mean(), 4) for m in metrics],
        "Delta"    : [round(df[f"proposed_{m}"].mean() - df[f"baseline_{m}"].mean(), 4) for m in metrics],
    }
    summary_df = pd.DataFrame(summary)
    summary_df.to_csv("summary_results.csv", index=False)
    print("\n  Summary saved to: summary_results.csv")

    # ── Print a Sample Q&A ────────────────────────────────
    print("\n" + "=" * 60)
    print("  SAMPLE OUTPUT (First Question)")
    print("=" * 60)
    r = results[0]
    print(f"\nQuestion    : {r['question']}")
    print(f"Ground Truth: {r['ground_truth']}")
    print(f"\nBaseline Answer:\n  {r['baseline_answer'][:300]}...")
    print(f"\nProposed Answer (with Moderator):\n  {r['proposed_answer'][:300]}...")

    return df


# =============================================================
# SECTION 9: INTERACTIVE CHAT MODE (Bonus)
# =============================================================

def interactive_chat(vectorstore):
    """
    Simple interactive Q&A loop using all 3 agents.
    Students can upload their own material and ask questions.
    """
    embeddings = OpenAIEmbeddings(
        model   = CONFIG["embedding_model"],
        api_key = OPENAI_API_KEY,
    )

    retriever_tool = RAGRetrieverTool(vectorstore=vectorstore, top_k=CONFIG["top_k"])
    agents = create_agents(retriever_tool)

    print("\n" + "=" * 60)
    print("  STUDY ASSISTANT — Interactive Mode")
    print("  Type 'quit' to exit")
    print("=" * 60)

    while True:
        question = input("\nYour Question: ").strip()
        if question.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break
        if not question:
            continue

        retrieved = vectorstore.similarity_search(question, k=CONFIG["top_k"])
        context   = "\n\n".join([d.page_content for d in retrieved])

        print("\n[Generating answer with all 3 agents ...]\n")
        answer = run_proposed(agents, question, context)
        print(f"Answer:\n{answer}")


# =============================================================
# ENTRY POINT
# =============================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "chat":
        # Interactive mode: python main.py chat
        chroma_path = CONFIG["chroma_dir"]
        if not Path(chroma_path).exists():
            print("Vector store not found. Run evaluation first: python main.py")
            sys.exit(1)
        vs = load_vector_store(chroma_path)
        interactive_chat(vs)
    else:
        # Full evaluation pipeline
        main()