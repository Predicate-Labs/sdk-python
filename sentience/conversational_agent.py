"""
Conversational Agent: Natural language interface for Sentience SDK
Enables end users to control web automation using plain English
"""

import json
import time
from typing import Dict, Any, List, Optional
from .llm_provider import LLMProvider, LLMResponse
from .browser import SentienceBrowser
from .agent import SentienceAgent
from .snapshot import snapshot
from .models import Snapshot


class ConversationalAgent:
    """
    Natural language agent that translates user intent into SDK actions
    and returns human-readable results.

    This is Layer 4 - the highest abstraction level for non-technical users.

    Example:
        >>> agent = ConversationalAgent(browser, llm)
        >>> result = agent.execute("Search for magic mouse on google.com")
        >>> print(result)
        "I searched for 'magic mouse' on Google and found several results.
         The top result is from amazon.com selling the Apple Magic Mouse 2 for $79."
    """

    def __init__(
        self,
        browser: SentienceBrowser,
        llm: LLMProvider,
        verbose: bool = True
    ):
        """
        Initialize conversational agent

        Args:
            browser: SentienceBrowser instance
            llm: LLM provider (OpenAI, Anthropic, LocalLLM, etc.)
            verbose: Print step-by-step execution logs (default: True)
        """
        self.browser = browser
        self.llm = llm
        self.verbose = verbose

        # Underlying technical agent
        self.technical_agent = SentienceAgent(browser, llm, verbose=False)

        # Conversation history and context
        self.conversation_history: List[Dict[str, Any]] = []
        self.execution_context: Dict[str, Any] = {
            "current_url": None,
            "last_action": None,
            "discovered_elements": [],
            "session_data": {}
        }

    def execute(self, user_input: str) -> str:
        """
        Execute a natural language command and return natural language result

        Args:
            user_input: Natural language instruction (e.g., "Search for magic mouse")

        Returns:
            Human-readable result description

        Example:
            >>> agent.execute("Go to google.com and search for magic mouse")
            "I navigated to google.com, searched for 'magic mouse', and found 10 results.
             The top result is from amazon.com selling Magic Mouse 2 for $79."
        """
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"👤 User: {user_input}")
            print(f"{'='*70}")

        start_time = time.time()

        # Step 1: Plan the execution (break down into atomic steps)
        plan = self._create_plan(user_input)

        if self.verbose:
            print(f"\n📋 Execution Plan:")
            for i, step in enumerate(plan['steps'], 1):
                print(f"  {i}. {step['description']}")

        # Step 2: Execute each step
        execution_results = []
        for step in plan['steps']:
            step_result = self._execute_step(step)
            execution_results.append(step_result)

            if not step_result.get('success', False):
                # Early exit on failure
                if self.verbose:
                    print(f"⚠️  Step failed: {step['description']}")
                break

        # Step 3: Synthesize natural language response
        response = self._synthesize_response(user_input, plan, execution_results)

        duration_ms = int((time.time() - start_time) * 1000)

        # Step 4: Update conversation history
        self.conversation_history.append({
            "user_input": user_input,
            "plan": plan,
            "results": execution_results,
            "response": response,
            "duration_ms": duration_ms
        })

        if self.verbose:
            print(f"\n🤖 Agent: {response}")
            print(f"⏱️  Completed in {duration_ms}ms\n")

        return response

    def _create_plan(self, user_input: str) -> Dict[str, Any]:
        """
        Use LLM to break down user input into atomic executable steps

        Args:
            user_input: Natural language command

        Returns:
            Plan dictionary with list of atomic steps
        """
        # Get current page context
        current_url = self.browser.page.url if self.browser.page else "None"

        system_prompt = """You are a web automation planning assistant.

Your job is to analyze a natural language request and break it down into atomic steps
that can be executed by a web automation agent.

AVAILABLE ACTIONS:
1. NAVIGATE - Go to a URL
2. FIND_AND_CLICK - Find and click an element by description
3. FIND_AND_TYPE - Find input field and type text
4. PRESS_KEY - Press a keyboard key (Enter, Escape, etc.)
5. WAIT - Wait for page to load or element to appear
6. EXTRACT_INFO - Extract specific information from the page
7. VERIFY - Verify a condition is met

RESPONSE FORMAT (JSON):
{
  "intent": "brief summary of user intent",
  "steps": [
    {
      "action": "NAVIGATE" | "FIND_AND_CLICK" | "FIND_AND_TYPE" | "PRESS_KEY" | "WAIT" | "EXTRACT_INFO" | "VERIFY",
      "description": "human-readable description",
      "parameters": {
        "url": "https://...",
        "element_description": "search box",
        "text": "magic mouse",
        "key": "Enter",
        "duration": 2.0,
        "info_type": "product link",
        "condition": "page contains results"
      }
    }
  ],
  "expected_outcome": "what success looks like"
}

IMPORTANT: Return ONLY valid JSON, no markdown, no code blocks."""

        user_prompt = f"""Current URL: {current_url}

User Request: {user_input}

Create a step-by-step execution plan."""

        try:
            response = self.llm.generate(
                system_prompt,
                user_prompt,
                json_mode=self.llm.supports_json_mode(),
                temperature=0.0
            )

            # Parse JSON response
            plan = json.loads(response.content)
            return plan

        except json.JSONDecodeError as e:
            # Fallback: create simple plan
            if self.verbose:
                print(f"⚠️  JSON parsing failed, using fallback plan: {e}")

            return {
                "intent": user_input,
                "steps": [
                    {
                        "action": "FIND_AND_CLICK",
                        "description": user_input,
                        "parameters": {"element_description": user_input}
                    }
                ],
                "expected_outcome": "Complete user request"
            }

    def _execute_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single atomic step from the plan

        Args:
            step: Step dictionary with action and parameters

        Returns:
            Execution result with success status and data
        """
        action = step['action']
        params = step.get('parameters', {})

        if self.verbose:
            print(f"\n⚙️  Executing: {step['description']}")

        try:
            if action == "NAVIGATE":
                url = params['url']
                # Add https:// if missing
                if not url.startswith(('http://', 'https://')):
                    url = 'https://' + url

                self.browser.page.goto(url, wait_until="domcontentloaded")
                self.execution_context['current_url'] = url
                time.sleep(1)  # Brief wait for page to settle

                return {
                    "success": True,
                    "action": action,
                    "data": {"url": url}
                }

            elif action == "FIND_AND_CLICK":
                element_desc = params['element_description']
                # Use technical agent to find and click (returns AgentActionResult)
                result = self.technical_agent.act(f"Click the {element_desc}")
                return {
                    "success": result.success,  # Use attribute access
                    "action": action,
                    "data": result.model_dump()  # Convert to dict for flexibility
                }

            elif action == "FIND_AND_TYPE":
                element_desc = params['element_description']
                text = params['text']
                # Use technical agent to find input and type (returns AgentActionResult)
                result = self.technical_agent.act(f"Type '{text}' into {element_desc}")
                return {
                    "success": result.success,  # Use attribute access
                    "action": action,
                    "data": {"text": text, "result": result.model_dump()}
                }

            elif action == "PRESS_KEY":
                key = params['key']
                result = self.technical_agent.act(f"Press {key} key")
                return {
                    "success": result.success,  # Use attribute access
                    "action": action,
                    "data": {"key": key, "result": result.model_dump()}
                }

            elif action == "WAIT":
                duration = params.get('duration', 2.0)
                time.sleep(duration)
                return {
                    "success": True,
                    "action": action,
                    "data": {"duration": duration}
                }

            elif action == "EXTRACT_INFO":
                info_type = params['info_type']
                # Get current page snapshot and extract info
                snap = snapshot(self.browser, limit=50)

                # Use LLM to extract specific information
                extracted = self._extract_information(snap, info_type)

                return {
                    "success": True,
                    "action": action,
                    "data": {"extracted": extracted, "info_type": info_type}
                }

            elif action == "VERIFY":
                condition = params['condition']
                # Verify condition using current page state
                is_verified = self._verify_condition(condition)
                return {
                    "success": is_verified,
                    "action": action,
                    "data": {"condition": condition, "verified": is_verified}
                }

            else:
                raise ValueError(f"Unknown action: {action}")

        except Exception as e:
            if self.verbose:
                print(f"❌ Step failed: {e}")
            return {
                "success": False,
                "action": action,
                "error": str(e)
            }

    def _extract_information(self, snap: Snapshot, info_type: str) -> Dict[str, Any]:
        """
        Extract specific information from snapshot using LLM

        Args:
            snap: Snapshot object
            info_type: Type of info to extract (e.g., "product link", "price")

        Returns:
            Extracted information dictionary
        """
        # Build context from snapshot
        elements_text = "\n".join([
            f"[{el.id}] {el.role}: {el.text} (importance: {el.importance})"
            for el in snap.elements[:30]  # Top 30 elements
        ])

        system_prompt = f"""Extract {info_type} from the following page elements.

