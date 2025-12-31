"""
LLM Provider abstraction layer for Sentience SDK
Enables "Bring Your Own Brain" (BYOB) pattern - plug in any LLM provider
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Standardized LLM response across all providers"""

    content: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    model_name: str | None = None
    finish_reason: str | None = None


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Implement this interface to add support for any LLM:
    - OpenAI (GPT-4, GPT-3.5)
    - Anthropic (Claude)
    - Local models (Ollama, LlamaCpp)
    - Azure OpenAI
    - Any other completion API
    """

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> LLMResponse:
        """
        Generate a response from the LLM

        Args:
            system_prompt: System instruction/context
            user_prompt: User query/request
            **kwargs: Provider-specific parameters (temperature, max_tokens, etc.)

        Returns:
            LLMResponse with content and token usage
        """
        pass

    @abstractmethod
    def supports_json_mode(self) -> bool:
        """
        Whether this provider supports structured JSON output

        Returns:
            True if provider has native JSON mode, False otherwise
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """
        Model identifier (e.g., "gpt-4o", "claude-3-sonnet")

        Returns:
            Model name string
        """
        pass


class OpenAIProvider(LLMProvider):
    """
    OpenAI provider implementation (GPT-4, GPT-4o, GPT-3.5-turbo, etc.)

    Example:
        >>> from sentience.llm_provider import OpenAIProvider
        >>> llm = OpenAIProvider(api_key="sk-...", model="gpt-4o")
        >>> response = llm.generate("You are a helpful assistant", "Hello!")
        >>> print(response.content)
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
        base_url: str | None = None,
        organization: str | None = None,
    ):
        """
        Initialize OpenAI provider

        Args:
            api_key: OpenAI API key (or set OPENAI_API_KEY env var)
            model: Model name (gpt-4o, gpt-4-turbo, gpt-3.5-turbo, etc.)
            base_url: Custom API base URL (for compatible APIs)
            organization: OpenAI organization ID
        """
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("OpenAI package not installed. Install with: pip install openai")

        self.client = OpenAI(api_key=api_key, base_url=base_url, organization=organization)
        self._model_name = model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        json_mode: bool = False,
        **kwargs,
    ) -> LLMResponse:
        """
        Generate response using OpenAI API

        Args:
            system_prompt: System instruction
            user_prompt: User query
            temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative)
            max_tokens: Maximum tokens to generate
            json_mode: Enable JSON response format (requires model support)
            **kwargs: Additional OpenAI API parameters

        Returns:
            LLMResponse object
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        # Build API parameters
        api_params = {
            "model": self._model_name,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            api_params["max_tokens"] = max_tokens

        if json_mode and self.supports_json_mode():
            api_params["response_format"] = {"type": "json_object"}

        # Merge additional parameters
        api_params.update(kwargs)

        # Call OpenAI API
        response = self.client.chat.completions.create(**api_params)

        choice = response.choices[0]
        usage = response.usage

        return LLMResponse(
            content=choice.message.content,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            total_tokens=usage.total_tokens if usage else None,
            model_name=response.model,
            finish_reason=choice.finish_reason,
        )

    def supports_json_mode(self) -> bool:
        """OpenAI models support JSON mode (GPT-4, GPT-3.5-turbo)"""
        model_lower = self._model_name.lower()
        return any(x in model_lower for x in ["gpt-4", "gpt-3.5"])

    @property
    def model_name(self) -> str:
        return self._model_name


class AnthropicProvider(LLMProvider):
    """
    Anthropic provider implementation (Claude 3 Opus, Sonnet, Haiku, etc.)

    Example:
        >>> from sentience.llm_provider import AnthropicProvider
        >>> llm = AnthropicProvider(api_key="sk-ant-...", model="claude-3-sonnet-20240229")
        >>> response = llm.generate("You are a helpful assistant", "Hello!")
        >>> print(response.content)
    """

    def __init__(self, api_key: str | None = None, model: str = "claude-3-5-sonnet-20241022"):
        """
        Initialize Anthropic provider

        Args:
            api_key: Anthropic API key (or set ANTHROPIC_API_KEY env var)
            model: Model name (claude-3-opus, claude-3-sonnet, claude-3-haiku, etc.)
        """
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError(
                "Anthropic package not installed. Install with: pip install anthropic"
            )

        self.client = Anthropic(api_key=api_key)
        self._model_name = model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs,
    ) -> LLMResponse:
        """
        Generate response using Anthropic API

        Args:
            system_prompt: System instruction
            user_prompt: User query
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate (required by Anthropic)
            **kwargs: Additional Anthropic API parameters

        Returns:
            LLMResponse object
        """
        # Build API parameters
        api_params = {
            "model": self._model_name,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        if system_prompt:
            api_params["system"] = system_prompt

        # Merge additional parameters
        api_params.update(kwargs)

        # Call Anthropic API
        response = self.client.messages.create(**api_params)

        content = response.content[0].text if response.content else ""

        return LLMResponse(
            content=content,
            prompt_tokens=response.usage.input_tokens if hasattr(response, "usage") else None,
            completion_tokens=response.usage.output_tokens if hasattr(response, "usage") else None,
            total_tokens=(
                (response.usage.input_tokens + response.usage.output_tokens)
                if hasattr(response, "usage")
                else None
            ),
            model_name=response.model,
            finish_reason=response.stop_reason,
        )

    def supports_json_mode(self) -> bool:
        """Anthropic doesn't have native JSON mode (requires prompt engineering)"""
        return False

    @property
    def model_name(self) -> str:
        return self._model_name


class GLMProvider(LLMProvider):
    """
    Zhipu AI GLM provider implementation (GLM-4, GLM-4-Plus, etc.)

    Requirements:
        pip install zhipuai

    Example:
        >>> from sentience.llm_provider import GLMProvider
        >>> llm = GLMProvider(api_key="your-api-key", model="glm-4-plus")
        >>> response = llm.generate("You are a helpful assistant", "Hello!")
        >>> print(response.content)
    """

    def __init__(self, api_key: str | None = None, model: str = "glm-4-plus"):
        """
        Initialize GLM provider

        Args:
            api_key: Zhipu AI API key (or set GLM_API_KEY env var)
            model: Model name (glm-4-plus, glm-4, glm-4-air, glm-4-flash, etc.)
        """
        try:
            from zhipuai import ZhipuAI
        except ImportError:
            raise ImportError("ZhipuAI package not installed. Install with: pip install zhipuai")

        self.client = ZhipuAI(api_key=api_key)
        self._model_name = model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Generate response using GLM API

        Args:
            system_prompt: System instruction
            user_prompt: User query
            temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional GLM API parameters

        Returns:
            LLMResponse object
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        # Build API parameters
        api_params = {
            "model": self._model_name,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            api_params["max_tokens"] = max_tokens

        # Merge additional parameters
        api_params.update(kwargs)

        # Call GLM API
        response = self.client.chat.completions.create(**api_params)

        choice = response.choices[0]
        usage = response.usage

        return LLMResponse(
            content=choice.message.content,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            total_tokens=usage.total_tokens if usage else None,
            model_name=response.model,
            finish_reason=choice.finish_reason,
        )

    def supports_json_mode(self) -> bool:
        """GLM-4 models support JSON mode"""
        return "glm-4" in self._model_name.lower()

    @property
    def model_name(self) -> str:
        return self._model_name


class GeminiProvider(LLMProvider):
    """
    Google Gemini provider implementation (Gemini 2.0, Gemini 1.5 Pro, etc.)

    Requirements:
        pip install google-generativeai

    Example:
        >>> from sentience.llm_provider import GeminiProvider
        >>> llm = GeminiProvider(api_key="your-api-key", model="gemini-2.0-flash-exp")
        >>> response = llm.generate("You are a helpful assistant", "Hello!")
        >>> print(response.content)
    """

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.0-flash-exp"):
        """
        Initialize Gemini provider

        Args:
            api_key: Google API key (or set GEMINI_API_KEY or GOOGLE_API_KEY env var)
            model: Model name (gemini-2.0-flash-exp, gemini-1.5-pro, gemini-1.5-flash, etc.)
        """
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "Google Generative AI package not installed. Install with: pip install google-generativeai"
            )

        # Configure API key
        if api_key:
            genai.configure(api_key=api_key)
        else:
            import os

            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)

        self.genai = genai
        self._model_name = model
        self.model = genai.GenerativeModel(model)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Generate response using Gemini API

        Args:
            system_prompt: System instruction
            user_prompt: User query
            temperature: Sampling temperature (0.0 = deterministic, 2.0 = very creative)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional Gemini API parameters

        Returns:
            LLMResponse object
        """
        # Combine system and user prompts (Gemini doesn't have separate system role in all versions)
        full_prompt = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt

        # Build generation config
        generation_config = {
            "temperature": temperature,
        }

        if max_tokens:
            generation_config["max_output_tokens"] = max_tokens

        # Merge additional parameters
        generation_config.update(kwargs)

        # Call Gemini API
        response = self.model.generate_content(full_prompt, generation_config=generation_config)

        # Extract content
        content = response.text if response.text else ""

        # Token usage (if available)
        prompt_tokens = None
        completion_tokens = None
        total_tokens = None

        if hasattr(response, "usage_metadata") and response.usage_metadata:
            prompt_tokens = response.usage_metadata.prompt_token_count
            completion_tokens = response.usage_metadata.candidates_token_count
            total_tokens = response.usage_metadata.total_token_count

        return LLMResponse(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            model_name=self._model_name,
            finish_reason=None,  # Gemini uses different finish reason format
        )

    def supports_json_mode(self) -> bool:
        """Gemini 1.5+ models support JSON mode via response_mime_type"""
        model_lower = self._model_name.lower()
        return any(x in model_lower for x in ["gemini-1.5", "gemini-2.0"])

    @property
    def model_name(self) -> str:
        return self._model_name


class LocalLLMProvider(LLMProvider):
    """
    Local LLM provider using HuggingFace Transformers
    Supports Qwen, Llama, Gemma, Phi, and other instruction-tuned models

    Example:
        >>> from sentience.llm_provider import LocalLLMProvider
        >>> llm = LocalLLMProvider(model_name="Qwen/Qwen2.5-3B-Instruct")
        >>> response = llm.generate("You are helpful", "Hello!")
    """

    def __init__(
        self,
        model_name: str = "Qwen/Qwen2.5-3B-Instruct",
        device: str = "auto",
        load_in_4bit: bool = False,
        load_in_8bit: bool = False,
        torch_dtype: str = "auto",
    ):
        """
        Initialize local LLM using HuggingFace Transformers

        Args:
            model_name: HuggingFace model identifier
                Popular options:
                - "Qwen/Qwen2.5-3B-Instruct" (recommended, 3B params)
                - "meta-llama/Llama-3.2-3B-Instruct" (3B params)
                - "google/gemma-2-2b-it" (2B params)
                - "microsoft/Phi-3-mini-4k-instruct" (3.8B params)
            device: Device to run on ("cpu", "cuda", "mps", "auto")
            load_in_4bit: Use 4-bit quantization (saves 75% memory)
            load_in_8bit: Use 8-bit quantization (saves 50% memory)
            torch_dtype: Data type ("auto", "float16", "bfloat16", "float32")
        """
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        except ImportError:
            raise ImportError(
                "transformers and torch required for local LLM. "
                "Install with: pip install transformers torch"
            )

        self._model_name = model_name

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)

        # Set padding token if not present
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # Configure quantization
        quantization_config = None
        if load_in_4bit:
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )
        elif load_in_8bit:
            quantization_config = BitsAndBytesConfig(load_in_8bit=True)

        # Determine torch dtype
        if torch_dtype == "auto":
            dtype = torch.float16 if device != "cpu" else torch.float32
        else:
            dtype = getattr(torch, torch_dtype)

        # Load model
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            quantization_config=quantization_config,
            torch_dtype=dtype if quantization_config is None else None,
            device_map=device,
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )
        self.model.eval()

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 512,
        temperature: float = 0.1,
        top_p: float = 0.9,
        **kwargs,
    ) -> LLMResponse:
        """
        Generate response using local model

        Args:
            system_prompt: System instruction
            user_prompt: User query
            max_new_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0 = greedy, higher = more random)
            top_p: Nucleus sampling parameter
            **kwargs: Additional generation parameters

        Returns:
            LLMResponse object
        """
        import torch

        # Auto-determine sampling based on temperature
        do_sample = temperature > 0

        # Format prompt using model's chat template
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        # Use model's native chat template if available
        if hasattr(self.tokenizer, "apply_chat_template"):
            formatted_prompt = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        else:
            # Fallback formatting
            formatted_prompt = ""
            if system_prompt:
                formatted_prompt += f"System: {system_prompt}\n\n"
            formatted_prompt += f"User: {user_prompt}\n\nAssistant:"

        # Tokenize
        inputs = self.tokenizer(formatted_prompt, return_tensors="pt", truncation=True).to(
            self.model.device
        )

        input_length = inputs["input_ids"].shape[1]

        # Generate
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature if do_sample else 1.0,
                top_p=top_p,
                do_sample=do_sample,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                **kwargs,
            )

        # Decode only the new tokens
        generated_tokens = outputs[0][input_length:]
        response_text = self.tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()

        return LLMResponse(
            content=response_text,
            prompt_tokens=input_length,
            completion_tokens=len(generated_tokens),
            total_tokens=input_length + len(generated_tokens),
            model_name=self._model_name,
        )

    def supports_json_mode(self) -> bool:
        """Local models typically need prompt engineering for JSON"""
        return False

    @property
    def model_name(self) -> str:
        return self._model_name
