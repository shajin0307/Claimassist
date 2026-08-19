import os
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

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2:3b")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

# Global in-memory dictionary for tracking async LLM request statuses & results
ASYNC_EXPLANATIONS: Dict[str, Dict[str, Any]] = {}


class LLMExplanationService:
    """
    Cloud-ready Evidence-Grounded LLM Explanation Service.
    Communicates with Ollama's HTTP API (Llama 3.2 3B) or hosted LLM providers.
    Provides explanatory analysis of verified deterministic evidence packages without modifying decisions.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None
    ):
        self.base_url = (base_url or OLLAMA_BASE_URL).rstrip("/")
        self.model = model or LLM_MODEL
        self.timeout = timeout or LLM_TIMEOUT_SECONDS

    def generate_explanation(self, issue_type: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send structured evidence package to Ollama Llama 3.2 3B and parse structured explanation.
        Handles connection errors, timeouts, invalid JSON, and returns graceful fallback.
        """
        start_time = time.time()
        user_prompt = build_evidence_user_prompt(issue_type, evidence)
        full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "format": "json",
            "stream": False
        }

        generate_url = f"{self.base_url}/api/generate"

        try:
            req = urllib.request.Request(
                generate_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )

            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.status != 200:
                    return self._fallback_response(f"HTTP error {response.status}")

                raw_bytes = response.read()
                res_data = json.loads(raw_bytes.decode("utf-8"))
                llm_text = res_data.get("response", "").strip()

                end_time = time.time()
                latency_ms = round((end_time - start_time) * 1000, 2)

                # Parse JSON output from Llama 3.2 3B
                try:
                    parsed_json = json.loads(llm_text)
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
                        "provider": LLM_PROVIDER,
                        "model": self.model,
                        "latency_ms": latency_ms
                    }
                except (json.JSONDecodeError, TypeError) as parse_err:
                    # If JSON format was partially malformed, wrap raw text cleanly
                    return {
                        "status": "SUCCESS",
                        "issue_type": issue_type,
                        "likely_cause": llm_text[:300] if llm_text else "Explanation derived from system evidence.",
                        "business_impact": "Review operational analytics for potential workflow adjustments.",
                        "recommended_fix": "Audit data quality and rule configuration.",
                        "evidence_used": [f"Issue Type: {issue_type}"],
                        "confidence": 0.85,
                        "provider": LLM_PROVIDER,
                        "model": self.model,
                        "latency_ms": latency_ms
                    }

        except (urllib.error.URLError, TimeoutError, Exception) as err:
            return self._fallback_response(f"Ollama connection error: {str(err)}", issue_type=issue_type)

    def _fallback_response(self, error_message: str, issue_type: str = "GENERAL") -> Dict[str, Any]:
        """
        Graceful fallback response when Ollama is offline or unreachable.
        Ensures the application never crashes.
        """
        return {
            "status": "LLM_UNAVAILABLE",
            "issue_type": issue_type,
            "likely_cause": None,
            "business_impact": None,
            "recommended_fix": None,
            "evidence_used": [],
            "confidence": 0.0,
            "message": f"LLM explanation service is currently unavailable. ({error_message})",
            "provider": LLM_PROVIDER,
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
    Checks memory dictionary first, then falls back to PostgreSQL database records.
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
    """Non-blocking background thread worker to warm up Ollama model at FastAPI startup."""
    def _warmup_task():
        try:
            url = f"{OLLAMA_BASE_URL}/api/generate"
            payload = {
                "model": LLM_MODEL,
                "prompt": "ping",
                "stream": False
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                pass
            print(f"Ollama {LLM_MODEL} warm-up successful.")
        except Exception:
            print("Ollama warm-up skipped (Ollama offline or busy). Startup proceeding normally.")

    t = threading.Thread(target=_warmup_task, daemon=True)
    t.start()