ELEMENTS:
{elements_text}

Return JSON with extracted information:
{{
  "found": true/false,
  "data": {{
    // extracted information fields
  }},
  "summary": "brief description of what was found"
}}"""

        user_prompt = f"Extract {info_type} from the elements above."

        try:
            response = self.llm.generate(
                system_prompt,
                user_prompt,
                json_mode=self.llm.supports_json_mode()
            )
            return json.loads(response.content)
        except:
            return {"found": False, "data": {}, "summary": "Failed to extract information"}

    def _verify_condition(self, condition: str) -> bool:
        """
        Verify a condition is met on current page

        Args:
            condition: Natural language condition to verify

        Returns:
            True if condition is met, False otherwise
        """
        try:
            snap = snapshot(self.browser, limit=30)

            # Build context
            elements_text = "\n".join([
                f"{el.role}: {el.text}"
                for el in snap.elements[:20]
            ])

            system_prompt = f"""Verify if the following condition is met based on page elements.

CONDITION: {condition}

PAGE ELEMENTS:
{elements_text}

Return JSON:
{{
  "verified": true/false,
  "reasoning": "explanation"
}}"""

            response = self.llm.generate(
                system_prompt,
                "",
                json_mode=self.llm.supports_json_mode()
            )
            result = json.loads(response.content)
            return result.get('verified', False)
        except:
            return False

    def _synthesize_response(
        self,
        user_input: str,
        plan: Dict[str, Any],
        execution_results: List[Dict[str, Any]]
    ) -> str:
        """
        Synthesize a natural language response from execution results

        Args:
            user_input: Original user input
            plan: Execution plan
            execution_results: List of step execution results

        Returns:
            Human-readable response string
        """
        # Build summary of what happened
        successful_steps = [r for r in execution_results if r.get('success')]
        failed_steps = [r for r in execution_results if not r.get('success')]

        # Extract key data
        extracted_data = []
        for result in execution_results:
            if result.get('action') == 'EXTRACT_INFO':
                extracted_data.append(result.get('data', {}).get('extracted', {}))

        # Use LLM to create natural response
        system_prompt = """You are a helpful assistant that summarizes web automation results
