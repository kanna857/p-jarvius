"""
JARVIS ResearchAgent — AI Research Scientist Mode
──────────────────────────────────────────────────
Read papers, generate hypotheses, plan experiments, compare results.

Capabilities:
  1. arXiv Search       — search papers by topic/keyword/author
  2. Paper Summaries    — fetch abstract, extract key findings via LLM
  3. Hypothesis Gen     — given a topic, propose testable hypotheses
  4. Experiment Plans   — generate structured experiment methodology
  5. Literature Review  — compare multiple papers, find consensus/gaps
  6. Citation Graphs    — find related work and build reading lists

Data Sources:
  - arXiv API  (free, no key needed) — cs, physics, math, bio, etc.
  - Semantic Scholar API (free) — citation data, paper influence
  - CrossRef (DOI resolution)

All LLM-powered analysis goes through the Groq/Grok/Voice client.
"""

import re
import time
import json
import threading
from pathlib import Path
from datetime import datetime, timedelta
from utils.logger import JarvisLogger
from utils.cache import cached


class ResearchAgent:
    """AI-powered research assistant for reading papers and generating hypotheses."""

    ARXIV_API = "http://export.arxiv.org/api/query"
    SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1"
    PAPERS_DIR = Path.home() / ".jarvis" / "research"

    def __init__(self, config=None, voice_agent=None):
        self.config = config
        self.voice = voice_agent
        self.logger = JarvisLogger("Research")
        self.PAPERS_DIR.mkdir(parents=True, exist_ok=True)
        self.logger.success("ResearchAgent ready — scientist mode active")

    # ─────────────────────────────────────────────────────────────────────────
    # arXiv Paper Search
    # ─────────────────────────────────────────────────────────────────────────

    @cached(ttl=600)  # Cache search results for 10 minutes
    def search_papers(self, query: str, max_results: int = 5, category: str = None) -> str:
        """
        Search arXiv for papers matching a query.

        Args:
            query: Search terms (e.g., "transformer attention mechanism")
            max_results: Number of papers to return (max 10)
            category: arXiv category filter (e.g., "cs.AI", "cs.CL", "physics")
        """
        import requests
        import xml.etree.ElementTree as ET

        max_results = min(max_results, 10)
        search_q = f"all:{query}"
        if category:
            search_q = f"cat:{category} AND all:{query}"

        params = {
            "search_query": search_q,
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending"
        }

        try:
            resp = requests.get(self.ARXIV_API, params=params, timeout=15)
            if resp.status_code != 200:
                return f"arXiv API error: HTTP {resp.status_code}"

            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom",
                  "arxiv": "http://arxiv.org/schemas/atom"}

            entries = root.findall("atom:entry", ns)
            if not entries:
                return f"No papers found for '{query}'."

            papers = []
            for entry in entries:
                title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
                summary = entry.find("atom:summary", ns).text.strip()[:200]
                published = entry.find("atom:published", ns).text[:10]
                authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)]
                authors_str = ", ".join(authors[:3]) + ("..." if len(authors) > 3 else "")
                arxiv_id = entry.find("atom:id", ns).text.split("/abs/")[-1]
                categories = [c.get("term") for c in entry.findall("atom:category", ns)]

                papers.append({
                    "id": arxiv_id,
                    "title": title,
                    "authors": authors_str,
                    "date": published,
                    "summary": summary,
                    "categories": ", ".join(categories[:3]),
                    "url": f"https://arxiv.org/abs/{arxiv_id}"
                })

            lines = [f"📚 Found {len(papers)} papers for '{query}':\n"]
            for i, p in enumerate(papers, 1):
                lines.append(
                    f"{i}. 📄 {p['title']}\n"
                    f"   👤 {p['authors']} • 📅 {p['date']} • 🏷️ {p['categories']}\n"
                    f"   🔗 {p['url']}\n"
                    f"   📝 {p['summary']}...\n"
                )

            # Save to local research directory
            self._save_search_results(query, papers)
            return "\n".join(lines)

        except Exception as e:
            self.logger.warning(f"arXiv search failed: {e}")
            return f"Search failed: {e}"

    def get_paper_details(self, arxiv_id: str) -> str:
        """Fetch full details of a specific arXiv paper by its ID."""
        import requests
        import xml.etree.ElementTree as ET

        # Normalize ID
        arxiv_id = arxiv_id.strip().replace("https://arxiv.org/abs/", "")
        url = f"{self.ARXIV_API}?id_list={arxiv_id}"

        try:
            resp = requests.get(url, timeout=10)
            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            entry = root.find("atom:entry", ns)
            if entry is None:
                return f"Paper '{arxiv_id}' not found."

            title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
            summary = entry.find("atom:summary", ns).text.strip()
            published = entry.find("atom:published", ns).text[:10]
            authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)]
            pdf_link = f"https://arxiv.org/pdf/{arxiv_id}"

            return (
                f"📄 {title}\n"
                f"{'─' * 50}\n"
                f"👤 Authors: {', '.join(authors)}\n"
                f"📅 Published: {published}\n"
                f"🔗 PDF: {pdf_link}\n\n"
                f"📝 Abstract:\n{summary}\n"
            )
        except Exception as e:
            return f"Could not fetch paper: {e}"

    # ─────────────────────────────────────────────────────────────────────────
    # Semantic Scholar (Citation data, related papers)
    # ─────────────────────────────────────────────────────────────────────────

    @cached(ttl=600)
    def get_citations(self, paper_id: str) -> str:
        """Get citation count and top citing papers from Semantic Scholar."""
        import requests
        url = f"{self.SEMANTIC_SCHOLAR_API}/paper/ARXIV:{paper_id}"
        params = {"fields": "title,citationCount,citations.title,citations.year"}

        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                return f"Semantic Scholar lookup failed for '{paper_id}'."
            data = resp.json()

            cite_count = data.get("citationCount", 0)
            title = data.get("title", paper_id)
            lines = [f"📊 '{title}' — {cite_count} citations\n"]

            citations = data.get("citations", [])[:5]
            if citations:
                lines.append("Top citing papers:")
                for c in citations:
                    year = c.get("year", "")
                    lines.append(f"  • {c.get('title', 'Unknown')} ({year})")

            return "\n".join(lines)
        except Exception as e:
            return f"Citation lookup failed: {e}"

    def find_related_papers(self, paper_id: str) -> str:
        """Find related papers using Semantic Scholar recommendations."""
        import requests
        url = f"{self.SEMANTIC_SCHOLAR_API}/recommendations"
        params = {"fields": "title,year,citationCount,url"}
        body = {"positivePaperIds": [f"ARXIV:{paper_id}"]}

        try:
            resp = requests.post(url, json=body, params=params, timeout=10)
            if resp.status_code != 200:
                return f"Recommendations not available for '{paper_id}'."
            papers = resp.json().get("recommendedPapers", [])[:5]

            if not papers:
                return "No related papers found."

            lines = [f"📚 Related papers to {paper_id}:\n"]
            for p in papers:
                lines.append(
                    f"  • {p.get('title', 'Unknown')} ({p.get('year', '')}) "
                    f"— {p.get('citationCount', 0)} citations"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Related paper search failed: {e}"

    # ─────────────────────────────────────────────────────────────────────────
    # LLM-Powered Analysis
    # ─────────────────────────────────────────────────────────────────────────

    def _llm_analyze(self, prompt: str) -> str:
        """Send a prompt to the LLM for analysis."""
        if self.voice and hasattr(self.voice, 'ask_ai'):
            return self.voice.ask_ai(prompt)
        return "LLM not available for analysis."

    def summarize_paper(self, arxiv_id: str) -> str:
        """Fetch a paper and generate an AI summary of its key contributions."""
        details = self.get_paper_details(arxiv_id)
        if "not found" in details.lower():
            return details

        prompt = (
            f"You are a research scientist. Analyze this paper and provide:\n\n"
            f"1. **Key Contribution**: What's the main novel contribution?\n"
            f"2. **Method**: What approach/technique did they use?\n"
            f"3. **Results**: What were the main findings?\n"
            f"4. **Limitations**: What are the weaknesses or gaps?\n"
            f"5. **Impact**: Why does this matter for the field?\n\n"
            f"Paper:\n{details}\n\n"
            f"Provide a concise, structured summary."
        )
        summary = self._llm_analyze(prompt)
        return f"🔬 AI Summary of {arxiv_id}:\n{'─'*40}\n{summary}"

    def generate_hypotheses(self, topic: str, context: str = None) -> str:
        """Generate testable research hypotheses for a given topic."""
        ctx = f"\n\nAdditional context:\n{context}" if context else ""
        prompt = (
            f"You are a senior research scientist. Generate 3-5 novel, testable hypotheses "
            f"for the following research topic:\n\n"
            f"Topic: {topic}{ctx}\n\n"
            f"For each hypothesis, provide:\n"
            f"1. **H#**: Clear hypothesis statement\n"
            f"2. **Rationale**: Why this is worth testing\n"
            f"3. **Test**: How you would test it (brief methodology)\n"
            f"4. **Expected outcome**: What a positive result would look like\n"
            f"5. **Novelty**: Why this hasn't been done before (or how it differs)\n\n"
            f"Focus on hypotheses that are:\n"
            f"- Specific and falsifiable\n"
            f"- Feasible with current methods\n"
            f"- Novel and impactful"
        )
        result = self._llm_analyze(prompt)
        return f"🧪 Research Hypotheses: {topic}\n{'─'*40}\n{result}"

    def plan_experiment(self, hypothesis: str, constraints: str = None) -> str:
        """Generate a structured experiment plan for a hypothesis."""
        cons = f"\n\nConstraints: {constraints}" if constraints else ""
        prompt = (
            f"You are a senior research scientist. Design a detailed experiment plan "
            f"to test this hypothesis:\n\n"
            f"Hypothesis: {hypothesis}{cons}\n\n"
            f"Provide:\n"
            f"1. **Objective**: What are you trying to prove/disprove?\n"
            f"2. **Variables**: Independent, dependent, and controlled variables\n"
            f"3. **Methodology**: Step-by-step procedure\n"
            f"4. **Data Collection**: What data to collect and how\n"
            f"5. **Analysis Plan**: Statistical tests or evaluation metrics\n"
            f"6. **Expected Results**: What success looks like\n"
            f"7. **Potential Issues**: Risks and mitigation strategies\n"
            f"8. **Timeline**: Rough time estimate for each phase\n"
            f"9. **Resources Needed**: Tools, compute, datasets\n\n"
            f"Be specific and practical."
        )
        result = self._llm_analyze(prompt)
        return f"🔬 Experiment Plan\n{'─'*40}\n{result}"

    def compare_papers(self, arxiv_ids: list[str]) -> str:
        """Compare multiple papers and find consensus, contradictions, and gaps."""
        details_list = []
        for pid in arxiv_ids[:5]:
            details = self.get_paper_details(pid.strip())
            if "not found" not in details.lower():
                details_list.append(details)

        if not details_list:
            return "Could not fetch any of the specified papers."

        combined = "\n\n---\n\n".join(details_list)
        prompt = (
            f"You are a senior research scientist conducting a literature review. "
            f"Compare these {len(details_list)} papers:\n\n"
            f"{combined}\n\n"
            f"Provide:\n"
            f"1. **Common Themes**: What do these papers agree on?\n"
            f"2. **Key Differences**: Where do they disagree or use different approaches?\n"
            f"3. **Complementary Findings**: How do they build on each other?\n"
            f"4. **Research Gaps**: What questions remain unanswered?\n"
            f"5. **Synthesis**: What's the overall state of this research area?\n"
            f"6. **Future Directions**: What should be studied next?"
        )
        result = self._llm_analyze(prompt)
        return f"📊 Literature Comparison ({len(details_list)} papers)\n{'─'*40}\n{result}"

    def literature_review(self, topic: str, num_papers: int = 5) -> str:
        """
        Full automated literature review:
        1. Search for top papers on a topic
        2. Summarize each paper
        3. Compare findings and identify gaps
        """
        self.logger.info(f"Starting literature review: {topic}")

        # Step 1: Search
        search_result = self.search_papers(topic, max_results=num_papers)

        # Extract arXiv IDs from search results
        ids = re.findall(r'arxiv\.org/abs/([\d.]+(?:v\d+)?)', search_result)
        if not ids:
            return f"No papers found for '{topic}'. Try different keywords."

        lines = [f"📚 Literature Review: {topic}", "═" * 50, ""]

        # Step 2: Summarize each paper
        for i, arxiv_id in enumerate(ids[:num_papers], 1):
            self.logger.info(f"Summarizing paper {i}/{len(ids)}: {arxiv_id}")
            summary = self.summarize_paper(arxiv_id)
            lines.append(f"Paper {i}:")
            lines.append(summary)
            lines.append("")

        # Step 3: Compare and synthesize
        if len(ids) > 1:
            self.logger.info("Generating comparative analysis...")
            comparison = self.compare_papers(ids[:num_papers])
            lines.append("Overall Analysis:")
            lines.append(comparison)

        # Step 4: Generate hypotheses based on gaps
        self.logger.info("Generating research hypotheses from gaps...")
        hypotheses = self.generate_hypotheses(
            topic,
            context=f"Based on reviewing {len(ids)} recent papers on this topic."
        )
        lines.append("")
        lines.append(hypotheses)

        result = "\n".join(lines)

        # Save the full review
        review_path = self.PAPERS_DIR / f"review_{topic.replace(' ', '_')[:30]}_{int(time.time())}.md"
        review_path.write_text(result, encoding="utf-8")
        self.logger.success(f"Literature review saved: {review_path}")

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Trending & Recent Papers
    # ─────────────────────────────────────────────────────────────────────────

    @cached(ttl=1800)  # Cache 30 minutes
    def get_trending_papers(self, category: str = "cs.AI", days: int = 7) -> str:
        """Get trending/recent papers from arXiv in a category."""
        import requests
        import xml.etree.ElementTree as ET

        params = {
            "search_query": f"cat:{category}",
            "start": 0,
            "max_results": 8,
            "sortBy": "submittedDate",
            "sortOrder": "descending"
        }

        try:
            resp = requests.get(self.ARXIV_API, params=params, timeout=15)
            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            entries = root.findall("atom:entry", ns)
            if not entries:
                return f"No recent papers in {category}."

            lines = [f"🔥 Trending in {category} (last {days} days):\n"]
            for i, entry in enumerate(entries, 1):
                title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
                authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)]
                date = entry.find("atom:published", ns).text[:10]
                arxiv_id = entry.find("atom:id", ns).text.split("/abs/")[-1]
                lines.append(
                    f"{i}. {title}\n"
                    f"   {', '.join(authors[:2])} • {date}\n"
                    f"   https://arxiv.org/abs/{arxiv_id}\n"
                )

            return "\n".join(lines)
        except Exception as e:
            return f"Could not fetch trending papers: {e}"

    # ─────────────────────────────────────────────────────────────────────────
    # Storage & History
    # ─────────────────────────────────────────────────────────────────────────

    def _save_search_results(self, query: str, papers: list):
        """Save search results to local JSON for later reference."""
        try:
            path = self.PAPERS_DIR / "search_history.json"
            history = []
            if path.exists():
                history = json.loads(path.read_text(encoding="utf-8"))
            history.append({
                "query": query,
                "timestamp": datetime.now().isoformat(),
                "papers": papers
            })
            # Keep last 50 searches
            history = history[-50:]
            path.write_text(json.dumps(history, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get_reading_list(self) -> str:
        """Returns previously searched papers as a reading list."""
        path = self.PAPERS_DIR / "search_history.json"
        if not path.exists():
            return "No research history yet. Search for papers first."

        try:
            history = json.loads(path.read_text(encoding="utf-8"))
            all_papers = {}
            for entry in history:
                for p in entry.get("papers", []):
                    all_papers[p["id"]] = p

            lines = [f"📖 Your Reading List ({len(all_papers)} papers):\n"]
            for p in list(all_papers.values())[-10:]:
                lines.append(f"  📄 {p['title'][:60]}...")
                lines.append(f"     {p['authors']} • {p['date']}")
                lines.append(f"     {p['url']}\n")

            return "\n".join(lines)
        except Exception as e:
            return f"Error loading reading list: {e}"

    # ─────────────────────────────────────────────────────────────────────────
    # Natural Language Command Handler
    # ─────────────────────────────────────────────────────────────────────────

    def handle_command(self, command: str) -> str:
        """Route natural language research commands."""
        cmd = command.lower()

        if any(k in cmd for k in ("search papers", "find papers", "arxiv search")):
            # Extract query
            for prefix in ("search papers on", "search papers about", "find papers on",
                           "find papers about", "arxiv search"):
                if prefix in cmd:
                    query = cmd.split(prefix)[-1].strip()
                    return self.search_papers(query)
            return self.search_papers(command)

        if "trending" in cmd or "latest papers" in cmd:
            cat = "cs.AI"
            if "nlp" in cmd or "language" in cmd:
                cat = "cs.CL"
            elif "vision" in cmd or "cv" in cmd:
                cat = "cs.CV"
            elif "robot" in cmd:
                cat = "cs.RO"
            elif "physics" in cmd:
                cat = "physics"
            elif "math" in cmd:
                cat = "math"
            return self.get_trending_papers(cat)

        if "summarize" in cmd or "summary" in cmd:
            # Extract arXiv ID
            match = re.search(r'(\d{4}\.\d{4,5}(?:v\d+)?)', command)
            if match:
                return self.summarize_paper(match.group(1))
            return "Please provide an arXiv paper ID (e.g., 2301.12345)."

        if "hypothesis" in cmd or "hypotheses" in cmd:
            for prefix in ("generate hypotheses for", "hypothesis for",
                           "hypotheses about", "hypotheses for"):
                if prefix in cmd:
                    topic = cmd.split(prefix)[-1].strip()
                    return self.generate_hypotheses(topic)
            return self.generate_hypotheses(command)

        if "experiment plan" in cmd or "design experiment" in cmd:
            for prefix in ("experiment plan for", "design experiment for",
                           "plan experiment for"):
                if prefix in cmd:
                    hyp = cmd.split(prefix)[-1].strip()
                    return self.plan_experiment(hyp)
            return "Please specify a hypothesis to plan an experiment for."

        if "literature review" in cmd or "review papers" in cmd:
            for prefix in ("literature review on", "literature review about",
                           "review papers on", "review papers about"):
                if prefix in cmd:
                    topic = cmd.split(prefix)[-1].strip()
                    return self.literature_review(topic)
            return self.literature_review(command)

        if "reading list" in cmd:
            return self.get_reading_list()

        if "compare" in cmd:
            ids = re.findall(r'(\d{4}\.\d{4,5}(?:v\d+)?)', command)
            if len(ids) >= 2:
                return self.compare_papers(ids)
            return "Please provide at least 2 arXiv paper IDs to compare."

        if "citations" in cmd:
            match = re.search(r'(\d{4}\.\d{4,5}(?:v\d+)?)', command)
            if match:
                return self.get_citations(match.group(1))
            return "Please provide an arXiv paper ID."

        return None  # Not a research command
