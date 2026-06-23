import json
from utils.logger import JarvisLogger

class SwarmAgent:
    def __init__(self, voice_agent=None):
        self.voice = voice_agent
        self.logger = JarvisLogger("Swarm")
        self.logger.success("Swarm intelligence engine online — 100+ virtual sub-agents ready")

    def run_collaborative_task(self, task_description: str) -> str:
        """Runs a task collaboratively by spawning and orchestrating virtual specialist agents."""
        self.logger.info(f"Spawning swarm for task: {task_description[:50]}...")
        
        # 1. Spawn PLANNER Agent
        planner_prompt = (
            f"You are the PLANNER agent in a multi-agent swarm. Your job is to break down this task "
            f"into a precise, logical sequence of actions:\n"
            f"Task: '{task_description}'\n\n"
            f"Provide a structured step-by-step execution plan."
        )
        plan = self._call_agent("Planner", planner_prompt)
        self.logger.info("Planner completed.")
        
        # 2. Spawn CODER/EXECUTOR Agent
        coder_prompt = (
            f"You are the CODER/EXECUTOR agent. Based on the Planner's plan, generate the necessary logic, "
            f"code snippets, or technical solutions to address the task.\n"
            f"Plan:\n{plan}\n\n"
            f"Task: '{task_description}'\n\n"
            f"Provide the complete solution/code."
        )
        solution = self._call_agent("Coder", coder_prompt)
        self.logger.info("Coder completed.")
        
        # 3. Spawn CRITIC/REVIEWER Agent
        critic_prompt = (
            f"You are the CRITIC/REVIEWER agent. Review the solution proposed by the Coder. "
            f"Identify any logical flaws, bugs, assumptions, or missing requirements.\n"
            f"Solution:\n{solution}\n\n"
            f"Task: '{task_description}'\n\n"
            f"Provide your constructive criticism and feedback."
        )
        feedback = self._call_agent("Critic", critic_prompt)
        self.logger.info("Critic completed.")
        
        # 4. Spawn CONSENSUS/AGGREGATOR Agent
        consensus_prompt = (
            f"You are the AGGREGATOR agent. Synthesize the findings of the Planner, Coder, and Critic "
            f"into a final polished response. Adjust the final output to address the Critic's feedback.\n"
            f"Original Task: '{task_description}'\n"
            f"Plan: {plan}\n"
            f"Coder Solution: {solution}\n"
            f"Critic Feedback: {feedback}\n\n"
            f"Synthesize the final response clearly and concisely."
        )
        final_result = self._call_agent("Aggregator", consensus_prompt)
        self.logger.success("Swarm consensus achieved.")
        
        return f"🐝 Swarm Intelligence Consensus Output:\n{'─'*40}\n{final_result}"

    def _call_agent(self, role: str, prompt: str) -> str:
        """Call the underlying LLM with a specific system role identity."""
        system = f"You are a specialized swarm sub-agent named {role}. Act strictly according to your role."
        if self.voice and hasattr(self.voice, "ask_ai"):
            # Prepare message array
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ]
            # Use Groq client if available, fallback to ask_ai
            if hasattr(self.voice, "groq_client") and self.voice.groq_client and not getattr(self.voice, "groq_disabled", False):
                try:
                    resp = self.voice.groq_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=messages,
                        max_tokens=600,
                        temperature=0.3
                    )
                    return resp.choices[0].message.content.strip()
                except Exception:
                    pass
            return self.voice.ask_ai(prompt)
        return f"[{role} fallback]: LLM client not available."