in natural, conversational language.

Your job is to take technical execution results and convert them into a friendly,
human-readable response that answers the user's original request.

Be concise but informative. Include key findings or data discovered.
If the task failed, explain what went wrong in simple terms.

IMPORTANT: Return only the natural language response, no JSON, no markdown."""

        results_summary = {
            "user_request": user_input,
            "plan_intent": plan.get('intent'),
            "total_steps": len(execution_results),
            "successful_steps": len(successful_steps),
            "failed_steps": len(failed_steps),
            "extracted_data": extracted_data,
            "final_url": self.browser.page.url if self.browser.page else None
        }

        user_prompt = f"""Summarize these automation results in 1-3 natural sentences:

{json.dumps(results_summary, indent=2)}

Respond as if you're talking to a user, not listing technical details."""

        try:
            response = self.llm.generate(system_prompt, user_prompt, temperature=0.3)
            return response.content.strip()
        except:
            # Fallback response
            if failed_steps:
                return f"I attempted to {user_input}, but encountered an error during execution."
            else:
                return f"I completed your request: {user_input}"

    def chat(self, message: str) -> str:
        """
        Conversational interface with context awareness

        Args:
            message: User message (can reference previous context)

        Returns:
            Agent response

        Example:
            >>> agent.chat("Go to google.com")
            "I've navigated to google.com"
            >>> agent.chat("Search for magic mouse")  # Contextual
            "I searched for 'magic mouse' and found 10 results"
        """
        return self.execute(message)

    def get_summary(self) -> str:
        """
        Get a summary of the entire conversation/session

        Returns:
            Natural language summary of all actions taken
        """
        if not self.conversation_history:
            return "No actions have been performed yet."

        system_prompt = """Summarize this web automation session in a brief, natural paragraph.
Focus on what was accomplished and key findings."""

        session_data = {
            "total_interactions": len(self.conversation_history),
            "actions": [
                {
                    "request": h['user_input'],
                    "outcome": h['response']
                }
                for h in self.conversation_history
            ]
        }

        user_prompt = f"Summarize this session:\n{json.dumps(session_data, indent=2)}"

        try:
            summary = self.llm.generate(system_prompt, user_prompt)
            return summary.content.strip()
        except:
            return f"Session with {len(self.conversation_history)} interactions completed."

    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history.clear()
        self.technical_agent.clear_history()
        self.execution_context = {
            "current_url": None,
            "last_action": None,
            "discovered_elements": [],
            "session_data": {}
        }
