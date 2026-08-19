import os
import re
import json
import time
import uuid
import threading
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app.llm_prompts import SYSTEM_PROMPT, build_evidence_user_prompt

# Read configuration from environment
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")

_default_provider = "groq" if GROQ_API_KEY else "ollama"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", _default_provider).lower()

_default_model = "openai/gpt-oss-120b" if LLM_PROVIDER in ("groq", "openai") else "llama3.2:3b"
LLM_MODEL = os.getenv("LLM_MODEL", os.getenv("GROQ_MODEL", _default_model))
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

# Global in-memory dictionary for tracking async LLM request statuses & results
ASYNC_EXPLANATIONS: Dict[str, Dict[str, Any]] = {}


class LLMExplanationService:
    """
    Cloud-ready Evidence-Grounded LLM Explanation Service.
    Supports Groq API (e.g. openai/gpt-oss-120b, llama-3.3-70b), OpenAI-compatible endpoints,
    and local Ollama instances.
    Provides explanatory analysis of verified deterministic evidence packages without modifying decisions.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None
    ):
        self.provider = (provider or LLM_PROVIDER).lower()
        self.api_key = api_key if api_key is not None else GROQ_API_KEY
        if self.provider in ("groq", "openai"):
            self.base_url = (base_url or GROQ_BASE_URL).rstrip("/")
        else:
            self.base_url = (base_url or OLLAMA_BASE_URL).rstrip("/")
        self.model = model or LLM_MODEL
        self.timeout = timeout or LLM_TIMEOUT_SECONDS

    def generate_explanation(self, issue_type: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send structured evidence package to the configured LLM provider (Groq / Ollama)
        and return structured explanatory JSON.
        Handles connection errors, timeouts, invalid JSON, and returns graceful fallback.
        """
        start_time = time.time()
        user_prompt = build_evidence_user_prompt(issue_type, evidence)

        try:
            if self.provider in ("groq", "openai"):
                return self._generate_groq_openai(issue_type, user_prompt, start_time)
            else:
                return self._generate_ollama(issue_type, user_prompt, start_time)
        except (urllib.error.URLError, TimeoutError, Exception) as err:
            return self._fallback_response(f"{self.provider.capitalize()} connection error: {str(err)}", issue_type=issue_type)

    def _generate_groq_openai(self, issue_type: str, user_prompt: str, start_time: float) -> Dict[str, Any]:
        """Send chat completion request to Groq / OpenAI-compatible endpoint."""
        generate_url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "ClaimAssist-AI/1.0"
        }

        req = urllib.request.Request(
            generate_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            if response.status != 200:
                return self._fallback_response(f"HTTP error {response.status}", issue_type=issue_type)

            raw_bytes = response.read()
            res_data = json.loads(raw_bytes.decode("utf-8"))
            choices = res_data.get("choices", [])
            if choices and isinstance(choices, list) and len(choices) > 0:
                llm_text = choices[0].get("message", {}).get("content", "").strip()
            else:
                llm_text = res_data.get("response", "").strip()

            end_time = time.time()
            latency_ms = round((end_time - start_time) * 1000, 2)
            return self._parse_llm_json(llm_text, issue_type, latency_ms)

    def _generate_ollama(self, issue_type: str, user_prompt: str, start_time: float) -> Dict[str, Any]:
        """Send generation request to local Ollama API."""
        full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"
        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "format": "json",
            "stream": False
        }
        generate_url = f"{self.base_url}/api/generate"

        req = urllib.request.Request(
            generate_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            if response.status != 200:
                return self._fallback_response(f"HTTP error {response.status}", issue_type=issue_type)

            raw_bytes = response.read()
            res_data = json.loads(raw_bytes.decode("utf-8"))
            llm_text = res_data.get("response", "").strip()
            if not llm_text:
                choices = res_data.get("choices", [])
                if choices and isinstance(choices, list) and len(choices) > 0:
                    llm_text = choices[0].get("message", {}).get("content", "").strip()

            end_time = time.time()
            latency_ms = round((end_time - start_time) * 1000, 2)
            return self._parse_llm_json(llm_text, issue_type, latency_ms)

    def _parse_llm_json(self, llm_text: str, issue_type: str, latency_ms: float) -> Dict[str, Any]:
        """Clean and parse JSON output from the LLM model."""
        clean_text = re.sub(r"^```(?:json)?\s*", "", llm_text.strip(), flags=re.MULTILINE)
        clean_text = re.sub(r"```\s*$", "", clean_text.strip())

        try:
            parsed_json = json.loads(clean_text)
            confidence = float(parsed_json.get("confidence", 0.90))
            confidence = max(0.0, min(1.0, confidence))

            return {
                "status": "SUCCESS",
                "issue_type": issue_type,
                "likely_cause": str(parsed_json.get("likely_cause", "Likely cause based on evidence.")),
                "business_impact": str(parsed_json.get("business_impact", "Downstream operational impact.")),
                "recommended_fix": str(parsed_json.get("recommended_fix", "Recommended operational action.")),
                "evidence_used": list(parsed_json.get("evidence_used", [])),
                "confidence": confidence,
                "provider": self.provider,
                "model": self.model,
                "latency_ms": latency_ms
            }
        except (json.JSONDecodeError, TypeError):
            return {
                "status": "SUCCESS",
                "issue_type": issue_type,
                "likely_cause": llm_text[:300] if llm_text else "Explanation derived from system evidence.",
                "business_impact": "Review operational analytics for potential workflow adjustments.",
                "recommended_fix": "Audit data quality and rule configuration.",
                "evidence_used": [f"Issue Type: {issue_type}"],
                "confidence": 0.85,
                "provider": self.provider,
                "model": self.model,
                "latency_ms": latency_ms
            }

    def _fallback_response(self, error_message: str, issue_type: str = "GENERAL") -> Dict[str, Any]:
        """Graceful fallback response when LLM service is offline or unreachable."""
        return {
            "status": "LLM_UNAVAILABLE",
            "issue_type": issue_type,
            "likely_cause": None,
            "business_impact": None,
            "recommended_fix": None,
            "evidence_used": [],
            "confidence": 0.0,
            "message": f"LLM explanation service is currently unavailable. ({error_message})",
            "provider": self.provider,
            "model": self.model
        }


def start_async_explanation(
    issue_type: str,
    evidence: Dict[str, Any],
    reference_id: Optional[str] = None,
    db_session_factory=None
) -> str:
    """
    Launch asynchronous LLM explanation task in background thread.
    Returns request_id immediately without blocking caller or HTTP request.
    """
    req_id = f"req_{uuid.uuid4().hex[:12]}"
    ASYNC_EXPLANATIONS[req_id] = {
        "status": "PROCESSING",
        "request_id": req_id,
        "reference_id": reference_id,
        "issue_type": issue_type,
        "started_at": time.time()
    }

    def _worker():
        service = LLMExplanationService()
        result = service.generate_explanation(issue_type, evidence)
        result["request_id"] = req_id
        result["reference_id"] = reference_id

        # Update in-memory status
        ASYNC_EXPLANATIONS[req_id] = result

        # Save to database if session factory is available
        if db_session_factory:
            try:
                db = db_session_factory()
                try:
                    from app.database import save_llm_explanation_record
                    save_llm_explanation_record(db, result, reference_id=reference_id)
                finally:
                    db.close()
            except Exception as err:
                print(f"Error persisting async LLM record to database: {err}")

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return req_id


def get_async_explanation_status(request_id: str, db=None) -> Dict[str, Any]:
    """
    Query current status of an async LLM explanation request.
    Checks memory dictionary first, then falls back to database records.
    """
    if request_id in ASYNC_EXPLANATIONS:
        return ASYNC_EXPLANATIONS[request_id]

    if db:
        try:
            from app.database import LLMExplanationRecord
            rec = db.query(LLMExplanationRecord).filter(
                (LLMExplanationRecord.reference_id == request_id) | 
                (LLMExplanationRecord.id == int(request_id) if request_id.isdigit() else False)
            ).first()
            if rec:
                return rec.to_dict()
        except Exception:
            pass

    return {
        "status": "NOT_FOUND",
        "request_id": request_id,
        "message": f"Explanation request {request_id} not found."
    }


def warmup_ollama_non_blocking():
    """Non-blocking background thread worker to test/warmup LLM service at FastAPI startup."""
    def _warmup_task():
        try:
            service = LLMExplanationService()
            if service.provider in ("groq", "openai") and service.api_key:
                print(f"[LLM] Connected to Groq provider with model '{service.model}'.")
            elif service.provider == "ollama":
                url = f"{OLLAMA_BASE_URL}/api/generate"
                payload = {"model": service.model, "prompt": "ping", "stream": False}
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    pass
                print(f"[LLM] Ollama {service.model} warm-up successful.")
        except Exception:
            print("[LLM] LLM warm-up skipped. Startup proceeding normally.")

    t = threading.Thread(target=_warmup_task, daemon=True)
    t.start()
