"""
Test script for LocalLLMProvider with Qwen2.5-3B-Instruct
Demonstrates using a local LLM with SentienceAgent
"""

from predicate.llm_provider import LocalLLMProvider


def test_local_llm_basic():
    """Test basic LLM response generation"""
    print("=" * 70)
    print("Testing LocalLLMProvider with Qwen2.5-3B-Instruct")
    print("=" * 70)

    # Initialize local LLM
    # Using the model from your local cache
    llm = LocalLLMProvider(
        model_name="Qwen/Qwen2.5-3B-Instruct",
        device="auto",  # Will use CUDA if available, else CPU
        load_in_4bit=False,  # Set to True to save memory
        torch_dtype="auto",
    )

    print("\n" + "=" * 70)
    print("Test 1: Simple question")
    print("=" * 70)

    response = llm.generate(
        system_prompt="You are a helpful web automation assistant.",
        user_prompt="What is 2+2?",
        max_new_tokens=50,
        temperature=0.1,
    )

    print(f"Response: {response.content}")
    print(
        f"Tokens: {response.total_tokens} (prompt: {response.prompt_tokens}, completion: {response.completion_tokens})"
    )

    print("\n" + "=" * 70)
    print("Test 2: Action parsing (for agent)")
    print("=" * 70)

    system_prompt = """You are an AI web automation agent.

GOAL: Click the search box

VISIBLE ELEMENTS (sorted by importance, max 50):
[1] <button> "Sign In" {PRIMARY,CLICKABLE,color:blue} @ (100,50) (Imp:900)
[2] <textbox> "" {CLICKABLE} @ (200,100) (Imp:850)
[3] <link> "Help" {} @ (50,150) (Imp:700)

VISUAL CUES:
- {PRIMARY}: Main call-to-action element
- {CLICKABLE}: Element is clickable
- {color:X}: Background color name

RESPONSE FORMAT (return ONLY the function call):
- CLICK(id) - Click element by ID
- TYPE(id, "text") - Type text into element
- PRESS("key") - Press keyboard key
- FINISH() - Task complete
"""

    user_prompt = "What is the next step to achieve the goal?"

    response = llm.generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_new_tokens=20,
        temperature=0.0,
    )

    print(f"Agent Response: {response.content}")
    print(f"Tokens: {response.total_tokens}")

    # Check if response is parseable
    if "CLICK(2)" in response.content or "click(2)" in response.content.lower():
        print("\n✅ SUCCESS: LLM correctly identified textbox (element 2) as search box!")
    else:
        print(f"\n⚠️  Response may need adjustment: {response.content}")

    print("\n" + "=" * 70)
    print("LocalLLMProvider Test Complete!")
    print("=" * 70)


if __name__ == "__main__":
    test_local_llm_basic()
